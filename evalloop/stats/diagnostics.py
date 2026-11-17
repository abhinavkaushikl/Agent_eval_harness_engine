"""Diagnostics: detect when a number looks wrong (T30, section E).

Four detectors, each matching the registry record it implements:

* **E1 score_jumped** -- per-item diff: compare two runs, report flips.
* **E3 length_increased** -- length spike: flag when output length jumps.
* **E5 all_candidates_high** -- ceiling effect: flag when all scores are near 100%.
* **E6 all_candidates_zero** -- floor effect: flag when all scores are near 0%.

Each detector takes the data it needs and returns a :class:`DiagnosticResult`
with a verdict (``flagged`` or ``clean``) and a human-readable explanation.
The registry records carry the thresholds and rules of thumb from the corpus;
the detectors here apply them.

Thresholds
----------
* E1: "If more than half the flipped items flipped for formatting reasons, the
  grader changed, not the model" (E:24).  The detector flags when the
  regression count exceeds the improvement count (a jump should be symmetric if
  real) or when the total flip count is suspiciously high (> 50% of items).
* E3: no numeric threshold in the corpus; the detector flags any increase above
  a user-specified ratio (default: 10% length increase).
* E5: ceiling at > 95% of items scoring above 90% (E:177-180: "if 95% of your
  items score above 90, the eval cannot distinguish good from great").
* E6: "Run your eval BEFORE any model does" (E:210).  The detector flags when
  > 50% of items score 0 (a floor too hard for all candidates).

None of these thresholds is invented: E1 and E5's come from the corpus, E3's
is a parameter the caller supplies, E6's 50% is the minimum useful signal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evalloop._compat import StrEnum

__all__ = [
    "DiagnosticKind",
    "DiagnosticResult",
    "diagnose_score_jump",
    "diagnose_length_spike",
    "diagnose_ceiling",
    "diagnose_floor",
    "run_all_diagnostics",
]


class DiagnosticKind(StrEnum):
    """Which section-E diagnostic this result came from."""

    score_jump = "E1_per_item_diff"
    length_spike = "E3_length_spike"
    ceiling = "E5_ceiling_effect"
    floor = "E6_floor_effect"


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    """One diagnostic's verdict: flagged (suspicious) or clean, with an explanation."""

    kind: DiagnosticKind
    flagged: bool
    explanation: str
    detail: Mapping[str, object]


# -- E1: score jump / per-item diff ------------------------------------------------


def diagnose_score_jump(
    regressions: int,
    improvements: int,
    total_items: int,
) -> DiagnosticResult:
    """E1: flag a suspicious score jump by comparing flip counts.

    Rules (from the corpus):
    - If more items flipped than half the total, something other than the model changed.
    - If regressions outnumber improvements, the "improvement" is not real.
    """
    total_flips = regressions + improvements
    detail: dict[str, object] = {
        "regressions": regressions,
        "improvements": improvements,
        "total_flips": total_flips,
        "total_items": total_items,
    }
    reasons: list[str] = []
    if total_items > 0 and total_flips > total_items / 2:
        reasons.append(
            f"{total_flips} of {total_items} items flipped ({total_flips / total_items:.0%}), "
            "which is more than half — the grader, parser, or data likely changed, not the model"
        )
    if regressions > improvements and improvements > 0:
        reasons.append(
            f"{regressions} regressions vs {improvements} improvements — "
            "a real improvement should not regress more items than it fixes"
        )
    if regressions > 0 and improvements == 0:
        reasons.append(
            f"{regressions} regressions and 0 improvements — this is a pure degradation, not a jump"
        )
    return DiagnosticResult(
        kind=DiagnosticKind.score_jump,
        flagged=bool(reasons),
        explanation="; ".join(reasons) if reasons else "flip counts look consistent with a real change",
        detail=detail,
    )


# -- E3: length spike ---------------------------------------------------------------


def diagnose_length_spike(
    lengths_before: Sequence[float],
    lengths_after: Sequence[float],
    *,
    threshold_ratio: float = 0.10,
) -> DiagnosticResult:
    """E3: flag when output length increases significantly between two runs.

    ``threshold_ratio`` is the minimum relative increase to flag (default: 10%).
    Lengths are per-item (e.g. character count, token count).
    """
    if not lengths_before or not lengths_after:
        return DiagnosticResult(
            kind=DiagnosticKind.length_spike,
            flagged=False,
            explanation="no length data to compare",
            detail={"before_n": len(lengths_before), "after_n": len(lengths_after)},
        )
    mean_before = sum(lengths_before) / len(lengths_before)
    mean_after = sum(lengths_after) / len(lengths_after)
    if mean_before == 0:
        ratio = float("inf") if mean_after > 0 else 0.0
    else:
        ratio = (mean_after - mean_before) / mean_before
    detail: dict[str, object] = {
        "mean_before": mean_before,
        "mean_after": mean_after,
        "ratio": ratio,
        "threshold_ratio": threshold_ratio,
    }
    flagged = ratio > threshold_ratio
    if flagged:
        explanation = (
            f"mean output length increased by {ratio:.1%} "
            f"({mean_before:.1f} -> {mean_after:.1f}), "
            f"above the {threshold_ratio:.0%} threshold — "
            "a length-controlled comparison may show a different winner"
        )
    else:
        explanation = f"length change of {ratio:.1%} is within the {threshold_ratio:.0%} threshold"
    return DiagnosticResult(
        kind=DiagnosticKind.length_spike,
        flagged=flagged,
        explanation=explanation,
        detail=detail,
    )


