"""One test per supported construct, one rejection test per unsupported one.

The parser serves two consumers that do not exist yet -- the 73 record files
(EL-110 onward) and the 20 planner fixtures (EL-118/EL-119) -- so the contract
has to be pinned here, before either is authored. ``test_fixture_sample_from_tasks_md``
is the load-bearing one: it parses the sample in ``TASKS.md`` group 6 verbatim,
which is the format the fixtures are specified in.

Rejection tests assert on ``FormatError.construct`` and ``.line`` rather than on
message prose, so the wording can improve without breaking the suite. The
messages themselves are read while hand-authoring 73 records, so
``test_messages_name_the_line_and_the_fix`` checks they stay useful.
"""

import pytest

from evalloop.registry.format import FormatError, load

# --------------------------------------------------------------------------
# Supported constructs
# --------------------------------------------------------------------------


def test_block_map_one_level() -> None:
    assert load("name: summarization_first_run\nid: A1_execution_based\n") == {
        "name": "summarization_first_run",
        "id": "A1_execution_based",
    }


def test_block_map_two_levels() -> None:
    assert load("given:\n  samples: 1\n") == {"given": {"samples": 1}}


def test_block_map_three_levels() -> None:
    """``expect.pending.B3_mcnemar`` -- the depth the fixtures need."""
    text = "expect:\n  pending:\n    B3_mcnemar: 8\n"
    assert load(text) == {"expect": {"pending": {"B3_mcnemar": 8}}}


def test_any_consistent_indent_width() -> None:
    assert load("a:\n    b:\n        c: 1\n") == {"a": {"b": {"c": 1}}}


def test_flow_list() -> None:
    assert load("situations: [summarization]\n") == {"situations": ["summarization"]}
    assert load("tools: [source_doc_read, llm_api_cross_family]\n") == {
        "tools": ["source_doc_read", "llm_api_cross_family"]
    }


def test_empty_flow_list() -> None:
    assert load("unavailable: []\n") == {"unavailable": []}


def test_flow_list_items_may_contain_commas_and_colons_when_quoted() -> None:
    loaded = load('reasons: ["needs paired_runs: 2, have 1", "ok"]\n')
    assert loaded == {"reasons": ["needs paired_runs: 2, have 1", "ok"]}


def test_flow_map() -> None:
    assert load("evidence: {samples: 1, runs: 1}\n") == {"evidence": {"samples": 1, "runs": 1}}


def test_empty_flow_map() -> None:
    assert load("requires: {}\n") == {"requires": {}}


def test_flow_map_values_may_be_bools_and_floats() -> None:
    loaded = load("requires: {requires_pre_instrumentation: true, kappa_manual: 0.6}\n")
    assert loaded == {"requires": {"requires_pre_instrumentation": True, "kappa_manual": 0.6}}


def test_trailing_comment() -> None:
    assert load("ready: [A1, A3]   # order matters\n") == {"ready": ["A1", "A3"]}
    assert load("section: A  # grading ladder\n") == {"section": "A"}


def test_whole_line_comments_and_blank_lines() -> None:
    text = "# a record\n\nid: A1_execution_based\n\n# the section\nsection: A\n"
    assert load(text) == {"id": "A1_execution_based", "section": "A"}


def test_hash_inside_a_quoted_string_is_not_a_comment() -> None:
    assert load('note: "uses # as a literal"\n') == {"note": "uses # as a literal"}


def test_double_quoted_string_containing_a_colon_space() -> None:
    assert load('pending: "needs paired_runs: 2, have 1"\n') == {
        "pending": "needs paired_runs: 2, have 1"
    }


def test_double_quoted_escapes() -> None:
    assert load(r'note: "said \"done\" \\ a\nb\tc"' + "\n") == {
        "note": 'said "done" \\ a\nb\tc'
    }


def test_single_quoted_string_doubles_its_quote() -> None:
    assert load("note: 'it''s fine: really'\n") == {"note": "it's fine: really"}


def test_scalars() -> None:
    text = (
        "ladder_priority: 1\n"
        "negative: -3\n"
        "kappa: 0.6\n"
        "gates: true\n"
        "absolute: false\n"
        "capture_cost: null\n"
        "name: Execution-based grading\n"
    )
    assert load(text) == {
        "ladder_priority": 1,
        "negative": -3,
        "kappa": 0.6,
        "gates": True,
        "absolute": False,
        "capture_cost": None,
        "name": "Execution-based grading",
    }


def test_plain_string_may_start_with_a_digit_when_it_is_not_one_word() -> None:
    """``worked_example`` prose routinely starts with a figure."""
    assert load("worked_example: 150 servicing tasks\n") == {
        "worked_example": "150 servicing tasks"
    }


