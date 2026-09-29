# SECTION C – DECIDING WHETHER A RESULT IS REAL
### Separates people who run evals from people who understand them

You are here when a number is about to drive a decision (ship, retrain, roll back, sign the contract) and nobody has asked how much of it is noise. A score of "82%" feels like a fact, but it's one draw from a distribution. On 100 items the true value could plausibly sit anywhere from the low 70s to the high 80s, and a stochastic system can move three points between identical runs. This section is the toolkit for asking "how sure are we?" *before* the decision, which is also the only time the answer can change the decision.

> **Every number is an estimate. Report its uncertainty, size your sample before you collect it, and don't treat noise as a result.**

```
  WHERE NOISE COMES FROM            WHAT CONTROLS IT
  ──────────────────────────────────────────────────────────────────
  Which items you sampled      →  CI on every score (C1, C4)
  How many items you have      →  power analysis before running (C2)
  Randomness in the system     →  k ≥ 5 runs, mean ± SD (C3)
  How many things you checked  →  multiple-comparison correction (C5)
  Weird distribution shapes    →  permutation test (C6)
```

**Three rules of thumb worth memorising:**
- *Sample size per arm ≈ 16·p(1−p) / δ²* (α = 0.05, 80% power). To detect 80% → 85% you need **≈ 920 items per arm** unpaired.
- *Rule of three:* 0 failures in n items → the true failure rate is **≤ 3/n** at 95% confidence.
- *False-alarm odds:* checking k slices at α = 0.05 gives P(at least one false alarm) = **1 − 0.95ᵏ**, which is already **64% at k = 20**.

---

# C1 – REPORT A 95% CI ON EVERY SCORE (WILSON FOR PROPORTIONS)

## What it is
Every reported score carries an interval. For pass rates, use the **Wilson score interval**. It stays inside [0, 1], it's accurate at small n, and it's one line in any stats library (`statsmodels.stats.proportion.proportion_confint(method="wilson")`).

## Why it matters
**A bare "82%" invites decisions made on noise.** 82 of 100 has a Wilson 95% CI of **[73.3%, 88.3%]**. That's a 15-point range, and it can answer a question the point estimate can't: could this system meet a 90% bar? Here the answer is no, even at the top of the interval.

## How to do it properly
1. **Make the CI part of the output format.** Your eval harness should print `82.0% [73.3, 88.3] n=100` by default. If computing it takes extra effort, nobody will.
2. **Use Wilson, not the textbook ±1.96·√(p(1−p)/n).** The textbook (Wald) interval misbehaves below n ≈ 100 and near 0% or 100%.
3. **Compare the interval with the decision threshold.** If the whole CI is above the bar, ship. If the whole CI is below, no. If it straddles the bar, you need more data.
4. **Put CIs on slices too.** Slices are smaller, so their intervals are wider, and that's exactly where people over-read differences.

## Real scenarios

**Healthcare – discharge-summary completeness checker**
- **Input:** 100 discharge notes, graded by two physicians.
- **Output:** 82/100 complete. The vendor deck said "82% accurate, approaching our 90% target."
- **Verdict:** Wilson CI **[73.3%, 88.3%]**. The upper bound is below 90%, so this isn't "needs more data". It's a clear "not ready". The CMO had been about to approve a pilot on the strength of "approaching". The CI turned a hopeful reading into a firm no, and the vendor went back for another iteration.

**Fintech – KYC income-verification, salaried vs self-employed**
- **Input:** 50 applications from each segment.
- **Output:** Salaried 47/50 (94%), self-employed 43/50 (86%). The team proposed building a separate self-employed pipeline, about six weeks of work.
- **Verdict:** Wilson CIs were **[83.8, 97.9]** and **[73.8, 93.0]**, which overlap heavily, so no gap had been demonstrated. Labelling 250 more per segment, about 3 days of work, showed 91% vs 89%. The six-week project was cancelled on the strength of a free calculation.

## The mistake people make
Putting a bare percentage in a slide title. Once it's there, it will be read as exact.

## The line to use in a meeting
*"It's 82%, but on 100 cases the true rate could be anywhere from 73 to 88, and even the top of that range is below our bar."*

---

# C2 – POWER ANALYSIS (SAMPLE SIZE BEFORE YOU RUN)

## What it is
Before you collect or label data, you solve for the n needed to detect the smallest effect you care about, at α = 0.05 and 80% power. Or you work backwards: given your budget of n, compute the **minimum detectable effect (MDE)**.

## Why it matters
**An underpowered eval reports "no difference" when the truth is "we couldn't tell."** Teams read "not significant" as "no effect" and kill good changes. Unpaired, detecting 80% → 85% needs ≈ 920 items per arm. With a paired design where about 12% of items flip between versions, it drops to **≈ 375**.

