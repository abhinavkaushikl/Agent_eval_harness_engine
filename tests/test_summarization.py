"""Tests for evalloop.judge.summarization (T37)."""

from __future__ import annotations

from evalloop.judge.summarization import (
    FAITHFULNESS_CRITERION,
    LENGTH_CRITERION,
    LengthCheck,
    SummarizationConfig,
    check_length,
    summarization_config,
)

from evalloop.judge.grader import Criterion, JudgeConfig


# ---------------------------------------------------------------------------
# Criteria constants
# ---------------------------------------------------------------------------

def test_faithfulness_criterion_is_criterion() -> None:
    assert isinstance(FAITHFULNESS_CRITERION, Criterion)
    assert FAITHFULNESS_CRITERION.name == "faithfulness"
    assert FAITHFULNESS_CRITERION.pass_label == "FAITHFUL"
    assert FAITHFULNESS_CRITERION.fail_label == "UNFAITHFUL"


def test_length_criterion_is_criterion() -> None:
    assert isinstance(LENGTH_CRITERION, Criterion)
    assert LENGTH_CRITERION.name == "length_appropriateness"
    assert LENGTH_CRITERION.pass_label == "APPROPRIATE"
    assert LENGTH_CRITERION.fail_label == "INAPPROPRIATE"


# ---------------------------------------------------------------------------
# SummarizationConfig
# ---------------------------------------------------------------------------

def test_summarization_config_defaults() -> None:
    cfg = summarization_config()
    assert cfg.max_length_ratio == 0.5
    assert cfg.min_length_ratio == 0.05
    assert cfg.faithfulness is FAITHFULNESS_CRITERION
    assert cfg.length is LENGTH_CRITERION


def test_summarization_config_custom() -> None:
    cfg = summarization_config(max_length_ratio=0.3, min_length_ratio=0.1)
    assert cfg.max_length_ratio == 0.3
    assert cfg.min_length_ratio == 0.1


def test_summarization_config_judge_config() -> None:
    cfg = summarization_config()
    jc = cfg.judge_config()
    assert isinstance(jc, JudgeConfig)
    assert len(jc.criteria) == 2
    assert jc.criteria[0].name == "faithfulness"
    assert jc.criteria[1].name == "length_appropriateness"


# ---------------------------------------------------------------------------
# check_length
# ---------------------------------------------------------------------------

def test_check_length_appropriate() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 20)  # 20% ratio
    result = check_length(source, summary)
    assert result.passed is True
    assert result.source_length == 100
    assert result.summary_length == 20
    assert abs(result.ratio - 0.2) < 1e-9


def test_check_length_too_long() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 60)  # 60% > 50% max
    result = check_length(source, summary)
    assert result.passed is False
    assert "too verbose" in result.reason


def test_check_length_too_short() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 2)  # 2% < 5% min
    result = check_length(source, summary)
    assert result.passed is False
    assert "too terse" in result.reason


def test_check_length_empty_source() -> None:
    result = check_length("", "some summary")
    assert result.passed is True
    assert result.source_length == 0
    assert "empty" in result.reason


def test_check_length_custom_thresholds() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 35)  # 35%
    # With max_ratio=0.3, this should fail
    result = check_length(source, summary, max_ratio=0.3)
    assert result.passed is False
    # With max_ratio=0.4, this should also fail
    result2 = check_length(source, summary, max_ratio=0.4)
    assert result2.passed is True


def test_check_length_at_boundary() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 50)  # exactly 50%
    # 50% == max_ratio, so ratio > max_ratio is False
    result = check_length(source, summary)
    assert result.passed is True  # 50/100 = 0.5, not > 0.5


def test_check_length_just_above_max() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 51)  # 51% > 50%
    result = check_length(source, summary)
    assert result.passed is False


def test_check_length_just_above_min() -> None:
    source = " ".join(["word"] * 100)
    summary = " ".join(["word"] * 5)  # 5% == min, not < min
    result = check_length(source, summary)
    assert result.passed is True


def test_check_length_single_word_summary() -> None:
    source = " ".join(["word"] * 100)
    summary = "word"
    result = check_length(source, summary)
    assert result.passed is False  # 1% < 5% min
