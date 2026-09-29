# SECTION F – TRUSTING YOUR GRADER
### Your judge is a measuring instrument. Instruments need calibration.

You are here when an LLM judge or a team of human labellers is producing the numbers your decisions rest on, and nobody has measured how often the grader is right. Maybe you just wrote a judge prompt. Maybe the judge's scores cluster at 7–8. Maybe two annotators keep disagreeing and you're not sure whose labels to believe. An uncalibrated grader doesn't just add noise. It adds *systematic* error, and then you optimise the model toward the grader's quirks. Every other section assumes the grader is sound. This section is how you check.

> **You can't trust a grader's scores until you've measured its agreement with humans on your own data, per class and per criterion, and humans can't be trusted until they agree with each other.**

```
  THE CALIBRATION STACK (fix from the bottom up)
  ─────────────────────────────────────────────────────────────────────
  4  Judge accuracy boosters   few-shot from disagreements, majority-of-3  (F8)
  3  Judge bias controls       position swap, cross-family panel           (F4, F5)
  2  Judge design              binary criteria, one call per criterion     (F6, F7)
  1  Judge validation          150–200 gold labels; κ + per-class P/R      (F1, F2)
  0  Human gold quality        codebook, calibration rounds; κ / α         (F9, F3)
  ─────────────────────────────────────────────────────────────────────
  Human–human agreement is the ceiling. No judge can be validated above it.
```

**Thresholds to state out loud:**
- *κ ≥ 0.6* before using a grader at all, and *κ ≥ 0.8* before letting it gate a release.
- *Krippendorff's α ≥ 0.667* for tentative conclusions and *≥ 0.8* for reliable ones.
- *A position-flip rate above 10–15%* means the judge can't make this comparison.

---

# F1 – VALIDATE AGAINST 150–200 HUMAN GOLD LABELS BEFORE USE

## What it is
Domain-competent humans label a stratified sample of 150–200 outputs using the same rubric the judge uses. You compare the judge's verdicts with theirs item by item, including per class, before the judge scores anything that matters.

## Why it matters
**An unvalidated judge has systematic quirks, and you end up optimising your model toward them.** Overall agreement hides where the judge fails. A judge can be 84% accurate overall and still miss half of the bad outputs, because most outputs are fine and the judge mostly says "fine".

## How to do it properly
1. **Stratify the sample:** include enough "fail" cases, at least 50, even if that means over-sampling from known failures.
2. **Keep the humans blind to the judge's verdicts.**
3. **Report the confusion matrix,** plus the judge's recall on "fail". That's the number that tells you whether it catches problems.
4. **Keep 30% of the gold set held out** to validate prompt changes, so you don't tune the judge to its own test.
5. **Re-validate** when the judge model, the rubric or the product domain changes.

## Real scenarios

**Fintech – judge for loan-collection messages under the RBI Fair Practices Code**
- **Input:** 200 collection messages, double-labelled by the compliance team.
- **Output:** Judge accuracy 84%, and it was about to be deployed as the compliance gate.
- **Verdict:** Of the 48 human-labelled violations, the judge caught 25, a **recall of 52%**. It missed implicit threats in Hinglish ("aapke office mein sabko pata chal jayega"), which read as polite to a model but are exactly what the Fair Practices Code prohibits. Deploying it would have passed half of the violations. After adding violation-specific few-shot examples (F8), recall on the held-out 60 reached 88%.

**Legal – judge for clause-extraction completeness**
- **Input:** 160 outputs labelled by two associates.
- **Output:** 91% agreement.
- **Verdict:** Per class, the judge was near-perfect on short NDAs and **62% accurate on MSAs longer than 30 pages**, which make up 40% of real volume but only 12% of the sample. Re-weighted to the real document mix, agreement was 80%. The gold set was re-stratified by document length.

## The mistake people make
Deploying a judge because its prompt "looks reasonable" and a few outputs you checked looked right.

## The line to use in a meeting
*"The judge agrees with compliance 84% of the time, but it catches only half the violations. We're not using it as a gate yet."*

---

# F2 – COHEN'S κ + PER-CLASS PRECISION/RECALL OF THE JUDGE

## What it is
**Cohen's κ = (p_o − p_e) / (1 − p_e)**, where p_o is observed agreement and p_e is the agreement you'd expect by chance given each rater's label frequencies. You report it alongside the judge's precision and recall on each class.

