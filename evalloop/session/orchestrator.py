"""The session orchestrator: watch, evaluate on change, publish state, serve a live dashboard.

``Session.tick`` is the whole loop made testable: snapshot the tree, and if anything changed since
last time, run the real ``evalloop.run.check`` loop and append a :class:`RunCard`. ``run_forever``
is that tick on an interval; ``serve`` exposes the state and the dashboard over a stdlib HTTP server
so the page (and the mascot) update themselves. Nothing here grades anything on its own — it only
drives the engine that M0/M1 already built.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from evalloop.run import Author, RunResult, check
from evalloop.session.dashboard import dashboard_html
from evalloop.session.poller import Snapshot, changed_files, snapshot
from evalloop.session.state import MascotState, RunCard, SessionState

__all__ = ["Session"]

# The engine the session drives. Injectable so a test can run the loop without real grading.
Evaluator = Callable[[str, str], RunResult]


def _default_evaluator(store_dir: str, author: "Author | None") -> Evaluator:
    def run(path: str, _store: str) -> RunResult:
        return check(path, store_dir=store_dir, author=author)

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
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = str(root)
        self._store = str(store_dir)
        self._evaluator = evaluator if evaluator is not None else _default_evaluator(self._store, author)
        self._clock = clock
        self.state = SessionState(root=self.root, updated_at=clock())
        self._seen: Snapshot = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def tick(self) -> RunCard | None:
        """One pass: evaluate iff the tree changed since the last tick. Returns the card, or None."""
        current = snapshot(self.root)
        trigger = changed_files(self._seen, current)
        first_run = not self._seen
        self._seen = current
        if not trigger and not first_run:
            return None
        with self._lock:
            # name the in-flight target before the run, so the bot's thought cloud can show it
            self.state.current = trigger or ("the repository",)
            self.state.mascot = MascotState.evaluating
        try:
            result = self._evaluator(self.root, self._store)
            card = RunCard.from_result(result, trigger=trigger, at=self._clock())
        except Exception as exc:  # a bad run must never kill the watcher — record it and keep going
            card = RunCard.errored(exc, trigger=trigger, at=self._clock())
        with self._lock:
            self.state.record(card)
        return card

    def snapshot_json(self) -> bytes:
        with self._lock:
            return json.dumps(self.state.to_json()).encode("utf-8")

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
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer((host, port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
