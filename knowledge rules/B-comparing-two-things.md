# SECTION B – COMPARING TWO THINGS
### Almost every eval decision is a comparison. Most are done wrong.

You are here when you have two (or more) versions of something, whether prompts, models, retrievers or judges, and someone wants to know which one to ship. Usually there's a spreadsheet with two percentages three points apart and a meeting in an hour. The question is almost never "how good is B?". It's "is B better than A, by how much, and could the gap be luck?" Answering that properly takes the same items on both sides, the right test for the shape of your data, and an interval on the *difference*, not two intervals side by side.

> **Compare on the same items, report the confidence interval of the difference, and never declare a winner whose interval crosses zero.**

```
  HOW TO COMPARE
  ─────────────────────────────────────────────────────────────────────────
  Same items on both sides?
     ├─ NO  → re-run so they are (B1). Unpaired is the last resort.
     └─ YES → What does each item produce?
                ├─ pass/fail          → McNemar on discordant pairs (B3)
                ├─ a score / metric   → paired bootstrap of the difference (B1, B6)
                ├─ "which is better"  → pairwise judging, both orders (B2)
                └─ 5+ candidates      → Bradley–Terry with rank intervals (B4)
     Items come in groups (docs, conversations)?  → resample groups (B7)
     Reading someone else's table?                → compute the margin first (B5)
```

**Rule of thumb:** *the worst-case 95% margin on a percentage is about 100/√n points.* At n = 100 that's ±10, at n = 400 it's ±5, and at n = 2,500 it's ±2. If the gap you're excited about is smaller than that, you haven't shown it's real.

---

# B1 – PAIRED EVALUATION + PAIRED BOOTSTRAP CI

## What it is
You run both versions on exactly the same items and analyse the per-item difference. To get a confidence interval, you resample items with replacement and compute *both* systems' scores on each resample, which gives an interval on the difference itself.

## Why it beats everything else
Most of the variance in an eval score comes from item difficulty, not from the system. Pairing cancels that variance, because each item is compared against itself. On 400 items where A scored 78% and B scored 81%, the unpaired 95% CI of the difference was **[−2.6, +8.6]**, which looks like noise. The paired CI on the same data was **[+0.2, +5.8]**, which is a real win. Nothing changed except the analysis, and in practice pairing is often worth more than doubling n.

## How to do it properly
1. **Freeze the item set** and run every version on it. Never compare "last month's run" with "this week's run" on a refreshed set.
2. **Store per-item results**, not just the aggregate. You can't pair what you didn't save.
3. **Bootstrap the difference:** draw 5,000 resamples of item IDs, compute `score_B − score_A` on each, and take the 2.5th and 97.5th percentiles.
4. **Read the losers.** List the items where B is worse than A. A net +3 can hide 30 regressions concentrated in one slice.
5. **Decide in advance what counts as a win:** a CI lower bound above 0, or above your minimum worthwhile effect (for example +1 point).

## Real scenarios

**Fintech – loan-eligibility explainer, prompt v3 vs v4**
- **Input:** v3 was evaluated in August on 400 applicant profiles. v4 was evaluated in September on 400 profiles from a refreshed set.
- **Output:** v3 81%, v4 79%. The team drafted a rollback of v4.
- **Verdict:** The September set had 3× more self-employed applicants with irregular ITRs, which are much harder cases. When both prompts were re-run on the *same* September items, v4 beat v3 by **+3.0 points (paired CI [+0.2, +5.8])**, with 22 items improved and 10 regressed. The apparent regression came entirely from the harder item set. v4 stayed.

**E-commerce – search query rewriter**
- **Input:** 1,200 real search queries, old vs new rewriter, judged for relevance of the top-5 results.
- **Output:** Net +2.1 points, with the paired CI clear of zero.
- **Verdict:** Pairing made it possible to read the 41 items where the new rewriter lost. **34 of the 41 were Hindi-script or Hinglish queries** ("ladies kurti 500 ke andar"), where it was "fixing" the grammar into English and dropping the price constraint. The aggregate would have shipped a regression for 11% of traffic. The rewriter shipped with a language guard.

## The mistake people make
Comparing two percentages from runs on different item sets, or computing a separate CI for each system and eyeballing whether they overlap. Overlap between two separate intervals is far more conservative than the interval of the paired difference.

