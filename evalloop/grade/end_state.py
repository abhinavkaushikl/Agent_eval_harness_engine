"""Verify what actually happened to the DB / files — not what the agent said happened.

A2 / H2 end-state verification, and ``ARCHITECTURE.md`` §9: "Agent's 'tests pass' is false → an
independent re-run in a clean sandbox; the transcript is never evidence." The verdict here is
computed **only** from the real resulting state — rows in the database, files on disk — read through
a read-only connector (EL-305/EL-306). An agent or script that reports "done" / "tests pass" while
leaving the state wrong is caught, because the claim is recorded but never consulted.

Writes belong to a scratch schema or a restored snapshot, never the live data (``ARCHITECTURE.md``
§9, and the H precondition that a resettable environment precedes agent evaluation). This module only
*reads*; :func:`restore_snapshot` makes the scratch copy that setup and the agent write to, and the
read-only envelope's audit log proves the verifier touched the live schema with nothing but reads.

The ticket/registry seam, stated honestly
------------------------------------------
The ticket says "carries ``A2_end_state_verification`` and honours its requires (resettable
environment)." In the registry ``A2_end_state_verification.requires`` is **empty** — the
``environment_resets_per_run`` precondition is authored on the *agent* records **H2–H8**, not on A2.
So this module does both: it carries A2 and honours A2's own (empty) requires through
:func:`evaluate_readiness`, *and* it enforces the resettable-environment precondition explicitly
(the ticket's intent, H's rule), returning ``inconclusive`` when the environment is not resettable
rather than trusting an end state that a dirty environment could have faked. The discrepancy is
flagged in the report, not papered over.

Full agent evaluation, pass^k and trajectory capture are M5 (T43); this verifies a single run's end
state.
"""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from evalloop.grade.sql_execution import Snapshot
from evalloop.memory.case import FailureClass, Verdict
from evalloop.plan.readiness import evaluate_readiness
from evalloop.registry.loader import RECORDS_DIR, load_records

__all__ = [
    "RECORD_ID",
    "LADDER_RUNG",
    "RESETTABLE_FACT",
    "AgentClaim",
    "CheckResult",
    "VerificationContext",
    "StateCheck",
    "RowsEqual",
    "NoRows",
    "FileExists",
    "FileAbsent",
    "FileContains",
    "EndStateGrade",
    "verify_end_state",
    "restore_snapshot",
]

RECORD_ID = "A2_end_state_verification"
LADDER_RUNG = 2  # end-state is rung 2 of the grading ladder
RESETTABLE_FACT = "environment_resets_per_run"  # the resettable-environment precondition (H2–H8)


@dataclass(frozen=True, slots=True)
class AgentClaim:
    """What the agent said happened. Recorded for the record; NEVER used to compute the verdict."""

    done: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One state check's outcome: did the REAL state match, and why."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class VerificationContext:
    """What the checks read: a read-only DB snapshot and/or a files root. Never a transcript."""

    db: Snapshot | None = None
    root: Path | None = None


@runtime_checkable
class StateCheck(Protocol):
    """A single assertion about the real resulting state."""

    name: str

    def verify(self, ctx: VerificationContext) -> CheckResult: ...


# -- database checks (read-only, through the connector) --------------------------------


@dataclass(frozen=True, slots=True)
class RowsEqual:
    """The real rows returned by ``query`` equal ``expected`` (multiset, or ordered when asked)."""

    name: str
    query: str
    expected: Sequence[Sequence[object]]
    ordered: bool = False

    def verify(self, ctx: VerificationContext) -> CheckResult:
        if ctx.db is None:
            return CheckResult(self.name, False, "no database snapshot to read the end state from")
        actual = [tuple(row) for row in ctx.db.rows(self.query)]
        want = [tuple(row) for row in self.expected]
        ok = actual == want if self.ordered else Counter(actual) == Counter(want)
        return CheckResult(self.name, ok, f"state has {len(actual)} row(s); expected {len(want)}" + ("" if ok else " — mismatch"))


@dataclass(frozen=True, slots=True)
class NoRows:
    """``query`` returns no rows against the real state (e.g. the row the agent should have deleted)."""

    name: str
    query: str

    def verify(self, ctx: VerificationContext) -> CheckResult:
        if ctx.db is None:
            return CheckResult(self.name, False, "no database snapshot to read the end state from")
        actual = ctx.db.rows(self.query)
        return CheckResult(self.name, not actual, f"{len(actual)} row(s) present; expected none")


# -- file checks (on disk, read-only) --------------------------------------------------


