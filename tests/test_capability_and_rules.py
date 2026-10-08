"""``check_capability``, ``apply_conflicts``, ``resolve_companions``.

Hand-built records throughout, so the tests state the rules. The two rulings in
``rules.py``'s docstring are each asserted by the test named after them, and the
registry is touched only in the last two tests, which check that the shipped
records do not contradict either ruling.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from evalloop.plan.capability import Capability, check_capability
from evalloop.plan.rules import apply_conflicts, resolve_companions
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.registry.schema import Cost, Gate, RecordType, TechniqueRecord
from evalloop.vocab import Situation, Tool

SHUFFLE_SEED = 22_122


def _record(
    record_id: str,
    *,
    record_type: RecordType = RecordType.statistic,
    ladder_priority: int | None = None,
    required_tools: tuple[Tool, ...] = (),
    companion_checks: tuple[str, ...] = (),
    conflicts_with: tuple[str, ...] = (),
) -> TechniqueRecord:
    if record_type is not RecordType.grader:
        ladder_priority = None
    base: dict[str, Any] = {
        "id": record_id,
        "section": record_id[0],
        "name": record_id,
        "type": record_type,
        "triggers_on_situation": (Situation.code_generation,),
        "required_signals": ("a precondition",),
        "required_tools": required_tools,
        "ladder_priority": ladder_priority,
        "requires": {},
        "produces": ("a_number",),
        "gates": Gate.false,
        "companion_checks": companion_checks,
        "unlocks": (),
        "conflicts_with": conflicts_with,
        "analysis_cost": Cost.low,
        "capture_cost": None,
        "anti_pattern": "the mistake",
        "worked_example": "1 item, 1 number",
        "domain_scenario": "**Testing**: a hand-built record",
        "rule_of_thumb": None,
        "source_ref": "hand-built, tests/test_capability_and_rules.py",
        "extraction_notes": None,
    }
    return TechniqueRecord(**base)


def _ids(records: tuple[TechniqueRecord, ...]) -> list[str]:
    return [record.id for record in records]


# == capability ===========================================================


def test_a_record_needing_no_tool_is_always_available() -> None:
    """25 of the 73 are like this, which is why a plan says something at n=0."""
    result = check_capability(_record("C1_wilson_ci"), [])
    assert result == Capability(available=True, missing=())


def test_every_tool_granted_is_available() -> None:
    record = _record("A1_execution_based", required_tools=(Tool.sandbox, Tool.test_runner))
    assert check_capability(record, [Tool.sandbox, Tool.test_runner]).available


def test_missing_tools_are_named_not_merely_counted() -> None:
    """``AGENT.md`` §5: a missing tool becomes a permission request."""
    record = _record("A1_execution_based", required_tools=(Tool.sandbox, Tool.test_runner))
    result = check_capability(record, [Tool.test_runner])
    assert result.available is False
    assert result.missing == (Tool.sandbox,)
    assert result.render() == "missing: sandbox"


def test_missing_keeps_the_records_own_tool_order() -> None:
    """H1's case: the order ``H:36-38`` introduces the tools in, not alphabetical.

    ``snapshot_restore`` before ``trace_capture`` is the record's order; sorted
    alphabetically it would be the same, so the test uses a record whose own
    order disagrees with alphabetical to prove which one is kept.
    """
    record = _record(
        "H1_resettable_env",
        required_tools=(Tool.trace_capture, Tool.snapshot_restore, Tool.sandbox),
    )
    result = check_capability(record, [])
    assert result.missing == (Tool.trace_capture, Tool.snapshot_restore, Tool.sandbox)
    assert result.render() == "missing: trace_capture, snapshot_restore, sandbox"


def test_missing_order_does_not_depend_on_the_grant_order() -> None:
    record = _record(
        "H1_resettable_env",
        required_tools=(Tool.trace_capture, Tool.snapshot_restore, Tool.sandbox),
    )
    grants = [Tool.sandbox, Tool.llm_api, Tool.repo_read]
    expected = check_capability(record, grants).missing
    rng = random.Random(SHUFFLE_SEED)
    for _ in range(20):
        shuffled = grants[:]
        rng.shuffle(shuffled)
        assert check_capability(record, shuffled).missing == expected


def test_there_is_no_tool_subsumption() -> None:
    """``llm_api_cross_family`` does not satisfy ``llm_api``. See the docstring.

    A real gap, reported rather than silently fixed: deciding that one grant
    covers another is a policy question about what the user agreed to, and
    decision EL-002 puts that in the capability layer.
    """
    record = _record("A4_judge_binary_criteria", required_tools=(Tool.llm_api,))
    result = check_capability(record, [Tool.llm_api_cross_family])
    assert result.available is False
    assert result.missing == (Tool.llm_api,)


def test_capability_consumes_a_generator() -> None:
    record = _record("A1_execution_based", required_tools=(Tool.sandbox,))
    assert check_capability(record, (t for t in (Tool.sandbox,))).available


def test_an_available_capability_cannot_list_missing_tools() -> None:
    with pytest.raises(ValueError, match="lists missing tools"):
        Capability(available=True, missing=(Tool.sandbox,))


def test_an_unavailable_capability_must_name_what_is_missing() -> None:
    with pytest.raises(ValueError, match="must name the missing tools"):
        Capability(available=False, missing=())


# == conflicts: ruling 1 ==================================================


def test_a_higher_grader_suppresses_a_lower_one() -> None:
    """§3.5 step 5: execution suppresses judging the same property."""
    execution = _record(
        "A1_execution_based",
        record_type=RecordType.grader,
        ladder_priority=1,
        conflicts_with=("A4_judge_binary_criteria",),
    )
    judge = _record("A4_judge_binary_criteria", record_type=RecordType.grader, ladder_priority=4)
    result = apply_conflicts([execution, judge])
    assert _ids(result.kept) == ["A1_execution_based"]
    assert result.suppressed == {"A4_judge_binary_criteria": "replaced by A1_execution_based"}
    assert not result.unapplied


def test_a_lower_grader_does_not_suppress_a_higher_one_and_says_so() -> None:
    """An edge the methodology does not support is left unapplied, not honoured."""
    judge = _record(
        "A4_judge_binary_criteria",
        record_type=RecordType.grader,
        ladder_priority=4,
        conflicts_with=("A1_execution_based",),
    )
    execution = _record("A1_execution_based", record_type=RecordType.grader, ladder_priority=1)
    result = apply_conflicts([judge, execution])
    assert _ids(result.kept) == ["A4_judge_binary_criteria", "A1_execution_based"]
    assert not result.suppressed
    assert "A1_execution_based" in result.unapplied
    assert "rung 4" in result.unapplied["A1_execution_based"]


def test_a_non_grader_replaces_a_non_grader_by_the_edges_direction() -> None:
    """RULING 1's live case: fixture 13, B7 replacing B6, neither with a rung.

    Priority cannot decide it, so ``conflicts_with`` -- "record ids this
    replaces/invalidates" -- is the whole answer.
    """
    cluster = _record("B7_cluster_bootstrap", conflicts_with=("B6_bootstrap_ci",))
    plain = _record("B6_bootstrap_ci")
    result = apply_conflicts([cluster, plain])
    assert _ids(result.kept) == ["B7_cluster_bootstrap"]
    assert result.suppressed == {"B6_bootstrap_ci": "replaced by B7_cluster_bootstrap"}
    assert not result.unapplied


def test_the_edge_direction_is_not_symmetric() -> None:
    """Reversing the declaration reverses the outcome -- it is a directed claim."""
    plain = _record("B6_bootstrap_ci", conflicts_with=("B7_cluster_bootstrap",))
    cluster = _record("B7_cluster_bootstrap")
    assert _ids(apply_conflicts([plain, cluster]).kept) == ["B6_bootstrap_ci"]


def test_an_unrunged_grader_in_a_conflict_falls_back_to_the_edge_direction() -> None:
    """A mixed pair is "anything else", so the direction decides."""
    unrunged = _record(
        "B2_pairwise_preference",
        record_type=RecordType.grader,
        ladder_priority=None,
        conflicts_with=("A4_judge_binary_criteria",),
    )
    judge = _record("A4_judge_binary_criteria", record_type=RecordType.grader, ladder_priority=4)
    result = apply_conflicts([unrunged, judge])
    assert _ids(result.kept) == ["B2_pairwise_preference"]


def test_a_conflict_target_outside_the_plan_does_nothing() -> None:
    """There is nothing to replace, and nothing is reported as replaced."""
    cluster = _record("B7_cluster_bootstrap", conflicts_with=("B6_bootstrap_ci",))
    result = apply_conflicts([cluster])
    assert _ids(result.kept) == ["B7_cluster_bootstrap"]
    assert not result.suppressed


def test_conflict_resolution_does_not_depend_on_input_order() -> None:
    execution = _record(
        "A1_execution_based",
        record_type=RecordType.grader,
        ladder_priority=1,
        conflicts_with=("A4_judge_binary_criteria",),
    )
    judge = _record("A4_judge_binary_criteria", record_type=RecordType.grader, ladder_priority=4)
    cluster = _record("B7_cluster_bootstrap", conflicts_with=("B6_bootstrap_ci",))
    plain = _record("B6_bootstrap_ci")
    records = [execution, judge, cluster, plain]
    rng = random.Random(SHUFFLE_SEED)
    for _ in range(20):
        shuffled = records[:]
        rng.shuffle(shuffled)
        result = apply_conflicts(shuffled)
        assert set(_ids(result.kept)) == {"A1_execution_based", "B7_cluster_bootstrap"}
        assert dict(result.suppressed) == {
            "A4_judge_binary_criteria": "replaced by A1_execution_based",
            "B6_bootstrap_ci": "replaced by B7_cluster_bootstrap",
        }


def test_apply_conflicts_does_not_mutate_its_argument() -> None:
    records = [_record("B7_cluster_bootstrap", conflicts_with=("B6_bootstrap_ci",))]
    before = list(records)
    apply_conflicts(records)
    assert records == before


# == companions: ruling 2 =================================================


def test_a_companion_is_pulled_into_the_plan() -> None:
    host = _record("A1_execution_based", companion_checks=("C1_wilson_ci",))
    companion = _record("C1_wilson_ci")
    result = resolve_companions([host], [host, companion])
    assert _ids(result.added) == ["C1_wilson_ci"]
    assert dict(result.demanded) == {"A1_execution_based": ("C1_wilson_ci",)}


def test_a_companion_already_in_ready_is_demanded_but_not_added_twice() -> None:
    host = _record("A1_execution_based", companion_checks=("C1_wilson_ci",))
    companion = _record("C1_wilson_ci")
    result = resolve_companions([host, companion], [host, companion])
    assert result.added == ()
    assert dict(result.demanded) == {"A1_execution_based": ("C1_wilson_ci",)}


def test_an_unready_companion_is_still_added_and_does_not_hide(
) -> None:
    """RULING 2. The companion joins the plan; the planner buckets it.

    ``resolve_companions`` has neither the evidence nor the grants, so it
    cannot and must not decide that a companion is ready. What it must not do
    is drop the companion -- that would hide the edge -- and what it must not
    do is report the parent as unready, which is fixture 19's ``I1 -> E4``
    case, where holding I1 back would suppress the must-pass gate ``I:33``
    exists to guarantee.
    """
    host = _record("I1_ci_regression_gate", companion_checks=("E4_aa_baseline",))
    # E4 carries a threshold this function knows nothing about, by design.
    companion = _record("E4_aa_baseline")
    result = resolve_companions([host], [host, companion])
    assert _ids(result.added) == ["E4_aa_baseline"]
    assert dict(result.demanded) == {"I1_ci_regression_gate": ("E4_aa_baseline",)}


def test_expansion_is_one_level_not_a_blind_closure() -> None:
    """RULING 2b. The second level is the caller's, because it needs readiness.

    Fixture 10 is why: ``F7`` is ready and names ``F2``, which is pending for
    want of human agreement; ``F2`` names ``B6`` (``F:74``, "Bootstrap κ"), and
    B6 needs no tool and carries no threshold. A blind closure would put B6 in
    ``ready`` -- offering to bootstrap a confidence interval around a κ that
    does not exist.
    """
    host = _record("F7_one_call_per_criterion", companion_checks=("F2_cohens_kappa",))
    middle = _record("F2_cohens_kappa", companion_checks=("B6_bootstrap_ci",))
    leaf = _record("B6_bootstrap_ci")
    result = resolve_companions([host], [host, middle, leaf])
    assert _ids(result.added) == ["F2_cohens_kappa"], "B6 must not be reached"
    assert dict(result.demanded) == {"F7_one_call_per_criterion": ("F2_cohens_kappa",)}


def test_the_second_level_arrives_when_the_caller_passes_a_ready_companion() -> None:
    """Fixture 19's ``E1 -> E4``: the same edge, followed because E1 IS ready.

    Fixtures 7-9 hold the counter-case -- there E1 is pending at one run, so
    the edge is absent. One rule, and the fixtures distinguish the two cases by
    E1's own readiness, which is what makes the loop belong in the planner.
    """
    host = _record("I1_ci_regression_gate", companion_checks=("E1_per_item_diff",))
    middle = _record(
        "E1_per_item_diff",
        record_type=RecordType.diagnostic,
        companion_checks=("E4_aa_baseline",),
    )
    leaf = _record("E4_aa_baseline", record_type=RecordType.diagnostic)
    everything = [host, middle, leaf]

    first = resolve_companions([host], everything)
    assert _ids(first.added) == ["E1_per_item_diff"]

    # the caller found E1 ready, so it joins and the next round follows its edge
    second = resolve_companions([host, middle], everything)
    assert _ids(second.added) == ["E4_aa_baseline"]
    assert dict(second.demanded) == {
        "E1_per_item_diff": ("E4_aa_baseline",),
        "I1_ci_regression_gate": ("E1_per_item_diff",),
    }

    # and a third round adds nothing, which is what ends the loop
    third = resolve_companions([host, middle, leaf], everything)
    assert third.added == ()


def test_a_mutual_companion_pair_settles_in_two_rounds() -> None:
    """``H2`` names ``H4`` (``H:73``) and ``H4`` names ``H2`` (``H:139``).

    The registry's only mutual pair. Recursion would not terminate on it; the
    caller's loop ends when a round adds nothing.
    """
    h2 = _record("H2_outcome_based_success", companion_checks=("H4_cost_per_success",))
    h4 = _record("H4_cost_per_success", companion_checks=("H2_outcome_based_success",))
    first = resolve_companions([h2], [h2, h4])
    assert _ids(first.added) == ["H4_cost_per_success"]
    second = resolve_companions([h2, h4], [h2, h4])
    assert second.added == (), "the second round adds nothing, so the loop ends"
    assert dict(second.demanded) == {
        "H2_outcome_based_success": ("H4_cost_per_success",),
        "H4_cost_per_success": ("H2_outcome_based_success",),
    }


def test_a_dangling_companion_id_is_skipped_not_raised_on() -> None:
    """``check_integrity`` rule 7 owns that defect and names it."""
    host = _record("A1_execution_based", companion_checks=("C1_wilson_c1",))
    result = resolve_companions([host], [host])
    assert result.added == ()
    assert dict(result.demanded) == {"A1_execution_based": ("C1_wilson_c1",)}


def test_added_companions_come_back_in_step_seven_order() -> None:
    host = _record("A1_execution_based", companion_checks=("E1_diag", "C1_stat"))
    stat = _record("C1_stat", record_type=RecordType.statistic)
    diag = _record("E1_diag", record_type=RecordType.diagnostic)
    result = resolve_companions([host], [host, stat, diag])
    assert _ids(result.added) == ["C1_stat", "E1_diag"]  # statistic before diagnostic


def test_resolve_companions_does_not_depend_on_input_order() -> None:
    host = _record("A1_execution_based", companion_checks=("C1_stat", "E1_diag"))
    other = _record("A2_other", companion_checks=("C1_stat",))
    stat = _record("C1_stat")
    diag = _record("E1_diag", record_type=RecordType.diagnostic)
    everything = [host, other, stat, diag]
    expected = resolve_companions([host, other], everything)
    rng = random.Random(SHUFFLE_SEED)
    for _ in range(20):
        shuffled = everything[:]
        rng.shuffle(shuffled)
        result = resolve_companions([host, other], shuffled)
        assert result.added == expected.added
        assert dict(result.demanded) == dict(expected.demanded)


# == the shipped registry does not contradict either ruling ===============


def test_every_registry_conflict_edge_resolves_without_an_unapplied_one() -> None:
    """All five edges in the registry are honoured, four by rung and one by direction."""
    records = load_records(RECORDS_DIR)
    result = apply_conflicts(records)
    assert not result.unapplied, dict(result.unapplied)
    assert dict(result.suppressed) == {
        "A4_judge_binary_criteria": "replaced by A1_execution_based",
        "B6_bootstrap_ci": "replaced by B7_cluster_bootstrap",
    }


def test_companion_resolution_over_the_whole_registry_is_a_fixed_point() -> None:
    """Handed every record, there is nothing left to add -- including H2/H4."""
    records = load_records(RECORDS_DIR)
    result = resolve_companions(records, records)
    assert result.added == ()
    assert sum(len(v) for v in result.demanded.values()) == 72, (
        "the registry holds 72 companion edges"
    )
