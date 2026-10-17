# S16 / EL-116 — Enrich G + H from the deep dives

**Status:** complete. 418 passed · `check_integrity()` returns `[]` · `mypy --strict` clean · 73 records · `unlocks` verified acyclic across the whole registry.

**Read:** `knowledge rules/G-rag-systems.md`, `knowledge rules/H-agents.md`, `AGENT.md` §3.5 + §5, `ARCHITECTURE.md` §6.4 + §6.5 (as an intent check only, per the ticket — no number was taken from them), `CLAUDE.md` §4 + §6, `TASKS.md` S16 and Group 6 fixtures 4 and 5.

**Citations** are `G:<line>` and `H:<line>` against the two deep dives. Every citation written into either record file was re-resolved against the file afterwards by script; four were wrong on the first pass and are fixed (`G:66`→`G:65`, `G:128`→`G:130`, `G:171`/`G:182`→`G:151`/`G:181`, `G:296`→`G:295`).

---

## 1. What changed

| | G | H |
|---|---|---|
| `source_ref` | → `G-rag-systems.md § G1` … `§ G8` | → `H-agents.md § H1` … `§ H8` |
| `requires` | 5 of 8 gated (§2) | **7 of 8 gated** (§3) |
| `unlocks` | G1 → 5 records | H1 → all 7, H2 → 3, H4 → J3, H5 → H7 |
| `companion_checks` | **10 edges**, 9 of them cross-section | **9 edges**, 4 of them cross-section |
| `required_tools` | G6 `source_doc_read`, G8 `+source_doc_read` | H5 `+db_connection` |
| `produces` | G6 gains `over_abstention_rate`, G8 gains `answers_with_a_bad_citation_rate` | H1 gains `scaffold_version`, H4 gains `full_cost_per_resolution` |
| `rule_of_thumb` | all 8 extended with the corpus's verbatim rules | all 8 |
| `required_signals` | all 8 sharpened from each record's "How to do it properly" | all 8 |

`anti_pattern`, `worked_example` and `domain_scenario` were **not touched**. Both files were patched key-by-key rather than rewritten, and `test_verbatim_fields_match_the_lookup_row` still passes. `tests/test_records.py`'s `ENRICHED_SECTIONS` is now `"ABCDEFGH"`.

**This stage added 17 `unlocks` edges, 19 `companion_checks` edges (G and H had none) and 15 boolean requirement entries across 12 records — nearly as many `unlocks` edges as the other eight sections hold between them (19), and five times their boolean gates (3). `check_integrity()` is still empty.**

---

## 2. The edges, and how a build order is actually made machine-readable

### The thing worth knowing before the traces

**Nothing in `AGENT.md` §3.5's resolution order reads `unlocks`.** Steps 1–7 read `triggers_on_situation`, the `constraint` records, `required_tools`, `requires`, `conflicts_with`, `companion_checks`, then `type`/`ladder_priority`/`id`. `unlocks` is read by no step.

So a build order recorded only in `unlocks` changes nothing about a plan. "recall@k before faithfulness" becomes real only when the downstream record carries something the **readiness** check can fail on. Every edge in both files is therefore written twice:

| direction | field | who reads it |
|---|---|---|
| upstream | `unlocks` | a human, and `plan/rules.py` later |
| downstream | `requires` | step 4, which is what produces `pending` |

and the boolean is named for the **world fact** that must hold, not for the record that establishes it:

* `recall_at_k_measured: true` — which is `G1.produces[0]`, so the gate is traceable to its producer by name.
* `environment_resets_per_run: true` — which is `H:291`'s own gate question, "Is the environment sandboxed and reset per run?"

This is deliberately *not* how D and F encode their orderings — `D1` unlocks `D2` and `D2.requires` is empty, so `D2` is ready at n=1 — and the difference is now documented in both file headers. It is also finding **F8** below: nothing checks that the two directions agree.

### G: four branches, not one chain

The authority is G's own decision flow (`G:287-306`), its thesis (`G:6`) and `AGENT.md` §5's non-negotiable. The flow has **four top-level branches**:

```
G:290   gold passage labels           "Nothing below works without them"
G:292   split the score         (G1)  → G2, G3, G4, G5, G7 hang beneath it
G:301   unanswerables           (G6)  a branch of its own
G:304   citations shown to users (G8)  a branch of its own
```

So `G1` unlocks five records and gates all five; **G6 and G8 carry no gate**. Reading the flow as one chain would have made them pending for a reason the corpus never states — and `ARCHITECTURE.md` §6.4's RAG recipe, which numbers its five items as if they were a chain, is the version that would have led there. §6.4 is intent, not source; the records follow `G:287-306`.