def test_plain_scalar_may_contain_an_apostrophe() -> None:
    """Corpus prose is full of them: "doesn't", "someone else's leaderboard"."""
    assert load("name: McNemar's test\n") == {"name": "McNemar's test"}
    assert load("why: the judge doesn't see it  # note\n") == {"why": "the judge doesn't see it"}


def test_plain_scalar_may_contain_a_double_quote_after_the_first_character() -> None:
    text = 'anti_pattern: agents say "Done" when nothing changed\n'
    assert load(text) == {"anti_pattern": 'agents say "Done" when nothing changed'}


def test_real_corpus_row_as_a_record_would_write_it() -> None:
    """A1's three prose cells, verbatim from the master lookup, incl. a colon and a quote."""
    text = (
        "anti_pattern: >-\n"
        "  String match marks correct-but-different SQL (reordered JOINs, aliases) as\n"
        "  wrong and near-identical wrong SQL as right\n"
        "worked_example: >-\n"
        "  200 text-to-SQL items: exact-match 41%, execution-match 68%. The 27-pt gap\n"
        "  was all equivalent rewrites\n"
        "domain_scenario: >-\n"
        '  **Fintech**: NL-to-SQL over a UPI transaction warehouse. For "total refunds\n'
        '  above \u20b95,000 in Q2", compare result sets on a frozen snapshot\n'
    )
    loaded = load(text)
    assert loaded["worked_example"] == (
        "200 text-to-SQL items: exact-match 41%, execution-match 68%. "
        "The 27-pt gap was all equivalent rewrites"
    )
    assert str(loaded["domain_scenario"]).startswith("**Fintech**: NL-to-SQL")
    assert "\u20b95,000" in str(loaded["domain_scenario"])


def test_block_scalar_literal_keeps_newlines_and_clips_to_one() -> None:
    assert load("anti_pattern: |\n  first\n  second\n") == {"anti_pattern": "first\nsecond\n"}


def test_block_scalar_folded_joins_lines_with_spaces() -> None:
    assert load("anti_pattern: >\n  first\n  second\n") == {"anti_pattern": "first second\n"}


def test_block_scalar_strip_chomping_drops_the_trailing_newline() -> None:
    assert load("a: |-\n  first\n  second\n") == {"a": "first\nsecond"}
    assert load("a: >-\n  first\n  second\n") == {"a": "first second"}


def test_block_scalar_blank_line_is_a_paragraph_break_when_folded() -> None:
    assert load("a: >-\n  first\n\n  second\n") == {"a": "first\nsecond"}
    assert load("a: |-\n  first\n\n  second\n") == {"a": "first\n\nsecond"}


def test_block_scalar_followed_by_a_sibling_key() -> None:
    text = "anti_pattern: >-\n  a bare percentage\n  invites a decision on noise\nsection: C\n"
    assert load(text) == {
        "anti_pattern": "a bare percentage invites a decision on noise",
        "section": "C",
    }


def test_load_is_pure_and_deterministic() -> None:
    text = "b: 2\na: 1\nc: {z: 1, a: 2}\n"
    first, second = load(text), load(text)
    assert first == second
    assert first is not second
    assert list(first) == ["b", "a", "c"], "key order must follow the file"
    assert list(first["c"]) == ["z", "a"]  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The two real consumers
# --------------------------------------------------------------------------

FIXTURE_SAMPLE = """\
name: summarization_first_run
given:
  situations: [summarization]
  available_tools: [source_doc_read, llm_api_cross_family]
  evidence: {samples: 1, runs: 1}
expect:
  ready: [G3_faithfulness, E3_length_bias]   # order matters
  pending:
    B3_mcnemar: "needs paired_runs: 2, have 1"
  unavailable: []
  companions:
    G3_faithfulness: [E3_length_bias]
  prohibited: []
"""


def test_fixture_sample_from_tasks_md() -> None:
    """The TASKS.md group 6 sample, verbatim. EL-118 writes 5 of these, EL-119 the rest."""
    assert load(FIXTURE_SAMPLE) == {
        "name": "summarization_first_run",
        "given": {
            "situations": ["summarization"],
            "available_tools": ["source_doc_read", "llm_api_cross_family"],
            "evidence": {"samples": 1, "runs": 1},
        },
        "expect": {
            "ready": ["G3_faithfulness", "E3_length_bias"],
            "pending": {"B3_mcnemar": "needs paired_runs: 2, have 1"},
            "unavailable": [],
            "companions": {"G3_faithfulness": ["E3_length_bias"]},
            "prohibited": [],
        },
    }


