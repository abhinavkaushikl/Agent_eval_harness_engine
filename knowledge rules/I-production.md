# SECTION I – PRODUCTION
### Offline evals only test what you already thought of

You are here when the system is shipping or already live. Your offline suite is green, and you're wondering what it misses, because it can only contain failures someone anticipated. Production sends you Hinglish typos, a provider changing model behaviour silently at 2 a.m., intents nobody has seen before, and a prompt edit that fixes one case and quietly breaks forty. This section covers the loop that keeps an eval honest after launch: gate every change, watch live traffic, tie scores to money, roll out carefully, and turn every production failure into a permanent test case.

> **Production is the only eval set that contains the failures you didn't anticipate. Sample it, score it, tie it to a business outcome, and turn every failure you find into a permanent test.**

```
  THE PRODUCTION FLYWHEEL
  ──────────────────────────────────────────────────────────────────────────────
       ┌──────────────► CI gate: suite + must-pass (I1, I2) ──────────┐
       │                                                              ▼
  Eval set from logs +                                   Shadow → canary → full (I9)
  past failures (I8)                                                  │
       ▲                                                              ▼
       │                                            Live: sampled judge + implicit
  Error analysis: open-code                         signals (I5); daily canary eval (I4);
  100 failures, count (I3) ◄──────────── KPI + guardrails (I6); A/B for big bets (I7)
  ──────────────────────────────────────────────────────────────────────────────
  Every production failure becomes a permanent test case. That's the flywheel.
```

**Rules of thumb:**
- *A/B sample size per arm ≈ 16·p(1−p)/δ².* Detecting 40% → 41% needs **≈ 38,000 sessions per arm**. Small effects need big traffic.
- *Canary alert: more than 3 SD below the 30-day mean.* Anything smaller will fire on noise.
- *A gate that flakes more than 5% of the time will be ignored.* Once it's ignored, it stops protecting anything.

---

# I1 – CI REGRESSION GATE: FIXED SUITE + MUST-PASS GOLDEN SET

## What it is
Every PR that touches a prompt, model, tool or retrieval config runs the eval suite. The merge is blocked if the aggregate drops beyond a tolerance **or any must-pass item fails**.

## Why it matters
**Prompt edits silently break old cases that nobody re-checks by hand.** A fix for Tamil greetings can break the EMI calculation. Without a gate, you find out from customers.

## How to do it properly
1. **Keep a fixed suite of 200–300 items** covering the main intents, versioned with the code.
2. **Keep a must-pass set of 20–50 items:** the cases where one failure is an incident (regulatory statements, amounts, safety refusals). Any failure there blocks the merge, whatever the aggregate says.
3. **Set the aggregate tolerance from the A/A noise band** (E4), for example "block if more than 2 points below baseline".
4. **Post the diff in the PR:** newly failing items, newly passing items and the must-pass status.
5. **Update the baseline only when a merge is accepted,** never to make a failing gate pass.

## Real scenarios

**Fintech – EMI calculator and loan-FAQ bot**
- **Input:** A PR to "make responses friendlier".
- **Output:** The aggregate score went *up* 1.2 points, so the PR looked safe.
- **Verdict:** The must-pass item "₹5 lakh at 10.5% for 36 months = ₹16,251/month" **failed**. The friendlier prompt rounded to "about ₹16,000", and the stated EMI must be exact under the KFS requirements. The gate blocked the merge, whereas the aggregate score alone would have shipped it. The fix kept the friendlier tone and exact figures.

**Healthcare – symptom-triage bot**
- **Input:** A new model version passed the aggregate gate with +3 points.
- **Output:** One must-pass item failed: "chest pain radiating to the left arm, sweating" must produce "call emergency services now".
- **Verdict:** The new model triaged it as "consult a doctor within 24 hours". That single item blocked the release. Investigation found that 4 of 40 red-flag scenarios (10%) had regressed. None of them affected the average by more than 0.5 points.

## The mistake people make
Gating only on the average, which is exactly where a single critical failure disappears.

## The line to use in a meeting
*"The average went up and the EMI answer broke. For the 40 answers that can't be wrong, we gate on each one individually."*

---

# I2 – SPLIT DETERMINISTIC TESTS FROM STATISTICAL EVALS; GATE ON A MULTI-RUN MEAN

## What it is
Unit tests (tool schemas, parsers, formatting) run on cached or temperature-0 responses and must pass 100%. Statistical evals run 3× and fail only when the **3-run mean** drops below baseline minus a tolerance band.

## Why it matters
**Flaky gates get ignored, then disabled, and then nothing is gated.** A gate that fails 18% of PRs for no reason teaches everyone to click "re-run" until it's green. At that point it isn't gating anything.

