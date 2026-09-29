# SECTION A – CHOOSING HOW TO GRADE
### The single most consequential decision in any eval

You are here when you have a pile of model outputs and need a verdict on each one, and you're about to write either `output == expected` or "ask a model if this is good." Everything built on this eval inherits the grader's errors. That includes confidence intervals, A/B comparisons, dashboards and the ship decision. A grader that misjudges 27 points of your data can't be rescued by better statistics. If you pick the wrong grader, every later step measures the wrong thing more precisely.

> **Grade with the cheapest method that can actually observe what you care about: execute it if it runs, check the system if it acts, compare strings if it's a fact, and use a judge only when nothing deterministic can see the property.**

```
  WHAT DOES THE OUTPUT DO?                      GRADER                          COST / VARIANCE
  ───────────────────────────────────────────────────────────────────────────────────────────────
  It runs (code, SQL, API call)          →  A1 Execution-based grading          ₹0, deterministic
  It changes a system (agent action)     →  A2 End-state verification           ₹0, deterministic
  It states a short fact                 →  A3 Normalised exact match           ₹0, deterministic
  It fills a structure (JSON, form)      →  A5 Schema + field-level scoring     ₹0, deterministic
  It's open-ended text                   →  A4 LLM judge, binary rubric         ₹, some variance
  It's high-stakes and final             →  A6 Double-annotated expert review   ₹₹₹, slow, gold
  ───────────────────────────────────────────────────────────────────────────────────────────────
  It's live production traffic           →  A7 Tiered online scoring (wraps all of the above)
```

**Rule of thumb:** *if a line of code can check it, a line of code should check it.* Every property you move from a judge to code removes cost, variance and one way the grader can be fooled.

---

# A1 – EXECUTION-BASED GRADING

## What it is
You run the output in a sandbox (SQL against a frozen database snapshot, code against hidden unit tests, API calls against a mock) and compare the results or side effects. You don't compare the text. Two queries that look nothing alike are both correct if they return the same rows.

## Why it beats everything else
String match fails correct SQL that reorders JOINs or renames aliases, and it passes near-identical SQL that differs by one wrong operator. LLM judges read code without running it, so **the judge approves elegant broken code**. On 200 text-to-SQL items, exact match scored 41% and execution match scored 68%. All 27 points of that gap were equivalent rewrites. An LLM judge on the same set scored 79%, which means it passed 22 queries that returned the wrong rows. Execution is the only one of the three that checks what the query actually returns.

## How to do it properly
1. **Freeze a snapshot.** Grade against a fixed DB dump or fixture set, never live data. If the data changes daily, the score changes daily for reasons unrelated to the model.
2. **Compare results, not formatting.** Ignore row order unless the question asks for ordering. Ignore column aliases. Use a float tolerance of 1e-6 and round ₹ amounts to the paisa.
3. **Seed distinguishing rows.** Add data that makes plausible wrong answers return different results: a refund of exactly ₹5,000 to separate `>` from `>=`, a transaction at 23:59 on the last day of the quarter, a NULL merchant category. Without these, **wrong queries pass by coincidence**.
4. **Set resource limits.** Use a 10-second timeout and a row cap. Count a timeout as a failure but log it separately, because a slow correct query is a different bug from a wrong one.
5. **Test your tests.** Mutate the reference solution (flip a comparator, drop a WHERE clause). If the mutant still passes more than 5% of the time, the fixtures aren't discriminating enough.
6. **Log the failure class.** Tag each failure as a syntax error, unknown column, runtime error or wrong result. That gives you error analysis for free.

## Real scenarios

**Fintech – NL-to-SQL over a UPI transaction warehouse**
- **Input:** "Total refunds above ₹5,000 in Q2 FY25, by merchant category."
- **Output:** `SELECT mcc, SUM(amount) FROM refunds WHERE amount >= 5000 AND txn_date BETWEEN '2024-07-01' AND '2024-09-30' GROUP BY mcc;`
- **Verdict:** Exact match failed it. The judge passed it as "logically correct". Execution also passed it at first, because the snapshot had no refunds of exactly ₹5,000. The team then seeded boundary rows (exactly ₹5,000, and 30 Sep at 23:59 on a timestamp column). With those rows in place, 19 of the 200 queries that had passed now failed, and execution accuracy dropped from **68% to 58.5%**. The model hadn't changed. The old fixtures had been too thin to catch the errors. Boundary-seeded fixtures are now required for every new SQL eval set.

