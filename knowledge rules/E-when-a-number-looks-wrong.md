# SECTION E – WHEN A NUMBER LOOKS WRONG
### The diagnostic section. Organised by symptom, not concept.

You are here when a number has surprised you. The score jumped 8 points overnight, dropped to zero, moved when nothing changed, improved with no effect on users, or looks too good to be true. Your instinct is to explain it with the model: it got smarter, it regressed, it's flaky. **Suspect the measurement first.** In practice most surprising eval numbers come from the grader, the parser, the harness, the data or the item set, not from the model. Each subsection below starts from a symptom and ends with the check that identifies the cause.

> **When a number surprises you, suspect the measurement before the model, and read the individual items before you believe the aggregate.**

```
  SYMPTOM                                   FIRST CHECK
  ──────────────────────────────────────────────────────────────────────────────
  Score jumped suddenly                  →  E1 per-item diff, read the flips
  Score up, users didn't notice          →  E2 eval-vs-traffic mix, metric↔KPI link
  Score up, answers got longer           →  E3 length-controlled win rate
  Nothing changed, score moved           →  E4 A/A noise band
  Everyone scores 90%+                   →  E5 harder set from real failures
  Everything scores 0%                   →  E6 oracle run through the harness
  Public benchmark looks too good        →  E7 paraphrase / contamination check
  One model wins one benchmark only      →  E8 3+ benchmarks + your own set
```

**Rules of thumb:**
- *A move inside ±2 SD of identical re-runs is noise.* Measure that band before you investigate anything.
- *A paraphrase drop of more than 5 points means suspect memorisation.*
- *If more than half the flipped items flipped for formatting reasons, the grader changed, not the model.*

---

# E1 – SCORE JUMPED SUDDENLY → PER-ITEM DIFF, THEN READ THE FLIPPED ITEMS

## What it is
You list every item whose verdict changed between the two runs (pass→fail and fail→pass) and read them by hand, tagging *why* each one flipped.

## Why it matters
**Big jumps usually come from a change in the grader, parser, data or leakage, not from the model improving.** An aggregate score tells you it changed but not why. Sixty flipped items read in 30 minutes will tell you whether you have a real improvement or a broken measurement.

## How to do it properly
1. **Diff at item level:** make two lists, newly passing and newly failing.
2. **Read every flip if there are fewer than 100,** or a random 100 otherwise.
3. **Tag each flip:** real improvement, formatting, grader change, data change, or noise (the item also flips between A/A runs).
4. **Only count the "real improvement" tags** as the model's gain.
5. **Check what else changed:** grader version, regex, normaliser, dataset hash, provider model alias.

## Real scenarios

**E-commerce – product Q&A bot after a prompt tweak**
- **Input:** Prompt v7 → v8, same 800 items.
- **Output:** 71% → 79%, reported as "+8 points."
- **Verdict:** 64 items flipped from fail to pass. **51 flipped only because v8 started writing answers as "Answer: …", which matched the grader's regex.** The same answers had been failing on a parsing bug. The real gain was 13 items, **+1.6 points**. The regex was fixed, v7 was re-scored at 77.4%, and v8's honest lead was 1.6 points.

**Fintech – GST query bot after a deploy**
- **Input:** No model or prompt change, just a new container image for the eval runner.
- **Output:** 84% → 76%, and an incident was opened.
- **Verdict:** All 58 newly failing items contained "₹". The new image had a different locale, and the grader's string comparison saw "₹" as "?" in the references. The model was fine. After pinning the locale and adding a Unicode-normalisation test to the grader's CI, the score went back to 84%.

## The mistake people make
Explaining the aggregate ("the new prompt is better") without opening any of the items that flipped.

## The line to use in a meeting
*"Of the 64 items that flipped, 51 changed because of formatting. The real gain is 1.6 points, not 8."*

---

# E2 – SCORE IMPROVED BUT USERS DIDN'T NOTICE → DISTRIBUTION + METRIC–OUTCOME CHECK