## How to do it properly
1. **Classify each check:** is it deterministic (a parser, a schema, a regex) or statistical (a quality score)?
2. **Deterministic checks** run on recorded responses and pass or fail with no tolerance.
3. **Statistical checks** run 3×, compare the mean with the baseline minus tolerance, and set the tolerance at about 2× the A/A SD.
4. **Track the gate's false-fail rate.** Above 5%, widen the tolerance or add runs.
5. **Cache the model responses** for the deterministic layer so it costs ₹0 per PR.

## Real scenarios

**Telecom – CI pipeline for a 12-language support bot**
- **Input:** One run per PR, fail if below baseline.
- **Output:** **18% false-fail rate.** Engineers had started re-running until green.
- **Verdict:** Gating on the 3-run mean with a ±2.5-point tolerance cut false fails to **2%**. The deterministic layer (Hindi numeral parsing, SMS length ≤ 160 characters) moved to cached responses. In the next quarter the gate caught 7 real regressions, and nobody bypassed it.

**E-commerce – catalogue-enrichment prompt changes**
- **Input:** A single gate mixed schema checks with quality scoring.
- **Output:** PRs failed on quality noise, so engineers disabled the gate "temporarily".
- **Verdict:** In the 3 weeks the gate was disabled, a PR broke JSON validity for 6% of outputs, which a deterministic check would have caught every time. Splitting the gate restored confidence. Schema validity is now a hard gate, and quality is gated statistically.

## The mistake people make
Putting stochastic quality scores in the same pass/fail gate as deterministic tests.

---

# I3 – ERROR ANALYSIS: SAMPLE 100 FAILURES, OPEN-CODE, COUNT

## What it is
You sample about 100 real failures (thumbs-down, escalations, failed evals), read each one, tag its root cause in free text, cluster the tags into categories and **sort by frequency**.

## Why it matters
**Teams fix the most memorable bug, not the most frequent one.** The failure someone screenshotted in Slack gets fixed first, whether it's 2% of failures or 40%. Counting fixes the order of work.

## How to do it properly
1. **Sample failures at random from the last 2–4 weeks,** not the ones people escalated to you.
2. **Tag the first root cause per item** in plain words.
3. **Cluster into 5–10 categories** and count them.
4. **Estimate the fix effort per category** and prioritise by frequency ÷ effort.
5. **Add every analysed failure to the eval set** (I8). This is how the flywheel turns.
6. **Repeat monthly.** The distribution shifts as you fix the top categories.

## Real scenarios

**Insurance – renewal-reminder generator**
- **Input:** 100 failures from customer complaints and QA flags.
- **Output:** Leadership's priority was "tone is too pushy", after one viral complaint.
- **Verdict:** **41 were date format (DD/MM vs MM/DD** on renewal due dates), 23 cited the wrong policy version and 12 misread Hinglish. Tone accounted for 4. The date fix took a day and removed 41% of failures. The tone rewrite, estimated at 3 weeks, moved down the list.

**Logistics – delivery-complaint bot**
- **Input:** 100 escalated conversations.
- **Output:** The assumption was that the bot "doesn't understand angry customers".
- **Verdict:** **38% were "delivered but not received"** complaints, where the bot kept quoting the tracking status ("aapka parcel deliver ho chuka hai") instead of opening a trace request. It wasn't a comprehension problem. The bot had no tool for opening a trace. Adding that tool cut escalations by 29%.

## The mistake people make
Prioritising by anecdote, or by whoever complained most recently.

## The line to use in a meeting
*"We read 100 failures. 41 were date formatting and 4 were tone. We're fixing dates first."*

---

# I4 – PINNED MODEL VERSIONS + DAILY CANARY EVAL WITH DRIFT ALERTS

## What it is
You call models by dated version identifiers, never by "latest" aliases. A fixed 100-item canary set runs daily against production config, and an alert fires when a metric falls **more than 3 SD below its 30-day mean**.

## Why it matters
**Providers update model aliases silently, so behaviour can shift without any code change.** JSON formatting, refusal rates, verbosity and language handling can all change overnight. Without a canary, customers are your alert.

## How to do it properly
1. **Pin every model**, both generator and judge, to a dated version. Treat upgrades as PRs through the CI gate (I1).
2. **Choose 100 canary items covering fragile behaviours:** strict JSON, regional languages, refusals, amounts.
3. **Run it daily** (or hourly for critical paths) and track 3–5 metrics.
4. **Alert at more than 3 SD below the 30-day mean.** 2 SD fires too often and 4 SD misses real shifts.
5. **Also run the canary against the provider's "latest" alias.** It warns you about upcoming changes before you migrate.

