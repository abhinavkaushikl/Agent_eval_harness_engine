"""Properties of ``evalloop.stats`` that the corpus gives no raw data to check.

The corpus prints results, not datasets: B:257's cluster CI of +-5.1 comes
from 1,000 questions nobody published. So the resampling and permutation code
cannot be checked against a worked example, and is checked here instead by
what must be true of it -- by definition, by construction, or by a bar the
corpus states. No assertion below compares against a number chosen for the
test; where a corpus line supplies the bar, it is cited.

``pytest.approx(..., rel=...)`` appears only where floating-point arithmetic
is being compared with exact arithmetic. It is a tolerance on rounding error,
not a methodology threshold.

Resample and shuffle counts of 1,000 are B:211's "1,000 while iterating",
used to keep the suite fast; the package default stays the reporting 5,000.
"""

from __future__ import annotations

import math
import random
from statistics import fmean, median

import pytest

from evalloop.stats import (
    DEFAULT_ALPHA,
    DEFAULT_CONFIDENCE,
    DEFAULT_SHUFFLES,
    IntervalMethod,
    McNemarMethod,
    bootstrap_ci,
    chi_square_1df_sf,
    clopper_pearson_interval,
    cluster_bootstrap_ci,
    design_effect,
    effective_sample_size,
    familywise_error_rate,
    margin_of_error,
    mcnemar,
    noise_floor,
    paired_bootstrap_ci,
    paired_mde,
    paired_n,
    paired_permutation_test,
    permutation_p_value,
    rule_of_three_items_needed,
    rule_of_three_upper_bound,
    standard_error,
    unpaired_mde,
    unpaired_n_per_arm,
    unpaired_power,
    wilson_interval,
    worst_case_margin,
)

ITERATING = 1_000  # B:211, "1,000 while iterating"

# -- proportions ----------------------------------------------------------------


def test_wilson_stays_inside_the_unit_interval_at_the_edges() -> None:
    """C:35 -- Wilson replaces Wald because Wald leaves [0, 1]; at 0/n and n/n Wilson must not."""
    for n in (1, 10, 300):
        none = wilson_interval(0, n)
        every = wilson_interval(n, n)
        assert none.lower == 0.0 and 0.0 < none.upper < 1.0
        assert every.upper == 1.0 and 0.0 < every.lower < 1.0


