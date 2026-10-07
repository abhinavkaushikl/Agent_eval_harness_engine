"""Both sides of every schema rule, on hand-built records.

A mis-typed or mis-validated record still loads and still passes integrity --
it just makes the planner rank a confidence interval on the grading ladder. So
each rule gets a record that must be accepted and one that must be rejected,
and every rejection is checked to name the record id and the offending field,
because EL-108 aggregates these across 73 records and the author reads the
list, not a traceback.

``_record()`` is B3 McNemar's real content, with the figures from the master
lookup. Overriding one field at a time keeps each test about one rule.
"""

import dataclasses
from typing import Any

import pytest

from evalloop.registry.schema import (
    FIELD_NAMES,
    Cost,
    Gate,
    RecordType,
    SchemaError,
    TechniqueRecord,
)
from evalloop.vocab import Situation, Tool

#: CLAUDE.md section 6's field table, in order, with domain_scenario after
#: worked_example per EL-011. A drift tripwire: the schema and the doc agree.
EXPECTED_FIELDS = (
    "id",
    "section",
    "name",
    "type",
    "triggers_on_situation",
    "required_signals",
    "required_tools",
    "ladder_priority",
    "requires",
    "produces",
    "gates",
    "companion_checks",
    "unlocks",
    "conflicts_with",
    "analysis_cost",
    "capture_cost",
    "anti_pattern",
    "worked_example",
    "domain_scenario",
    "rule_of_thumb",
    "source_ref",
    "extraction_notes",
)


def _record(**overrides: Any) -> TechniqueRecord:
    """A valid record (B3 McNemar), with any field overridden."""
    base: dict[str, Any] = {
        "id": "B3_mcnemar",
        "section": "B",
        "name": "McNemar's test",
        "type": RecordType.statistic,
        "triggers_on_situation": (Situation.two_candidates,),
        "required_signals": ("paired binary outcomes on the same items",),
        "required_tools": (),
        "ladder_priority": None,
        "requires": {"discordant_pairs": 25},
        "produces": ("chi_square", "p_value"),
        "gates": Gate.statistical,
        "companion_checks": ("C1_wilson_ci",),
        "unlocks": (),
        "conflicts_with": (),
        "analysis_cost": Cost.low,
        "capture_cost": None,
        "anti_pattern": "A two-proportion z-test assumes independent samples.",
        "worked_example": "500 claims: b = 40, c = 65. chi-square = 5.49, p = 0.019.",
        "domain_scenario": "**Insurance**: old vs new fraud-flag classifier on 500 claims",
        "rule_of_thumb": "b + c < 25 -> exact binomial instead",
        "source_ref": "master lookup, section B",
        "extraction_notes": None,
    }
    base.update(overrides)
    return TechniqueRecord(**base)


# --------------------------------------------------------------------------
# The enums
# --------------------------------------------------------------------------


@pytest.mark.parametrize("enum", [RecordType, Gate, Cost])
def test_enum_values_equal_their_lowercase_names(enum: Any) -> None:
    for member in enum:
        assert member.value == member.name.lower()


def test_record_type_members() -> None:
    assert [m.value for m in RecordType] == [
        "grader",
        "metric",
        "statistic",
        "diagnostic",
        "procedure",
        "constraint",
    ]


def test_gate_and_cost_members() -> None:
    assert [m.value for m in Gate] == ["absolute", "statistical", "false"]
    assert [m.value for m in Cost] == ["low", "medium", "high"]


def test_gate_false_is_truthy_so_it_must_be_compared_by_identity() -> None:
    """The trap the Gate docstring warns about: 'false' is a non-empty string."""
    assert bool(Gate.false) is True
    assert _record(gates=Gate.false).gates is Gate.false


def test_record_type_docstring_states_the_assignment_rule() -> None:
    """EL-110 onward reads this instead of guessing."""
    doc = " ".join((RecordType.__doc__ or "").split())  # the text, not its line breaks
    assert "Most records are not graders" in doc
    assert "Wilson, McNemar and bootstrap are statistics" in doc
    assert "Section E is almost entirely diagnostics" in doc