## Real scenarios

**E-commerce – catalogue enrichment that depends on strict JSON**
- **Input:** A daily canary of 100 product pages.
- **Output:** JSON validity fell from **92% to 84%** overnight with no deploy.
- **Verdict:** The alert fired at 6 a.m. The generator was configured with a "latest" alias that the provider had updated, and the new version wrapped JSON in markdown code fences. Pinning to the previous dated version restored 92% within an hour. Without the canary, about 1.3 lakh product pages would have been enriched with broken data before anyone noticed.

**Banking – credit-card servicing bot**
- **Input:** A daily canary on a pinned version, plus a parallel run on "latest".
- **Output:** The latest alias showed refusals on dispute questions rising from 1% to 9%.
- **Verdict:** Production was pinned, so customers saw no change. The team had 5 weeks' notice before the pinned version's deprecation date, found the new refusal trigger ("chargeback" was being read as a fraud-assistance request), and fixed the prompt before migrating.

## The mistake people make
Calling a "latest" alias in production and assuming behaviour won't change without a deploy.

---

# I5 – SAMPLED ONLINE EVAL: REFERENCE-FREE JUDGE + IMPLICIT SIGNALS

## What it is
You judge a random 1–2% of live traffic with a validated reference-free judge, and track implicit signals on 100% of traffic: thumbs up/down, escalation to a human, re-asks, abandonment. (Section A7 covers the tiered architecture.)

## Why it matters
**Live traffic has no ground truth, and judging all of it is too expensive.** Offline sets go stale, and live sampling is the only view of *today's* failures. Implicit signals are free and complete but noisy. Judged samples are precise but sparse. You need both.

## How to do it properly
1. **Take a uniform random sample of 1–2%**, stratified by intent and language if some slices are small.
2. **Use a judge validated on production-like data** (Section F), not just on the offline set.
3. **Track implicit signals with clear definitions:** re-ask means the same intent within 2 turns, abandonment means no reply within 10 minutes after a bot turn.
4. **Correlate the judge's scores with the implicit signals weekly.** If they diverge, one of them has drifted.
5. **Send judged failures straight into error analysis** (I3).

## Real scenarios

**Telecom – WhatsApp support bot for a mobile operator**
- **Input:** 2% of 5 lakh daily chats, which is 10,000 judged. Escalation rate tracked on 100%.
- **Output:** The judged quality score was stable at 87%.
- **Verdict:** Escalations climbed from **7.2% to 9.8%** over 10 days while the judge score stayed flat. The judged sample showed a new intent, a spike in "5G not working after SIM upgrade" queries following a network rollout, that the bot answered fluently and uselessly. The judge rated tone and relevance, not whether the problem got resolved. A "resolves or routes correctly" criterion was added, and the new intent got a troubleshooting flow.

**HR – employee helpdesk bot**
- **Input:** Thumbs down on 100% of traffic, and a 1% judged sample.
- **Output:** The thumbs-down rate was only 3%.
- **Verdict:** Only 6% of users ever clicked either thumb, and the judged sample put the real failure rate at **14%**. Implicit signals from a 6% self-selected slice weren't representative. Re-ask rate, measured on 100% of traffic, tracked the judge at r = 0.81 and became the headline live metric.

## The mistake people make
Treating thumbs-down rates as a quality metric when most users never click anything.

---

# I6 – BUSINESS OUTCOME METRIC TIED TO THE EVAL + GUARDRAILS

## What it is
You pick **one primary KPI with a ₹ value** (containment, resolution, conversion, handle time) and **2–3 guardrail metrics** that must not get worse (CSAT, complaints, escalations on sensitive intents). Offline eval scores are validated by whether they predict this KPI.

## Why it matters
**Offline gains that don't move outcomes waste roadmap time.** An eval score is a proxy. The KPI is what the business pays for. Guardrails stop you from buying the KPI with harm, for example "containing" customers by making it hard to reach a human.

## How to do it properly
1. **Put a ₹ value on the KPI:** containment × volume × cost of a human-handled contact.
2. **Define the guardrails** with thresholds ("CSAT must not fall by more than 0.1").
3. **Check the offline-to-online relationship** across releases (E2). If offline gains don't predict KPI gains, fix the eval.
4. **Report in ₹ at leadership level** and in eval points at team level.

## Real scenarios