| record | gated on | authority |
|---|---|---|
| G2 | `recall_at_k_measured` | `G:65` — "G1 gives you two averages. Attribution tells you what share of the actual failures each stage causes" |
| G3 | `recall_at_k_measured`, `claim_labels: 150` | `G:292`, `G:298`, `AGENT.md` §5; `G:102` for the labels |
| G4 | `recall_at_k_measured` | the flow only (`G:292-295`) — **the weakest of the five**, see §8 |
| G5 | `recall_at_k_measured` | the flow only (`G:292-295`) — same |
| G7 | `recall_at_k_measured` | `G:230`, which injects distractors "into gold context", and gold context is G1's own apparatus |

### H: the stack is the authority, the flow is the gate

`H:9-17`'s **AGENT EVAL STACK** is the `unlocks` authority, as D's pipeline box was for D and F's calibration stack for F. `H:291-292` — "Is the environment sandboxed and reset per run? (H1) / NO → build it first" — is the only thing mirrored into `requires`, together with `AGENT.md` §5. All seven of H2–H8 carry `environment_resets_per_run: true`.

The asymmetry is deliberate and is stated in the file header: **the stack states an ordering; only `H:291` states a hard precondition.** So `H2` unlocks `H3`/`H4`/`H8` without gating them, exactly as `D1` unlocks `D2` without gating it.

---

## 3. Trace 1 — `rag_answer`, `vector_store` granted, no runs

Steps 1–6 of `AGENT.md` §3.5, by hand, against the records as now authored. Step 1 matches exactly G1–G8: no record outside G triggers on `rag_answer`. No G record is a `constraint`, so `prohibited` is empty in every variant.

### 1a — the ticket's literal grant: `{vector_store}` only

| bucket | records |
|---|---|
| **READY** | `G1_component_wise_eval` → then step 6 forces its companion `C1_wilson_ci` (no tools, no `requires`) |
| **PENDING** | `G2`, `G5`, `G7` — each *"needs recall_at_k_measured: True, have False"* |
| **UNAVAILABLE** | `G3` ← `llm_api` · `G4` ← `human_labels` · `G6` ← `source_doc_read` · `G8` ← `llm_api`, `source_doc_read` |

**G1 is READY. ✅ But faithfulness is UNAVAILABLE, not PENDING** — and that is correct behaviour, not a wrong edge. Step 3 (capability) runs before step 4 (readiness), so a record missing a tool never reaches the readiness check and never shows its reason. G3 needs `llm_api` for the NLI/entailment call and nothing granted it.

> **⚠ For `EL-118`, fixture 4:** the acceptance criterion says "vector_store granted … faithfulness PENDING". Those two cannot both be true. **Fixture 4 must grant `llm_api` as well as `vector_store`**, or it will assert `pending` on a record the planner correctly puts in `unavailable`. This is an under-specified ticket, not a wrong record — the edge is verified in 1b below.

### 1b — `{vector_store, llm_api}`: the edge under test

| bucket | records |
|---|---|
| **READY** | `G1_component_wise_eval`, `C1_wilson_ci` (forced companion) |
| **PENDING** | `G2` *"needs recall_at_k_measured: True, have False"*<br>**`G3_faithfulness` *"needs recall_at_k_measured: True, have False; claim_labels: 150, have 0"*** ✅<br>`G5`, `G7` — same recall gate |
| **UNAVAILABLE** | `G4` ← `human_labels` · `G6`, `G8` ← `source_doc_read` |

**Faithfulness is PENDING, on recall@k. The edge points the right way.**

### 1c — `ARCHITECTURE.md` §6.5's actual RAG grant: `{vector_store, llm_api, source_doc_read}`

| bucket | records |
|---|---|
| **READY** | `G1`, `G6`, `G8` (metrics, id order), then `C1_wilson_ci` (statistic) |
| **PENDING** | `G2`, `G3`, `G5`, `G7` |
| **UNAVAILABLE** | `G4` ← `human_labels` |

This is the plan the product actually shows on a fresh RAG repo, and it reads exactly as §6.5's right-hand column promises: *"faithfulness **blocked** until recall@k is measured"*. G6 and G8 being ready alongside G1 is the four-branch flow doing its job — the unanswerable set and the citation check do not wait on retrieval.

### 1d — the same grant, one evidence key later (`recall_at_k_measured: true`)

