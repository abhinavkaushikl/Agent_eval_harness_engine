"""Every worked example in sections B and C that ``evalloop.stats`` can reproduce.

EL-203's "Done when" is "matches the corpus worked examples", so these tests
are the specification. Each one names its line as ``<section>:<line>``, every
such line is in ``tests/stats_citations.CITES``, and the sweep at the bottom
checks that each cited fragment is still on that line -- so a figure cannot
move in the corpus without a test naming where it went.

How a figure is compared
------------------------
``reads_as(value, "73.3")`` rounds the computed value half-up to the decimal
places the corpus printed and compares for equality. The figures are copied as
printed, with only ``%``, ``±`` and thousands commas removed. Rates come out of
the package as proportions, so the tests multiply by 100 where the corpus
prints percentages or points.

Three figures are printed as approximate -- "~ 920", "~ 375", "~ 1,960" -- and
no single rounding rule produces all three from their formulas (924, 373.96 and
1,957.6). Those are tested twice instead: the implementation against the
formula as the corpus prints it, and the corpus's own n fed back through the
inverse, which must recover the corpus's stated effect at the precision it
states the effect.

``pytest.approx(..., rel=1e-12)`` appears only where two floating-point
expressions of the same formula are compared. It is arithmetic, not a bar.

Beyond the ticket's 21 rows
---------------------------
Reading B and C for the ticket turned up six more reproducible figures, tested
here too: B:116 (McNemar 5.49, p ~ 0.019), B:108 (the chi^2 critical values),
C:84 (paired MDE at 300 is "about 5 points"), C:100's span and C:118's spread,
and B:261/B:262 (+-1.5 at 2,000 turns, +-5.6 at 250 conversations).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

import tests.test_stats_properties as stats_properties
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.stats import (
    CHI_SQUARE_MIN_DISCORDANT,
    DEFAULT_ALPHA,
    DEFAULT_CONFIDENCE,
    DEFAULT_RESAMPLES,
    DEFAULT_SHUFFLES,
    McNemarMethod,
    PermutationResult,
    chi_square_1df_sf,
    clopper_pearson_interval,
    design_effect,
    effective_sample_size,
    familywise_error_rate,
    margin_of_error,
    mcnemar,
    noise_floor,
    paired_mde,
    paired_n,
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
from tests.conftest import SECTION_FILES, require_corpus_files
from tests.stats_citations import CITES, citations_in, reads_as

# -- the defaults, each with its line --------------------------------------


def test_every_default_is_the_corpus_figure() -> None:
    """C:25, C:19, B:37, B:203, B:211, C:209, B:107 -- the package's defaults, against their lines."""
    assert DEFAULT_CONFIDENCE == 0.95  # C:25, "A 95% CI ON EVERY SCORE"
    assert DEFAULT_ALPHA == 0.05  # C:19, "(alpha = 0.05, 80% power)"
    assert DEFAULT_RESAMPLES == 5_000  # B:211, "Use 5,000 resamples for reporting"
    assert 1_000 <= DEFAULT_RESAMPLES <= 10_000  # B:203, "1,000-10,000 times"
    assert DEFAULT_SHUFFLES == 10_000  # C:209, "Use 10,000 shuffles."
    assert CHI_SQUARE_MIN_DISCORDANT == 25  # B:107, "b + c >= 25"


def test_the_planner_and_mcnemar_read_the_same_bound() -> None:
    """B:107 -- B3's readiness bar and mcnemar()'s branch switch are one number from one line.

    The registry holds it as ``B3_mcnemar.requires``; this package holds it as
    the point where chi^2 takes over from the exact test. If either moves alone,
    the plan and the statistic disagree about the same 25 pairs.
    """
    (b3,) = [record for record in load_records(RECORDS_DIR) if record.id == "B3_mcnemar"]
    assert b3.requires["discordant_pairs"] == CHI_SQUARE_MIN_DISCORDANT


# -- C1 and C4: an interval on every score ---------------------------------


def test_wilson_on_82_of_100() -> None:
    """C:31 -- "82 of 100 has a Wilson 95% CI of [73.3%, 88.3%]"."""
    interval = wilson_interval(82, 100)
    assert reads_as(interval.lower * 100, "73.3")
    assert reads_as(interval.upper * 100, "88.3")