@pytest.mark.parametrize("n", [1, 2, 5, 13, 100, 1_000, 1_000_000])
def test_every_interval_brackets_its_estimate_inside_the_unit_interval(n: int) -> None:
    """C:28 -- Wilson "stays inside [0, 1]"; so must the exact interval, at every count."""
    counts = sorted({0, 1, 2, n // 3, n // 2, n - 2, n - 1, n} & set(range(n + 1)))
    for successes in counts:
        for interval in (wilson_interval(successes, n), clopper_pearson_interval(successes, n)):
            assert 0.0 <= interval.lower <= interval.estimate <= interval.upper <= 1.0, interval


def test_wilson_is_symmetric_under_relabelling() -> None:
    """Counting failures instead of passes mirrors the interval."""
    passes = wilson_interval(82, 100)
    failures = wilson_interval(18, 100)
    assert passes.lower == pytest.approx(1 - failures.upper, rel=1e-12)
    assert passes.upper == pytest.approx(1 - failures.lower, rel=1e-12)


def test_clopper_pearson_bounds_are_exactly_the_binomial_tails() -> None:
    """C:140 -- "a conservative exact interval": at each bound, the far tail is exactly alpha/2."""
    successes, n = 82, 100
    interval = clopper_pearson_interval(successes, n)
    tail = (1 - DEFAULT_CONFIDENCE) / 2

    def pmf(k: int, p: float) -> float:
        return math.comb(n, k) * p**k * (1 - p) ** (n - k)

    at_lower = sum(pmf(k, interval.lower) for k in range(successes, n + 1))
    at_upper = sum(pmf(k, interval.upper) for k in range(successes + 1))
    assert at_lower == pytest.approx(tail, rel=1e-9)
    assert at_upper == pytest.approx(tail, rel=1e-9)


def test_clopper_pearson_at_zero_and_at_n() -> None:
    """C:132 -- zero events: the lower bound is 0 and P(X = 0) at the upper bound is alpha/2."""
    tail = (1 - DEFAULT_CONFIDENCE) / 2
    none = clopper_pearson_interval(0, 300)
    every = clopper_pearson_interval(300, 300)
    assert none.lower == 0.0
    assert (1 - none.upper) ** 300 == pytest.approx(tail, rel=1e-9)
    assert every.upper == 1.0
    assert every.lower**300 == pytest.approx(tail, rel=1e-9)


def test_the_b5_margin_is_its_printed_constant_times_se() -> None:
    """B:169 -- "the 95% margin is +-1.96*SE", with 1.96 as printed."""
    assert margin_of_error(0.85, 500) == 1.96 * standard_error(0.85, 500)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: wilson_interval(1, 0), "n must be at least 1"),
        (lambda: wilson_interval(5, 3), "successes must be in"),
        (lambda: wilson_interval(-1, 3), "successes must be in"),
        (lambda: wilson_interval(1, 3, confidence=1.0), "confidence must be in"),
        (lambda: clopper_pearson_interval(1, 3, confidence=0.0), "confidence must be in"),
        (lambda: rule_of_three_upper_bound(0), "n must be at least 1"),
        (lambda: rule_of_three_items_needed(0.0), "max_rate must be in"),
        (lambda: rule_of_three_items_needed(1.5), "max_rate must be in"),
        (lambda: standard_error(1.2, 10), "p must be in"),
        (lambda: standard_error(0.5, 0), "n must be at least 1"),
        (lambda: worst_case_margin(0), "n must be at least 1"),
    ],
)
def test_proportion_inputs_are_checked(call: object, match: str) -> None:
    assert callable(call)
    with pytest.raises(ValueError, match=match):
        call()


# -- McNemar --------------------------------------------------------------------


def test_mcnemar_switches_branch_exactly_at_25_pairs() -> None:
    """B:107 -- "b + c >= 25" for chi^2: 24 pairs is exact, 25 is chi^2."""
    assert mcnemar(12, 12).method is McNemarMethod.exact_binomial
    assert mcnemar(12, 13).method is McNemarMethod.chi_square_continuity_corrected


def test_a_tie_is_no_evidence_in_either_branch() -> None:
    """B:100 -- b == c says nothing about a difference, so p is 1 on both sides of B:107's switch.

    B:100's formula read literally gives (0 - 1)^2 / (b + c) > 0 for a tie; the
    module clamps the correction at zero, and this is the test that holds it.
    """
    exact = mcnemar(5, 5)
    approximate = mcnemar(20, 20)
    assert exact.method is McNemarMethod.exact_binomial and exact.p_value == 1.0
    assert approximate.method is McNemarMethod.chi_square_continuity_corrected
    assert approximate.chi_square == 0.0 and approximate.p_value == 1.0