## How to do it properly
1. **Name the effect that would change your decision.** "We'd retrain if it's +5 points" is enough. Don't power the eval for a 0.5-point effect you would never act on.
2. **Unpaired:** n ≈ 16·p(1−p)/δ² per arm.
3. **Paired (McNemar):** n ≈ (1.96·√d + 0.84·√(d − δ²))² / δ², where d is the expected share of discordant items. Estimate d from a 50-item pilot.
4. **If the budget is fixed, compute and publish the MDE**, for example: "With 200 paired items we can detect ≥ 7 points. Smaller effects will read as 'no difference'."
5. **Write down n before you run.** Collecting until the result looks significant is p-hacking, even when nobody means it to be.

## Real scenarios

**Fintech – KYC document extractor, retrain decision**
- **Input:** 150 items per version, old vs candidate.
- **Output:** 80% vs 83%, "not significant, don't retrain." The candidate was shelved.
- **Verdict:** A power calculation afterwards showed that at n = 150 per arm, the chance of detecting a real 5-point gain was **21%**. The eval had been four times more likely to miss a real improvement than to find one. Re-run paired on 400 items (12% discordant), the candidate won by **+4.5 (CI [+1.1, +7.9])** and was deployed. The shelved candidate had cost six weeks.

**Telecom – intent classifier for a 12-language support bot**
- **Input:** A product manager asked for a 2-point improvement to be detected on a 300-item budget.
- **Output:** The team was about to run it anyway.
- **Verdict:** Detecting 2 points with 10% discordance needs **≈ 1,960 paired items**. The MDE at 300 was about 5 points. The meeting chose between two honest options: accept "we can detect 5+ points", or spend ₹1.8 lakh on labels for 2,000 items. They took the first and agreed that sub-5-point changes would be judged in an online A/B test instead.

## The mistake people make
Treating "not statistically significant" as "no effect" without checking whether the eval could have detected the effect.

## The line to use in a meeting
*"This eval could only detect gains of 7 points or more. 'No difference' means we couldn't tell, not that there's no gain."*

---

# C3 – k ≥ 5 RUNS PER ITEM; REPORT MEAN ± SD ACROSS RUNS

## What it is
For stochastic systems (sampling temperature above 0, agents, anything that calls tools or retrieves), you run the full eval k ≥ 5 times and report the mean and standard deviation across runs. The run-to-run SD is your noise floor.

## Why it exists
**One run at temperature 0.7 can land ±3 points from the mean, and you ship a lucky seed.** Five runs of one config on 300 items gave 76.1, 79.4, 77.8, 74.9 and 78.2. The mean is 77.3 and the SD is 1.8. Any single run could have been reported as "the score", and they span 4.5 points.

## How to do it properly
1. **Run k = 5** for decisions and k = 3 for daily iteration. Log the seed and the provider model version for each run.
2. **Report mean ± SD** and the per-run numbers.
3. **Don't treat temperature 0 as deterministic.** Provider-side batching and floating-point nondeterminism still move scores. Measure it (see E4).
4. **Classify items by pass count** (always, sometimes, never). The "sometimes" items are where the noise lives and where the fixes are.
5. **Compare configs on means of k runs.** Only call a difference real if it's larger than about 2× the run-to-run SD *and* the paired CI (B1) agrees.

## Real scenarios

**Insurance – health-claim triage agent, v1 vs v2**
- **Input:** 300 claims, one run each.
- **Output:** v1 74.9%, v2 78.9%. "+4 points" was announced at the weekly review.
- **Verdict:** With 5 runs each, v1 averaged **77.3 ± 1.8** and v2 **77.9 ± 1.6**, a +0.6 difference inside the noise. v1's single run had been its worst of five. The team was two days into rolling v2 out to 3 hospitals, and v2 had a new tool dependency that needed an IT change at each site. The rollout was paused until an improvement was actually demonstrated.

**Legal – NDA clause extractor at temperature 0**
- **Input:** 3 identical runs at temperature 0 "to be safe".
- **Output:** 84.1, 82.0 and 83.5, a 2.1-point spread on a config everyone assumed was deterministic.
- **Verdict:** 17 of 400 items changed their verdict across runs. All were long NDAs where the extraction sat near the output token limit. Raising max tokens made 14 of the 17 stable. The eval now always runs 3×, and a regression has to exceed the 2-SD band before anyone is paged.

## The mistake people make
Comparing one run against one run and calling a 3-point gap a result.

## The line to use in a meeting
*"We ran it five times, and the score moves ±2 points on its own. A 3-point change from one run isn't evidence of anything."*

---

# C4 – WILSON / CLOPPER–PEARSON NEAR 0% OR 100%; RULE OF THREE AT ZERO

