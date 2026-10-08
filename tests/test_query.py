"""``match``: selection, the merge, and the ordering rules.

Every test here builds its own records. **None of them loads the registry**, on
purpose: these tests are the *statement* of the ordering rules, and a test that
asserted them through 73 real files would break when a record was re-typed for
an unrelated reason, and would pass for the wrong reason if the rule were
weakened and the registry happened not to contain a counterexample.

The real registry is checked separately and once, in
``test_the_shipped_registry_comes_out_in_step_seven_order``, which asserts only
that the shipped records do not contradict the rule -- not what the rule is.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.registry.query import TYPE_GROUP_ORDER, match, sort_key
from evalloop.registry.schema import Cost, Gate, RecordType, TechniqueRecord
from evalloop.vocab import Situation

#: A seed, so a shuffle failure is reproducible from the test name alone.
SHUFFLE_SEED = 20_117


def _record(
    record_id: str,
    record_type: RecordType = RecordType.metric,
    *,
    triggers: tuple[Situation, ...] = (Situation.code_generation,),
    ladder_priority: int | None = None,
) -> TechniqueRecord:
    """A schema-valid record with only the fields ordering depends on varied."""
    if record_type is not RecordType.grader:
        ladder_priority = None
    base: dict[str, Any] = {
        "id": record_id,
        "section": record_id[0],
        "name": record_id,
        "type": record_type,
        "triggers_on_situation": triggers,
        "required_signals": ("a precondition",),
        "required_tools": (),
        "ladder_priority": ladder_priority,
        "requires": {},
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
        "source_ref": "hand-built, tests/test_query.py",
        "extraction_notes": None,
    }
    return TechniqueRecord(**base)


def _ids(records: tuple[TechniqueRecord, ...]) -> list[str]:
    return [record.id for record in records]


# -- selection ------------------------------------------------------------


def test_selects_records_the_situation_triggers() -> None:
    wanted = _record("A1_wanted", triggers=(Situation.code_generation,))
    other = _record("A2_other", triggers=(Situation.summarization,))
    assert _ids(match([wanted, other], [Situation.code_generation])) == ["A1_wanted"]


def test_a_record_with_several_triggers_is_selected_by_any_of_them() -> None:
    record = _record("A1_two", triggers=(Situation.code_generation, Situation.sql_generation))
    for situation in (Situation.code_generation, Situation.sql_generation):
        assert _ids(match([record], [situation])) == ["A1_two"]


def test_no_situation_selects_nothing() -> None:
    """Empty in, empty out -- not "everything", which no source justifies."""
    assert match([_record("A1_any")], []) == ()


def test_no_record_matches_without_an_overlapping_situation() -> None:
    record = _record("A1_prose", triggers=(Situation.prose_generation,))
    assert match([record], [Situation.rare_class]) == ()


# -- the multi-label merge (fixture 18's case) ----------------------------


def test_multi_label_merges_without_duplication() -> None:
    """Fixture 18: one record triggered by two input situations appears ONCE.

    This is the case a merge implemented as "for each situation, extend the
    list" gets wrong, and it is the reason ``match`` walks the records once and
    tests against the whole situation set.
    """
    shared = _record(
        "A1_execution_based",
        RecordType.grader,
        triggers=(Situation.api_endpoint, Situation.sql_generation),
        ladder_priority=1,
    )
    selected = match([shared], [Situation.api_endpoint, Situation.sql_generation])
    assert _ids(selected) == ["A1_execution_based"]


def test_multi_label_still_takes_the_union_of_different_records() -> None:
    """Dedup must not become "only the records every situation triggers"."""
    one = _record("A1_api", triggers=(Situation.api_endpoint,))
    two = _record("A2_sql", triggers=(Situation.sql_generation,))
    both = _record("A3_both", triggers=(Situation.api_endpoint, Situation.sql_generation))
    selected = match([one, two, both], [Situation.api_endpoint, Situation.sql_generation])
    assert _ids(selected) == ["A1_api", "A2_sql", "A3_both"]


# -- order ----------------------------------------------------------------


def test_graders_come_before_every_non_grader() -> None:
    records = [
        _record("B9_constraint", RecordType.constraint),
        _record("A9_metric", RecordType.metric),
        _record("J1_grader", RecordType.grader, ladder_priority=5),
    ]
    # Ids are chosen so the grader sorts LAST alphabetically: a key that
    # ignored `type` would put it at the end instead of the front.
    assert _ids(match(records, [Situation.code_generation])) == [
        "J1_grader",
        "A9_metric",
        "B9_constraint",
    ]


def test_graders_are_ordered_by_ladder_priority_ascending() -> None:
    """1 execution, 2 end-state, 3 deterministic, 4 judge, 5 human."""
    records = [
        _record("A4_judge", RecordType.grader, ladder_priority=4),
        _record("A1_execution", RecordType.grader, ladder_priority=1),
        _record("A6_human", RecordType.grader, ladder_priority=5),
        _record("A2_end_state", RecordType.grader, ladder_priority=2),
    ]
    assert _ids(match(records, [Situation.code_generation])) == [
        "A1_execution",
        "A2_end_state",
        "A4_judge",
        "A6_human",
    ]


def test_ladder_priority_beats_id_for_graders() -> None:
    """A lower rung wins even when its id sorts later -- the real A/B shape."""
    records = [
        _record("A3_deterministic", RecordType.grader, ladder_priority=3),
        _record("J1_execution", RecordType.grader, ladder_priority=1),
    ]
    assert _ids(match(records, [Situation.code_generation])) == [
        "J1_execution",
        "A3_deterministic",
    ]


def test_graders_sharing_a_rung_are_ordered_by_id() -> None:
    """A3 and A5 both carry rung 3; the corpus never orders them, so id does."""
    records = [
        _record("A5_schema_field_scoring", RecordType.grader, ladder_priority=3),
        _record("A3_normalised_exact_match", RecordType.grader, ladder_priority=3),
    ]
    assert _ids(match(records, [Situation.code_generation])) == [
        "A3_normalised_exact_match",
        "A5_schema_field_scoring",
    ]


def test_an_unrunged_grader_sorts_after_every_runged_one() -> None:
    """``B2_pairwise_preference``'s case: a grader the ladder never ranks.

    It sorts last among graders rather than at a guessed rung, which is the
    same refusal EL-113 made when it declined to invent a rung for B2.
    """
    records = [
        _record("B2_pairwise_preference", RecordType.grader, ladder_priority=None),
        _record("A6_expert_human_review", RecordType.grader, ladder_priority=5),
    ]
    assert _ids(match(records, [Situation.code_generation])) == [
        "A6_expert_human_review",
        "B2_pairwise_preference",
    ]


def test_non_graders_are_grouped_in_the_documented_type_order() -> None:
    """grader -> metric -> statistic -> diagnostic -> procedure -> constraint.

    Ids are chosen to sort in exactly the reverse order, so a key that ignored
    ``type`` would produce the reverse of this list and the test would fail.
    """
    records = [
        _record("A1_constraint", RecordType.constraint),
        _record("B2_procedure", RecordType.procedure),
        _record("C3_diagnostic", RecordType.diagnostic),
        _record("D4_statistic", RecordType.statistic),
        _record("E5_metric", RecordType.metric),
        _record("F6_grader", RecordType.grader, ladder_priority=3),
    ]
    assert _ids(match(records, [Situation.code_generation])) == [
        "F6_grader",
        "E5_metric",
        "D4_statistic",
        "C3_diagnostic",
        "B2_procedure",
        "A1_constraint",
    ]


def test_ids_break_the_tie_within_one_type_group() -> None:
    records = [
        _record("C9_zebra", RecordType.statistic),
        _record("C1_alpha", RecordType.statistic),
        _record("C5_middle", RecordType.statistic),
    ]
    assert _ids(match(records, [Situation.code_generation])) == [
        "C1_alpha",
        "C5_middle",
        "C9_zebra",
    ]


# -- purity ---------------------------------------------------------------


def test_order_is_stable_under_a_shuffled_input() -> None:
    """The output order comes from the key, never from the input order.

    Without this property a fixture's ``ready`` list would assert the order its
    author happened to type.
    """
    records = [
        _record("A1_execution", RecordType.grader, ladder_priority=1),
        _record("A4_judge", RecordType.grader, ladder_priority=4),
        _record("B2_unrunged", RecordType.grader, ladder_priority=None),
        _record("C1_statistic", RecordType.statistic),
        _record("D1_constraint", RecordType.constraint),
        _record("E1_diagnostic", RecordType.diagnostic),
        _record("G1_metric", RecordType.metric),
        _record("I1_procedure", RecordType.procedure),
    ]
    expected = _ids(match(records, [Situation.code_generation]))
    rng = random.Random(SHUFFLE_SEED)
    for _ in range(25):
        shuffled = records[:]
        rng.shuffle(shuffled)
        assert _ids(match(shuffled, [Situation.code_generation])) == expected


def test_situation_order_does_not_change_the_result() -> None:
    records = [
        _record("A1_api", triggers=(Situation.api_endpoint,)),
        _record("A2_sql", triggers=(Situation.sql_generation,)),
    ]
    forward = match(records, [Situation.api_endpoint, Situation.sql_generation])
    reverse = match(records, [Situation.sql_generation, Situation.api_endpoint])
    assert forward == reverse


def test_match_does_not_mutate_its_arguments() -> None:
    records = [
        _record("C9_zebra", RecordType.statistic),
        _record("C1_alpha", RecordType.statistic),
    ]
    before = list(records)
    situations = [Situation.code_generation]
    match(records, situations)
    assert records == before
    assert situations == [Situation.code_generation]


def test_match_consumes_iterators_once_and_works_with_generators() -> None:
    records = [_record("C1_alpha", RecordType.statistic), _record("C9_zebra")]
    selected = match(
        (record for record in records), (s for s in (Situation.code_generation,))
    )
    assert _ids(selected) == ["C9_zebra", "C1_alpha"]  # metric before statistic


def test_two_calls_return_equal_tuples() -> None:
    records = [_record("A1_one"), _record("A2_two")]
    first = match(records, [Situation.code_generation])
    second = match(records, [Situation.code_generation])
    assert first == second
    assert isinstance(first, tuple)


def test_duplicate_ids_are_returned_rather_than_silently_halved() -> None:
    """``check_integrity`` owns duplicate ids; ``match`` must not hide one."""
    records = [_record("A1_twice"), _record("A1_twice")]
    assert len(match(records, [Situation.code_generation])) == 2


# -- the type-group order is a decision, and stays one --------------------


def test_type_group_order_covers_every_record_type() -> None:
    """A seventh ``RecordType`` must be placed by a person, not by a default.

    Without this, adding a type would leave ``_TYPE_RANK`` without a key and
    ``match`` would raise at runtime on the first record of that type -- in a
    plan, not in a test.
    """
    assert set(TYPE_GROUP_ORDER) == set(RecordType)
    assert len(TYPE_GROUP_ORDER) == len(set(TYPE_GROUP_ORDER)), "no type twice"


def test_type_group_order_matches_the_enum_declaration_order() -> None:
    """A tripwire, not a derivation.

    ``TYPE_GROUP_ORDER`` is written out explicitly so the order is a documented
    decision rather than an artifact of how the enum happens to be spelled. It
    currently agrees with the declaration order, and if someone reorders
    ``RecordType`` for a cosmetic reason this test says so, so the two can be
    re-reconciled deliberately.
    """
    assert TYPE_GROUP_ORDER == tuple(RecordType)


# -- the shipped registry, checked once -----------------------------------


def test_the_shipped_registry_comes_out_in_step_seven_order() -> None:
    """The 73 real records do not contradict the rule the tests above state."""
    records = load_records(RECORDS_DIR)
    for situation in Situation:
        selected = match(records, [situation])
        keys = [sort_key(record) for record in selected]
        assert keys == sorted(keys), situation
