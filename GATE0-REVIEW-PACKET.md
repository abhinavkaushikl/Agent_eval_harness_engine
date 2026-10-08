# 🔒 Gate 0 — review packet

**What this is.** `PLAN.md` §5 makes the human review of the 20 rendered plans *the gate*: "Human reads all 20 rendered plans and agrees with every one. Fix anything disputed before M1." This is that packet. Read it in one sitting and either agree or send it back.

**State at the time of writing:** 73 records · 641 tests passing, 0 skipped · `mypy --strict` clean · `check_integrity()` empty · 17 of 20 fixtures asserted and passing, 3 blocked on a ruling.

**How to read it.** §1 is the 20 plans, each with one line saying what it claims and the corpus line that makes it right. **§2 is my doubts** — if you read only one section, read that one; it is where I think you may disagree, stated as the alternative rather than as a defence. §3 is the definition-of-done with commands and output. §4 is the findings ledger from EL-103 to EL-123. §5 answers M0's actual question.

**Nothing was changed to make this packet read well.** No planner code was written, no fixture edited, no plan "fixed". Two factual corrections were made and are listed in §3.

---

## 1. The 20 plans

Every `render()` block below is produced by `evalloop.plan.planner.plan()` at review time, not transcribed. `GATE0-RENDERED-PLANS.md` holds the same 20 with a test asserting it stays current.

Three plans are marked **⚠ BLOCKED ON A RULING**: their fixture asserts nothing, because the specification contradicts the corpus or names something that does not exist. The plan is still rendered, because the plan is what the ruling is about.

### 01 · `code_generation_first_run`

**Claims:** run the generated code and put an interval on the result. **Right because** `A:6` says grade with the cheapest method that can actually *observe* what you care about, and execution is the only rung that sees whether code works — `A:51` measures the gap, a judge passing 88% where execution passed 63%; `C1` attaches because `00-INDEX.md:35` puts a confidence interval on every number.

```
situations      code_generation
available_tools sandbox, test_runner
evidence        {'samples': 1, 'runs': 1}

READY        A1_execution_based · C1_wilson_ci
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 02 · `code_generation_no_sandbox`

**Claims:** with no sandbox there is nothing honest to run on code, so the whole plan is one permission request. **Right because** `A:21` is "if a line of code can check it, a line of code should check it" and `A:15` routes only open-ended text to a judge — so no lower rung applies to code, and `A:31` shows what judging it costs (a judge scored 79% where execution scored 68%, passing 22 queries that returned the wrong rows).

```
situations      code_generation
available_tools test_runner
evidence        {'samples': 1, 'runs': 1}

READY        (none)
PENDING      (none)
UNAVAILABLE  A1_execution_based  missing: sandbox
PROHIBITED   (none)
```

### 03 · `summarization_first_run`

**Claims:** the only technique for prose is an LLM judge, and it may not be used until it agrees with humans. **Right because** `F:72` states "use a grader only at 0.6 or above" and `F:17` is "human–human agreement is the ceiling — no judge can be validated above it".

```
situations      summarization
available_tools llm_api, llm_api_cross_family, source_doc_read
evidence        {'samples': 1, 'runs': 1}

READY        (none)
PENDING      A4_judge_binary_criteria  needs judge_human_kappa_to_trust: 0.6, have 0; judge_human_kappa_to_gate: 0.8, have 0
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 04 · `rag_answer_recall_before_faithfulness`

**Claims:** measure retrieval first; faithfulness waits for it. **Right because** `G:6` is "evaluate retrieval and generation separately, because an end-to-end score can't tell you which stage to fix", and `G:292` splits the score at G1 with G2/G3/G5/G7 hanging beneath it.

```
situations      rag_answer
available_tools vector_store, llm_api
evidence        {}

READY        G1_component_wise_eval · C1_wilson_ci
PENDING      G3_faithfulness               needs recall_at_k_measured: true, have false; claim_labels: 150, have 0
             G5_mrr_hit_at_k               needs recall_at_k_measured: true, have false
             G7_context_precision          needs recall_at_k_measured: true, have false
             G2_oracle_context_test        needs recall_at_k_measured: true, have false
UNAVAILABLE  G4_ndcg                       missing: human_labels
             G6_unanswerable_set           missing: source_doc_read
             G8_citation_precision_recall  missing: source_doc_read
PROHIBITED   (none)
```

### 05 · `agent_action_no_trace_capture`

**Claims:** no agent number is trustworthy until the environment resets per run and the trajectory is logged. **Right because** `H:291` is the section's own first gate — "Is the environment sandboxed and reset per run? (H1) / NO → build it first".

