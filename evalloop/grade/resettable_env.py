"""A resettable environment: the clean baseline an agent acts in, restorable between runs.

``H1_resettable_env`` / ``H3_pass_hat_k`` / ``H8_flaky_classification``: agent evaluation needs a
*resettable environment* — a working directory (files) plus an optional seed database the agent
writes to — that can be restored to an **identical** clean baseline before each run. Without that
reset two things are impossible to do honestly: an end-state verdict (a dirty environment could have
faked the state, which is why :func:`~evalloop.grade.end_state.verify_end_state` returns
``inconclusive`` unless ``RESETTABLE_FACT`` is true), and pass^k (run the *same* task k times from
the *same* start and see how often it really succeeds).

Scope, drawn honestly
---------------------
This component owns the environment and the reset, nothing more. It does **not** run the agent: the
caller injects *how* a run happens (a callable given the env), so LLM egress and arbitrary code
execution stay out of this layer entirely — which keeps it pure standard library, deterministic, and
unit-testable without a model or a network. Actually executing a real agent (with its egress and
trajectory capture) is the next step that builds on this; it is deliberately not here.

The reset is a whole-directory restore from a baseline copy taken at build time: the live workdir is
emptied and rebuilt from the baseline, so **anything** the agent wrote — files and the database
alike — is undone. The workdir is a scratch directory the harness owns; the agent never acts in the
real repository (``ARCHITECTURE.md`` §9: writes belong to a scratch copy, never live data).

Capability
----------
A resettable environment *is* the ``snapshot_restore`` capability (decision EL-002: a capability, not
a transport). :func:`grant_snapshot_restore` records that grant through the broker — the one place
consent lives — so the planner may treat ``Tool.snapshot_restore`` as present once an env exists.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evalloop.capability.broker import CapabilityBroker, Grant
from evalloop.grade.end_state import (
    RESETTABLE_FACT,
    AgentClaim,
    EndStateGrade,
    StateCheck,
    verify_end_state,
)
from evalloop.grade.sql_execution import Snapshot, build_snapshot
from evalloop.memory.case import Verdict
from evalloop.vocab import Tool

__all__ = [
    "ResettableEnv",
    "TrialResult",
    "PassHatK",
    "run_trials",
    "grant_snapshot_restore",
]

#: The baseline lives beside the workdir under this suffix, so a reset is a local copy, not a rebuild.
_BASELINE_SUFFIX = ".baseline"


class ResettableEnv:
    """A scratch workdir (+ optional seed DB) that restores to an identical baseline on :meth:`reset`."""

    def __init__(self, root: Path, baseline: Path, db_name: str | None) -> None:
        self._root = root
        self._baseline = baseline
        self._db_name = db_name

    # -- construction -----------------------------------------------------------------

    @classmethod
    def build(
        cls,
        workdir: str | Path,
        *,
        files: Mapping[str, str] | None = None,
        db_name: str | None = None,
        sqlite_setup: str | None = None,
    ) -> "ResettableEnv":
        """Create a clean workdir from ``files`` and an optional seeded SQLite DB, and record a baseline.

        ``workdir`` is a scratch path the harness owns and will overwrite on reset; never point it at a
        real project. ``db_name`` + ``sqlite_setup`` seed a database the agent writes to; the setup
        should include the *distinguishing* rows an end-state check needs (``build_snapshot``'s rule).
        """
        root = Path(workdir)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)

        for relpath, content in (files or {}).items():
            target = root / relpath
            if not _is_within(root, target):
                raise ValueError(f"template file {relpath!r} escapes the workdir")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        if db_name is not None:
            if sqlite_setup is None:
                raise ValueError("db_name needs sqlite_setup to seed the database")
            db_path = root / db_name
            if not _is_within(root, db_path):
                raise ValueError(f"db_name {db_name!r} escapes the workdir")
            build_snapshot(db_path, sqlite_setup).close()  # seed the file, then release the handle
        elif sqlite_setup is not None:
            raise ValueError("sqlite_setup needs a db_name to say where to seed it")

        baseline = root.with_name(root.name + _BASELINE_SUFFIX)
        if baseline.exists():
            shutil.rmtree(baseline)
        shutil.copytree(root, baseline)
        return cls(root, baseline, db_name)

    # -- the reset --------------------------------------------------------------------

    def reset(self) -> None:
        """Restore the workdir to its baseline exactly: everything the agent wrote is undone."""
        if not self._baseline.exists():
            raise RuntimeError("the baseline is gone; this environment can no longer be reset")
        if self._root.exists():
            shutil.rmtree(self._root)
        shutil.copytree(self._baseline, self._root)

    # -- what the agent acts in, and what the verifier reads --------------------------

    @property
    def root(self) -> Path:
        """The live workdir the agent writes to, and the files root an end-state check reads."""
        return self._root

    def open_db(self) -> Snapshot | None:
        """A read-only snapshot over the (current) database, or None if this env has no DB. Caller closes."""
        if self._db_name is None:
            return None
        return Snapshot(self._root / self._db_name)

    @property
    def facts(self) -> dict[str, object]:
        """The session facts an end-state grade needs: this environment resets, so the fact is true."""
        return {RESETTABLE_FACT: True}

    def verify(self, checks: Sequence[StateCheck], *, claim: AgentClaim | None = None) -> EndStateGrade:
        """Grade the current end state of this environment with :func:`verify_end_state`."""
        db = self.open_db()
        try:
            return verify_end_state(
                checks, db=db, root=self._root, claim=claim, session_facts=self.facts, require_resettable=True
            )
        finally:
            if db is not None:
                db.close()

    def dispose(self) -> None:
        """Remove the workdir and its baseline. Idempotent; the env cannot be reset afterwards."""
        for path in (self._root, self._baseline):
            if path.exists():
                shutil.rmtree(path)


def _is_within(root: Path, target: Path) -> bool:
    """True if ``target`` stays inside ``root`` (no ``..`` escape), without touching the filesystem."""
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# -- pass^k over a resettable environment (H3) ----------------------------------------


@dataclass(frozen=True, slots=True)
class TrialResult:
    """One trial: which run, and the end-state grade of the environment after that run."""

    trial: int
    grade: EndStateGrade

    @property
    def passed(self) -> bool:
        return self.grade.verdict is Verdict.passed


@dataclass(frozen=True, slots=True)
class PassHatK:
    """The pass^k summary: the same task run k times from a clean reset each time (H3)."""

    k: int
    trials: tuple[TrialResult, ...]

    @property
    def passes(self) -> int:
        return sum(1 for t in self.trials if t.passed)

    @property
    def pass_hat_k(self) -> bool:
        """True only if **every** one of the k runs passed — the agent is reliable, not just lucky."""
        return self.k > 0 and self.passes == self.k

    @property
    def pass_rate(self) -> float:
        return self.passes / self.k if self.k else 0.0

    def describe(self) -> str:
        return f"pass^{self.k} = {self.pass_hat_k} ({self.passes}/{self.k} runs passed, rate {self.pass_rate:.2f})"


def run_trials(
    env: ResettableEnv,
    act: Callable[[ResettableEnv], None],
    checks: Sequence[StateCheck],
    *,
    k: int,
    claim: AgentClaim | None = None,
) -> PassHatK:
    """Run ``act`` against ``env`` k times, resetting to the clean baseline before each, and grade each.

    ``act`` is the injected agent run — it acts on ``env.root`` and the env's database, and this
    harness never inspects *how* it does so. Because the environment is reset before every trial, the
    k grades are independent, which is exactly what makes ``pass^k`` honest (H3): a flaky agent that
    only sometimes leaves the right end state fails pass^k even if it passed once.
    """
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    trials: list[TrialResult] = []
    for i in range(k):
        env.reset()
        act(env)
        trials.append(TrialResult(i + 1, env.verify(checks, claim=claim)))
    return PassHatK(k, tuple(trials))


# -- capability -----------------------------------------------------------------------


def grant_snapshot_restore(broker: CapabilityBroker, *, granted_by: str, reason: str) -> Grant:
    """Record, through the broker, that a resettable environment is available as ``snapshot_restore``.

    A resettable environment *is* the capability (EL-002), so the grant is what lets the planner treat
    ``Tool.snapshot_restore`` as present. Consent still goes through the one place that holds grants.
    """
    return broker.grant(Tool.snapshot_restore, granted_by=granted_by, reason=reason)
