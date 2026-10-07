"""The loader's one promise: every problem in every file, in one message.

``CLAUDE.md`` section 7.7 is the reason -- 73 hand-authored records, and a
loader that stops at the first bad file turns one authoring session into 73
round trips. So the central test here is not "a bad record raises"; it is that
a directory holding thirteen distinct problems across four files, at four
different layers (parse, top-level key, field shape, schema), reports all
thirteen and reports each exactly once.

``tests/fixtures/registry/`` holds both halves. The records in ``good/`` carry
real corpus content and real figures; the ones in ``broken/`` are malformed on
purpose and are never expected to load. Per ``CLAUDE.md`` section 7.4, neither
tree is edited to make a test pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import BROKEN_RECORDS_DIR

from evalloop.registry.loader import (
    BODY_FIELDS,
    RECORD_SUFFIX,
    Problem,
    RegistryError,
    load_records,
)
from evalloop.registry.schema import FIELD_NAMES, Cost, Gate, RecordType
from evalloop.vocab import Situation, Tool

#: Every problem the ``broken/`` tree must produce: the file, the record id
#: (``None`` for a file-level problem) and a fragment that identifies it. One
#: row per defect, written from the fixtures rather than from a run.
EXPECTED_PROBLEMS: tuple[tuple[str, str | None, str], ...] = (
    ("A_grading.yaml", "A1_execution_based", "must not carry an 'id' field"),
    ("A_grading.yaml", "A1_execution_based", "unknown field 'ladder_rung'"),
    ("A_grading.yaml", "A1_execution_based", "gates: missing"),
    ("A_grading.yaml", "A1_execution_based", "unknown situation 'sql_gen'"),
    ("A_grading.yaml", "A1_execution_based", "unknown tool 'sandbox_runner'"),
    ("B_comparison.yaml", "B1_paired_evaluation", "worked_example: contains no digit"),
    ("B_comparison.yaml", "B3_mcnemar", "unknown record type 'test'"),
    ("B_comparison.yaml", "B3_mcnemar", "threshold 'discordant_pairs' must be a number"),
    ("B_comparison.yaml", "B3_mcnemar", "produces: must be a flow list"),
    ("B_comparison.yaml", "B3_mcnemar", "unknown cost 'cheap'"),
    ("C_statistics.yaml", None, "block sequences are outside the subset"),
    ("D_rare_events.yaml", "notes", "is not a record id"),
    ("D_rare_events.yaml", "D1_recall_not_accuracy", "must be an indented block of fields"),
)

#: A valid B3 McNemar body, as on-disk text, one field per entry. Figures are
#: the master lookup's section B row. Tests override one entry at a time, so
#: each is about one rule.
VALID_BODY: dict[str, str] = {
    "section": "B",
    "name": "McNemar's test",
    "type": "statistic",
    "triggers_on_situation": "[two_candidates]",
    "required_signals": "['paired binary outcomes on the same items']",
    "required_tools": "[]",
    "ladder_priority": "null",
    "requires": "{discordant_pairs: 25}",
    "produces": "[chi_square, p_value]",
    "gates": "statistical",
    "companion_checks": "[]",
    "unlocks": "[]",
    "conflicts_with": "[]",
    "analysis_cost": "low",
    "capture_cost": "null",
    "anti_pattern": "A two-proportion z-test assumes independent samples",
    "worked_example": "'500 claims: b = 40, c = 65, chi-square = 5.49, p = 0.019'",
    "domain_scenario": "null",
    "rule_of_thumb": "null",
    "source_ref": "master lookup § B",
    "extraction_notes": "null",
}


def _write_record(
    directory: Path,
    record_id: str = "B3_mcnemar",
    drop: tuple[str, ...] = (),
    **overrides: str,
) -> Path:
    """Write one record file into ``directory`` and return the directory."""
    body = {name: text for name, text in VALID_BODY.items() if name not in drop}
    body.update(overrides)
    lines = [f"{record_id}:", *(f"  {name}: {text}" for name, text in body.items())]
    (directory / f"B_comparison{RECORD_SUFFIX}").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return directory


def _problems(directory: Path) -> tuple[Problem, ...]:
    """The problems from a load that must fail."""
    with pytest.raises(RegistryError) as raised:
        load_records(directory)
    return raised.value.problems


def _details(directory: Path) -> str:
    return "\n".join(problem.detail for problem in _problems(directory))


# -- the body field list ---------------------------------------------------


def test_body_fields_are_the_schema_fields_minus_id() -> None:
    """Derived, not re-typed: the loader and the schema cannot drift apart."""
    assert BODY_FIELDS == tuple(name for name in FIELD_NAMES if name != "id")
    assert len(BODY_FIELDS) == 21
    assert "id" not in BODY_FIELDS


# -- the happy path --------------------------------------------------------


def test_records_come_back_sorted_by_id(good_records_dir: Path) -> None:
    """A_grading.yaml declares A2 before A1, so file order cannot explain this."""
    records = load_records(good_records_dir)
    ids = tuple(record.id for record in records)
    assert ids == ("A1_execution_based", "A2_end_state_verification", "B3_mcnemar")
    assert ids == tuple(sorted(ids))


def test_the_id_is_the_top_level_key(good_records_dir: Path) -> None:
    by_id = {record.id: record for record in load_records(good_records_dir)}
    assert by_id["A1_execution_based"].section == "A"
    assert by_id["A1_execution_based"].name == "Execution-based grading"


def test_loading_twice_gives_the_same_records(good_records_dir: Path) -> None:
    assert load_records(good_records_dir) == load_records(good_records_dir)


def test_result_does_not_depend_on_directory_order(
    good_records_dir: Path, tmp_path: Path
) -> None:
    """The same records in files named to reverse the order load identically.

    No filesystem guarantees directory order, so the sort is the only thing
    making the result reproducible on another machine.
    """
    expected = load_records(good_records_dir)
    reversed_names = {"A_grading.yaml": "Z_last.yaml", "B_comparison.yaml": "A_first.yaml"}
    for original, renamed in reversed_names.items():
        (tmp_path / renamed).write_text(
            (good_records_dir / original).read_text(encoding="utf-8"), encoding="utf-8"
        )
    assert load_records(tmp_path) == expected


def test_vocabulary_strings_become_enum_members(good_records_dir: Path) -> None:
    """The whole point of the vocab parsers: no bare strings reach the planner."""
    by_id = {record.id: record for record in load_records(good_records_dir)}
    a1 = by_id["A1_execution_based"]
    assert a1.triggers_on_situation == (
        Situation.code_generation,
        Situation.sql_generation,
        Situation.api_endpoint,
    )
    assert a1.required_tools == (Tool.sandbox, Tool.test_runner)
    assert all(isinstance(member, Situation) for member in a1.triggers_on_situation)
    assert all(isinstance(member, Tool) for member in a1.required_tools)


def test_enum_fields_and_optionals_round_trip(good_records_dir: Path) -> None:
    by_id = {record.id: record for record in load_records(good_records_dir)}
    a1, b3 = by_id["A1_execution_based"], by_id["B3_mcnemar"]
    assert a1.type is RecordType.grader
    assert a1.gates is Gate.absolute
    assert a1.analysis_cost is Cost.low
    assert a1.capture_cost is Cost.medium
    assert a1.ladder_priority == 1
    assert b3.type is RecordType.statistic
    assert b3.ladder_priority is None
    assert b3.capture_cost is None
    assert b3.rule_of_thumb == "b + c < 25 -> exact binomial instead"
    assert dict(b3.requires) == {"discordant_pairs": 25}


def test_a_bare_false_is_the_false_gate(good_records_dir: Path) -> None:
    """``gates: false`` is read by YAML as the boolean, and means ``Gate.false``.

    The one place the on-disk format and an enum member disagree, so it is
    pinned here rather than left to whoever next writes ``gates: false``.
    """
    by_id = {record.id: record for record in load_records(good_records_dir)}
    assert by_id["B3_mcnemar"].gates is Gate.false


def test_verbatim_prose_survives_the_round_trip(good_records_dir: Path) -> None:
    """``domain_scenario`` keeps its ``**<Domain>**:`` prefix (EL-011)."""
    by_id = {record.id: record for record in load_records(good_records_dir)}
    scenario = by_id["A1_execution_based"].domain_scenario
    assert scenario is not None
    assert scenario.startswith("**Fintech**: ")
    assert '"total refunds above ₹5,000 in Q2"' in scenario


# -- aggregation, the reason this module exists ----------------------------


def test_every_problem_in_every_file_is_reported_exactly_once(
    broken_records_dir: Path,
) -> None:
    """Thirteen defects, four files, four layers, one message.

    Matched both ways: every expected problem is found, and every reported
    problem was expected -- so the test fails on a swallowed problem and on a
    spurious one alike.
    """
    problems = _problems(broken_records_dir)
    unmatched = list(problems)
    for file, record_id, fragment in EXPECTED_PROBLEMS:
        hits = [
            problem
            for problem in unmatched
            if problem.file == file
            and problem.record_id == record_id
            and fragment in problem.detail
        ]
        assert hits, f"not reported: {file} / {record_id} / {fragment!r}"
        assert len(hits) == 1, f"reported {len(hits)}×: {file} / {record_id} / {fragment!r}"
        unmatched.remove(hits[0])
    assert not unmatched, f"unexpected problems: {[str(problem) for problem in unmatched]}"
    assert len(problems) == len(EXPECTED_PROBLEMS)


def test_the_message_carries_every_problem(broken_records_dir: Path) -> None:
    """The rendered message is the list, because that is what a human reads."""
    with pytest.raises(RegistryError) as raised:
        load_records(broken_records_dir)
    message = str(raised.value)
    assert message.startswith(f"{len(EXPECTED_PROBLEMS)} problems loading records from ")
    for problem in raised.value.problems:
        assert str(problem) in message


def test_every_problem_names_a_file_and_the_specific_problem(
    broken_records_dir: Path,
) -> None:
    for problem in _problems(broken_records_dir):
        assert problem.file.endswith(RECORD_SUFFIX)
        assert problem.detail.strip()
        assert str(problem).startswith(problem.file)


def test_a_parse_error_in_one_file_does_not_hide_the_other_files(
    broken_records_dir: Path,
) -> None:
    """C_statistics.yaml is unparseable; A, B and D must still be reported."""
    problems = _problems(broken_records_dir)
    files = {problem.file for problem in problems}
    assert files == {
        "A_grading.yaml",
        "B_comparison.yaml",
        "C_statistics.yaml",
        "D_rare_events.yaml",
    }
    parse_errors = [problem for problem in problems if problem.file == "C_statistics.yaml"]
    assert len(parse_errors) == 1
    assert parse_errors[0].record_id is None, "a parse error belongs to the file, not a record"
    assert parse_errors[0].line == 12, "the format parser's line number is kept"
    assert str(parse_errors[0]).startswith("C_statistics.yaml:12: ")


def test_problem_order_is_stable(broken_records_dir: Path) -> None:
    """File-name order, then document order, then schema field order."""
    assert _problems(broken_records_dir) == _problems(broken_records_dir)
    files = [problem.file for problem in _problems(broken_records_dir)]
    assert files == sorted(files)


def test_several_problems_in_one_record_are_all_reported(tmp_path: Path) -> None:
    """Within a record, every field is checked before anything is reported."""
    details = _details(
        _write_record(
            tmp_path,
            drop=("gates", "source_ref"),
            type="judge",
            triggers_on_situation="[two_models]",
            required_tools="[llm]",
            analysis_cost="cheap",
        )
    )
    for fragment in (
        "gates: missing",
        "source_ref: missing",
        "unknown record type 'judge'",
        "unknown situation 'two_models'",
        "unknown tool 'llm'",
        "unknown cost 'cheap'",
    ):
        assert fragment in details


# -- the vocab messages, surfaced rather than re-worded --------------------


def test_unknown_situation_names_the_value_and_the_valid_options(tmp_path: Path) -> None:
    problems = _problems(_write_record(tmp_path, triggers_on_situation="[two_models]"))
    assert len(problems) == 1
    problem = problems[0]
    assert problem.file == f"B_comparison{RECORD_SUFFIX}"
    assert problem.record_id == "B3_mcnemar"
    assert problem.detail.startswith("triggers_on_situation: unknown situation 'two_models'.")
    assert f"The {len(Situation)} valid situation values are:" in problem.detail
    assert "two_candidates" in problem.detail
    assert "many_candidates" in problem.detail


def test_unknown_tool_names_the_value_and_the_valid_options(tmp_path: Path) -> None:
    problems = _problems(_write_record(tmp_path, required_tools="[llm_api_v2]"))
    assert len(problems) == 1
    problem = problems[0]
    assert problem.record_id == "B3_mcnemar"
    assert problem.detail.startswith("required_tools: unknown tool 'llm_api_v2'.")
    assert f"The {len(Tool)} valid tool values are:" in problem.detail
    assert "llm_api" in problem.detail
    assert "llm_api_cross_family" in problem.detail


def test_the_bad_situation_is_named_even_among_good_ones(tmp_path: Path) -> None:
    details = _details(
        _write_record(tmp_path, triggers_on_situation="[two_candidates, many_models]")
    )
    assert "unknown situation 'many_models'" in details
    assert "'two_candidates'" not in details


# -- field shape -----------------------------------------------------------


def test_a_missing_field_names_the_field(tmp_path: Path) -> None:
    assert "gates: missing; every field is required" in _details(
        _write_record(tmp_path, drop=("gates",))
    )


def test_an_unknown_field_is_rejected_rather_than_ignored(tmp_path: Path) -> None:
    assert "unknown field 'ladder_rung'" in _details(_write_record(tmp_path, ladder_rung="2"))


def test_a_body_may_not_repeat_its_id(tmp_path: Path) -> None:
    assert "must not carry an 'id' field" in _details(_write_record(tmp_path, id="B3_mcnemar"))


def test_a_top_level_key_that_is_not_a_record_id_is_rejected(tmp_path: Path) -> None:
    assert "is not a record id" in _details(_write_record(tmp_path, record_id="mcnemar"))


def test_a_boolean_is_not_a_ladder_priority(tmp_path: Path) -> None:
    """``bool`` is an ``int`` in Python; ``ladder_priority: true`` is not a rung."""
    assert "must be a whole number or null, not the boolean true" in _details(
        _write_record(tmp_path, ladder_priority="true")
    )


def test_true_is_not_a_gate(tmp_path: Path) -> None:
    detail = _details(_write_record(tmp_path, gates="true"))
    assert "'true' is not a gate" in detail
    assert "absolute, statistical or false" in detail


def test_text_where_a_list_belongs(tmp_path: Path) -> None:
    assert "produces: must be a flow list" in _details(
        _write_record(tmp_path, produces="chi_square")
    )


def test_a_non_text_list_item_names_its_position(tmp_path: Path) -> None:
    assert "required_signals: item 1 must be text, not the number 25" in _details(
        _write_record(tmp_path, required_signals="['paired outcomes', 25]")
    )


def test_a_number_where_prose_belongs(tmp_path: Path) -> None:
    assert "name: must be text, not the number 7" in _details(_write_record(tmp_path, name="7"))


def test_requires_must_be_a_map(tmp_path: Path) -> None:
    assert "requires: must be a flow map of thresholds" in _details(
        _write_record(tmp_path, requires="25")
    )


def test_a_threshold_must_be_a_number_or_a_boolean(tmp_path: Path) -> None:
    detail = _details(_write_record(tmp_path, requires="{discordant_pairs: twenty-five}"))
    assert "threshold 'discordant_pairs' must be a number or a boolean" in detail
    assert "never a guess" in detail


def test_a_float_threshold_is_accepted(tmp_path: Path) -> None:
    """The corpus has κ ≥ 0.6 verbatim; rounding it to 60 is an invented number."""
    _write_record(tmp_path, requires="{kappa: 0.6, pre_instrumented: true}")
    records = load_records(tmp_path)
    assert dict(records[0].requires) == {"kappa": 0.6, "pre_instrumented": True}


def test_optional_fields_accept_null(tmp_path: Path) -> None:
    _write_record(tmp_path, domain_scenario="null", rule_of_thumb="null", extraction_notes="null")
    record = load_records(tmp_path)[0]
    assert record.domain_scenario is None
    assert record.rule_of_thumb is None
    assert record.extraction_notes is None


def test_a_record_body_must_be_a_field_block(tmp_path: Path) -> None:
    (tmp_path / f"B_comparison{RECORD_SUFFIX}").write_text(
        "B3_mcnemar: see the deep dive\n", encoding="utf-8"
    )
    assert "must be an indented block of fields, not text" in _details(tmp_path)


# -- schema violations reach the same list --------------------------------


def test_a_schema_violation_is_reported_as_a_problem(tmp_path: Path) -> None:
    """A shape-clean record that breaks a schema rule still comes back as a line."""
    problems = _problems(_write_record(tmp_path, worked_example="no figures here"))
    assert len(problems) == 1
    assert problems[0].record_id == "B3_mcnemar"
    assert problems[0].detail.startswith("worked_example: contains no digit")


def test_an_empty_trigger_list_is_a_schema_violation(tmp_path: Path) -> None:
    assert "triggers_on_situation: is empty" in _details(
        _write_record(tmp_path, triggers_on_situation="[]")
    )


def test_a_ladder_priority_on_a_non_grader_is_a_schema_violation(tmp_path: Path) -> None:
    assert "only a grader has a rung on the ladder" in _details(
        _write_record(tmp_path, ladder_priority="2")
    )


# -- the directory itself --------------------------------------------------


def test_a_missing_directory_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "records"
    problems = _problems(missing)
    assert len(problems) == 1
    assert problems[0].file == str(missing)
    assert "is not a directory" in problems[0].detail


def test_a_directory_with_no_record_files_is_an_error(tmp_path: Path) -> None:
    """Loading zero records silently is the failure CLAUDE.md section 4 warns of."""
    (tmp_path / "README.md").write_text("notes, not records\n", encoding="utf-8")
    problems = _problems(tmp_path)
    assert len(problems) == 1
    assert f"holds no {RECORD_SUFFIX} record file" in problems[0].detail


def test_a_file_holding_only_comments_is_reported(tmp_path: Path) -> None:
    """A half-authored section file must not pass as zero records."""
    (tmp_path / f"C_statistics{RECORD_SUFFIX}").write_text(
        "# section C, not written yet\n", encoding="utf-8"
    )
    problems = _problems(tmp_path)
    assert len(problems) == 1
    assert problems[0].file == f"C_statistics{RECORD_SUFFIX}"
    assert problems[0].record_id is None
    assert "empty document" in problems[0].detail


def test_a_string_path_is_accepted(good_records_dir: Path) -> None:
    assert load_records(str(good_records_dir)) == load_records(good_records_dir)


def test_the_fixture_tree_is_the_declared_one(broken_records_dir: Path) -> None:
    """conftest owns the path; this test owns the expectation about its content."""
    assert broken_records_dir == BROKEN_RECORDS_DIR
    assert sorted(path.name for path in broken_records_dir.glob(f"*{RECORD_SUFFIX}")) == [
        "A_grading.yaml",
        "B_comparison.yaml",
        "C_statistics.yaml",
        "D_rare_events.yaml",
    ]
