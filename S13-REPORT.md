# S13 / EL-113 — Enrich A + B from the deep dives

**Status:** complete. 418 passed, `check_integrity()` returns `[]`, `mypy --strict` clean.
**Read:** `knowledge rules/A-choosing-how-to-grade.md`, `knowledge rules/B-comparing-two-things.md`, `knowledge rules/00-INDEX.md`, `decisions/EL-004-claude-md-corpus-gaps.md`.
**Citations** are `A:<line>` and `B:<line>` against the two deep dives, `I:<line>` against `00-INDEX.md`. Every one in this report and in the record files was re-resolved against the file after writing; none points at a heading or a blank line.

Four things in here need a human ruling, and they are collected in §6. Everything else is copied or cited.

---

## 1. What changed

| | A | B |
|---|---|---|
| `source_ref` | → `A-choosing-how-to-grade.md § A1` … `§ A7` | → `B-comparing-two-things.md § B1` … `§ B7` |
| `ladder_priority` | 1, 2, 3, 4, 3, 5, null | null throughout |
| `requires` | 3 of 7 records now bounded | 5 of 7 records now bounded |
| `conflicts_with` | 4 new edges, all into A4 | 1 new edge, B7 → B6 |
| `unlocks` | A6 → A4 | B1 → B3, B2 → B4, B5 → B1 |
| `companion_checks` | all 7 records | B1, B2, B3 |
| `required_tools` | A2 gained `snapshot_restore` | unchanged |
| `required_signals` | all 7 sharpened | all 7 sharpened |
| `rule_of_thumb` | 6 of 7 carry a verbatim formula | all 7 |

`anti_pattern`, `worked_example` and `domain_scenario` were **not touched**. They are the master lookup's three columns and `tests/test_records.py::test_verbatim_fields_match_the_lookup_row` diffs them against the corpus; it still passes, which is the proof nothing drifted.

---

## 2. The ladder

```
rung  record                      source line
  1   A1 execution-based          A:11  "It runs (code, SQL, API call)"         ₹0, deterministic
  2   A2 end-state verification   A:12  "It changes a system (agent action)"    ₹0, deterministic
  3   A3 normalised exact match   A:13  "It states a short fact"                ₹0, deterministic
  3   A5 schema + field scoring   A:14  "It fills a structure (JSON, form)"     ₹0, deterministic
  4   A4 judge, binary rubric     A:15  "It's open-ended text"                  ₹, some variance
  5   A6 expert human review      A:16  "It's high-stakes and final"            ₹₹₹, slow, gold
  -   A7 tiered online scoring    A:18  "wraps all of the above"                ladder_priority: null
```

Five rungs. Nothing sits above 5 and nothing below 1.

### A3 and A5 share rung 3

**The line that decided it is the ladder box's cost/variance column.** `A:13` and `A:14` carry the *identical* annotation `₹0, deterministic`, which is the ladder's own marker for "same tier". Three things corroborate it and nothing contradicts it:

- The section's opening rule (`A:6`) names four grading moves — "execute it if it runs, check the system if it acts, compare strings if it's a fact, and use a judge only when nothing deterministic can see the property". A5's case (filling a structure) is not among them, so that sentence does not order A3 against A5 either.
- The decision flow reaches them from **mutually exclusive branches**: `A:299` "Is it a short fact with one right answer?" and `A:304` "Is it structured output (JSON, form, extraction)?". No artifact is ever a candidate for both, so the source never has to order them.
- `EL-004`'s own audit row reads them as one rung: "deterministic | A | `A:13` A3 normalised exact match; `A:14` A5 schema + field-level, both '₹0, deterministic'".

**The cost of a shared rung,** stated because it is real: the planner's step 7 orders graders by `ladder_priority` ascending, so an A3-vs-A5 tie falls through to the id tiebreak rather than to the methodology. It cannot bite, because their triggers are disjoint (`qa_answer` vs `structured_extraction`) and one situation never selects both. This invariant was on `integrity.py`'s "deliberately not checked" list as a hypothetical; it is now real, and the list was corrected rather than the rule added — a rule forbidding shared rungs would reject the corpus.

### A7 stays null

`A:18` places it outside the ladder in the ladder box itself: "A7 Tiered online scoring (**wraps all of the above**)". **Rung 0 and rung 6 were both declined.** 6 would reintroduce under a new name the rung `EL-004` removed for having zero corpus support, and 0 would be an ordering the corpus states nowhere. Its priority remains the open question `CLAUDE.md` §6 records for S6; S13 did not close it and had no basis to.

