# S17 / EL-117 — Enrich I + J, and the end-to-end sweep

**Status:** complete, and **the registry is finished**. 419 passed · `check_integrity()` returns `[]` · `mypy --strict` clean · 73 records · `unlocks` acyclic · **all 73 `source_ref`s resolve to a real deep-dive subsection, now asserted by a test**.

**Read:** `knowledge rules/I-production.md`, `knowledge rules/J-choosing-a-model.md`, `knowledge rules/00-INDEX.md`, `AGENT.md` §3.5 + §5, `PLAN.md` §5, `TASKS.md` S17 + Group 6.

**Citations** are `I:<line>` and `J:<line>` against the two deep dives. Every citation written into either record file was re-resolved by script afterwards; **ten were wrong on the first pass** and are fixed (`I:36`→`I:33`, `I:70`/`I:71`→`I:68`, `I:99`→`I:100`, `I:224`→`I:221`, `I:236`→`I:237`, `J:112`→`J:111`, `J:73`→`J:74`, `J:166`→`J:230`). The pattern in both S16 and S17: a citation to a record's thesis sentence tends to land on the `## Why it matters` heading one line above it.

> **§4 is the part to read.** The `PLAN.md` §5 sanity queries do **not** all come out the way `PLAN.md` says they should, and two of the four problems are in the docs rather than the records. One is a genuine consequence of an earlier policy decision and is the most important finding in M0.

---

## 1. What changed

| | I | J |
|---|---|---|
| `source_ref` | → `I-production.md § I1` … `§ I9` | → `J-choosing-a-model.md § J1` … `§ J5` |
| `requires` | 4 of 9 bounded (§2) | 3 of 5 bounded (§3) |
| `unlocks` | 6 edges, following the flywheel | 2 edges, following the funnel |
| `companion_checks` | 8 edges, 6 cross-section | 8 edges, **all** cross-section |
| `gates` | **I6 `false` → `absolute`** (§5) | unchanged — the source states none for any of the five |
| `required_tools` | unchanged | J1 `+llm_api +cost_api` · J4 `+llm_api` · J5 `+llm_api` |
| `rule_of_thumb` | all 9 extended verbatim | all 5 |
| `required_signals` | all 9 sharpened from "How to do it properly" | all 5 |

`anti_pattern`, `worked_example` and `domain_scenario` were **not touched** — patched key-by-key, and `test_verbatim_fields_match_the_lookup_row` still passes.

**Registry totals, now final:** 73 records · 7 graders, 16 metrics, 14 statistics, 10 diagnostics, 23 procedures, 3 constraints · gates 17 absolute / 31 statistical / 25 false · `requires` bounded on 42 of 73, of which 17 carry a boolean · 44 `unlocks`, 72 `companion_checks`, 5 `conflicts_with`.

---

## 2. Section I — the gates, the history, and a cycle that would not fit

### `gates`, with the deep-dive line for each

| | value | source |
|---|---|---|
| I1 | `absolute` | `I:33` "The merge is blocked if the aggregate drops beyond a tolerance **or any must-pass item fails**" |
| I2 | `statistical` | `I:68` — **but see below** |
| I3 | `false` | states none |
| I4 | `statistical` | `I:145` "Alert at more than 3 SD below the 30-day mean" |
| I5 | `false` | states none |
| I6 | **`absolute`** ← changed | `I:207` "Define the guardrails **with thresholds**"; `I:221` "is now a hard guardrail" |
| I7 | `statistical` | `I:240` pre-registration + `I:244` "Read the result once" |
| I8 | `false` | states none |
| I9 | `absolute` | `I:310` "Define rollback triggers before starting" |

### I2 gates two ways and the schema holds one value ← finding **F12**

`I:68` is one sentence containing both halves: *"Unit tests … run on cached or temperature-0 responses and **must pass 100%**. Statistical evals run 3× and **fail only when the 3-run mean** drops below baseline minus a tolerance band."*

That is an **absolute** gate and a **statistical** gate, and the record *is* the split — its name is "Split deterministic tests from statistical evals". `gates: Gate` holds one value.

`statistical` is kept, matching the row's name and its `anti_pattern` ("Flaky gates get ignored, then disabled"). **The loss is real and it is on the safety side:** a planner reading this record alone cannot tell that a JSON-schema failure must block outright, which is exactly the E-commerce scenario at `I:88-91` — *"a PR broke JSON validity for 6% of outputs, which a deterministic check would have caught every time."* `A5_schema_field_scoring` carries `gates: absolute` and is the nearest record that does say so.