def test_wilson_on_198_of_200() -> None:
    """C:135 -- "Wilson for 198/200 gives [96.4%, 99.7%]"."""
    interval = wilson_interval(198, 200)
    assert reads_as(interval.lower * 100, "96.4")
    assert reads_as(interval.upper * 100, "99.7")


def test_wilson_on_both_kyc_segments() -> None:
    """C:49 -- 47/50 and 43/50: "Wilson CIs were [83.8, 97.9] and [73.8, 93.0]"."""
    salaried = wilson_interval(47, 50)
    self_employed = wilson_interval(43, 50)
    assert reads_as(salaried.lower * 100, "83.8") and reads_as(salaried.upper * 100, "97.9")
    assert reads_as(self_employed.lower * 100, "73.8") and reads_as(self_employed.upper * 100, "93.0")


def test_wald_on_198_of_200_is_impossible_and_wilson_is_not() -> None:
    """C:35, C:135, C:147, B:169 -- Wald gives [97.6%, 100.4%], the dashboard's "99.0% +- 1.4".

    The Wald half-width is B:169's margin, which is why there is no separate
    Wald function: the one place the formula belongs is reading someone else's
    numbers. On your own score it produces an upper bound above 100%.
    """
    p = 198 / 200
    half_width = margin_of_error(p, 200)
    assert reads_as(half_width * 100, "1.4")
    assert reads_as((p - half_width) * 100, "97.6")
    assert reads_as((p + half_width) * 100, "100.4")
    assert p + half_width > 1.0
    assert wilson_interval(198, 200).upper <= 1.0


def test_rule_of_three_on_zero_in_300() -> None:
    """C:20, C:132, C:138, C:159 -- "0/300 -> <= 1.0% at 95%"; C:159 says "could still be up to 1%"."""
    bound = rule_of_three_upper_bound(300) * 100
    assert reads_as(bound, "1.0")  # C:138
    assert reads_as(bound, "1")  # C:159


def test_rule_of_three_sizes_a_safety_eval() -> None:
    """C:139, C:159 -- "To claim <= 0.1% you need 3,000 clean items, and to claim <= 0.01% you need 30,000"."""
    assert reads_as(rule_of_three_items_needed(0.001), "3000")
    assert reads_as(rule_of_three_items_needed(0.0001), "30000")


def test_clopper_pearson_one_sided_bound_is_the_rule_of_three() -> None:
    """C:132, C:138, C:140 -- the exact one-sided 95% bound at 0/300 reads as the rule's 1.0%.

    C:132 calls 3/n "approximately" the 95% upper bound. The exact bound it
    approximates is one-sided, which is the upper end of the two-sided 90%
    Clopper-Pearson interval: 1 - 0.05^(1/300) = 0.99%.
    """
    exact = clopper_pearson_interval(0, 300, confidence=0.90)
    assert exact.lower == 0.0
    assert reads_as(exact.upper * 100, "1.0")
    assert exact.upper <= rule_of_three_upper_bound(300)


# -- C2: power, sample size, minimum detectable effect --------------------


def test_unpaired_n_for_80_to_85() -> None:
    """C:19, C:65, C:69 -- "To detect 80% -> 85% you need ~ 920 items per arm" unpaired.

    Approximate, so a round trip: C:69's formula with p as the midpoint gives
    924, and the corpus's 920 fed back through the inverse recovers 5 points.
    """
    p_bar = (0.80 + 0.85) / 2
    as_printed = 16 * p_bar * (1 - p_bar) / 0.05**2
    assert unpaired_n_per_arm(0.80, 0.85) == pytest.approx(as_printed, rel=1e-12)
    assert reads_as(unpaired_mde(0.80, 920) * 100, "5")


def test_paired_n_at_twelve_percent_discordant() -> None:
    """C:65, C:70 -- "With a paired design where about 12% of items flip ... ~ 375"."""
    as_printed = (1.96 * math.sqrt(0.12) + 0.84 * math.sqrt(0.12 - 0.05**2)) ** 2 / 0.05**2
    assert paired_n(0.12, 0.05) == pytest.approx(as_printed, rel=1e-12)
    assert reads_as(paired_mde(375, 0.12) * 100, "5")


def test_paired_n_for_two_points_at_ten_percent() -> None:
    """C:70, C:84 -- "Detecting 2 points with 10% discordance needs ~ 1,960 paired items"."""
    as_printed = (1.96 * math.sqrt(0.10) + 0.84 * math.sqrt(0.10 - 0.02**2)) ** 2 / 0.02**2
    assert paired_n(0.10, 0.02) == pytest.approx(as_printed, rel=1e-12)
    assert reads_as(paired_mde(1960, 0.10) * 100, "2")