The null needs no integrity exemption: A7 is typed `procedure`, so no grader rule looks at it.

---

## 3. Execution beats judging

### The ticket's quoted line is not in the corpus

The ticket gives the corpus line as *"if there is any way to execute, execute"*. **That string does not appear anywhere in `knowledge rules/`** (`grep` over all twelve files returns nothing). The claim is right; the wording is a paraphrase. What I encoded against instead, verbatim:

| line | text |
|---|---|
| `I:34` | "**If you can execute the output or check it against the real world, do that instead of judging it.** Run the SQL, query the database, validate the checksum. **A judge is the fallback.**" |
| `A:6` | "… and use a judge only when nothing deterministic can see the property." |
| `A:54` | "Grading runnable output by its text … or asking a judge 'is this code correct?'. **A judge reads the code. It doesn't run it.**" |
| `A:92` | "A transcript tells you what the agent says it did, **not what it did**." |
| `A:127` | "Switching to an LLM judge because exact match is 'too strict'. The fix is a better normaliser. **A judge adds leniency where you least want it: on numbers.**" |
| `A:130` | "For a fact with one right answer, **a judge only adds cost and a way to be wrong**." |
| `A:166` | A4's own *When NOT to use it*: "**When code could check the criterion.** Length limits, 'contains a timeline', **valid JSON** and banned phrases are regex jobs. Don't pay a judge to do them." |

### The edges

Four, all one-way into A4, each cited in that record's `extraction_notes`:

| edge | the line that carries it |
|---|---|
| `A1 → A4` | `A:54` + `A:166` + `I:34` |
| `A2 → A4` | `A:92` + `A:70` + `I:34`'s "query the database" |
| `A3 → A4` | `A:127` + `A:130` — the most explicit statement in the section |
| `A5 → A4` | `A:166`, which names A5's first stage by name ("valid JSON … are regex jobs") |

Direction is one-way by design. `CLAUDE.md` §6 defines the field as "record ids this **replaces/invalidates**": the deterministic grader replaces the judge, and a judge never invalidates execution, so A4 lists none of them back. `integrity.py` already flags unreciprocated `conflicts_with` as an unguarded invariant, and this is the case it was anticipating.

### ⚠ The edge will not actually suppress a judge for code generation

The ticket's rationale is "this is what makes the planner suppress a judge for code generation". **It does not, and I did not make it, because doing so would require inventing a trigger.**

A1 triggers on `code_generation, sql_generation, api_endpoint`. A4 triggers on `prose_generation, summarization`. **The trigger sets are disjoint**, so `match()` never returns both from a code-generation situation, and step 5 has nothing to suppress. Two sub-cases:

- **Session is code only.** A4 never matches, so there is no judge to suppress. The right outcome, reached without the edge.
- **Session is code *and* prose** (both situations inferred, which the agent does routinely). A1 and A4 both match, the edge fires, and A4 is suppressed — **which is wrong.** The prose still needs a judge. The corpus's claim is scoped to *an artifact* ("for this output, execute rather than judge"); `conflicts_with` is scoped to *a record*.

I did not add `code_generation` to A4's triggers. The lookup row says "output is open-ended text", so adding it would be an invented trigger, and it would make A4 fire on every code session — the opposite of what the edge is for. The edge is written, correct and cited; it is **documentation the planner cannot yet act on correctly**. This is schema finding **F4** and it is the one I would fix first after F1.

---

## 4. Thresholds

### 4a. Copied verbatim into `requires`

| record | key | value | source |
|---|---|---|---|
| A4 | `judge_human_kappa_to_trust` | `0.6` | `A:146` "Require **κ ≥ 0.6 before you trust a criterion**" |
| A4 | `judge_human_kappa_to_gate` | `0.8` | `A:146` "and **κ ≥ 0.8 before it gates a release**" |
| A6 | `annotators` | `2` | `A:211` "**Two** qualified experts independently grade a stratified sample" |
| A6 | `expert_kappa` | `0.6` | `A:220` "**If κ is below 0.6, the rubric is ambiguous.**" |
| A7 | `judge_labelled_items` | `5000` | `A:257` "trained on **5,000+** judge-labelled items" |
| B2 | `judgment_orders` | `2` | `B:64` "Every pair is judged **twice**, as A-then-B and as B-then-A"; `B:70` "**Judge both orders, always.**" |
| **B3** | **`discordant_pairs`** | **`25`** | **`B:107` "At least 25 discordant pairs (b + c ≥ 25) are needed for the χ² approximation."** |
| B4 | `candidates` | `5` | `B:134` "When you're ranking **five or more** options" |