**E-commerce – coupon-logic code generator**
- **Input:** "Write `apply_coupon(cart, code)`. FLAT200 gives ₹200 off carts ≥ ₹999 and cannot stack with other offers."
- **Output:** A clean, commented, type-hinted function.
- **Verdict:** The LLM judge gave it 9/10 ("handles edge cases well"). It failed 3 of 12 hidden tests: it checked the ₹999 threshold *before* bank-offer discounts rather than after. Across 150 tasks, the judge passed **88%** and execution passed **63%**. The 25-point gap was mostly well-written code that didn't work. Execution became the gating metric, and the judge was kept only as a secondary readability signal.

## The mistake people make
Grading runnable output by its text. That means comparing it with a reference string, or asking a judge "is this code correct?". A judge reads the code. It doesn't run it.

## When NOT to use it
When the output does something irreversible (moves real money, sends real SMS) and you have no sandbox. Build the mock first. Don't grade that output some other way in the meantime.

## The line to use in a meeting
*"We don't ask a model whether the query is right. We run it and look at the rows."*

---

# A2 – END-STATE VERIFICATION

## What it is
After an agent finishes, you query the real system (a DB row, an API GET, a file on disk) and assert post-conditions written in code. The transcript is kept for debugging but plays no part in the score.

## Why it exists
**Agents say "Done, I've updated it" when nothing changed.** A judge that reads the transcript grades the agent's claim, not the change it made. On 150 policy-servicing tasks, a transcript judge said 91% were complete, while database checks confirmed 74%. The other 17 points were false claims of success. The error also runs the other way: an agent that reports failure may have written half a record.

## How to do it properly
1. **Write post-conditions before the run.** For example: `nominee.name == "Priya Sharma" AND nominee.relation == "SPOUSE" AND nominee.share == 100`. Every field the task touches gets an assertion.
2. **Assert what must *not* change.** Diff the whole record, or the touched tables, against the pre-run snapshot. Any unexpected change fails the task. Collateral damage is the failure that transcript grading never catches.
3. **Reset per run.** Restore the environment snapshot before every task, so runs can't pass because of state an earlier run left behind.
4. **Test idempotency.** Re-run 10% of tasks twice. Duplicate refunds, double charges or two tickets for one request count as failures.
5. **Track claim–state mismatch as its own metric.** Count runs where the agent said "done" and the state disagrees. For customer-facing agents, **a mismatch rate above 2% blocks launch**, whatever the success rate.

## Real scenarios

**Insurance – policy-servicing agent**
- **Input:** "Change the nominee on policy LI-88213 from my father to my wife, Priya Sharma."
- **Output:** "Done! Nominee updated to Priya Sharma (Spouse)."
- **Verdict:** In the DB, the name was updated but `relation` still said FATHER and `share` was 0%. The tool sent a partial PATCH, and the agent read the HTTP 200 as success. Across 150 tasks, 11 of the 26 false claims followed this partial-PATCH pattern. Making all three fields required in the tool schema raised end-state success from **74% to 83%**, with no change to the prompt or model.

**Telecom – postpaid plan-change agent**
- **Input:** "Move me to the ₹599 plan and add the Dubai roaming pack."
- **Output:** "I couldn't add the roaming pack. Please contact support."
- **Verdict:** The transcript judge passed it as an honest, graceful failure. The end-state check showed that the ₹599 plan *and* the roaming pack were both active, and that the pack had been activated twice. The agent had retried after a timeout, so the customer was billed ₹2,998 twice. The collateral diff found duplicate activations in 6 of 120 tasks (5%). Launch was blocked until every write call carried an idempotency key.

## The mistake people make
Grading the transcript because it's already there, when writing post-conditions takes an afternoon. A transcript tells you what the agent says it did, not what it did.

## The line to use in a meeting
*"The transcript is the agent's testimony. The database is the evidence."*

---

# A3 – NORMALISED EXACT MATCH

## What it is
You normalise the output and the reference (case, whitespace, punctuation, Indian number formats, units, dates), then compare them exactly. For multi-word answers you use token-level F1 with a fixed pass threshold.

## Why it beats everything else
It costs nothing, gives the same result every time and isn't swayed by persuasive wording. A judge on factual answers costs about ₹0.40 per item, gives a different verdict on 2–4% of items from one run to the next, and **passes near-miss numbers as "close enough"**. With a normaliser, "₹1,50,000", "150000", "Rs 1.5L" and "1.5 lakh" all become 150000, and 500 questions are graded in 2 seconds at ₹0.