| bucket | records |
|---|---|
| **READY** | `G1`, `G5`, `G6`, `G7`, `G8`, `C1_wilson_ci`, `G2` (diagnostic, so last by type) |
| **PENDING** | `G3_faithfulness` *"needs claim_labels: 150, have 0"* |
| **UNAVAILABLE** | `G4` ← `human_labels` |

The gate opens for four records at once, and G3 stays pending on its *other* requirement — the judge-validation bar. That is the behaviour the second number was recorded for.

---

## 4. Trace 2 — `agent_action`, no `snapshot_restore` or `trace_capture`

Step 1 matches **nine** records: H1–H8 **and `A2_end_state_verification`**, which also triggers on `agent_action`. None is a `constraint`.

### 2a — nothing granted

Everything is UNAVAILABLE. `ready` and `pending` are both empty, and the plan is nine permission requests:

| record | missing |
|---|---|
| `A2_end_state_verification` | `db_connection`, `snapshot_restore` |
| `H1_resettable_env` | `sandbox`, `snapshot_restore`, `trace_capture` |
| `H2` | `db_connection` |
| `H3`, `H8` | `sandbox`, `snapshot_restore` |
| `H5` | `trace_capture`, `db_connection` |
| `H6` | `sandbox`, `trace_capture` |
| `H7` | `trace_capture` |

### 2b — the informative variant: `{sandbox, db_connection, cost_api}`, still no `snapshot_restore`/`trace_capture`

| bucket | records |
|---|---|
| **READY** | *(nothing)* |
| **PENDING** | `H2` and `H4` — each *"needs environment_resets_per_run: True, have False"* |
| **UNAVAILABLE** | `A2` ← `snapshot_restore` · `H1` ← `snapshot_restore`, `trace_capture` · `H3`, `H8` ← `snapshot_restore` · `H5`, `H6`, `H7` ← `trace_capture` |

**The whole trajectory family — H5, H6, H7 — is UNAVAILABLE and names `trace_capture` as the reason.** That is fixture 5's requirement ("trajectory family unavailable, and it says so") met through `required_tools`, before the booleans are ever consulted.

### 2c — the decisive variant: **every** tool granted, no runs

This is the one that proves the precondition, because here no capability gap can be doing the work:

| bucket | records |
|---|---|
| **READY** | `A2_end_state_verification` (+ its companion `C1_wilson_ci`), `H1_resettable_env` (+ its companion `E6_oracle_run`) |
| **PENDING** | `H2` *needs `environment_resets_per_run`*<br>`H3` *needs `environment_resets_per_run`; `trials: 5`, have 0*<br>`H4` *needs `environment_resets_per_run`*<br>`H5`, `H6`, `H7` *need `environment_resets_per_run`; `requires_pre_instrumentation`*<br>`H8` *needs `environment_resets_per_run`; `trials: 5`, have 0* |
| **UNAVAILABLE** | *(nothing)* |

**Nothing in H is READY without H1. ✅** H1 itself is ready and is the only agent-eval work the plan offers, which is `H:292` — "build it first" — rendered as a plan.

### ⚠ The leak this trace found: `A2` is ready, and it is an agent eval

`A2_end_state_verification` triggers on `agent_action`, lives in section A, and `requires` is `{}`. In 2c it is **READY while H1 has not run**. So `AGENT.md` §5's "Resettable environment before any agent eval" holds across section H and **not** across the whole agent plan.

It is not wide open — A2 already requires the `snapshot_restore` *tool*, which is the closest thing section A has to the gate — but a granted tool is not a performed reset, and that is exactly the distinction H1 exists to draw.

**Not fixed here.** Section A is S13's, `CLAUDE.md` §7.1 says one stage at a time, and §7.5 says raise schema and scope problems rather than work around them. The one-line edit, for whoever rules on it:

```yaml
# evalloop/registry/records/A_grading.yaml, A2_end_state_verification
  requires: {environment_resets_per_run: true}   # H:291, and only when the situation is agent_action
```

with the caveat that it would also fire for A2's non-agent situations (`api_endpoint`, `data_pipeline`), which is S13's finding **F4** again — `requires` has no situation scope, just as `conflicts_with` has no artifact scope. A faithful fix needs F4 resolved first.

---

## 5. The two kinds of requirement (ticket item 4)

`requires_pre_instrumentation: true` is present as a **boolean**, on three records:

