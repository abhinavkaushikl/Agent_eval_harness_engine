"""Consent for the session: which endpoints may be opened, which need asking, and what the popup shows.

Decision ``EL-018``. Each tick the session turns what discovery found (EL-303, classified by EL-304)
into :class:`ConsentRequest` values and hands them to a :class:`ConsentGate`:

* an endpoint with a live grant (remembered in the store, or allowed once this session) runs
  **silently**;
* one denied this session (or revoked this session) is **not asked again** until the next session;
* anything else (new, or its approval expired) joins the **pending queue**, and the bot shows the
  popup for the head of the queue.

The popup's decision logic lives here, not in Tk: :func:`popup_model` says what the window shows and
which buttons it offers, and :func:`decide` turns a button press (plus any typed name) into a
:class:`Resolution`. The Tk code (:mod:`evalloop.session.consent_popup`) only draws that model and
posts the press, so all of this is tested without a window.

Production-suspected endpoints keep their rules (operator decision, EL-018): **default Deny**,
approval **only by typing the endpoint name**, and **never remembered**. The popup offers no
"remember" button for them, and :func:`decide` refuses to remember one even when asked, so it asks
again every session.

Which endpoints actually open
-----------------------------
The only connection a session makes today is the automatic, read-only SQLite check
(:mod:`evalloop.grade.dbcheck`), and it now waits for consent. Remote endpoints (Postgres, Qdrant,
…) are asked about and their approvals recorded, but the session has no credential resolution for
them yet, so an approval makes them *available* to the broker (``available_tools``) and opens
nothing. No credential is read: requests carry the credential **source** only.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from evalloop._compat import StrEnum
from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.classify_endpoint import Posture, classify
from evalloop.connect.discover import DATABASE, Candidate, Provenance
from evalloop.connect.scan import scan
from evalloop.vocab import Tool

__all__ = [
    "Choice",
    "ConsentGate",
    "ConsentRequest",
    "PopupModel",
    "Resolution",
    "decide",
    "discovered_requests",
    "popup_model",
    "sqlite_request",
]

_GRANTED_BY = "evalloop bot"


class Choice(StrEnum):
    """The three buttons. Production-suspected endpoints get two of them."""

    allow_once = "allow_once"
    allow_remember = "allow_remember"
    deny = "deny"


_LABEL = {Choice.allow_once: "Allow once", Choice.allow_remember: "Allow and remember", Choice.deny: "Deny"}


@dataclass(frozen=True, slots=True)
class ConsentRequest:
    """Everything the popup must show about one endpoint before it may be opened. Never a credential."""

    tool: Tool
    endpoint: str
    kind: str
    host: str | None
    database: str | None
    credential_source: str | None
    operations: tuple[str, ...]
    caps: Caps
    posture: Posture
    rationale: str
    default_deny: bool
    require_typed_confirmation: bool
    confirm_name: str
    found_at: str

    @property
    def key(self) -> str:
        return f"{self.tool.value}|{self.endpoint}"

    @property
    def production(self) -> bool:
        return self.posture is Posture.production_suspected

    def to_json(self) -> dict[str, object]:
        model = popup_model(self)
        return {
            "key": self.key,
            "tool": self.tool.value,
            "endpoint": self.endpoint,
            "posture": self.posture.value,
            "popup": model.to_json(),
        }


@dataclass(frozen=True, slots=True)
class PopupModel:
    """What the permission window shows, decided without Tk."""

    title: str
    rows: tuple[tuple[str, str], ...]
    warning: str | None
    buttons: tuple[Choice, ...]
    default: Choice
    needs_typed_name: bool
    typed_hint: str | None

    def label(self, choice: Choice) -> str:
        return _LABEL[choice]

    def to_json(self) -> dict[str, object]:
        return {
            "title": self.title,
            "rows": [list(row) for row in self.rows],
            "warning": self.warning,
            "buttons": [{"choice": b.value, "label": _LABEL[b]} for b in self.buttons],
            "default": self.default.value,
            "needs_typed_name": self.needs_typed_name,
            "typed_hint": self.typed_hint,
        }


@dataclass(frozen=True, slots=True)
class Resolution:
    """What a button press did. ``accepted=False`` means the popup stays open (e.g. a wrong name)."""

    accepted: bool
    granted: bool
    remembered: bool
    message: str


def _caps_line(caps: Caps) -> str:
    parts: list[str] = []
    parts.append(f"rows ≤ {caps.max_rows}" if caps.max_rows is not None else "rows: no cap set")
    parts.append(f"time ≤ {caps.max_seconds:g} s" if caps.max_seconds is not None else "time: no cap set")
    if caps.max_bytes is not None:
        parts.append(f"bytes ≤ {caps.max_bytes}")
    return " · ".join(parts)


def popup_model(request: ConsentRequest) -> PopupModel:
    """The window for one request: host, database/collection, credential source, operations, caps."""
    what = "collection" if request.tool is Tool.vector_store else "database"
    rows: list[tuple[str, str]] = [
        ("endpoint", request.endpoint),
        ("host", request.host or "not known until connected"),
        (what, request.database or "not known (it is inside the credential, which is never read)"),
        ("credential source", request.credential_source or "none (no credential needed)"),
        ("operations", ", ".join(request.operations)),
        ("caps", _caps_line(request.caps)),
        ("risk", f"{request.posture.value.replace('_', '-')}: {request.rationale}"),
        ("found at", request.found_at),
    ]
    if request.production:
        return PopupModel(
            title="Production-suspected endpoint",
            rows=tuple(rows),
            warning=(
                "This looks like production. Approval lasts this session only and is never remembered. "
                f"Type {request.confirm_name!r} to allow it."
            ),
            buttons=(Choice.allow_once, Choice.deny),
            default=Choice.deny,
            needs_typed_name=True,
            typed_hint=request.confirm_name,
        )
    return PopupModel(
        title="May I connect to this?",
        rows=tuple(rows),
        warning="Read-only: writes are rejected before they are sent." if not request.default_deny else (
            "No signal says this is safe, so the default is Deny. Read-only if you allow it."
        ),
        buttons=(Choice.allow_once, Choice.allow_remember, Choice.deny),
        default=Choice.deny if request.default_deny else Choice.allow_once,
        needs_typed_name=request.require_typed_confirmation,
        typed_hint=request.confirm_name if request.require_typed_confirmation else None,
    )


def decide(request: ConsentRequest, choice: Choice, typed: str = "") -> Resolution:
    """What a press means, before anything is granted. Pure; the gate applies it."""
    if choice is Choice.deny:
        return Resolution(True, False, False, f"denied {request.endpoint}; I won't ask again this session")
    if request.require_typed_confirmation and typed.strip() != request.confirm_name:
        return Resolution(
            False, False, False, f"type the exact name {request.confirm_name!r} to allow this endpoint"
        )
    if request.production:
        return Resolution(
            True, True, False,
            f"allowed {request.endpoint} for this session only; production-suspected endpoints are never remembered",
        )
    if choice is Choice.allow_remember:
        return Resolution(True, True, True, f"allowed {request.endpoint} and remembered it")
    return Resolution(True, True, False, f"allowed {request.endpoint} for this session")


class ConsentGate:
    """The session's consent state: the broker's grants, this session's denials, the pending queue."""

    def __init__(self, broker: CapabilityBroker) -> None:
        self.broker = broker
        self._pending: dict[str, ConsentRequest] = {}
        self._denied: dict[str, ConsentRequest] = {}
        self._known: dict[str, ConsentRequest] = {}
        #: set when a decision granted something, so the session re-runs what was waiting on it
        self.changed = False

    def is_granted(self, request: ConsentRequest) -> bool:
        return self.broker.check(request.tool, endpoint=request.endpoint).granted

    def observe(self, requests: Iterable[ConsentRequest]) -> tuple[ConsentRequest, ...]:
        """Sort this tick's endpoints: return the granted ones; queue the new or expired ones."""
        granted: list[ConsentRequest] = []
        for request in requests:
            self._known[request.key] = request
            if self.is_granted(request):
                self._pending.pop(request.key, None)
                granted.append(request)
            elif request.key in self._denied:
                continue
            else:
                self._pending.setdefault(request.key, request)
        return tuple(granted)

    def pending(self) -> tuple[ConsentRequest, ...]:
        return tuple(self._pending.values())

    def denied(self) -> tuple[ConsentRequest, ...]:
        return tuple(self._denied.values())

    def resolve(self, key: str, choice: Choice, typed: str = "") -> Resolution:
        """Apply a button press to the pending request ``key``."""
        request = self._pending.get(key)
        if request is None:
            return Resolution(False, False, False, f"nothing is waiting for permission under {key!r}")
        resolution = decide(request, choice, typed)
        if not resolution.accepted:
            return resolution
        del self._pending[key]
        if not resolution.granted:
            self._denied[key] = request
            return resolution
        self.broker.grant(
            request.tool,
            granted_by=_GRANTED_BY,
            reason=f"{_LABEL[choice]} in the permission popup ({request.posture.value})",
            endpoint=request.endpoint,
            caps=request.caps,
            credential_source=request.credential_source,
            remember=resolution.remembered,
            posture=request.posture.value,
        )
        self.changed = True
        return resolution

    def revoke(self, key: str) -> bool:
        """Withdraw an approval (and forget it in the store). It is not asked again this session."""
        tool_value, _, endpoint = key.partition("|")
        try:
            tool = Tool(tool_value)
        except ValueError:
            return False
        revoked = self.broker.revoke(tool, endpoint=endpoint)
        request = self._known.get(key)
        if revoked and request is not None:
            self._denied[key] = request
        return revoked

    def approvals(self) -> list[dict[str, object]]:
        """Every live grant, for the Permissions view."""
        out: list[dict[str, object]] = []
        for grant in self.broker.grants():
            key = f"{grant.tool.value}|{grant.endpoint or ''}"
            request = self._known.get(key)
            out.append({
                "key": key,
                "tool": grant.tool.value,
                "endpoint": grant.endpoint,
                "remembered": grant.remembered,
                "granted_by": grant.granted_by,
                "reason": grant.reason,
                "credential_source": grant.credential_source,
                "posture": request.posture.value if request is not None else None,
            })
        return out

    def to_json(self) -> dict[str, object]:
        return {
            "pending": [r.to_json() for r in self.pending()],
            "approvals": self.approvals(),
            "denied": [{"key": r.key, "endpoint": r.endpoint} for r in self.denied()],
        }