## What it is
You compare the eval set's slice mix (language, intent, difficulty) with current production traffic, and check whether eval scores across past releases actually predicted the business KPI.

## Why it matters
**The offline set stops representing real traffic, and you end up optimising a proxy.** Eval sets are built once and traffic keeps changing. If the eval is 80% English and traffic is 55% Hinglish, a big offline gain can be concentrated in the traffic you have least of.

## How to do it properly
1. **Tabulate the slice mix** of the eval set and of 30 days of traffic side by side.
2. **Re-weight the eval score to the traffic mix,** by computing per-slice scores and then weighting them by traffic share.
3. **Plot eval score against the KPI** (CSAT, containment, escalation) across your last 6–10 releases. If the correlation r is below about 0.3, the eval isn't predicting outcomes.
4. **Refresh the eval set** from recent logs every quarter (see Section I8).

## Real scenarios

**Telecom – prepaid recharge support bot**
- **Input:** Release 14: offline +6 points.
- **Output:** CSAT flat at 3.9/5 for three weeks.
- **Verdict:** The eval set was **80% English**, and traffic was **55% Hinglish**. Per slice, English gained +8.1 and Hinglish +1.4. Re-weighted to traffic, the gain was **+4.4**, and most of it was in the English minority. The next quarter's work went to Hinglish, and the eval set was rebuilt to match the traffic mix.

**Insurance – renewal-reminder generator**
- **Input:** Eight releases over a year, each with an offline quality score and a renewal-conversion rate.
- **Output:** The offline score climbed steadily from 71 to 88.
- **Verdict:** The correlation between release score and conversion was **r = 0.12**. The eval graded tone and grammar, while conversions depended on whether the reminder stated the exact premium and due date. Two binary criteria were added for those. On the new rubric, the historical releases' scores correlated with conversion at r = 0.71.

## The mistake people make
Assuming an eval set built last year still represents today's traffic.

## The line to use in a meeting
*"We improved 6 points on an eval that's 80% English. Our users are mostly Hinglish, and for them the gain is closer to 1."*

---

# E3 – SCORE IMPROVED AND ANSWERS GOT LONGER → LENGTH-CONTROLLED WIN RATE

## What it is
You adjust pairwise win rates for the length difference between the two outputs. Either regress the preference on the length difference and report the win rate at zero difference, or re-judge on length-matched pairs.

## Why it matters
**LLM judges prefer longer answers (verbosity bias), so a "quality" win can just be a word-count win.** Longer answers look thorough, but for a user on a phone they're often worse.

## How to do it properly
1. **Log the token count of every output** in every eval run.
2. **If the mean length changed by more than about 20%, compute the length-controlled win rate** before reporting.
3. **Spot-check with length-matched pairs:** truncate or pick pairs within ±10% length and re-judge 50–100 of them.
4. **Add a length constraint to the rubric** if the product has a real length budget (SMS, WhatsApp, IVR).

## Real scenarios

**Insurance – policy-exclusion explainer**
- **Input:** A new prompt vs the old one, 300 pairs judged pairwise.
- **Output:** A raw win rate of **64%** for the new prompt, with answers 140 tokens longer on average.
- **Verdict:** The length-controlled win rate was **51%**, a coin flip. The new prompt had added a generic paragraph on "how exclusions work" to every answer. The claims team found the longer answers *raised* follow-up calls, because customers stopped reading before the specific exclusion. The team rewrote for brevity and kept the specific-exclusion sentence first.

**Healthcare – OPD visit summaries for doctors**
- **Input:** Summariser v2 vs v1.
- **Output:** The judge preferred v2 in 70% of pairs. v2 averaged 310 words and v1 190.
- **Verdict:** On 80 length-matched pairs, v2's win rate was **49%**. Doctors timed on 40 summaries took **38 seconds longer** to read each v2 summary. With 60 patients a day, that's 38 minutes of a doctor's day. v1 stayed.

## The mistake people make
Reporting a pairwise win without checking whether the winner simply wrote more.