| record | `requires` | kinds |
|---|---|---|
| `H2_outcome_based_success` | `{environment_resets_per_run: true}` | boolean |
| `H3_pass_hat_k` | `{environment_resets_per_run: true, trials: 5}` | **both** |
| `H4_cost_per_success` | `{environment_resets_per_run: true}` | boolean |
| `H5_milestone_localisation` | `{environment_resets_per_run: true, requires_pre_instrumentation: true}` | boolean ×2 |
| `H6_injection_asr` | `{environment_resets_per_run: true, requires_pre_instrumentation: true}` | boolean ×2 |
| `H7_trajectory_taxonomy` | `{environment_resets_per_run: true, requires_pre_instrumentation: true}` | boolean ×2 |
| `H8_flaky_classification` | `{environment_resets_per_run: true, trials: 5}` | **both** |

**H3 and H8 carry one of each, so neither kind can be the one `EL-121` handles.** The registry-wide count is now 15 records with a boolean requirement, up from 3 (`B5`, `B7`, `E2`); within G and H it is 15 boolean entries across 12 records, since six of them carry two.

**Where the boolean goes, and why.** `requires_pre_instrumentation` sits on exactly the records whose `required_tools` include `trace_capture`, because that is what it means: the trace cannot be reconstructed after the runs, so the logging had to be on before them. The correspondence is deliberate and is stated in the H header, so a later stage adding `trace_capture` to a record knows to add the boolean too.

**H1 is the stated exception** — it *is* the instrumentation. See finding F7.

**H8 deliberately does not get it.** `H:266`'s "compare passing and failing traces" is a follow-up that reaches into H5/H7's data; the three buckets themselves need pass counts only. Requiring the tool and the boolean there would make the classification unavailable for a step that is not part of it.

> **For `EL-121`:** the reason string for a boolean cannot be `"needs requires_pre_instrumentation: True, have 0"`. The keys are written as readable predicates on purpose, so a boolean reason can render as *"the environment does not reset per run"* / *"trajectory logging was not on before these runs"* rather than as a failed comparison. The gotcha in the `EL-121` ticket is real, and the key names are the half of it this stage could fix.

---

## 6. Numbers

### Recorded verbatim

| record | `requires` | source |
|---|---|---|
| `G3_faithfulness` | `claim_labels: 150` | `G:102` "Validate the entailment judge against **150+** human claim labels (Section F)" |
| `H3_pass_hat_k` | `trials: 5` | `H:102` "Run each task **k ≥ 5** times in the reset environment" — S12 had left this empty |
| `H8_flaky_classification` | `trials: 5` | `H:264` "Run **k ≥ 5** trials per task in the reset environment (H1)" — unchanged, and now joined by the boolean from the same line |

**Both k values are copied verbatim and they are the same k.** `H:13` states it once for both records ("pass^k over k ≥ 5"), and the worked examples' 5 and 8 are scenario figures, not the bound.

**`G3.claim_labels: 150` is G's figure, not F's.** `F:27`/`F:30` say *150–200*, a range, which S15 correctly left out of `F1.requires`. `G:102`'s *"150+"* is a single lower bound and is therefore recorded — on the consumer record, exactly as `A4` carries its own κ bars rather than leaving them to `F2`. This is the fourth time an apparent "same number, two places" has turned out to be two different statements; the three earlier ones are in S14 §2 and S15 §2.

### Recorded verbatim in `rule_of_thumb`, because no field can hold them

Every one is a bar or a formula on a **produced** number, which is S13's finding **F2**, still unresolved:

| record | text | source |
|---|---|---|
| `G1` | "end-to-end accuracy ≈ retrieval recall@k × generator accuracy given gold context" | `G:20` |
| `G3` | "faithfulness = entailed claims / total claims" | `G:93` |
| `G4` | "gains discounted by log₂(rank + 1)" | `G:130` |
| `G5` | "Hit@k = the share of queries where it appears in the top k; report Hit@1, Hit@3 and MRR together" | `G:158`, `G:165` |
| `G6` | "set a bar for each, **for example** false answers ≤ 5% and over-abstention ≤ 8%" | `G:196` |
| `G7` | "**a drop of more than 5 points** means the generator can't handle noise" | `G:230` |
| `H1` | "the same model in two scaffolds commonly differs by 15–20 points" | `H:23` |
| `H3` | "pass@5 = 1 − 0.2⁵ = 99.97%, and pass^5 ≈ 0.8⁵ = 33%" | `H:22` |
| `H4` | "₹ per success = total ₹ / successes" | `H:137` |
| `H5` | "task success ≈ (per-step success)^steps, so 0.98⁴⁰ = 0.45 and 0.99⁴⁰ = 0.67" | `H:21` |

