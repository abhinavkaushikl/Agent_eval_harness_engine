"""Tests for evalloop.judge.position_swap (T35)."""

from __future__ import annotations

from evalloop.judge.position_swap import (
    PositionPair,
    SwapResult,
    SwapSummary,
    check_position_bias,
    summarise_swaps,
)


# ---------------------------------------------------------------------------
# PositionPair
# ---------------------------------------------------------------------------

def test_pair_no_flip() -> None:
    p = PositionPair(item_id="1", verdict_original="PASS", verdict_swapped="PASS")
    assert p.flipped is False


def test_pair_flip() -> None:
    p = PositionPair(item_id="1", verdict_original="PASS", verdict_swapped="FAIL")
    assert p.flipped is True


# ---------------------------------------------------------------------------
# check_position_bias
# ---------------------------------------------------------------------------

def test_no_pairs() -> None:
    r = check_position_bias([], criterion_name="test")
    assert r.flip_rate == 0.0
    assert r.flagged is False
    assert r.pairs == ()


def test_no_flips() -> None:
    pairs = [
        PositionPair("1", "PASS", "PASS"),
        PositionPair("2", "FAIL", "FAIL"),
        PositionPair("3", "PASS", "PASS"),
    ]
    r = check_position_bias(pairs, criterion_name="acc")
    assert r.flip_rate == 0.0
    assert r.flagged is False
    assert r.criterion_name == "acc"


def test_low_flip_rate() -> None:
    # 1 flip out of 20 = 5%, below 10% threshold
    pairs = [PositionPair(str(i), "PASS", "PASS") for i in range(19)]
    pairs.append(PositionPair("19", "PASS", "FAIL"))
    r = check_position_bias(pairs)
    assert r.flip_rate == 1 / 20
    assert r.flagged is False


def test_borderline_flip_rate() -> None:
    # 12 flips out of 100 = 12%, in the 10-15% range
    pairs = [PositionPair(str(i), "PASS", "PASS") for i in range(88)]
    pairs.extend(PositionPair(str(88 + i), "PASS", "FAIL") for i in range(12))
    r = check_position_bias(pairs)
    assert abs(r.flip_rate - 0.12) < 1e-9
    assert r.flagged is True
    assert "borderline" in r.explanation


def test_high_flip_rate() -> None:
    # 20 flips out of 100 = 20%, above 15%
    pairs = [PositionPair(str(i), "PASS", "PASS") for i in range(80)]
    pairs.extend(PositionPair(str(80 + i), "PASS", "FAIL") for i in range(20))
    r = check_position_bias(pairs)
    assert abs(r.flip_rate - 0.20) < 1e-9
    assert r.flagged is True
    assert "strong position bias" in r.explanation


def test_custom_thresholds() -> None:
    # 1 flip out of 10 = 10%, flag with low threshold of 5%
    pairs = [PositionPair(str(i), "PASS", "PASS") for i in range(9)]
    pairs.append(PositionPair("9", "PASS", "FAIL"))
    r = check_position_bias(pairs, threshold_low=0.05, threshold_high=0.08)
    assert r.flagged is True


def test_all_flipped() -> None:
    pairs = [PositionPair(str(i), "PASS", "FAIL") for i in range(10)]
    r = check_position_bias(pairs)
    assert r.flip_rate == 1.0
    assert r.flagged is True


# ---------------------------------------------------------------------------
# summarise_swaps
# ---------------------------------------------------------------------------

def test_summarise_empty() -> None:
    s = summarise_swaps([])
    assert s.any_flagged is False
    assert s.overall_flip_rate == 0.0
    assert s.results == ()


def test_summarise_multiple() -> None:
    pairs_a = [PositionPair(str(i), "PASS", "PASS") for i in range(10)]
    pairs_b = [PositionPair(str(i), "PASS", "FAIL") for i in range(10)]
    r_a = check_position_bias(pairs_a, criterion_name="a")
    r_b = check_position_bias(pairs_b, criterion_name="b")
    s = summarise_swaps([r_a, r_b])
    assert s.any_flagged is True  # r_b is 100% flip rate
    assert s.overall_flip_rate == 10 / 20  # 10 flips out of 20 total pairs


def test_summarise_no_flags() -> None:
    pairs = [PositionPair(str(i), "PASS", "PASS") for i in range(10)]
    r = check_position_bias(pairs, criterion_name="x")
    s = summarise_swaps([r])
    assert s.any_flagged is False
    assert s.overall_flip_rate == 0.0
