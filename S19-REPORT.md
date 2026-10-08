# S18 + S19 / EL-118 + EL-119 — the 20 planner fixtures

**Status:** complete, with **three of the twenty blocked on a ruling and not written**. 541 passed · 1 skipped (the parked planner comparison) · `mypy --strict` clean · `check_integrity()` `[]`.

**Scope note.** The ticket asked for "the remaining 15 fixtures", and **S18 had never been run** — there was no `tests/fixtures/planner/`, no format, and none of the first five. Result item 1 asks for "20 total", so this stage did S18's five as well. Had I written only 6–20, nothing would have loaded.

**Read:** `TASKS.md` group 6, `AGENT.md` §3.5 + §5, `CLAUDE.md` §7.3 + §7.4, `knowledge rules/00-INDEX.md`, and the sections of the corpus each fixture cites.

> **§2 is the one you said you'd decide yourself.** §3 is a sweep result I did not expect to find and think matters more than any single fixture.

---

## 1. What exists now

| | count | where |
|---|---|---|
| **Live fixtures** | 17 | `tests/fixtures/planner/NN_*.yaml` |
| **Blocked fixtures** | 3 | `tests/fixtures/planner/NN_*.BLOCKED.yaml` — excluded from the glob, each holding its question and its options |
| **Validation tests** | 9 × 17 parametrised + 3 whole-set | `tests/test_planner_fixtures.py` |
| **The real comparison** | 1, skipped | `test_fixtures_match_the_planner` — skips with a reason until `evalloop/plan` lands |

**Format**, as `TASKS.md` group 6 fixes it, with one correction: `unavailable` and `companions` are **maps**, not lists, because `AGENT.md` §3.5 types them `Mapping[str, tuple[Tool, ...]]` and `Mapping[str, tuple[str, ...]]`. `TASKS.md`'s example writes `unavailable: []`; empty maps are `{}`. The parser already supported the three-level nesting — its docstring cites these fixtures as the reason it does.

### What the validation tests assert now, before a planner exists

Every one of these is a defect class that would otherwise surface at `EL-123` as a confusing planner failure:

* the file parses under the record format parser;
* `given` and `expect` have exactly the agreed keys — a fixture that forgets `prohibited` fails rather than silently asserting nothing about it;
* **every situation and tool name parses through the enums.** A hand-written `llm_api_crossfamily` would otherwise sit in a fixture until the planner matched nothing — `CLAUDE.md` §6 calls this the most important correctness decision in M0;
* **every record id in every bucket resolves**, companions included;
* `ready`/`pending`/`unavailable` are **pairwise disjoint** — `prohibited` is deliberately excluded, see §4;
* **every companion edge is one the registry actually holds.** A fixture asserting `X: [Y]` where record X never names Y is describing a planner nobody will build;
* **every pending reason names a key the record's `requires` actually has.** This is not hypothetical — it is precisely what `TASKS.md`'s illustrative example said before S17 corrected it (`paired_runs` for a record keyed on `discordant_pairs`);
* every `unavailable` entry lists a tool the record requires **and** the fixture withholds.

### How the expectations were derived, and then checked

Each `expect` block was written by reading the records (which were read from the corpus). **Then**, independently, a throwaway script in the scratchpad applied `AGENT.md` §3.5 steps 1–6 to each `given` block and diffed the result. **All 17 agreed on `ready` order, `pending` keys and reasons, `unavailable` keys and tools, and `prohibited`.** One disagreement surfaced on `companions` and was a real authoring slip in fixture 19 — a transitive companion (`E1 → E4`) I had left out — now fixed.

That script is verification, not generation: it lives in the scratchpad, nothing in the repo imports it, and `CLAUDE.md` §7.3's rule ("fixtures written from the source methodology, not from imagined code") holds.

---

## 2. Fixture 11 — the κ / label-count question. **Yours to decide.**

### The specification

> `11. new_judge_built, 60 labels, kappa 0.71 -> judge may gate`

### The corpus says otherwise, twice, in the imperative