## What it is
Near the edges (99% accurate, 0 failures), you use score-based (Wilson) or exact (Clopper–Pearson) intervals. When you observe **zero events in n trials**, the 95% upper bound on the true rate is approximately **3/n**.

## Why it matters
The textbook Wald interval breaks exactly where the stakes are highest. For 198/200 it gives **[97.6%, 100.4%]**, which is impossible. For 0/n it gives an interval of zero width, which says "certainly zero." Wilson for 198/200 gives **[96.4%, 99.7%]**. Zero failures in 300 means the failure rate could still be **up to 1%**.

## How to do it properly
1. **Never report "0 failures" without the upper bound.** Say "0/300 → ≤ 1.0% at 95%."
2. **Turn the rule of three around to size a safety eval.** To claim ≤ 0.1% you need **3,000 clean items**, and to claim ≤ 0.01% you need 30,000.
3. **Use Clopper–Pearson** when a regulator or auditor wants a conservative exact interval. Use Wilson otherwise.
4. **Report counts next to percentages.** "198/200" gives the reader the evidence and the sample size in one figure.

## Real scenarios

**Healthcare – prescription dosage extraction**
- **Input:** 200 handwritten and printed prescriptions from a pharmacy chain.
- **Output:** 198/200 correct. The dashboard used the Wald formula and showed "99.0% ± 1.4" as a band reaching 100.4%.
- **Verdict:** Wilson gives **[96.4%, 99.7%]**. The lower bound, 96.4%, is the honest planning figure: up to about 36 errors per 1,000 prescriptions at the worst case. At 4,000 prescriptions a day, that's up to 144 dosage errors a day. The pharmacist-verification step that was about to be removed stayed.

**Fintech – PAN masking in customer-support transcripts**
- **Input:** 300 transcripts containing PAN numbers.
- **Output:** 0 leaks. The compliance deck said "100% masking".
- **Verdict:** The rule of three gives **≤ 1.0% at 95%**. The compliance requirement was ≤ 0.1%, which needs 3,000 clean transcripts. The team built a 3,000-item synthetic-plus-real set, found 2 leaks (PANs split across two chat messages), fixed the masker and re-ran 3,000 clean. The claim became "≤ 0.1%", which is one the auditor accepted.

## The mistake people make
Writing "0 errors" or "100%" as if it meant certainty. It means the sample was too small to see the errors.

## The line to use in a meeting
*"Zero failures in 300 means the true rate could still be up to 1%. To claim 0.1% we need 3,000 clean cases."*

---

# C5 – MULTIPLE-COMPARISON CORRECTION

## What it is
When you test many slices or metrics at once, you tighten the significance threshold for each test so the chance of *any* false alarm stays at 5%. Use **Holm–Bonferroni** when a false alarm has a real cost (blocking a release), and **Benjamini–Hochberg** (which controls the false-discovery rate) when you're exploring and will re-test anything you find.

## Why it matters
With 20 slices tested at α = 0.05, P(at least one false alarm) = 1 − 0.95²⁰ = **64%**. Slice dashboards all but guarantee a spurious "regression" somewhere, and teams then spend a sprint chasing it. The same problem applies to picking the best of many prompt variants: the winner's score is inflated by selection. This is the **winner's curse**.

## How to do it properly
1. **Count your tests honestly.** That includes every slice, metric and variant you looked at, not just the ones you reported.
2. **Bonferroni:** α per test = 0.05 / k. **Holm** is uniformly better: sort the p-values, compare the smallest with 0.05/k, the next with 0.05/(k−1), and so on.
3. **For exploration, use BH at q = 0.10** and treat everything it flags as a hypothesis to confirm on fresh data.
4. **After picking the best of N variants, re-measure the winner on a held-out set.** Its original score is biased upwards.
5. **Pre-register must-check slices** (for example your top 3 languages). A slice that's pre-registered doesn't count as one of the k tests.

## Real scenarios

**Telecom – support bot across 20 language and circle slices**
- **Input:** A new release evaluated on 20 slices.
- **Output:** Tamil dropped 4.1 points at p = 0.03, and a Tamil-specific rollback was proposed.
- **Verdict:** The Bonferroni threshold was 0.0025, and under Holm, Tamil wasn't the smallest p-value, so it wasn't significant. Re-running Tamil on 400 fresh items showed **−0.4 (CI [−3.2, +2.4])**. The release went out, and the rollback would have cost two weeks of Tamil-market fixes for a regression that didn't exist.