## The line to use in a meeting
*"The new version wins 64% of comparisons, but it's 140 tokens longer. Once we control for length, it wins 51%."*

---

# E4 – YOU CHANGED NOTHING BUT THE SCORE MOVED → A/A BASELINE

## What it is
You run the identical configuration 3–5 times to measure the run-to-run noise band. You also check for silent upstream changes: the provider's model version, judge temperature, the dataset hash and library versions.

## Why it matters
**Without a noise floor, you chase ghosts and "fix" random fluctuation.** Teams spend days debugging a 1.5-point drop that's inside the normal variation between identical runs.

## How to do it properly
1. **Run A/A 3–5 times** and compute the SD. The noise band is **±2 SD**.
2. **Store it with the eval,** and re-measure whenever the grader or the provider changes.
3. **Log provenance for every run:** model version string, judge version, temperature, dataset hash, harness commit.
4. **If a move is outside the band, diff the provenance first,** then do the per-item diff (E1).

## Real scenarios

**Legal – NDA clause-classification regression suite**
- **Input:** A release candidate scored 1.5 points below last week's baseline.
- **Output:** A regression ticket blocked the release.
- **Verdict:** Three A/A runs of the *baseline* config gave **81.2, 79.6 and 82.0**, so SD = 1.2 and the ±2 SD band is ±2.4. The 1.5-point drop was inside it. The release went ahead, and the CI gate now fails only when a result falls outside the band.

**E-commerce – catalogue attribute extraction**
- **Input:** No change on the team's side.
- **Output:** Score down **3.4 points**, well outside the ±1.1 A/A band.
- **Verdict:** The provenance diff showed the *judge* was configured as a "latest" alias, and the provider had updated it the night before. The new judge was stricter on partial matches. The extraction model hadn't changed. Pinning the judge to a dated version restored the score, and judge upgrades now go through their own validation (Section F).

## The mistake people make
Investigating a movement before you know how much the score moves on its own.

## The line to use in a meeting
*"The same config scores within ±2.4 points on re-runs. This 1.5-point move is noise."*

---

# E5 – ALL MODELS SCORE 90%+ → BUILD A HARDER SET

## What it is
You collect the items current models fail on in production (hard-negative mining), add adversarial and edge-case variants, and build a separate hard set that spreads the candidates apart.

## Why it matters
**A saturated benchmark compresses real differences into noise.** If five models sit between 91% and 94% on 500 items, the ±2.5-point margin covers the whole range. You'd be choosing a model on noise. The differences that matter live in the tail the easy set doesn't cover.

## How to do it properly
1. **Mine production failures:** escalations, thumbs-down, human corrections, re-asks.
2. **Add perturbations:** negations, multi-part questions, regional spellings, amounts in lakh/crore, conflicting information.
3. **Target 40–70% accuracy for the best current model.** That's hard enough to spread candidates apart without being impossible.
4. **Keep the easy set as a regression floor** and the hard set as the comparison set.
5. **Retire items that every model passes** each quarter.

## Real scenarios

**Fintech – GST query bot for SMEs**
- **Input:** 5 candidate models on a 500-item general GST FAQ set.
- **Output:** 91–94% for all five.
- **Verdict:** A 200-item hard set built from real escalations covered reverse-charge mechanism cases, ITC reversal under Rule 42, and mixed supply with exempt items. It spread the models from **48% to 71%**. The model ranked 4th on the easy set ranked **1st on the hard set**, by 9 points. The easy set had been hiding the difference that mattered.

**Logistics – address normalisation for last-mile delivery**
- **Input:** Three parsers on 1,000 metro addresses.
- **Output:** 95–97% for all three.
- **Verdict:** The team built 300 hard addresses from failed deliveries: rural pin codes, landmark-only addresses ("peepal ke ped ke saamne, school ke peeche") and transliterated Hindi. Scores ranged from **52% to 68%**. Failed-delivery cost is concentrated in exactly those addresses, so the hard set, not the metro set, became the selection criterion.