def test_mcnemar_evidence_grows_with_the_imbalance() -> None:
    """At a fixed number of discordant pairs, a more lopsided split is never weaker evidence."""
    for total in (14, 40, 41):
        p_values = [mcnemar(total - c, c).p_value for c in range((total + 1) // 2, total + 1)]
        assert p_values == sorted(p_values, reverse=True)


def test_mcnemar_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        mcnemar(-1, 4)


def test_chi_square_survival_function_bounds() -> None:
    assert chi_square_1df_sf(0.0) == 1.0
    with pytest.raises(ValueError, match="cannot be negative"):
        chi_square_1df_sf(-0.1)


# -- the paired permutation test -------------------------------------------------

BASELINE = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
CANDIDATE = [1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0]


def test_identical_systems_give_p_of_one() -> None:
    """C:201 -- every shuffle is "at least as large" as an observed difference of zero."""
    result = paired_permutation_test(BASELINE, BASELINE, fmean, seed=11, shuffles=ITERATING)
    assert result.observed == 0.0
    assert result.extreme == ITERATING
    assert result.p_value == 1.0


def test_the_permutation_test_is_two_sided() -> None:
    """C:201 -- swapping which system is the baseline negates the difference and leaves p alone."""
    forward = paired_permutation_test(BASELINE, CANDIDATE, fmean, seed=3, shuffles=ITERATING)
    backward = paired_permutation_test(CANDIDATE, BASELINE, fmean, seed=3, shuffles=ITERATING)
    assert backward.observed == -forward.observed
    assert backward.extreme == forward.extreme


def test_label_swapping_is_sign_flipping_for_the_mean() -> None:
    """C:201, C:208 -- for the mean, swapping an item's labels is flipping the sign of its difference.

    The reference below is C:208 written out with the same random draws, in
    exact integer arithmetic: these values are 0 and 1, so comparing means is
    comparing integer sums.
    """
    seed = 7
    result = paired_permutation_test(BASELINE, CANDIDATE, fmean, seed=seed, shuffles=ITERATING)
    differences = [int(new - old) for old, new in zip(BASELINE, CANDIDATE)]
    observed = abs(sum(differences))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(ITERATING):
        flipped = [-d if rng.random() < 0.5 else d for d in differences]
        if abs(sum(flipped)) >= observed:
            extreme += 1
    assert result.extreme == extreme


def test_the_statistic_is_the_callers_choice() -> None:
    """C:207 -- "Use the median or a 10% trimmed mean for heavy tails": any statistic is accepted."""
    latency_old = [110.0, 95.0, 102.0, 400.0, 99.0, 105.0, 101.0, 97.0, 650.0, 103.0]
    latency_new = [100.0, 90.0, 99.0, 380.0, 96.0, 101.0, 95.0, 93.0, 700.0, 98.0]
    result = paired_permutation_test(latency_old, latency_new, median, seed=13, shuffles=ITERATING)
    assert result.observed == median(latency_new) - median(latency_old)
    assert 0.0 < result.p_value <= 1.0
    assert result == paired_permutation_test(
        latency_old, latency_new, median, seed=13, shuffles=ITERATING
    )


def test_an_effect_on_every_item_reaches_the_floor() -> None:
    """C:209 -- when no shuffle is as extreme, p is 1/shuffles and the result says it is a floor.

    Thirty items all improved by one: a shuffle matches that only if it swaps
    all thirty or none, which happens about twice in a billion.
    """
    result = paired_permutation_test([0.0] * 30, [1.0] * 30, fmean, seed=5)
    assert result.shuffles == DEFAULT_SHUFFLES
    assert result.at_floor
    assert result.p_value == 1 / DEFAULT_SHUFFLES


def test_the_permutation_result_carries_its_seed() -> None:
    """B:213 -- "Fix the random seed so the CI is reproducible in the review": same for a p-value."""
    first = paired_permutation_test(BASELINE, CANDIDATE, fmean, seed=2024, shuffles=ITERATING)
    assert first.seed == 2024
    assert first == paired_permutation_test(BASELINE, CANDIDATE, fmean, seed=2024, shuffles=ITERATING)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: paired_permutation_test([1.0], [1.0, 2.0], fmean, seed=0), "one baseline and one candidate"),
        (lambda: paired_permutation_test([], [], fmean, seed=0), "at least one item"),
        (lambda: paired_permutation_test([1.0], [2.0], fmean, seed=0, shuffles=0), "shuffles must be"),
        (lambda: permutation_p_value(5, 4), "extreme must be in"),
        (lambda: permutation_p_value(-1, 4), "extreme must be in"),
        (lambda: permutation_p_value(0, 0), "shuffles must be"),
        (lambda: familywise_error_rate(0), "tests must be at least 1"),
        (lambda: familywise_error_rate(3, alpha=1.0), "alpha must be in"),
    ],
)
def test_comparison_inputs_are_checked(call: object, match: str) -> None:
    assert callable(call)
    with pytest.raises(ValueError, match=match):
        call()


def test_one_check_has_exactly_alpha_false_alarm_odds() -> None:
    """C:21 -- 1 - 0.95^k at k = 1 is the per-test alpha."""
    assert familywise_error_rate(1) == pytest.approx(DEFAULT_ALPHA, rel=1e-12)