# -- E5: ceiling effect -------------------------------------------------------------

# E:177-180: "if 95% of your items score above 90, the eval cannot distinguish"
_CEILING_ITEM_THRESHOLD = 0.90
_CEILING_SHARE_THRESHOLD = 0.95


def diagnose_ceiling(
    scores: Sequence[float],
    *,
    item_threshold: float = _CEILING_ITEM_THRESHOLD,
    share_threshold: float = _CEILING_SHARE_THRESHOLD,
) -> DiagnosticResult:
    """E5: flag when too many items score near the top (ceiling effect).

    Default thresholds from the corpus: 95% of items above 90%.
    """
    if not scores:
        return DiagnosticResult(
            kind=DiagnosticKind.ceiling,
            flagged=False,
            explanation="no scores to check",
            detail={},
        )
    high = sum(1 for s in scores if s >= item_threshold)
    share = high / len(scores)
    detail: dict[str, object] = {
        "high_count": high,
        "total": len(scores),
        "share": share,
        "item_threshold": item_threshold,
        "share_threshold": share_threshold,
    }
    flagged = share >= share_threshold
    if flagged:
        explanation = (
            f"{high} of {len(scores)} items ({share:.0%}) score >= {item_threshold:.0%} — "
            "the eval cannot distinguish good from great; "
            "harder items or a stricter rubric is needed"
        )
    else:
        explanation = (
            f"{share:.0%} of items above {item_threshold:.0%} — "
            f"below the {share_threshold:.0%} ceiling threshold"
        )
    return DiagnosticResult(kind=DiagnosticKind.ceiling, flagged=flagged, explanation=explanation, detail=detail)


# -- E6: floor effect ---------------------------------------------------------------

_FLOOR_THRESHOLD = 0.50


def diagnose_floor(
    scores: Sequence[float],
    *,
    zero_threshold: float = 0.0,
    share_threshold: float = _FLOOR_THRESHOLD,
) -> DiagnosticResult:
    """E6: flag when too many items score zero (floor effect).

    ``zero_threshold`` is the score at or below which an item is "at the floor".
    ``share_threshold`` is the fraction of items that must be at the floor to flag.
    """
    if not scores:
        return DiagnosticResult(
            kind=DiagnosticKind.floor,
            flagged=False,
            explanation="no scores to check",
            detail={},
        )
    at_floor = sum(1 for s in scores if s <= zero_threshold)
    share = at_floor / len(scores)
    detail: dict[str, object] = {
        "at_floor": at_floor,
        "total": len(scores),
        "share": share,
        "zero_threshold": zero_threshold,
        "share_threshold": share_threshold,
    }
    flagged = share >= share_threshold
    if flagged:
        explanation = (
            f"{at_floor} of {len(scores)} items ({share:.0%}) score <= {zero_threshold} — "
            "the eval is too hard for all candidates; "
            "run it BEFORE any model does to establish a human baseline (E:210)"
        )
    else:
        explanation = (
            f"{share:.0%} of items at the floor — "
            f"below the {share_threshold:.0%} floor threshold"
        )
    return DiagnosticResult(kind=DiagnosticKind.floor, flagged=flagged, explanation=explanation, detail=detail)


# -- run all diagnostics on a run pair -----------------------------------------------


def run_all_diagnostics(
    *,
    regressions: int = 0,
    improvements: int = 0,
    total_items: int = 0,
    lengths_before: Sequence[float] = (),
    lengths_after: Sequence[float] = (),
    scores: Sequence[float] = (),
) -> tuple[DiagnosticResult, ...]:
    """Run all four diagnostics and return the results.

    Callers supply whatever data they have; diagnostics that lack data report
    ``flagged=False`` with an explanation that says so.
    """
    return (
        diagnose_score_jump(regressions, improvements, total_items),
        diagnose_length_spike(lengths_before, lengths_after),
        diagnose_ceiling(scores),
        diagnose_floor(scores),
    )
