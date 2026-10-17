# S14 / EL-114 — Enrich C + D from the deep dives

**Status:** complete, with one deliverable partially blocked by the schema (§5, finding F5).
418 passed · `check_integrity()` returns `[]` · `mypy --strict` clean · 73 records.

**Read:** `knowledge rules/C-deciding-whether-a-result-is-real.md`, `knowledge rules/D-rare-events.md`, `CLAUDE.md` §4, `TASKS.md` S14 + T16.5, `AGENT.md` §3.8 + §5, `USER_EXPERIENCE.md` §3.1, `decisions/EL-004-claude-md-corpus-gaps.md`.
**Citations** are `C:<line>` and `D:<line>` against the two deep dives, `E:<line>` against `E-when-a-number-looks-wrong.md`. Every citation in this report and in both record files was re-resolved against the file after writing; the only ones pointing at a heading are the two deliberate record-title references (`C:94`, `D:26`).

---

## 1. What changed

| | C | D |
|---|---|---|
| `source_ref` | → `C-deciding-whether-a-result-is-real.md § C1` … `§ C6` | → `D-rare-events.md § D1` … `§ D6` |
| `requires` | C3 re-cited; the other five stay empty **on purpose** (§4c) | D1, D5, D6 now bounded |
| `rule_of_thumb` | all 6 carry the corpus's verbatim formulas | all 6 |
| `companion_checks` | C3 → B1, E4 | D1, D2, D3, D5, D6 — 9 edges |
| `unlocks` | none (§4d) | D1 → D2/D3, D2 → D4, D5 → D6 |
| `required_signals` | all 6 sharpened | all 6 sharpened |

`anti_pattern`, `worked_example` and `domain_scenario` were **not touched** in either file — they are the master lookup's columns and `test_verbatim_fields_match_the_lookup_row` diffs them against the corpus. It still passes.

---

## 2. The three numbers the docs disagreed on

**The corpus file decides.** All three rows below were resolved against it, and in every case `CLAUDE.md` §4 was already right — `EL-004` had corrected it. The stale copies were in `TASKS.md` and `AGENT.md`.

