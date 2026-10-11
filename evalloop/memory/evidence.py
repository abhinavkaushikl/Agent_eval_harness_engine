"""Assemble ``plan()``'s fourth argument from what was actually measured.

``plan(records, situations, available_tools, evidence)`` reads an
``evidence: Mapping[str, object]`` to decide readiness (step 4), and nothing in
M1 as first scoped produced it -- so every bar was fed by hand, which makes the
pending queue, the system's whole honesty claim, a literal. This module is the
producer. It counts what the metric store can honestly count and **declares
everything else absent**, because:

**A key no component can honestly answer is ABSENT, not zero.**
``evaluate_readiness`` treats a missing key as unmet (it never assumes
satisfied), and absent is the honest state. A guessed ``runs: 5`` turns a pending
check into a false claim -- the exact failure ``CLAUDE.md`` §3 ("never invent a
number") and ``AGENT.md`` §5 exist to prevent. So no key is ever filled with a
plausible default: a key is counted from real data, taken from a stated session
fact, or left out of the mapping entirely, with a reason that names the milestone
which will answer it.

The 34 ``requires`` keys, grouped against the registry
------------------------------------------------------
All 73 records declare **34 distinct** ``requires`` keys. Each is in exactly one
group below; :data:`_KEY_PLAN` is that grouping, and ``tests/test_evidence.py``
rebuilds the key set from the registry at test time and fails if a key is added,
removed or retyped -- so a new bar cannot pass silently.

* **countable (4)** -- ``runs``, ``trials``, ``failures``, ``discordant_pairs``:
  counted from EL-201's metric store. ``discordant_pairs`` needs two candidate
  runs, so it is produced only when a ``comparison_run`` is given, and is absent
  otherwise rather than guessed at 0.
* **session fact (7)** -- ``environment_resets_per_run``, ``cluster_id_recorded``,
  ``paired_ci_available``, ``sample_size_stated``, ``recall_at_k_measured``,
  ``requires_pre_instrumentation``, ``judgment_orders``: things the harness or
  session knows but the store does not. Taken from ``session_facts`` when
  supplied, absent otherwise. ``session_facts`` may carry **only** these keys;
  any other key is a caller error (it would be hand-feeding an unanswerable bar).
* **store field absent (5)** -- ``positives``, ``attempts_per_category``,
  ``candidates``, ``smoke_items``, ``benchmarks``: need a field EL-201's v1 store
  does not have, and no M1 technique uses. Always absent.
* **process fact absent (3)** -- ``pre_registration_filed``,
  ``release_history_available``, ``baseline_days``: process facts no M1 component
  knows. Always absent.
* **judge trust absent (15)** -- every judge-trust and annotator-agreement bar.
  All M4. Always absent.

I checked the grouping against the records and agree with it, with one
correction reported to the ticket author: **three** records carry a boolean *and*
a numeric bound (``G3_faithfulness``, ``H3_pass_hat_k``, ``H8_flaky_classification``),
not six. The "17 records carry a boolean requirement" figure is right.

Booleans and numerics are kept distinct
---------------------------------------
``evaluate_readiness`` compares a numeric bar with ``>=`` and a boolean bar as a
fact that must hold, so the value this module produces must be of the
requirement's own kind. :data:`_KEY_PLAN` records each key's kind, the coverage
test checks it against the registry, and a session fact supplied as the wrong
type is refused rather than coerced.

F2, which this is the first code to confront
--------------------------------------------
F2 is the open Gate 0 finding that ``requires`` holds two different bars --
"enough evidence yet" and "trustworthy enough to use". Classifying the produced
keys forced a **third** kind into the open: a methodological **precondition**
(the environment must reset, cluster ids must be recorded, recall@k must be
measured first). Of the keys M1 can produce, the numeric ones are *evidence*
bars and the boolean session facts are *preconditions*; **none is a trust bar** --
every trust bar is a judge-kappa key, and those are all absent (M4). That is the
finding, reported as evidence for the F2 ruling, not routed around. See
:class:`Bar`.

Scope: this reads the store and classifies keys. It does not change the planner,
a record, ``requires``, or build the M3 pending-queue renderer, and it produces
no judge-trust key (all M4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from evalloop._compat import StrEnum
from evalloop.memory.case import Verdict
from evalloop.memory.metric_store import MetricStore, diff_runs

__all__ = [
    "Bar",
    "EvidenceGroup",
    "EvidenceItem",
    "EvidenceReport",
    "SESSION_FACT_KEYS",
    "assemble_evidence",
    "assemble_report",
]


class EvidenceGroup(StrEnum):
    """Which of the five groups a ``requires`` key is in -- how, or whether, M1 can answer it."""

    countable = "countable"
    session_fact = "session_fact"
    store_field_absent = "store_field_absent"
    process_fact_absent = "process_fact_absent"
    judge_trust_absent = "judge_trust_absent"


class Bar(StrEnum):
    """F2's two kinds of bar, plus the third this ticket surfaces. ``None`` for an absent key."""

    evidence = "evidence"          # "enough evidence yet": an accumulation count
    trust = "trust"                # "trustworthy enough to use": a measured trust bar
    precondition = "precondition"  # neither: a methodological precondition that must hold