**On B3 specifically, as the ticket asked.** The corpus states `25` exactly, as a hard lower bound on `b + c`, and it is neither a range nor a rule-in-place-of-a-number. `TASKS.md` said "~25"; **the corpus has no tilde**, and the bound is repeated as a hard test twice more — `B:293` in the decision flow ("b + c < 25? → exact binomial instead") and `B:121` in the second worked example ("b + c = 14, which is below 25"). So `25` is copied, not chosen, and `TASKS.md`'s approximation was the loose form. That line is now corrected.

### 4b. Copied verbatim into `rule_of_thumb`

These are formulas, comparator settings and budget rules — not readiness thresholds — so they do not belong in `requires`. Each is verbatim from its own record.

| record | content | source |
|---|---|---|
| A1 | "if a line of code can check it, a line of code should check it" | `A:21` (section-level; noted as such in the record) |
| A3 | token-F1 ≥ 0.8, hand-audit the 50 items closest to it | `A:111`, repeated `A:302` |
| A4 | 150–200 human labels; κ ≥ 0.6 to trust, ≥ 0.8 to gate | `A:146` |
| A5 | comparator per field type: checksum/regex, ₹1, ISO, token-F1 ≥ 0.9, exact | `A:183` |
| A6 | 3–5 min per item per expert; ~₹300 per review; 400 reviews ≈ ₹1.2 lakh | `A:222` |
| A7 | tier 0 < 5 ms, tier 1 < 50 ms, both on 100%; tier 2 on a 1–2% uniform sample | `A:250`, `A:256`–`A:258` |
| B1 | 5,000 resamples of item IDs; 2.5th and 97.5th percentiles | `B:37` |
| B2 | judged twice, both orders; a win counts only when both orders agree | `B:64` |
| B3 | χ² = (\|b − c\| − 1)² / (b + c), 1 df; compare with 3.84 (p = 0.05) or 6.63 (p = 0.01) | `B:100`, `B:108` |
| B4 | P(i beats j) = sᵢ / (sᵢ + sⱼ); ML fit not sequential Elo; bootstrap 1,000× | `B:134`, `B:142`, `B:143` |
| B5 | SE = √(p(1−p)/n), 95% margin ±1.96·SE; ±100/√n worst case, ±80/√n near 80%; tie below 1.4× margin | `B:169`, `B:176`, `B:177` |
| B6 | resample, recompute, 2.5th/97.5th; 5,000 for reporting, 1,000 while iterating | `B:209`–`B:211` |
| B7 | effective n ≈ n / (1 + (m − 1)·ρ); m = 10, ρ = 0.4 → 1,000 questions carry 217 | `B:243` |

B3's symbolic formula closes the note S10 left on that record. B6's "1,000–10,000×" from the lookup is replaced by the two values the deep dive actually prescribes for the two uses.

**B7's rule of thumb is a formula, and it needed no schema change.** The ticket flagged this as a candidate. `CLAUDE.md` §6 defines the field as "any stated formula, **verbatim**", the value is the formula's text, and nothing in M0 computes from it — the planner renders it. Reported as a predicted problem that did not materialise.

### 4c. Left null / empty, because the source states no number

| record | field | what is absent |
|---|---|---|
| A1 | `requires: {}` | no data-volume floor anywhere in A1 |
| A2 | `requires: {}`, `rule_of_thumb: null` | A2 states no formula and no minimum task count |
| A3 | `requires: {}` | the F1 ≥ 0.8 bound is the comparator's pass threshold, not readiness |
| A5 | `requires: {}` | all four bounds at `A:183` are comparator settings |
| **B1** | **`requires: {}`** | **no minimum n is stated — see the gap below** |
| B6 | `requires: {}` | 5,000/1,000 are method parameters; the 9- and 900-example classes at `B:212` are the worked example's |

**Stated ranges, deliberately not reduced to a number**, continuing the policy S10 set (picking a value out of a range is the invented number `CLAUDE.md` §3 forbids):

