"""``evaluate_readiness``: one test per branch, and the reason strings.

The branch tests build their own records, so they state the rules. The reason
strings are then checked against the **real fixtures**, because those strings
are a contract the fixtures assert character for character -- a hand-built test
could agree with a renderer that had drifted from every fixture at once.
"""

from __future__ import annotations

from typing import Any

import pytest

from evalloop.plan.readiness import Readiness, evaluate_readiness, render_value
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.registry.schema import Cost, Gate, RecordType, TechniqueRecord
from evalloop.vocab import Situation
from tests.planner_fixture import load_fixture
from tests.test_planner_fixtures import LIVE_PATHS


def _record(requires: dict[str, Any], record_id: str = "C1_wilson_ci") -> TechniqueRecord:
    base: dict[str, Any] = {
        "id": record_id,
        "section": record_id[0],
        "name": record_id,
        "type": RecordType.statistic,
        "triggers_on_situation": (Situation.small_sample,),
        "required_signals": ("a precondition",),
        "required_tools": (),
        "ladder_priority": None,
        "requires": requires,
        "produces": ("a_number",),
        "gates": Gate.false,
        "companion_checks": (),
        "unlocks": (),
        "conflicts_with": (),
        "analysis_cost": Cost.low,
        "capture_cost": None,
        "anti_pattern": "the mistake",
        "worked_example": "1 item, 1 number",
        "domain_scenario": "**Testing**: a hand-built record",
        "rule_of_thumb": None,
        "source_ref": "hand-built, tests/test_readiness.py",
        "extraction_notes": None,
    }
    return TechniqueRecord(**base)


# -- the seven branches ---------------------------------------------------


def test_empty_requires_is_met() -> None:
    """A record with no threshold fires at n = 1 -- 31 of the 73 are like this."""
    result = evaluate_readiness(_record({}), {})
    assert result == Readiness(met=True, reason=None)


def test_numeric_requirement_met() -> None:
    assert evaluate_readiness(_record({"runs": 2}), {"runs": 2}).met
    assert evaluate_readiness(_record({"runs": 2}), {"runs": 5}).met


def test_numeric_requirement_unmet_names_threshold_and_actual() -> None:
    result = evaluate_readiness(_record({"discordant_pairs": 25}), {"discordant_pairs": 8})
    assert result.met is False
    assert result.reason == "needs discordant_pairs: 25, have 8"


def test_a_missing_key_counts_as_zero_never_as_satisfied() -> None:
    """Rule 2. The capture layer writes what it has seen; silence is not proof."""
    result = evaluate_readiness(_record({"discordant_pairs": 25}), {})
    assert result.met is False
    assert result.reason == "needs discordant_pairs: 25, have 0"


def test_boolean_requirement_met() -> None:
    record = _record({"recall_at_k_measured": True})
    assert evaluate_readiness(record, {"recall_at_k_measured": True}).met


def test_boolean_requirement_unmet_says_true_and_false_not_True_and_zero() -> None:
    """The two faults the ticket names, both avoided.

    ``"needs recall_at_k_measured: True, have 0"`` quotes Python at the user
    and implies a count where there is none.
    """
    record = _record({"recall_at_k_measured": True})
    for evidence in ({}, {"recall_at_k_measured": False}):
        result = evaluate_readiness(record, evidence)
        assert result.reason == "needs recall_at_k_measured: true, have false"
        assert "True" not in result.reason
        assert "have 0" not in result.reason


def test_several_unmet_requirements_are_all_named_in_declaration_order() -> None:
    """Not the first, not the worst, not alphabetical -- all, as declared."""
    record = _record({"recall_at_k_measured": True, "claim_labels": 150})
    result = evaluate_readiness(record, {})
    assert result.reason == (
        "needs recall_at_k_measured: true, have false; claim_labels: 150, have 0"
    )


# -- the judgement calls, each resolving toward "not ready" ---------------


def test_only_met_requirements_are_left_out_of_a_partial_reason() -> None:
    record = _record({"recall_at_k_measured": True, "claim_labels": 150})
    result = evaluate_readiness(record, {"recall_at_k_measured": True})
    assert result.reason == "needs claim_labels: 150, have 0"