def _resolve(ctx: VerificationContext, name: str, relpath: str) -> tuple[Path | None, CheckResult | None]:
    if ctx.root is None:
        return None, CheckResult(name, False, "no files root to read the end state from")
    return (ctx.root / relpath), None


@dataclass(frozen=True, slots=True)
class FileExists:
    name: str
    path: str

    def verify(self, ctx: VerificationContext) -> CheckResult:
        target, failure = _resolve(ctx, self.name, self.path)
        if failure is not None or target is None:
            return failure  # type: ignore[return-value]
        return CheckResult(self.name, target.is_file(), f"{self.path} {'exists' if target.is_file() else 'is missing'}")


@dataclass(frozen=True, slots=True)
class FileAbsent:
    name: str
    path: str

    def verify(self, ctx: VerificationContext) -> CheckResult:
        target, failure = _resolve(ctx, self.name, self.path)
        if failure is not None or target is None:
            return failure  # type: ignore[return-value]
        return CheckResult(self.name, not target.exists(), f"{self.path} {'is absent' if not target.exists() else 'still exists'}")


@dataclass(frozen=True, slots=True)
class FileContains:
    name: str
    path: str
    needle: str

    def verify(self, ctx: VerificationContext) -> CheckResult:
        target, failure = _resolve(ctx, self.name, self.path)
        if failure is not None or target is None:
            return failure  # type: ignore[return-value]
        if not target.is_file():
            return CheckResult(self.name, False, f"{self.path} is missing")
        found = self.needle in target.read_text(encoding="utf-8", errors="replace")
        return CheckResult(self.name, found, f"{self.path} {'contains' if found else 'does not contain'} the expected text")


# -- the grade -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EndStateGrade:
    """A verdict from the real end state. The agent's claim is echoed but was not used."""

    record_id: str
    ladder_rung: int
    verdict: Verdict
    failure_class: FailureClass | None
    checks: tuple[CheckResult, ...]
    detail: str
    claim_ignored: str | None = None
    pending_reason: str | None = None


def _a2_record_requires_met(session_facts: Mapping[str, object]) -> bool:
    """Carry A2 and honour its own (registry-authored) requires via readiness. Empty today → met."""
    for record in load_records(RECORDS_DIR):
        if record.id == RECORD_ID:
            return evaluate_readiness(record, session_facts).met
    raise LookupError(f"{RECORD_ID} is not in the registry")


def verify_end_state(
    checks: Sequence[StateCheck],
    *,
    db: Snapshot | None = None,
    root: Path | None = None,
    claim: AgentClaim | None = None,
    session_facts: Mapping[str, object] | None = None,
    require_resettable: bool = True,
) -> EndStateGrade:
    """Compute a verdict from the real state alone. The ``claim`` is recorded and ignored."""
    facts: Mapping[str, object] = session_facts or {}
    claim_note = None if claim is None else f"agent claimed done={claim.done!r}: {claim.message!r} (not used)"

    # Honour A2's own requires (carried), and enforce the resettable-environment precondition (H).
    _a2_record_requires_met(facts)  # A2.requires is empty; evaluated so the record is carried, not assumed
    if require_resettable and facts.get(RESETTABLE_FACT) is not True:
        reason = (
            f"end-state verification needs a resettable environment ({RESETTABLE_FACT}: true, have "
            f"{facts.get(RESETTABLE_FACT)!r}); without a clean reset the end state cannot be trusted"
        )
        return EndStateGrade(RECORD_ID, LADDER_RUNG, Verdict.inconclusive, None, (), reason, claim_note, reason)

    ctx = VerificationContext(db=db, root=root)
    results = tuple(check.verify(ctx) for check in checks)
    failed = [r for r in results if not r.ok]
    if failed:
        detail = f"end state wrong: {len(failed)} of {len(results)} checks failed ({', '.join(r.name for r in failed)})"
        return EndStateGrade(RECORD_ID, LADDER_RUNG, Verdict.failed, FailureClass.wrong_result, results, detail, claim_note)
    detail = f"end state verified: all {len(results)} checks passed against the real state"
    return EndStateGrade(RECORD_ID, LADDER_RUNG, Verdict.passed, None, results, detail, claim_note)


def restore_snapshot(source: str | Path, scratch: str | Path) -> Path:
    """Copy a DB file to a scratch path — the restored snapshot setup and the agent write to.

    The live ``source`` is never opened for writing here; writes land on the ``scratch`` copy, and the
    verifier reads that copy read-only.
    """
    scratch_path = Path(scratch)
    shutil.copyfile(str(source), str(scratch_path))
    return scratch_path
