# S23 / EL-124 — Planner assembly + render

**Status:** complete. **641 passed, 0 skipped** · `mypy --strict` clean (16 source files) · all **17 live fixtures pass** · all **20 plans rendered** to [GATE0-RENDERED-PLANS.md](GATE0-RENDERED-PLANS.md).

**M0 is code-complete.** What remains is 🔒 **Gate 0** itself: a human reading the 20 plans and agreeing with every one.

**Read:** `AGENT.md` §3.5, `TASKS.md` S23, `USER_EXPERIENCE.md` §3.1 + §4, `PLAN.md` §5, and all 20 fixtures.

> **§3 and §4 are the ones to read.** §3 is the six sanity queries — three of six do not behave as `PLAN.md` says, all three were reported before this module existed, and none was papered over. §4 is the surprises you asked to hear about now rather than at Gate 0.

---

## 1. What exists

| | |
|---|---|
| `evalloop/plan/planner.py` | frozen `Plan`, pure `plan()`, `render()` |
| `tests/test_planner.py` | 33 tests: the 17-fixture runner, render, the six sanity queries, the three constraint records |
| `tests/render_gate0.py` | builds the artifact; `python -m tests.render_gate0` regenerates |
| `tests/test_planner_artifact.py` | 5 tests: the artifact exists, is **current**, holds 20 plans, marks the blocked ones, shows four states on every one |
| `GATE0-RENDERED-PLANS.md` | the Gate 0 artifact, 20 plans, 301 lines |

**The parked test is gone, not skipped.** `test_fixtures_match_the_planner` existed with a `@pytest.mark.skip` while `evalloop/plan` did not; the real comparison is now `test_planner.py::test_fixture`, and a superseded skip is noise in the summary. The suite has **no skips**.

### The fixture runner names the field, not just "assertion failed"

Item 2 asked for this and it earned its keep immediately. On a mismatch it prints, per field: `ready` with **order marked as significant**, and for the three mappings a split into *only in planner* / *only in fixture* / *differing (planner, fixture)* — then the full rendered plan. That shape is what localised the ruling-2b defect in S22 in one read instead of a bisect.

---

## 2. The resolution order, and the three places it is load-bearing

Implemented in `AGENT.md` §3.5's sequence exactly. Three orderings are behaviour rather than convention, and each is asserted:

* **Step 2 before 3 and 4.** A constraint fires on the situation alone, so a prohibition does not wait on a tool grant or on evidence. "Never accuracy on a rare class" is true on the first observation — `test_sanity_4_rare_class` asserts `D1` in `prohibited` at *zero* evidence.
* **Step 3 before 4.** A record missing a tool never reaches the readiness check, so it never shows a pending reason. `G3_faithfulness` without `llm_api` is **unavailable, not "pending on recall@k"** — which is the whole reason fixture 4 grants `llm_api`.
* **Step 5 before 6.** Conflicts resolve among what the situation selected, *then* companions arrive. A suppressed record does not drag its companions into the plan.

**Step 6 is a loop**, per S22's ruling 2b: `resolve_companions` expands one level, the planner buckets what came back, and calls again with the newly **ready** records until a round adds nothing. Every fixture settles in **1 or 2 rounds**; `MAX_COMPANION_ROUNDS = 16` guards a future registry, not this one.

**`pending` and `unavailable` preserve bucketing order** — step-7 order for matched records, then companions in the round they arrived. Deterministic, and it means the pending queue reads in the same priority order as `ready`, so the next thing you will be able to run is near the top.

---

## 3. `PLAN.md` §5's six sanity queries — **three of six diverge**

Each is an explicit test asserting **what the planner does**, with the divergence in its docstring. Nothing was adjusted to make a query pass: the only ways to do that are to change a record or a fixture, which `CLAUDE.md` §3 and §7.4 forbid.

### ❌ Q1 `summarization` → "faithfulness, with the length check attached". **Neither.**

```
READY        (none)
PENDING      A4_judge_binary_criteria  needs judge_human_kappa_to_trust: 0.6, have 0; judge_human_kappa_to_gate: 0.8, have 0
UNAVAILABLE  (none)
PROHIBITED   (none)
```

Two independent causes:

