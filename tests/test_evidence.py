"""The evidence assembler: counts the countable, keeps the rest honestly absent.

The load-bearing test is ``test_every_requires_key_is_accounted_for``: it rebuilds the key set
from the registry at test time, so a ``requires`` key added, removed or retyped in any record
**fails here** rather than slipping through as a silently un-produced bar.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.memory import evidence as evidence_module
from evalloop.memory.case import CaseKind, CaseResult, FailureClass, OracleConfidence, Verdict
from evalloop.memory.evidence import (
    SESSION_FACT_KEYS,
    Bar,
    EvidenceGroup,
    assemble_evidence,
    assemble_report,
)
from evalloop.memory.metric_store import MetricStore
from evalloop.plan.planner import plan
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.vocab import Situation, Tool

RECORDS = load_records(RECORDS_DIR)
_H = "a" * 64


def _case(case_id: str, verdict: Verdict = Verdict.passed, failure: FailureClass | None = None, *, run: str = "r1") -> CaseResult:
    return CaseResult(
        run_id=run,
        record_id="A1_execution_based",
        case_id=case_id,
        case_kind=CaseKind.generated,
        artifact_id="src/pricing.py",
        oracle_id=f"tests/test_pricing.py::{case_id}",
        oracle_confidence=OracleConfidence.high,
        ladder_rung=1,
        verdict=verdict,
        failure_class=failure,
        timeout=None,
        inconclusive_reason=None,
        score=None,
        evidence=None,
        artifact_hash=_H,
        oracle_hash=_H,
        reused_from=None,
        seed=None,
        cost_usd=None,
        duration_seconds=0.1,
    )


@pytest.fixture
def store(tmp_path: Path) -> MetricStore:
    s = MetricStore(tmp_path)
    s.write_run("r1", [_case("c1"), _case("c2", Verdict.failed, FailureClass.wrong_result)])
    return s


def _registry_requires() -> dict[str, str]:
    """Every distinct requires key in the registry, mapped to 'bool' or 'numeric'."""
    kinds: dict[str, str] = {}
    for record in RECORDS:
        for key, need in record.requires.items():
            kinds[key] = "bool" if isinstance(need, bool) else "numeric"
    return kinds


# -- the coverage test: the key set comes from the registry, at test time ----------------


def test_every_requires_key_is_accounted_for() -> None:
    registry = _registry_requires()
    planned = evidence_module._KEY_PLAN
    # Exactly the registry's keys -- a key added or removed in any record fails here.
    assert set(planned) == set(registry), (
        f"plan is missing {set(registry) - set(planned)}, or has stale {set(planned) - set(registry)}"
    )
    for key, kind in registry.items():
        plan_entry = planned[key]
        assert plan_entry.kind == kind, f"{key}: registry says {kind}, plan says {plan_entry.kind}"
        if plan_entry.group in (EvidenceGroup.countable, EvidenceGroup.session_fact):
            assert plan_entry.bar is not None  # a produced key feeds a bar
        else:
            # an absent key names the milestone that will answer it, and nothing pretends to a bar
            assert plan_entry.bar is None and plan_entry.answered_by


def test_the_groups_have_the_sizes_checked_against_the_records() -> None:
    sizes = {group: 0 for group in EvidenceGroup}
    for plan_entry in evidence_module._KEY_PLAN.values():
        sizes[plan_entry.group] += 1
    assert sizes == {
        EvidenceGroup.countable: 4,
        EvidenceGroup.session_fact: 7,
        EvidenceGroup.store_field_absent: 5,
        EvidenceGroup.process_fact_absent: 3,
        EvidenceGroup.judge_trust_absent: 15,
    }
    assert SESSION_FACT_KEYS == {k for k, p in evidence_module._KEY_PLAN.items() if p.group is EvidenceGroup.session_fact}
    assert len(evidence_module._KEY_PLAN) == 34


# -- counting the countable, and never more ----------------------------------------------


def test_only_the_countable_keys_are_produced_without_session_facts(store: MetricStore) -> None:
    produced = assemble_evidence(store, "r1", {})
    assert dict(produced) == {"runs": 1, "trials": 1, "failures": 1}  # nothing estimated, nothing defaulted


def test_runs_and_failures_are_counted_from_the_store(tmp_path: Path) -> None:
    s = MetricStore(tmp_path)
    s.write_run("r1", [_case("c1"), _case("c2")])
    s.write_run("r2", [_case("c1", Verdict.failed, FailureClass.runtime_error, run="r2")])
    report = assemble_report(s, "r2", {})
    assert report.item("runs").value == 2 and report.item("trials").value == 2
    assert report.item("failures").value == 1  # counted in the named run, r2


def test_booleans_and_numerics_stay_distinct(store: MetricStore) -> None:
    produced = assemble_evidence(store, "r1", {"environment_resets_per_run": True, "judgment_orders": 2})
    assert produced["environment_resets_per_run"] is True
    assert produced["judgment_orders"] == 2 and not isinstance(produced["judgment_orders"], bool)


# -- absent and zero are different (the honest-state rule) --------------------------------


def test_absent_and_a_counted_zero_read_differently(tmp_path: Path) -> None:
    s = MetricStore(tmp_path)
    s.write_run("r1", [_case("c1"), _case("c2")])  # no failures -> a genuine, measured zero
    report = assemble_report(s, "r1", {})
    failures = report.item("failures")
    positives = report.item("positives")
    assert failures.present and failures.value == 0 and "counted 0" in failures.reason
    assert not positives.present and positives.value is None and "absent" in positives.reason
    assert failures.reason != positives.reason
    # And the distinction survives into the mapping plan() consumes:
    mapping = assemble_evidence(s, "r1", {})
    assert mapping["failures"] == 0 and "positives" not in mapping


# -- F2: what bar each produced key feeds ------------------------------------------------


def test_the_produced_keys_split_into_evidence_and_precondition_never_trust() -> None:
    produced = [p for p in evidence_module._KEY_PLAN.values() if p.bar is not None]
    evidence_bars = {k for k, p in evidence_module._KEY_PLAN.items() if p.bar is Bar.evidence}
    precondition_bars = {k for k, p in evidence_module._KEY_PLAN.items() if p.bar is Bar.precondition}
    assert evidence_bars == {"runs", "trials", "failures", "discordant_pairs", "judgment_orders"}
    assert precondition_bars == {
        "environment_resets_per_run",
        "cluster_id_recorded",
        "paired_ci_available",
        "sample_size_stated",
        "recall_at_k_measured",
        "requires_pre_instrumentation",
    }
    assert all(p.bar is not Bar.trust for p in produced)  # every trust bar is an absent judge key


# -- discordant pairs need a second candidate --------------------------------------------


def test_discordant_pairs_are_absent_without_a_comparison_and_counted_with_one(tmp_path: Path) -> None:
    s = MetricStore(tmp_path)
    s.write_run("r1", [_case("c1"), _case("c2")])
    s.write_run("r2", [_case("c1", Verdict.failed, FailureClass.wrong_result, run="r2"), _case("c2", run="r2")])
    without = assemble_report(s, "r2", {})
    assert not without.item("discordant_pairs").present
    assert "comparison_run" in without.item("discordant_pairs").reason
    with_cmp = assemble_report(s, "r2", {}, comparison_run="r1")
    item = with_cmp.item("discordant_pairs")
    assert item.present and item.value == 1  # c1 flipped passed->failed


# -- session facts: only session keys, of the right kind ---------------------------------


def test_session_facts_may_only_carry_session_keys(store: MetricStore) -> None:
    with pytest.raises(ValueError, match="not session facts"):
        assemble_evidence(store, "r1", {"positives": 100})  # hand-feeding an unanswerable bar
    with pytest.raises(ValueError, match="not session facts"):
        assemble_evidence(store, "r1", {"runs": 99})  # even a countable key cannot be overridden


@pytest.mark.parametrize(
    ("facts", "match"),
    [
        ({"environment_resets_per_run": 5}, "boolean"),
        ({"judgment_orders": True}, "numeric"),
        ({"judgment_orders": "two"}, "numeric"),
    ],
)
def test_a_session_fact_of_the_wrong_kind_is_refused(store: MetricStore, facts: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        assemble_evidence(store, "r1", facts)


def test_an_unknown_run_is_refused(store: MetricStore) -> None:
    with pytest.raises(ValueError, match="not in the store"):
        assemble_evidence(store, "nope", {})
    with pytest.raises(ValueError, match="comparison run"):
        assemble_evidence(store, "r1", {}, comparison_run="nope")


# -- assemble_evidence is the mapping of assemble_report ---------------------------------


def test_assemble_evidence_is_the_reports_mapping(store: MetricStore) -> None:
    facts: dict[str, object] = {"environment_resets_per_run": True}
    assert dict(assemble_evidence(store, "r1", facts)) == assemble_report(store, "r1", facts).mapping()


# -- the round trip: real evidence -> plan() -> verbatim pending reasons ------------------


def test_round_trip_renders_agent_md_pending_reasons_verbatim(store: MetricStore) -> None:
    evidence = assemble_evidence(store, "r1", {})  # runs=1
    produced = plan(RECORDS, [Situation.stochastic_system], [], evidence)
    assert produced.pending["C3_repeat_runs"] == "needs runs: 5, have 1"

    agent = plan(RECORDS, [Situation.agent_action], [Tool.sandbox, Tool.snapshot_restore], evidence)
    assert agent.pending["H8_flaky_classification"] == "needs environment_resets_per_run: true, have false; trials: 5, have 1"

    with_reset = assemble_evidence(store, "r1", {"environment_resets_per_run": True})
    agent2 = plan(RECORDS, [Situation.agent_action], [Tool.sandbox, Tool.snapshot_restore], with_reset)
    assert agent2.pending["H8_flaky_classification"] == "needs trials: 5, have 1"


def test_a_failures_bar_renders_the_counted_value(tmp_path: Path) -> None:
    s = MetricStore(tmp_path)
    s.write_run("r1", [_case(f"c{i}", Verdict.failed, FailureClass.wrong_result) for i in range(3)])
    evidence = assemble_evidence(s, "r1", {})
    produced = plan(RECORDS, [Situation.debugging_regression], [Tool.production_logs], evidence)
    assert produced.pending["I3_error_analysis"] == "needs failures: 100, have 3"