def test_a_float_threshold_keeps_its_own_spelling() -> None:
    record = _record({"judge_human_kappa_to_gate": 0.8})
    result = evaluate_readiness(record, {"judge_human_kappa_to_gate": 0.71})
    assert result.reason == "needs judge_human_kappa_to_gate: 0.8, have 0.71"


def test_a_boolean_under_a_numeric_key_counts_as_absent() -> None:
    """A boolean is not a count, and coercing it could only make a record ready."""
    result = evaluate_readiness(_record({"runs": 2}), {"runs": True})
    assert result.met is False
    assert result.reason == "needs runs: 2, have 0"


def test_a_number_under_a_boolean_key_does_not_satisfy_it() -> None:
    """Only ``True`` is proof that the fact holds; 1 is a type error upstream."""
    record = _record({"environment_resets_per_run": True})
    result = evaluate_readiness(record, {"environment_resets_per_run": 1})
    assert result.met is False
    assert result.reason == "needs environment_resets_per_run: true, have false"


def test_an_unusable_evidence_value_counts_as_absent() -> None:
    result = evaluate_readiness(_record({"runs": 2}), {"runs": "two"})
    assert result.reason == "needs runs: 2, have 0"


# -- purity and the result type -------------------------------------------


def test_evaluate_readiness_does_not_mutate_its_arguments() -> None:
    record = _record({"runs": 2})
    evidence = {"runs": 1}
    evaluate_readiness(record, evidence)
    assert evidence == {"runs": 1}
    assert dict(record.requires) == {"runs": 2}


def test_two_calls_agree() -> None:
    record = _record({"runs": 2})
    assert evaluate_readiness(record, {}) == evaluate_readiness(record, {})


def test_a_met_readiness_cannot_carry_a_reason() -> None:
    with pytest.raises(ValueError, match="carries a reason"):
        Readiness(met=True, reason="needs something")


def test_an_unmet_readiness_must_say_why() -> None:
    """``USER_EXPERIENCE.md`` §4 principle 3, enforced by the type."""
    with pytest.raises(ValueError, match="must say what is missing"):
        Readiness(met=False, reason=None)


def test_render_value_spells_booleans_the_way_the_records_do() -> None:
    assert render_value(True) == "true"
    assert render_value(False) == "false"
    assert render_value(25) == "25"
    assert render_value(0.6) == "0.6"
    assert render_value(0) == "0"


# -- the contract: against the real fixtures ------------------------------


def test_every_fixture_pending_reason_is_reproduced_exactly() -> None:
    """The strings are a contract, so they are checked against all of them.

    This is the test that would fail if the reason format were "improved".
    Eight distinct strings across five fixtures, including both κ pairs, both
    boolean forms and the two-clause mixed case.
    """
    records = {record.id: record for record in load_records(RECORDS_DIR)}
    known = frozenset(records)
    checked = 0
    for path in LIVE_PATHS:
        fixture = load_fixture(path, known)
        for record_id, expected in fixture.pending.items():
            result = evaluate_readiness(records[record_id], fixture.evidence)
            assert result.met is False, f"{path.name}: {record_id} should be pending"
            assert result.reason == expected, (
                f"{path.name}: {record_id}\n  fixture: {expected!r}\n  rendered: "
                f"{result.reason!r}"
            )
            checked += 1
    assert checked >= 3, f"only {checked} pending reasons checked"


def test_every_fixture_ready_record_is_actually_ready_on_its_evidence() -> None:
    """The other half of the contract: nothing in ``ready`` is secretly pending.

    Companions reach ``ready`` from outside the situation's own set, so this
    covers records the fixture never mentions in ``pending``.
    """
    records = {record.id: record for record in load_records(RECORDS_DIR)}
    known = frozenset(records)
    for path in LIVE_PATHS:
        fixture = load_fixture(path, known)
        for record_id in fixture.ready:
            result = evaluate_readiness(records[record_id], fixture.evidence)
            assert result.met, f"{path.name}: {record_id} is in ready but {result.reason}"