**Banking – credit-card servicing bot**
- **Input:** 3 lakh chats a month. A release targeted containment.
- **Output:** Containment rose from **38% to 46%**.
- **Verdict:** That's 24,000 fewer agent calls × ₹35 = **₹8.4 lakh a month**. The guardrail check found that repeat contacts within 7 days rose 1.5 points, with customers coming back through the IVR. Netting those out, the real saving was ₹6.1 lakh a month. The release stayed, and the repeat-contact guardrail became permanent.

**E-commerce – returns bot**
- **Input:** A release that raised containment by 11 points.
- **Output:** It was celebrated in the weekly review.
- **Verdict:** Guardrails showed consumer-forum complaints up 40% and chargebacks up 18%. The new flow was steering customers into accepting store credit instead of refunds. By the numbers the release was a success, and in practice it was a legal and trust risk. It was rolled back within a week. Chargeback rate is now a hard guardrail with a ₹ cost attached.

## The mistake people make
Optimising a KPI with no guardrails, or reporting eval points to leadership without translating them into ₹.

## The line to use in a meeting
*"Containment is up 8 points, which is ₹8.4 lakh a month. Netting out repeat contacts, the real figure is ₹6.1 lakh."*

---

# I7 – PRE-REGISTERED ONLINE A/B TEST

## What it is
Before launching the test, you write down the primary metric, the sample size, the duration and the decision rule. You read the result once, at the end.

## Why it matters
**Peeking and choosing metrics after the fact manufacture false wins.** If you check a 2-week test daily and stop when it looks significant, the false-positive rate climbs from 5% to 20–30%. If you pick among 10 metrics after the test, one of them will look like a win by chance.

## How to do it properly
1. **Pre-register** the primary metric, the minimum detectable effect, n per arm, the duration (whole weeks, to cover weekday and weekend patterns), the guardrails and the decision rule.
2. **Size the test:** n per arm ≈ 16·p(1−p)/δ².
3. **Don't peek** unless you use a sequential design built for it (e.g. alpha spending).
4. **Check the traffic split** (sample-ratio mismatch). If a 50/50 split comes out as 50.8/49.2 on large n, something in the assignment is broken.
5. **Read the result once.** Every metric other than the primary one is exploratory.

## Real scenarios

**E-commerce – checkout assistant nudging COD users toward UPI**
- **Input:** Pre-registered: primary metric UPI conversion, 40% → 41% MDE, **≈ 38,000 sessions per arm**, 2 weeks, 50/50.
- **Output:** On day 4 the dashboard showed +2.3 points at p = 0.03, and the PM asked to ship early.
- **Verdict:** The team held to the plan. At 2 weeks the result was **+0.6 points (CI [−0.1, +1.3])**, not significant. The day-4 spike was a weekend payday effect in one arm. Shipping early would have claimed a gain of about 4× the real one.

**Insurance – quote-page chatbot**
- **Input:** An A/B test with no pre-registration.
- **Output:** Primary conversion flat. The team reported "+9% time on page, +4% scroll depth, +3% return visits."
- **Verdict:** A review found **14 metrics** had been checked after the test. Three "wins" at p < 0.05 is what chance would produce among 14. The pre-registered primary would have been conversion, which was flat. The chatbot was not expanded, and pre-registration became mandatory.

## The mistake people make
Checking the dashboard daily and stopping when it looks significant, or choosing the success metric after seeing the results.

---

# I8 – EVAL SET FROM STRATIFIED LOGS + PAST FAILURES + ADVERSARIAL ITEMS

## What it is
You build the eval set from three sources: a **stratified sample of real traffic** (by intent, language and difficulty), **every past production incident**, and **adversarial or edge cases**. Part of it is held out and never tuned on, and the set is refreshed quarterly.

## Why it matters
**A synthetic-only set misses Hinglish, typos and the real mix of intents.** Synthetic items are grammatical, polite and on-topic. Real users write "parcel delivered dikha raha hai par mila nahi", and those messages are where the failures happen.

## How to do it properly
1. **Stratify logs** by intent and language to match traffic, and over-sample small but critical intents.
2. **Add every past incident** as a permanent item. This is the flywheel: once a failure is found, it's tested on every future change.
3. **Add adversarial items** (injections, edge amounts, conflicting information) at 10–20%.
4. **Hold out 20%** that nobody tunes prompts against, and use it only for release decisions.
5. **Refresh quarterly** with new logs and retire items that every candidate passes.
6. **Scrub PII** before items enter the set.

## Real scenarios

**Logistics – delivery-complaint bot**
- **Input:** The original eval set had 500 synthetic items, and the bot scored 93% on it.
- **Output:** Production escalation rate was 21%.
- **Verdict:** A rebuilt 600-item set had 400 items from logs across 12 intents, **100 past failures** and 100 adversarial items, with 20% held out. It scored the same bot at **68%**. Hinglish complaints scored 51%, and the synthetic set had contained none. The new set's scores tracked escalations across the next 4 releases at r = 0.83.

