"""Intervals on a proportion: Wilson, Clopper-Pearson, the rule of three, and B5's margin.

Section C's first rule is the one every other module in this package serves:
"Every number is an estimate. Report its uncertainty" (C:6). For a pass rate
that means **Wilson** by default (C:28, C:35), **Clopper-Pearson** when an
auditor wants a conservative exact interval (C:140), and the **rule of three**
when nothing failed at all (C:20, C:132).

Why there is no ``wald_interval``
---------------------------------
C:35 is explicit: "Use Wilson, not the textbook +-1.96*sqrt(p(1-p)/n)". C:135
shows why -- for 198/200 the Wald interval is [97.6%, 100.4%], "which is
impossible". The Wald half-width does exist here, once, as
:func:`margin_of_error`, because B5 prescribes exactly that computation for a
different job: reading **someone else's** leaderboard, where p and n are all
you are given (B:169). It is not an interval on your own score, and its
docstring says so. A separate ``wald_interval`` would be a second, misusable
spelling of a formula the corpus tells you not to use.

Where the confidence level comes from
-------------------------------------
Interval estimators take ``confidence`` and derive z from it exactly
(``NormalDist().inv_cdf``), because the corpus states the level -- "a 95% CI on
every score" (C:25) -- and not a z. :func:`margin_of_error` is different: B:169
states its formula with the constant written in, "the 95% margin is +-1.96*SE",
so it uses 1.96 verbatim. Both reproduce every corpus figure; the split exists
so that each function is checkable against the line it implements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from evalloop._compat import StrEnum

__all__ = [
    "DEFAULT_CONFIDENCE",
    "Interval",
    "IntervalMethod",
    "clopper_pearson_interval",
    "margin_of_error",
    "rule_of_three_items_needed",
    "rule_of_three_upper_bound",
    "standard_error",
    "wilson_interval",
    "worst_case_margin",
]

#: C:25, "Report a 95% CI on every score"; B:203, "as the 95% CI".
DEFAULT_CONFIDENCE = 0.95

#: B:169, "the 95% margin is +-1.96*SE". Verbatim; see the module docstring.
_B5_Z = 1.96

#: C:20 and C:132: zero events in n -> the 95% upper bound is "approximately 3/n".
_RULE_OF_THREE = 3

# Numerical constants for the incomplete beta function below. They control
# floating-point convergence, not methodology: no corpus line is being
# interpreted by them, and changing them changes digits past the 12th.
_BETA_EPS = 1e-15
_BETA_FPMIN = 1e-300
_BETA_MAX_ITERATIONS = 10_000
_BISECTION_STEPS = 200


class IntervalMethod(StrEnum):
    """How an interval was computed. Rendered next to it, so a reader knows which rule applied."""

    wilson = "wilson"
    clopper_pearson = "clopper_pearson"
    percentile_bootstrap = "percentile_bootstrap"
    cluster_bootstrap = "cluster_bootstrap"


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with its interval. Proportions are in [0, 1], never percentages."""

    estimate: float
    lower: float
    upper: float
    confidence: float
    method: IntervalMethod


def _check_counts(successes: int, n: int) -> None:
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be in [0, n] = [0, {n}], got {successes}")


def _check_confidence(confidence: float) -> None:
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")


def _two_sided_z(confidence: float) -> float:
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)


