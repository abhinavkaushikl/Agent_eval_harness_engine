"""The live session state: what the dashboard (and the mascot) render, as plain serialisable data.

One ``RunCard`` per evaluation the session has run, newest first, plus a derived ``MascotState`` so
the front end never has to know the grading vocabulary. Everything here is JSON-ready; the HTTP
layer just dumps :meth:`SessionState.to_json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evalloop._compat import StrEnum
from evalloop.run import RunResult
from evalloop.memory.case import Verdict

__all__ = ["MascotState", "CaseCard", "RunCard", "SessionState"]


class MascotState(StrEnum):
    """How the mascot should look, derived from the latest run. The dashboard maps these to a pose."""

    idle = "idle"            # watching, nothing new
    evaluating = "evaluating"  # a run is in flight
    happy = "happy"          # last run clean
    alarmed = "alarmed"      # last run found a problem
    unsure = "unsure"        # last run could decide nothing
    errored = "errored"      # the evaluation itself raised


_OUTCOME_TO_MASCOT = {
    "clean": MascotState.happy,
    "problem": MascotState.alarmed,
    "undecided": MascotState.unsure,
    "errored": MascotState.errored,
}


@dataclass(frozen=True, slots=True)
class CaseCard:
    """One graded case, flattened for display."""

    artifact: str
    record: str
    verdict: str
    rung: int | None
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"artifact": self.artifact, "record": self.record, "verdict": self.verdict, "rung": self.rung, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class RunCard:
    """One evaluation run: its outcome, what changed to trigger it, and the per-case verdicts."""

    run_id: str
    outcome: str
    trigger: tuple[str, ...]
    situations: tuple[str, ...]
    cases: tuple[CaseCard, ...]
    permission_requests: tuple[str, ...]
    at: float
    error: str = ""

    @classmethod
    def errored(cls, exc: BaseException, *, trigger: tuple[str, ...], at: float) -> RunCard:
        """A run whose evaluation raised. The watcher records it and keeps going."""
        return cls(
            run_id="errored",
            outcome="errored",
            trigger=trigger,
            situations=(),
            cases=(),
            permission_requests=(),
            at=at,
            error=f"{type(exc).__name__}: {exc}",
        )

    @classmethod
    def from_result(cls, result: RunResult, *, trigger: tuple[str, ...], at: float) -> RunCard:
        cases = tuple(
            CaseCard(
                artifact=c.artifact_id,
                record=c.record_id,
                verdict=c.verdict.value if isinstance(c.verdict, Verdict) else str(c.verdict),
                rung=c.ladder_rung,
                detail=c.inconclusive_reason or (c.failure_class.value if c.failure_class is not None else "ok"),
            )
            for c in result.cases
        )
        return cls(
            run_id=result.run_id,
            outcome=result.outcome.value,
            trigger=trigger,
            situations=tuple(f"{s.value} ({conf:.2f})" for s, conf in result.situations),
            cases=cases,
            permission_requests=tuple(result.permission_requests),
            at=at,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "outcome": self.outcome,
            "trigger": list(self.trigger),
            "situations": list(self.situations),
            "cases": [c.to_json() for c in self.cases],
            "permission_requests": list(self.permission_requests),
            "at": self.at,
            "error": self.error,
        }


@dataclass
class SessionState:
    """The whole session, as the dashboard sees it: who is watched, the mascot, and the run history."""

    root: str
    watching: bool = True
    mascot: MascotState = MascotState.idle
    runs: list[RunCard] = field(default_factory=list)
    updated_at: float = 0.0
    #: What is being evaluated *right now* — set before a run starts, cleared when it ends. The
    #: finished ``runs`` cannot answer this, and it is what the on-screen thought cloud names.
    current: tuple[str, ...] = ()

    def record(self, card: RunCard) -> None:
        self.runs.insert(0, card)
        self.mascot = _OUTCOME_TO_MASCOT.get(card.outcome, MascotState.idle)
        self.updated_at = card.at
        self.current = ()

    def to_json(self) -> dict[str, object]:
        return {
            "root": self.root,
            "watching": self.watching,
            "mascot": self.mascot.value,
            "updated_at": self.updated_at,
            "current": list(self.current),
            "runs": [r.to_json() for r in self.runs],
        }