## The line to use in a meeting
*"Each system was tested on the same 400 cases, and B is ahead on the case-by-case difference. That's a much stronger test than comparing two averages."*

---

# B2 – PAIRWISE PREFERENCE JUDGING WITH A POSITION SWAP

## What it is
A judge (a model or a person) sees two outputs for the same input and picks the better one, or declares a tie. Every pair is judged twice, as A-then-B and as B-then-A. A win only counts when both orders agree.

## Why it matters
Absolute scoring can't separate outputs that are both good. **Both answers get 8/10 even when one is clearly better**, because a 1–10 scale compresses near the top. Asking "which is better?" is an easier and more reliable judgement for humans and models alike. On 300 lease-summary pairs judged in both orders, B won 58%, A won 30% and 12% were ties. The absolute scores had been 8.1 vs 8.2.

## How to do it properly
1. **Judge both orders, always.** Position bias typically flips 10–30% of verdicts.
2. **Count a flip as a tie.** A judge that changes its mind when you swap the order has no real preference on that pair.
3. **Allow an explicit tie option** with a definition ("both equally correct and complete"). A forced choice turns ties into noise.
4. **Watch the flip rate. Above 10–15%, the judge is unreliable for this comparison.** Tighten the criteria before trusting any win rate.
5. **Report the win rate with a CI** from a bootstrap over pairs, and state the tie rate.
6. **Check whether length explains the win** (see Section E3) before announcing it.

## Real scenarios

**Legal – commercial lease summariser**
- **Input:** A 40-page lease for a Bengaluru office, with summaries from two prompt versions.
- **Output:** Absolute judge scores of 8.1 (A) and 8.2 (B).
- **Verdict:** In pairwise mode, 21% of verdicts flipped when the order was swapped, which is above the 15% line. The judge was told to "prefer the summary that correctly states the lock-in period and escalation clause", and the flip rate fell to 7%. With flips counted as ties, B won **58% to 30%**. B reliably named the 36-month lock-in and 5% annual escalation, while A often called it "standard lock-in". The absolute scores had shown no difference.

**Insurance – claim-denial letter generator**
- **Input:** 250 denied health claims, with letters from the old and new prompts.
- **Output:** The new prompt won 64% of pairs, with a flip rate of 9%.
- **Verdict:** The new letters averaged 190 words more. Re-judging on 80 pairs trimmed to equal length gave a win rate of **52%**, which is a coin flip. The judge was preferring longer letters, and the policyholders reading them on a phone would not have. The team rewrote the prompt to be shorter first and compared again.

## The mistake people make
Running pairwise in one order only. The position bias then decides the winner, which is often whichever system the harness put first.

## The line to use in a meeting
*"Every pair was judged twice with the order swapped, and we only counted wins where both orders agreed."*

---

# B3 – McNEMAR'S TEST

## What it is
A significance test for two paired pass/fail results. It uses only the **discordant** items: b, where the old version was right and the new one wrong, and c, where the old was wrong and the new right. With continuity correction, χ² = (|b − c| − 1)² / (b + c), with 1 degree of freedom.

## Why it matters
The two-proportion z-test that most people reach for assumes independent samples. Evaluating both systems on the same items breaks that assumption, so the p-value is wrong. McNemar also shows you what actually changed: items both versions got right or both got wrong tell you nothing about the difference.

## How to do it properly
1. **Build the 2×2 table** from per-item results: both right, both wrong, b and c.
2. **Check the discordant count.** **At least 25 discordant pairs (b + c ≥ 25) are needed for the χ² approximation.** Below that, use the exact binomial test on b against b + c at p = 0.5.
3. **Compute χ² with continuity correction.** Compare it with 3.84 (p = 0.05) or 6.63 (p = 0.01).
4. **Read the b cell.** These are your regressions. A significant win with 40 regressions can still be unshippable if those 40 are the expensive cases.

## Real scenarios

**Insurance – motor-claim fraud flag, old vs new classifier**
- **Input:** 500 motor claims labelled by the SIU team.
- **Output:** Old 80% correct, new 85%. b = 40, c = 65.
- **Verdict:** χ² = (|40 − 65| − 1)² / 105 = **5.49, p ≈ 0.019**, so the new model is better. Reading the 40 regressions changed the ship plan: **31 of them were claims above ₹5 lakh**, where the new model had learned to trust garage-network invoices. It shipped with a rule that routes claims above ₹5 lakh through the old model, and value-weighted recall rose as well.