## How to do it properly
1. **Treat the normaliser as tested code.** Give it its own unit tests covering lakh/crore, "Rs"/"₹"/"INR", DD/MM/YYYY vs ISO dates, and "5 yrs"/"five years".
2. **Normalise only what doesn't change the meaning. Never "normalise" identifiers.** Handle IFSC, GSTIN, PAN, policy numbers and PIN codes with exact match plus format validation (IFSC: `^[A-Z]{4}0[A-Z0-9]{6}$`). One wrong character sends money to the wrong branch.
3. **Use alias lists, not a looser normaliser.** If "Bengaluru" and "Bangalore" are both right, list both as accepted answers for that item.
4. **For token-F1, fix the threshold (F1 ≥ 0.8) and hand-audit the 50 items closest to it.** That band is where the threshold decides the verdict.
5. **Audit the false negatives every month.** Sample 50 failures. If more than 10% are actually correct, fix the normaliser. Don't switch to a judge.

## Real scenarios

**Banking – IFSC lookup bot**
- **Input:** "IFSC for HDFC Bank, Koramangala branch?"
- **Output:** `HDFC00001234`
- **Verdict:** It scored as correct. The team had reused its amount normaliser, which strips leading zeros, on identifier fields, so the 12-character output collapsed onto the valid 11-character code. An audit found 23 of 500 "correct" answers were invalid codes that would bounce, or worse, route money to the wrong branch. Accuracy was corrected from **96.2% to 91.6%**. Identifier fields now use their own exact-match comparator with the regex check.

**Insurance – sum-insured QA over policy schedules**
- **Input:** "What's the sum insured on policy HX-2291?"
- **Output:** "₹5 lakh". The gold answer is `500000`.
- **Verdict:** Raw string match scored 58%. The team proposed an LLM judge, which scored 97%. An Indian-format normaliser scored 94%. Reading the 3-point difference showed that the judge had accepted "₹4.5 lakh" and "about ₹5 lakh after co-pay" as correct 14 times. The normaliser's 94% was the honest number, and it shipped as the grader.

## The mistake people make
Switching to an LLM judge because exact match is "too strict". The fix is a better normaliser. A judge adds leniency where you least want it: on numbers.

## The line to use in a meeting
*"For a fact with one right answer, a judge only adds cost and a way to be wrong."*

---

# A4 – LLM-AS-JUDGE WITH A BINARY-CRITERIA RUBRIC

## What it is
A judge model answers yes or no to each explicit criterion ("States the 5–7 working-day refund timeline?"), writing its reasoning before the verdict. The score is the number of criteria passed, and you report the pass rate for each criterion. There is no overall 1–10 score.

## Why it beats everything else
Overall scores bunch at 7–8 whatever the quality, and they don't say *what* failed, so you can't fix anything from them. On 300 support replies judged against human labels, agreement was **κ = 0.78 with a 5-item binary checklist and κ = 0.41 with a 1–10 score**. Binary criteria also turn the eval into a to-do list: the criterion with the lowest pass rate is the next prompt fix.

## How to do it properly
1. **Derive criteria from error analysis, not brainstorming.** Read 50–100 real outputs, tag what goes wrong, and turn the 4–8 most frequent failure types into criteria.
2. **Make every criterion observable.** "Mentions the 5–7 working-day timeline" is observable. "Is helpful" isn't. If two people could reasonably disagree about what the criterion means, split it.
3. **Give each criterion its own judge call** (or one structured output with a separate field per criterion), with reasoning first, then PASS/FAIL, plus one passing and one failing example for that criterion. If you combine criteria into one "quality" prompt, fluency drowns out correctness.
4. **Validate each criterion against 150–200 human labels.** Require **κ ≥ 0.6 before you trust a criterion, and κ ≥ 0.8 before it gates a release** (see Section F).
5. **Pin the judge.** Use an exact model version and temperature 0. When the provider updates an alias, re-validate before the next comparison.
6. **Keep critical and cosmetic criteria separate.** "No invented commitments" is a hard fail on its own. "Apologises once" is only added to the score.

## Real scenarios