## Why it matters
**Raw percentage agreement looks high when most items are "pass".** If 90% of outputs are fine and the judge says "pass" almost every time, it agrees 90% of the time while contributing nothing. With 90% raw agreement and 82% chance agreement, κ = **0.44**, which is only moderate.

## How to do it properly
1. **Compute κ for every criterion,** not just overall.
2. **Use these bands:** below 0.4 poor, 0.4–0.6 moderate, 0.6–0.8 substantial, above 0.8 near-perfect. **Use a grader only at 0.6 or above, and gate releases only at 0.8 or above.**
3. **Report per-class precision and recall.** κ alone doesn't tell you which direction the errors go.
4. **Bootstrap κ** (Section B6). A κ of 0.65 on 150 items can have a CI running from 0.52 to 0.77.

## Real scenarios

**Insurance – judge for claim-rejection letter compliance (IRDAI wording)**
- **Input:** 250 letters, 88% of them compliant.
- **Output:** The judge agreed with compliance officers 90% of the time.
- **Verdict:** Chance agreement was 0.82, so κ = **0.44**. The judge passed 92% of everything, including 18 of the 30 non-compliant letters that omitted the grievance-redressal and Ombudsman line. A binary criterion for "includes grievance and Ombudsman details" was added, and its κ reached 0.86.

**E-commerce – judge for "answer is grounded in product specs"**
- **Input:** 180 labelled answers.
- **Output:** κ = 0.71, so the judge was approved.
- **Verdict:** Per class, precision on "ungrounded" was 0.93 but **recall was 0.58**. The judge was reliable when it flagged something but missed 4 in 10 invented specs, mostly battery capacity and warranty duration. The team kept the judge for monitoring and added a deterministic spec-lookup check for numeric fields.

## The mistake people make
Quoting raw agreement ("the judge agrees with humans 90% of the time") on an imbalanced dataset.

## The line to use in a meeting
*"90% agreement sounds good, but a judge that always said 'pass' would get 88%. Corrected for chance, κ is 0.44."*

---

# F3 – KRIPPENDORFF'S α FOR MORE THAN TWO LABELLERS

## What it is
A reliability coefficient that handles any number of raters, missing labels (not everyone labels every item) and nominal, ordinal or interval scales. α = 1 − (observed disagreement / expected disagreement).

## Why it matters
Cohen's κ only works for two raters who label the same items. Real annotation projects have four annotators, partial overlap and ordinal scales. Averaging pairwise κ over a partially overlapping design gives an unreliable number. α handles that design as it is.

## How to do it properly
1. **Plan for overlap:** at least 20–30% of items labelled by 2 or more annotators.
2. **Choose the right distance metric:** nominal for categories, ordinal for severity levels.
3. **Use these thresholds: α ≥ 0.8 is reliable, 0.667–0.8 supports only tentative conclusions, and below 0.667 means rework the rubric** before you scale labelling.
4. **Compute α per annotator (leave-one-out).** If removing one person raises α by more than 0.1, that annotator needs recalibration.

## Real scenarios

**HR – ratings of AI-generated interview-feedback summaries**
- **Input:** 4 annotators, 300 items, with about 40% labelled by two or more people.
- **Output:** The team planned to scale to 3,000 items.
- **Verdict:** α = **0.61**, below 0.667. Leave-one-out showed that dropping annotator 3 raised α to 0.74. Annotator 3 had been treating "mentions a weakness" as negative tone, when the rubric counted it as balanced feedback. After one calibration session, overall α was **0.79**, and scaling went ahead.

**Healthcare – radiology report severity grading (none, mild, moderate, severe)**
- **Input:** 5 radiologists, 200 reports, ordinal scale.
- **Output:** Averaged pairwise Cohen's κ was 0.52, and the dataset was judged unusable.
- **Verdict:** Ordinal α was **0.74**. Most disagreements were one step apart (mild vs moderate), which nominal κ counts as complete disagreement. The dataset was usable for severity trends, and the "severe" cut-off was put through adjudication.

## The mistake people make
Averaging pairwise κ across a partially overlapping multi-annotator design, or using a nominal metric on an ordinal scale.

## The line to use in a meeting
*"Our four annotators reach α = 0.61, which is below the reliability bar. We fix the rubric before paying for 3,000 more labels."*

---

# F4 – RUN BOTH ORDERS; COUNT ONLY CONSISTENT VERDICTS, TREAT FLIPS AS TIES

