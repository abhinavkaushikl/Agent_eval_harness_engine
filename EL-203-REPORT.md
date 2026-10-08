# EL-203 — Statistics module (stages S26–S29)

**Status: done.** `pytest` 802 passed on 3.12, and 801 passed + 1 skipped on 3.10
(the skip is the existing `test_compat.py` stdlib-StrEnum comparison, which is
3.11+ only). `mypy --strict evalloop/` clean on 21 files. Standard library only.

EL-203 is one of three E2 tickets that don't depend on 🔒 Gate 0, so this work
doesn't wait on the Gate 0 review.

---

## 1. What exists

| File | What it holds |
|---|---|
| `evalloop/stats/__init__.py` | Package conventions, stated once: units, rounding, the two kinds of constant, cited defaults, determinism scope |
| `evalloop/stats/proportions.py` | `wilson_interval`, `clopper_pearson_interval`, `rule_of_three_upper_bound`, `rule_of_three_items_needed`, `standard_error`, `margin_of_error`, `worst_case_margin` |
| `evalloop/stats/compare.py` | `mcnemar` (with B:107's branch switch), `chi_square_1df_sf`, `paired_permutation_test`, `permutation_p_value`, `familywise_error_rate` |
| `evalloop/stats/resample.py` | `bootstrap_ci`, `paired_bootstrap_ci`, `cluster_bootstrap_ci`, `design_effect`, `effective_sample_size` |
| `evalloop/stats/power.py` | `unpaired_n_per_arm`, `paired_n`, `unpaired_mde`, `paired_mde`, `unpaired_power`, `noise_floor` |
| `tests/test_stats_corpus_examples.py` | 86 tests: every reproducible worked example, a citation sweep, and a registry cross-check |
| `tests/test_stats_properties.py` | 75 tests: properties where the corpus prints results but no data |
| `tests/stats_citations.py` | The 54 cited corpus lines with verbatim snippets, plus `reads_as()`, the one rounding rule |

**Two departures from the ticket's file list, both additions:** a second test file
and a helper module. The ticket listed one file. Properties without corpus data
needed their own home, and both files share one citation table.

**Citations check themselves.** Every `<section>:<line>` in a stats test docstring
must be in `CITES`. Every `CITES` snippet is checked against its corpus line, and
every entry has to be cited by at least one test. While I was writing the tests, a
missing `C:28` was caught by exactly this check.

**The planner and the statistic share a bound by test.**
`B3_mcnemar.requires.discordant_pairs` must equal `CHI_SQUARE_MIN_DISCORDANT`. If
either moves alone, the test fails.

---

## 2. The worked examples: all 21 rows reproduce, plus 6 the ticket missed

| # | Example | Result | Line |
|---|---|---|---|
| 1 | Wilson 82/100 | [73.3, 88.3] ✅ | C:31 |
| 2 | Wilson 198/200 | [96.4, 99.7] ✅ | C:135 |
| 3 | Wald 198/200 | [97.6, 100.4], "± 1.4" ✅ | C:135, C:147 |
| 4 | Wilson 47/50, 43/50 | [83.8, 97.9], [73.8, 93.0] ✅ | C:49 |
| 5 | Rule of three, 0/300 | ≤ 1.0% ✅ | C:138 |
| 6 | ≤ 0.1% / ≤ 0.01% | 3,000 / 30,000 ✅ | C:139 |
| 7 | Unpaired 80 → 85 | ≈ 920 ✅ *(formula 924)* | C:19, C:65 |
| 8 | Paired, d = 0.12 | ≈ 375 ✅ *(formula 373.96)* | C:65 |
| 9 | Paired, 2 pts, d = 0.10 | ≈ 1,960 ✅ *(formula 1,957.6)* | C:84 |
| 10 | Power, n = 150/arm | 21% ✅ | C:79 |
| 11 | Noise floor | mean 77.3, SD 1.8 ✅ | C:100 |
| 12 | FWER, k = 20 | 64% ✅ | C:21, C:169 |
| 13 | FWER, k = 12 | 46% ✅ | C:188 |
| 14 | n = 500, p = .85 | SE 1.6, ±3.1 ✅ | B:172 |
| 15 | n = 120 / 600, p ≈ .8 | ±7.2 / ±3.2 ✅ | B:190 |
| 16 | 100/√n | ±10 / ±5 / ±2 ✅ | B:22 |
| 17 | McNemar b = 3, c = 11 | exact p 0.057; analyst's χ² 4.57, p 0.033 ✅ | B:121 |
| 18 | McNemar b = 8, c = 21 | p 0.03 ✅ *(continuity-corrected only)* | B:121 |
| 19 | Design effect | 217 ✅ | B:243 |
| 20 | Cluster widening | 2.1×, ±2.4 → ±5.1 ✅ *(via √DEFF)* | B:257 |
| 21 | Permutation p | 180/10,000 → 0.018; floor 1/10,000 ✅ | C:209, C:217 |
| 22 | McNemar b = 40, c = 65 | χ² 5.49, p ≈ 0.019 ✅ | B:116 |
| 23 | χ² critical values | 3.84 → 0.05, 6.63 → 0.01 ✅ | B:108 |
| 24 | Paired MDE at n = 300 | "about 5 points" ✅ | C:84 |
| 25 | Run spreads | 4.5, 2.1 ✅ | C:100, C:118 |
| 26 | Turn / conversation margins | ±1.5 at 2,000; ±5.6 at 250 ✅ | B:261, B:262 |
| 27 | CP one-sided = rule of three | 0.99% → "1.0%" ✅ | C:132 |

**How a figure is compared.** The computed value is rounded half-up to the decimal
places the corpus printed, then compared. Rows 7–9 are printed as "≈", and no
single rounding rule turns 924, 373.96 and 1,957.6 into 920, 375 and 1,960. So
those rows are tested by round trip: the corpus's own n, fed back through the
inverse, must recover the corpus's stated effect (5, 5, 2 points).

**Row 18 decided the McNemar formula.** Uncorrected χ² gives p = 0.016 → "0.02".
Only B:100's continuity correction gives the corpus's 0.03. The 4.57/0.033 in
row 17 is the analyst's *mistake* as B:121 tells it. `mcnemar()` won't compute
it; the test reproduces it through `chi_square_1df_sf` instead.

**Row 3 has no `wald_interval`.** The ticket said a Wald function should exist
only to fail this test. Instead, the Wald half-width is B5's `margin_of_error`,
which B:169 prescribes for reading someone else's numbers. A separate Wald
function would be a second, misusable spelling of what C:35 says not to use.

---

## 3. What the corpus would not support

| Figure | Why not tested |
|---|---|
| B:32 paired CI [+0.2, +5.8] | Needs b and c; the corpus gives neither |
| B:32 unpaired CI [−2.6, +8.6] | Reproduces as [−2.59, 8.59] with the unpaired Wald difference CI, which no ticket asks for |
| C:79 re-run CI [+1.1, +7.9] | Reproduces analytically as [1.13, 7.87], taking b = 15, c = 33 from "12% discordant" and "+4.5". On that reconstruction the paired bootstrap gives [1.25, 7.75], seeds 1–2. Reported, not asserted |
| B:185, B:206, B:220, B:225, C:217's median, C:222's trimmed mean, B:262's ±3.4 | Results of data the corpus doesn't publish. These are mechanism tests in `test_stats_properties.py` instead |
| C:71/C:90 "200 paired items → ≥ 7 points" | d isn't stated (d = 0.12 would give 6.8) |
| Master lookup C2, "≈ 905" | **Explained, and this closes M0's open C2 discrepancy:** 905 = 15.68 × 0.144375 / 0.0025. That's the unrounded constant 2(1.96 + 0.84)², where the deep dive rounds it to 16 and gets 924 ≈ 920 |
| Master lookup C2, "≈ 400 at 60% agreement" | **Does not reproduce:** C:70 at d = 0.40 gives 1,252. The lookup's paired parameter isn't C:70's d |

---

## 4. Interpretations — the human-review queue

| # | Interpretation | Grounds |
|---|---|---|
| 1 | **The p in 16·p(1−p)/δ² is the midpoint of the two rates** | Not stated anywhere. C:19's "80 → 85 needs ≈ 920" reproduces only at p = 0.825 (p = 0.80 gives 1,024; p = 0.85 gives 816). The API takes both rates, so callers can't get this wrong |
| 2 | **The permutation test is two-sided** (\|diff\| ≥ \|observed\|) | C:201 says "at least as large", C:217 says "as extreme" |
| 3 | **McNemar's continuity correction is clamped at zero** | B:100 read literally gives (0 − 1)² / (b + c) > 0 when b = c, which scores a tie as *more* evidence than b and c one apart. Clamped, as R's `mcnemar.test` does. Only affects b = c above 25 pairs; no worked example changes |
| 4 | **Percentiles use linear interpolation (type 7)** | B:203 says "2.5th and 97.5th percentiles" with no definition |
| 5 | **5,000 resamples by default, no minimum enforced** | B:211 gives "5,000 for reporting, 1,000 while iterating". Treating B:203's 1,000 as a hard floor would be an interpretation, so there is none |
| 6 | **The power formula** | C:79 prints only the result (21%). I use the normal approximation the 16 rule inverts, at the pooled midpoint. The unpooled variant gives 20.7%, so the corpus can't tell them apart |
| 7 | **The rule of three is one-sided** | C:132's "95% upper bound ≈ 3/n" matches the one-sided bound (0.99%); two-sided gives 1.22%. So it's tested as the upper end of the two-sided 90% Clopper–Pearson interval |
| 8 | **When no shuffle is as extreme, p = 1/shuffles with `at_floor = True`** | C:209: "The smallest p-value you can report is 1/10,000" |
| 9 | **Sample sizes are returned unrounded** | "≈ n" in the corpus. Callers round up when sizing |

**Decided by a worked example, not interpreted:** the noise floor's SD is the
*sample* SD (n − 1). C:100's 1.8 reproduces only that way; the population SD is 1.6.

**Numerical constants that are not methodology:** the incomplete-beta convergence
constants, bisection step counts, and a 1e-12 relative tie tolerance in the
permutation count. The tie tolerance makes floating-point near-ties count as extreme,
which errs toward a larger p. Each is labelled as numerical where it is defined.

---

## 5. Rulings I need

1. **B3 below 25 pairs: pending, or ready with the exact test?** The planner marks
   `B3_mcnemar` PENDING below 25 discordant pairs. B:107 doesn't say wait; it says
   "use the exact binomial test". `mcnemar()` now implements that fallback, so the gap
   is entirely on the planner side. B3's extraction notes record the schema can't
   express the fallback.
2. **Decision thresholds on statistics have no home.** This is EL-015's question
   again, from the other side. None of these is a readiness bar or a statistic, so
   neither the registry nor this module holds them:
   B:177/B:299 "gap < 1.4× margin → tie" · B:248 "ratio > 1.5× → report the cluster
   CI" · C:107/C:243 "differences must exceed ~2 SD" · C:36/C:250 "CI vs. bar → ship /
   no / more data" · C:174 "BH at q = 0.10" · B:296 "flip rate > 10–15%".
   **Recommendation:** widen EL-015 to cover decision thresholds, not just comparator
   constants.
3. **C5's corrections aren't built.** Bonferroni, Holm and BH (C:173–174, with a worked
   example at C:183) weren't in the ticket. That means nothing in M1 can produce
   `C5_multiple_comparisons`' declared outputs, `corrected_alpha` and
   `adjusted_p_value`. Follow-up ticket, or M3?
4. **Cross-machine float determinism, an input to EL-201.** Random draws are identical
   across versions and platforms: I diffed seven results byte for byte on 3.10 against
   3.12. Closed forms go through libm (`erf`, `lgamma`, `log`), so their last digit can
   differ between machines. EL-201's metric store ("same bytes") should store or compare
   at a stated precision.
5. **C:207's 10% trimmed mean** isn't in the stdlib and wasn't built. The corpus also
   doesn't say whether it means 10% per tail or 10% total.

Not built, by the ticket's own scope: Bradley–Terry (B4), nDCG and MRR (Track V), and
the analytic paired CI from finding 3 in §3.

---

## 6. Stale doc lines

| Where | What's stale |
|---|---|
| `CLAUDE.md` §2 | "Milestone 0 only … do not create `stats/`". This session built `evalloop/stats/` under the M1 preamble. §2 needs the M1 scope text; it's ready in `E2-M1-TICKETS-AND-PROMPTS.md` §0 |
| `CLAUDE.md` §5 | The target layout has no `evalloop/stats/` |
| `E2-M1-TICKETS-AND-PROMPTS.md`, EL-203 | (a) "Wald exists only so test 3 can prove it is wrong": superseded, see §2. (b) The acceptance table never says McNemar is continuity-corrected, yet row 18 depends on it (B:100). (c) The file list names one test file; there are three test-side files. I left the ticket text alone, per scope |

**One bug found and fixed during the build.** `noise_floor` used `statistics.stdev`,
whose last digit changed in Python 3.12 (`…808` on 3.10 vs `…8077` on 3.12). It now
uses `math.fsum` and `math.sqrt`, which are correctly rounded and so identical on
every version.

---

## 10. Re-verification against the full EL-203 prompt — 2026-10-09

I built the module from the session preamble alone, because no ticket block had been pasted.
This pass checks it against the ticket's own prompt, line by line. It was not rebuilt.

**Two gaps fixed.** Two citations named in the prompt had never been checked against the
corpus:

- **C:159** is the prompt's second source for the rule of three: "could still be up to 1%".
  It is now in the citation table, and both rule-of-three tests assert its figures.
- **B:203** is the prompt's source for "1,000–10,000" resamples. It is now in the citation
  table, and the defaults test asserts that the 5,000 default lies inside that printed range.

The stats suite now has 163 tests, up from 161. It passes on 3.12 and on 3.10.

| # | Requirement | Status |
|---|---|---|
| 1 | Four modules, stdlib only | ✅ No NumPy |
| 2 | One test per example, naming its line | ✅ Lines are written `C:31`, not `<file>:31`. `CLAUDE.md` §3 keeps corpus filenames in `tests/conftest.py` only, which maps each section letter to its file. That rule outranks the prompt's "file:line" |
| 3 | Wilson as the default; Wald only for the 198/200 demonstration, citing C:35 | ✅ With one deviation: there is no `wald_interval`. The Wald half-width is B5's `margin_of_error`, which the corpus prescribes for reading other people's numbers (B:169). Its docstring cites C:35 to say it is not the interval for your own score. A second function would be a second, misusable spelling of the same formula |
| 4 | The b + c ≥ 25 switch, with both branches proven | ✅ b=3, c=11 takes the exact branch: 0.057. b=8, c=21 takes the χ² branch: 0.03. A boundary test covers 24 versus 25 pairs. The χ² branch reproduces 0.03 **only with B:100's continuity correction**, which the prompt does not mention |
| 5 | Every default cited, or required | ✅ 10,000 shuffles (C:209); 5,000 resamples (B:211, inside B:203's range); α 0.05 (C:19); confidence 0.95 (C:25); 25 discordant pairs (B:107). Seeds have no default |
| 6 | Seeded, with the seed recorded | ✅ Re-verified today: the seeded results are byte-identical on 3.10 and 3.12 |
| 7 | One rounding convention, in the package docstring | ✅ Round half-up to the decimal places the corpus printed |
| 8 | Report every figure that does not reproduce | Below |

**Figures that do not reproduce to the digit the corpus prints:**

| Row | Corpus prints | The corpus's own formula gives |
|---|---|---|
| C:19 / C:65, unpaired | ≈ 920 | 924 |
| C:65, paired | ≈ 375 | 373.96 |
| C:84, paired | ≈ 1,960 | 1,957.6 |
| B:257, cluster CI | ±5.1 | Cannot be recomputed: the corpus gives no data |

- **The three sample sizes** are printed with "≈". Each is tested by round trip instead: the
  corpus's own n, fed back through the inverse formula, recovers the effect the corpus states.
- **The cluster CI** is checked only through the formula: the design-effect prediction of a
  2.1× widening reproduces, but the bootstrap behind ±5.1 cannot be re-run.

Every other figure reproduces exactly under the stated rounding.

**Decisions made since the build:**

- **EL-014** ruled that timeouts count as failures. That changes no statistics. The caller
  computes a pass rate as `wilson_interval(passed, passed + failed)`: timeouts are counted,
  inconclusive runs are not. That aggregation is EL-211's job.
- **EL-015** ruled that corpus figures live on the technique's record. It forecloses "corpus
  figures as module literals", and that **conflicts with five of this module's cited
  defaults**:
  - confidence 0.95 (C1);
  - α 0.05 (C2, C5);
  - 10,000 shuffles (C6);
  - 5,000 resamples (B6);
  - 25 discordant pairs (B3).

  The other constants are unaffected. The formula constants — 16, 1.96, 0.84 and 3 — *are* the
  corpus's printed formulas, not settings, so they stay. The bisection counts and convergence
  epsilons are not corpus figures at all.

  *Recommendation:* once EL-015's implementing story inventories those five records, add one
  test per default asserting that the module's default equals the record's parameter. The
  pattern already exists, as `test_the_planner_and_mcnemar_read_the_same_bound` does for B3. It
  keeps this library free of registry I/O, and the two copies of each number cannot drift
  apart. *The alternative* is to make the five arguments required and have every caller pass
  the record's value. **This needs a ruling.**

**Bookkeeping:** the E2 board still showed EL-203 and EL-202 as Ready, although both were done.
Both rows are corrected. The stale status is the likely reason this ticket arrived a second
time.