# -- turning discovery into requests ------------------------------------------------------------

_DB_OPERATIONS = ("probe", "describe tables", "read (SELECT only, through the read-only envelope)")
_VECTOR_OPERATIONS = ("probe", "describe collections", "search (read-only)")


def _endpoint_of(candidate: Candidate) -> str:
    if candidate.host:
        port = f":{candidate.port}" if candidate.port is not None else ""
        return f"{candidate.kind}://{candidate.host}{port}"
    if candidate.credential_source:
        return candidate.credential_source
    return f"{candidate.kind}@{candidate.provenance}"


def _database_of(candidate: Candidate) -> str | None:
    marker = " service '"
    if marker in candidate.detail:
        return candidate.detail.split(marker, 1)[1].split("'", 1)[0] + " (compose service)"
    return None


def discovered_requests(root: str | Path, caps: Caps) -> tuple[ConsentRequest, ...]:
    """One request per endpoint discovery finds in ``root``. Opens nothing and reads no credential."""
    out: dict[str, ConsentRequest] = {}
    for finding in scan(root).findings:
        candidate, cl = finding.candidate, finding.classification
        tool = candidate.tool or Tool.db_connection
        request = ConsentRequest(
            tool=tool,
            endpoint=_endpoint_of(candidate),
            kind=candidate.kind,
            host=candidate.host,
            database=_database_of(candidate),
            credential_source=candidate.credential_source,
            operations=_DB_OPERATIONS if candidate.category == DATABASE else _VECTOR_OPERATIONS,
            caps=caps,
            posture=cl.posture,
            rationale=cl.rationale,
            default_deny=cl.default_deny,
            require_typed_confirmation=cl.require_typed_confirmation,
            confirm_name=cl.endpoint_name,
            found_at=f"{candidate.provenance} ({candidate.provenance.reason})",
        )
        out.setdefault(request.key, request)
    return tuple(out.values())