## What it is
Every pairwise judgment is made twice, A/B and B/A. A win counts only when both orders agree. A flip is recorded as a tie, and the **flip rate** is reported as a health metric for the judge.

## Why it matters
**Position bias flips 10–30% of pairwise verdicts.** Some judges favour the first answer and some the second. If you run only one order, the harness's ordering decides the result.

## How to do it properly
1. **Always run both orders.** It doubles the judge cost, and that cost is worth paying.
2. **Report the flip rate. Above 10–15%, the judge can't make this comparison reliably.** Sharpen the criteria or switch to per-criterion binary judging.
3. **Randomise which system appears first** across items, as a backstop.
4. **Check which way the judge leans.** If it favours slot 1 by more than 60/40 on flipped items, note it in the judge's validation record.

## Real scenarios

**E-commerce – two product-description generators**
- **Input:** 400 pairs.
- **Output:** One-order judging gave B a **61%** win rate.
- **Verdict:** **23% of verdicts flipped** when the order was swapped, and the judge favoured slot 2 in 71% of those flips. B had been in slot 2 by default. With flips counted as ties, B's win rate was **54%**, still a win but a much smaller one. The team had been preparing a "B is much better" review.

**Legal – two contract-risk summaries**
- **Input:** 150 pairs, both orders.
- **Output:** Flip rate **31%**.
- **Verdict:** That's above the 15% line, so no win rate from this judge could be trusted. The question "which summary is better?" was replaced with three binary criteria (names the indemnity cap, flags auto-renewal, states the governing law). Per-criterion judging brought flip-equivalent inconsistency down to 6%, and B won on 2 of the 3 criteria.

## The mistake people make
Judging pairs in one order, with the incumbent always in slot A.

## The line to use in a meeting
*"We swapped the order for every comparison. A quarter of the verdicts changed, so we only counted wins where both orders agreed."*

---

# F5 – CROSS-FAMILY JUDGE PANEL

## What it is
You use three judges from different model families (vendors) and take the majority vote per item. The panel's verdict replaces any single judge.

## Why it matters
**Self-preference bias inflates results for the judge's own model family.** Judges prefer outputs whose style, phrasing and structure resemble their own. In a vendor bake-off, a same-family judge biases the result toward its own vendor.

## How to do it properly
1. **Choose judges from three different vendors,** none of them from the same family as a candidate if you can avoid it.
2. **Validate each judge on the gold set (F1)** and exclude any below κ 0.6.
3. **Take the majority vote.** Report the individual judges' results as well, since disagreement between them is informative.
4. **Always use a panel for vendor comparisons.** You can use a single judge for comparisons within one model family.

## Real scenarios

**Telecom – bake-off between two model providers for a Hindi IVR bot**
- **Input:** 300 pairs, Vendor P vs Vendor Q, judged by a model from Vendor P's family.
- **Output:** P won **61%**.
- **Verdict:** A 3-family panel gave P **49%**, a tie. The same-family judge had rewarded P's characteristic phrasing ("Main aapki madad karne ke liye yahan hoon"). Human raters in a 100-pair check rated them 50/50. The decision went to cost, and Q was 30% cheaper.

**HR – performance-review summary generator**
- **Input:** An in-house fine-tuned model vs its base model, judged by the base model.
- **Output:** The base model won **58%**, which suggested the fine-tune had failed.
- **Verdict:** The 3-family panel gave the fine-tune **57%**. The base model had been preferring its own untuned style. HR business partners confirmed the fine-tune on 80 pairs. The fine-tune shipped.

## The mistake people make
Using one vendor's model to judge a contest that includes that vendor's model.

## The line to use in a meeting
*"The judge was made by one of the two vendors, so we used three judges from different vendors instead."*

---

# F6 – EVERYTHING SCORES 7 OR 8 → REPLACE THE LIKERT SCALE WITH BINARY CRITERIA

## What it is
You replace a 1–10 or 1–5 quality scale with 4–8 yes/no checks, each for one observable property, and sum them. (The rubric design is covered in Section A4. This subsection covers the diagnosis.)

## Why it matters
**A compressed scale can't tell outputs apart.** When 80%+ of scores land on two adjacent values, the metric can't separate good outputs from mediocre ones, and small differences between systems vanish into rounding.