```
situations      agent_action
available_tools sandbox, db_connection, cost_api
evidence        {}

READY        (none)
PENDING      H2_outcome_based_success   needs environment_resets_per_run: true, have false
             H4_cost_per_success        needs environment_resets_per_run: true, have false
UNAVAILABLE  A2_end_state_verification  missing: snapshot_restore
             H3_pass_hat_k              missing: snapshot_restore
             H5_milestone_localisation  missing: trace_capture
             H6_injection_asr           missing: trace_capture
             H8_flaky_classification    missing: snapshot_restore
             H1_resettable_env          missing: snapshot_restore, trace_capture
             H7_trajectory_taxonomy     missing: trace_capture
PROHIBITED   (none)
```

### 06 · `structured_extraction_with_schema`

**Claims:** check the schema and the fields in code, with an interval. **Right because** `A:14` routes "it fills a structure (JSON, form)" to A5 at ₹0 and deterministic, and `A:21` says a line of code should check what a line of code can.

```
situations      structured_extraction
available_tools (none)
evidence        {'samples': 1}

READY        A5_schema_field_scoring · C1_wilson_ci
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 07 · `two_candidates_one_run`

**Claims:** compare on the same items now; the significance test waits for disagreements. **Right because** `00-INDEX.md:36` uses the same items on both sides of every comparison, and `B:107` needs "at least 25 discordant pairs (b + c ≥ 25)" for McNemar's χ² approximation.

```
situations      two_candidates
available_tools (none)
evidence        {'runs': 1}

READY        B1_paired_evaluation
PENDING      B3_mcnemar              needs discordant_pairs: 25, have 0
             E1_per_item_diff        needs runs: 2, have 1
UNAVAILABLE  B2_pairwise_preference  missing: llm_api
             H4_cost_per_success     missing: cost_api
PROHIBITED   (none)
```

### 08 · `two_candidates_eight_discordant`

**Claims:** eight disagreements is not enough to call a winner. **Right because** `B:107` puts the floor at 25, and `B:121` is the scenario where ignoring it turned p = 0.057 into a declared win at p = 0.033.

```
situations      two_candidates
available_tools (none)
evidence        {'paired_runs': 2, 'discordant_pairs': 8}

READY        B1_paired_evaluation
PENDING      B3_mcnemar              needs discordant_pairs: 25, have 8
             E1_per_item_diff        needs runs: 2, have 0
UNAVAILABLE  B2_pairwise_preference  missing: llm_api
             H4_cost_per_success     missing: cost_api
PROHIBITED   (none)
```

### 09 · `two_candidates_forty_discordant`

**Claims:** forty disagreements clears the floor, so the significance test can run. **Right because** `B:107`'s bound is met, which is the only thing that changed between this plan and the one above.

```
situations      two_candidates
available_tools (none)
evidence        {'paired_runs': 2, 'discordant_pairs': 40}

READY        B1_paired_evaluation · B3_mcnemar
PENDING      E1_per_item_diff        needs runs: 2, have 0
UNAVAILABLE  B2_pairwise_preference  missing: llm_api
             H4_cost_per_success     missing: cost_api
PROHIBITED   (none)
```

### 10 · `new_judge_zero_labels`

**Claims:** you can build the judge's prompt now, and you cannot trust it yet. **Right because** `F:17` makes human agreement the ceiling and `F:36` needs "at least 50" fail cases in the validation sample.

```
situations      new_judge_built
available_tools human_labels, llm_api
evidence        {}

READY        F7_one_call_per_criterion
PENDING      F1_gold_label_validation        needs fail_cases: 50, have 0
             F8_few_shot_from_disagreements  needs majority_samples: 3, have 0
             F2_cohens_kappa                 needs judge_human_kappa_to_trust: 0.6, have 0; judge_human_kappa_to_gate: 0.8, have 0
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 11 · `new_judge_sixty_labels_kappa_point_seven_one`  —  ⚠ **BLOCKED ON A RULING**

**Claims:** at κ 0.71 on 60 labels the judge may be *used* and may not *gate* a release. **Right because** `F:72` is "use a grader only at 0.6 or above, and gate releases only at 0.8 or above" — which is the opposite of this fixture's specified expectation, and the reason it is blocked.

```
situations      new_judge_built
available_tools human_labels, llm_api
evidence        {'gold_labels': 60, 'fail_cases': 60, 'judge_human_kappa_to_trust': 0.71, 'judge_human_kappa_to_gate': 0.71, 'majority_samples': 3}

READY        F1_gold_label_validation · F7_one_call_per_criterion · F8_few_shot_from_disagreements
PENDING      F2_cohens_kappa   needs judge_human_kappa_to_gate: 0.8, have 0.71
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 12 · `rare_class_accuracy_prohibited`

**Claims:** plot the precision–recall curve, and never report accuracy. **Right because** `D:32` is the figure — predicting "all good" scores 97% accuracy and catches 0% of fraud at 3% prevalence — and `D:238` gates the curve on "≥ 100 positives in your eval set".

```
situations      rare_class
available_tools (none)
evidence        {'positives': 100}