| range | source | consequence |
|---|---|---|
| 150–200 human labels | `A:146` | A4 has no label-count floor in `requires` |
| 3–5 minutes per item | `A:222` | budget only; nothing needs it |
| 1–2% uniform sample | `A:250`, `A:259` | A7 has no sample-rate floor |
| **10–15% flip rate** | `B:73` | **B2's single most operative number is unencoded** — also an *upper* bound, see F3 |
| 10–30% position-bias flips | `B:70` | an observed base rate, not a threshold |
| **50–100 judgments per pair** | `B:140` | **B4 cannot tell whether the collected comparisons suffice to fit at all** |

> **⚠ Gap, not an omission — B1 fires at n = 1.** `requires: {}` means `evaluate_readiness` will call a paired bootstrap ready on one item. B1 states no minimum item count anywhere, so there is nothing to copy. The corpus's answer to small n lives in a *different* record — B5's `±100/√n` margin — and nothing in the schema lets B1 borrow it. This is the clearest case of the registry being unable to be honest about readiness while still being faithful to its source, and it is worth a decision of its own.

### 4d. Interpreted from prose — **FLAGGED FOR HUMAN REVIEW**

Four. In each, the *number* (where there is one) is verbatim and the *reading* is mine.

1. **`A6 requires.items: 200`** — `A:217` says "**Draw 200 items**, with at least 40% from the highest-risk intents". The figure is verbatim; reading an instruction to draw 200 as a readiness **floor** ("at least 200") is interpretation. The source does not say "at least". *If overruled:* drop the key; `annotators` and `expert_kappa` stand on their own.
2. **`B5 requires.sample_size_stated: true`** — `B:175` says "**Find n.** If the leaderboard doesn't state the test-set size, treat its rankings as unverified." The corpus states a *consequence*, not a flag; turning it into a boolean is my encoding. *If overruled:* drop it; `required_signals` already carries the precondition in prose, but then nothing machine-checks it.
3. **`B7 requires.cluster_id_recorded: true`** — `B:246` says "**Tag every item with its cluster ID**". Same shape: an instruction, not a flag. This is the ticket's "B7 grouping requirement into `requires` / `required_signals`", and I put it in both — the boolean for the readiness check, the prose for the reviewer. *If overruled:* B7 keeps only the `required_signals` form.
4. **`A4`'s two-key split.** Both κ values are verbatim from `A:146`, but splitting one metric into `judge_human_kappa_to_trust` and `judge_human_kappa_to_gate` encodes in key *names* a condition the source states in prose ("before you trust a criterion" vs "before it gates a release"). `requires` cannot say that the second applies only when the record is gating. See F3.

Two further readings, lower stakes, recorded so they are not silent:

- **`A4` keeps `required_tools: [llm_api]` and does not gain `human_labels`**, although `A:146` requires validation against human labels and `A:163` calls shipping unvalidated criteria a mistake. The Tool enum means "must exist for the technique to be **runnable**" (`EL-002`); a judge is runnable without gold labels, it is only *untrustworthy* without them, and untrustworthiness is a readiness fact — which is why the κ bounds are in `requires` instead. Encoding it as a capability would make the planner refuse to propose a judge at all.
- **`A2` gained `required_tools: snapshot_restore`** from `A:75` step 3, "Reset per run. **Restore the environment snapshot** before every task". A1 did not, although `A:34` says "Freeze a snapshot": freezing a fixture once is not per-run restoration.

---

## 5. Schema findings

`CLAUDE.md` §7.5 predicted the schema would need a change after the first two deep dives. It does. **Nothing below was worked around and no field type was widened.** Every number without a home is sitting verbatim in the owning record's `extraction_notes`, where a human can read it and the planner cannot.

### F1 — No field for a fallback technique when a readiness bound is not met ← *highest severity*

`B:107`, second sentence: "**Below that, use the exact binomial test** on b against b + c at p = 0.5." `B:293` repeats it in the decision flow.

So the corpus's instruction below 25 discordant pairs is *do something else*. With `requires: {discordant_pairs: 25}` and no fallback field, the planner reports B3 as not-ready and **stops** — it will tell a developer "not enough data" when the methodology has a test that works at that n. This is worse than an incomplete plan: the readiness machinery produces a confidently wrong "nothing can be said here".