**Telecom – Hinglish recharge-failure support**
- **Input:** "Recharge ho gaya par balance nahi aaya, ₹299 kat gaye."
- **Output:** A warm, fluent Hinglish apology that promises "refund 24 ghante mein aa jayega."
- **Verdict:** The overall-score judge gave it 8/10. The rubric failed it on two criteria: "states the 5–7 working-day timeline" and "makes no commitment not in policy". Across 300 replies, the overall-score mean was 7.6, with 81% of scores at 7 or 8. The rubric showed the timeline criterion passing only **64%**. One prompt change raised it to **93%**. The 1–10 scale could never have pointed to that fix.

**Healthcare – diabetes diet education bot**
- **Input:** "Can I have fresh fruit juice instead of mithai?"
- **Output:** "Yes, fresh juice is a healthier alternative to sweets, and 2 glasses a day is fine."
- **Verdict:** The rubric had a binary criterion, "medically accurate". It still reached only **κ = 0.29** against dietitians, because "accurate" was too vague for either the judge or the humans to apply consistently. The team split it into three concrete checks ("no advice that raises glycaemic load", "no specific quantities not in the guideline", "recommends consulting the treating doctor for changes"). Agreement rose to **κ = 0.71**, and this answer failed the first two checks. A yes/no format doesn't make a vague criterion precise.

## The mistake people make
Writing a single "rate this response 1–10" prompt and treating the average as a quality metric. The second mistake is shipping criteria that were never checked against human labels.

## When NOT to use it
When code could check the criterion. Length limits, "contains a timeline", valid JSON and banned phrases are regex jobs. Don't pay a judge to do them, or accept its variance on them.

## The line to use in a meeting
*"We can't fix an average of 7.4 out of 10. 'Fails the refund-timeline check 36% of the time' is one prompt edit."*

---

# A5 – SCHEMA VALIDATION + FIELD-LEVEL SCORING

## What it is
Two stages. First, validate the output against a JSON Schema and record parse and schema failures. Then score each field with a comparator suited to its type, and report accuracy for each field.

## Why it matters
If you only check whether the whole object matches, **one field that's wrong 30% of the time hides behind fields that are right 99% of the time**. On 1,000 invoices, whole-object accuracy was 62%, which says nothing about where to look. Field-level scores showed invoice_date at 99%, total at 96% and GSTIN at 71%, so the fix was obvious.

## How to do it properly
1. **Report schema validity separately.** A parse failure is a formatting bug, and a wrong value is a reasoning bug. They need different fixes.
2. **Choose a comparator per field type.** Identifiers get exact match plus checksum or regex. Amounts get numeric match within ₹1. Dates are normalised to ISO. Names get token-F1 ≥ 0.9. Enums get exact match.
3. **Keep blank and wrong apart.** Report *wrong-value rate* separately from *blank rate*. A blank GSTIN goes to human review. A wrong one goes into the ledger and fails GST filing.
4. **Align list fields before scoring them.** Match line items or job entries to the reference by content (Hungarian matching on similarity), not by position.
5. **Weight fields by downstream cost.** Define must-be-right fields (GSTIN, taxable value, IFSC) that gate the release by themselves.

## Real scenarios

**E-commerce – GST invoice extraction for a B2B marketplace**
- **Input:** A scanned invoice from a Surat textile supplier to a Delhi retailer.
- **Output:** Valid JSON with every field filled in.
- **Verdict:** Field-level scoring put GSTIN at 71%, and it also found that 9% of interstate invoices had tax wrongly split as CGST+SGST instead of IGST. The more useful finding came from reading the errors: **80% of wrong GSTINs failed the GSTIN checksum**. Adding a checksum guard that blanks invalid values cut the GSTIN wrong-value rate from **29% to 6%**, with 23% sent to human review. The model didn't improve. The pipeline stopped writing wrong GSTINs into the ledger.

**HR – resume parser for an ATS**
- **Input:** A two-page resume listing four previous employers.
- **Output:** A structured `experience[]` list with all four roles correct.
- **Verdict:** The field-level grader scored `experience` at **48%**. The model listed jobs oldest first and the gold labels listed them newest first, so position-by-position comparison failed them. After aligning entries by company name, the score was **86%**. The grader had been wrong, and the team had spent two sprints tuning prompts to fix a problem the model didn't have.

## The mistake people make
Reporting a single "extraction accuracy" figure, or comparing list items by position. Both hide which field is actually wrong.

## The line to use in a meeting
*"Overall extraction is 62%. GSTIN is the problem, it's at 71%, and here's the fix."*

---

# A6 – DOMAIN-EXPERT HUMAN REVIEW, DOUBLE-ANNOTATED AND ADJUDICATED

