"""Is the difference real? McNemar, the paired permutation test, and false-alarm odds.

Section B's headline is "Compare on the same items" (B:6), and every test here
is a **paired** test: the same items, scored by both versions. There is no
unpaired two-proportion z-test in this package, on purpose -- B:124 names
"running a two-proportion z-test ... on paired data" as *the* mistake.

McNemar's two branches
----------------------
B:100 states the statistic **with continuity correction**,
chi^2 = (|b - c| - 1)^2 / (b + c), and B:107 states when it may be used: "At
least 25 discordant pairs (b + c >= 25) are needed for the chi^2
approximation. Below that, use the exact binomial test on b against b + c at
p = 0.5." :func:`mcnemar` applies that switch itself and reports which branch
ran, because B:121 is a worked example of what happens when it is skipped: an
analyst ran an uncorrected chi^2 on b + c = 14, got p = 0.033, and declared a
win the exact test (p = 0.057) does not support.

The uncorrected statistic is **not** available as an option. The tests
reproduce the analyst's 4.57 and 0.033 through :func:`chi_square_1df_sf`, to
show the corpus's figures are the corpus's mistake rather than this module's.

**One departure from B:100's formula as printed, flagged for review.** Read
literally, (|b - c| - 1)^2 is 1/(b + c) when b == c, so a tie would score as
*more* evidence of a difference than b and c one apart (which scores 0). The
correction is therefore clamped, max(|b - c| - 1, 0)^2, the behaviour of R's
``mcnemar.test``. It changes the result only when b == c, and only above 25
discordant pairs; every corpus worked example is unaffected.

The planner and this module disagree, and the corpus sides with this module
---------------------------------------------------------------------------
``B3_mcnemar`` carries ``requires: {discordant_pairs: 25}``, so below 25 the
planner reports B3 as PENDING. B:107 does not say "wait for 25"; it says "use
the exact binomial test". The record's own extraction notes record that the
schema cannot express that fallback. This module implements it; whether the
planner should treat b + c < 25 as ready-with-exact rather than pending is a
ruling, not something this module decides.

The permutation test's p-value
------------------------------
C:201: "The p-value is the fraction of shuffles whose difference is at least as
large as the one you observed." C:209: "Use 10,000 shuffles. The smallest
p-value you can report is 1/10,000." So the p-value is the fraction, floored
at 1/shuffles, and :attr:`PermutationResult.at_floor` says when the floor was
hit -- the honest report is then "p < 1/shuffles", not "p = 0".

"At least as large" is read as **two-sided**, comparing magnitudes: C:217
counts shuffles "as extreme" as the observed improvement, and an improvement
and a regression of the same size are equally extreme under the null. That
reading is an interpretation of C:201's wording and is flagged as such.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from evalloop._compat import StrEnum

__all__ = [
    "CHI_SQUARE_MIN_DISCORDANT",
    "DEFAULT_ALPHA",
    "DEFAULT_SHUFFLES",
    "McNemarMethod",
    "McNemarResult",
    "PermutationResult",
    "chi_square_1df_sf",
    "familywise_error_rate",
    "mcnemar",
    "paired_permutation_test",
    "permutation_p_value",
]

#: B:107, "At least 25 discordant pairs (b + c >= 25) are needed for the chi^2
#: approximation." The same bound is ``B3_mcnemar``'s ``requires``.
CHI_SQUARE_MIN_DISCORDANT = 25

#: C:19, "(alpha = 0.05, 80% power)"; C:21, "checking k slices at alpha = 0.05".
DEFAULT_ALPHA = 0.05

#: C:209, "Use 10,000 shuffles."
DEFAULT_SHUFFLES = 10_000

# Floating point, not methodology: a shuffled difference within this relative
# distance of the observed one is counted as "at least as large". Two
# arrangements that tie in exact arithmetic can differ in the last bits, and
# counting the near-tie errs toward a larger p-value -- the honest direction.
_TIE_RELATIVE_TOLERANCE = 1e-12


class McNemarMethod(StrEnum):
    """Which of B:107's two branches produced the p-value."""

    chi_square_continuity_corrected = "chi_square_continuity_corrected"
    exact_binomial = "exact_binomial"


@dataclass(frozen=True, slots=True)
class McNemarResult:
    """McNemar on the discordant cells.

    ``b``: the old version was right and the new one wrong -- B:109, "Read the
    b cell. These are your regressions." ``c``: the old was wrong and the new
    right. ``chi_square`` is ``None`` when the exact branch ran, because no
    chi^2 was computed.
    """

    b: int
    c: int
    method: McNemarMethod
    chi_square: float | None
    p_value: float


@dataclass(frozen=True, slots=True)
class PermutationResult:
    """A paired permutation test. ``observed`` is statistic(candidate) - statistic(baseline)."""

    observed: float
    p_value: float
    extreme: int
    shuffles: int
    seed: int

    @property
    def at_floor(self) -> bool:
        """No shuffle was as extreme: report "p < 1/shuffles", not the floor itself (C:209)."""
        return self.extreme == 0


