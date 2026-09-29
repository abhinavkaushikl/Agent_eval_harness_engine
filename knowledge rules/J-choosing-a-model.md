# SECTION J – CHOOSING A MODEL
### Benchmarks shortlist. Your own eval decides.

You are here when you have to pick a model, replace one, or respond to a vendor who says theirs is better. There are 15 candidates, a leaderboard, three vendor decks with "state-of-the-art" on slide 2, and a deadline. Public benchmarks help you rule out models that clearly can't do the job. They can't tell you which model is best for your task, your data, your languages, your latency budget and your ₹ per request. Model choice is a funnel. Cheap filters remove most candidates, and an expensive eval on your own data picks the winner from the few that remain.

> **Use public numbers to shortlist and your own paired eval to decide, and when models are statistically tied, pick the cheapest one.**

```
  THE MODEL-SELECTION FUNNEL
  ─────────────────────────────────────────────────────────────────────────────
  15 candidates
     │  Hard constraints: price, p95 latency, context, languages,
     │  data residency, licence, availability                        (J1)
     ▼
   ~9 viable
     │  50-item smoke test on YOUR domain                            (J1)
     ▼
   ~4 finalists
     │  300–500 item paired eval + human pairwise on top 2           (J2)
     │  Normalise setups; replicate vendor claims                    (J4, J5)
     ▼
  Cost–quality frontier → cheapest model inside the best one's CI    (J3)
  ─────────────────────────────────────────────────────────────────────────────
```

**Rules of thumb:**
- *Cheapest model inside the best model's CI.* If you can't show a quality difference, pay for the cheaper model.
- *A 50-item smoke test catches disqualifying failures, not small differences.* Its margin is ±14 points, which is fine for eliminating candidates and useless for choosing between close ones.
- *A difference in eval setup can outweigh a difference between models.* 5-shot CoT vs 0-shot can be worth 5+ points, so never compare numbers produced under different setups.

---

# J1 – HARD-CONSTRAINT FILTER → 50-ITEM SMOKE TEST

## What it is
First, eliminate candidates on non-negotiables: price ceiling, p95 latency, context length, language support, data residency, licence and regional availability. Then run the survivors through a **50-item domain smoke test** to remove any that fail obviously on your task.

## Why it matters
**A full eval of 15 models spends weeks on candidates that were never viable.** A model that can't legally process your data in India, or that takes 6 seconds at p95 when your IVR allows 2, is out whatever its quality. Constraints cost nothing to check. Evals cost labels, judge calls and time.

## How to do it properly
1. **Write the constraints down with owners.** Legal owns residency, infra owns latency, finance owns price. This prevents arguments later.
2. **Measure latency yourself** from your region, with your prompt length, at p95. Vendor latency figures come from their own region with short prompts.
3. **Build the smoke test from your hardest real items:** 50 items, including 10 in regional languages and 10 edge cases.
4. **Eliminate on disqualifying failures only,** such as below 50% accuracy, broken formatting or wrong language. With a ±14-point margin at n = 50, don't rank models on the smoke test.
5. **Aim for 3–5 finalists.**

## Real scenarios

**Fintech – lending platform with RBI data-localisation requirements**
- **Input:** 15 candidate models for a loan-document assistant.
- **Output:** The team was preparing a 400-item eval for all 15, estimated at ₹3.5 lakh in labels and 3 weeks.
- **Verdict:** Constraints went first. **India data residency removed 4**, and **p95 latency ≤ 2 seconds** from Mumbai with a 6k-token prompt removed 2 more, leaving 9. The 50-item smoke test, which included handwritten salary slips and Marathi bank statements, removed 5 that scored below 50% or produced broken JSON. **4 finalists** went to the full eval. That saved about 70% of the eval budget and two weeks.

**Telecom – Hindi IVR assistant**
- **Input:** 8 candidates passed the paper constraints.
- **Output:** Everyone expected the top leaderboard model to win.
- **Verdict:** Measured from an Indian region with streaming, the leaderboard leader's **p95 time-to-first-token was 2.8 seconds** against a 1.2-second budget. Callers hang up during long silences. It was eliminated before any quality testing. The final choice was ranked 6th on the public leaderboard.