READY        C1_wilson_ci · D1_pr_curve_never_accuracy
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   D1_pr_curve_never_accuracy  rare_class: Predicting "all good" scores 97% accuracy with 0% recall, and ROC-AUC also looks flattering under imbalance
```

### 13 · `grouped_items_cluster_bootstrap_replaces`

**Claims:** when items come in groups the cluster bootstrap *replaces* the plain one. **Right because** ten questions from one document are correlated, so an item-level interval comes out too narrow and gives false confidence (B7's own row), and `B:246` tags every item with its cluster id.

```
situations      grouped_items, metric_without_formula
available_tools (none)
evidence        {'cluster_id_recorded': True}

READY        B7_cluster_bootstrap
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 14 · `small_sample_margin_stated`  —  ⚠ **BLOCKED ON A RULING**

**Claims:** at n = 25 the only thing on offer is a Wilson interval. **Right because** `C:245` routes small n to Wilson — but the margin a user most needs here, `B:22`'s 100/√n = ±20 points, is unreachable from this situation, which is why the fixture is blocked.

```
situations      small_sample
available_tools (none)
evidence        {'samples': 25}

READY        C1_wilson_ci
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 15 · `score_jumped_investigation`

**Claims:** diff the two runs item by item before believing the jump, and the noise baseline is not there yet. **Right because** `E:11` is the symptom box's own first action — "Score jumped suddenly → E1 per-item diff, read the flips".

```
situations      score_jumped
available_tools (none)
evidence        {'runs': 2}

READY        C1_wilson_ci · E1_per_item_diff
PENDING      E4_aa_baseline    needs runs: 3, have 2
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 16 · `all_candidates_high_ceiling`

**Claims:** when everyone scores 90%+ the set is too easy, so build a harder one from real failures. **Right because** `E:15` is "Everyone scores 90%+ → E5 harder set from real failures".

```
situations      all_candidates_high
available_tools production_logs
evidence        {}

READY        C1_wilson_ci · E5_harder_set
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 17 · `length_increased_summarization`

**Claims:** the answers got longer, so control for length before calling it better. **Right because** `E:13` is "Score up, answers got longer → E3 length-controlled win rate", and `AGENT.md` §5 reports any judge score with output length.

```
situations      length_increased, summarization
available_tools (none)
evidence        {}

READY        C1_wilson_ci · E3_length_controlled_win_rate
PENDING      (none)
UNAVAILABLE  A4_judge_binary_criteria  missing: llm_api
PROHIBITED   (none)
```

### 18 · `api_endpoint_and_sql_generation`

**Claims:** both artefacts are graded by execution, and the record appears **once**. **Right because** `A:6` grades by what can observe the property, and `AGENT.md` §3.5 step 1 merges multi-label input without duplication.

```
situations      api_endpoint, sql_generation
available_tools sandbox, test_runner
evidence        {'samples': 1}

READY        A1_execution_based · C1_wilson_ci
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 19 · `shipping_change_gates`

**Claims:** gate the merge on a must-pass set, stage the rollout, show the per-item diff — and the tolerance is not calibrated yet. **Right because** `I:33` blocks the merge "if the aggregate drops beyond a tolerance **or any must-pass item fails**", and `I:41` takes that tolerance from E4's A/A noise band.

```
situations      shipping_change
available_tools test_runner, repo_read, production_logs
evidence        {'runs': 2}

READY        E1_per_item_diff · I1_ci_regression_gate · I9_shadow_then_canary
PENDING      E4_aa_baseline    needs runs: 3, have 2
UNAVAILABLE  (none)
PROHIBITED   (none)
```

### 20 · `phi_present_gate_precedes_everything`  —  ⚠ **BLOCKED ON A RULING**

**Claims:** nothing about PHI, because no record mentions it — this is fixture 6's plan with an extra situation attached. **Right because** it is not: "PHI" appears nowhere in `knowledge rules/`, so there is no gate to order first, which is why the fixture is blocked.

