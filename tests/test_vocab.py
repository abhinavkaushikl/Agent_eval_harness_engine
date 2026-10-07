"""The vocabulary drift tripwire.

After extraction there are 73 records keyed on these spellings, and a mismatch
between a record file and the enum fails silently at match time rather than
loudly at load time. These tests are what make it loud.

Why the coverage test is a mapping and not a list of strings that parse
----------------------------------------------------------------------
``TASKS.md`` S5 originally asked for "~20 situation strings taken verbatim from
the master lookup" that "all parse successfully". They cannot: the lookup's
Situation column is English prose -- "Output is code / SQL / an API call", "The
bad thing is under 5% of traffic" -- and ``parse_situation`` takes an enum value,
not prose. Teaching it prose normalisation would put a classifier (M1 work) in
the vocabulary. So the test is the mapping that reading implies: verbatim source
phrase -> the member a record author must cite for that row, with both ends
checked. The phrase end is checked against the corpus itself, so a corpus edit
or a typo here fails rather than quietly weakening the tripwire. That line of
``TASKS.md`` has been corrected to describe this.

The mapping is coarse on purpose. Section G's eight rows all map to
``rag_answer`` and section H's to ``agent_action``, because the finer distinction
between them lives in ``required_signals`` (the EL-003 audit's group 2 reading).
Rows whose Situation cell maps to no member, or to several, are listed in
``UNMAPPED_PHRASES`` below rather than hidden.
"""

from pathlib import Path

import pytest

from evalloop.vocab import Situation, Tool, parse_situation, parse_tool
from tests.conftest import MASTER_LOOKUP, SECTION_FILES, require_corpus_files
from tests.test_corpus_shape import _lookup_rows  # one parser for the table, not two

MINIMUM_PHRASES = 20