def sqlite_request(root: str | Path, db: Path, caps: Caps) -> ConsentRequest:
    """The request for the repo's own SQLite file, which the automatic DB check wants to open.

    A file inside the repository is local, so it is classified as if on ``localhost``. The name rules
    still apply: a ``prod.db`` is production-suspected and needs its name typed.
    """
    rel = db.resolve().relative_to(Path(root).resolve()).as_posix()
    candidate = Candidate(
        kind="sqlite",
        tool=Tool.db_connection,
        detail=f"SQLite file {rel}",
        credential_source=None,
        host="localhost",
        port=None,
        provenance=Provenance(rel, 1, "a SQLite file in the repository"),
    )
    cl = classify(candidate)
    return ConsentRequest(
        tool=Tool.db_connection,
        endpoint=f"sqlite:///{rel}",
        kind="sqlite",
        host="this machine (a file in the repo)",
        database=rel,
        credential_source=None,
        operations=("open read-only (mode=ro, query_only)", "run this repo's SELECT queries against a snapshot"),
        caps=caps,
        posture=cl.posture,
        # classify() reasons about the stand-in "localhost"; for a file, say what it actually is
        rationale="a file inside this repository, on this machine" if cl.posture is Posture.local else cl.rationale,
        default_deny=cl.default_deny,
        require_typed_confirmation=cl.require_typed_confirmation,
        confirm_name=f"sqlite:///{rel}" if cl.require_typed_confirmation else cl.endpoint_name,
        found_at=f"{rel} (the automatic DB check wants to validate this repo's SQL against it)",
    )