```
situations      phi_present, structured_extraction
available_tools (none)
evidence        {'samples': 1}

READY        A5_schema_field_scoring · C1_wilson_ci
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

---

## 2. Things I would question if I were you

Ordered by how much the answer changes. Each is the **alternative** and the line that would support it — not a defence of what is there.

### 2.1 Plan 03 — a summarization session offers *nothing*. This is the one I would push back on.

**What you would question:** the plan for the single most common artefact in the corpus is empty.

**The alternative:** `A4`'s κ bars do not belong in `requires`. Make the judge **READY with its calibration state attached**, and let κ block only at the gate.

**The line that supports it:** `F:72` is *"Use a grader only at 0.6 or above, and gate releases only at 0.8 or above."* That is a **usage rule and a gating rule** — two different bars on two different acts. `requires` is the *readiness* field, so putting either in it reads as "not enough data yet", which is a third thing the corpus never says. Worse, the suppression cascades: step 6 follows companion edges only out of *ready* records, so a pending A4 takes the mandated length-bias check (`AGENT.md` §5, "any judge score is reported with output length") out of the plan with it.

**What it costs to change:** a new field, and `A4`/`F2`/`F9` re-authored. This is finding **F2**, raised at S13 and listed as cosmetic for four stages; plan 03 is what it actually costs.

### 2.2 Plan 07/08/09 — `B1_paired_evaluation` is READY at one run

**What you would question:** a "paired difference" computed over a single pair is not a fact, and `PLAN.md` §5 says a single observation should yield only facts.

**The alternative:** gate `B1` on `B5_ci_from_n`, which already **unlocks** it.

**The line that supports it:** `B:22` — *"the worst-case 95% margin on a percentage is about 100/√n points"* — is the thing that makes a one-pair difference meaningless, and `B5` is the record that holds it. The edge exists in the registry and does nothing, because **`unlocks` is read by no step of `AGENT.md` §3.5**. That is finding **F8**, and this is its visible cost.

**Note:** the same is true of `C6_permutation_test` (one permutation), which no fixture happens to select.

### 2.3 Plan 12 — `D1` is in READY **and** PROHIBITED, and the word "accuracy" never appears

**What you would question:** one record occupying two mutually exclusive states, and a prohibition that cannot name what it prohibits.

**The alternatives, two of them:** (a) `prohibited` excludes anything in `ready`; or (b) `D1` splits into a constraint and a metric.

**The lines:** `CLAUDE.md` §6 types `constraint` as "forbids something" and `metric` as a number — `D1` is both, because the master lookup gives it one row and the one-row-one-record rule forced the merge. And the PROHIBITED line reads `D1_pr_curve_never_accuracy  rare_class: …` where `TASKS.md` S23's own mock wants `accuracy  rare_class: …`; no field names the forbidden metric (finding **F5**). `TASKS.md` already records that this line "cannot be rendered from the schema" — I am confirming it by having built it.

### 2.4 Plan 04 — G4 and G5 are pending on recall@k, and their own text never says so

**What you would question:** two of the five records gated by the RAG build order are gated on the section's flow diagram rather than on anything they themselves state.

**The alternative:** drop `recall_at_k_measured` from `G4_ndcg` and `G5_mrr_hit_at_k`, leaving G2, G3 and G7 gated.

**The line:** `G:292-295` is the only authority, and it is a diagram. G4's own case for being downstream is `G:130` — *"Recall@k ignores order, but users only read the top 3"* — which is a **rationale for why nDCG exists**, not a statement that recall must be measured first. G7 by contrast is gated on its own instrument: `G:230` injects distractors "into gold context", and gold context is G1's apparatus. **Nothing else in the registry depends on this call.**

### 2.5 Plan 19 — `I1` is READY while the companion that supplies its tolerance is PENDING

**What you would question:** the CI gate is offered before the number that parameterises it exists.

**The alternative:** report `I1` as ready **for the must-pass half only**, or hold it until `E4` lands.

**The lines, pulling against each other:** `I:41` takes the aggregate tolerance from E4's A/A noise band, so the aggregate half genuinely cannot run. But `I:33` blocks the merge *"or any must-pass item fails"*, and `I:58` is the mistake this record exists to prevent — *"Gating only on the average, which is exactly where a single critical failure disappears."* Holding `I1` back would suppress the half that needs no tolerance. **I chose the reading that keeps the must-pass gate, and the schema cannot express "half ready".**

### 2.6 Plan 02 — nothing remains without a sandbox. Should a judge be the last resort?

**What you would question:** A's ladder says to prefer the highest rung that *can* answer the question, which implies falling to a lower one.

**The alternative:** let `A4` trigger on `code_generation` as a bottom rung.

**The lines:** `A:6` says use a judge *"only when nothing deterministic can see the property"* — which could license a judge when execution is unavailable. Against it: `A:15` routes only open-ended text to A4, and `A:31`/`A:51` measure what judging code costs (79% vs 68%, and 88% vs 63% — "mostly well-written code that didn't work"). **I lean to the empty plan**, because the corpus measures the failure rather than merely warning about it, but the ladder's wording is on your side if you disagree.

### 2.7 Plan 05 — `A2_end_state_verification` carries no environment gate

**What you would question:** `A2` triggers on `agent_action` and sits in section A, so with `snapshot_restore` granted it would be READY while `H1` had never run — making `AGENT.md` §5's "resettable environment before any agent eval" true across H and not across the whole agent plan.

**The alternative:** add `{environment_resets_per_run: true}` to `A2.requires`.

**The line:** `H:291`. **Why I did not:** `A2` also triggers on `api_endpoint` and `data_pipeline`, where the gate is meaningless, and `requires` has no situation scope (finding **F4**). A faithful fix needs F4 first.

### 2.8 Plan 13 — the conflict edge needed a second situation to be observable at all

**What you would question:** the fixture states `grouped_items` *and* `metric_without_formula`, which looks like a contrivance.

**The alternative:** have `B6_bootstrap_ci` trigger on `grouped_items` too, so the replacement is visible from the situation that calls for it.

**The line:** B7's own row is about correlated items within a cluster; B6's situation cell is `metric_without_formula`. **A plan built from `grouped_items` alone never contains B6**, so the edge the corpus states would be untestable — and a fixture that only checked B7's presence would pass whether or not replacement worked.

### 2.9 Two thresholds I recorded from hedged prose

Both would be defensible as `null`, and both are in the human-review queue in §4.

* **`I3 {failures: 100}`** from `I:100`'s *"about 100 real failures"*. "About" is a hedge; I recorded it because the row's own title is "SAMPLE 100 FAILURES" and the ticket asked for it verbatim.
* **`J1 {smoke_items: 50}`** from `J:33`/`J:44`/`J:45`. This **overturns S12's call** that the 50 was part of the technique's name rather than a readiness bound.

### 2.10 One `gates` value I changed

**`I6_business_metric_guardrails`: `false` → `absolute`.** S12 read the lookup row as stating no gate; `I:207` says *"Define the guardrails **with thresholds**"* and `I:221` says a breach rolled a release back and *"Chargeback rate is now a hard guardrail"*. **The alternative** is to revert: the thresholds are per-deployment, so arguably the methodology states no bar, only an instruction to set one.

---

## 3. M0 definition of done — `PLAN.md` §5, with evidence

| | line | evidence |
|---|---|---|
| ✅ | `pytest` green | `python -m pytest -q` → **`641 passed in 0.30s`**, 0 skipped |
| ✅ | `mypy --strict` clean | `python -m mypy --strict evalloop/` → **`Success: no issues found in 16 source files`** |
| ✅ | ~70 records load | `len(load_records(RECORDS_DIR))` → **`73`** |
| ✅ | integrity check returns nothing | `check_integrity(records)` → **`[]`** |
| ⚠ | **All 20 fixtures pass** | `pytest -k test_fixture` → **`17 passed`**. **3 are blocked on a ruling and assert nothing** — 11, 14, 20. See §1 and §4.3. |
| ⚠ | **Sanity queries give sensible answers** | `pytest -k sanity` → **`7 passed`**, but the tests assert what the planner *does*: **three of six diverge from `PLAN.md`** — see below |
| ✅ | All 20 rendered plans printed for human review | `python -m tests.render_gate0` → `GATE0-RENDERED-PLANS.md`, 20 plans; `pytest tests/test_planner_artifact.py` → **`5 passed`**, including a currency check |

### The six sanity queries, honestly

| | query | verdict |
|---|---|---|
| ✅ | RAG → recall ordered before faithfulness | met |
| ✅ | code generation → execution first, judging excluded | met, but **vacuously**: A4 never matches `code_generation`, so the suppression edge never fires |
| ⚠ | rare class → recall ready, accuracy prohibited | **half**: prohibition is structural only (F5); recall is pending below 100 positives |
| ❌ | summarization → faithfulness with the length check | **neither**: faithfulness is unreachable, the length check is suppressed with its pending host (§2.1) |
| ❌ | single observation → only facts | **no**: `B1` and `C6` fire at n = 1 (§2.2) |
| ⚠ | 200+ samples → significance tests, judge agreement | **true as asked, wrong records**: the only ≥200 bars are `A6` (items: 200) and `A7` (5000). Significance is a *formula* (`C2`) and judge agreement a *range* (F1's 150–200, left null), so the query cannot be answered from `requires` at all |

**So `PLAN.md` §5 is not met as written, and `PLAN.md` was not edited.** Two of the three failures are the two findings in §2.1 and §2.2. Moving the gate's wording, or fixing F2 and F8, is your ruling.

### Corrections made while assembling this packet

Two citations in my own prose did not resolve, found by sweeping every `<LETTER>:<line>` reference in code, records and fixtures against the corpus:

* the "Bootstrap κ" line: I had written line 73, which is "Report per-class precision and recall". It is **`F:74`** — 5 places.
* "Gating only on the average": I had written line 63, which is blank. It is **`I:58`** — 1 place.

No behaviour changed. The sweep now reports **zero unresolvable citations** anywhere in code, records or fixtures.

---

## 4. Findings ledger, EL-103 → EL-123

### 4.1 Thresholds left `null`, and why

The rule: **a stated *range* is never recorded**, because picking a value from a range is the invented number `CLAUDE.md` §3 forbids. Every row below is a real figure in the corpus that is deliberately *not* in `requires`; each lives verbatim in `rule_of_thumb` or `required_signals` instead.

| record | the figure | line | why null |
|---|---|---|---|
| `A4` | 150–200 gold labels | `A:146` | range |
| `C3` | "3–5 runs" | `C:103` | **not a range**: C:103 *downgrades* 3 to daily iteration, so 5 is the bound and 3 is a different use |
| `D5` | 6–12 categories | `D:173` | range (the per-category 50 **is** recorded) |
| `E2` | 6–10 releases | `E:74` | range → carried as a boolean instead (interpreted, §4.2) |
| `F1` | 150–200 gold labels | `F:27`, `F:30` | range (F1's own single bound, "at least 50" fail cases at `F:36`, **is** recorded) |
| `F3` | 20–30% overlap | `F:105` | range |
| `F4` | flip rate above 10–15% | `F:140` | **both a range and an upper bound** — `requires` can hold neither, and encoding it would *invert* the record's trigger |
| `F6` | 4–8 checks | — | range |
| `G1` | 200–300 questions; ~40/annotator-hour | `G:33` | range; and a rate, not a bound |
| `G2` | 100–200 failures | `G:68` | range |
| `G4` | 0–3 scale, top 10–20, 200–500 queries | `G:133-134` | ranges |
| `G6` | 15–25% unanswerables; ≤5% / ≤8% bars | `G:188`, `G:196` | range; and the bars are prefaced "for example" |
| `G7` | 1–3 distractors, 150–200 queries | `G:228`, `G:230` | ranges |
| `H5` | 5–10 sub-goals | — | range |
| `H6` | 100–300 injected items | `H:198` | range |
| `H7` | 50–100 traces | `H:232` | range |
| `I1` | 200–300 suite, 20–50 must-pass, "2 points" | `I:39-41` | ranges; and "more than 2 points" is prefaced "for example" |
| `I3` | 2–4 weeks, 5–10 categories | `I:106`, `I:108` | ranges |
| `I5` | 1–2% of traffic | `I:174` | range |
| `I8` | 10–20% adversarial; hold out 20% | `I:274-275` | range; and 20% is a *fraction of a set*, not a count of evidence |
| `I9` | 3–7 days, 24–48 hours | `I:308`, `I:311` | ranges |
| `J1` | 3–5 finalists | `J:46` | range |
| `J2` | 300–500 items | `J:68` | range (the 100 human pairwise judgments **is** recorded) |
| `J5` | 100–200 held-out items | `J:186` | range — **although it is the row's own readiness condition**, so this is the most arguable null |

Also null by a different rule: **every bar on a *produced* metric**, because no field holds one (finding F2). Ten instances, all verbatim in `rule_of_thumb`: `G7`'s "a drop of more than 5 points", `G6`'s two launch bars, `I2`'s 5% false-fail ceiling, `J1`'s "below 50% accuracy", `J4`'s 5–10 point setup swing, and the formulas `G:20`, `G:93`, `H:21`, `H:22`, `H:137`.

### 4.2 Thresholds **interpreted** from prose — the human-review queue

Six entries. Each is a number the corpus states but not in a form `requires` can take verbatim; each is flagged in its record's `extraction_notes`.

| record | recorded | interpretation | stage |
|---|---|---|---|
| `A6` | `items: 200` | `A:217` says "Draw 200 items" — read as a readiness floor | S13 |
| `B5` | `sample_size_stated: true` | `B:175` states a *consequence*, not a flag | S13 |
| `B7` | `cluster_id_recorded: true` | `B:246` gives an *instruction*, not a flag | S13 |
| `D5` | `attempts_per_category: 50` | lower end of `D:173`'s "at least 50–100" — defensible because `D:210` states 50 independently | S14 |
| `E4` | `runs: 3` | lower end of `E:140`'s "3–5 times"; **overturns S10's call** to leave it empty | S15 |
| `E2` | `release_history_available: true` | `E:74`'s "6–10 releases" is a range, so the *precondition* is carried as a boolean and the count is dropped | S15 |
| `I3` | `failures: 100` | `I:100`'s "about 100" — a hedge (§2.9) | S17 |
| `J1` | `smoke_items: 50` | overturns S12's call that the 50 was part of the name (§2.9) | S17 |

**Eight, not six.** Nothing else in the 73 was interpreted.

### 4.3 Source rows and fields that could not be represented

| what | where it bites | finding |
|---|---|---|
| A constraint cannot name **what it forbids** | the PROHIBITED line reads as a record id (§2.3) | **F5** |
| No field for a **bar on a produced metric** | 10 instances; and the κ bars landed in `requires` instead, which empties plan 03 (§2.1) | **F2** |
| `requires` cannot hold a **range or an upper bound** | ~26 figures left null (§4.1); `F4`'s ceiling would *invert* its trigger | **F3** |
| No **fallback** field when a bound is unmet | `B3` → exact binomial (`B:107`) is unexpressible | **F1** |
| No `wraps`/`modifies` edge; `conflicts_with` has **no artifact or situation scope** | `A7` over the ladder, `B7` over `B6`; and blocks the `A2` fix (§2.7) | **F4** |
| No field for a diagnostic's **first action** | all 8 E records; captured in `extraction_notes` instead | **F6** |
| Nothing prevents a record **gating itself** | `G1` and `H1` must be exempted by hand or their section deadlocks | **F7** |
| **`unlocks` is read by nothing** in §3.5 | `B5 → B1` does nothing (§2.2); D's pipeline and F's calibration stack gate nothing | **F8** |
| Two numbers from **one record** cannot be marked never-alone | `D6`, `G6`, `H6`, `I6` — four instances, all `AGENT.md` §5 non-negotiables, zero enforceable | **F9** |
| `conflicts_with` cannot hold a **data-conditional** conflict | `G4` vs `G5`: both trigger on `rag_answer` alone, so the edge would fire every session | **F10** |
| `gates` holds **one value** where `I2` needs two | `I:68` states "must pass 100%" (absolute) and "fail only when the 3-run mean" (statistical) in one sentence; the safety half is lost | **F12** |
| The production **flywheel is a cycle**; `unlocks` is a DAG | 5 of 6 arrows written; `I9 → I5` dropped deliberately | **F13** |
| `Plan`'s five fields cannot render §3.1's PROHIBITED **reason** | a sixth field, `prohibition_reasons`, was added | **15** |

### 4.4 Vocabulary gaps

| gap | detail |
|---|---|
| **6 of 57 `Situation` members reach no record** | `classification`, `data_pipeline`, `model_training`, `contamination_risk`, `distribution_mismatch`, `phi_present`. `match()` returns nothing for them, so such a session gets an empty plan with no explanation. |
| ↳ one is a plain authoring miss | **`contamination_risk` is dead while `E7_contamination_check` exists** and triggers on `benchmark_too_good` only. One line in S15's file — not changed, because a trigger change decides which sessions select the record. |
| **2 of 15 `Tool` members unused** | `ocr`, `vision_model`. |
| **No tool subsumption** | `llm_api_cross_family` does not satisfy `llm_api`, so plan 03 must be granted both. `EL-002` puts grant kinds in the capability layer, which is where an implication belongs. |
| **No `Tool` member for an evaluation harness** | `J:154` reruns benchmarks "on one harness"; `test_runner` is the nearest and was *not* stretched to cover it. |
| **Section G collapses onto one member** | all 8 G rows trigger on `rag_answer`, so `match()` cannot discriminate within G; the build order is what sequences them (plan 04 shows four distinct states from one member). |
| **C1 "Any score, ever" has no faithful mapping** | no member means "a score exists"; C1 triggers on the ten measurement members plus `small_sample`, and the real route is `companion_checks` from every grader and metric. |
| **Two F rows have no `grader_trust` member** | F7 "judge grades the wrong dimension" and F8 "want better judge accuracy" both map to `new_judge_built`. |
| **H1's "Any agent evaluation"** | a universal within H, the same unmappable shape as C1's. |

### 4.5 Techniques the corpus names and the registry does not hold

| missing | named in | consequence |
|---|---|---|
| **Reward-hacking detection** | `AGENT.md` §3.8, `ARCHITECTURE.md` §10 Track L, `TASKS.md` T30.5 | `ARCHITECTURE.md` §5.1's strongest intent signal — "just make the test pass" in a transcript — has nothing to route to. Fixture 15 asserts the diagnostics that *do* exist. |
| **"Slice the results"** | `00-INDEX.md:37`, the **fourth of five** cross-cutting principles | codified nowhere. It appears *inside* D5, G5, I8, J2 and J5; `J:120`'s critical-slice check has nothing to point at. |
| **PHI / redaction gate** | `phi_present` in the enum; `ARCHITECTURE.md` §4.3 | "PHI" appears nowhere in the corpus. Plan 20 is the consequence. |
| **The winner's curse** | `C:175`, "re-measure the winner on a held-out set" | no record in any section. |
| **Summarization faithfulness** | — | G3 is scoped to retrieved context; no row covers entailment against a source document. Plan 03's first cause. |

### 4.6 Schema changes raised, and how each resolved

| raised | resolution |
|---|---|
| `requires` typed `Mapping[str, int \| bool]` in `CLAUDE.md` §6, but the corpus has **float** thresholds (κ 0.6, α 0.667, token-F1 0.8, BH q 0.10) | **Widened** to `int \| float \| bool`. A schema that could not hold `0.6` would force an author to write `60`. |
| `domain_scenario` had no home | **Added** as a 22nd field, `decisions/EL-011`. |
| `gates` has **no null member**, but 25 rows state no gate | **Not changed.** "The source states no gate" is written `Gate.false`, and every such record says so in `extraction_notes`. |
| Integrity rule 4 ("every grader has a rung") contradicted the corpus twice | **Scoped twice**: to all-or-nothing (S10), then to **section A only** (S13), because `B2_pairwise_preference` is a grader the corpus never places on A's ladder and inventing a rung is forbidden. |
| `TechniqueRecord` is **unhashable** (frozen dataclass holding a `MappingProxyType`) | **Accepted and documented.** Nothing in M0 needs it; records are keyed by `id`. |
| F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F12, F13 | **All raised, none implemented**, per `CLAUDE.md` §7.5. See §4.3. |
| `Plan` needs a sixth field to render a prohibition reason | **Implemented** as `prohibition_reasons`, keeping §3.5's five exactly. Ruling **15**. |

### 4.7 Numbers that turned out to be cross-contamination between records

Four, each found by reading the corpus rather than the docs. Worth listing because three of our own documents were wrong:

1. **"3–5 runs noise floor"** under `C3`'s name was `E4`'s A/A figure. (S14)
2. **"50–100 human labels"** under `F1`'s name was `A:143`'s error-analysis sample ("Read 50–100 real outputs") and `H:232`'s trace count. F1's real figure is **150–200**, at `F:27`/`F:30`; A4's own 150–200 is a third statement, at `A:146`. (S15)
3. **F's 150–200 gold labels** is *not* `G3`'s **"150+"** claim labels (`G:102`) — different statements, and the latter is a single bound, so it **is** recorded. (S16)
4. **`margin ≈ 100/√n`** was attributed to section C; it is **B5's** (`B:22`). C never states it. (S14)

---

## 5. Does situation → technique matching work?

**Yes, and the weakest link is the vocabulary, not the machinery.** The seven-step order does what it claims: 73 records load clean, 17 hand-written fixtures derived from the corpus reproduce exactly, the build orders that `AGENT.md` §5 calls non-negotiable hold as data rather than as comments (plan 04 puts faithfulness behind recall; plan 05 puts nothing in front of a resettable environment), and the three states that mean "no" each carry a reason a user can act on. Where the plan is thin it is usually *honestly* thin — plan 02's single permission request is the right answer, not a gap.

**The weakness is on the way in.** `match()` is only as good as the situation mapping, and that mapping is where the corpus and the enum fit worst: **six of 57 members reach no record at all**, so a session classified into any of them gets an empty plan with no explanation; all eight RAG rows collapse onto `rag_answer`, so within section G the *build order* is doing work the situation vocabulary should be doing; and the two universals (`C1`'s "any score, ever", `H1`'s "any agent evaluation") have no faithful member, so they are reached through `companion_checks` rather than by matching. None of that is visible in the 20 plans, because every fixture states a situation that *does* reach something — which is precisely why I would not read Gate 0's green as evidence that the front door is sound.

**The second weakness is that two correct edges change nothing.** `unlocks` is read by no step, so orderings recorded there — D's pipeline, F's calibration stack, `B5 → B1` — are documentation. That is why `B1` fires on one pair (§2.2). And `requires` is carrying two different kinds of bar: "enough evidence yet" and "trustworthy enough to use", which is why plan 03 is empty (§2.1). **Those two findings, F8 and F2, are the difference between a planner that is right and a planner that is right for the right reasons.** I would rather you ruled on them before M1 builds on top.

---

### What I need from you

1. **Agree or dispute each of the 20 plans** (§1).
2. **Rule on §2.1 (F2) and §2.2 (F8)** — the two that change what the product shows on day one.
3. **Rule on the three blocked fixtures** — 11 (κ/labels), 14 (`small_sample` → B5), 20 (PHI). Options are written out in each `.BLOCKED.yaml` and in `S19-REPORT.md`.
4. **Decide whether `PLAN.md` §5's wording moves**, or whether F2 and F8 are fixed to meet it (§3).
5. **Clear the eight interpreted thresholds** (§4.2), or send any of them back to `null`.

Fifteen rulings are open in total; twelve are decisions rather than work.