# -- the bootstraps -----------------------------------------------------------------

SCORES = [float((i * 37) % 11) for i in range(60)]


def test_the_bootstrap_is_reproducible_from_its_seed() -> None:
    """B:213 -- same seed, same interval, and the seed travels with it."""
    first = bootstrap_ci(SCORES, fmean, seed=2024, resamples=ITERATING)
    assert first == bootstrap_ci(SCORES, fmean, seed=2024, resamples=ITERATING)
    assert (first.seed, first.resamples, first.units) == (2024, ITERATING, len(SCORES))
    assert first.method is IntervalMethod.percentile_bootstrap


def test_constant_data_has_no_width() -> None:
    interval = bootstrap_ci([0.5] * 40, fmean, seed=1, resamples=ITERATING)
    assert interval.lower == interval.upper == interval.estimate == 0.5


def test_pairing_cancels_item_difficulty() -> None:
    """B:37 -- score_B - score_A on one resample: a uniform gain has a paired interval of zero width.

    32 items, so every mean is exact in floating point. Unpaired, the same
    candidate scores carry the spread of the items' difficulty.
    """
    baseline = [float(i % 4) for i in range(32)]
    candidate = [score + 0.25 for score in baseline]
    paired = paired_bootstrap_ci(baseline, candidate, fmean, seed=17, resamples=ITERATING)
    assert paired.lower == paired.upper == paired.estimate == 0.25
    alone = bootstrap_ci(candidate, fmean, seed=17, resamples=ITERATING)
    assert alone.upper - alone.lower > 0.0


def test_one_item_clusters_are_the_item_bootstrap() -> None:
    """B:247 -- resampling clusters of one item is resampling items, draw for draw."""
    items = bootstrap_ci(SCORES, fmean, seed=99, resamples=ITERATING)
    clusters = cluster_bootstrap_ci(
        {f"{i:03d}": [score] for i, score in enumerate(SCORES)}, fmean, seed=99, resamples=ITERATING
    )
    assert (clusters.estimate, clusters.lower, clusters.upper) == (items.estimate, items.lower, items.upper)
    assert clusters.method is IntervalMethod.cluster_bootstrap


def test_the_order_clusters_were_built_in_does_not_matter() -> None:
    groups = {f"contract-{i:02d}": [float(i % 3), float(i % 5)] for i in range(12)}
    backwards = dict(reversed(list(groups.items())))
    assert cluster_bootstrap_ci(groups, fmean, seed=4, resamples=ITERATING) == cluster_bootstrap_ci(
        backwards, fmean, seed=4, resamples=ITERATING
    )


def test_perfectly_clustered_data_clears_the_bar_where_clustering_matters() -> None:
    """B:243, B:248 -- at rho = 1 the cluster interval is wider than "about 1.5x" the item one.

    20 clusters of 10 identical items: B:243's design effect is 1 + 9 * 1 = 10.
    The assertion is B:248's bar, not a predicted ratio.
    """
    clusters = {f"c{i:02d}": [float(i % 2)] * 10 for i in range(20)}
    items = [score for group in clusters.values() for score in group]
    item_level = bootstrap_ci(items, fmean, seed=8, resamples=ITERATING)
    cluster_level = cluster_bootstrap_ci(clusters, fmean, seed=8, resamples=ITERATING)
    assert cluster_level.units == 20 and item_level.units == 200
    ratio = (cluster_level.upper - cluster_level.lower) / (item_level.upper - item_level.lower)
    assert ratio > 1.5


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: bootstrap_ci([], fmean, seed=0), "at least one item"),
        (lambda: bootstrap_ci([1.0], fmean, seed=0, resamples=0), "resamples must be"),
        (lambda: bootstrap_ci([1.0], fmean, seed=0, confidence=1.0), "confidence must be in"),
        (lambda: paired_bootstrap_ci([1.0], [], fmean, seed=0), "one baseline and one candidate"),
        (lambda: cluster_bootstrap_ci({}, fmean, seed=0), "at least one cluster"),
        (lambda: cluster_bootstrap_ci({"a": [1.0], "b": []}, fmean, seed=0), "clusters with no items: b"),
        (lambda: design_effect(0, 0.4), "items_per_cluster must be"),
        (lambda: design_effect(10, 1.5), "intra_cluster_correlation must be"),
        (lambda: design_effect(3, -0.6), "not a variance ratio"),
        (lambda: effective_sample_size(0, 10, 0.4), "n must be at least 1"),
    ],
)
def test_resampling_inputs_are_checked(call: object, match: str) -> None:
    assert callable(call)
    with pytest.raises(ValueError, match=match):
        call()