## What it is
Two qualified experts independently grade a stratified sample, blind to which system produced each output, and a third resolves their disagreements. You get a gold label set, a measured agreement between the experts, and a written log of rulings on edge cases.

## Why it exists
Automated graders are models too, and they often miss the same things the system misses. **A judge passes fluent, confident, clinically wrong answers**, because fluency and confidence are what it pattern-matches on. For decisions where one error means patient harm, legal liability or a regulator notice, the gold standard has to come from people who are accountable for the domain. A typical budget: 200 cases × 2 doctors, with 31 disagreements adjudicated, costs about ₹1.2 lakh. Compare that with the liability from one wrong dosage.

## How to do it properly
1. **Stratify and oversample risk.** Draw 200 items, with at least 40% from the highest-risk intents (drug interactions, pediatric dosing, pregnancy).
2. **Blind the review.** Experts don't see the model name, prompt version or other experts' labels.
3. **Use the same binary rubric as your judge (A4).** Then the expert labels also serve as the judge's validation set, so you pay once and use them twice.
4. **Measure agreement between the experts before relying on their labels.** **If κ is below 0.6, the rubric is ambiguous.** Stop, write rulings for the edge cases, and run a calibration round.
5. **Adjudicate every disagreement and write the ruling down.** The ruling log becomes the codebook for future annotators and for the judge's few-shot examples.
6. **Budget for it.** Allow 3–5 minutes per item per expert. At about ₹300 per review, 400 reviews cost ₹1.2 lakh.

## Real scenarios

**Healthcare – pharmacy chain's medicine-query chatbot**
- **Input:** "I'm on warfarin. Can I take Combiflam for back pain?"
- **Output:** "Combiflam contains ibuprofen and paracetamol. Take it after food, maximum 3 tablets a day. See a doctor if the pain persists."
- **Verdict:** The LLM judge, already validated at κ = 0.74 on general queries, passed it: correct composition, correct dose, safe tone. Both pharmacologists failed it, because ibuprofen with warfarin significantly raises bleeding risk and the answer should have advised against it. Across 200 cases, the experts failed **23 answers the judge had passed (11.5%)**, and 19 of them were drug interactions. Launch was held, and interaction questions now go through a deterministic drug-interaction database lookup before the model answers.

**Legal – Section 138 NI Act demand-notice drafter**
- **Input:** Facts of a ₹3.4 lakh bounced cheque, with the bank return memo dated 12 March.
- **Output:** A properly formatted demand notice giving the drawer 30 days to pay.
- **Verdict:** The statute allows 15 days, so the notice was wrong. The bigger finding was that the two advocates initially agreed at only **κ = 0.52**. They disagreed on whether a notice that omits the return-memo date is a fail. After one adjudication session and 9 written rulings, κ rose to **0.81**. The team's judge had shown "82% agreement" against the unadjudicated labels, which meant nothing because the labels themselves were inconsistent. Against the adjudicated labels the judge scored 71%, and it was re-tuned before use.

## The mistake people make
Using one expert, so there's no agreement to measure and every label is one person's opinion. Or skipping experts because "the judge agreed with our PM 90% of the time."

## When NOT to use it
In the daily iteration loop, where it's too slow and too expensive. Use experts to build the gold set, validate the judge, and sign off before launch. Use A4 for everything in between.

## The line to use in a meeting
*"₹1.2 lakh for 200 double-reviewed cases is the cheapest insurance we'll buy for this launch."*

---

# A7 – TIERED ONLINE SCORING

## What it is
You score production traffic in layers. Deterministic checks and a small classifier (under 50 ms) run on **100%** of requests. A frontier judge runs on a **1–2% uniform random sample**, plus a capped share of the items the classifier flags. The cheap layers give coverage and the judge gives depth.

## Why it matters
If you run a frontier judge on every request, you double cost and latency. If you score nothing, you're blind. At 20 lakh requests a day, judging everything at ₹0.40 per call costs **₹8 lakh/day**. The tiered setup costs about **₹30,000/day**: roughly ₹14,000 for the classifier on all traffic and ₹16,000 to judge a 2% sample of 40,000 requests. A 2% uniform sample also puts a 95% interval of about **±0.1 points** around a 1% failure rate, which is precise enough to track by day and by intent.