def wilson_interval(
    successes: int, n: int, confidence: float = DEFAULT_CONFIDENCE
) -> Interval:
    """The Wilson score interval: the default interval on any pass rate (C1, C4).

    C:28: "It stays inside [0, 1], it's accurate at small n". At 0/n the lower
    bound is exactly 0 and at n/n the upper bound is exactly 1; those two are
    set rather than computed, because the arithmetic lands an ulp either side.
    """
    _check_counts(successes, n)
    _check_confidence(confidence)
    z = _two_sided_z(confidence)
    p = successes / n
    z2_n = z * z / n
    denominator = 1.0 + z2_n
    centre = p + z2_n / 2.0
    half_width = z * math.sqrt(p * (1.0 - p) / n + z2_n / (4.0 * n))
    lower = 0.0 if successes == 0 else (centre - half_width) / denominator
    upper = 1.0 if successes == n else (centre + half_width) / denominator
    return Interval(p, lower, upper, confidence, IntervalMethod.wilson)


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Lentz's evaluation of the incomplete-beta continued fraction."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _BETA_FPMIN:
        d = _BETA_FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _BETA_MAX_ITERATIONS + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _BETA_FPMIN:
            d = _BETA_FPMIN
        c = 1.0 + aa / c
        if abs(c) < _BETA_FPMIN:
            c = _BETA_FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _BETA_FPMIN:
            d = _BETA_FPMIN
        c = 1.0 + aa / c
        if abs(c) < _BETA_FPMIN:
            c = _BETA_FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _BETA_EPS:
            return h
    raise ArithmeticError(
        f"incomplete beta did not converge for a={a}, b={b}, x={x} "
        f"in {_BETA_MAX_ITERATIONS} iterations"
    )


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b). For a binomial, P(X >= k | n, p) = I_p(k, n - k + 1)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - _log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _solve_increasing(a: float, b: float, target: float) -> float:
    """The p in [0, 1] with I_p(a, b) == target, by bisection (I_p rises with p)."""
    lo, hi = 0.0, 1.0
    for _ in range(_BISECTION_STEPS):
        mid = (lo + hi) / 2.0
        if mid in (lo, hi):
            break
        if _regularized_incomplete_beta(a, b, mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def clopper_pearson_interval(
    successes: int, n: int, confidence: float = DEFAULT_CONFIDENCE
) -> Interval:
    """The exact (Clopper-Pearson) interval: for when an auditor wants it (C:140).

    C:140: "Use Clopper-Pearson when a regulator or auditor wants a conservative
    exact interval. Use Wilson otherwise." The bounds are the binomial tails
    inverted exactly: the lower bound L has P(X >= k | n, L) = alpha/2 and the
    upper bound U has P(X <= k | n, U) = alpha/2.

    **The rule of three is the one-sided version of this.** C:132's "95% upper
    bound ... approximately 3/n" is a one-sided bound, which is the upper end of
    the two-sided interval at ``confidence=0.90``. At 0/300 that is 0.99%, and
    the rule of three's 3/300 is 1.0% (C:138).
    """
    _check_counts(successes, n)
    _check_confidence(confidence)
    tail = (1.0 - confidence) / 2.0
    estimate = successes / n
    if successes == 0:
        lower = 0.0
    elif successes == n:
        lower = tail ** (1.0 / n)
    else:
        lower = _solve_increasing(successes, n - successes + 1, tail)
    if successes == n:
        upper = 1.0
    elif successes == 0:
        upper = 1.0 - tail ** (1.0 / n)
    else:
        upper = _solve_increasing(successes + 1, n - successes, 1.0 - tail)
    return Interval(estimate, lower, upper, confidence, IntervalMethod.clopper_pearson)


def rule_of_three_upper_bound(n: int) -> float:
    """Zero events in n -> the true rate is at most 3/n at 95% (C:20, C:132).

    C:138: "Never report '0 failures' without the upper bound. Say '0/300 -> <=
    1.0% at 95%.'" Only valid when nothing was observed; for any other count
    use :func:`wilson_interval` or :func:`clopper_pearson_interval`.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    return _RULE_OF_THREE / n


def rule_of_three_items_needed(max_rate: float) -> float:
    """Clean items needed before "<= max_rate" can be claimed at 95% (C:139).

    C:139: "Turn the rule of three around to size a safety eval. To claim <=
    0.1% you need 3,000 clean items". Returned unrounded; when sizing a set,
    round up.
    """
    if not 0.0 < max_rate <= 1.0:
        raise ValueError(f"max_rate must be in (0, 1], got {max_rate}")
    return _RULE_OF_THREE / max_rate


def standard_error(p: float, n: int) -> float:
    """SE = sqrt(p(1-p)/n) for a proportion (B:169)."""
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be in [0, 1], got {p}")
    return math.sqrt(p * (1.0 - p) / n)


def margin_of_error(p: float, n: int) -> float:
    """B5's 95% margin, +-1.96*SE, for reading a score someone else reported (B:169).

    **This is the Wald half-width, and it is not the interval on your own
    score.** B:169 prescribes it for "anyone's leaderboard or dashboard", where
    p and n are all you are given. For a score you measured, C:35 says "Use
    Wilson, not the textbook +-1.96*sqrt(p(1-p)/n)" -- see :func:`wilson_interval`.
    """
    return _B5_Z * standard_error(p, n)


def worst_case_margin(n: int) -> float:
    """B:22's "worst-case 95% margin on a percentage is about 100/sqrt(n) points".

    Returned as a proportion, like everything in this package: 1/sqrt(n) is the
    same figure as 100/sqrt(n) percentage points.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    return 1.0 / math.sqrt(n)
