"""One judged case: the unit the metric store persists, and the vocabulary its verdict uses.

A *case* is one oracle check of one artifact by one technique — for example, one harvested test
run against ``src/pricing.py`` under ``A1_execution_based``. The metric store keeps one line per
case, and two runs are compared case by case.

The verdict vocabulary is decision EL-014's
-------------------------------------------
``decisions/EL-014-timeout-semantics.md`` settled it:

- ``Verdict`` is ``passed`` / ``failed`` / ``inconclusive``.
- ``FailureClass`` is A:39's four classes — "syntax error, unknown column, runtime error or wrong
  result" — plus ``timeout``.
- A case has a failure class **if and only if** it failed.
- An inconclusive case carries a reason, because the evaluation failed rather than the artifact.
- A timeout records which cap was hit and the value in force.

EL-014's text says EL-206 "writes" these enums. The store persists them first, so they are defined
here, exactly as specified, and EL-206 imports them. That is the order the E2 plan gave: the store
defines the type, and the sandbox uses it.

The full schema, on day one
---------------------------
``PLAN.md`` T7 asks for the whole schema now, because adding a field later invalidates every run
already stored. Every field below is either filled by the code that judges a case, or ``None``
until the ticket named in its row exists. None is filled with a guessed value. The JSON key order
is this table's order, with ``run_id`` omitted: it lives once, in the run file's header. Volatile
measurements come last, so lines from two runs line up when read side by side.

====================  ===============================================  ============================
field                 meaning                                          filled by
====================  ===============================================  ============================
record_id             the registry technique that judged this case     the grader (EL-207/208)
case_id               this case's id, unique per technique in a run    the oracle (EL-205/210)
case_kind             ``generated`` or ``permanent`` (AGENT.md §3.9)   the run driver (EL-214)
artifact_id           what was judged, e.g. a file path                the run driver
oracle_id             what judged it, e.g. a test's node id            the oracle (EL-205/210)
oracle_confidence     HIGH if a human wrote the oracle, LOW if          the oracle (EL-205/210)
                      EvalLoop generated it (AGENT.md §3.6)
ladder_rung           the technique's rung when judged, or None for    the grader, from the record
                      a non-grader. ``summary.md`` §2 shows it
verdict               passed / failed / inconclusive (EL-014)          the grader
failure_class         set iff failed (A:39 plus timeout)               the grader
timeout               set iff the class is timeout: which cap, and     the sandbox (EL-206)
                      the limit in force
inconclusive_reason   set iff inconclusive                             the grader or the sandbox
score                 the technique's own score, if it has one:        the grader; None for a
                      partial credit, token-F1, field accuracy         pure pass/fail technique
evidence              what the grader saw: an assertion message, an    the grader; None if nothing
                      exception summary. ``summary.md`` §3 shows it    to say
artifact_hash         SHA-256 of the artifact's content                the run driver; EL-214's
                                                                       skip-if-unchanged reads it
oracle_hash           SHA-256 of the oracle's content. A changed       the oracle; read by M3's
                      oracle must not reuse an old result              reward-hack check
                      (ARCHITECTURE.md §9, "Test weakened to pass")
reused_from           None if judged in this run. Otherwise the run    the run driver (EL-214),
                      that judged it, when the content-hash skip       through ``reused_in``
                      reused an unchanged result (AGENT.md §3.9)
seed                  the seed of any randomness used for this case    the sandbox (EL-206) or the
                                                                       grader; None if none
cost_usd              LLM spend on one model call that judged this     M4's judge, via the router.
                      case alone                                       None for every M1 case
duration_seconds      wall-clock time spent judging this case          the grader or the sandbox
====================  ===============================================  ============================

A reused case is in its run, so the run says what it skipped, and a diff does not report the case
as gone. Its other fields are the judging run's, ``duration_seconds`` and ``cost_usd`` included:
they describe the judgement that produced the verdict. Spend in this run therefore excludes
reused cases.

``cost_usd`` is never an allocation. A call that serves several cases, such as EL-210 authoring
one test file, is not divided among them: its spend is the session's, in the router's
``CostLedger``. No M1 model call judges a single case, so ``cost_usd`` is ``None`` throughout M1.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, replace
from decimal import Decimal

from evalloop._compat import StrEnum
from evalloop.registry.schema import RECORD_ID

__all__ = [
    "CASE_FIELDS",
    "CaseKind",
    "CaseResult",
    "FailureClass",
    "OracleConfidence",
    "PermanentCase",
    "Timeout",
    "TimeoutCap",
    "Verdict",
    "check_run_id",
    "content_hash",
]


class Verdict(StrEnum):
    """EL-014: what happened to the artifact. Not ``pass``: that is a Python keyword."""

    passed = "passed"
    failed = "failed"
    inconclusive = "inconclusive"


class FailureClass(StrEnum):
    """A:39's four classes, verbatim, plus EL-014's ``timeout``."""

    syntax_error = "syntax_error"
    unknown_column = "unknown_column"
    runtime_error = "runtime_error"
    wrong_result = "wrong_result"
    timeout = "timeout"


class OracleConfidence(StrEnum):
    """AGENT.md §3.6: HIGH for a harvested oracle a human wrote, LOW for one EvalLoop generated."""

    high = "high"
    low = "low"


class CaseKind(StrEnum):
    """AGENT.md §3.9: ``generated`` is ephemeral; ``permanent`` was promoted, e.g. a failure kept as a test."""

    generated = "generated"
    permanent = "permanent"


class TimeoutCap(StrEnum):
    """EL-014: either cap counts as a timeout, and the record says which one was hit."""

    wall_clock = "wall_clock"
    cpu_time = "cpu_time"


#: The JSON key order of a stored case, which is also the order of the table above.
CASE_FIELDS: tuple[str, ...] = (
    "record_id",
    "case_id",
    "case_kind",
    "artifact_id",
    "oracle_id",
    "oracle_confidence",
    "ladder_rung",
    "verdict",
    "failure_class",
    "timeout",
    "inconclusive_reason",
    "score",
    "evidence",
    "artifact_hash",
    "oracle_hash",
    "reused_from",
    "seed",
    "cost_usd",
    "duration_seconds",
)

_HASH = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def content_hash(data: bytes) -> str:
    """The hash every stored case uses: SHA-256, as lowercase hex."""
    return hashlib.sha256(data).hexdigest()


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string, got {value!r}")
    return value


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def check_run_id(run_id: object) -> str:
    """A run id names a file, so it is restricted to a safe, portable alphabet."""
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError(
            f"run_id {run_id!r} must start with a letter or digit and use only letters, "
            "digits, '.', '_' and '-'"
        )
    return run_id


@dataclass(frozen=True)
class Timeout:
    """Which cap stopped the run, and the limit that was in force (EL-014)."""

    cap: TimeoutCap
    limit_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.cap, TimeoutCap):
            raise ValueError(f"cap must be a TimeoutCap, got {self.cap!r}")
        if _number("limit_seconds", self.limit_seconds) <= 0:
            raise ValueError(f"limit_seconds must be positive, got {self.limit_seconds!r}")


@dataclass(frozen=True)
class CaseResult:
    """One judged case. See the module docstring for what fills each field."""

    run_id: str
    record_id: str
    case_id: str
    case_kind: CaseKind
    artifact_id: str
    oracle_id: str
    oracle_confidence: OracleConfidence
    ladder_rung: int | None
    verdict: Verdict
    failure_class: FailureClass | None
    timeout: Timeout | None
    inconclusive_reason: str | None
    score: float | None
    evidence: str | None
    artifact_hash: str
    oracle_hash: str
    reused_from: str | None
    seed: int | None
    cost_usd: Decimal | None
    duration_seconds: float

    def __post_init__(self) -> None:
        check_run_id(self.run_id)
        if self.reused_from is not None:
            if check_run_id(self.reused_from) == self.run_id:
                raise ValueError("a case cannot be reused from its own run")
            if self.verdict is Verdict.inconclusive:
                raise ValueError("an inconclusive result is never reused: the evaluation has to run again")
        if not isinstance(self.record_id, str) or not RECORD_ID.fullmatch(self.record_id):
            raise ValueError(f"record_id {self.record_id!r} is not a technique record id")
        for name, value in (("case_id", self.case_id), ("artifact_id", self.artifact_id), ("oracle_id", self.oracle_id)):
            _text(name, value)
        for name, enum_value, kind in (
            ("case_kind", self.case_kind, CaseKind),
            ("oracle_confidence", self.oracle_confidence, OracleConfidence),
            ("verdict", self.verdict, Verdict),
        ):
            if not isinstance(enum_value, kind):
                raise ValueError(f"{name} must be a {kind.__name__}, got {enum_value!r}")
        if self.ladder_rung is not None and (
            isinstance(self.ladder_rung, bool) or not isinstance(self.ladder_rung, int) or self.ladder_rung < 1
        ):
            raise ValueError(f"ladder_rung must be a positive integer or None, got {self.ladder_rung!r}")
        self._check_outcome()
        if self.score is not None:
            _number("score", self.score)
        if self.evidence is not None:
            _text("evidence", self.evidence)
        for name, value in (("artifact_hash", self.artifact_hash), ("oracle_hash", self.oracle_hash)):
            if not isinstance(value, str) or not _HASH.fullmatch(value):
                raise ValueError(f"{name} must be a SHA-256 hex digest, got {value!r}")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise ValueError(f"seed must be an integer or None, got {self.seed!r}")
        if self.cost_usd is not None and (
            not isinstance(self.cost_usd, Decimal) or not self.cost_usd.is_finite() or self.cost_usd < 0
        ):
            raise ValueError(f"cost_usd must be a non-negative, finite Decimal or None, got {self.cost_usd!r}")
        if _number("duration_seconds", self.duration_seconds) < 0:
            raise ValueError(f"duration_seconds cannot be negative, got {self.duration_seconds!r}")

    def _check_outcome(self) -> None:
        """EL-014's three rules, which tie the verdict to the fields that explain it."""
        if self.failure_class is not None and not isinstance(self.failure_class, FailureClass):
            raise ValueError(f"failure_class must be a FailureClass or None, got {self.failure_class!r}")
        if (self.verdict is Verdict.failed) != (self.failure_class is not None):
            raise ValueError("a case has a failure class if and only if it failed (EL-014)")
        if (self.failure_class is FailureClass.timeout) != (self.timeout is not None):
            raise ValueError("a timeout records its cap and limit, and only a timeout does (EL-014)")
        if self.timeout is not None and not isinstance(self.timeout, Timeout):
            raise ValueError(f"timeout must be a Timeout or None, got {self.timeout!r}")
        if self.verdict is Verdict.inconclusive:
            _text("inconclusive_reason", self.inconclusive_reason)
        elif self.inconclusive_reason is not None:
            raise ValueError("only an inconclusive case carries an inconclusive_reason (EL-014)")

    @property
    def key(self) -> tuple[str, str]:
        """How a case is matched across runs: the technique and the case id."""
        return (self.record_id, self.case_id)

    def reused_in(self, run_id: str) -> CaseResult:
        """This result, carried into ``run_id`` unjudged. It names the run that judged it, never a reuse."""
        return replace(self, run_id=run_id, reused_from=self.reused_from or self.run_id)