## The mistake people make
Evaluating every model on quality before checking whether it's deployable.

## The line to use in a meeting
*"Six of the fifteen can't be deployed because of data residency or latency. We only evaluate models we could actually ship."*

---

# J2 – FULL DOMAIN EVAL (300–500 ITEMS) WITH PAIRED STATS + HUMAN PAIRWISE ON THE TOP 2

## What it is
The finalists run on the same 300–500 items from your domain (Section I8), graded with a validated grader (Sections A and F), and compared with paired statistics (Section B). The top two then get **100 human pairwise judgments** as a final check that the automated grader is measuring what users care about.

## Why it matters
**Small sets can't separate close models, so you end up choosing on noise.** Finalists are, by construction, close. At n = 400 with a paired design you can resolve differences of about 3 points. The human pairwise check catches cases where the automated grader prefers something users don't, such as verbosity (Section E3).

## How to do it properly
1. **Use the same items, prompts and scaffold** for every finalist. Allow a small amount of per-model prompt tuning only if you do the same for all of them.
2. **Include your hard set** (E5) and slice by language and intent.
3. **Report pass rates with Wilson CIs** and **paired CIs of the differences** between finalists.
4. **Run 100 human pairwise judgments** (both orders) on the top two.
5. **Decide in advance:** if the paired CI includes 0, the models are tied, and you choose on cost and latency (J3).

## Real scenarios

**Insurance – claims-summary copilot for assessors**
- **Input:** 4 finalists, 400 claim files, binary-criteria judge validated at κ 0.79.
- **Output:** Model A 83.5%, Model B 82.0%.
- **Verdict:** The paired CI of the difference was **[−0.8, +3.8]**, which includes 0, so the models were tied. In 100 human pairwise judgments by senior assessors, B won 47, A won 41 and 12 were ties, also a tie. B was 35% cheaper and 40% faster at p95. **B shipped.** The pre-agreed tie rule meant the decision took 20 minutes, not a 3-week debate.

**Legal – contract-review assistant**
- **Input:** 3 finalists, 350 clauses.
- **Output:** Model C led on the automated grader by 4.1 points (paired CI [+1.2, +7.0]).
- **Verdict:** In human pairwise with 4 associates, C **lost** to Model A 38–52. The grader rewarded C's longer risk explanations, which associates found padded, and it missed that C cited the wrong sub-clause in 11% of cases. The grader was re-validated, a citation-accuracy criterion was added, and A won on both the grader and the humans.

**E-commerce – multilingual product Q&A**
- **Input:** 4 finalists, 500 items.
- **Output:** Overall scores within 2.5 points of each other.
- **Verdict:** The per-language slices showed Model D at **78% in Tamil** against 61–66% for the others, with its overall score pulled down by slightly weaker English. Tamil Nadu was 14% of traffic and the fastest-growing region, so D shipped with a language-based router that sends English to the cheapest finalist.

## The mistake people make
Choosing between finalists on an unpaired 100-item eval, or treating a lead of 1.5 points as a decision.

## The line to use in a meeting
*"The two finalists are statistically tied on 400 cases, and human reviewers split 47–41. So we choose on cost, and B is 35% cheaper."*

---

# J3 – COST–QUALITY PARETO FRONTIER: THE CHEAPEST MODEL WITHIN THE BEST MODEL'S CI

## What it is
You plot each finalist's quality score against its ₹ cost per 1,000 tasks, or ₹ per *successful* task (H4). Any model whose paired CI against the best model includes 0 counts as **equivalent**. Among equivalent models, choose the cheapest.

## Why it matters
**Teams pay 5× for quality that's statistically indistinguishable.** The top model usually has a small point-estimate lead and a large price premium. At scale, that premium is a line item in the budget.

## How to do it properly
1. **Compute the full cost:** input and output tokens at your real prompt lengths, retries and failed-run costs.
2. **Plot quality against cost** and mark the Pareto frontier.
3. **Test equivalence with a paired CI** of each model against the best.
4. **Check the critical slices separately.** A cheaper model that's equivalent overall may fail a slice you can't compromise on.
5. **Revisit the choice quarterly.** Prices drop and new models arrive.

