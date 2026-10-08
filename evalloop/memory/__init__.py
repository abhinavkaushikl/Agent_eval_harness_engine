"""Memory: what EvalLoop remembers between runs (``AGENT.md`` §3.9).

M1 holds two stores:

- The **episodic store** (``episodic``, SQLite) records each episode's decisions
  and the reasoning behind them.
- The **metric store** (``metric_store``, JSONL) records every judged case, one
  line each, so two runs can be compared case by case. ``case`` defines a case
  and its verdict vocabulary (decision EL-014).

Two things are called ``Verdict``, so the case vocabulary is not re-exported here:

- ``evalloop.memory.case.Verdict`` is EL-014's enum: passed, failed or inconclusive.
- ``evalloop.memory.Verdict`` is the episodic store's record of a grader's decision.

Import the enum from ``evalloop.memory.case``. Renaming the record is raised as a follow-up to
EL-202.
"""

from __future__ import annotations

from evalloop.memory.case import (
    CaseKind,
    CaseResult,
    FailureClass,
    OracleConfidence,
    PermanentCase,
    Timeout,
    TimeoutCap,
    content_hash,
)
from evalloop.memory.episodic import (
    SCHEMA_VERSION,
    Classification,
    Episode,
    EpisodicStore,
    EpisodicStoreBusy,
    EpisodicStoreError,
    Label,
    PlanEntry,
    PlanSnapshot,
    PlanState,
    Trigger,
    Verdict,
    Why,
)
from evalloop.memory.metric_store import (
    MetricStore,
    MetricStoreError,
    Run,
    RunDiff,
    diff_runs,
)

__all__ = [
    "SCHEMA_VERSION",
    "CaseKind",
    "CaseResult",
    "FailureClass",
    "MetricStore",
    "MetricStoreError",
    "OracleConfidence",
    "PermanentCase",
    "Run",
    "RunDiff",
    "Timeout",
    "TimeoutCap",
    "content_hash",
    "diff_runs",
    "Classification",
    "Episode",
    "EpisodicStore",
    "EpisodicStoreBusy",
    "EpisodicStoreError",
    "Label",
    "PlanEntry",
    "PlanSnapshot",
    "PlanState",
    "Trigger",
    "Verdict",
    "Why",
]