## The mistake people make
Choosing between models whose scores all sit inside one margin of error on an easy set.

## The line to use in a meeting
*"Everyone gets 93% on the easy questions. On the questions our customers actually escalate, the range is 48% to 71%."*

---

# E6 – NOTHING COMPLETES AT ALL → ORACLE RUN THROUGH THE HARNESS

## What it is
You feed a known-correct solution (a scripted perfect agent, the reference answers or a gold trajectory) through the same pipeline. If the oracle doesn't score 100%, the harness is broken.

## Why it matters
**A 0% score is usually a timeout, tool-schema or environment bug, and it gives you nothing to learn from.** Teams spend days tweaking prompts to fix a score the model has no way to affect.

## How to do it properly
1. **Build an oracle for every new eval:** a script that performs the correct actions or returns the gold answer.
2. **Run it before running any model.** It should score 100%, or close to it with known exceptions.
3. **When it fails, read the harness logs:** timeouts, schema mismatches, missing environment state, grader parse errors.
4. **Keep the oracle in CI** so harness changes can't silently break the eval.

## Real scenarios

**Logistics – shipment-booking agent on a carrier-portal sandbox**
- **Input:** 50 booking tasks.
- **Output:** **0/50.** The team had started comparing larger models.
- **Verdict:** The scripted oracle also scored 0/50. The harness had a **30-second timeout**, and the sandbox portal took **90 seconds** to confirm a booking. With the timeout raised to 180 seconds, the original model scored **34%**. The week spent comparing larger models had been spent on a timeout setting.

**Telecom – plan-change agent**
- **Input:** 80 tasks, with every run failing at the "apply plan" step.
- **Output:** 0%.
- **Verdict:** The oracle failed too. The tool schema declared `plan_type` as an enum of `"POSTPAID" | "PREPAID"`, while the sandbox API accepted only lowercase values. Every correct call returned HTTP 400. After fixing the schema, the agent scored **61%**, and the oracle went into CI.

## The mistake people make
Iterating on the model when the harness can't score a perfect answer.

## The line to use in a meeting
*"Before we blamed the model, we ran a perfect answer through the pipeline. It scored zero too, so the pipeline was broken."*

---

# E7 – PUBLIC BENCHMARK SCORE LOOKS TOO GOOD → CONTAMINATION CHECK

## What it is
You rewrite benchmark items so the answer stays the same but the wording changes (paraphrase, reordered options, changed numbers), then compare scores. You add n-gram overlap checks and, for your own sets, canary strings.

## Why it matters
**If the model memorised the test set, the score measures recall of those items, not ability.** Public benchmarks leak into training data. A model that scores 88% on the original items and 71% on paraphrased copies was scoring partly on memory.

## How to do it properly
1. **Paraphrase 200–300 items,** keeping the answers identical, and have a human verify equivalence.
2. **For MCQs, shuffle the option order** as well.
3. **Compare scores. A drop of more than 5 points means suspect memorisation.** More than 10 points is near-certain.
4. **Check 13-gram overlap** between the benchmark and any available training or corpus data.
5. **For your own sets, embed a canary string** and never publish the set.

## Real scenarios

**Healthcare – vendor model on NEET-PG-style medical MCQs**
- **Input:** The vendor quoted 88% on a public 300-item set.
- **Output:** The hospital group was ready to sign.
- **Verdict:** On paraphrased copies with shuffled options, the score was **71%**, a **17-point drop**. On 150 fresh questions written by the hospital's own faculty, it scored 69%. The contract was renegotiated with acceptance tied to the hospital's private set.

**Legal – contract-reasoning benchmark**
- **Input:** Model M led a public legal-reasoning benchmark by 11 points.
- **Output:** A law firm shortlisted it.
- **Verdict:** A 13-gram overlap check found **34% of the benchmark's passages** in a public web crawl that M's vendor lists as training data. On the non-overlapping 66% of items, M's lead fell to **2 points (CI [−1.8, +5.8])**, which is a tie. The firm built a 200-item private set from its own anonymised matters.