def test_paired_mde_on_a_300_item_budget() -> None:
    """C:84 -- "The MDE at 300 was about 5 points", at the same 10% discordance."""
    assert reads_as(paired_mde(300, 0.10) * 100, "5")


def test_power_at_150_per_arm() -> None:
    """C:79 -- "at n = 150 per arm, the chance of detecting a real 5-point gain was 21%"."""
    assert reads_as(unpaired_power(0.80, 0.85, 150) * 100, "21")


# -- C3: the noise floor -----------------------------------------------------


def test_noise_floor_of_five_runs() -> None:
    """C:100 -- 76.1, 79.4, 77.8, 74.9, 78.2: "The mean is 77.3 and the SD is 1.8", spanning 4.5."""
    floor = noise_floor([76.1, 79.4, 77.8, 74.9, 78.2])
    assert floor.runs == 5
    assert reads_as(floor.mean, "77.3")
    assert reads_as(floor.sd, "1.8")
    assert reads_as(floor.spread, "4.5")


def test_spread_of_three_runs_at_temperature_zero() -> None:
    """C:118 -- "84.1, 82.0 and 83.5, a 2.1-point spread"."""
    assert reads_as(noise_floor([84.1, 82.0, 83.5]).spread, "2.1")


# -- C5: the odds of a false alarm --------------------------------------------


def test_false_alarm_odds_at_twenty_slices() -> None:
    """C:21, C:169 -- "1 - 0.95^20 = 64%"."""
    assert reads_as(familywise_error_rate(20) * 100, "64")


def test_false_alarm_odds_at_twelve_variants() -> None:
    """C:188 -- "Twelve comparisons at alpha = 0.05 each gave a 46% chance of at least one false win"."""
    assert reads_as(familywise_error_rate(12) * 100, "46")


# -- C6: the permutation p-value ----------------------------------------------


def test_permutation_p_value_from_its_count() -> None:
    """C:201, C:217 -- "p = 0.018 (180 of 10,000 shuffles were as extreme)"."""
    assert reads_as(permutation_p_value(180, 10_000), "0.018")


def test_permutation_p_value_floor() -> None:
    """C:209 -- "The smallest p-value you can report is 1/10,000"; at the floor, say so."""
    assert permutation_p_value(0, DEFAULT_SHUFFLES) == 1 / 10_000
    nothing_as_extreme = PermutationResult(0.4, 1 / 10_000, 0, 10_000, seed=0)
    assert nothing_as_extreme.at_floor
    assert not PermutationResult(0.4, 0.018, 180, 10_000, seed=0).at_floor


# -- B5: the margin from n -----------------------------------------------------


def test_margin_on_a_500_item_leaderboard() -> None:
    """B:169, B:172 -- "At n = 500 and p = 0.85, SE = 1.6 points, so the margin is +-3.1"."""
    assert reads_as(standard_error(0.85, 500) * 100, "1.6")
    assert reads_as(margin_of_error(0.85, 500) * 100, "3.1")


def test_margin_on_a_weekly_dashboard() -> None:
    """B:190 -- n = 120 at p ~ 0.8 is +-7.2 points; growing it to 600 gives +-3.2."""
    assert reads_as(margin_of_error(0.8, 120) * 100, "7.2")
    assert reads_as(margin_of_error(0.8, 600) * 100, "3.2")


def test_worst_case_margin_shortcut() -> None:
    """B:22 -- "At n = 100 that's +-10, at n = 400 it's +-5, and at n = 2,500 it's +-2"."""
    assert reads_as(worst_case_margin(100) * 100, "10")
    assert reads_as(worst_case_margin(400) * 100, "5")
    assert reads_as(worst_case_margin(2_500) * 100, "2")


def test_margin_at_turn_level_and_at_conversation_level() -> None:
    """B:260, B:261, B:262 -- 2,000 turns at 86% reported "86 +- 1.5"; 250 conversations at 71%, +-5.6.

    Both reported margins are B5's formula at the stated n. The +-3.4 cluster
    figure between them is a bootstrap of data the corpus does not give.
    """
    assert reads_as(margin_of_error(0.86, 2_000) * 100, "1.5")
    assert reads_as(margin_of_error(0.71, 250) * 100, "5.6")


