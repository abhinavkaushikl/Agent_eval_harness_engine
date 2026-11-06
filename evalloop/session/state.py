"""The live session state: what the dashboard (and the mascot) render, as plain serialisable data.

One ``RunCard`` per evaluation the session has run, newest first, plus a derived ``MascotState`` so
the front end never has to know the grading vocabulary. Everything here is JSON-ready; the HTTP
layer just dumps :meth:`SessionState.to_json`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from evalloop._compat import StrEnum
from evalloop.run import RunResult
from evalloop.memory.case import CaseResult, Verdict
from evalloop.stats.proportions import wilson_interval

__all__ = [
    "MascotState",
    "CaseCard",
    "RunCard",
    "SessionState",
    "worst_outcome",
    "exit_code_for",
]


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

#: How a tick's cards are ranked to pick its headline. One ``tick`` grades several things (the
#: Python-function path, any SQL/RAG specs, the auto DB-access check), each its own card. The
#: card recorded LAST is not the one a developer needs to see first: a real PROBLEM outranks an
#: errored eval, which outranks UNDECIDED, which outranks CLEAN. "PROBLEM wins the tick" — so the
#: mascot, the single-line CLI summary, and the exit code all speak for the worst thing found,
#: never the last thing graded.
_OUTCOME_SEVERITY = {"clean": 0, "undecided": 1, "errored": 2, "problem": 3}

#: The process exit code each headline outcome maps to, same honesty as ``run.RunOutcome``:
#: 0 clean, 1 a problem found (or the eval itself errored — both need attention), 2 undecided.
_OUTCOME_EXIT_CODE = {"clean": 0, "problem": 1, "errored": 1, "undecided": 2}


def worst_outcome(outcomes: Iterable[str]) -> str:
    """The most severe outcome among a tick's cards, or ``"clean"`` when there are none."""
    return max(outcomes, key=lambda o: _OUTCOME_SEVERITY.get(o, -1), default="clean")


def exit_code_for(outcome: str) -> int:
    """The honest exit code for a headline outcome (unknown outcomes read as undecided)."""
    return _OUTCOME_EXIT_CODE.get(outcome, 2)


def _case_name(case_id: str) -> str:
    """The specific test out of a case id like ``file.py::test_adds`` or ``…::test_x[param]``."""
    tail = case_id.split("::")[-1]
    return tail or case_id


def _case_detail(case: CaseResult) -> str:
    """The honest 'why' for one case: the real failing assertion if there is one, else the reason."""
    if case.verdict is Verdict.failed:
        evidence = (str(case.evidence) if case.evidence else "").strip()
        return evidence or (case.failure_class.value if case.failure_class is not None else "failed")
    if case.verdict is Verdict.inconclusive:
        return case.inconclusive_reason or "inconclusive"
    return "ok"


@dataclass(frozen=True, slots=True)
class CaseCard:
    """One graded case, flattened for display: which test, which technique, and why it landed."""

    artifact: str        # the file / target under test
    name: str            # the specific test case (the thing that passed or failed)
    record: str          # the technique id (e.g. A1_execution_based)
    verdict: str
    detail: str          # for a failure: the real evidence (the assertion, expected vs actual)
    failure_class: str   # "" unless it failed — e.g. wrong_result, unknown_column, syntax_error
    rung: int | None = None
    confidence: str = ""  # oracle confidence: high (harvested) / low (model-written) / "" (spec)
    kind: str = ""        # case kind: generated (LLM-written) / permanent / spec
    oracle: str = ""      # which oracle judged it (a harvested test file, or "authored:…")

    def to_json(self) -> dict[str, object]:
        return {
            "artifact": self.artifact, "name": self.name, "record": self.record,
            "verdict": self.verdict, "detail": self.detail,
            "failure_class": self.failure_class, "rung": self.rung,
            "confidence": self.confidence, "kind": self.kind, "oracle": self.oracle,
        }


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
    #: Why things were not graded ("app.py::load_data: no test oracle", reused verdicts…), so a
    #: run that checked nothing can say why instead of a bare "undecided".
    notes: tuple[str, ...] = ()

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
    def from_spec(cls, kind: str, situation: str, outcome: str, cases: tuple[CaseCard, ...], *,
                  trigger: tuple[str, ...], at: float) -> RunCard:
        """A card for a SQL / RAG / agent eval spec, which grades outside the Python-function path."""
        return cls(
            run_id=f"spec:{kind}",
            outcome=outcome,
            trigger=trigger,
            situations=(f"{situation} (spec)",),
            cases=cases,
            permission_requests=(),
            at=at,
        )

    @classmethod
    def from_result(cls, result: RunResult, *, trigger: tuple[str, ...], at: float) -> RunCard:
        cases = tuple(
            CaseCard(
                artifact=c.artifact_id,
                name=_case_name(c.case_id),
                record=c.record_id,
                verdict=c.verdict.value if isinstance(c.verdict, Verdict) else str(c.verdict),
                detail=_case_detail(c),
                failure_class=c.failure_class.value if c.failure_class is not None else "",
                rung=c.ladder_rung,
                confidence=c.oracle_confidence.value,
                kind=c.case_kind.value,
                oracle=c.oracle_id,
            )
            for c in result.cases
        )
        return cls(
            run_id=result.run_id,
            # the session grades the specs as cards of their own, so this card is the code path only
            outcome=(result.code_outcome or result.outcome).value,
            trigger=trigger,
            situations=tuple(f"{s.value} ({conf:.2f})" for s, conf in result.situations),
            cases=cases,
            permission_requests=tuple(result.permission_requests),
            notes=tuple(result.notes) + tuple(result.skipped),
            at=at,
        )

    def rate(self) -> dict[str, object] | None:
        """The run's pass rate over DECIDED cases, with its Wilson interval (C1). None if nothing decided."""
        passed = sum(1 for c in self.cases if c.verdict == "passed")
        failed = sum(1 for c in self.cases if c.verdict == "failed")
        n = passed + failed
        if n == 0:
            return None
        iv = wilson_interval(passed, n)
        return {"passed": passed, "failed": failed, "n": n,
                "estimate": iv.estimate, "lower": iv.lower, "upper": iv.upper, "confidence": iv.confidence}

    def to_json(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "outcome": self.outcome,
            "trigger": list(self.trigger),
            "situations": list(self.situations),
            "cases": [c.to_json() for c in self.cases],
            "rate": self.rate(),
            "permission_requests": list(self.permission_requests),
            "at": self.at,
            "error": self.error,
            "notes": list(self.notes),
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
