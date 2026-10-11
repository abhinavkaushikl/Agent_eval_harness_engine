"""Grading: the oracle layer, the sandbox, and the grader ladder (``AGENT.md`` §3.6, §3.7).

- ``oracles.harvest`` finds the oracles a repository already has and tags them HIGH (EL-205).
- ``sandbox.run_sandboxed`` runs a command safely and returns a typed result (EL-206).
- ``verdict`` holds that result and maps it onto EL-014's verdict vocabulary.

The graders that read an oracle and run it through the sandbox are later tickets (EL-207, EL-208).
"""

from __future__ import annotations

from evalloop.grade.sandbox import SandboxError, run_sandboxed
from evalloop.grade.verdict import Limits, Outcome, SandboxResult

__all__ = ["Limits", "Outcome", "SandboxError", "SandboxResult", "run_sandboxed"]