_PRODUCED = frozenset({EvidenceGroup.countable, EvidenceGroup.session_fact})
_NUMERIC = "numeric"
_BOOL = "bool"


@dataclass(frozen=True, slots=True)
class _KeyPlan:
    group: EvidenceGroup
    kind: str  # _NUMERIC or _BOOL -- the requirement's type, checked against the registry
    answered_by: str
    bar: Bar | None  # only for a produced key


def _absent_plan(group: EvidenceGroup, kind: str, answered_by: str) -> _KeyPlan:
    return _KeyPlan(group, kind, answered_by, None)


#: Every ``requires`` key in the registry, grouped. The coverage test proves this is exactly the
#: registry's key set, with each kind matching -- a key added to a record fails the test here.
_KEY_PLAN: Mapping[str, _KeyPlan] = {
    # -- countable, from the metric store --
    "runs": _KeyPlan(EvidenceGroup.countable, _NUMERIC, "M1", Bar.evidence),
    "trials": _KeyPlan(EvidenceGroup.countable, _NUMERIC, "M1", Bar.evidence),
    "failures": _KeyPlan(EvidenceGroup.countable, _NUMERIC, "M1", Bar.evidence),
    "discordant_pairs": _KeyPlan(EvidenceGroup.countable, _NUMERIC, "M1 (with a comparison run)", Bar.evidence),
    # -- session / harness facts --
    "environment_resets_per_run": _KeyPlan(EvidenceGroup.session_fact, _BOOL, "M1 session", Bar.precondition),
    "cluster_id_recorded": _KeyPlan(EvidenceGroup.session_fact, _BOOL, "M1 session", Bar.precondition),
    "paired_ci_available": _KeyPlan(EvidenceGroup.session_fact, _BOOL, "M1 session", Bar.precondition),
    "sample_size_stated": _KeyPlan(EvidenceGroup.session_fact, _BOOL, "M1 session", Bar.precondition),
    "recall_at_k_measured": _KeyPlan(EvidenceGroup.session_fact, _BOOL, "M1 session", Bar.precondition),
    "requires_pre_instrumentation": _KeyPlan(EvidenceGroup.session_fact, _BOOL, "M1 session", Bar.precondition),
    "judgment_orders": _KeyPlan(EvidenceGroup.session_fact, _NUMERIC, "M1 session", Bar.evidence),
    # -- needs a store field v1 does not have, and no M1 technique uses --
    "positives": _absent_plan(EvidenceGroup.store_field_absent, _NUMERIC, "a metric-store v2 field; Track V / M3"),
    "attempts_per_category": _absent_plan(EvidenceGroup.store_field_absent, _NUMERIC, "a metric-store v2 field; M4"),
    "candidates": _absent_plan(EvidenceGroup.store_field_absent, _NUMERIC, "a metric-store v2 field; M3"),
    "smoke_items": _absent_plan(EvidenceGroup.store_field_absent, _NUMERIC, "a metric-store v2 field; M3"),
    "benchmarks": _absent_plan(EvidenceGroup.store_field_absent, _NUMERIC, "a metric-store v2 field; M3"),
    # -- process facts no M1 component knows --
    "pre_registration_filed": _absent_plan(EvidenceGroup.process_fact_absent, _BOOL, "a process fact; M3"),
    "release_history_available": _absent_plan(EvidenceGroup.process_fact_absent, _BOOL, "a process fact; M3"),
    "baseline_days": _absent_plan(EvidenceGroup.process_fact_absent, _NUMERIC, "a process fact; M3"),
    # -- judge trust and annotator agreement, all M4 --
    "judge_human_kappa_to_trust": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "judge_human_kappa_to_gate": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "judge_labelled_items": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "judge_families": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "expert_kappa": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "target_agreement": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "annotators": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "human_pairwise_judgments": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "alpha_tentative": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "alpha_reliable": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "claim_labels": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "items": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "fail_cases": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "calibration_items": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
    "majority_samples": _absent_plan(EvidenceGroup.judge_trust_absent, _NUMERIC, "M4 judge trust"),
}

