"""Position swap and flip-rate tracking (T35).

Corpus F4 (F:135): "Present the two outputs in both orders to the same judge.
If swapping the position changes the verdict on more than 10–15% of items, the
judge has position bias and cannot make this comparison."

The flip rate is not a statistical estimate; it is a direct count over the same
items judged twice.  10–15% is the threshold from the corpus; this module reports
the rate and flags it against that range.

How it works
------------
For each item, the judge sees the artifact twice:
  1. Original order: ``(A, B)``
  2. Swapped order: ``(B, A)``

A "flip" is an item where the two calls disagree.  The flip rate is
``flips / items``.  F:140: "unreliable above 10–15%".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "PositionPair",
    "SwapResult",
    "SwapSummary",
    "check_position_bias",
]


@dataclass(frozen=True, slots=True)
class PositionPair:
    """One item judged in both orders."""

    item_id: str
    verdict_original: str  # verdict when shown in order (A, B)
    verdict_swapped: str  # verdict when shown in order (B, A)

    @property
    def flipped(self) -> bool:
        return self.verdict_original != self.verdict_swapped


@dataclass(frozen=True, slots=True)
class SwapResult:
    """The position-swap analysis for one criterion."""

    criterion_name: str
    pairs: tuple[PositionPair, ...]
    flip_rate: float
    flagged: bool
    explanation: str


@dataclass(frozen=True, slots=True)
class SwapSummary:
    """Position-swap results across all criteria."""

    results: tuple[SwapResult, ...]
    any_flagged: bool
    overall_flip_rate: float


#: F:140: "unreliable above 10–15%".  We flag at the low end (10%).
_FLIP_RATE_THRESHOLD_LOW = 0.10
_FLIP_RATE_THRESHOLD_HIGH = 0.15


def check_position_bias(
    pairs: Sequence[PositionPair],
    *,
    criterion_name: str = "",
    threshold_low: float = _FLIP_RATE_THRESHOLD_LOW,
    threshold_high: float = _FLIP_RATE_THRESHOLD_HIGH,
) -> SwapResult:
    """Check position bias for a set of position-swapped judgments.

    Returns a :class:`SwapResult` with the flip rate and whether it's flagged.
    """
    if not pairs:
        return SwapResult(
            criterion_name=criterion_name,
            pairs=(),
            flip_rate=0.0,
            flagged=False,
            explanation="no position-swap pairs to check",
        )
    pairs_tuple = tuple(pairs)
    flips = sum(1 for p in pairs_tuple if p.flipped)
    rate = flips / len(pairs_tuple)
    if rate > threshold_high:
        flagged = True
        explanation = (
            f"flip rate {rate:.1%} is above {threshold_high:.0%} — "
            "the judge has strong position bias and cannot make this comparison (F:140)"
        )
    elif rate > threshold_low:
        flagged = True
        explanation = (
            f"flip rate {rate:.1%} is in the {threshold_low:.0%}–{threshold_high:.0%} range — "
            "position bias is borderline; consider more items or a different judge"
        )
    else:
        flagged = False
        explanation = f"flip rate {rate:.1%} is below {threshold_low:.0%} — no significant position bias"
    return SwapResult(
        criterion_name=criterion_name,
        pairs=pairs_tuple,
        flip_rate=rate,
        flagged=flagged,
        explanation=explanation,
    )


def summarise_swaps(results: Sequence[SwapResult]) -> SwapSummary:
    """Summarise position-swap results across criteria."""
    if not results:
        return SwapSummary(results=(), any_flagged=False, overall_flip_rate=0.0)
    total_pairs = sum(len(r.pairs) for r in results)
    total_flips = sum(sum(1 for p in r.pairs if p.flipped) for r in results)
    overall = total_flips / total_pairs if total_pairs > 0 else 0.0
    return SwapSummary(
        results=tuple(results),
        any_flagged=any(r.flagged for r in results),
        overall_flip_rate=overall,
    )