| line | text |
|---|---|
| `F:20` | "*κ ≥ 0.6* before using a grader at all, and *κ ≥ 0.8* before letting it gate a release." |
| `F:72` | "**Use a grader only at 0.6 or above, and gate releases only at 0.8 or above.**" |
| `F:27` | "# F1 – VALIDATE AGAINST 150–200 HUMAN GOLD LABELS BEFORE USE" (the record's own heading) |

So **κ 0.71 clears the *use* bar and fails the *gate* bar**, and 60 labels is well under the 150–200 the record is named for.

The records agree with the corpus, and were re-checked before this fixture was attempted: `F2_cohens_kappa.requires` is `{judge_human_kappa_to_trust: 0.6, judge_human_kappa_to_gate: 0.8}`, recorded by S13 and re-confirmed by S15 against both lines.

### What the registry actually produces for the specified inputs

```
ready:   [F1_gold_label_validation, F7_one_call_per_criterion, F8_few_shot_from_disagreements]
pending: F2_cohens_kappa: "needs judge_human_kappa_to_gate: 0.8, have 0.71"
```

**The judge may be used and may not gate** — the opposite of the fixture's stated expectation.

### A third point, which is why the label count is not a side issue

`F:74` — *"Bootstrap κ (Section B6). A κ of 0.65 on 150 items can have a CI running from 0.52 to 0.77."*

On **60** labels the interval around 0.71 is wider still and would straddle 0.6. **The two numbers in the specification pull against each other:** 60 labels is too few to establish the κ that the fixture then wants to act on. Whichever way you rule on the gate bar, the label count is independently too low to support the claim.

### Your options

| | option | cost |
|---|---|---|
| **A** ← recommended | **Fix the expectation, keep the inputs.** F2 pending on the gate bar; the judge may be used, not gate. | None. The fixture then tests the 0.6/0.8 split — and it is the **only** fixture in the set that would distinguish the two bars from each other, which makes it more valuable than the original. |
| **B** | **Fix the inputs, keep "may gate."** 150 labels, κ 0.82. Then F2 is ready, the judge may gate, and the fixture agrees with `F:20`, `F:72` and `F:27` at once. | None, but it loses the 0.6-vs-0.8 distinction A captures. **Taking both A and B** as two fixtures costs one over the 20 `TASKS.md` budgets for, and I would spend it. |
| **C** | **Change the records so 0.71 may gate.** | Requires overruling `F:20` and `F:72`, which state 0.8 in the imperative. This is the invented number `CLAUDE.md` §3 forbids. Listed for completeness; not recommended. |
| **D** | **Decide the κ bars don't belong in `requires` at all.** | This is the deeper question — S17 finding **F2**. A *trust* bar in the *readiness* field suppresses the record instead of reporting it with its calibration state. If the bars move to a new field, this fixture's shape changes with them, and A's `expect` block is what it looks like meanwhile. |

Nothing is implemented. `11_judge_may_gate.BLOCKED.yaml` holds the `given` block, all of the above, and **no `expect` block** — asserting either reading would pre-empt your ruling, and a test enforces that a blocked fixture has no `expect`.

---

## 3. The sweep nobody asked for: **six `Situation` members reach no record**

Fixture 20 could not be written because there is no PHI record. Chasing that produced a worse result.

```
Situation members: 57    reachable: 51    DEAD: 6
    classification        data_pipeline        model_training
    contamination_risk    distribution_mismatch    phi_present
```

**`match()` returns nothing for six of the 57 members.** A session classified into any of them gets an empty plan with no explanation — not "pending", not "needs a tool", just nothing. S3 justified every member it added; these six were added and never claimed by a record.

### One of the six is a plain authoring miss, not a corpus gap

**`contamination_risk` is dead while `E7_contamination_check` exists** — and E7 triggers on `benchmark_too_good` only. A record named for contamination that does not fire on the contamination situation is the cheapest of the six to fix, and it is a one-line change to S15's file. I did not make it: adding a trigger changes which sessions select the record, which is a decision, not a typo.

The other five look like genuine gaps: `classification`, `data_pipeline` and `model_training` are artifact kinds the corpus never writes a row for, and `distribution_mismatch` has no technique attached anywhere.

**Two `Tool` members are also unused:** `ocr` and `vision_model`. Less serious — an unused tool costs nothing until a record needs it — but worth knowing that nothing in the registry requires either.

---

## 4. The other two blocked fixtures, and four that could not assert what they were named for

### Blocked: fixture 20 — PHI

**There is no PHI record.** Checked three ways: nothing triggers on `phi_present`; the string "PHI" appears **nowhere** in `knowledge rules/`; the nearest thing is a `required_signal` on `I8` — "PII is scrubbed before an item enters the set" (`I:277`) — which is a precondition on building an eval set, not a gate, and is PII rather than PHI.

So the plan for `phi_present + structured_extraction` is just fixture 6's plan. There is nothing to assert a position for, and inventing a record to be the gate is what `CLAUDE.md` §3 forbids.

Four options are in the file. **The one I'd look at first is D:** treat redaction-before-egress as a *capability-broker* concern rather than a registry one. Decision `EL-002` already puts transports and grants in the broker; a precondition the broker enforces on every tool call is the same kind of thing, and if that is right then `phi_present` does not belong in `Situation` at all. Option A — authoring the record — would create the **first record in the registry with no corpus provenance**, and its `source_ref` would fail S17's resolution test. That is a decision about what the registry *is*.

### Blocked: fixture 14 — the margin at n = 25

The margin rule exists and is **unreachable from `small_sample`**. It is `B5_ci_from_n`'s, recorded verbatim: *"the worst-case 95% margin on a percentage is about 100/√n points."* At n = 25 that is **±20 points** — exactly the figure the fixture wants stated. But **B5 triggers on `external_leaderboard` only**, so a `small_sample` session never selects it.

And no statistical comparison is pending, because none is matched: the only record triggering on `small_sample` is `C1_wilson_ci`, whose `requires` is empty — correctly, since Wilson is chosen precisely because it behaves at small n. The traced plan is `ready: [C1_wilson_ci]`, `pending: {}`. **There is nothing to be pending.**

**Recommended option: add `small_sample` to `B5.triggers_on_situation`.** `small_sample` currently reaches exactly one record — it is one record away from joining the six dead members — and B5 is the single most useful thing to say at n = 25. The cost is a situation mapping the master lookup does not state, in a section S13 already enriched: the same class of change as the A2 gate S16 proposed and did not make.

### Written, but unable to assert their stated purpose

| fixture | stated as | what it actually asserts |
|---|---|---|
| **15** `score_jumped` | "reward-hacking investigation" | **No reward-hacking record exists** in any of the 73 (S16's finding, re-confirmed). `ARCHITECTURE.md` §5.1 names the strongest signal for it and says it should "route to E-section diagnostics"; nothing is there to route to. The fixture asserts the diagnostics that do exist: `E1_per_item_diff` ready, `E4_aa_baseline` pending on three runs. |
| **19** `shipping_change` | "regression suite + **statistical** gates" | Both gates reachable from `shipping_change` are **absolute** (I1 `I:33`, I9 `I:310`). The statistical gate is `I2`, which triggers on `ci_flaking` — so a session that is merely shipping never selects it. |
| **18** `api_endpoint + sql_generation` | "both families, correctly merged" | **Both situations reach only `A1_execution_based`.** So it is a clean dedup test — A1 appears once, which is what result item 3 asks for — but it tests no breadth, because there is no second record. For `api_endpoint` that is thin: `ARCHITECTURE.md` §6.5 expects schema validation on the response too, and `A5_schema_field_scoring` triggers only on `structured_extraction`. |
| **12** `rare_class` | "accuracy **explicitly** prohibited" | `D1` lands in `prohibited`, but **the word "accuracy" appears nowhere in the plan** — no field names what a constraint forbids (S14 finding **F5**, still open). The prohibition is structural only, which is the one thing the fixture is named for. |

### Fixture 13 needed a second situation to test anything

"cluster bootstrap **replaces** plain bootstrap" is a `conflicts_with` edge, and it is the only fixture that exercises one. `B7_cluster_bootstrap` triggers on `grouped_items`; `B6_bootstrap_ci` triggers on `metric_without_formula`. **A plan built from `grouped_items` alone never contains B6, so the edge never fires and the replacement would be untested.** The fixture states both situations so both records are matched and the suppression is observable, and it asserts B6's **absence from all four buckets** — a fixture checking only B7's presence would pass whether or not the edge worked.

### `prohibited` is excluded from the disjointness check, on purpose

`D1` in fixture 12 is both `ready` **and** `prohibited`: it is the prohibition *and* the measurement, and step 2 runs before step 4. The `Plan` dataclass permits it and **nobody has ruled on whether it is intended** (S17 §4, Q4). The test must not assert that away, so it checks only `ready`/`pending`/`unavailable` pairwise, with the reason in its docstring.

---

## 5. Two findings from authoring the `given` blocks

### Tool subsumption does not exist, and `TASKS.md`'s example tripped on it

`A4_judge_binary_criteria` requires `llm_api`. `TASKS.md`'s illustrative fixture grants `[source_doc_read, llm_api_cross_family]` — so A4 is **UNAVAILABLE**, not pending, and the example would have asserted the wrong bucket for a third reason beyond the two S17 already found.

A cross-family LLM API *is* an LLM API, and the registry has no way to say so. `AGENT.md` §4 puts routing in the capability layer, which is where subsumption presumably belongs — but today a fixture (and a session) must grant both members explicitly. Fixture 3 grants both, so it tests readiness rather than this gap.

### Fixture 2's answer is "nothing", and that is the honest answer

`code_generation` with no sandbox: exactly one record triggers on `code_generation`, so removing the sandbox **empties the plan**. The judge is not a fallback — `A4` triggers on `prose_generation` and `summarization`, not on code. The plan's entire content is one permission request. Defensible (without execution you cannot grade generated code honestly) and worth having written down before someone reads it as a bug.

---

## 6. Ambiguities, per fixture

Everything below was a judgement call in authoring the `given` block. None required interpreting a corpus number.

| fixture | the call |
|---|---|
| 3 | granted `llm_api` **and** `llm_api_cross_family`, so the fixture is about the κ gate rather than about §5's subsumption gap |
| 4 | granted `llm_api` so G3 reaches readiness — `EL-116`'s criterion said `vector_store` alone, which cannot produce a pending faithfulness |
| 5 | granted `sandbox`, `db_connection`, `cost_api` but not the two the fixture is named for, so both buckets are exercised: tools stop H1/H3/H5/H6/H7/H8, the boolean stops H2/H4 |
| 8, 9 | `evidence` states `discordant_pairs` and not `runs`, so `E1_per_item_diff` stays pending on `runs`. Deliberate: group 6 says keep evidence minimal. It does mean 8 and 9 read "have 0" for runs while stating 2 paired runs — the two are different evidence keys and `paired_runs` is not what E1 asks for |
| 12 | `positives: 100` from `D:34`, without which "recall ready" is simply false |
| 13 | two situations rather than one, per §4 |
| 16 | granted `production_logs`, without which the fixture is about a missing tool rather than about the ceiling |
| 17 | withheld `llm_api`, so A4 is unavailable and the fixture stays about the diagnostic. The contrast with fixture 3 is the point: E3 is ready here because the *symptom* selects it, and absent there because its *host* was pending |
| 19 | `runs: 2` so I1 and I9 are ready while their companion `E4` is pending on three — the clearest instance of a mandated companion arriving in the wrong bucket |

**No fixture was adjusted to make a test pass**, and no record was changed by this stage.

---

## 7. Carry forward

### For `EL-120`–`EL-122` (readiness, capability, planner)

1. **`test_fixtures_match_the_planner` is the parked comparison.** When `evalloop.plan` lands, parametrise it over `LIVE_PATHS`: build from `given`, assert `ready` **as an ordered list**, plus `pending` keys, `unavailable` keys and tools, `companions`, `prohibited`. Fixture 18 additionally needs reversing `given.situations` to leave `ready` unchanged; fixture 13 needs `B6_bootstrap_ci` in no bucket.
2. **Pending reasons are prose.** The fixtures write the canonical `needs <key>: <threshold>, have <actual>` form, and the validation test checks only that a real requirement key is named. `EL-121` owns the exact sentence, including the boolean form — which must not render as `"needs requires_pre_instrumentation: True, have 0"`.
3. **17 records carry a boolean requirement.** Fixtures 4, 5 and 13 exercise them.
4. **Step 6 forces companions only for ready records.** Fixtures 3 and 19 are the two faces of it.

### Rulings this stage adds to the list

| # | ruling | where |
|---|---|---|
| 9 | **Fixture 11's κ / label count** — options A–D | §2, and the `.BLOCKED.yaml` |
| 10 | **Six dead `Situation` members**, and `contamination_risk` being a one-line fix | §3 |
| 11 | **PHI: registry record, broker policy, or dropped?** — options A–D, D first | §4 |
| 12 | **`small_sample` → `B5`?** Without it the margin is never shown at the n where it matters most | §4 |
| 13 | **Tool subsumption** — does `llm_api_cross_family` satisfy `llm_api`? | §5 |
| 14 | **`D1` in two buckets** — intended or not | §4 |

Rulings 1–8 are in `S17-REPORT.md` §9 and are unchanged. **Of the fourteen, eleven are decisions rather than work.**

### What is left in M0 after this

`evalloop/plan/` — `readiness.py`, `capability.py`, `rules.py`, `planner.py` — and then the 20 rendered plans printed for human review, which `PLAN.md` §5 calls the gate. The registry and the fixtures are both finished.
