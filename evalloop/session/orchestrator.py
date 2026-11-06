"""The session orchestrator: watch, evaluate on change, publish state, serve a live dashboard.

``Session.tick`` is the whole loop made testable: snapshot the tree, and if anything changed since
last time, run the real ``evalloop.run.check`` loop and append a :class:`RunCard`. ``run_forever``
is that tick on an interval; ``serve`` exposes the state and the dashboard over a stdlib HTTP server
so the page (and the mascot) update themselves. Nothing here grades anything on its own — it only
drives the engine that M0/M1 already built.

Consent (decision EL-018): before a tick opens anything, it asks the :class:`ConsentGate`. Endpoints
with a saved or session approval run silently; new or expired ones are queued for the bot's
permission popup and published in ``status.json`` under ``consent``. The bot answers by POSTing to
``/consent/decide`` or ``/consent/revoke``. Those routes need ``Content-Type: application/json`` and
an ``X-EvalLoop-Bot`` header, which a web page cannot send to this port without a CORS preflight
the server never answers, so a browser tab cannot approve anything. Each tick also re-reads the
consent store, so ``evalloop consents revoke`` takes effect on a running session.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.capability.consent_store import store_for
from evalloop.classify.heuristics import classify_source
from evalloop.grade.agent_scaffold import SCAFFOLD_SUFFIX, scaffold_agent_eval
from evalloop.grade.dbcheck import check_file, find_sqlite
from evalloop.grade.specs import SPEC_SUFFIX, grade_spec_file
from evalloop.run import Author, RunResult, check
from evalloop.session.consent import Choice, ConsentGate, Resolution, discovered_requests, sqlite_request
from evalloop.session.dashboard import dashboard_html
from evalloop.session.poller import Snapshot, changed_files, snapshot
from evalloop.session.state import CaseCard, MascotState, RunCard, SessionState, worst_outcome
from evalloop.session.state import _OUTCOME_TO_MASCOT
from evalloop.vocab import Situation

__all__ = ["Session"]

# The engine the session drives. Injectable so a test can run the loop without real grading.
Evaluator = Callable[[str, str], RunResult]


def _default_evaluator(store_dir: str, author: "Author | None", calibrate_native: bool = False) -> Evaluator:
    def run(path: str, _store: str) -> RunResult:
        return check(path, store_dir=store_dir, author=author, calibrate_native=calibrate_native)

    return run


class Session:
    """Watch ``root``; on each change, evaluate and publish state. One instance per session."""

    def __init__(
        self,
        root: str | Path,
        *,
        store_dir: str | Path,
        evaluator: Evaluator | None = None,
        author: Author | None = None,
        calibrate_native: bool = False,
        clock: Callable[[], float] = time.time,
        consent: ConsentGate | None = None,
        caps: Caps | None = None,
    ) -> None:
        self.root = str(root)
        # Saved approvals load from <root>/.evalloop/consents.json; caps are what each request asks
        # for (EL-006: never defaulted, so unset unless the operator passes them).
        self.consent = consent if consent is not None else ConsentGate(CapabilityBroker(store=store_for(root)))
        self._caps = caps if caps is not None else Caps()
        self._store = str(store_dir)
        # calibrate_native: a tick whose sandbox run has failures also runs the repo's own pytest once,
        # unsandboxed, so a failure only the sandbox causes is withheld (evalloop.grade.native)
        self._evaluator = (
            evaluator if evaluator is not None else _default_evaluator(self._store, author, calibrate_native)
        )
        self._clock = clock
        self.state = SessionState(root=self.root, updated_at=clock())
        self._seen: Snapshot = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def tick(self) -> RunCard | None:
        """One pass: evaluate iff the tree changed since the last tick. Returns the last card, or None."""
        current = snapshot(self.root)
        trigger = changed_files(self._seen, current)
        first_run = not self._seen
        self._seen = current
        with self._lock:
            self.consent.broker.sync()  # pick up approvals revoked or added outside this session
            recheck, self.consent.changed = self.consent.changed, False
        if not trigger and not first_run:
            # nothing changed on disk, but a permission just granted unblocks the waiting DB check
            if not recheck:
                return None
            unblocked = self._consented_dbcheck((), current)
            for db_card in unblocked:
                self._record(db_card)
            return self._conclude(unblocked)
        if first_run or trigger:
            requests = discovered_requests(self.root, self._caps)
            with self._lock:
                self.consent.observe(requests)
        with self._lock:
            # name the in-flight target before the run, so the bot's thought cloud can show it
            self.state.current = trigger or ("the repository",)
            self.state.mascot = MascotState.evaluating

        # One tick can grade several things, each its own card; collect them so the headline can be
        # the WORST outcome found, not the last card recorded (see _conclude).
        produced: list[RunCard] = []

        def emit(card: RunCard) -> None:
            self._record(card)
            produced.append(card)

        py_trigger = tuple(f for f in trigger if f.endswith(".py"))

        # SQL / RAG / agent specs grade outside the Python-function path. Grade the ones whose own file
        # changed (or, on the first look, every spec under the tree) AND the ones whose referenced agent
        # module changed -- a behaviour/end-state spec depends on the code it runs, so editing that code
        # must re-grade the spec, not just the plain (undecidable) py-path.
        spec_rels = {f for f in (trigger or tuple(current)) if f.endswith(SPEC_SUFFIX)}
        spec_rels |= self._specs_for_changed_modules(py_trigger, current)
        for rel in sorted(spec_rels):
            emit(self._grade_spec(rel))

        # Auto DB-access validation: a changed .py that issues SQL, and a SQLite db in the tree -> run
        # the no-oracle layers (read-only / schema / executes / shape) against a read-only snapshot.
        # Only once the developer has allowed it: the popup asks first (EL-018).
        for db_card in self._consented_dbcheck(py_trigger, current):
            emit(db_card)

        # Agent files cannot be auto-graded yet (no resettable env / trajectory capture), and the
        # classifier can only flag them. So instead of silently ignoring one, drop a starter eval
        # scaffold beside it and surface it, rather than letting it fall through as "nothing to do".
        for rel in sorted(f for f in (py_trigger or tuple(current)) if f.endswith(".py")):
            card = self._agent_scaffold(rel)
            if card is not None:
                emit(card)

        # the Python-function path still grades the whole repo as before
        if py_trigger or first_run:
            try:
                result = self._evaluator(self.root, self._store)
                card = RunCard.from_result(result, trigger=py_trigger, at=self._clock())
            except Exception as exc:  # a bad run must never kill the watcher — record it and keep going
                card = RunCard.errored(exc, trigger=py_trigger, at=self._clock())
            # Don't let an empty "nothing in the function path" card (the usual result for an agent file,
            # which has no execution grader) sit ABOVE a real verdict from a spec/DB check in the same
            # tick — it reads as UNDECIDED on top and hides the actual PASS/FAIL. Keep it only when it
            # graded something, failed/errored, or is the only thing this tick produced.
            if card.cases or card.outcome in ("problem", "errored") or not produced:
                emit(card)
        return self._conclude(produced)

    def _conclude(self, produced: list[RunCard]) -> RunCard | None:
        """Pick the tick's headline: the single most severe card, and set the mascot to match.

        ``_record`` set the mascot per card as they came in, so after a multi-card tick it reflects
        whichever happened to be graded last. That is the bug this fixes: a developer needs to see
        the worst thing found (a PROBLEM on a data-access file), never the last thing graded (a
        CLEAN/UNDECIDED pass over the rest of the tree). PROBLEM wins the tick.
        """
        with self._lock:
            if not produced:
                return self.state.runs[0] if self.state.runs else None
            top = worst_outcome(card.outcome for card in produced)
            self.state.mascot = _OUTCOME_TO_MASCOT.get(top, MascotState.idle)
            # Return a representative card for that outcome — the first one in record order, which is
            # deterministic for a given tree and seed.
            return next(card for card in produced if card.outcome == top)

    def _record(self, card: RunCard) -> None:
        with self._lock:
            self.state.record(card)

    def _consented_dbcheck(self, py_trigger: tuple[str, ...], current: Snapshot) -> list[RunCard]:
        """Run the DB check over the repo's SQLite file, if one exists and its opening is allowed."""
        db = find_sqlite(self.root)
        if db is None:
            return []
        request = sqlite_request(self.root, db, self._caps)
        with self._lock:
            allowed = bool(self.consent.observe([request]))
        if not allowed:
            return []  # waiting in the popup, or denied this session: nothing is opened
        cards: list[RunCard] = []
        for rel in sorted(f for f in (py_trigger or tuple(current)) if f.endswith(".py")):
            card = self._dbcheck(rel, db)
            if card is not None:
                cards.append(card)
        return cards

    def decide(self, key: str, choice: Choice, typed: str = "") -> Resolution:
        """Apply the bot's answer to one pending permission request."""
        with self._lock:
            return self.consent.resolve(key, choice, typed)

    def revoke(self, key: str) -> bool:
        """Withdraw an approval from the Permissions view (also forgets it in the store)."""
        with self._lock:
            return self.consent.revoke(key)

    def _dbcheck(self, rel: str, db: "Path") -> RunCard | None:
        """Auto-validate a data-access .py's SQL, read-only, against the snapshot. None if no SQL."""
        try:
            db_cases = check_file(Path(self.root) / rel, db)
            if not db_cases:
                return None
            outcome = "problem" if any(c.verdict == "failed" for c in db_cases) else "clean"
            cards = tuple(CaseCard(artifact=rel, name=c.name, record="db_access", verdict=c.verdict,
                                   detail=c.detail, failure_class=c.category if c.verdict == "failed" else "",
                                   rung=None, kind="auto", oracle=db.name) for c in db_cases)
            return RunCard.from_spec("db", "db_access", outcome, cards, trigger=(rel,), at=self._clock())
        except Exception as exc:
            return RunCard.errored(exc, trigger=(rel,), at=self._clock())

    def _specs_for_changed_modules(self, py_trigger: tuple[str, ...], current: Snapshot) -> set[str]:
        """Specs whose referenced ``module`` is among the changed ``.py`` files — so editing an agent's
        code re-grades its spec. Empty when no ``.py`` changed."""
        if not py_trigger:
            return set()
        changed = set(py_trigger)
        out: set[str] = set()
        for rel in current:
            if not rel.endswith(SPEC_SUFFIX):
                continue
            module_rel = self._spec_module_rel(rel)
            if module_rel is not None and module_rel in changed:
                out.add(rel)
        return out

    def _spec_module_rel(self, spec_rel: str) -> str | None:
        """The repo-relative path of a spec's ``module`` field, or None if it has none / cannot resolve."""
        try:
            data = json.loads((Path(self.root) / spec_rel).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        module = data.get("module") if isinstance(data, dict) else None
        if not isinstance(module, str):
            return None
        spec_dir = (Path(self.root) / spec_rel).parent
        try:
            return (spec_dir / module).resolve().relative_to(Path(self.root).resolve()).as_posix()
        except (ValueError, OSError):
            return None

    def _agent_scaffold(self, rel: str) -> RunCard | None:
        """If ``rel`` classifies as an agent, write a starter eval scaffold beside it (once) and a card.

        None unless the file is an agent. If a real spec already exists it defers to that (the spec
        path grades it). The scaffold is written only when absent — a developer's edits are never
        overwritten — and is inert (``.scaffold``) until they activate it.
        """
        path = Path(self.root) / rel
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return None
        result = classify_source(source, name=path.name)
        if result.abstention is not None:
            return None
        if Situation.agent_action not in {situation for situation, _ in result.labels}:
            return None

        stem = path.name[:-3] if path.name.endswith(".py") else path.stem
        activated = path.with_name(f"{stem}.agent.eval.json")
        if activated.exists():
            return None  # a real agent spec exists; the spec path grades it, no scaffold needed

        scaffold = path.with_name(f"{stem}{SCAFFOLD_SUFFIX}")
        wrote = False
        if not scaffold.exists():
            try:
                scaffold.write_text(scaffold_agent_eval(rel, source), encoding="utf-8")
                wrote = True
            except OSError:
                pass
        scaffold_rel = scaffold.relative_to(self.root).as_posix()
        verb = "wrote a starter eval to" if wrote else "a starter eval is at"
        detail = (
            "looks like an agent (an LLM call inside a tool-dispatch loop); agents are graded by their "
            f"real end state, which I can't infer. {verb} {scaffold_rel} — fill in the end-state checks "
            "and drop the '.scaffold' suffix to grade it."
        )
        case = CaseCard(
            artifact=rel, name="agent detected — eval scaffold ready", record="agent_scaffold",
            verdict="inconclusive", detail=detail, failure_class="", rung=None, kind="scaffold",
            oracle=scaffold_rel,
        )
        return RunCard(
            run_id="scaffold:agent", outcome="undecided", trigger=(rel,), situations=("agent_action",),
            cases=(case,), permission_requests=(), at=self._clock(),
        )

    def _grade_spec(self, rel: str) -> RunCard:
        """Grade one ``*.eval.json`` spec into a card, turning any failure into an errored card."""
        try:
            spec = grade_spec_file(Path(self.root) / rel)
            cases = tuple(CaseCard(artifact=rel, name=c.name, record=spec.kind, verdict=c.verdict,
                                   detail=c.detail, failure_class="" if c.verdict != "failed" else spec.kind,
                                   rung=None, kind="spec", oracle=rel)
                          for c in spec.cases)
            return RunCard.from_spec(spec.kind, spec.situation, spec.outcome, cases, trigger=(rel,), at=self._clock())
        except Exception as exc:
            return RunCard.errored(exc, trigger=(rel,), at=self._clock())

    def snapshot_json(self) -> bytes:
        with self._lock:
            payload = self.state.to_json()
            payload["consent"] = self.consent.to_json()
            return json.dumps(payload).encode("utf-8")

    def run_forever(self, *, interval: float = 2.0) -> None:
        """Tick every ``interval`` seconds until :meth:`stop`. This is the blocking session loop."""
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(interval)

    def stop(self) -> None:
        self.state.watching = False
        self._stop.set()

    def serve(self, *, host: str = "127.0.0.1", port: int = 7420) -> ThreadingHTTPServer:
        """Start an HTTP server (in a daemon thread) that serves the dashboard and live state."""
        session = self
        page = dashboard_html().encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:  # silence the default stderr logging
                return

            def do_GET(self) -> None:  # noqa: N802 (http.server's required name)
                if self.path in ("/", "/index.html"):
                    body, ctype = page, "text/html; charset=utf-8"
                elif self.path.startswith("/status.json"):
                    body, ctype = session.snapshot_json(), "application/json"
                else:
                    self.send_error(404)
                    return
                self._reply(200, body, ctype)

            def do_POST(self) -> None:  # noqa: N802
                # A browser page cannot set this header cross-origin without a preflight we never
                # answer, so only the bot (or a deliberate local client) can approve or revoke.
                if self.headers.get("X-EvalLoop-Bot") is None or not (
                    self.headers.get("Content-Type", "").startswith("application/json")
                ):
                    self.send_error(403, "consent routes need the bot's header and a JSON body")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    data = json.loads(self.rfile.read(min(length, 65536)).decode("utf-8") or "{}")
                    key = str(data["key"])
                except (ValueError, KeyError, TypeError):
                    self.send_error(400, "expected a JSON object with a 'key'")
                    return
                if self.path == "/consent/decide":
                    try:
                        choice = Choice(str(data.get("choice", "")))
                    except ValueError:
                        self.send_error(400, "choice must be allow_once, allow_remember or deny")
                        return
                    result = session.decide(key, choice, str(data.get("typed", "")))
                    reply: dict[str, object] = {
                        "accepted": result.accepted, "granted": result.granted,
                        "remembered": result.remembered, "message": result.message,
                    }
                elif self.path == "/consent/revoke":
                    reply = {"revoked": session.revoke(key)}
                else:
                    self.send_error(404)
                    return
                self._reply(200, json.dumps(reply).encode("utf-8"), "application/json")

            def _reply(self, status: int, body: bytes, ctype: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer((host, port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