**Healthcare – discharge-summary medication checker**
- **Input:** 300 discharge notes, old vs new checker.
- **Output:** 88.0% vs 90.7%, with b = 3 and c = 11.
- **Verdict:** The analyst ran uncorrected χ² = 64/14 = 4.57 and got **p = 0.033**, so the change was declared significant. But b + c = 14, which is below 25. The exact binomial gives **p = 0.057**. The change wasn't shown to be significant. The team labelled another 300 notes, found 29 discordant pairs in total (b = 8, c = 21), got p = 0.03 by McNemar, and shipped with evidence behind it.

## The mistake people make
Running a two-proportion z-test (or χ² on the two accuracies) on paired data, or using the χ² approximation with a handful of discordant pairs.

## The line to use in a meeting
*"Only the 105 claims where the models disagreed tell us anything. The new model won 65 of them and lost 40, and that's significant."*

---

# B4 – BRADLEY–TERRY (OR ELO) WITH BOOTSTRAP CIs

## What it is
When you're ranking five or more options, you collect pairwise win/loss data and fit a latent "strength" for each option, with P(i beats j) = sᵢ / (sᵢ + sⱼ). Refitting on bootstrap resamples of the comparisons gives an interval for each option's rank.

## Why it matters
If you average absolute scores from different judges or different days, the ranking is arbitrary. A bare rank also hides the fact that ranks 2–4 are statistically tied. Bradley–Terry uses every comparison, handles options that never met directly, and shows where the ranking actually has a gap and where it's a tie.

## How to do it properly
1. **Design the comparisons:** cover all pairs, or a connected random design, with at least 50–100 judgments per pair.
2. **Swap positions** for every judgment (see B2) and count flips as ties.
3. **Fit Bradley–Terry by maximum likelihood**, not sequential Elo. Online Elo depends on the order of the matches.
4. **Bootstrap 1,000× over comparisons** and report a 95% interval for each option's rank.
5. **Group options whose rank intervals overlap into tiers.** Within a tier, choose on cost, latency or maintainability.

## Real scenarios

**HR – gender-neutral job-description rewriter, 6 prompts**
- **Input:** All 15 pairs × 100 judgments = 1,500 comparisons.
- **Output:** Point ranking P3 > P1 > P5 > P6 > P2 > P4.
- **Verdict:** Only P3 was clearly first, with a rank interval of [1, 1]. P1, P5 and P6 had overlapping intervals of [2, 4], so they formed one tier. The team had planned a week of polishing P1. Instead they dropped it, because P3 was clearly best. For a cheap fallback they chose P6, the shortest prompt in the tied tier and ₹0.8 lakh a year cheaper in tokens.

**Telecom – Hindi IVR response styles, 5 candidates**
- **Input:** 2,000 pairwise judgments collected over a week.
- **Output:** The team's online Elo leaderboard put Style C first.
- **Verdict:** Replaying the same 2,000 matches in 10 random orders changed the top spot **3 times out of 10**. The Elo ranking depended on the order the matches happened to be played in. A Bradley–Terry fit on the same data put C and A in a tie at the top with overlapping intervals, and C was 40% more expensive per call. A shipped.

## The mistake people make
Treating a sequential Elo table as a ranking and quoting ranks without intervals.

## The line to use in a meeting
*"We have one clear winner and three options that are tied. Ranking inside the tie would be ranking noise, so we choose among them on cost."*

---

# B5 – COMPUTE THE CI FROM n BEFORE READING THE GAP

## What it is
Before you interpret a difference on anyone's leaderboard or dashboard, compute the margin from the sample size: SE = √(p(1−p)/n), and the 95% margin is ±1.96·SE. It takes ten seconds and a calculator.

## Why it matters
**Teams pick a model over a 0.8-point gap that sits well inside the noise.** Public leaderboards rarely show intervals, and internal dashboards almost never do. At n = 500 and p = 0.85, SE = 1.6 points, so the margin is ±3.1. Models at 85.2 and 84.4 are indistinguishable.

## How to do it properly
1. **Find n.** If the leaderboard doesn't state the test-set size, treat its rankings as unverified.
2. **Compute the margin for each score.** Shortcut: ±100/√n points at worst, or ±80/√n near 80%.
3. **If the gap is smaller than about 1.4× the per-score margin, treat it as a tie.** Two independent CIs of that width overlap enough that the difference isn't shown.
4. **Break the tie on your own paired set** (B1). Your 300 items are worth more than their 5,000.