# --------------------------------------------------------------------------
# Shape: the 22 fields, frozen, tuples, immutable mapping
# --------------------------------------------------------------------------


def test_has_exactly_the_twenty_two_fields_of_claude_md_section_6() -> None:
    assert FIELD_NAMES == EXPECTED_FIELDS
    assert len(FIELD_NAMES) == 22


def test_every_field_is_required_so_a_missing_one_cannot_default_silently() -> None:
    for field in dataclasses.fields(TechniqueRecord):
        assert field.default is dataclasses.MISSING, field.name
        assert field.default_factory is dataclasses.MISSING, field.name


def test_record_is_frozen() -> None:
    record = _record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.id = "B4_other"  # type: ignore[misc]


def test_requires_is_read_only() -> None:
    record = _record(requires={"discordant_pairs": 25})
    with pytest.raises(TypeError):
        record.requires["discordant_pairs"] = 1  # type: ignore[index]


def test_requires_does_not_alias_the_callers_dict() -> None:
    """The subtle half of immutability: a frozen record holding a live dict."""
    source = {"discordant_pairs": 25}
    record = _record(requires=source)
    source["discordant_pairs"] = 1
    source["injected"] = 99
    assert dict(record.requires) == {"discordant_pairs": 25}


def test_requires_accepts_the_corpus_float_thresholds() -> None:
    """kappa >= 0.6 and alpha < 0.667 are verbatim corpus figures."""
    record = _record(requires={"kappa_manual": 0.6, "krippendorff_alpha": 0.667})
    assert record.requires["kappa_manual"] == 0.6


def test_requires_accepts_a_boolean_requirement() -> None:
    record = _record(requires={"requires_pre_instrumentation": True})
    assert record.requires["requires_pre_instrumentation"] is True


def test_empty_requires_is_allowed_and_means_fires_at_n_equals_1() -> None:
    assert dict(_record(requires={}).requires) == {}


def test_record_is_not_hashable_and_that_is_documented() -> None:
    """Consequence of the read-only mapping; no consumer in M0 hashes a record."""
    with pytest.raises(TypeError):
        hash(_record())


# --------------------------------------------------------------------------
# Rule 1 - triggers_on_situation must be non-empty
# --------------------------------------------------------------------------


def test_triggers_populated_is_accepted() -> None:
    record = _record(triggers_on_situation=(Situation.two_candidates, Situation.many_candidates))
    assert record.triggers_on_situation[0] is Situation.two_candidates


def test_empty_triggers_is_rejected() -> None:
    with pytest.raises(SchemaError) as caught:
        _record(triggers_on_situation=())
    assert caught.value.record_id == "B3_mcnemar"
    assert caught.value.field == "triggers_on_situation"
    assert "B3_mcnemar" in str(caught.value) and "triggers_on_situation" in str(caught.value)


# --------------------------------------------------------------------------
# Rule 2 - ladder_priority only on a grader
# --------------------------------------------------------------------------


def test_grader_with_a_rung_is_accepted() -> None:
    record = _record(id="A1_execution_based", type=RecordType.grader, ladder_priority=1)
    assert record.ladder_priority == 1


def test_non_grader_with_a_rung_is_rejected() -> None:
    with pytest.raises(SchemaError) as caught:
        _record(ladder_priority=3)
    assert caught.value.field == "ladder_priority"
    assert "statistic" in str(caught.value), "the message should name the offending type"


def test_grader_may_leave_the_rung_none_for_a7() -> None:
    """A7 wraps the ladder rather than ranking in it; CLAUDE.md leaves it open."""
    record = _record(id="A7_tiered_online_scoring", type=RecordType.grader, ladder_priority=None)
    assert record.ladder_priority is None


# --------------------------------------------------------------------------
# Rule 3 - ladder_priority within 1..5 (five, per EL-004)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rung", [1, 2, 3, 4, 5])
def test_every_real_rung_is_accepted(rung: int) -> None:
    record = _record(id="A1_execution_based", type=RecordType.grader, ladder_priority=rung)
    assert record.ladder_priority == rung