`G6`'s two bars are stated **"for example"**, so they are nowhere near `requires` or `gates`. A later stage must not promote them.

`H5`'s compounding rule and `H1`'s scaffold rule are **section-level** rules of thumb (`H:20-23`) with no record of their own. They are carried on the nearest record rather than dropped — `CLAUDE.md` §4 lists "step compounding" among H's contents and H5 is the only record it can mean. Flagged as a placement judgement, not a source claim.

### Left out as ranges, by the standing policy

`G:33` 200–300 questions · `G:68` 100–200 failures · `G:133-134` a 0–3 scale, top 10–20 results, 200–500 queries · `G:188` 15–25% unanswerables · `G:228` 150–200 queries · `G:230` 1–3 distractors · `H:198` 100–300 injected items · `H:232` 50–100 traces · `H5`'s 5–10 sub-goals.

**`H7`'s "50–100 traces" is genuine and stays** — S15 traced the *F1* "50–100 human labels" to `A:143` and `H:226`/`H:232` being quoted under F1's name, and the S16 hand-off said not to "fix" it. It was not touched.

### Interpreted, and flagged — one place only

**`G3`: `G:99`'s "Validate the decomposition on 50 answers first" is a single bound and is deliberately NOT in `requires`.** It validates the *decomposition prompt*, not the judge whose verdict enters the metric, and `requires` already carries the judge bar from `G:102`. It is recorded as a `required_signal` instead, verbatim in substance.

