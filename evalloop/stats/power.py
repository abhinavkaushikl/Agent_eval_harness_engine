"""How many items, how small an effect, and how much does a rerun move: C2 and C3.

C2: "Before you collect or label data, you solve for the n needed to detect the
smallest effect you care about, at alpha = 0.05 and 80% power. Or you work
backwards: given your budget of n, compute the minimum detectable effect"
(C:62). C3: "The run-to-run SD is your noise floor" (C:97).

The two formulas are the corpus's, constants included
-----------------------------------------------------
* Unpaired, C:19 and C:69: n ~ 16*p(1-p)/delta^2 per arm.
* Paired (McNemar), C:70: n ~ (1.96*sqrt(d) + 0.84*sqrt(d - delta^2))^2 / delta^2,
  where d is the expected share of discordant items.

Both are implemented with the printed constants -- 16, 1.96, 0.84 -- rather than
exact normal quantiles, because they are rules of thumb and the point of a rule
of thumb is that a reader can check it by hand against the line it came from.
The 16 is 2*(1.96 + 0.84)^2 = 15.68, rounded. **That rounding is the whole
of a discrepancy M0 recorded and could not explain:** the master lookup's
"~ 905 items per arm" is 15.68 * 0.144375 / 0.0025 = 905.5, and the deep dive's
"~ 920" is 16 * 0.144375 / 0.0025 = 924. Same formula, two roundings of its
constant. This module uses the deep dive's 16.

What "p" means -- an interpretation, flagged
--------------------------------------------
C:19 and C:69 write p(1-p) and never say which p. The worked example settles
it: "To detect 80% -> 85% you need ~ 920 items per arm" reproduces only with p
as the **midpoint**, 0.825 (924). p = 0.80 gives 1,024 and p = 0.85 gives 816.
So the unpaired functions take the two rates and use their midpoint, and the
caller cannot get this wrong. The reading comes from the worked example rather
than from a stated definition, and it is flagged for review.

The power function is the one formula here that the corpus does not print
-------------------------------------------------------------------------
C:79 states a result, "at n = 150 per arm, the chance of detecting a real
5-point gain was 21%", and no formula. :func:`unpaired_power` is the normal
approximation that the 16 rule inverts. It gives 20.6% for C:79, and the
unpooled-variance variant gives 20.7%, so the corpus's figure does not
discriminate between them; the pooled midpoint is used for consistency with
:func:`unpaired_n_per_arm`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import NormalDist

from evalloop.stats.compare import DEFAULT_ALPHA

__all__ = [
    "NoiseFloor",
    "noise_floor",
    "paired_mde",
    "paired_n",
    "unpaired_mde",
    "unpaired_n_per_arm",
    "unpaired_power",
]

#: C:19, "Sample size per arm ~ 16*p(1-p) / delta^2 (alpha = 0.05, 80% power)"; C:69.
_UNPAIRED_CONSTANT = 16.0

#: C:70, "(1.96*sqrt(d) + 0.84*sqrt(d - delta^2))^2 / delta^2".
_PAIRED_Z_ALPHA = 1.96
_PAIRED_Z_POWER = 0.84

# Bisection steps for the MDE inversions. Numerical, not methodological: the
# loop stops early once the bracket can no longer shrink in floating point.
_BISECTION_STEPS = 200


@dataclass(frozen=True, slots=True)
class NoiseFloor:
    """Mean and SD across k repeat runs (C3), in the units the scores were given in.

    ``sd`` is the **sample** SD (n - 1). C:100's own figures decide it: runs of
    76.1, 79.4, 77.8, 74.9 and 78.2 have "SD ... 1.8" only with n - 1; the
    population SD is 1.6. ``spread`` is max - min, the "they span 4.5 points"
    of C:100 and the "2.1-point spread" of C:118.
    """

    runs: int
    mean: float
    sd: float
    spread: float
    scores: tuple[float, ...]


def _check_rate(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a proportion in [0, 1], got {value}")


def unpaired_n_per_arm(p_from: float, p_to: float) -> float:
    """Items per arm to detect ``p_from`` -> ``p_to`` unpaired: 16*p(1-p)/delta^2 (C:19, C:69).

    p is the midpoint of the two rates (see the module docstring). Returned
    unrounded; round up when sizing a set.
    """
    _check_rate("p_from", p_from)
    _check_rate("p_to", p_to)
    delta = p_to - p_from
    if delta == 0.0:
        raise ValueError("p_from and p_to are equal: there is no effect to detect")
    p_bar = (p_from + p_to) / 2.0
    return _UNPAIRED_CONSTANT * p_bar * (1.0 - p_bar) / delta**2


def paired_n(discordant_share: float, delta: float) -> float:
    """Paired items to detect an effect ``delta`` at discordant share ``d`` (C:70).

    C:70: "Estimate d from a 50-item pilot." An effect cannot exceed the
    discordant share -- delta = (c - b)/n and d = (b + c)/n -- so |delta| > d is
    rejected as impossible rather than computed.
    """
    if not 0.0 < discordant_share <= 1.0:
        raise ValueError(f"discordant_share must be in (0, 1], got {discordant_share}")
    if not 0.0 < abs(delta) <= discordant_share:
        raise ValueError(
            f"delta must satisfy 0 < |delta| <= discordant_share = {discordant_share}, "
            f"got {delta}: an effect larger than the share of items that changed is impossible"
        )
    root = _PAIRED_Z_ALPHA * math.sqrt(discordant_share) + _PAIRED_Z_POWER * math.sqrt(
        discordant_share - delta**2
    )
    return root**2 / delta**2


def _smallest_detectable(
    n_needed: Callable[[float], float], largest: float, budget: float
) -> float:
    """The delta in (0, largest] at which ``n_needed(delta) == budget``.

    ``n_needed`` falls as delta grows, from infinity near 0, so bisection finds
    the boundary between "budget too small" and "budget enough".
    """
    low, high = 0.0, largest
    for _ in range(_BISECTION_STEPS):
        mid = (low + high) / 2.0
        if mid in (low, high):
            break
        if n_needed(mid) > budget:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def unpaired_mde(p_from: float, n_per_arm: float) -> float:
    """C:71: given n per arm, the smallest increase from ``p_from`` the 16 rule can detect."""
    _check_rate("p_from", p_from)
    largest = 1.0 - p_from
    if largest == 0.0:
        raise ValueError("p_from is 1.0: there is no room above it for an effect")
    floor = unpaired_n_per_arm(p_from, 1.0)
    if n_per_arm < floor:
        raise ValueError(
            f"n_per_arm = {n_per_arm} cannot detect any increase from {p_from}: "
            f"even {p_from} -> 1.0 needs {floor}"
        )
    return _smallest_detectable(
        lambda delta: unpaired_n_per_arm(p_from, p_from + delta), largest, n_per_arm
    )


def paired_mde(n: float, discordant_share: float) -> float:
    """C:71: given n paired items, the smallest effect C:70's formula can detect.

    C:84: "The MDE at 300 was about 5 points", at 10% discordance.
    """
    floor = paired_n(discordant_share, discordant_share)
    if n < floor:
        raise ValueError(
            f"n = {n} cannot detect any effect at discordant_share = {discordant_share}: "
            f"even the largest possible effect needs {floor}"
        )
    return _smallest_detectable(
        lambda delta: paired_n(discordant_share, delta), discordant_share, n
    )


def unpaired_power(
    p_from: float, p_to: float, n_per_arm: float, alpha: float = DEFAULT_ALPHA
) -> float:
    """The chance an unpaired comparison at ``n_per_arm`` detects ``p_from`` -> ``p_to``.

    C:79: "at n = 150 per arm, the chance of detecting a real 5-point gain was
    21%." Normal approximation, two-sided at ``alpha``, p the midpoint -- see the
    module docstring for why this formula and not another.
    """
    _check_rate("p_from", p_from)
    _check_rate("p_to", p_to)
    if n_per_arm <= 0:
        raise ValueError(f"n_per_arm must be positive, got {n_per_arm}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    delta = p_to - p_from
    if delta == 0.0:
        raise ValueError("p_from and p_to are equal: there is no effect to detect")
    p_bar = (p_from + p_to) / 2.0
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - alpha / 2.0)
    return normal.cdf(math.sqrt(n_per_arm * delta**2 / (2.0 * p_bar * (1.0 - p_bar))) - z_alpha)


def noise_floor(scores: Sequence[float]) -> NoiseFloor:
    """C3: mean and SD across repeat runs of one configuration.

    C3 asks for k >= 5 runs for a decision and k = 3 for daily iteration
    (C:103). That bar is ``C3_repeat_runs``'s ``requires: {runs: 5}``, so the
    planner holds it; this function only needs the two runs an SD needs.
    """
    if len(scores) < 2:
        raise ValueError(
            f"an SD needs at least two runs, got {len(scores)}; C3 asks for k >= 5 (C:94)"
        )
    values = tuple(scores)
    # fsum and sqrt are correctly rounded, so this is the same float on every
    # Python version. statistics.stdev is not: 3.12 changed how it takes the
    # square root, and its last digit moved.
    mean = math.fsum(values) / len(values)
    sd = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1))
    return NoiseFloor(len(values), mean, sd, max(values) - min(values), values)