@dataclass(frozen=True)
class PermanentCase:
    """A case promoted to run in every future run, e.g. a failure kept as a test (I:273's flywheel).

    ``oracle_hash`` is the oracle's content when it was promoted. A later run can then tell a kept
    test that still holds from one that was weakened to pass (``ARCHITECTURE.md`` §9).
    """

    record_id: str
    case_id: str
    artifact_id: str
    oracle_id: str
    oracle_confidence: OracleConfidence
    oracle_hash: str
    promoted_from_run: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not RECORD_ID.fullmatch(self.record_id):
            raise ValueError(f"record_id {self.record_id!r} is not a technique record id")
        for name, value in (
            ("case_id", self.case_id),
            ("artifact_id", self.artifact_id),
            ("oracle_id", self.oracle_id),
            ("reason", self.reason),
        ):
            _text(name, value)
        if not isinstance(self.oracle_confidence, OracleConfidence):
            raise ValueError(f"oracle_confidence must be an OracleConfidence, got {self.oracle_confidence!r}")
        if not isinstance(self.oracle_hash, str) or not _HASH.fullmatch(self.oracle_hash):
            raise ValueError(f"oracle_hash must be a SHA-256 hex digest, got {self.oracle_hash!r}")
        check_run_id(self.promoted_from_run)

    @property
    def key(self) -> tuple[str, str]:
        return (self.record_id, self.case_id)