1. **Faithfulness is unreachable.** `G3_faithfulness` triggers on `rag_answer` only. The corpus scopes claim-decomposition faithfulness to section G, where it is entailment against *retrieved context*; **no row of the master lookup covers entailment against a source document**, which is what summarization faithfulness is.
2. **The length check cannot attach, because its host is not ready.** The `A4 → E3` edge exists and is correct (`AGENT.md` §5, "any judge score is reported with output length"), but step 6 follows edges only out of ready records, and A4 is pending on the κ bars `F:20` and `F:72` state in the imperative.

**This is finding F2 at full force:** trust bars placed in `requires` read as "not enough data yet" and suppress the record *along with its mandated companion*. A summarization session on a fresh repo offers nothing at all.

### ✅ Q2 `code generation` → "execution first, judging deprioritised or excluded". **Satisfied, vacuously.**

A1 is rung 1 and first. It carries `conflicts_with: [A4_judge_binary_criteria]`, so judging *would* be suppressed — but **A4 never matches `code_generation`** (`A:15` routes only open-ended text to it), so the edge never fires. Judging is excluded by not being selected. The stated behaviour is delivered; the mechanism the query tests is never exercised.

And with no sandbox, **nothing remains** — one permission request is the entire plan.

### ✅ Q3 RAG → recall before faithfulness. **The only one fully met.**

`G3` pending on `recall_at_k_measured`; once that is true it stays pending on `claim_labels: 150` (`G:102`) and nothing else. Asserted both before and after.

### ⚠ Q4 `rare class` → "recall ready, accuracy prohibited". **Half.**

* `D1` reaches `prohibited` ✅ — but **the subject column holds a record id, not "accuracy"**. `TASKS.md` S23's mock wants `PROHIBITED   accuracy   rare_class: …`; the schema cannot produce it, because no field names the forbidden metric (**finding F5**, which `TASKS.md` itself already records against this mock).
* **"recall ready" is false at low n.** `D1` carries `positives: 100` from `D:34`, so at zero evidence `D1` is `prohibited` **and** `pending`. Recall becomes available at 100 positives.
* `D1` lands in `prohibited` *and* `ready` once there is evidence, because step 2 runs before step 4 and one record is both the prohibition and the PR-curve measurement. Awaiting a ruling.

### ❌ Q5 "a single observation" → "only facts". **Two statistics fire at n = 1.**

`B1_paired_evaluation` produces a paired difference over a single pair; `C6_permutation_test` a permutation test with one permutation. Neither is a fact.

**The cause is finding F8.** `B5_ci_from_n` carries `{sample_size_stated: true}` and **unlocks B1** — the ordering exists, in `unlocks`, which `AGENT.md` §3.5 never reads. The registry knows B1 should follow B5 and the planner fires B1 anyway. The test asserts this **as the defect it is**, with a comment saying so.

The honest half does hold: for every situation checked, no record with a stated bound fires without its evidence.

### ⚠ Q6 "what needs 200+ samples?" → "significance tests, judge agreement". **True as asked; not what `PLAN.md` means.**

Every record carrying a ≥200 bar is pending at low n ✅. But the only two are **`A6_expert_human_review`** (`items: 200`) and **`A7_tiered_online_scoring`** (`judge_labelled_items: 5000`) — neither a significance test nor a judge-agreement check. Significance is stated as a *formula* (`C2`'s `n ≈ 16·p(1−p)/δ²`, in `rule_of_thumb`) and judge agreement as a *range* (F1's 150–200, left null by the range policy). **The query cannot be answered by reading `requires` at all.**

### Scoreboard

| | query | verdict |
|---|---|---|
| Q1 | summarization | ❌ nothing ready; faithfulness unreachable; companion suppressed with its host |
| Q2 | code generation | ✅ vacuously; no-sandbox plan is empty |
| Q3 | RAG | ✅ |
| Q4 | rare class | ⚠ prohibition unnameable; recall pending at low n; D1 in two buckets |
| Q5 | single observation | ❌ B1 and C6 fire at n=1 (F8) |
| Q6 | 200+ samples | ⚠ true as asked, wrong records |

**`PLAN.md` §5's gate is not met as written, and `PLAN.md` was not edited.** Moving the gate is your call.

---

## 4. Surprises from the fixed order — the ones I would rather you read now

### 4.1 A prohibition cannot name what it prohibits, so PROHIBITED reads as an id

The rendered line is:

```
PROHIBITED   D1_pr_curve_never_accuracy  rare_class: Predicting "all good" scores 97% accuracy with 0% recall, …
```

