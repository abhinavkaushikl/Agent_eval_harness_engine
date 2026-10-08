"""Bootstrap intervals -- item, paired and cluster -- and B7's design effect.

B6: "You resample items with replacement 1,000-10,000 times, recompute the
metric on each resample, and take the 2.5th and 97.5th percentiles as the 95%
CI. It works for any metric you can compute" (B:203). That generality is why
every function here takes a ``statistic``: macro-F1, nDCG, a ratio or rupees
per outcome are all one callable away.

Resample count
--------------
The default is **5,000**, B:211's figure for reporting: "Use 5,000 resamples
for reporting and 1,000 while iterating." B:37 gives the same 5,000 for the
paired difference. B:203's wider "1,000-10,000" is the range the deep dive then
narrows to those two values for two uses; EvalLoop reports, so it uses the
reporting one. Nothing enforces a minimum -- the corpus states practice, not a
validity floor, and a hard floor would be an interpretation.

Reproducibility
---------------
``seed`` is required and recorded in every result: B:213, "Fix the random seed
so the CI is reproducible in the review." Every draw is
``random.Random(seed).random()``, the one method whose output Python guarantees
not to change across versions; ``choices`` and ``randrange`` carry no such
promise, and the floor is 3.10 while the runtime may be newer.

Percentiles
-----------
The 2.5th and 97.5th percentiles (B:203) are taken with linear interpolation
between order statistics (Hyndman-Fan type 7, ``statistics.quantiles``'s
"inclusive" method). The corpus names percentiles without a definition; at
5,000 replicates the choice moves an endpoint by less than one replicate's gap.

What is not here
----------------
B:248 says "A ratio above about 1.5x means clustering matters, so report the
cluster CI." That is a **decision threshold** on two of this module's outputs,
not a statistic, and decision thresholds have no home in the registry yet --
the same question EL-015 asks for the grader's comparator constants. This
module produces both widths; it does not decide between them.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from evalloop.stats.proportions import DEFAULT_CONFIDENCE, IntervalMethod

__all__ = [
    "DEFAULT_RESAMPLES",
    "BootstrapInterval",
    "bootstrap_ci",
    "cluster_bootstrap_ci",
    "design_effect",
    "effective_sample_size",
    "paired_bootstrap_ci",
]

T = TypeVar("T")

#: B:211, "Use 5,000 resamples for reporting"; B:37, "draw 5,000 resamples of item IDs".
DEFAULT_RESAMPLES = 5_000


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """A percentile bootstrap interval, with everything needed to reproduce it.

    ``units`` is how many things were resampled: items for the item and paired
    bootstraps, clusters for the cluster bootstrap. That is the honest sample
    size -- B:268, "The contracts are what we sampled, so the interval has to be
    computed over contracts."
    """

    estimate: float
    lower: float
    upper: float
    confidence: float
    method: IntervalMethod
    resamples: int
    seed: int
    units: int


def _check(confidence: float, resamples: int) -> None:
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if resamples < 1:
        raise ValueError(f"resamples must be at least 1, got {resamples}")


def _percentile(ordered: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics (type 7). ``ordered`` is sorted."""
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def _draw(rng: random.Random, units: int) -> list[int]:
    """``units`` indices in [0, units), with replacement, from ``random()`` alone."""
    return [int(rng.random() * units) for _ in range(units)]


def _interval(
    estimate: float,
    replicates: list[float],
    confidence: float,
    method: IntervalMethod,
    resamples: int,
    seed: int,
    units: int,
) -> BootstrapInterval:
    replicates.sort()
    tail = (1.0 - confidence) / 2.0
    return BootstrapInterval(
        estimate,
        _percentile(replicates, tail),
        _percentile(replicates, 1.0 - tail),
        confidence,
        method,
        resamples,
        seed,
        units,
    )