# -- B3: McNemar --------------------------------------------------------------


def test_mcnemar_on_500_motor_claims() -> None:
    """B:100, B:116 -- b = 40, c = 65: chi^2 = (|40 - 65| - 1)^2 / 105 = 5.49, p ~ 0.019."""
    result = mcnemar(40, 65)
    assert result.method is McNemarMethod.chi_square_continuity_corrected
    assert result.chi_square is not None and reads_as(result.chi_square, "5.49")
    assert reads_as(result.p_value, "0.019")


def test_mcnemar_below_25_discordant_pairs_is_exact() -> None:
    """B:107, B:120, B:121 -- b = 3, c = 11: b + c = 14 < 25, so exact binomial, p = 0.057.

    The analyst's mistake is reproduced too, through the chi^2 survival
    function, because mcnemar() will not compute it: uncorrected
    chi^2 = 64/14 = 4.57, p = 0.033 -- a "significant" result the exact test
    does not support.
    """
    result = mcnemar(3, 11)
    assert result.method is McNemarMethod.exact_binomial
    assert result.chi_square is None
    assert reads_as(result.p_value, "0.057")
    analysts_statistic = (3 - 11) ** 2 / (3 + 11)
    assert reads_as(analysts_statistic, "4.57")
    assert reads_as(chi_square_1df_sf(analysts_statistic), "0.033")


def test_mcnemar_after_labelling_300_more_notes() -> None:
    """B:100, B:107, B:121 -- b = 8, c = 21: 29 pairs, so chi^2 with continuity correction, p = 0.03.

    This is the example that decides the formula: uncorrected chi^2 gives
    0.016, and only B:100's continuity correction gives the corpus's 0.03.
    """
    result = mcnemar(8, 21)
    assert result.method is McNemarMethod.chi_square_continuity_corrected
    assert reads_as(result.p_value, "0.03")


def test_chi_square_critical_values() -> None:
    """B:108 -- "Compare it with 3.84 (p = 0.05) or 6.63 (p = 0.01)"."""
    assert reads_as(chi_square_1df_sf(3.84), "0.05")
    assert reads_as(chi_square_1df_sf(6.63), "0.01")


# -- B7: clustering -----------------------------------------------------------


def test_design_effect_on_1000_questions() -> None:
    """B:243 -- "With m = 10 and rho = 0.4, 1,000 questions carry the information of only 217"."""
    assert reads_as(effective_sample_size(1_000, 10, 0.4), "217")


def test_cluster_widening_on_contract_qa() -> None:
    """B:254, B:256, B:257 -- 10 questions per contract at rho = 0.4: a 2.1x widening, +-2.4 -> +-5.1.

    The corpus gives no per-item data, so the bootstrap itself cannot be rerun.
    What it does give is the prediction it says the bootstrap matched: the
    item-level interval understates the width by sqrt(design effect).
    """
    widening = math.sqrt(design_effect(10, 0.4))
    assert reads_as(widening, "2.1")
    assert reads_as(2.4 * widening, "5.1")


# -- the citations themselves -------------------------------------------------


@pytest.mark.parametrize("key", sorted(CITES))
def test_citation_is_on_its_line(corpus_dir: Path, key: str) -> None:
    """Each cited fragment is still on the line it is cited from."""
    entry = CITES[key]
    filename = SECTION_FILES[entry.section]
    require_corpus_files(corpus_dir, (filename,))
    lines = (corpus_dir / filename).read_text(encoding="utf-8").splitlines()
    assert entry.line <= len(lines), f"{key}: {filename} has only {len(lines)} lines"
    text = lines[entry.line - 1]
    for snippet in entry.snippets:
        assert snippet in text, f"{key}: {snippet!r} is not on line {entry.line} of {filename}: {text!r}"


def test_every_cited_line_is_verified_and_every_verified_line_is_cited() -> None:
    """A test that names a line the sweep does not check could be citing anything."""
    cited: dict[str, list[str]] = {}
    for module in (sys.modules[__name__], stats_properties):
        for key, tests in citations_in(module).items():
            cited.setdefault(key, []).extend(tests)
    unverified = {key: tests for key, tests in cited.items() if key not in CITES}
    assert not unverified, f"cited but not in tests/stats_citations.CITES: {unverified}"
    uncited = sorted(set(CITES) - set(cited))
    assert not uncited, f"in CITES but cited by no test: {uncited}"