| | What the corpus says, verbatim | Which doc was wrong | Fix applied |
|---|---|---|---|
| **1. Power** | `C:19` "*Sample size per arm ≈ 16·p(1−p) / δ²* (α = 0.05, 80% power)", restated identically at `C:69` "**Unpaired:** n ≈ 16·p(1−p)/δ² per arm" and `C:249` | **`TASKS.md` S14 and T16.5** and **`AGENT.md` §3.8**, all three saying `n ≈ 16/gap²`. `CLAUDE.md` §4 ✅ already correct | `rule_of_thumb` on C2 now carries the corpus form, **plus the paired formula `C:70` that no doc of ours had at all**. All three stale sites rewritten |
| **2. Noise floor** | `C:94` (the record's own title) "**k ≥ 5 RUNS PER ITEM; REPORT MEAN ± SD ACROSS RUNS**", `C:97` "you run the full eval k ≥ 5 times", `C:242`. `C:103` is the only place 3 appears, and it *downgrades* it: "Run k = 5 for decisions and k = 3 for daily iteration" | **`TASKS.md` S14** ("3–5 runs"), **`AGENT.md` §3.8** ("3–5 repeat runs"), and — not named in the ticket — **`USER_EXPERIENCE.md` §3.1** ("needs runs: 3") and **`TASKS.md` S18's render mock** (same). `CLAUDE.md` §4 ✅ already correct | `requires: {runs: 5}` was already right and is unchanged; `rule_of_thumb` now carries `C:103` verbatim so the k=3 exception is visible. All four stale sites rewritten |
| **3. CI margin** | **C never states it.** `grep "100/√n"` over the C deep dive returns nothing. It is `B:22` (section B's own rule of thumb) and `B:176`, i.e. **B5's** | **`TASKS.md` S14**, which listed `margin ≈ 100/√n` as a verbatim target *for this stage*. `CLAUDE.md` §4 ✅ already attributes it to B. `AGENT.md` §3.8 listed it unsectioned, so not wrong, only vague | Nothing to record in C. S13 already put it in B5's `rule_of_thumb`. `TASKS.md` S14 now says it is not C's and cites where it lives; `AGENT.md` §3.8 now tags each formula with its record |

### Why "3–5" is wrong rather than merely loose

Worth stating, because it looks like a harmless paraphrase. `C:103` splits the two uses: **5 for decisions, 3 for daily iteration.** A "3–5 runs" range flattens that and implies 3 is acceptable for a decision — which is the exact failure C3 exists to prevent. So the range is a claim the corpus denies, not a rounding of it.

### Where the "3–5" probably came from

`E:134`, `E:140` and `E:309` give **E4, the A/A baseline, its own "3–5 times"** — a genuinely different record with a genuinely different k. `TASKS.md` line 112 lists "E4 3–5 runs" among the stated ranges, and **that line is correct and must stay.** Two records measure run-to-run noise at different k, and the likeliest origin of the error is one being quoted under the other's name. Flagged in `TASKS.md`'s next-action note for S15, which owns E.

### Two more conflicts the ticket did not name

4. **The rare-class accuracy figure.** The ticket offered "flag nothing scores 99.8%" with the caveat *"if that is what it says"*. **It is not.** The corpus says **97%**: `D:32` "A model that predicts 'all good' scores 97% accuracy and catches 0% of fraud" *when fraud is 3% of traffic*, and `D:45` "The 'always legit' baseline scores 97.0% accuracy". 99.8% is `D6`'s **"% safe" headline** from the unrelated HR bias audit (`D:217`). The 99.8% figure had propagated into **`USER_EXPERIENCE.md` §3.1**, **`AGENT.md` §5's constraint table** and **`TASKS.md` S18's render mock**; all three now say 97%.

   One thing to note about this number: **there is no prevalence-free version of it.** The baseline accuracy *is* one minus the prevalence, so 97% is only true at D1's 3% fraud rate. The corrected docs therefore read "scores 97% at 3% prevalence" rather than quoting a bare percentage — otherwise we would be reproducing, in our own docs, exactly the context-free percentage D1 forbids.

5. **Two stale record ids in the render mocks.** `USER_EXPERIENCE.md` §3.1 and `TASKS.md` S18 both named `C3_noise_floor` and `A3_deterministic`; neither id exists (`C3_repeat_runs`, `A3_normalised_exact_match`). These are the ids S18 will be implemented against, so both are corrected.

**`E1-M0-TICKETS-AND-PROMPTS.md` is deliberately left alone.** It still contains `16/gap²`, `3-5 runs` and `99.8%`. It is the ticket archive — those strings are the historical prompts, and editing them would falsify the record of what was asked.

---

## 3. C4's near-boundary condition — and why it could not go in `requires`

The ticket said "into `requires` **or** `required_signals`, verbatim". It is in `required_signals`, and the choice was forced rather than preferred:

```
required_signals:
  "the observed score is near 0% or 100%, or n < 100"                 ← C:245 verbatim
  "the event count and n are both known"
  "zero events in n trials are reported with the upper bound, never
   as \"0 failures\" or \"100%\""                                      ← C:138
  "Clopper–Pearson is used when a regulator or auditor wants a
   conservative exact interval, Wilson otherwise"                     ← C:140
  "counts are reported next to percentages, so the reader sees the
   evidence and the sample size in one figure"                        ← C:141
rule_of_thumb:
  "Rule of three: 0 failures in n items → the true failure rate is
   ≤ 3/n at 95% confidence. Turned around to size a safety eval,
   claiming ≤ 0.1% needs 3,000 clean items and ≤ 0.01% needs 30,000"  ← C:20 + C:139
```

**`n < 100` is an upper bound.** `requires` reads every value as a floor, so `{n: 100}` would mean "needs n ≥ 100" — which would switch C4 off in exactly the small-n case it exists for, and switch it on where Wilson's advantage over Wald has gone. This is the sharpest instance of S13's finding **F3** (`requires` encodes no direction) and the **first where the wrong encoding would be actively harmful rather than merely inert**: an unrepresentable threshold left out costs a pending state, but an inverted one silently changes the plan.

`C:139`'s 3,000 and 30,000 are conditional on which claim you want to make, so neither is a readiness threshold either.

---

## 4. Thresholds

### 4a. Copied verbatim into `requires`

| record | key | value | source |
|---|---|---|---|
| C3 | `runs` | `5` | `C:94` (title) "**k ≥ 5 RUNS PER ITEM**", `C:97`, `C:242`. Already correct from S10; unchanged, re-cited |
| D1 | `positives` | `100` | `D:238` decision flow, "Do you have **≥ 100** positives in your eval set?" |
| D6 | `attempts_per_category` | `50` | `D:210` "**Flag every category with fewer than 50 attempts as 'under-tested'**", repeated `D:259` "any category < 50 attempts → mark under-tested; no claim" |

D6's is exactly the pending state the ticket asked for: below 50 attempts in a category, the planner marks it pending rather than reporting a bound the corpus says cannot support a claim.

### 4b. Copied verbatim into `rule_of_thumb`

Every symbol kept as the corpus writes it (`δ²`, `√`, `·`, `−`, `π`, `ᵏ`, `t*`, `≤`, `≥`).

| record | content | source |
|---|---|---|
| C1 | print `82.0% [73.3, 88.3] n=100` by default; CI above bar → ship, below → no, straddling → more data | `C:34`, `C:36` |
| **C2** | **`Sample size per arm ≈ 16·p(1−p) / δ²`**; unpaired `n ≈ 16·p(1−p)/δ²` per arm; **paired (McNemar) `n ≈ (1.96·√d + 0.84·√(d − δ²))² / δ²`** | `C:19`, `C:69`, **`C:70`** |
| **C3** | **`Run k = 5 for decisions and k = 3 for daily iteration`**; a difference is real only if > ~2× the run-to-run SD *and* the paired CI agrees | `C:103`, `C:107` |
| C4 | rule of three, `≤ 3/n` at 95%, and its inversion for sizing a safety eval | `C:20`, `C:139` |
| C5 | `P(at least one false alarm) = 1 − 0.95ᵏ`, 64% at k = 20; Bonferroni `α = 0.05/k`; Holm's descending ladder; BH at `q = 0.10` | `C:21`, `C:173`, `C:174` |
| C6 | 10,000 shuffles, smallest reportable p = 1/10,000; median or 10% trimmed mean for heavy tails; report p95/p99 separately | `C:209`, `C:207`, `C:210` |
| D1 | `To see k positives at prevalence π, you need about k/π random samples` — 100 frauds at 0.3% needs 33,000; PR-AUC's baseline equals the prevalence | `D:22`, `D:32` |
| **D2** | **`Precision_deployed = TPR·π / (TPR·π + FPR·(1−π))`** — precision doesn't carry over between prevalences but recall does; 96% on a 50/50 enriched set can be 9% in production | `D:21`, which `D:70` points back to by name |
| D3 | compare AP with bootstrap CIs (0.03 apart on 150 positives is a tie), then at candidate operating points | `D:103`, `D:104` |
| **D4** | **`t* = C_fp / (C_fp + C_fn)`** for a calibrated model; the more a miss costs, the lower the threshold | `D:132` |
| D5 | `ASR = successful attacks / attempts`, per category with Wilson CIs, never only the pooled ASR | `D:176` |
| D6 | lead with the upper bound: "≤ 0.4% at 95%", not "99.8% safe" | `D:208` |

### 4c. Left empty — and for C this is a finding, not a gap

**Five of C's six records have `requires: {}`, and that is correct.** C is the section that decides whether *other* records' numbers are real; its own techniques mostly need no accumulated evidence. C2 is the clearest case: a power analysis runs **before any data exists**, so there is nothing to be ready for, and `gates: false` says the same thing. This is the first section where an empty `requires` is a positive statement rather than an absence, and it is worth recording so a later stage does not "fix" it.

The exception noted for the record: **C6 has no minimum item count**, so like B1 (S13's finding) it would be called ready at n = 1. The 10,000 shuffles are a method parameter, not an evidence floor.

**Stated ranges, not reduced to a number** (continuing S10's policy):

| range | source | consequence |
|---|---|---|
| 100–300 positives | `D:35` | D1 uses `D:238`'s hard `≥ 100` instead, so nothing is lost here |
| 6–12 harm categories | `D:173` | D5 has no category-count floor |
| 20–30% quarterly refresh | `D:177` | carried in `required_signals` as prose |

### 4d. Interpreted from prose — **FLAGGED FOR HUMAN REVIEW**

**One, and it is the only interpretation in the whole stage.**

**`D5 requires.attempts_per_category: 50`** — `D:173` says "Typically 6–12, each with **at least 50–100** prompts". The category count is a range and is left out. The 50 is the **lower end of an "at least" range read as the floor.**

What makes it defensible rather than a pick from a range: **`D:210` states 50 independently, as a hard bound, on the same quantity** — "Flag every category with fewer than 50 attempts as 'under-tested'". D5 builds the per-category set and D6 reports it, so the two records agree on where under-testing starts, and taking the lower end of D5's range lands on D6's stated bound rather than somewhere inside it.

*If overruled:* D5 keeps no per-category floor, and the planner cannot mark a thin category pending at the point where the set is being built — only later, at D6, when it is being reported.

Everything else in C and D is verbatim or null.

---

## 5. Schema findings

S13 raised F1–F4 and they all still stand. One new one, and it blocks a deliverable of this ticket.

### F5 — A `constraint` record has no field naming what it forbids ← *new, and blocking*

This is ticket deliverable 3, and it is **partially blocked**.

`AGENT.md` §3.5 step 2: "Apply `constraint` records. **Anything they prohibit** is removed from `ready` and listed in `prohibited` **with the reason**."
`USER_EXPERIENCE.md` §3.1 wants the line:

```
PROHIBITED   accuracy          rare_class: "flag nothing" scores 97% at 3% prevalence
```

Three parts. **Two are already renderable** from D1 as it now stands:

| part | field | status |
|---|---|---|
| `rare_class` — where it applies | `triggers_on_situation` | ✅ renderable |
| the reason, with the corpus's figure | `anti_pattern` | ✅ renderable |
| **`accuracy` — what is forbidden** | **none** | ❌ **no field holds it** |

`produces` holds the *replacement* metrics (`precision_recall_curve`, `pr_auc`) — a repurposing S11 already made. `conflicts_with` holds **record ids**, and there is no "accuracy" record to point at: **accuracy is never codified as a technique anywhere in the corpus.** It exists only inside other records' prose. So the forbidden thing is not in the registry at all, and cannot be referenced by the one field designed for "this replaces that".

D6 shows the same gap in a harder form: what it forbids is a **pooled percentage headline**, not a named metric, so even a metric-name field would not hold it cleanly.

Two ways out, both needing a ruling:

- **(a) Add `prohibits: tuple[str, ...]`**, holding metric names, symmetrical with `produces`. Clean and directly renderable. Cost: a 23rd **required** field, so all 73 record files, `FIELD_NAMES`, the loader and the registry fixtures change. Every field in `TechniqueRecord` is required by design, so there is no cheap optional-field version of this.
- **(b) Author "anti-technique" records** for forbidden things so `conflicts_with` can point at them. No schema change at all. Cost: records for things the corpus does not teach as techniques, which breaks "one row per technique" and the 73-record count that `test_section_count_matches_the_lookup` guards against the corpus.

**Recommendation: (a).** (b) puts invented rows in the registry to avoid adding a field, which trades a schema problem for a corpus-fidelity problem.

Not implemented, per `CLAUDE.md` §7.5. The repo-wide blast radius makes it a decision to take in the open, and it wants an `EL-0NN` doc rather than a quiet 73-file diff.

### Still open from S13, with new instances from this stage

- **F3 (`requires` has no direction or range)** now has its worst case: C4's `n < 100`, where encoding it would **invert** the record's trigger (§3). Also C3's "~2× the run-to-run SD" (`C:107`) and D6's "for example ≤ 2%" bar.
- **F2 (no field for a trust bar on a produced metric)** gains `C:107`'s 2-SD band — a bar on `sd_across_runs`, which C3 itself produces.
- **F1 and F4** gained no new instances in C or D.

---

## 6. Corpus-internal discrepancy, left as found

**C2's power figures disagree between the master lookup and the deep dive.**

| source | unpaired | paired |
|---|---|---|
| master lookup, C row | "≈ **905** items per arm" | "a paired design with **60% agreement** needs ≈ **400**" |
| deep dive `C:19`, `C:65` | "≈ **920** items per arm" | "about **12% of items flip** … drops to ≈ **375**" |

Different figures *and* a different paired parameter (agreement vs discordance). `worked_example` is lookup-verbatim and guarded by `test_verbatim_fields_match_the_lookup_row`, so **it is not touched** — changing it would break the guard that proves our records match the corpus, to resolve a disagreement inside the corpus itself. Recorded in C2's `extraction_notes` and raised here. This is the corpus's to fix, not the registry's.

---

## 7. D's companion pairings

### precision ⇔ a stated recall level — **done, in both places the source puts it**

- **Inside D2.** `D:63` "You require precision ≥ X … and then maximise recall under that constraint" and `D:71` "Maximise recall at that floor. Accept whatever recall results, even 60%". A precision floor is reported *with* the recall it bought, and D2's `produces` already carries `precision_at_floor` **and** `recall_at_floor`. No companion edge is needed or appropriate — the pairing is internal.
- **Across records, D3 → D2.** `D:104` "Then compare at candidate operating points. **Show recall at the precision floor** and at the review budget for each model." "Recall at the precision floor" is precisely what D2 produces.

**The direction is one-way, and the source requires only one.** D3 cannot be read without D2's operating point; D2 does not need a threshold-free comparison, and `D:69`–`D:72` names no AP. The ticket said "in BOTH directions **if the source demands both**" — it demands one, so one is encoded.

### violation rate ⇔ over-refusal rate — **NOT ENCODABLE, and this is the finding**

`AGENT.md` §5 lists it as a non-negotiable: "Violation rate always reported with over-refusal rate | **Never alone**".

**There is no over-refusal record in the registry.** Grepping the whole corpus for `over-refus`, `over-block` and `over-abstention` returns hits in **G6 only**, scoped to RAG answerables (`G:195` pairs a false-answer rate with an over-abstention rate *for retrieval*). Section D has none, and section I has none.

So the pairing cannot be written from D5 or D6. Pointing either at G6 would make a safety plan demand a RAG record — wrong, and it would misreport a RAG metric as a safety one.

**`EL-004` found this gap already**, as item 5 of "what the registry will not be able to plan": *"No record pairing an over-refusal rate with a violation rate… so a safety plan will report ASR (D5) with no over-blocking counterpart."* S14 confirms it from the other side: `AGENT.md` §5 **demands a pairing the methodology does not contain.** Either `AGENT.md` drops the non-negotiable, or the corpus gains a safety over-refusal technique. Both are outside this stage.

**Corrected a wrong claim while I was there.** D6's `extraction_notes` from S11 said "the over-refusal half is section I's, so no cross-reference is written here". It is not section I's — it does not exist. The note now says so, with the grep that establishes it.

### The other nine D edges, each named by the source

| edge | source |
|---|---|
| D3 → `B6_bootstrap_ci` | `D:103` "Compare AP with bootstrap CIs **(Section B6)**" |
| D5 → `C1_wilson_ci` | `D:176` "Report ASR per category with Wilson CIs **(Section C)**" |
| D5 → `F1_gold_label_validation` | `D:175` "a category-specific rubric, validated against human labels **(Section F)**" |
| D6 → `C4_near_bounds_interval` | `D:202` "the upper Wilson or Clopper–Pearson bound, or 3/n at zero" — C4's three outputs exactly |
| D6 → `C1_wilson_ci` | `D:209` per-category table "with counts, rates and Wilson CIs" |
| D1, D2 → `C1_wilson_ci` | `00-INDEX.md:35`, principle 2 |
| D1 → D2, D3 · D2 → D4 · D5 → D6 (`unlocks`) | the deep dive's **own numbered pipeline**, `D:11`–`D:15` |

`unlocks` follows the pipeline box rather than the decision flow, because the box numbers its five steps explicitly (1 Measure → 2 Constrain → 3 Price → 4 Attack → 5 Report) while the decision flow presents them as independent branches.

And **C3 gained two companions the corpus names as records**: `C:107` "the paired CI **(B1)** agrees" → `B1_paired_evaluation`, and `C:105` "Don't treat temperature 0 as deterministic … Measure it **(see E4)**" → `E4_aa_baseline`.

---

## 8. Smaller things, recorded so they are not silent

- **C:175's winner's curse has no record.** "After picking the best of N variants, re-measure the winner on a held-out set. Its original score is biased upwards." No section codifies this as a technique, so it survives only as a `required_signal` on C5. `EL-004` listed selection effects among the registry's blind spots; this is a concrete instance with a concrete instruction attached.
- **Fixed a garbled `required_signal` on D4.** S11 wrote "a **dishonest** and a missed detection both have a stated rupee cost" — "a dishonest" is a corruption of "a false alarm" (`D:138` "Get C_fp and C_fn from the business owner, in ₹"). That field is our own prose, not lookup-verbatim, so correcting it drifts from nothing.
- **C1's `companion_checks` stays empty on purpose.** C1 is the record *others* name; naming anything back would make every interval drag a second record into the plan. Open ruling 1 (C1's unmappable "Any score, ever" situation) is now **two-thirds resolved by companion edges**: S13 wired all seven A records, S14 adds D5 and D6 plus D1/D2. E–J remain for S15–S17, after which C1 is reachable from any graded artifact and the narrow trigger set stops mattering.
- **`schema.py`'s docstring cites "BH q = 0.10 (C:174)"** while arguing for float support in `requires`. `q` is a correction *parameter*, not a readiness threshold, so S14 put it in `rule_of_thumb`. The docstring's framing should be corrected when EL-107's `requires` type is settled — it is currently the only place implying q belongs in `requires`.
- **`produces` was left alone throughout**, as in S13, since it is outside the enrichment field list. Two records would gain outputs if it were in scope: C2's MDE (`C:71` tells you to publish it) and A1's failure class.
- **`gates` confirmed, not re-derived.** C1/C3/C4/C5/C6 and D2/D3 statistical; D1/D5/D6 absolute; C2 and D4 `false`. C2's `false` is now positively justified by `C:238` (it runs before data exists) rather than merely derived.