def bootstrap_ci(
    items: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    *,
    seed: int,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
) -> BootstrapInterval:
    """B6: resample items with replacement, recompute ``statistic``, take percentiles.

    For a comparison of two systems, prefer :func:`paired_bootstrap_ci`, or pass
    items that carry both systems' outputs and a statistic that returns the
    difference -- B:210, "resample once and compute both systems on the same
    resample." Grouped items belong in :func:`cluster_bootstrap_ci` (B:209).
    """
    _check(confidence, resamples)
    if not items:
        raise ValueError("a bootstrap needs at least one item")
    rng = random.Random(seed)
    units = len(items)
    replicates = [
        statistic([items[i] for i in _draw(rng, units)]) for _ in range(resamples)
    ]
    return _interval(
        statistic(items),
        replicates,
        confidence,
        IntervalMethod.percentile_bootstrap,
        resamples,
        seed,
        units,
    )


def paired_bootstrap_ci(
    baseline: Sequence[float],
    candidate: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    seed: int,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
) -> BootstrapInterval:
    """B1: the interval on statistic(candidate) - statistic(baseline), resampling item pairs.

    B:37: "draw 5,000 resamples of item IDs, compute score_B - score_A on each,
    and take the 2.5th and 97.5th percentiles." Each resample draws item
    indices once and scores both systems on them, so the interval is on the
    paired difference itself (B:29).
    """
    if len(baseline) != len(candidate):
        raise ValueError(
            f"paired data needs one baseline and one candidate value per item; "
            f"got {len(baseline)} and {len(candidate)}"
        )
    pairs = list(zip(baseline, candidate))

    def difference(sample: Sequence[tuple[float, float]]) -> float:
        return statistic([new for _, new in sample]) - statistic([old for old, _ in sample])

    return bootstrap_ci(
        pairs, difference, seed=seed, confidence=confidence, resamples=resamples
    )


def cluster_bootstrap_ci(
    clusters: Mapping[str, Sequence[T]],
    statistic: Callable[[Sequence[T]], float],
    *,
    seed: int,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
) -> BootstrapInterval:
    """B7: resample whole clusters, keeping each cluster's items together.

    B:247: "Resample cluster IDs with replacement and include all items from
    each chosen cluster." ``clusters`` maps a cluster ID (document,
    conversation, customer, template -- B:246) to its items. Clusters are
    visited in sorted-ID order, so the result does not depend on the order the
    mapping was built in. With one item per cluster this is exactly
    :func:`bootstrap_ci`, draw for draw.
    """
    _check(confidence, resamples)
    if not clusters:
        raise ValueError("a cluster bootstrap needs at least one cluster")
    ordered = sorted(clusters)
    empty = [cluster_id for cluster_id in ordered if not clusters[cluster_id]]
    if empty:
        raise ValueError(f"clusters with no items: {', '.join(empty)}")
    groups = [clusters[cluster_id] for cluster_id in ordered]
    rng = random.Random(seed)
    units = len(groups)
    replicates = [
        statistic([item for i in _draw(rng, units) for item in groups[i]])
        for _ in range(resamples)
    ]
    everything = [item for group in groups for item in group]
    return _interval(
        statistic(everything),
        replicates,
        confidence,
        IntervalMethod.cluster_bootstrap,
        resamples,
        seed,
        units,
    )


def design_effect(items_per_cluster: float, intra_cluster_correlation: float) -> float:
    """1 + (m - 1)*rho: how much clustering inflates the variance (B:243).

    An item-level interval understates the width by about sqrt(design effect).
    B:257 is that prediction checked: at m = 10 and rho = 0.4 the design effect
    is 4.6, sqrt(4.6) is 2.1, and an item-level +-2.4 became a cluster +-5.1.
    """
    if items_per_cluster < 1:
        raise ValueError(f"items_per_cluster must be at least 1, got {items_per_cluster}")
    if not -1.0 <= intra_cluster_correlation <= 1.0:
        raise ValueError(
            f"intra_cluster_correlation must be in [-1, 1], got {intra_cluster_correlation}"
        )
    effect = 1.0 + (items_per_cluster - 1.0) * intra_cluster_correlation
    if effect <= 0.0:
        raise ValueError(
            f"m = {items_per_cluster} and rho = {intra_cluster_correlation} give a "
            f"design effect of {effect}, which is not a variance ratio"
        )
    return effect


def effective_sample_size(
    n: float, items_per_cluster: float, intra_cluster_correlation: float
) -> float:
    """B:243: "effective n ~ n / (1 + (m - 1)*rho)". 1,000 at m = 10, rho = 0.4 is 217."""
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    return n / design_effect(items_per_cluster, intra_cluster_correlation)