**E-commerce – 12 prompt variants for product-description generation**
- **Input:** 12 variants each compared with baseline on the same 300 items, and the best one picked.
- **Output:** Variant 9 scored **+2.8, p = 0.04**, and was declared the winner.
- **Verdict:** Twelve comparisons at α = 0.05 each gave a 46% chance of at least one false win. On a held-out 300 items, variant 9 scored **+0.3**. Its 2.8-point lead had come from being the luckiest of 12 on those particular items. Variant selection now happens on a dev split, with confirmation on a held-out split.

## The mistake people make
Scanning a 20-row slice table for red cells and treating each one as a finding.

## The line to use in a meeting
*"We checked 20 slices, so we'd expect about one 'significant' drop by chance. This one doesn't survive correction."*

---

# C6 – PERMUTATION TEST

## What it is
To test whether A and B really differ, you randomly swap the A/B labels within each item 10,000 times and recompute the difference each time. The p-value is the fraction of shuffles whose difference is at least as large as the one you observed. It makes no assumptions about the shape of the distribution.

## Why it matters
A t-test assumes roughly normal data. **Heavy-tailed metrics, such as latency, ₹ cost and ETA error, break that assumption.** A few extreme values inflate the variance, and the t-test loses power or gives misleading answers. A permutation test works for any statistic, including medians and trimmed means, which are the statistics that suit heavy-tailed data.

## How to do it properly
1. **Choose a statistic that suits the data before looking at the results.** Use the median or a 10% trimmed mean for heavy tails, and the mean when the tails are light.
2. **Shuffle within pairs** when the design is paired: flip the sign of each item's difference at random.
3. **Use 10,000 shuffles.** The smallest p-value you can report is 1/10,000.
4. **Report the tail separately.** p95 or p99 is often the business metric, and the median test won't cover it.

## Real scenarios

**Logistics – delivery-ETA model, old vs new**
- **Input:** 2,400 deliveries in Mumbai and Pune, with absolute ETA error in minutes.
- **Output:** The mean error was *worse* by 1.1 minutes (t-test p = 0.21), and the new model was about to be rejected.
- **Verdict:** Six deliveries on a monsoon-flooded route had misses above 6 hours under *both* models, and they dominated the mean. A permutation test on **median error** showed a **2.6-minute improvement, p = 0.018** (180 of 10,000 shuffles were as extreme). The new model shipped, and p95 error became a separate tracked metric so the flood-route problem stayed visible.

**Fintech – LLM cost per support conversation, new router vs old**
- **Input:** 5,000 conversations on each router, ₹ cost per conversation.
- **Output:** The mean fell from ₹1.84 to ₹1.61, and the t-test gave p = 0.09.
- **Verdict:** Costs were heavily skewed, with 2% of conversations running 40+ turns. A paired permutation test on the 10% trimmed mean gave **p = 0.003** for a ₹0.21 saving. That's **₹35.7 lakh a year** at 1.7 crore conversations. The saving was real, and the t-test had been under-powered by the long tail.

## The mistake people make
Running a t-test on latency or ₹ cost because it's the default in the notebook.

## The line to use in a meeting
*"We didn't assume any distribution. We shuffled the labels 10,000 times, and a gain this size appeared by chance in fewer than 2% of the shuffles."*

---

# SECTION C DECISION FLOW

```
START: A number is about to drive a decision.
│
├─ Have you collected the data yet?
│     └─ NO → power analysis first (C2)
│              ├─ n ≈ 16·p(1−p)/δ² per arm (unpaired) — paired is ~2–3× cheaper
│              └─ budget fixed? → publish the MDE before running
│
├─ Is the system stochastic (temp > 0, agents, retrieval)?
│     └─ YES → k ≥ 5 runs; mean ± SD; differences must exceed ~2 SD (C3)
│
├─ Is the score near 0% or 100%, or n < 100?
│     ├─ 0 events → rule of three: ≤ 3/n (C4)
│     └─ otherwise → Wilson (or Clopper–Pearson for auditors) (C4)
│
├─ Otherwise → Wilson 95% CI on every score and slice (C1)
│     └─ CI entirely above bar → ship · entirely below → no · straddles → more data
│
├─ Did you check many slices / metrics / variants?
│     └─ YES → Holm (gating) or BH q = 0.10 (exploring) (C5)
│              └─ picked best of N? → re-measure on held-out set
│
└─ Is the metric heavy-tailed (latency, ₹, ETA)?
      └─ YES → permutation test on median / trimmed mean; report p95 separately (C6)
```

---

# THE THREE THINGS TO REMEMBER

1. **A number without an interval is just a guess that looks precise.** Report Wilson CIs on every score and slice, and state the upper bound on any zero.

2. **Decide n before you look.** An underpowered "no difference" means you couldn't tell, and collecting until the result looks significant manufactures a false one.

3. **The more you look, the more noise you'll find.** Correct for the number of slices and variants you checked, and re-measure any winner on data it wasn't picked on.