## How to do it properly
1. **Diagnose it:** plot the score histogram. If two adjacent values hold 75% or more of the mass, the scale has collapsed.
2. **Derive the binary checks from error analysis** of low- and high-rated outputs.
3. **Validate each check** (F2), then measure how well the summed score correlates with human rankings.

## Real scenarios

**Legal – AI-drafted demand notices under Section 138 NI Act (cheque bounce)**
- **Input:** 300 notices scored 1–10.
- **Output:** **83% of scores were 7 or 8.**
- **Verdict:** Six binary checks were introduced: cheque number and date, bank memo date, amount in words and figures, the 15-day payment demand, service within 30 days of the memo, and advocate details. Scores spread from 1 to 6, and correlation with senior-advocate rankings rose from **0.31 to 0.72**. The notices that had scored 8 included 22 with the wrong statutory period.

**Logistics – customer delay notifications**
- **Input:** 1–5 scale, 400 messages.
- **Output:** 88% scored 4.
- **Verdict:** Four checks were introduced: states the new ETA, gives the reason, includes a tracking link, and has no unapproved compensation promise. Only **57% passed the ETA check**, a failure the 4/5 scores had hidden for 2 months.

## The mistake people make
Adjusting the Likert prompt ("be more critical!") instead of replacing the scale.

---

# F7 – ONE JUDGE CALL PER CRITERION, WITH FEW-SHOT EXAMPLES

## What it is
Each quality dimension (factuality, tone, completeness, safety) gets its own judge prompt, with a pass and a fail example for that dimension, and asks for reasoning before the verdict.

## Why it matters
**In a combined "quality" prompt, fluency dominates correctness.** The judge forms an overall impression from tone and structure and then rates every dimension to match it. So a warm, well-written, factually wrong answer passes.

## How to do it properly
1. **Use one prompt per criterion.** Batch items to save cost, but not criteria.
2. **Put the reasoning before the verdict.** That order gives better agreement than verdict-then-justification.
3. **Give each criterion 1–2 pass examples and 1–2 fail examples,** with the fail example written fluently.
4. **Validate each criterion separately** (F2).

## Real scenarios

**Healthcare – patient-education answers on a diabetes diet**
- **Input:** 250 answers, a combined quality judge vs separate factuality and tone judges.
- **Output:** The combined judge passed **40% of fluent-but-wrong answers.**
- **Verdict:** The separate factuality call caught **88%** of them. The combined judge had passed "jaggery is a healthy sugar substitute for diabetics", which was written warmly and was clinically wrong. The warm tone had carried the factuality score with it.

**Banking – credit-card dispute responses**
- **Input:** A combined judge scored tone, correctness and completeness at once.
- **Output:** Dimension scores correlated at **r = 0.91** with each other.
- **Verdict:** Such high correlation between supposedly independent dimensions showed the judge was giving one overall impression three times. Split into separate calls, the correlation was r = 0.34, and completeness, which covers mentioning the 90-day chargeback window, turned out to be failing 29% of the time.

## The mistake people make
Asking for five dimension scores in one prompt and treating them as five independent measurements.

---

# F8 – FEW-SHOT FROM JUDGE–HUMAN DISAGREEMENTS + MAJORITY OF 3

## What it is
You take the items where the judge disagreed with humans, add some of them as labelled examples in the judge prompt, and then sample the judge 3 times and take the majority verdict.

## Why it matters
**Generic instructions don't fix the judge's specific, systematic errors.** "Be strict about factuality" changes nothing. Showing the exact kind of case it got wrong ("here's an implicit threat in Hinglish, and it's a FAIL") does. Majority voting then smooths out the remaining randomness.

## How to do it properly
1. **Cluster the disagreements** into 3–5 error types.
2. **Add 1–2 examples per error type** (6–10 in total) with the human label and a one-line reason.
3. **Take these examples from the development split only.** Validate on the held-out split to avoid circularity.
4. **Sample 3 times at temperature about 0.7 and take the majority,** or use temperature 0 plus a different example order each call.
5. **Stop when held-out agreement plateaus,** usually after about 10 examples.

## Real scenarios

**Fintech – judge for mis-selling risk in mutual-fund chatbot answers**
- **Input:** 220 human-labelled answers.
- **Output:** Baseline agreement **78%**.
- **Verdict:** 8 examples from the disagreements (guaranteed-return language, "safe as FD" comparisons, omitted risk disclosures) raised agreement to **86%**, and majority-of-3 raised it to **89%**. The biggest single gain came from one example: "SIP mein kabhi loss nahi hota" is a FAIL. The judge had been reading it as general encouragement.