RECORD_SHAPE = """\
id: B3_mcnemar
section: B
name: McNemar's test
type: statistic
triggers_on_situation: [two_candidates]
required_signals: [paired binary outcomes on the same items]
required_tools: []
ladder_priority: null
requires: {discordant_pairs: 25}
produces: [chi_square, p_value]
gates: statistical
companion_checks: [C1_wilson_ci]
unlocks: []
conflicts_with: []
analysis_cost: low
capture_cost: null
anti_pattern: >-
  A two-proportion z-test assumes independent samples. Reusing the same items
  breaks that and gives the wrong p-value.
worked_example: >-
  500 claims: b = 40, c = 65. chi-square = 5.49, p = 0.019.
domain_scenario: "**Insurance**: old vs new fraud-flag classifier on the same 500 motor claims"
rule_of_thumb: "b + c < 25 -> exact binomial instead"
source_ref: "master lookup, section B"
extraction_notes: null
"""


def test_record_shaped_document_covers_every_field_type() -> None:
    loaded = load(RECORD_SHAPE)
    assert len(loaded) == 22, "CLAUDE.md section 6 defines 22 fields"
    assert loaded["triggers_on_situation"] == ["two_candidates"]
    assert loaded["requires"] == {"discordant_pairs": 25}
    assert loaded["ladder_priority"] is None
    assert loaded["required_tools"] == []
    assert loaded["worked_example"] == (
        "500 claims: b = 40, c = 65. chi-square = 5.49, p = 0.019."
    ), "a block scalar is how prose containing ': ' is written"
    assert "\n" not in str(loaded["anti_pattern"]), ">- keeps render() on one line"


# --------------------------------------------------------------------------
# Rejected constructs: one test each, asserting construct and line
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "construct", "line"),
    [
        ("tools:\n  - sandbox\n", "block sequence", 2),
        ("a: 1\n\tb: 2\n", "tab", 2),
        ("base: &anchor\n  a: 1\n", "anchor or alias", 1),
        ("a: 1\n*alias\n", "anchor or alias", 2),
        ("a: 1\n<<: other\n", "merge key", 2),
        ("---\na: 1\n", "document marker", 1),
        ("a: [[1], [2]]\n", "flow list", 1),
        ("a: {k: [1]}\n", "flow map", 1),
        ("a: plain text: with a colon\n", "ambiguous scalar", 1),
        ("a: yes\n", "ambiguous scalar", 1),
        ("a: no\n", "ambiguous scalar", 1),
        ("a: 'on'\n", None, None),  # quoting it is the documented fix
        ("a: True\n", "ambiguous scalar", 1),
        ("a: NULL\n", "ambiguous scalar", 1),
        ("a: ~\n", "ambiguous scalar", 1),
        ("a: 0x10\n", "ambiguous scalar", 1),
        ("a: 1e5\n", "ambiguous scalar", 1),
        ("a: 012\n", "ambiguous scalar", 1),
        ("a: 2026-10-07\n", "ambiguous scalar", 1),
        ("a: .5\n", "ambiguous scalar", 1),
        ("a: 1\na: 2\n", "duplicate key", 2),
        ("a: {k: 1, k: 2}\n", "duplicate key", 1),
        ("a: |+\n  text\n", "block scalar", 1),
        ("a: |2\n  text\n", "block scalar", 1),
        ("a: |\n  first\n    more indented\n", "block scalar", 3),
        ("a: |\n", "block scalar", 1),
        ("just a scalar\n", "top-level value", 1),
        ("a:\nb: 1\n", "missing value", 1),
        ('"quoted": 1\n', "quoted key", 1),
        ('a: "unterminated\n', "quoting", 1),
        (r'a: "bad \q escape"' + "\n", "escape", 1),
        ("a: 1\n  b: 2\n", "indentation", 2),
        ("  a: 1\n", "indentation", 1),
        ("", "empty document", 1),
        ("# only a comment\n", "empty document", 1),
        ("a: [1,, 2]\n", "flow collection", 1),
        ("a: [1, 2\n", "flow list", 1),
        ("a: {k 1}\n", "flow map", 1),
    ],
)
def test_rejections(text: str, construct: str | None, line: int | None) -> None:
    if construct is None:
        load(text)  # documented as the way to write it; must not raise
        return
    with pytest.raises(FormatError) as caught:
        load(text)
    assert caught.value.construct == construct
    assert caught.value.line == line


def test_messages_name_the_line_and_the_fix() -> None:
    """These are read while hand-authoring 73 records, so they state the remedy."""
    with pytest.raises(FormatError) as caught:
        load("tools:\n  - sandbox\n")
    message = str(caught.value)
    assert message.startswith("line 2: block sequence:")
    assert "[a, b]" in message, "the message must say what to write instead"
    assert "- sandbox" in message, "the message must quote the offending line"

    with pytest.raises(FormatError) as second:
        load("a: plain text: with a colon\n")
    assert "double quotes" in str(second.value)


def test_error_is_a_value_error_so_the_loader_can_aggregate() -> None:
    with pytest.raises(ValueError):
        load("tools:\n  - sandbox\n")