#: The keys a caller may supply in ``session_facts`` -- no other key may be hand-fed.
SESSION_FACT_KEYS: frozenset[str] = frozenset(
    key for key, plan in _KEY_PLAN.items() if plan.group is EvidenceGroup.session_fact
)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One ``requires`` key's accounting: present with a value, or absent, each with a reason."""

    key: str
    present: bool
    value: int | float | bool | None
    reason: str
    group: EvidenceGroup
    answered_by: str
    bar: Bar | None


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """Every ``requires`` key accounted for: what was measured, and why the rest is absent."""

    run_id: str
    items: tuple[EvidenceItem, ...]

    def mapping(self) -> dict[str, object]:
        """The evidence ``plan()`` consumes: only the keys that were honestly answered."""
        return {item.key: item.value for item in self.items if item.present}

    def item(self, key: str) -> EvidenceItem:
        for item in self.items:
            if item.key == key:
                return item
        raise KeyError(key)

    @property
    def produced(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.items if item.present)

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.items if not item.present)


def _check_kind(key: str, plan: _KeyPlan, value: object) -> int | float | bool:
    """A session fact must be of the requirement's own kind: a bool is not a count, nor a count a fact."""
    if plan.kind is _BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"session fact {key!r} is a boolean requirement; got {value!r}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"session fact {key!r} is a numeric requirement; got {value!r}")
    return value


def assemble_report(
    store: MetricStore,
    run_id: str,
    session_facts: Mapping[str, object],
    *,
    comparison_run: str | None = None,
) -> EvidenceReport:
    """Account for every ``requires`` key for ``run_id``: count the countable, pass stated session
    facts, and declare the rest absent with the milestone that will answer it.

    ``session_facts`` may hold only :data:`SESSION_FACT_KEYS`; any other key is refused, because
    feeding an unanswerable bar by hand is the dishonesty this exists to prevent. ``comparison_run``
    is the second candidate run that makes ``discordant_pairs`` countable.
    """
    known = set(store.runs())
    if run_id not in known:
        raise ValueError(f"run {run_id!r} is not in the store")
    if comparison_run is not None and comparison_run not in known:
        raise ValueError(f"comparison run {comparison_run!r} is not in the store")
    unexpected = set(session_facts) - SESSION_FACT_KEYS
    if unexpected:
        raise ValueError(
            f"session_facts may only carry session keys {sorted(SESSION_FACT_KEYS)}; "
            f"refusing {sorted(unexpected)} -- those are not session facts and must not be hand-fed"
        )

    run = store.read_run(run_id)
    n_runs = len(known)
    failures = sum(1 for case in run.cases if case.verdict is Verdict.failed)
    counts: dict[str, int] = {"runs": n_runs, "trials": n_runs, "failures": failures}
    count_reason = {
        "runs": f"counted {n_runs} run(s) in the store",
        "trials": f"counted {n_runs} trial(s): one per run in the store (run-granular, not per-case)",
        "failures": f"counted {failures} failed case(s) in run {run_id!r}",
    }

    items: list[EvidenceItem] = []
    for key, plan in _KEY_PLAN.items():
        present = False
        value: int | float | bool | None = None
        reason: str

        if key in counts:
            present, value = True, counts[key]
            reason = count_reason[key]
        elif key == "discordant_pairs":
            if comparison_run is None:
                reason = "absent: needs a second candidate run to compare; pass comparison_run to count it"
            else:
                diff = diff_runs(store.read_run(comparison_run), run)
                present = True
                value = len(diff.regressions) + len(diff.improvements)
                reason = f"counted {value} discordant pair(s) vs run {comparison_run!r} (a passed/failed disagreement)"
        elif plan.group is EvidenceGroup.session_fact:
            if key in session_facts:
                present = True
                value = _check_kind(key, plan, session_facts[key])
                reason = f"supplied by the session: {key}={value}"
            else:
                reason = f"absent: the session did not state {key!r} (a harness/session fact)"
        else:
            reason = f"absent: {_absent_detail(plan.group, key)}; answered by {plan.answered_by}"

        items.append(EvidenceItem(key, present, value, reason, plan.group, plan.answered_by, plan.bar))

    return EvidenceReport(run_id=run_id, items=tuple(items))


def _absent_detail(group: EvidenceGroup, key: str) -> str:
    if group is EvidenceGroup.store_field_absent:
        return f"EL-201's v1 metric store has no {key!r} field, and no M1 technique produces it"
    if group is EvidenceGroup.process_fact_absent:
        return f"no M1 component records the process fact {key!r}"
    return f"{key!r} is a judge-trust / annotator-agreement bar that only M4 can measure"


def assemble_evidence(
    store: MetricStore,
    run_id: str,
    session_facts: Mapping[str, object],
    *,
    comparison_run: str | None = None,
) -> Mapping[str, object]:
    """``plan()``'s fourth argument, from what was measured: the honestly-answered keys only.

    A thin view over :func:`assemble_report`; absent keys are simply not in the mapping, which is
    what ``evaluate_readiness`` reads as unmet. See that function for the full accounting.
    """
    return assemble_report(store, run_id, session_facts, comparison_run=comparison_run).mapping()