## The mistake people make
Treating a public benchmark score as independent evidence when the test items may have been in the model's training data.

## The line to use in a meeting
*"When we rewrote the same questions, the score dropped 17 points. The model had memorised the questions, not learned the subject."*

---

# E8 – ONE MODEL DOMINATES ONE BENCHMARK ONLY → 3+ BENCHMARKS + YOUR OWN SET

## What it is
Before believing a single-benchmark lead, you check how the model ranks on at least three independent benchmarks and on your own internal set.

## Why it matters
**A lead on one benchmark usually means the model was tuned to that benchmark's format, not that it's generally better.** Vendors optimise for the benchmarks that appear in their launch posts. If the ranking isn't consistent across benchmarks, the lead probably won't carry over to your task either.

## How to do it properly
1. **Collect ranks on 3+ benchmarks** relevant to your task type.
2. **Add your own 200–300 item internal set** (Section J).
3. **Look at the ranks, not the scores.** A model ranked 1st on one benchmark and 4th everywhere else is a specialist, not a leader.
4. **Weight your own set highest.** It's the only one drawn from your data.

## Real scenarios

**E-commerce – catalogue attribute extraction (fabric, fit, sleeve type)**
- **Input:** Model X led public benchmark A by 9 points.
- **Output:** It was proposed as the default model.
- **Verdict:** X ranked **4th of 6 on three other benchmarks** and 4th on the marketplace's own 300-item set. Benchmark A was MCQ-style extraction, and X's vendor had published fine-tuning on that exact format. On free-form product descriptions, X was 6 points *behind* the leader. X was dropped.

**Telecom – Hindi generation for customer notifications**
- **Input:** A model topped a Hindi benchmark.
- **Output:** It was shortlisted for SMS and WhatsApp notifications.
- **Verdict:** That benchmark was multiple-choice comprehension. On two generation benchmarks and 250 of the operator's own notification templates, the model ranked **3rd and 5th**, with frequent unnatural Sanskritised phrasing that customers in a pilot rated 2.8/5 against 4.1 for the leader. Understanding Hindi and writing natural Hindi turned out to be different skills.

## The mistake people make
Picking a model because of its best benchmark, which is the one its vendor chose to show you.

## The line to use in a meeting
*"It's first on one benchmark and fourth on three others and on our own data. It's a specialist in that benchmark's format."*

---

# SECTION E DECISION FLOW

```
START: A number looks wrong. Do NOT touch the model yet.
│
├─ Do you know the A/A noise band?
│     └─ NO → run identical config 3–5×; band = ±2 SD (E4)
│              └─ move inside band? → STOP. It's noise.
│
├─ Score went to 0% (or near)?
│     └─ oracle run through the harness (E6)
│           └─ oracle fails → harness bug (timeout, schema, env)
│
├─ Score jumped / dropped outside the band?
│     └─ provenance diff (model alias, judge, locale, dataset hash)
│           └─ then per-item diff; read the flips (E1)
│                 └─ >50% formatting/grader flips → the measurement changed
│
├─ Score up but KPI flat?
│     └─ eval-vs-traffic slice mix; re-weight; metric↔KPI correlation (E2)
│
├─ Score up and outputs longer?
│     └─ length-controlled win rate (E3)
│
├─ Everyone ≥ 90%?
│     └─ hard set from production failures; target 40–70% (E5)
│
└─ Public benchmark looks great?
      ├─ paraphrase drop > 5 pts → contamination (E7)
      └─ leads only one benchmark → check 3+ and your own set (E8)
```

---

# THE THREE THINGS TO REMEMBER

1. **Suspect the measurement before the model.** Graders, regexes, locales, timeouts and judge aliases cause more surprising numbers than models do.

2. **Know your noise band before investigating anything.** A move inside ±2 SD of identical re-runs is noise, not a finding.

3. **Read the items that moved.** Half an hour reading 60 flipped items settles questions a week of aggregate analysis can't.