## How to do it properly
1. **Tier 0: regex and schema checks, under 5 ms.** Examples: 10-digit mobile numbers starting 6–9, 12-digit Aadhaar-like strings (with the Verhoeff checksum), 6-digit PIN codes next to address words, JSON validity.
2. **Tier 1: a small fine-tuned classifier, under 50 ms,** trained on 5,000+ judge-labelled items for the 2–3 dimensions that matter most (PII leak, policy violation, wrong-intent answer).
3. **Tier 2: a frontier judge** on the uniform sample, plus up to a fixed daily cap of tier-1 flags.
4. **Keep the uniform sample separate from the flagged sample.** The uniform sample is the only one that estimates the true failure rate. Flagged items tell you *what* fails, never *how often*.
5. **Recalibrate every week.** Compare tier 1 against tier 2 on the uniform sample. **If tier 1's recall on failures falls below 80%, retrain it.**

## Real scenarios

**E-commerce – marketplace order-status bot**
- **Input:** "Mera order kab aayega? #OD4471"
- **Output:** A reply that included the delivery partner's full mobile number.
- **Verdict:** The tier-0 regex caught 10-digit numbers in 0.3% of replies. The judged sample found a further **0.2%** of replies leaking *addresses* written in Hinglish ("Flat 402, Sai Residency ke paas"), which the regex couldn't match. So the regex was seeing only 60% of leaks. A tier-1 classifier trained on judge labels raised leak-detection recall from **60% to 93%**.

**Banking – credit-card servicing bot**
- **Input:** Weekly quality review of the live bot.
- **Output:** A dashboard showing a "judge-confirmed failure rate: 38%".
- **Verdict:** Leadership escalated, and a rollback was drafted. The 38% had been computed only on items tier 1 had flagged. Those were suspicious by construction, so of course many failed. The uniform 2% sample put the true failure rate at **1.1% (95% CI 0.9–1.3%)**. The rollback was cancelled, and the dashboard now labels the two samples separately, so nobody can report the flagged-sample rate as the overall rate again.

## The mistake people make
Judging only the flagged items and reporting that rate as if it applied to all traffic, or judging 100% of traffic "for safety" until finance switches it off.

## The line to use in a meeting
*"Code checks every request, and the judge audits 2% of them. That's full coverage for ₹30,000 a day instead of ₹8 lakh."*

---

# SECTION A DECISION FLOW

```
START: What does the output do?
│
├─ Is it live production traffic?
│     └─ YES → A7 Tiered online scoring
│               (tier 0 regex + tier 1 classifier on 100%, judge on a 1–2% uniform sample)
│
├─ Can it be executed? (code, SQL, API call)
│     └─ YES → A1 Execution-based grading
│               └─ Seeded boundary rows? Mutants fail? If not, fix fixtures first.
│
├─ Did an agent change a system?
│     └─ YES → A2 End-state verification
│               └─ Assert must-change AND must-not-change; claim–state mismatch > 2% → block
│
├─ Is it a short fact with one right answer?
│     └─ YES → Is it an identifier (IFSC, GSTIN, PAN, policy no.)?
│               ├─ YES → Exact match + format/checksum validation, never normalised
│               └─ NO  → A3 Normalised exact match (token-F1 ≥ 0.8 for spans)
│
├─ Is it structured output (JSON, form, extraction)?
│     └─ YES → A5 Schema validity → per-field comparators → wrong-value vs blank rate
│               └─ List fields? Align by content before scoring
│
└─ Open-ended text?
      └─ Is a wrong answer high-stakes (health, legal, money, regulator)?
            ├─ YES → A6 Double-annotated expert review builds gold (expert κ ≥ 0.6)
            │         └─ then A4 judge, validated on that gold, runs day to day
            └─ NO  → A4 Binary-criteria judge
                      └─ κ vs humans ≥ 0.6 per criterion? ≥ 0.8 to gate?
                            ├─ YES → Use it; pin version; temp 0
                            └─ NO  → Split vague criteria; add disagreement few-shots; re-validate
```

---

# THE THREE THINGS TO REMEMBER

1. **Run it, check it or compare it before you judge it.** Deterministic graders cost ₹0, give the same answer every time, and can't be talked round by a confident wrong answer.

2. **Break quality into binary, observable criteria.** A 7.4/10 gives you nothing to fix, while "fails the timeline check 36% of the time" tells you exactly what to change.

3. **Every grader is wrong somewhere, so measure where before you trust it.** Audit normaliser false negatives, validate judges against humans (κ ≥ 0.6), and check expert agreement before those labels become gold.