against a mock that wants `accuracy  rare_class: …`. The reason is assembled from the only fields that exist — the situations that selected the record, and its `anti_pattern`, which is where the corpus's own figure lives. **The subject is missing and is not invented.** `TASKS.md` S23 already says "the PROHIBITED line still cannot be rendered from the schema"; this is that, confirmed by building it.

### 4.2 Step 2's "anything they prohibit leaves ready" is a **no-op** against this registry

What `D1` forbids is accuracy. **There is no accuracy record to remove.** So step 2 adds to `prohibited` and removes nothing — not an implementation shortcut, a consequence of F5. It will stay a no-op until a constraint can name its subject. Asserted for all three constraint records (`D1`, `D6`, `F5_cross_family_panel`).

### 4.3 `Plan` needed a sixth field, because the stated five cannot render the stated line

`AGENT.md` §3.5 types `prohibited: tuple[str, ...]`. `USER_EXPERIENCE.md` §3.1 renders a *reason* on the PROHIBITED line and §4 principle 3 requires one. **Those two cannot both hold with five fields.** I kept the five exactly as specified and added `prohibition_reasons: Mapping[str, str]`, documented as to why, rather than re-typing `prohibited` and breaking the stated shape. `Plan.__post_init__` refuses a prohibited id with no reason — §4 principle 3 enforced by the type.

### 4.4 The blocked fixtures render perfectly well, and fixture 11's plan *is* the ruling

A blocked fixture has no `expect`, but it has a `given`, so the plan renders. Fixture 11's:

```
READY        F1_gold_label_validation · F7_one_call_per_criterion · F8_few_shot_from_disagreements
PENDING      F2_cohens_kappa   needs judge_human_kappa_to_gate: 0.8, have 0.71
```

**The judge may be used and may not gate** — the opposite of the fixture's specified "judge may gate", now produced by running code rather than by a hand trace. That is the sharpest form of the question in §2 of `S19-REPORT.md`, and it is in the Gate 0 artifact marked **⚠ BLOCKED ON A RULING** so a reviewer cannot mistake it for an agreed plan.

Fixture 20's plan is **identical to fixture 6's** — `PROHIBITED (none)` — because `phi_present` matches no record. The absence is now visible in the artifact instead of being a missing file.

### 4.5 Where I expected a surprise and did not get one

`match` returning step-7 order from step 1 means `pending` and `unavailable` come out in priority order for free, and the `ready` list needed only one final `sort` after companions arrived. I had expected the companion loop to need a re-sort per round; it does not, because `resolve_companions` already returns `added` in step-7 order.

---

## 5. Fixtures I suspect are wrong

**None of the 17.** All pass, and none was edited.

The three **blocked** ones are not "suspect" — they are known-unanswerable and carry their options. For completeness, with the source line that makes each unanswerable:

| | why it cannot be written | source |
|---|---|---|
| 11 | κ 0.71 clears the *use* bar and fails the *gate* bar | `F:20`, `F:72` |
| 14 | the margin rule is `B5`'s, and B5 triggers on `external_leaderboard` only | `B:22` / the record's triggers |
| 20 | there is no PHI record; "PHI" appears nowhere in `knowledge rules/` | — |

---

## 6. Carry forward

### M0 is code-complete. 🔒 Gate 0 is a human reading 20 plans.

`PLAN.md` §5: "Human reads all 20 rendered plans and agrees with every one. Fix anything disputed before M1." The artifact is [GATE0-RENDERED-PLANS.md](GATE0-RENDERED-PLANS.md), and `test_the_artifact_is_current` means it cannot go stale behind you.

### Fifteen rulings are open; twelve are decisions rather than work

1–8 in `S17-REPORT.md` §9, 9–14 in `S19-REPORT.md` §7, and this stage adds:

| # | ruling | where |
|---|---|---|
| 15 | **`Plan`'s sixth field** — accept `prohibition_reasons`, or re-type `prohibited` as a mapping and amend `AGENT.md` §3.5 | §4.3 |

The two that change M0's visible output most are unchanged and now demonstrated by running code: **F2** (κ trust bars in `requires` empty every judge-graded plan on day one — §3 Q1) and **F8** (`unlocks` read by nothing, so `B1` fires on a single pair — §3 Q5).

### What M1 inherits

`plan()` is pure and total: four arguments in, a frozen `Plan` out, no I/O. The session layer (M2) turns `Plan.unavailable` into permission requests — `check_capability` already names the tools in the order the record declares them, so the request text needs no further work.