#: Verbatim master-lookup Situation cell -> the member that routes it, by section.
PHRASES_BY_SECTION: dict[str, tuple[tuple[str, Situation], ...]] = {
    "A": (
        ("Output is code / SQL / an API call", Situation.code_generation),
        ("Output is code / SQL / an API call", Situation.sql_generation),
        ("Output is code / SQL / an API call", Situation.api_endpoint),
        ("Agent claims it did something", Situation.agent_action),
        ("Output is a short fact", Situation.qa_answer),
        ("Output is open-ended text", Situation.prose_generation),
        ("Output is structured data", Situation.structured_extraction),
        ("High-stakes final decision", Situation.high_stakes_decision),
        ("Score needed on every production request", Situation.scoring_live_traffic),
    ),
    "B": (
        ("Old prompt vs new prompt", Situation.two_candidates),
        ("Which of two answers is better", Situation.two_candidates),
        ("Two paired binary results", Situation.two_candidates),
        ("Need to rank 5+ options", Situation.many_candidates),
        ("Reading someone else's leaderboard", Situation.external_leaderboard),
        ("Weird metric with no clean formula", Situation.metric_without_formula),
        ("Items come in groups", Situation.grouped_items),
    ),
    "C": (
        ("Before running the eval", Situation.pre_development),
        ("Stochastic system", Situation.stochastic_system),
        ("Score near 0% or 100%", Situation.score_near_0_or_100),
        ("Checking many metrics or slices", Situation.many_slices_checked),
        ("You don't trust the test's assumptions", Situation.heavy_tailed_metric),
    ),
    "D": (
        ("Bad class is under 5% of traffic", Situation.rare_class),
        ("False alarms are expensive", Situation.false_alarm_expensive),
        ("You haven't picked a threshold yet", Situation.threshold_not_chosen),
        ("Setting the threshold", Situation.error_costs_priceable),
        ("Measuring safety", Situation.measuring_safety),
        ("Reporting safety numbers", Situation.reporting_safety_numbers),
    ),
    "E": (
        ("Score jumped suddenly", Situation.score_jumped),
        ("Score improved but users didn't notice", Situation.score_up_business_flat),
        ("Score improved and answers got longer", Situation.length_increased),
        ("You changed nothing but the score moved", Situation.no_change_score_moved),
        ("All models score 90%+", Situation.all_candidates_high),
        ("Nothing completes at all", Situation.all_candidates_zero),
        ("Public benchmark score looks too good", Situation.benchmark_too_good),
        ("One model dominates one benchmark only", Situation.single_benchmark_dominance),
    ),
    "F": (
        ("Built a new LLM judge", Situation.new_judge_built),
        ("Measuring that agreement", Situation.measuring_agreement),
        ("More than two labellers", Situation.multiple_annotators),
        ("Judge might favour one position", Situation.position_bias_risk),
        ("Judge might favour its own family", Situation.self_preference_risk),
        ("Everything scores 7 or 8", Situation.scale_compressed),
        ("Judge grades the wrong dimension", Situation.new_judge_built),
        ("Want better judge accuracy", Situation.new_judge_built),
        ("Human labellers disagree", Situation.annotators_disagree),
    ),
    "G": (
        ("RAG gives wrong answers", Situation.rag_answer),
        ("Isolating which stage broke", Situation.rag_answer),
        ("Isolating which stage broke", Situation.debugging_regression),
        ("Answer contains invented facts", Situation.rag_answer),
        ("Ranking quality matters", Situation.rag_answer),
        ("Only one right document exists", Situation.rag_answer),
        ("System invents answers to unknowns", Situation.rag_answer),
        ("Retrieval sometimes returns junk", Situation.rag_answer),
        ("Citations shown to users", Situation.rag_answer),
    ),
    "H": (
        ("Any agent evaluation", Situation.agent_action),
        ("Measuring task success", Situation.agent_action),
        ("Quoting reliability to a customer", Situation.agent_action),
        ("Comparing agent costs", Situation.agent_action),
        ("Comparing agent costs", Situation.two_candidates),
        ("Long multi-step tasks", Situation.agent_action),
        ("Agent reads external content", Situation.agent_action),
        ("Agent behaves erratically", Situation.agent_action),
        ("Agent behaves erratically", Situation.debugging_regression),
        ("Runs fail inconsistently", Situation.agent_action),
        ("Runs fail inconsistently", Situation.stochastic_system),
    ),
    "I": (
        ("Shipping any change", Situation.shipping_change),
        ("CI keeps flaking", Situation.ci_flaking),
        ("Understanding what broke", Situation.debugging_regression),
        ("Detecting provider changes", Situation.detecting_drift),
        ("Scoring live traffic", Situation.scoring_live_traffic),
        ("Measuring real impact", Situation.measuring_impact),
        ("Testing a change on users", Situation.ab_testing),
        ("Building the eval set", Situation.building_eval_set),
        ("Deploying a new model", Situation.shipping_change),
    ),
    "J": (
        ("15 candidates, no time", Situation.model_selection),
        ("15 candidates, no time", Situation.many_candidates),
        ("Narrowing 4 to 1", Situation.model_selection),
        ("Balancing quality and money", Situation.model_selection),
        ("Comparing published numbers", Situation.external_leaderboard),
        ("Reading a vendor claim", Situation.external_leaderboard),
    ),
}

#: Situation cells with no honest single member. Kept here so the gap is visible.
UNMAPPED_PHRASES: dict[str, str] = {
    "Any score, ever": (
        "C1 applies to every score, and triggers_on_situation is specified "
        "non-empty, so a universal record has no encoding yet (schema question)"
    ),
}


def _situation_cells(corpus_dir: Path, section: str) -> set[str]:
    return {cells[0].strip() for cells in _lookup_rows(corpus_dir)[section]}


def test_every_situation_value_equals_its_lowercase_name() -> None:
    for member in Situation:
        assert member.value == member.name.lower()


def test_every_tool_value_equals_its_lowercase_name() -> None:
    for member in Tool:
        assert member.value == member.name.lower()