It is also a **corpus-coverage** finding: there is no exact-binomial record to point at (it is not a section B row), so a `fallback_when_unready: tuple[str, ...]` field would have nothing to resolve to until one exists. Both halves need deciding together.

### F2 — No field for a trust bar on a *produced* metric

Eight instances in A and B alone. These are thresholds that **invalidate the technique or block a launch** when a number the technique produced crosses them. `requires` is pre-run readiness; `gates` is a three-valued enum, not a number. Neither can hold them.

| bound | source | what it does |
|---|---|---|
| mutant survival > 5% | `A:38` | the fixtures aren't discriminating; fix them before trusting A1 |
| claim–state mismatch > 2% | `A:77` | **blocks launch, whatever the success rate** |
| normaliser false negatives > 10% of 50 sampled | `A:112` | fix the normaliser |
| expert κ < 0.6 | `A:220` | rubric is ambiguous — *this one fits `requires` and is encoded* |
| judge κ < 0.6 / < 0.8 | `A:146` | don't trust / don't gate — *encoded, see F3* |
| tier-1 recall < 80% | `A:260` | retrain the classifier |
| flip rate > 10–15% | `B:73` | **the judge is unreliable for this comparison** |
| CI width ratio > 1.5× | `B:248` | clustering matters; report the cluster CI instead |

Suggested shape: `invalidated_when: Mapping[str, Threshold]`, keyed by a name that appears in the record's own `produces`. Three of the eight happen to be readable as readiness and are encoded there; the other five are prose only.

### F3 — `requires` cannot express a direction, a range, or two bounds on one metric

- **Direction.** Every key is read as a floor. `B:73`'s flip rate and `B:248`'s CI ratio are **upper** bounds — encoding them in `requires` would invert their meaning, so they are not encoded.
- **Range.** `B:73` is "10–15%", `B:140` is "50–100", `A:146` is "150–200". One number per key cannot hold a range, so by S10's policy all three are null.
- **Two bounds, one metric.** A4's κ needs 0.6 to trust and 0.8 to gate. Worked around in *key names*, which is a naming trick, not a representation.

Suggested shape: a frozen `Threshold(op, low, high)` value type in place of the bare scalar. Note that `requires`'s type **already** disagrees with `CLAUDE.md` §6 — §6 says `Mapping[str, int | bool]`, `schema.py` says `int | float | bool` because the corpus has float thresholds (raised at EL-107 and still open). Whatever is decided here, §6's row needs an edit.

### F4 — No `wraps`/`modifies` edge, and `conflicts_with` has no artifact scope

Two faces of one gap.