## Real scenarios

**E-commerce – product-review summarisation over 2 crore reviews**
- **Input:** Model A 86% at ₹1,200 per 1,000 tasks, Model B 84.5% at ₹240.
- **Output:** The team's instinct was to use A because it was the best.
- **Verdict:** The paired CI of A − B was **[−0.4, +3.4]**, so there was no demonstrated difference. B saves ₹960 per 1,000 tasks, which is **₹1.92 crore** over the 2-crore-review backfill, plus ongoing savings. The slice check found B 6 points behind on reviews longer than 500 words, 4% of volume, so those were routed to A. The blended cost was ₹278 per 1,000.

**Healthcare – clinical-note coding (ICD-10 suggestions)**
- **Input:** 3 models with costs of ₹0.90, ₹0.35 and ₹0.12 per note.
- **Output:** All three were within 2 points on accuracy.
- **Verdict:** The paired CIs all included 0. But the must-pass subset of 60 notes (oncology and paediatric codes, where an error has billing and clinical consequences) showed the ₹0.12 model failing **9 of 60**, against 2 of 60 for the others. The ₹0.35 model shipped, the cheapest one that held up on the must-pass subset.

## The mistake people make
Picking the top of the leaderboard, or the top of your own eval, without checking whether its lead is larger than its CI.

## The line to use in a meeting
*"We can't show that the expensive model is any better. The cheaper one is inside its confidence interval and saves ₹1.9 crore on the backfill."*

---

# J4 – SAME BENCHMARK VERSION, SAME SHOTS/CoT, SAME HARNESS, OR RERUN IT YOURSELF

## What it is
Before comparing published numbers, you check that they were produced under the same conditions: benchmark version, number of few-shot examples, chain-of-thought or not, prompt template, answer-extraction method and harness. If they weren't, you rerun them yourself under one setup.

## Why it matters
**A difference in evaluation setup can outweigh the difference between models.** 5-shot CoT against 0-shot direct can move a score by 5–10 points. Vendors each report their best setup, so side-by-side published numbers often aren't comparable.

## How to do it properly
1. **Read the footnotes** for shots, CoT, benchmark version or subset, and whether majority voting was used.
2. **Treat comparisons without matching conditions as unknown,** neither a win nor a loss.
3. **Rerun on one harness** (an open-source evaluation harness, or your own) with identical settings for every model.
4. **Use the setup you'll actually deploy.** If production is 0-shot with no CoT for latency reasons, evaluate 0-shot with no CoT.

## Real scenarios

**Legal – choosing a model for a law-firm research copilot**
- **Input:** Model X "82%" and Model Y "78%" on the same legal-reasoning benchmark, from the vendors' launch posts.
- **Output:** X was shortlisted as clearly better.
- **Verdict:** X's figure was **5-shot CoT** and Y's was **0-shot**. Rerun 0-shot on one harness, as the firm would actually deploy, X scored **77% and Y 78%**. The 4-point "lead" came entirely from the setup. The firm's own 200-item set, not the benchmark, then decided between them.

**HR – resume-screening classifier**
- **Input:** Vendor A reported 91% F1 and Vendor B 86% on the "same" public dataset.
- **Output:** A was preferred.
- **Verdict:** A had reported on **v1** of the dataset, and B on **v2**, which added 2,000 harder, noisier samples. On v2 with identical preprocessing, A scored **85%** and B 86%. Both were then evaluated on 300 of the company's own anonymised applications, where the per-group selection-rate parity check (the four-fifths rule) decided the choice.

## The mistake people make
Putting two vendors' published numbers side by side as if they came from the same test.

## The line to use in a meeting
*"Those numbers were measured under different setups. Rerun under identical conditions, the 4-point gap disappears."*

---

# J5 – REPLICATE VENDOR CLAIMS ON YOUR OWN 100–200 ITEM HELD-OUT SET

## What it is
You take the vendor's model and run it on your real data (100–200 held-out items the vendor has never seen) with your grader, before signing anything.

## Why it matters
**Vendors pick favourable benchmarks, settings and slices, and leave out n and CIs.** "95% on Indian invoices" may mean 95% on clean, printed, English-language invoices from their demo set. Your data includes handwriting, regional scripts, stamps across the text and scans taken on a phone. A vendor number is a claim, and your eval is how you check it.