def test_situation_values_are_unique() -> None:
    values = [member.value for member in Situation]
    assert len(set(values)) == len(values), "duplicate Situation values"


def test_tool_values_are_unique() -> None:
    values = [member.value for member in Tool]
    assert len(set(values)) == len(values), "duplicate Tool values"


def test_no_situation_is_a_reversal_of_another() -> None:
    """items_grouped / grouped_items was one source row with two members (S3 ruling)."""
    reversed_words = {"_".join(reversed(m.value.split("_"))): m.value for m in Situation}
    collisions = sorted(
        (original, member.value)
        for member in Situation
        for original in [reversed_words.get(member.value)]
        if original is not None and original != member.value
    )
    assert not collisions, f"word-reversed near-duplicates: {collisions}"


@pytest.mark.parametrize("member", list(Situation), ids=lambda m: str(m))
def test_parse_situation_round_trips(member: Situation) -> None:
    assert parse_situation(member.value) is member
    assert parse_situation(member) is member


@pytest.mark.parametrize("member", list(Tool), ids=lambda m: str(m))
def test_parse_tool_round_trips(member: Tool) -> None:
    assert parse_tool(member.value) is member
    assert parse_tool(member) is member


@pytest.mark.parametrize("bad", ["text_summary", "", "Code_Generation", " code_generation"])
def test_parse_situation_rejects_unknown_naming_the_value(bad: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_situation(bad)
    message = str(caught.value)
    assert repr(bad) in message, message
    assert "code_generation" in message, "the valid options are not listed"


@pytest.mark.parametrize("bad", ["mcp_client", "mcp_gateway", "SANDBOX", "sand box"])
def test_parse_tool_rejects_unknown_naming_the_value(bad: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_tool(bad)
    message = str(caught.value)
    assert repr(bad) in message, message
    assert "sandbox" in message, "the valid options are not listed"


def test_parse_error_lists_options_in_sorted_order() -> None:
    with pytest.raises(ValueError) as caught:
        parse_tool("nope")
    listed = str(caught.value).split(": ", 1)[1].split(", ")
    assert listed == sorted(listed)
    assert set(listed) == {member.value for member in Tool}


def test_coverage_mapping_spans_every_section_and_is_big_enough() -> None:
    assert set(PHRASES_BY_SECTION) == set(SECTION_FILES), "not all ten sections"
    total = sum(len(entries) for entries in PHRASES_BY_SECTION.values())
    assert total >= MINIMUM_PHRASES, f"only {total} mapped phrases"
    for section, entries in PHRASES_BY_SECTION.items():
        assert entries, f"section {section} has no mapped phrase"


@pytest.mark.parametrize("section", sorted(PHRASES_BY_SECTION))
def test_mapped_phrases_are_verbatim_corpus_cells(corpus_dir: Path, section: str) -> None:
    """A phrase here that the corpus no longer contains is drift, not a typo to tidy."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    cells = _situation_cells(corpus_dir, section)
    missing = sorted({phrase for phrase, _ in PHRASES_BY_SECTION[section]} - cells)
    assert not missing, f"section {section} phrases absent from the corpus: {missing}"


@pytest.mark.parametrize("section", sorted(PHRASES_BY_SECTION))
def test_mapped_members_parse(section: str) -> None:
    for phrase, member in PHRASES_BY_SECTION[section]:
        assert parse_situation(member.value) is member, phrase


def test_every_lookup_row_is_mapped_or_declared_unmapped(corpus_dir: Path) -> None:
    """No Situation cell may be quietly skipped: it is mapped, or it is a known gap."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    for section in sorted(SECTION_FILES):
        mapped = {phrase for phrase, _ in PHRASES_BY_SECTION[section]}
        unaccounted = sorted(
            _situation_cells(corpus_dir, section) - mapped - set(UNMAPPED_PHRASES)
        )
        assert not unaccounted, (
            f"section {section}: Situation cells neither mapped nor declared "
            f"unmapped: {unaccounted}"
        )