- **Wrapper records.** A7 "wraps all of the above" (`A:18`) and B7 changes the resampling unit of B1, B3 and B6 alike (`B:209` "clusters if they're grouped (B7)", `B:284` "resample GROUPS for **every CI below**"). Neither replaces the records it wraps; both modify them. A7's relationship is **not encoded at all** — there is no field for it. B7's is encoded as `conflicts_with: [B6_bootstrap_ci]`, which is the nearest available edge and not the right one: it is justified by B6's own explicit handoff at `B:209`, but it says "replaces" where the corpus says "changes the unit of".
- **Scope.** The A1→A4 edge is correct about artifacts and wrong about records — fully written up in §3 above. B7→B6 has the same shape plus a second condition the schema cannot hold (`B:248`'s 1.5× ratio, which decides *which* CI to report).

Suggested shape: a `modifies: tuple[str, ...]` edge distinct from `conflicts_with`, and some way for an edge to name the artifact or situation it is scoped to. The second is the larger design question and probably belongs with the planner's step 5, not the record schema.

---

## 6. One change was required, and made

**`integrity.py` rule 4 is now scoped to section A.** This is the only change to code behaviour in this stage, and it needs ratification.

Rule 4 was "all-or-nothing over every grader": silent while no grader carries a rung, firing for every unrunged grader as soon as one does. That form survived only while *no* grader had a rung. S13 assigns A1 rung 1, at which point the rule fires on **`B2_pairwise_preference`** — a `grader` in section B that the corpus never places on the ladder. `TASKS.md` carried this as the open ruling "Rule 4's residual", and `integrity.py`'s own docstring already called B2 a "permanently unrunged grader".

The stage's done-when is `check_integrity() == []`, so it had three ways out and two are forbidden:

- **Invent rung 4 for B2.** B2 *is* an LLM judge and would sit plausibly at the judge tier — but the ladder is section A's own (`A:11`–`A:18`) and the corpus never places B2 on it, so the rung would be a number no source states. Forbidden by §3.
- **Retype B2 to `metric`.** S10 considered and rejected this on §6's own test ("a grader renders a verdict on an artifact") and recorded B2 as "the record that shows a grader can exist with no rung on section A's ladder". Retyping a record to silence a checker is the workaround §7.5 forbids.
- **Narrow the rule to what the corpus states.** Taken.

The ladder belongs to section A. `A:11`–`A:18` is the only place the corpus draws one and `EL-004` fixes its depth at "five rungs plus a wrapper", so rule 4 now asks for a rung only from **section-A graders**. This is the same kind of narrowing the module docstring already describes making once, for the same reason: the strict form "asserted something `CLAUDE.md` §6 never says".

**What it deliberately does not assert:** that a grader outside section A may *not* carry a rung. §6 states no such prohibition and inventing one would repeat the over-reach. Two new tests pin both halves — `test_a_grader_outside_section_a_needs_no_rung` and `test_a_runged_grader_outside_section_a_does_not_start_the_ladder`.

**If this is overruled,** the fallback is to rung B2 at 4 and record it as an EL decision with the reasoning, since it cannot be sourced. I would not recommend it: it fabricates a methodology claim to satisfy a checker.

Two test-level consequences, both mechanical: the rule-4 message now says "other section-A graders", and `_messy_registry` needed a section-A grader (`A2`, rung 2) to start the ladder, because `B1`'s rung no longer starts anything.

---

## 7. `TASKS.md` corrections

- **S13's "6 distilled" is gone.** The ticket asked for this in the same diff; the working tree had **already** corrected it before this stage ran — line 125 reads "There is no rung 6: decision `EL-004` removed the distilled rung, and `schema.py` now rejects it". Verified, not re-done. The same line's "~25" **was** stale and is now corrected to the verbatim bound (§4a).
- `integrity.py`'s "EL-113 assigning five rungs out of six" was the remaining six-rung phrasing anywhere in the repo. Rewritten; `grep -rn "out of six"` is now empty.
- S9's rule list, its rule-4 note, and its "five unguarded invariants" (now four) updated for §6's change and for A3/A5 sharing rung 3.
- S13 marked `[x]` with its rulings; "Next action" advanced to S14, with the resolved and carried-forward rulings separated.

---

## 8. Nothing else to flag

- **No source row could not be represented.** All 14 A and B rows carry their deep-dive content; what could not be represented is numbers and edge *shapes*, listed in §4c and §5.
- **No vocabulary gap.** Every trigger and tool needed by A and B already exists in `Situation` and `Tool`. One near-miss: A7's tier-1 "small fine-tuned classifier" (`A:257`) has no `Tool` member; `llm_api` is the nearest and is not the same capability. Recorded in A7's notes, not added — a fine-tuned classifier is arguably a capability by `EL-002`'s test, and that is S14+'s call if another section needs it.
- **`gates` is confirmed, not re-derived.** S10 derived it with no lookup column to copy. The deep dives corroborate all 14: A1 `A:51` "Execution became the gating metric"; A2 `A:77` "blocks launch"; A5 `A:186` "gate the release by themselves"; A6 `A:229` "Launch was held"; A4 `A:146` "before it gates a release"; B1–B7 `B:301` "Winner declared only if the CI of the DIFFERENCE excludes 0". A7 stays `false` — an operating posture, no verdict. `analysis_cost` and `capture_cost` are unchanged; nothing in the deep dives contradicts them.
- **Cross-cutting principles.** `I:34` (principle 1) became the four `conflicts_with` edges (§3). `I:36` (principle 3, "same items on both sides") became `required_signals` on B1, B2 and B3 plus B1's `unlocks` edge into B3, which is the order `B:277` states. `I:35` (principle 2, "a CI on every number") became `companion_checks: [C1_wilson_ci]` on all seven A records — which also partly answers S13's carried ruling that C1 has no faithful situation mapping and must be reached by companion edges. The B statistics deliberately do **not** name C1: they produce intervals of their own, and B2 names `B6_bootstrap_ci` instead because `B:74` prescribes a bootstrap over pairs, not Wilson. C–J still need the same treatment in S14–S17.