@pytest.mark.parametrize("rung", [0, 6, -1, 99])
def test_rung_outside_one_to_five_is_rejected(rung: int) -> None:
    with pytest.raises(SchemaError) as caught:
        _record(id="A1_execution_based", type=RecordType.grader, ladder_priority=rung)
    assert caught.value.field == "ladder_priority"
    assert "1-5" in str(caught.value)


def test_rung_six_is_rejected_because_el_004_removed_the_distilled_rung() -> None:
    with pytest.raises(SchemaError) as caught:
        _record(id="A1_execution_based", type=RecordType.grader, ladder_priority=6)
    assert "distilled" in str(caught.value)


# --------------------------------------------------------------------------
# Rule 4 - id shape
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "record_id",
    ["A1_execution_based", "B3_mcnemar", "C4_wilson_clopper_pearson", "H3_pass_k", "D2_f0_5"],
)
def test_well_formed_ids_are_accepted(record_id: str) -> None:
    assert _record(id=record_id).id == record_id


@pytest.mark.parametrize(
    "record_id",
    [
        "A1execution",          # no underscore
        "a1_execution_based",   # lower-case section
        "K1_something",         # section outside A-J
        "A0_zero",              # rung numbering starts at 1
        "A1_Execution_Based",   # not snake_case
        "A1_",                  # empty name
        "1_execution",          # no section letter
        "",                     # empty
        "A1_execution-based",   # hyphen, not underscore
    ],
)
def test_malformed_ids_are_rejected(record_id: str) -> None:
    with pytest.raises(SchemaError) as caught:
        _record(id=record_id)
    assert caught.value.field == "id"
    assert "A1_execution_based" in str(caught.value), "the message should show the shape"


# --------------------------------------------------------------------------
# Rule 5 - worked_example must contain a digit
# --------------------------------------------------------------------------


def test_worked_example_with_figures_is_accepted() -> None:
    record = _record(worked_example="200 items: exact-match 41%, execution-match 68%")
    assert "41%" in record.worked_example


def test_worked_example_without_a_digit_is_rejected() -> None:
    with pytest.raises(SchemaError) as caught:
        _record(worked_example="the new model was clearly better")
    assert caught.value.field == "worked_example"
    assert caught.value.record_id == "B3_mcnemar"


# --------------------------------------------------------------------------
# Rule 6 - source_ref must be non-empty
# --------------------------------------------------------------------------


def test_source_ref_present_is_accepted() -> None:
    assert _record(source_ref="B-comparing-two-things.md, B3").source_ref.startswith("B-")


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_empty_source_ref_is_rejected(value: str) -> None:
    with pytest.raises(SchemaError) as caught:
        _record(source_ref=value)
    assert caught.value.field == "source_ref"


# --------------------------------------------------------------------------
# The seventh check, from the ticket's "tuple fields (not list)" requirement
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "triggers_on_situation",
        "required_signals",
        "required_tools",
        "produces",
        "companion_checks",
        "unlocks",
        "conflicts_with",
    ],
)
def test_a_list_where_a_tuple_belongs_is_rejected(field: str) -> None:
    """The loader parses flow lists into lists; a record must not keep one."""
    value = [Situation.two_candidates] if field == "triggers_on_situation" else ["x"]
    if field == "required_tools":
        value = [Tool.sandbox]
    with pytest.raises(SchemaError) as caught:
        _record(**{field: value})
    assert caught.value.field == field
    assert "tuple" in str(caught.value)


def test_a_bare_string_where_a_tuple_belongs_is_rejected() -> None:
    """Coercion would silently explode this into one entry per character."""
    with pytest.raises(SchemaError):
        _record(produces="chi_square")


# --------------------------------------------------------------------------
# All rules together
# --------------------------------------------------------------------------


def test_the_valid_record_is_valid() -> None:
    record = _record()
    assert record.id == "B3_mcnemar"
    assert record.type is RecordType.statistic
    assert record.gates is Gate.statistical
    assert record.analysis_cost is Cost.low
    assert record.triggers_on_situation == (Situation.two_candidates,)


def test_schema_error_is_a_value_error_so_the_loader_can_aggregate() -> None:
    with pytest.raises(ValueError):
        _record(source_ref="")
