"""The session tool (M2 slice): watch a repo, run the eval loop on every change, show it live.

This is the thin spine that turns the built engine (M0 registry + planner, M1 grading) into
something you *start* and then forget about. ``Session`` watches a working tree with a stdlib
poller, and on each coherent change runs the same honest ``evalloop.run.check`` loop and appends a
``RunCard`` to its state. A tiny HTTP server (stdlib) serves a dashboard that polls that state, so a
developer sees what is being evaluated — and a small mascot reacting — without lifting a finger.

Deliberately *not* here yet (later milestones, flagged not faked): the AI-transcript / git / shell
sensors and the Intent Bus (M2 Track O), the readiness/noise-floor honesty layer (M3), and the
opt-in screen sensor (Track X). This slice watches the filesystem, which ``ARCHITECTURE.md`` §4
ranks as the real, cheap signal; it never reads pixels.
"""

from __future__ import annotations

from evalloop.session.dashboard import dashboard_html
from evalloop.session.orchestrator import Session
from evalloop.session.poller import Snapshot, changed_files, snapshot
from evalloop.session.state import MascotState, RunCard, SessionState

__all__ = [
    "Session",
    "SessionState",
    "RunCard",
    "MascotState",
    "Snapshot",
    "snapshot",
    "changed_files",
    "dashboard_html",
]