## How to do it properly
1. **Keep a private held-out set** of 100–200 items that has never been shared with any vendor. Its value depends on staying private.
2. **Stratify it by the difficulty you actually see:** clean vs messy, language, format.
3. **Grade with your own grader** and report Wilson CIs by slice.
4. **Put acceptance criteria into the contract,** measured on your set, for example "field-level accuracy ≥ 88% on the buyer's held-out set".
5. **Re-test on a fresh sample after onboarding** to catch any tuning to your data during the pilot.

## Real scenarios

**Logistics – vendor pitching GST e-way bill and invoice extraction**
- **Input:** The claim was "95% accuracy on Indian invoices."
- **Output:** The procurement team was ready to sign a ₹40 lakh annual contract.
- **Verdict:** On 150 of the company's own invoices, field-level accuracy was **81%**, and on handwritten invoices, 40% of volume from small transporters, it was **64%**. The vendor's 95% had been measured on printed invoices only. The contract was re-scoped with an acceptance clause of ≥ 85% on the company's set including handwritten invoices, and a pilot fee in place of the annual commitment.

**Banking – conversational-AI vendor for vernacular customer service**
- **Input:** The claim was "supports 11 Indian languages with 90%+ intent accuracy."
- **Output:** The demo was flawless in Hindi and English.
- **Verdict:** On 200 real transcripts across 6 languages, accuracy was 91% in Hindi, 89% in English, **72% in Bengali** and **58% in Odia**. The worst slice, not the average, decided the rollout: launch in Hindi and English only, with a contractual roadmap and re-test dates for the other languages.

**Healthcare – radiology report-generation vendor**
- **Input:** The claim was "radiologist-level accuracy," with a published study cited.
- **Output:** The published study used 500 chest X-rays from a US hospital.
- **Verdict:** On 120 of the hospital's own X-rays, taken on older equipment with a higher TB prevalence, radiologists found clinically significant errors in **17% of reports**, against 6% in the vendor's study. TB-related findings drove most of the gap, since the vendor's training data had seen little TB. The pilot was restricted to normal/abnormal triage, with no report generation.

## The mistake people make
Signing on the strength of the vendor's benchmark and running your own evaluation only after the contract is in place, when you have no leverage left.

## The line to use in a meeting
*"They say 95%. On our invoices it's 81%, and 64% on the handwritten ones. We'll sign when the contract guarantees the number measured on our data."*

---

# SECTION J DECISION FLOW

```
START: You need to pick or replace a model.
│
├─ How many candidates?
│     └─ > 5 → hard constraints first: residency, p95 latency (measured from
│              your region), price, context, languages, licence (J1)
│              └─ then 50-item smoke test → eliminate only obvious failures
│
├─ Comparing published numbers?
│     └─ same version, shots, CoT, harness? 
│           ├─ NO  → treat as unknown; rerun under one setup (J4)
│           └─ YES → still just a shortlist signal
│
├─ Vendor making a claim?
│     └─ run their model on YOUR private 100–200 held-out items (J5)
│           └─ acceptance criteria in the contract, measured on your set
│
├─ 2–5 finalists?
│     └─ 300–500 item paired eval, validated grader, slices (J2)
│           ├─ paired CI excludes 0 → a real winner (check slices anyway)
│           └─ includes 0 → tied → go to cost
│           └─ top 2: 100 human pairwise judgments, both orders
│
└─ Final call:
      └─ cheapest model inside the best model's CI (J3)
            └─ must-pass / critical slices hold? → ship
                  └─ not? → route that slice to the model that passes it
```

---

# THE THREE THINGS TO REMEMBER

1. **Public benchmarks shortlist and your own data decides.** Filter on constraints first, and don't trust a number you didn't reproduce under your own setup on your own items.

2. **If you can't show a difference, pay for the cheaper model.** Choose the cheapest model inside the best one's paired CI, then check it holds on the must-pass slices.

3. **Test vendor claims before you sign.** A private held-out set and acceptance criteria in the contract are your only leverage once the deal is done.
