"""Statistics for section B and C: intervals, paired tests, resampling, power.

M1's statistics module (``PLAN.md`` T16, ticket EL-203). Every function
implements a line of ``knowledge rules/`` and cites it as ``<section>:<line>``,
the convention the registry's extraction notes use, and every corpus worked
example the module can reproduce is a test in
``tests/test_stats_corpus_examples.py``.

Conventions, stated once
------------------------
* **Proportions, not percentages.** Rates, intervals and margins are in [0, 1].
  ``noise_floor`` and the bootstraps are unit-agnostic: they answer in the
  units of their input.
* **Full precision out; nothing rounds.** Rounding is presentation. When a test
  compares a result with a figure the corpus prints, it rounds the computed
  value half-up to the decimal places the corpus printed, and compares for
  equality. Figures the corpus marks as approximate (~ 920, ~ 375, ~ 1,960,
  "about 5 points") are checked by round-trip instead -- the corpus's n, fed
  back through the inverse, must recover the corpus's effect at the precision
  it states the effect -- because no single rounding rule produces all of them
  from their formulas.
* **Two kinds of constant.** Interval estimators derive z exactly from the
  stated confidence level, because the corpus states the level ("a 95% CI").
  Rules of thumb use their printed constants verbatim -- 16, 1.96, 0.84, 3 --
  because the corpus prints them, and a reader should be able to check them
  by hand against the line.
* **Every default is cited or absent.** confidence 0.95 (C:25), alpha 0.05
  (C:19), 5,000 resamples (B:211), 10,000 shuffles (C:209), 25 discordant
  pairs (B:107). Seeds have no default: they are required and recorded.
* **Deterministic, and precise about where.** Every random draw is
  ``random.Random(seed).random()``, whose sequence Python guarantees across
  versions and platforms, so the bootstraps and the permutation test -- given
  a statistic built from correctly rounded arithmetic, such as ``fmean`` or
  ``median`` -- return the same floats everywhere; that was checked byte for
  byte on 3.10 and 3.12. The noise floor uses ``math.fsum`` and ``math.sqrt``
  for the same reason (``statistics.stdev`` changed its last digit in 3.12).
  The closed forms are different: z-values, chi^2 tails, power and
  Clopper-Pearson go through ``exp``, ``log``, ``erf``, ``erfc`` and
  ``lgamma``, which come from the platform's C library and are not guaranteed
  correctly rounded, so their last digit can differ between machines. No
  corpus figure is within reach of that digit; a store comparing raw floats
  across machines should compare at a stated precision.
* **Readiness is not checked here.** Whether there are enough runs, pairs or
  items to report a number honestly is the planner's job, through each
  record's ``requires``. These functions refuse only what is mathematically
  impossible.
"""

from __future__ import annotations

from evalloop.stats.compare import (
    CHI_SQUARE_MIN_DISCORDANT,
    DEFAULT_ALPHA,
    DEFAULT_SHUFFLES,
    McNemarMethod,
    McNemarResult,
    PermutationResult,
    chi_square_1df_sf,
    familywise_error_rate,
    mcnemar,
    paired_permutation_test,
    permutation_p_value,
)
from evalloop.stats.power import (
    NoiseFloor,
    noise_floor,
    paired_mde,
    paired_n,
    unpaired_mde,
    unpaired_n_per_arm,
    unpaired_power,
)
from evalloop.stats.proportions import (
    DEFAULT_CONFIDENCE,
    Interval,
    IntervalMethod,
    clopper_pearson_interval,
    margin_of_error,
    rule_of_three_items_needed,
    rule_of_three_upper_bound,
    standard_error,
    wilson_interval,
    worst_case_margin,
)
from evalloop.stats.resample import (
    DEFAULT_RESAMPLES,
    BootstrapInterval,
    bootstrap_ci,
    cluster_bootstrap_ci,
    design_effect,
    effective_sample_size,
    paired_bootstrap_ci,
)

__all__ = [
    "CHI_SQUARE_MIN_DISCORDANT",
    "DEFAULT_ALPHA",
    "DEFAULT_CONFIDENCE",
    "DEFAULT_RESAMPLES",
    "DEFAULT_SHUFFLES",
    "BootstrapInterval",
    "Interval",
    "IntervalMethod",
    "McNemarMethod",
    "McNemarResult",
    "NoiseFloor",
    "PermutationResult",
    "bootstrap_ci",
    "chi_square_1df_sf",
    "clopper_pearson_interval",
    "cluster_bootstrap_ci",
    "design_effect",
    "effective_sample_size",
    "familywise_error_rate",
    "margin_of_error",
    "mcnemar",
    "noise_floor",
    "paired_bootstrap_ci",
    "paired_mde",
    "paired_n",
    "paired_permutation_test",
    "permutation_p_value",
    "rule_of_three_items_needed",
    "rule_of_three_upper_bound",
    "standard_error",
    "unpaired_mde",
    "unpaired_n_per_arm",
    "unpaired_power",
    "wilson_interval",
    "worst_case_margin",
]