# -- power and the noise floor ----------------------------------------------------


def test_the_16_rule_buys_the_power_it_promises() -> None:
    """C:19 -- "(alpha = 0.05, 80% power)": at the 16 rule's n, the power is at least 80%.

    16 rounds 2 * (1.96 + 0.84)^2 = 15.68 up, so the rule slightly over-delivers.
    """
    for p_from, p_to in ((0.80, 0.85), (0.50, 0.60), (0.90, 0.92), (0.30, 0.25)):
        assert unpaired_power(p_from, p_to, unpaired_n_per_arm(p_from, p_to)) >= 0.80


def test_power_rises_with_n() -> None:
    powers = [unpaired_power(0.80, 0.85, n) for n in (50, 150, 500, 1_500)]
    assert powers == sorted(powers) and len(set(powers)) == len(powers)


def test_the_mde_is_the_effect_the_budget_buys() -> None:
    """C:62 -- "given your budget of n, compute the minimum detectable effect": it inverts n."""
    unpaired = unpaired_mde(0.80, 500.0)
    assert unpaired_n_per_arm(0.80, 0.80 + unpaired) == pytest.approx(500.0, rel=1e-9)
    paired = paired_mde(500.0, 0.12)
    assert paired_n(0.12, paired) == pytest.approx(500.0, rel=1e-9)


def test_unpaired_n_does_not_depend_on_direction() -> None:
    assert unpaired_n_per_arm(0.80, 0.85) == unpaired_n_per_arm(0.85, 0.80)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: unpaired_n_per_arm(0.8, 0.8), "no effect to detect"),
        (lambda: unpaired_n_per_arm(1.2, 0.5), "p_from must be a proportion"),
        (lambda: paired_n(0.05, 0.10), "impossible"),
        (lambda: paired_n(0.0, 0.01), "discordant_share must be in"),
        (lambda: paired_mde(2.0, 0.10), "cannot detect any effect"),
        (lambda: unpaired_mde(0.80, 1.0), "cannot detect any increase"),
        (lambda: unpaired_mde(1.0, 500.0), "no room above it"),
        (lambda: unpaired_power(0.8, 0.85, 0), "n_per_arm must be positive"),
        (lambda: unpaired_power(0.8, 0.85, 100, alpha=0.0), "alpha must be in"),
        (lambda: unpaired_power(0.8, 0.8, 100), "no effect to detect"),
    ],
)
def test_power_inputs_are_checked(call: object, match: str) -> None:
    """C:70 -- an effect larger than the discordant share is impossible, not merely unlikely."""
    assert callable(call)
    with pytest.raises(ValueError, match=match):
        call()


def test_the_noise_floor_keeps_the_per_run_numbers() -> None:
    """C:97, C:104 -- the run-to-run SD is the noise floor, reported with "the per-run numbers"."""
    floor = noise_floor([84.1, 82.0, 83.5])
    assert floor.scores == (84.1, 82.0, 83.5)
    assert floor.sd == pytest.approx(math.sqrt(sum((s - floor.mean) ** 2 for s in floor.scores) / 2), rel=1e-12)


def test_the_noise_floor_needs_two_runs_and_leaves_five_to_the_planner() -> None:
    """C:94, C:103 -- k >= 5 for a decision is C3's readiness bar; an SD needs only two runs."""
    assert noise_floor([77.0, 78.0]).runs == 2
    with pytest.raises(ValueError, match="at least two runs"):
        noise_floor([77.0])