## Real scenarios

**Telecom – Hindi call-centre summarisation model choice**
- **Input:** A public leaderboard showing Model P at 85.2 and Model Q at 84.4 on a 500-item multilingual summary benchmark.
- **Output:** Procurement had already started paperwork for P.
- **Verdict:** The ±3.1 margin put the 0.8 gap far inside the noise. On 400 of the operator's own call transcripts, graded in pairs, **Q beat P by 4.2 points (paired CI [+1.9, +6.5])**, mainly on code-switched Hindi–English segments, which the public benchmark barely included. Q shipped. The leaderboard gap was noise, and it also pointed the wrong way.

**Logistics – weekly dashboard for an address-parsing model**
- **Input:** A weekly score on 120 hand-labelled addresses.
- **Output:** "+5 points this week!" was posted in the team channel.
- **Verdict:** At n = 120 and p ≈ 0.8, the margin is **±7.2 points**. Over the previous 10 weeks the score had moved between 73 and 86 with no model change. The dashboard was reporting sampling noise. The fixed weekly set grew to 600 addresses, giving a margin of ±3.2, and the chart now shows the interval.

## The mistake people make
Reading the rank column. Two numbers next to each other on a leaderboard can be the same number.

## The line to use in a meeting
*"With 500 test items, the margin is ±3 points. The gap is 0.8, so this leaderboard doesn't show which model is better."*

---

# B6 – BOOTSTRAP CONFIDENCE INTERVAL FOR "WEIRD" METRICS

## What it is
You resample items with replacement 1,000–10,000 times, recompute the metric on each resample, and take the 2.5th and 97.5th percentiles as the 95% CI. It works for any metric you can compute: macro-F1, nDCG, ratios, ₹ per outcome.

## Why it matters
There's no textbook formula for the variance of macro-F1, nDCG or a ratio metric. So people report a bare point estimate like "macro-F1 0.71", which implies a precision nobody measured. Over 5,000 resamples, that 0.71 came out as **[0.66, 0.75]**. That tells you a +0.02 improvement is noise.

## How to do it properly
1. **Resample the unit that was sampled.** That's usually items, and clusters if they're grouped (B7).
2. **For comparisons, resample once and compute both systems on the same resample.** That gives the CI of the *difference*, which is paired.
3. **Use 5,000 resamples for reporting** and 1,000 while iterating.
4. **Watch small classes.** Bootstrap each class's F1 as well. A macro average treats a 9-example class the same as a 900-example one.
5. **Fix the random seed** so the CI is reproducible in the review.

## Real scenarios

**E-commerce – return-reason classifier across 14 categories**
- **Input:** 2,100 returns, comparing v1 and v2.
- **Output:** Macro-F1 went from 0.71 to 0.74, and the team called it a win.
- **Verdict:** The paired bootstrap of the difference was [−0.01, +0.07]. Per-class bootstraps showed why: the "counterfeit suspected" class had 9 examples and an F1 CI of **[0.20, 0.78]**. Two more correct predictions there moved macro-F1 by 0.02 on their own. The whole "improvement" came from a class too small to measure. The team labelled 150 more counterfeit cases before re-comparing.

**Fintech – collections bot, ₹ recovered per 1,000 calls**
- **Input:** 6,000 calls on each script.
- **Output:** The new script recovered ₹3.1 lakh per 1,000 calls against ₹2.7 lakh for the old one, a gain of about 15%.
- **Verdict:** Recoveries are heavily skewed, and one call recovered ₹4.2 lakh on its own. The bootstrap CI of the difference was **[−₹0.2 lakh, +₹0.9 lakh]**. With that single call removed, the gain fell to ₹0.2 lakh. The script is still in test, and the metric is now reported with a trimmed-mean check alongside it.

## The mistake people make
Reporting a ratio or macro average to two decimal places with no interval, then acting on a change in the second decimal.

## The line to use in a meeting
*"Macro-F1 is 0.71, somewhere between 0.66 and 0.75. A gain of 0.03 on this set isn't something we can distinguish from noise yet."*

---

# B7 – CLUSTER BOOTSTRAP