This is the one place this stage drew a line by hand, and it is the line between "a precondition on the instrument that produces the verdict" (→ `requires`, per `A4`'s precedent) and "a step of the procedure" (→ `required_signals`). `H:234`'s "re-read 20 traces" was placed on the same side, in `H7.required_signals`. **If the ruling goes the other way, both move, and `G3` gains a third pending reason.** No other threshold in either section was interpreted.

---

## 7. Schema findings

### F7 — nothing prevents a record from gating itself, and a gate-establishing record must be exempted by hand ← *new*

`G1` satisfies `recall_at_k_measured`. `H1` satisfies `environment_resets_per_run`. Both must therefore have **empty** `requires` for that key, and nothing enforces it:

* the schema validates fields in isolation, so `H1.requires = {environment_resets_per_run: true}` constructs cleanly;
* `check_integrity()`'s seven rules never look at `requires` at all;
* the result is not an error anywhere — it is a record that can never become ready, and in H's case **a whole section deadlocked behind it**, with eight pending entries and a plan that offers nothing.

The schema cannot distinguish "this record *establishes* the precondition" from "this record *consumes* it". With `produces` and `requires` both being free-text keys, it could: a record whose `requires` key corresponds to its own `produces` is always a defect.

**Proposal** — the cheapest useful version is an integrity rule, not a field:

> **Rule 8.** A record whose `requires` contains a key naming one of its own `produces` entries (or, for the booleans, a key derived from one) is reported. Alternatively, and more simply: for every boolean gate key, exactly one record may be its producer, and that record may not require it.

**Not implemented**, per `CLAUDE.md` §7.5 — it needs a convention for how a gate key relates to a `produces` name, and that convention is a decision, not a loop. Both file headers state the hand rule in the meantime.

### F8 — `unlocks` is read by nothing, so an edge written once is an edge that does nothing ← *new*

`AGENT.md` §3.5's seven steps never read `unlocks` (§2 above). The practical consequences:

1. **Build order encoded only in `unlocks` is invisible.** D's pipeline order (`D1` → `D2`, `D3`; `D2` → `D4`; `D5` → `D6`) and F's calibration stack currently change no plan: every one of those downstream records is ready at n=1. Whether that is right is a question for whoever owns D and F — it may well be, since neither section's corpus states a hard "do this first" the way `G:292` and `H:291` do — but it should be a decision rather than a side effect.
2. **The two directions can drift silently.** `G1.unlocks` names five records and five records carry `recall_at_k_measured`. Nothing checks that those sets agree. Delete one boolean and the plan quietly stops gating, with `unlocks` still claiming it does — the same class of silent failure `check_integrity()` exists to prevent for `companion_checks`.

**Proposal:** either **(a)** an integrity rule that every record named in `X.unlocks` carries a `requires` key that `X` produces — too strong, since the D/F edges are orderings rather than gates — or **(b)** split the field: `unlocks` for the advisory order, and a new `gated_by: tuple[str, ...]` naming the upstream record directly, which `check_integrity()` can resolve like any other id reference and which the planner can read at step 4 without a key-naming convention.

**(b) is the better shape** and it subsumes F7: a `gated_by` edge pointing at a record id cannot accidentally point at itself (rule 6 already catches self-reference), and the gate stops depending on two free-text strings matching. **Not implemented** — it is a 23rd field, same ruling class as F5's `prohibits` and F6's `first_action`.

### F9 — two numbers from **one** record cannot be marked as "never report one alone" ← *new, third instance*

`G6` must report the false-answer rate **and** the over-abstention rate (`G:195`: "Refusing everything scores 0% on the first and fails on the second"). The ticket's instruction was to encode that as `companion_checks` — and it cannot be:

* `companion_checks` holds **record ids**, and both numbers come from the single `G6` record;
* splitting `G6` into two records would break the one-row-one-record rule (`CLAUDE.md` §6, and `test_section_count_matches_the_lookup` would fail);
* so the pairing lives in `produces` as two strings, and `produces` carries no "report together" semantics.

**This is the third instance, and all three are `AGENT.md` §5 non-negotiables:**

| record | the pair | §5 rule |
|---|---|---|
| `D6_upper_bound_no_safe_headline` | violation rate + per-category counts | "Violation rate always reported with over-refusal rate" |
| `G6_unanswerable_set` | false-answer rate + over-abstention rate | the RAG form of the same |
| `H6_injection_asr` | ASR + task utility | "alongside", `H:200` |

A rule the registry states three times and can enforce zero times is the sharpest schema gap this stage found. **Proposal:** `produces` becomes a tuple of tuples, where an inner tuple of length > 1 means "these are reported together or not at all" — a shape change rather than a 23rd field, and the planner's render step is the only consumer. **Not implemented.**

### F10 — `conflicts_with` cannot express a conflict conditional on the data ← *S13 finding F4, in its worst form*

`G4` (nDCG) and `G5` (MRR/Hit@k) are **mutually exclusive by the data**: `G:164` "If there are several valid documents, use nDCG", and the two mirrored mistakes at `G:151` and `G:181`. S12 flagged a `conflicts_with` edge between them for this stage to decide. **The answer is no**, and the reason is worse than S13's:

S13's `A1` → `A4` edge "only fires when both situations are present", which at least makes it conditional on something the planner knows. **`G4` and `G5` both trigger on `rag_answer` and nothing else**, so the edge would fire on *every* RAG session and unconditionally suppress one of them — based on a data property ("exactly one document is correct per query") that lives in `required_signals` as free text and is not machine-readable at all.

Left empty, flagged on `G5`. Two more instances of the same shape, both also left empty:

* **`G2` → `G4`/`G5`** (`G:295`): the reranker branch is reached only when "ranked beyond k" is G2's **largest bucket**. A condition on a bucket of another record's output.
* **`G1`'s own branch** (`G:293`, `G:297`): *which* of G1's two numbers is lower decides whether the session goes to the retrieval records or the generation records. The single most useful routing decision in section G, and the registry gates all five identically because it cannot read it.

This is the honest limit of M0's registry: it can say *"not until recall@k is measured"*, and it cannot say *"and then go left or right depending on what recall@k said"*. Worth a decision before M1 builds on it.

### F11 — the registry's first mutual `companion_checks` pair ← *new, and correct*

`H2` names `H4` and `H4` names `H2`. Both directions are in the source: `H:73` "Track path efficiency separately (steps and ₹ per success) as a secondary metric", and `H:139` "Plot success rate against ₹ per success across candidates". The two numbers are reported together, so the cycle is the methodology, not a mistake — it was checked against every other pair in the registry and it is the only one.

**For `EL-122`'s step 6:** companion resolution must be a **fixed point**, not recursion — "add companions until the set stops growing" — or this pair hangs. `check_integrity()`'s docstring lists `unlocks` cycles among the things it deliberately does not check; companion cycles are not on that list, and after this stage one exists.

### Earlier findings, with this stage's new instances

* **F2** (no field for a bar on a produced metric) — **ten** new instances, §6. The two sharpest are `G7`'s "a drop of more than 5 points" and `G6`'s two launch bars, all three of which are exactly the "gate" a user would want and all three of which are prose.
* **F3** (`requires` cannot hold a range or an upper bound) — nine new range instances, §6. No new *upper*-bound case in G or H.
* **F4** (`conflicts_with` has no scope) — see F10, and the `A2` note in §4, where the same missing scope blocks the fix.
* **F5** (a `constraint` has no field naming what it forbids) — no new instance: neither G nor H has a `constraint` record. `H1` is the near miss, typed `procedure` with a `Why` cell that reads as a prohibition; the alternative reading stays in its `extraction_notes`.

---

## 8. Declined, and why — each flagged rather than written

| what | why declined |
|---|---|
| **`source_doc_read` on `G1`** | The ticket's section-wide pair is `vector_store` + `source_doc_read`, and `G1` carries only `vector_store`. Labelling gold passages is a *capture* act, recorded in `required_signals`; computing recall@k needs the retriever. Adding the tool would make `G1` **UNAVAILABLE in the very trace the same ticket requires to be READY** (§3, 1a). `source_doc_read` is carried by `G6` and `G8`, the two records that must open a document to run at all. |
| **`human_labels` on `G7`** | `G:228` labels chunk relevance for 150–200 queries, but the distractor half of `G7` needs no labels. Requiring the tool would take the whole record unavailable for a number that is half of it. |
| **`production_logs` on `G6`** | `G:194`'s first authoring route is "real out-of-corpus traffic"; the second, near-miss questions, needs only the corpus. The cheaper route governs the tool. |
| **`H6` → `D6` companion** | It would make §5's reporting rule hold for H6's ASR too, which is tempting. `H6` never cites section D, and S15's precedent for a doc-authority edge (`F4` → `E3`) had `AGENT.md` §5 naming it explicitly. This one is not named. |
| **`H7` → `I3` companion** | Same shape: `H7` is the agent form of `I3` error analysis and the corpus never cross-cites them. |
| **`G8` inheriting `G3`'s 150-label bar** | `G:259` says the citation check uses "the same NLI or judge setup as G3", which arguably carries the bar. That is an inference, not a statement. |
| **`pass_at_1` in `H3.produces`** | `H:104` does say "Use pass@1 (the mean) for internal iteration". Naming pass@1 beside pass^k in a field the planner renders is how the optimistic figure gets quoted by accident, which is the one thing `H3` exists to prevent. Cited in `extraction_notes` instead. |
| **`B1_paired_evaluation` on `G4`** | `G:135` says "paired bootstrap CI (Section B)". `B2` already names `B6` alone for the same phrase, so the precedent decides it. |
| **Gating `G4`/`G5` more weakly** | These two are the **weakest of the five G gates**: the authority is the section flow (`G:292-295`), not a sentence in either record. The argument for gating them is that `G4`'s whole case is read *against* recall@k — "Recall@k ignores order" (`G:130`), and its worked figure is recall flat at 0.83 while nDCG moves — and `G:164` defines `G5` relative to nDCG. **The alternative, if a reviewer disagrees:** drop `recall_at_k_measured` from `G4` and `G5` only, leaving `G2`, `G3` and `G7` gated. Nothing else in either file depends on it. |

### Two edges the ticket asked for that cannot be written

* **"H1/H7 unlock … reward-hacking detection"** — **there is no reward-hacking record in any of the 73.** `AGENT.md` §3.8 and `ARCHITECTURE.md` §10's Track L (L5) both name reward-hacking detection as a deliverable, and `TASKS.md` T30.5 schedules a synthetic reward-hack test in M1, but no row of the master lookup is it; the nearest records are `E1_per_item_diff` and `E7_contamination_check`, and neither is it. Writing the edge would mean inventing a record, so it is not written. **This is a corpus gap, not an authoring omission** — worth deciding before M3, since `ARCHITECTURE.md` §5.1's strongest intent signal — the phrase "just make the test pass" in a transcript, which §5.1 says should "route to E-section diagnostics" — has no record in E or anywhere else to route to.
* **`H7`'s step 5** (`H:236`, "Turn each category into an automatic detector") — same: no record exists, so `H7.unlocks` is empty.

The rest of the ticket's list resolved cleanly: "cost-per-success" is `H4`, "step compounding" is `H5`, "infra-vs-capability" is `H8`, and all three are in `H1.unlocks`. The ticket's phrase "H1/H7 unlock" is a paraphrase of `TASKS.md` line 164's "trajectory capture … unlocks"; the corpus direction is **H5 → H7** (`H:310-311`), not H7 → H5, and the records follow the corpus.

---

## 9. Doc conflicts found

| doc | says | corpus says | action |
|---|---|---|---|
| `ARCHITECTURE.md` §6.4, RAG recipe | five numbered items reading as one chain, with the unanswerable set last | `G:287-306` is **four branches**; G6 and G8 do not wait on recall@k | **No edit.** §6.4 is explicitly intent, and the records follow the corpus. Noted so nobody later "fixes" the records to match the prose. |
| `EL-116` acceptance criterion | "`vector_store` granted … faithfulness PENDING" | capability precedes readiness (`AGENT.md` §3.5 steps 3–4), so `G3` without `llm_api` is UNAVAILABLE | **No edit** to the ticket archive, per S14's rule. Carried into `TASKS.md` S18 as a fixture-4 note instead. |
| `TASKS.md` line 164 | "trajectory capture … unlocks cost-per-success, step compounding, infra-vs-capability, reward-hacking detection" | the first three are H4/H5/H8 and are encoded; the fourth has no record | **`TASKS.md` updated** (S16 section) to say so. |

`CLAUDE.md` §4's G and H rows were checked line by line against both deep dives and are **correct on every item**, including "unanswerable (false-answer rate + over-abstention)" — which is the wording that led to `G6.produces` gaining its third number (§10).

---

## 10. Smaller things, recorded so they are not silent

* **`G6` produces three numbers, not two.** `G:188` names the false-answer rate and abstention **precision** (of all refusals, how many questions really were unanswerable); `G:195`/`G:196` name the **over-abstention** rate (of answerable questions, how many were refused). They are different quantities measured on different halves of the set. The lookup row and `CLAUDE.md` §4 each name one of them, which is why they looked like they disagreed. Both are now in `produces`, alongside the false-answer rate. S14's note that "`G6` is the only over-abstention record anywhere" is still true, and it still cannot serve §5's safety non-negotiable, because it is scoped to RAG answerables.
* **`G8` gains a third number too**, `answers_with_a_bad_citation_rate`, from `G:261` "Report both, plus the share of answers with at least one bad citation" — the same user-experienced figure `G3` already reports as its unsupported-claim rate.
* **`H1` gains `scaffold_version` in `produces`**, from `H:39`. `H:23` makes the scaffold part of the system under test, and the fintech scenario's +19 points came from the scaffold, not the model: a result without the scaffold version recorded is not interpretable.
* **`H4` gains `full_cost_per_resolution`**, from `H:138`. It is the number that *flips the answer* in the logistics scenario — ₹18.5 for the "cheap" agent versus ₹11.5 for the "expensive" one — and the row's own worked example computes it.
* **`H5` gains `db_connection`** in `required_tools`, from `H:167` "Define milestones as state checks (A2), not transcript events". A milestone that reads the transcript is the failure the record exists to prevent, so asserting state is not optional.
* **Section G's vocabulary collapse is unchanged and now mitigated.** All eight `Situation` cells still map onto `rag_answer` alone, so `match()` cannot discriminate within G. S12 said the build order would have to be what sequences them; it now does — §3's traces show four distinct plan states from the same single situation member.
* **`gates` was not touched** in either file. No G row and no H row states one beyond what S12 derived.
* **`capture_cost` was not touched.** `G1`'s `medium` is arguable against `G4`'s `high` (gold-passage labels at ~40 questions per annotator-hour, `G:33`), but nothing in the deep dive ranks them, and re-litigating an S12 judgement without a source is not enrichment.

---

## 11. Carry into S17 (`EL-117`, enrich I + J)

1. **`H4.unlocks` already names `J3_cost_quality_pareto`** (`H:139`). S17 owns J3 and should check the edge reads correctly from the other side.
2. **`J3` is the only J record reachable from H.** Section J's own gates are S17's.
3. **`E2_metric_outcome_check` is now named by `G4`** (`G:136`), and `E6_oracle_run` by both `H1` (`H:40`) and `H8` (`H:267`). All three were already enriched by S15 and were not modified.
4. **The `A2` gate question in §4 is open** and is section A's, not S17's. It needs a ruling, not a stage.
5. **`C1_wilson_ci` companions were added to G1, G5, G6, G7, G8** on `00-INDEX.md:35`'s authority, continuing what S13 started and S14 carried through D. **`G2`, `G3`, `G4` and all of H except `H2`/`H3` do not name C1**, each for a stated reason: G2 and H1/H5/H7/H8 produce explanations rather than proportions, G3 and G4 name `F1` and `B6` instead because the source names those, and H4's output is money. S17 should make the same pass over I and J, at which point every section will have been decided and the "which records get C1" question closes.
6. **S18's fixtures 4 and 5 both have a trace in this report to copy from** — §3 variant 1b or 1c for fixture 4 (with the `llm_api` grant note), §4 variant 2b for fixture 5. Fixture 5's assertion should be on `unavailable`, naming `trace_capture`, not on `pending`.
