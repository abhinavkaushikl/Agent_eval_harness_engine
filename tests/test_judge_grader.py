"""Tests for evalloop.judge.grader (T33)."""

from __future__ import annotations

from evalloop.judge.grader import (
    Criterion,
    JudgeConfig,
    JudgeRequest,
    JudgeVerdict,
    build_judge_prompt,
    parse_judge_response,
)

import pytest


# ---------------------------------------------------------------------------
# Criterion
# ---------------------------------------------------------------------------

def test_criterion_defaults() -> None:
    c = Criterion(name="test", question="Is it good?")
    assert c.pass_label == "PASS"
    assert c.fail_label == "FAIL"
    assert c.description == ""
    assert c.few_shot == ()


def test_criterion_custom_labels() -> None:
    c = Criterion(name="faith", question="faithful?", pass_label="FAITHFUL", fail_label="UNFAITHFUL")
    assert c.pass_label == "FAITHFUL"
    assert c.fail_label == "UNFAITHFUL"


# ---------------------------------------------------------------------------
# JudgeConfig
# ---------------------------------------------------------------------------

def test_judge_config_requires_criteria() -> None:
    with pytest.raises(ValueError, match="at least one criterion"):
        JudgeConfig(criteria=())


def test_judge_config_unique_names() -> None:
    c = Criterion(name="dup", question="q")
    with pytest.raises(ValueError, match="duplicates"):
        JudgeConfig(criteria=(c, c))


def test_judge_config_valid() -> None:
    c1 = Criterion(name="a", question="q1")
    c2 = Criterion(name="b", question="q2")
    cfg = JudgeConfig(criteria=(c1, c2))
    assert len(cfg.criteria) == 2


# ---------------------------------------------------------------------------
# build_judge_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_contains_criterion() -> None:
    c = Criterion(name="accuracy", question="Is it accurate?")
    req = build_judge_prompt(c, "The sky is blue.")
    assert "accuracy" in req.system
    assert "Is it accurate?" in req.system
    assert "PASS" in req.system
    assert "FAIL" in req.system
    assert "VERDICT:" in req.system
    assert "The sky is blue." in req.user
    assert req.artifact == "The sky is blue."


def test_build_prompt_with_preamble() -> None:
    c = Criterion(name="x", question="q")
    req = build_judge_prompt(c, "art", preamble="You are an expert.")
    assert req.system.startswith("You are an expert.")


def test_build_prompt_with_description() -> None:
    c = Criterion(name="x", question="q", description="Extra context here.")
    req = build_judge_prompt(c, "art")
    assert "Extra context here." in req.system


def test_build_prompt_with_few_shot() -> None:
    c = Criterion(
        name="x", question="q",
        few_shot=(("example artifact", "PASS"),),
    )
    req = build_judge_prompt(c, "art")
    assert "Example 1" in req.system
    assert "example artifact" in req.system
    assert "Expected verdict: PASS" in req.system


def test_build_prompt_custom_labels() -> None:
    c = Criterion(name="faith", question="q", pass_label="FAITHFUL", fail_label="UNFAITHFUL")
    req = build_judge_prompt(c, "art")
    assert "FAITHFUL" in req.system
    assert "UNFAITHFUL" in req.system


# ---------------------------------------------------------------------------
# parse_judge_response
# ---------------------------------------------------------------------------

_CRIT = Criterion(name="test", question="q")


def test_parse_verdict_pass() -> None:
    resp = "The answer is correct because...\nVERDICT: PASS"
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is True
    assert v.verdict == "PASS"
    assert v.parsed is True
    assert v.criterion_name == "test"
    assert "correct" in v.reasoning


def test_parse_verdict_fail() -> None:
    resp = "It is wrong.\nVERDICT: FAIL"
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is False
    assert v.verdict == "FAIL"
    assert v.parsed is True


def test_parse_verdict_case_insensitive() -> None:
    resp = "Reasoning here.\nverdict: pass"
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is True
    assert v.parsed is True


def test_parse_verdict_custom_labels() -> None:
    c = Criterion(name="faith", question="q", pass_label="FAITHFUL", fail_label="UNFAITHFUL")
    resp = "The summary is consistent.\nVERDICT: FAITHFUL"
    v = parse_judge_response(resp, c)
    assert v.passed is True
    assert v.verdict == "FAITHFUL"


def test_parse_verdict_custom_labels_fail() -> None:
    c = Criterion(name="faith", question="q", pass_label="FAITHFUL", fail_label="UNFAITHFUL")
    resp = "Fabricated claim found.\nVERDICT: UNFAITHFUL"
    v = parse_judge_response(resp, c)
    assert v.passed is False
    assert v.verdict == "UNFAITHFUL"


def test_parse_fallback_last_line() -> None:
    resp = "Some reasoning\nPASS"
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is True
    assert v.parsed is False


def test_parse_fallback_last_line_fail() -> None:
    resp = "Some reasoning\nFAIL"
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is False
    assert v.parsed is False


def test_parse_unparseable_defaults_to_fail() -> None:
    resp = "I don't know what to say"
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is False
    assert v.parsed is False
    assert v.verdict == "FAIL"


def test_parse_verdict_with_trailing_punctuation() -> None:
    resp = "Good.\nVERDICT: PASS."
    v = parse_judge_response(resp, _CRIT)
    assert v.passed is True
    assert v.parsed is True


def test_parse_reasoning_before_verdict() -> None:
    resp = "Line one.\nLine two.\nLine three.\nVERDICT: PASS"
    v = parse_judge_response(resp, _CRIT)
    assert "Line one." in v.reasoning
    assert "Line two." in v.reasoning
    assert "Line three." in v.reasoning


def test_parse_empty_response() -> None:
    v = parse_judge_response("", _CRIT)
    assert v.passed is False
    assert v.parsed is False