**Proposal:** `gates: Gate | tuple[Gate, ...]`, or a second field scoping the absolute half to the deterministic layer. **Not implemented**, per `CLAUDE.md` §7.5. This is the ticket's own framing — "ABSOLUTE for safety and schema, STATISTICAL for quality" — and I2 is the one record that needs both at once.

### History requirements, which is what the ticket asked for

| record | `requires` | source |
|---|---|---|
| `I2` | `{runs: 3}` | `I:76` "Statistical checks run 3×" — a single count; S12 had left it empty |
| `I3` | `{failures: 100}` | `I:97` (the row's own title) and `I:100` "about 100 real failures" |
| `I4` | `{baseline_days: 30}` | `I:145` — the alert is defined against a **30-day mean**, so on a fresh install there is no baseline to be 3 SD below |
| `I7` | `{pre_registration_filed: true}` | `I:240` — a **boolean**: an A/B read without a pre-registered primary metric is the false win `I:237` describes, where peeking takes the false-positive rate "from 5% to 20–30%" |

`I4`'s is the one the ticket named ("needs history, so requires a baseline") and `baseline_days: 30` is it, read straight off the line that defines the alert.

`I1` is deliberately **unbounded**, and that is the point of the record: the must-pass half fires on the first run, because one failure there is an incident whatever the aggregate says. Gating it would invert its own thesis.

### The production flywheel is a cycle, and `unlocks` must stay acyclic ← finding **F13**

`I:9-21` draws six arrows:

```
eval set from logs (I8) → CI gate (I1, I2) → shadow/canary (I9)
        ↑                                           ↓
error analysis (I3) ← live sampling (I5) + daily canary (I4)
```

**Five are written. The sixth is not, and cannot be.**

| edge | written? | authority |
|---|---|---|
| `I5 → I3` | ✅ | `I:178` "Send judged failures straight into error analysis (I3)" |
| `I3 → I8` | ✅ | `I:110` "Add every analysed failure to the eval set (I8). **This is how the flywheel turns**" |
| `I8 → I1`, `I8 → I2` | ✅ | the flywheel box's own arrow, `I:13-17` |
| `I1 → I9`, `I2 → I9` | ✅ | the decision flow, `I:336-342` — CI before any rollout |
| **`I9 → I5`** | ❌ | the box only; writing it makes `unlocks` **cyclic** |

The dropped arrow was chosen, not lost: it is the least gate-like of the six — nothing has to be unlocked before you may start sampling live traffic — and it is the only one drawn in the box and never stated in a record's prose. The two `I3 → I8` and `I5 → I3` arrows, which are the flywheel's actual point, are both kept.

**This is the first place the corpus's own structure is a cycle and the registry's is a DAG.** Nothing in the schema says `unlocks` must be acyclic; the stages have simply verified it each time, and `check_integrity()`'s docstring lists cycles among the things it deliberately does not check. If `unlocks` is ever read by the planner, the ruling needed is whether a cycle is a defect or a legitimate description of a loop.

### Cross-section companions, each from its own line

`I1` → `E1` (`I:42` "Post the diff in the PR: newly failing items, newly passing items") and `E4` (`I:41` the tolerance comes from the A/A noise band) · `I2` → `E4` (`I:76` "about 2× the A/A SD") · `I4` → `I1` (`I:142` "Treat upgrades as PRs through the CI gate") · `I5` → `F1` (`I:175` "a judge validated on production-like data (Section F)") · `I6` → `E2` (`I:208`) · `I7` → `C2` (`I:241`, the formula verbatim) and `C5` (`I:244` "Every metric other than the primary one is exploratory", and the insurance scenario's 14 metrics yielding three chance "wins") · `I9` → `E1` (`I:308` "Log the disagreement rate … and judge a sample of the disagreements").

**`E4` is a companion and not a gate on `I1`** on purpose: gating the whole record on an A/A baseline would hold back the must-pass check, which needs no tolerance at all.

---

## 3. Section J — pointing at B and C rather than restating them

The ticket asked for this explicitly, and it is the whole shape of the section. Every statistical claim in J is an edge:

| edge | source line |
|---|---|
| `J1` → `B5` | `J:28` "Its margin is ±14 points" — which is B5's own `margin ≈ 100/√n` at n = 50 (100/√50 = 14.1) |
| `J2` → `B1`, `C1` | `J:79` "Report pass rates with **Wilson CIs** and **paired CIs of the differences**" |
| `J2` → `E5` | `J:78` "Include your hard set (E5)" |
| `J2` → `F4` | `J:80` "100 human pairwise judgments **(both orders)**" — position swap by another name |
| `J3` → `B1` | `J:119` "Test equivalence with a paired CI" |
| `J3` → `H4` | `J:111` "₹ per 1,000 tasks, or ₹ per *successful* task (H4)" |
| `J5` → `C1` | `J:188` "report Wilson CIs by slice" |
| `J5` → `E7` | `J:190` "Re-test on a fresh sample after onboarding to catch any **tuning to your data** during the pilot" — contamination, applied to a vendor |

**`J3` ⇄ `H4` is the registry's only reciprocal cross-section pair.** S16 wrote `H4.unlocks → J3` from H's side (`H:139`); S17 wrote `J3.companion_checks → H4` from J's. Neither stage saw the other's file, and they agree.

**The reciprocal `B1 → J3` and `C1 → J2`/`J5` edges are not written.** Adding them means editing S13's and S14's files to document an ordering that changes no plan, since `unlocks` is read by nothing (S16 finding F8). Proposed, not made.

### The funnel as the ordering authority

`J:9-21` is explicit and directional — 15 candidates → ~9 viable → ~4 finalists → the frontier — so `J1 → J2 → J3`. `J2 → J3` is verbatim at `J:81`: *"if the paired CI includes 0, the models are tied, and you choose on cost and latency (J3)."*

`J4` and `J5` sit outside the chain and unlock nothing: `J:230` says a matched comparison is *"still just a shortlist signal"*.

### Figures: recorded, or left null

| recorded | source |
|---|---|
| `J1 {smoke_items: 50}` | `J:33`, `J:44`, `J:45` — stated three times. **Overturns S12's call** that the 50 was only part of the name: there is no smoke test until 50 items exist, and the planner should say so rather than fire on three |
| `J2 {human_pairwise_judgments: 100}` | `J:80` "Run 100 human pairwise judgments" |
| `J3 {paired_ci_available: true}` | `J:111` — a **boolean**, and S12's open question answered: the technique *is* "inside the best model's CI", so without the interval there is nothing to be inside |

| left null, as ranges | source |
|---|---|
| J2's 300–500 items | `J:68`, `J:71` |
| J5's 100–200 held-out items | `J:177`, `J:186` — **the row's own readiness condition**, and the range policy still wins. A reviewer wanting a floor here has to rule on 100 |
| J1's 3–5 finalists | `J:46` |

Bars on produced numbers, verbatim in `rule_of_thumb` because no field holds them (S13 finding **F2**): J1's "below 50% accuracy" elimination bar (`J:45`), J1's ±14-point margin (`J:28`), J2's "about 3 points at n = 400" resolution (`J:74`), J4's "5–10 points" setup swing (`J:149`), J3's "cheapest inside the best model's CI" (`J:27`).

---

## 4. The `PLAN.md` §5 sanity queries, by hand — **two of six come out wrong**

Steps 1–6 of `AGENT.md` §3.5 applied to the records as now authored. Verdicts are against what `PLAN.md` §5 says the answer should be.

### ❌ Q1 `summarization` → "faithfulness, with the length check attached"

Granted `llm_api_cross_family`, `llm_api`, `source_doc_read`; no runs.

| bucket | records |
|---|---|
| READY | **(nothing)** |
| PENDING | `A4_judge_binary_criteria` — *needs judge_human_kappa_to_trust: 0.6, have 0; judge_human_kappa_to_gate: 0.8, have 0* |

**Only one record matches `summarization` at all, and it is not ready.** Two separate problems:

1. **Faithfulness is unreachable.** `G3_faithfulness` triggers on `rag_answer` only. The corpus scopes claim-decomposition faithfulness to section G, where it is entailment against *retrieved context*; summarization faithfulness — entailment against the *source document* — is the same technique on a different artifact, and **no row of the master lookup covers it**. Even if `G3` were given the `summarization` trigger, S16's `recall_at_k_measured` gate would make it pending for a reason that is meaningless without a retriever — S13 finding **F4** again (`requires` has no situation scope), biting in a second place.

2. **The length check cannot attach, because its host is not ready.** `A4 → E3` is encoded correctly (S15) and `AGENT.md` §5's rule is in the registry. But step 6 forces companions only for records that are *ready*, and A4 is pending on κ. So on a fresh repo a summarization plan contains **no ready record and no length check**.

That second point is the one that matters beyond this query:

> **Putting the κ trust bars in `requires` makes every judge-based record unready on a fresh repo.** S13 raised finding **F2** — no field for a trust bar on a produced metric — and the bars went into `requires` because it was the only field that could hold a number. The consequence, visible for the first time here: `requires` is the *readiness* gate, so a trust bar placed there reads as "not enough data yet" and suppresses the record entirely, along with every companion it would have pulled in. It is strictly correct methodology (`F:21`, κ ≥ 0.6 before you use a grader) and it is the wrong *bucket* — the plan should offer the judge with its calibration as the next action, not silently hold it back.
>
> **F2 is therefore not cosmetic. It changes what the product shows on day one for every judge-graded artifact**, which is most of them.

### ⚠ Q2 `code generation` → "execution first, judging deprioritised or excluded" — satisfied, but vacuously

| grant | plan |
|---|---|
| `sandbox` + `test_runner` | READY: `A1_execution_based` (rung 1), then its companion `C1_wilson_ci` |
| `test_runner` only | READY: **(nothing)**. UNAVAILABLE: `A1` ← `sandbox` |

"Execution first" ✅ — A1 is rung 1 and carries `conflicts_with: [A4_judge_binary_criteria]`. But **A4 never matches `code_generation`**, so the conflict edge never fires: judging is excluded by not being selected, not by being suppressed. The stated behaviour is delivered; the mechanism the query is testing is not exercised.

And **fixture 2's question — "no sandbox → what remains?" — has the answer "nothing".** Exactly one record triggers on `code_generation`. That is defensible (without execution you cannot grade generated code honestly) but S18 should write it knowing the expected plan is empty, not go looking for the records it is missing.

### ✅ Q3 RAG → "retrieval recall ordered before faithfulness" — satisfied

Traced in full in `S16-REPORT.md` §3. `G3.requires` is `{recall_at_k_measured: true, claim_labels: 150}`.

### ⚠ Q4 `rare class` → "recall ready, accuracy prohibited" — half satisfied

| bucket | records |
|---|---|
| PROHIBITED | `D1_pr_curve_never_accuracy` ✅ |
| PENDING | `D1_pr_curve_never_accuracy` — *needs positives: 100, have 0* |

1. **"accuracy prohibited" is structurally right and cannot be rendered.** D1 is in `prohibited`; the planner cannot say the word *accuracy*, because no field names what a constraint forbids — S14 finding **F5**, still open and still blocking.
2. **"recall ready" is false.** D1 is the only record matching `rare_class`, and it is pending on `{positives: 100}` (`D:34`, a hard bound). Recall becomes available at 100 positives, not at n=1. The records are right and the query's expectation is loose — but it should be written down, because a reviewer reading `PLAN.md` §5 will expect a ready record.
3. **D1 appears in two buckets at once** — `prohibited` *and* `pending` — because step 2 (constraints) runs before step 4 (readiness). The `Plan` dataclass permits it. **Nobody has ruled on whether that is intended**, and it is the shape every "never X, measure Y instead" record will have. For `EL-122`.

### ⚠ Q5 "what works on a single observation?" → "only facts" — **not satisfied**

**31 of 73 records have empty `requires` and therefore fire at n = 1:** 4 graders, 16… by type, 4 graders / 6 metrics / 7 statistics / 3 diagnostics / 11 procedures.

Graders, metrics and procedures firing on one observation are fine — a single execution result is a fact. **The seven statistics are not all fine:**

| record | at n = 1 |
|---|---|
| `C1_wilson_ci` | fine — Wilson is *chosen* because it behaves at small n; the interval is wide and honest |
| `C4_near_bounds_interval` | fine — it exists for the small-n, near-boundary case |
| `C2_power_analysis` | fine — it computes the required n, it does not consume n |
| `C5_multiple_comparisons` | fine — it corrects an α, given a count of comparisons |
| `B6_bootstrap_ci` | borderline — a bootstrap over one item resamples one item |
| **`B1_paired_evaluation`** | **wrong** — a "paired difference" over a single pair |
| **`C6_permutation_test`** | **wrong** — a permutation test on one observation has one permutation |

**And the reason is finding F8.** `B5_ci_from_n` carries `{sample_size_stated: true}` and **unlocks `B1`** — the ordering exists, in `unlocks`, which `AGENT.md` §3.5 never reads. So the registry *knows* B1 should follow B5 and the planner will fire B1 at n = 1 anyway.

> This is the clearest demonstration that **F8 is a defect and not a documentation nit**: a sanity query in `PLAN.md` §5 comes out wrong, today, because an ordering was recorded in the one field nothing reads.

### ❌ Q6 "what needs 200+ samples?" → "significance tests, judge agreement" — **not what the records say**

Querying `requires` for a threshold ≥ 200 returns **two records, neither of which is a significance test or a judge-agreement check**:

| record | threshold |
|---|---|
| `A6_expert_human_review` | `items: 200` |
| `A7_tiered_online_scoring` | `judge_labelled_items: 5000` |

Where those requirements actually live:

| what `PLAN.md` expects | what the registry holds | why |
|---|---|---|
| significance tests | `B3_mcnemar {discordant_pairs: 25}` · `C2_power_analysis {}` · `C6_permutation_test {}` | the corpus states significance as a **formula** — `n ≈ 16·p(1−p)/δ²`, which at p = 0.5, δ = 0.05 gives 400 — and a formula lives in `rule_of_thumb`, not `requires` |
| judge agreement | `F1 {fail_cases: 50}` · `F2 {κ bars}` · `J2 {human_pairwise_judgments: 100}` | F1's gold-label count is **150–200**, a *range*, which the standing policy leaves null |

**Q6 cannot be answered by querying `requires` at all**, and that is the direct consequence of two earlier policy decisions — ranges left null (S10's rule) and formulas kept in `rule_of_thumb` (S14's). Both are right individually. Together they mean the registry cannot answer "what needs 200 samples?", which `PLAN.md` §5 lists as a definition-of-done query.

**Nothing was changed to make this query pass.** The options are: resolve finding F3 so `requires` can hold a range (then F1 gets 150), or accept that this query is answered by reading `rule_of_thumb` and reword `PLAN.md` §5. That is a ruling, not a stage.

### Summary of the six

| | query | verdict |
|---|---|---|
| Q1 | summarization → faithfulness + length | ❌ **neither half ready**; faithfulness unreachable, length check blocked behind an unready host |
| Q2 | code gen → execution first | ✅ satisfied, mechanism untested; no-sandbox plan is empty |
| Q3 | RAG → recall before faithfulness | ✅ satisfied |
| Q4 | rare class → recall ready, accuracy prohibited | ⚠ prohibition structural-only (F5); recall pending on 100 positives; D1 in two buckets |
| Q5 | single observation → only facts | ❌ B1 and C6 fire at n = 1, because of F8 |
| Q6 | 200+ samples → significance, judge agreement | ❌ not answerable from `requires` |

**Three of six come out as `PLAN.md` says. The gate in `PLAN.md` §5 is not met, and `PLAN.md` §5 is not edited here** — it is the definition of done, and moving it is the user's call. The four problems are the deliverable.

---

## 5. The one judgement this stage overturned

**`I6_business_metric_guardrails`: `gates` `false` → `absolute`.**

S12 read the master-lookup row as stating no gate. The deep dive states one twice:

* `I:207` — "**Define the guardrails** with thresholds (\"CSAT must not fall by more than 0.1\")."
* `I:221` — a guardrail breach rolled a release back within a week, and "Chargeback rate **is now a hard guardrail** with a ₹ cost attached."

A metric whose purpose is "must not get worse, or revert" blocks on any failure, which is what `absolute` means in `CLAUDE.md` §6. The *threshold* is per-deployment and is **not invented**: "CSAT must not fall by more than 0.1" is carried as the source's own example in a `required_signal`.

Flagged rather than buried, because it changes whether a guardrail can block a ship. The three remaining `false` rows in I — I3, I5, I8 — were re-checked against the deep dive and the source genuinely states no gate for any of them.

---

## 6. Schema findings

### F12 — `gates` holds one value and `I2` needs two ← *new*

Covered in §2. **Proposal:** `gates: Gate | tuple[Gate, ...]`, or a layer-scoped second field. Not implemented.

### F13 — the corpus's flywheel is a cycle; `unlocks` is a DAG ← *new*

Covered in §2. No proposal beyond a ruling: is a cycle in `unlocks` a defect, or a legitimate description of a loop? `check_integrity()` does not check either way.

### F2 — no field for a trust bar on a produced metric ← *S13, and now shown to change behaviour*

§4's Q1. The κ bars in `A4.requires` make every judge-graded artifact's plan empty on a fresh repo, and suppress the length-bias companion with it. **Severity raised from "cosmetic" to "changes the product's day-one output".** New instances this stage: five bars in J (§3) and I2's 5% false-fail ceiling.

### F8 — `unlocks` is read by nothing ← *S16, and now shown to break a sanity query*

§4's Q5. `B5 → B1` exists and does nothing, so a paired evaluation fires on a single pair. **The `gated_by` proposal in `S16-REPORT.md` §7 is the fix, and this is the evidence for it.**

### F5, F4, F3, F9 — unchanged, with new instances

* **F5** (a constraint cannot name what it forbids) — §4's Q4. Still blocking the one query it touches.
* **F4** (`requires`/`conflicts_with` have no situation scope) — §4's Q1, where a `summarization` trigger on G3 would import a recall gate that means nothing.
* **F3** (`requires` cannot hold a range or an upper bound) — three new range instances in J, one upper bound in I2 (`I:77`, "Above 5%, widen the tolerance").
* **F9** (two numbers from one record cannot be marked never-alone) — **fourth instance**: `I6`'s primary KPI and its guardrails, joining D6, G6 and H6.

### Two cross-cutting principles with no record at all

`00-INDEX.md:34-38` lists five principles that "appear in every single section". Three have a record: #1 execution → `A1`, #2 confidence interval → `C1`, #3 pairing → `B1`, #5 flywheel → `I8` and `I3`.

**#4, "Slice the results. The average always hides the one language, intent or field you actually need to know about", has no record.** Slicing appears *inside* records — `D5` per category, `G5` by query type, `I8` stratified by intent, `J2` by language, `J5`'s "worst slice decides" — and nothing codifies it. `J:120` ("Check the critical slices separately") has nothing to point at, which is why `J3`'s companion list does not include it.

That is the **second** uncodified cross-cutting rule found by these stages; S16 found the first (reward-hacking detection, named in `AGENT.md` §3.8 and `ARCHITECTURE.md` §10 with no record anywhere). Both are corpus gaps, not authoring omissions, and both want a decision before M3 builds the honesty layer on top of a registry that cannot express them.

---

## 7. The source_ref sweep, kept as a test (ticket item 2)

`tests/test_records.py::test_every_source_ref_resolves_in_the_corpus`.

For each of the 73 records it splits `source_ref` on `" § "`, opens the named file under `corpus_dir`, and requires a heading matching `^#+\s*<subsection>\b` inside it. Problems are aggregated across all 73 and reported together, the same reason the loader aggregates.

**What it catches that nothing else does:** a renamed or deleted deep-dive heading; a record citing `§ I10` when the file stops at I9; a section file disappearing while records keep pointing into it. All three leave the registry loading cleanly and every other test green.

**It was mutation-tested, not just written.** Two independent faults were injected — `§ I3` → `§ I13` and `I-production.md` → `I-produciton.md` — and the test failed naming both, with the fix in each message. Reverted; the suite is green.

The existing `test_every_record_cites_its_source` checks the *shape* of the citation; this one checks that it is *true*. Both are kept. `ENRICHED_SECTIONS` is now `"ABCDEFGHIJ"`, which makes that test's master-lookup branch unreachable — kept deliberately, since it is what would catch a record regressing to a section-level citation, and the assertion after it derives the set from the records so neither half can go stale.

---

## 8. Smaller things, recorded so they are not silent

* **An evaluation harness has no `Tool` member.** `J:154` says "Rerun on one harness (an open-source evaluation harness, or your own)". `test_runner` is the nearest member and was **not** used: by decision `EL-002`'s own test, a benchmark harness is a different capability from a unit-test runner, and stretching the member would make `J4` look satisfiable by a pytest install. `J4` carries `source_doc_read` + `llm_api` instead, and the gap is raised rather than papered over.
* **`I8`'s "hold out 20%"** (`I:275`) is a single figure but a *fraction of a set*, not a count of evidence. A `requires` key reading `{held_out_fraction: 20}` would be a percentage in a field every other record fills with counts, so it is carried verbatim in `rule_of_thumb` and as a `required_signal`. The nearest thing to an interpreted threshold in this stage.
* **`I3`'s `{failures: 100}` comes from a hedged statement** — "about 100 real failures" (`I:100`). It is the one number in I recorded from a hedge, and the ticket asked for it verbatim. If a reviewer reads "about 100" as approximate rather than as a floor, this is the entry to clear.
* **`J2`'s `E3` citation is a rationale, not an edge.** `J:74` cites E3 as the *reason* the human pairwise check exists ("the automated grader prefers something users don't, such as verbosity"). A rationale is not a thing to report alongside, so E3 is not a companion on J2 — unlike `A4`, `B2` and `F4`, where the source prescribes reporting length with the score.
* **`I5` points at `A7`** (`I:168`, "Section A7 covers the tiered architecture") and no edge is written: a pointer to an architecture is not a statement that both must be reported. The two remain unmerged, as S12 decided.
* **13 records have no edges of any kind**: B4, B6, C1, C2, C4, C5, C6, D4, E3, E6, E7, H7, J4. Most are leaf statistics that other records point *at* — C1 alone is named by 20 companions. Listed so that "no edges" is visibly a conclusion rather than an omission.

---

## 9. Carry forward

### For `EL-118`/`EL-119` (the 20 fixtures) — three concrete corrections

**`TASKS.md`'s "Fixture format" example cannot be satisfied by the registry**, and S18 will copy it. It has four faults, two of them outright errors:

| in the example | problem |
|---|---|
| `ready: [G3_faithfulness, ...]` for `situations: [summarization]` | `G3` triggers on `rag_answer` only — it is never matched, let alone ready (§4 Q1) |
| `E3_length_bias` | **not a record id**; it is `E3_length_controlled_win_rate` |
| `B3_mcnemar: "needs paired_runs: 2, have 1"` | `B3` does not trigger on `summarization` either, and its key is `discordant_pairs: 25`, not `paired_runs: 2` |
| the whole `expect` block | the real plan for `summarization` on a fresh repo is: `ready: []`, `pending: {A4_judge_binary_criteria: "needs judge_human_kappa_to_trust: 0.6, have 0; ..."}` |

**The two id/key errors are fixed in `TASKS.md` by this stage**, because they are unambiguous and S18 would propagate them. **The `ready` list is annotated, not rewritten** — changing it is the Q1 ruling, which is §4's to raise and not S17's to decide.

Also carried: fixture 4 needs `llm_api` granted (S16), fixture 5 asserts on `unavailable` not `pending` (S16), and **fixture 2's expected plan is empty** (§4 Q2).

### For `EL-121`/`EL-122` (readiness, capability, planner)

1. **17 records carry a boolean requirement.** The reason string cannot be a failed comparison; the keys are written as readable predicates (`pre_registration_filed`, `paired_ci_available`, `environment_resets_per_run`, `recall_at_k_measured`) so a boolean renders as a sentence.
2. **`D1` lands in `prohibited` and `pending` simultaneously** (§4 Q4). Rule on it.
3. **Companion resolution must be a fixed point**, not recursion — `H2` ⇄ `H4` (S16 finding F11).
4. **Step 6 only forces companions of *ready* records.** §4's Q1 shows the cost: a mandated companion silently disappears when its host is pending. `check_integrity()`'s docstring already lists "a companion that can never be ready" among the unguarded defects; this is the live case.

### Rulings this stage is waiting on

| # | ruling | consequence if unresolved |
|---|---|---|
| 1 | **F2** — trust bars vs readiness bars | every judge-graded artifact has an empty plan on day one |
| 2 | **F8** — `gated_by`, or `unlocks` read by the planner | B1 fires on one pair; D's and F's orderings gate nothing |
| 3 | **F12** — `gates` holding two values | a schema failure does not read as an absolute block |
| 4 | **F13** — is a cycle in `unlocks` a defect? | the flywheel is stored incomplete |
| 5 | `PLAN.md` §5 Q1 and Q6 — reword, or change the records | the M0 gate cannot be met as written |
| 6 | **F5** (S14), **F4** (S13), **F3** (S13), **F9** (S16) | carried unchanged, with new instances in §6 |
| 7 | `I3`'s "about 100", `J5`'s unrecorded 100–200 floor | §8 |
| 8 | Two uncodified cross-cutting principles: slicing, reward-hacking | §6 |

**The registry is finished. Six of the eight rulings above are schema or doc decisions, not work.**