## What it is
When items come in groups (10 questions per contract, 8 turns per conversation, 20 fields per invoice), you resample whole groups rather than individual items. Items from the same group stay together in every resample.

## Why it matters
Ten questions about one contract are not ten independent observations. If the model misreads that contract's structure, it gets all ten wrong. An item-level CI treats them as independent, so it comes out **too narrow**, and you get confidence you haven't earned. The fix is a design-effect correction:

**Rule of thumb:** *effective n ≈ n / (1 + (m − 1)·ρ)*, where m is the number of items per cluster and ρ is the within-cluster correlation. With m = 10 and ρ = 0.4, 1,000 questions carry the information of only **217**.

## How to do it properly
1. **Tag every item with its cluster ID** (document, conversation, customer or template).
2. **Resample cluster IDs with replacement** and include all items from each chosen cluster.
3. **Compare the item-level and cluster-level CI widths.** A ratio above about 1.5× means clustering matters, so report the cluster CI.
4. **Check whether a few clusters drive the difference.** Compute the per-cluster difference and look at its distribution.
5. **To add power, add clusters, not items per cluster.** The 11th question on the same contract adds little.

## Real scenarios

**Legal – QA over 100 vendor contracts, 10 questions each**
- **Input:** v1 vs v2 of the contract-QA prompt on 1,000 questions.
- **Output:** +3.8 points. With item-level CI ±2.4, it looked significant.
- **Verdict:** The cluster CI was **±5.1**, the same 2.1× widening the design-effect formula predicts at ρ = 0.4, so the gain wasn't significant. Per-contract differences showed that **60% of the gain came from 4 contracts**, all built on one long MSA template that v2 happened to parse better. The team added 60 more contracts from different templates before deciding.

**Telecom – multi-turn support bot, turn-level grading**
- **Input:** 2,000 bot turns from 250 conversations, grading "correct next action".
- **Output:** 86% correct, reported as "86 ± 1.5".
- **Verdict:** The cluster bootstrap over conversations gave **±3.4**. Once a conversation went wrong at turn 2, turns 3–8 usually failed too. The team switched the headline metric to *conversation-level* success, 71% ± 5.6 on 250 conversations. That number was less flattering, and it was the one CSAT actually tracked.

## The mistake people make
Treating 1,000 questions drawn from 100 documents as 1,000 independent data points.

## The line to use in a meeting
*"We have 1,000 questions but only 100 contracts. The contracts are what we sampled, so the interval has to be computed over contracts."*

---

# SECTION B DECISION FLOW

```
START: You have two or more versions to compare.
│
├─ Are both evaluated on the SAME items?
│     ├─ NO → Can you re-run them on the same items?
│     │        ├─ YES → do it, then continue below
│     │        └─ NO  → unpaired CI; expect ~2× wider; report it honestly
│     └─ YES ↓
│
├─ Are items grouped (docs, conversations, customers)?
│     └─ YES → resample GROUPS for every CI below (B7)
│
├─ How many versions?
│     ├─ 5+ → pairwise judgments, both orders → Bradley–Terry + rank CIs (B4)
│     │        └─ overlapping ranks = one tier → choose on cost
│     └─ 2 ↓
│
├─ What does each item produce?
│     ├─ pass/fail → McNemar (B3)
│     │        └─ b + c < 25? → exact binomial instead
│     ├─ a numeric metric (F1, nDCG, ₹, latency) → paired bootstrap of the difference (B1/B6)
│     └─ "which is better" (open-ended) → pairwise judge, both orders (B2)
│              └─ flip rate > 10–15%? → tighten criteria before trusting any win rate
│
├─ Reading someone else's numbers?
│     └─ margin ≈ 100/√n points → gap < 1.4 × margin? treat as a tie (B5)
│
└─ Winner declared only if the CI of the DIFFERENCE excludes 0
         (or excludes your minimum worthwhile effect). Then read the regressions.
```

---

# THE THREE THINGS TO REMEMBER

1. **Pair everything.** Running both versions on the same items is the cheapest statistical power you'll ever get, often worth more than doubling n.

2. **Put the interval on the difference, not on each score.** A winner exists only when that interval excludes zero, and then you still read the items that got worse.

3. **Count what you actually sampled.** 1,000 questions from 100 contracts is 100 samples, and a leaderboard gap below 100/√n points is noise.