**Content moderation – Hinglish hate-speech judge**
- **Input:** 300 labelled posts. The judge over-flagged reclaimed slurs and under-flagged coded caste insults.
- **Output:** κ = 0.58.
- **Verdict:** 10 disagreement examples raised κ to **0.72**. Majority-of-3 added only 0.02, because the remaining errors were consistent rather than random, so voting couldn't fix them. They went to the codebook (F9).

## The mistake people make
Rewriting the judge's instructions in more forceful language instead of showing it the specific mistakes.

---

# F9 – HUMAN LABELLERS DISAGREE → FIX THE RUBRIC FIRST

## What it is
When the humans disagree, you run calibration rounds. Annotators label the same batch, discuss every disagreement, and write the resolution into a **codebook** of edge-case rulings. Then you re-measure agreement.

## Why it exists
**Human agreement is the ceiling for any grader.** If humans agree at κ 0.42, no judge can be validated beyond that, and gold labels that noisy distort every downstream metric. Most human disagreement comes from an ambiguous rubric, not from careless annotators.

## How to do it properly
1. **Measure the starting agreement** (κ or α).
2. **Run a calibration round:** everyone labels the same 50 items, then goes through the disagreements together.
3. **Write each resolution down as a ruling** with an example, for instance: "Reclaimed slurs used by in-group speakers → not hate speech unless they target someone else."
4. **Repeat until agreement is at least 0.6** (at least 0.7 for high-stakes work). Two or three rounds is typical.
5. **Give the codebook to the judge as well.** Its rulings make good few-shot material (F8).

## Real scenarios

**Content moderation – Hinglish hate-speech labelling**
- **Input:** 5 annotators. Sarcasm, reclaimed slurs and regional insults split them.
- **Output:** κ = **0.42**.
- **Verdict:** After 2 calibration rounds and **15 written rulings**, κ was **0.76**. The rulings that mattered most covered sarcasm aimed at a group ("inke log toh aise hi hote hain 🙂"), which was ruled hate speech, and film dialogue quoted without endorsement, which was ruled not hate speech. The judge had been "failing" against labels that were themselves inconsistent.

**Insurance – grading claim-assessment rationales**
- **Input:** 3 senior assessors.
- **Output:** α = 0.55.
- **Verdict:** Most disagreements were over whether a rationale needed to cite the specific policy clause number. That rule had never been written down, and one assessor thought it was obvious while the other two didn't. **One ruling raised α to 0.81.**

## The mistake people make
Blaming the annotators, or taking a majority vote over inconsistent labels, instead of fixing the rubric that produces the disagreement.

## The line to use in a meeting
*"Our experts agree at κ 0.42. We can't validate any judge above what the humans achieve with each other, so we fix the rubric first."*

---

# SECTION F DECISION FLOW

```
START: A grader (human or LLM) is producing numbers you'll act on.
│
├─ Do humans agree with each other?
│     ├─ Unknown → measure: 2 raters → Cohen's κ · 3+ / partial overlap → α (F3)
│     └─ κ < 0.6 or α < 0.667 → calibration rounds + codebook (F9). STOP until fixed.
│
├─ Is the LLM judge validated on 150–200 gold labels? (F1)
│     └─ NO → do it. Report κ AND per-class recall on "fail" (F2)
│              ├─ κ < 0.6            → not usable
│              ├─ 0.6 ≤ κ < 0.8      → monitoring only
│              └─ κ ≥ 0.8            → may gate releases
│
├─ Scores bunched at 7–8?          → binary criteria (F6)
├─ One prompt judging many things? → one call per criterion (F7)
├─ Pairwise judging?               → both orders; flip rate > 10–15% → redesign (F4)
├─ Comparing vendors?              → 3-family panel, majority vote (F5)
│
└─ Validated but not accurate enough?
      └─ few-shot from disagreements (dev split) + majority of 3 (F8)
            └─ re-validate on held-out split
```

---

# THE THREE THINGS TO REMEMBER

1. **Validate before you trust.** Compare the judge with 150–200 human labels, and check its recall on "fail", not just overall agreement.

2. **Correct for chance and for bias.** Report κ instead of raw agreement, swap positions, and don't let a vendor's model judge its own vendor.

3. **Humans set the ceiling.** If your experts don't agree with each other, fix the rubric before you tune any judge.