**Fintech – UPI dispute bot**
- **Input:** Past incidents were fixed but never added to the eval set.
- **Output:** A prompt refactor 5 months later.
- **Verdict:** The refactor **re-introduced 3 of 7 previously fixed incidents**, including telling users that a failed UPI debit reverses "within 24 hours" when the NPCI timeline is T+1 working day. None of the 7 were in the suite. All incidents are now added automatically when an incident ticket is closed, and the suite grew by 140 items in a quarter.

## The mistake people make
Fixing a production incident without adding it to the eval set, so a later change can bring it back unnoticed.

## The line to use in a meeting
*"Every incident we fix goes into the test suite permanently. Otherwise we'll be fixing the same bug again in six months."*

---

# I9 – SHADOW MODE → STAGED CANARY WITH AUTO-ROLLBACK

## What it is
The new version runs **silently** on live traffic alongside the current one (shadow), with outputs logged and compared but not shown to users. Then it's served to a growing share of users (1% → 10% → 50% → 100%), with automatic rollback triggers at each stage.

## Why it matters
**Offline eval misses production edge cases, so you limit how many users a failure can reach.** Shadow mode shows how the new version behaves on real traffic at zero user risk. A staged canary with automatic rollback means a missed failure reaches 1% of users for hours, not everyone for days.

## How to do it properly
1. **Shadow for 3–7 days.** Log the disagreement rate with the current version and judge a sample of the disagreements.
2. **Read the disagreements.** They're where new behaviour appears, for better or worse.
3. **Define rollback triggers before starting,** for example escalation +1 point, error rate above 0.5%, any must-pass canary item failing.
4. **Hold each stage 24–48 hours,** long enough to cover daily traffic patterns.
5. **Automate the rollback.** Rolling back shouldn't depend on someone being awake at 2 a.m.

## Real scenarios

**Healthcare – appointment-booking bot for a multi-city hospital chain**
- **Input:** A new model shadowed for 1 week on 50,000 requests.
- **Output:** **6% disagreement** with the current model.
- **Verdict:** In the judged disagreements, the new model was better in 71% of cases. But 40 of them were cases where it booked with the **wrong doctor at the same department in a different city**. The shadow logs showed it resolving "Dr. Sharma, cardiology" without checking the city. The issue was fixed before any patient was affected. The 5% canary then ran 48 hours with no rollback trigger, and the rollout completed.

**Telecom – new intent router**
- **Input:** Canary at 10% with an auto-rollback trigger at escalation +1 point.
- **Output:** The trigger fired at hour 9.
- **Verdict:** A new intent label for "port-out requests" was routing to a flow that didn't exist in one region's config. It affected 10% of traffic in one circle for 9 hours, about 2,100 users. A full rollout would have hit about 21,000 in that circle alone. The rollback was automatic. The config gap was added to the pre-rollout checklist and as a canary item.

## The mistake people make
Going from offline eval straight to 100% of traffic.

---

# SECTION I DECISION FLOW

```
START: You're changing something that will reach users.
│
├─ Does the change pass CI?
│     ├─ deterministic layer: 100% (cached responses) (I2)
│     ├─ statistical layer: 3-run mean ≥ baseline − tolerance (I2)
│     └─ must-pass golden set: every item passes (I1)
│
├─ Is it a new model or major version?
│     └─ YES → shadow 3–7 days, read disagreements → staged canary + auto-rollback (I9)
│
├─ Is it a product bet with a business KPI?
│     └─ YES → pre-registered A/B: metric, n (≈16·p(1−p)/δ²), duration, rule (I7)
│              └─ primary KPI in ₹ + 2–3 guardrails (I6)
│
├─ Once live:
│     ├─ daily canary on pinned versions; alert at > 3 SD below 30-day mean (I4)
│     ├─ 1–2% judged sample + implicit signals on 100% (I5)
│     └─ monthly: 100 failures → open-code → count → fix the biggest (I3)
│
└─ Every failure found anywhere above:
      └─ becomes a permanent eval item; refresh set quarterly; 20% held out (I8)
```

---

# THE THREE THINGS TO REMEMBER

1. **Gate every change on a must-pass set as well as the average.** A single critical failure can hide inside an improving mean.

2. **Tie the eval to money and protect it with guardrails.** Translate eval points into ₹ for leadership, and watch the metrics a "win" might damage.

3. **Every production failure becomes a permanent test case.** Offline evals only contain what you've already found, so production has to keep supplying the rest.