def chi_square_1df_sf(statistic: float) -> float:
    """P(chi^2 with 1 degree of freedom > statistic).

    For one degree of freedom chi^2 is the square of a standard normal, so the
    survival function is erfc(sqrt(x/2)) exactly. B:108's critical values check
    it: 3.84 -> p = 0.05 and 6.63 -> p = 0.01.
    """
    if statistic < 0.0:
        raise ValueError(f"a chi-square statistic cannot be negative, got {statistic}")
    return math.erfc(math.sqrt(statistic / 2.0))


def _exact_binomial_two_sided(b: int, c: int) -> float:
    """B:107: "the exact binomial test on b against b + c at p = 0.5", two-sided.

    At p = 0.5 the distribution is symmetric, so the two-sided p-value is twice
    the smaller tail, capped at 1. Computed in exact integer arithmetic.
    """
    n = b + c
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return float(min(Fraction(1), Fraction(2 * tail, 2**n)))


def mcnemar(b: int, c: int) -> McNemarResult:
    """McNemar's test on paired pass/fail results (B3), with B:107's branch applied.

    ``b + c >= 25``: chi^2 with continuity correction, B:100, clamped at zero
    (see the module docstring). Below 25: the exact binomial test, B:107.
    Concordant items are not an argument because they carry no information
    about the difference (B:103).
    """
    if b < 0 or c < 0:
        raise ValueError(f"discordant counts cannot be negative, got b={b}, c={c}")
    if b + c >= CHI_SQUARE_MIN_DISCORDANT:
        statistic = max(abs(b - c) - 1, 0) ** 2 / (b + c)
        return McNemarResult(
            b,
            c,
            McNemarMethod.chi_square_continuity_corrected,
            statistic,
            chi_square_1df_sf(statistic),
        )
    return McNemarResult(
        b, c, McNemarMethod.exact_binomial, None, _exact_binomial_two_sided(b, c)
    )


def familywise_error_rate(tests: int, alpha: float = DEFAULT_ALPHA) -> float:
    """P(at least one false alarm) across ``tests`` independent checks: 1 - (1 - alpha)^k.

    C:21: "checking k slices at alpha = 0.05 gives P(at least one false alarm)
    = 1 - 0.95^k, which is already 64% at k = 20."
    """
    if tests < 1:
        raise ValueError(f"tests must be at least 1, got {tests}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    return 1.0 - (1.0 - alpha) ** tests


def permutation_p_value(extreme: int, shuffles: int) -> float:
    """The fraction of shuffles at least as extreme (C:201), floored at 1/shuffles (C:209)."""
    if shuffles < 1:
        raise ValueError(f"shuffles must be at least 1, got {shuffles}")
    if not 0 <= extreme <= shuffles:
        raise ValueError(f"extreme must be in [0, {shuffles}], got {extreme}")
    return max(extreme, 1) / shuffles


def paired_permutation_test(
    baseline: Sequence[float],
    candidate: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    seed: int,
    shuffles: int = DEFAULT_SHUFFLES,
) -> PermutationResult:
    """C6: swap the A/B labels within each item at random, ``shuffles`` times.

    C:201: "randomly swap the A/B labels within each item 10,000 times and
    recompute the difference each time." Each shuffle swaps item i's baseline
    and candidate values with probability 1/2 and recomputes
    ``statistic(candidate) - statistic(baseline)``. For the mean this is C:208's
    "flip the sign of each item's difference at random"; for a median or a
    trimmed mean -- which C:207 recommends for heavy tails -- the label swap is
    the general form.

    ``statistic`` should be chosen "before looking at the results" (C:207).
    ``seed`` is required and recorded in the result. Every draw comes from
    ``random.Random(seed).random()``, the one method whose sequence Python
    guarantees stable across versions.
    """
    if len(baseline) != len(candidate):
        raise ValueError(
            f"paired data needs one baseline and one candidate value per item; "
            f"got {len(baseline)} and {len(candidate)}"
        )
    if not baseline:
        raise ValueError("a permutation test needs at least one item")
    if shuffles < 1:
        raise ValueError(f"shuffles must be at least 1, got {shuffles}")
    pairs = list(zip(baseline, candidate))
    observed = statistic(candidate) - statistic(baseline)
    threshold = abs(observed) * (1.0 - _TIE_RELATIVE_TOLERANCE)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(shuffles):
        shuffled_baseline: list[float] = []
        shuffled_candidate: list[float] = []
        for old, new in pairs:
            if rng.random() < 0.5:
                old, new = new, old
            shuffled_baseline.append(old)
            shuffled_candidate.append(new)
        if abs(statistic(shuffled_candidate) - statistic(shuffled_baseline)) >= threshold:
            extreme += 1
    return PermutationResult(
        observed, permutation_p_value(extreme, shuffles), extreme, shuffles, seed
    )
