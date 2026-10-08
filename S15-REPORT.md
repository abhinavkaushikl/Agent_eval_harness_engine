# S15 / EL-115 — Enrich E + F from the deep dives

**Status:** complete. 418 passed · `check_integrity()` returns `[]` · `mypy --strict` clean · 73 records · `unlocks` verified acyclic across the whole registry.

**Read:** `knowledge rules/E-when-a-number-looks-wrong.md`, `knowledge rules/F-trusting-your-grader.md`, `AGENT.md` §5, `CLAUDE.md` §4, `TASKS.md` S15 + T36.
**Citations** are `E:<line>` and `F:<line>` against the two deep dives, `A:`/`C:`/`H:` against those files. Every citation in this report and in both record files was re-resolved against the file after writing; the one pointing at a heading is the deliberate record-title reference `F:27`.

---

## 1. What changed

| | E | F |
|---|---|---|
| `source_ref` | → `E-when-a-number-looks-wrong.md § E1` … `§ E8` | → `F-trusting-your-grader.md § F1` … `§ F9` |
| `requires` | 5 of 8 now bounded (§3) | 6 of 9 now bounded (§4) |
| `rule_of_thumb` | all 8 replaced with the corpus's verbatim rules | all 9 |
| `companion_checks` | E1 → E4, E8 → J2 | 8 edges |
| `unlocks` | E2 → I8, E4 → E1, E5 → I8 | 6 edges |
| `required_signals` | all 8 sharpened from each record's "How to do it properly" | all 9 |
| first actions | **all 8 captured verbatim in `extraction_notes`** (§5, finding F6) | F6's captured; the rest are not framed as first actions |

`anti_pattern`, `worked_example` and `domain_scenario` were **not touched**. To guarantee that, both files were patched key-by-key rather than rewritten, and `test_verbatim_fields_match_the_lookup_row` still passes.

---

## 2. The F1 label count

**The corpus says 150–200, four times.** Two of our docs said 50–100, and **F never says 50–100 anywhere** — `grep "50–100"` over the F deep dive returns nothing.

| | Text |
|---|---|
| `F:27` | `# F1 – VALIDATE AGAINST 150–200 HUMAN GOLD LABELS BEFORE USE` *(the record's own title)* |
| `F:30` | "Domain-competent humans label a stratified sample of **150–200** outputs using the same rubric the judge uses." |
| `F:335` | decision flow: "Is the LLM judge validated on **150–200** gold labels? (F1)" |
| `F:14` | calibration stack, level 1: "Judge validation · **150–200** gold labels; κ + per-class P/R (F1, F2)" |

| doc | claim | verdict | fix |
|---|---|---|---|
| **`TASKS.md` S15** | "calibration 50–100 labels" | **wrong** | rewritten with the four citations, and with what the real 50s are |
| **`TASKS.md` T36.1** | "Collect 50–100 human labels" | **wrong**, and it ships — T36 is the runtime judge gate | now "Collect **150–200** human gold labels, with **at least 50 fail cases**" |
| `CLAUDE.md` §4 | "150–200 gold labels" | ✅ already correct | none |
| `TASKS.md` line 112 | lists "F1 150–200 gold labels" among ranges left empty | ✅ correct, and **contradicts line 152** in the same file | line 152 fixed; 112 stands |

### Where "50–100" actually comes from

Not from F. Two other records state it, and both are genuine:

- **`A:143`** — A4's rubric design: "Read **50–100** real outputs, tag what goes wrong, and turn the 4–8 most frequent failure types into criteria." An *error-analysis* sample.
- **`H:226`, `H:232`** — H7's trace review: "You read **50–100** failed traces…", "Sample **50–100** failures at random." A *trace* count. `TASKS.md` line 112 already lists "H7 50–100 traces" correctly, and S16 owns it.

So this is the **second** figure this project has traced to cross-contamination between records. S14 found the "3–5 runs noise floor" was E4's A/A figure quoted under C3's name. Same failure mode, different pair. Both are now noted in `TASKS.md`'s next-action block so S16 does not "fix" H7's genuine 50–100.

### What *is* recorded, and why it is the better gate

150–200 is a **range**, so by the policy S10 set it stays out of `requires` and sits verbatim in `rule_of_thumb`. **F1's own single bound goes in instead:**

```
requires: {fail_cases: 50}      ← F:36 "Stratify the sample: include enough 'fail' cases,
                                   at least 50, even if that means over-sampling from
                                   known failures."
```

`F:33` explains why this is the more useful readiness gate of the two: a judge "can be 84% accurate overall and still **miss half of the bad outputs**" when the sample has too few failures. A gold set of 200 items with 4 failures passes a label-count gate and tells you nothing. The fail-case floor is a hard "at least", stated once, with no range.

**The real 50 in F** is F9's calibration batch — `F:301` "everyone labels the same **50 items**" — an exact figure, a different record and a different purpose. That is recorded as `F9 requires.calibration_items: 50`.

---

## 3. The two numbers that become runtime gates in M4 (T36)

The ticket flagged these as shipping numbers. Both are copied verbatim; **one of them is deliberately `null` in `requires`, and T36 must not read it from there.**

### Cohen's κ — recorded

| key | value | source |
|---|---|---|
| `F2 requires.judge_human_kappa_to_trust` | `0.6` | `F:21` "*κ ≥ 0.6* before using a grader at all"; `F:72` "Use a grader only at 0.6 or above" |
| `F2 requires.judge_human_kappa_to_gate` | `0.8` | `F:21` "*κ ≥ 0.8* before letting it gate a release"; `F:72` "gate releases only at 0.8 or above" |

Stated twice, identically, plus the three bands in the decision flow (`F:337`–`F:339`). The key names match A4's from S13 on purpose: it is the same measurement on the same judge, with F2 producing the number and A4 consuming it. The four-band scale (`F:72`: "below 0.4 poor, 0.4–0.6 moderate, 0.6–0.8 substantial, above 0.8 near-perfect") is verbatim in `rule_of_thumb`.

**Krippendorff's α, the same shape:** `F3 requires.alpha_tentative: 0.667` and `alpha_reliable: 0.8`, from `F:22` and `F:107`, both stated twice.

### The flip-rate ceiling — **`null`, and this is load-bearing**

`F:140`: "**Report the flip rate. Above 10–15%, the judge can't make this comparison reliably.**"

That is **both a range and an upper bound**, and `requires` can hold neither. It takes one number per key and reads every value as a **floor**, so `{flip_rate: 10}` would mean *"needs a flip rate of at least 10%"* — the exact inverse of the rule. Encoding it would not merely lose the bound, it would **invert** it, which is the same failure S14 found for C4's `n < 100`.

So the figure is verbatim in `F4`'s `rule_of_thumb`, alongside `F:136`'s "Position bias flips 10–30% of pairwise verdicts" — kept in the same string precisely so the **observed base rate (10–30%)** and the **decision ceiling (10–15%)** are never confused, since they are adjacent, overlapping and easy to transpose.

> **For whoever builds T36:** κ comes from `F2.requires`. The flip-rate ceiling does **not** exist in `requires` and must be read from `F4.rule_of_thumb` until S13 finding F3 is resolved. A gate that reads `requires` alone will silently have no flip-rate check at all.

---

## 4. E's history requirements

The ticket's point 3. **Done, and the split is the interesting part.**

| record | `requires` | what the history is | source |
|---|---|---|---|
| E1 per-item diff | `{runs: 2}` | two scored runs to diff | `E:31` "every item whose verdict changed between **the two runs**"; `E:37` "make two lists" |
| E4 A/A baseline | `{runs: 3}` ⚠ | repeat runs of one config | `E:140` "Run A/A **3–5 times**" — **interpreted**, see §6 |
| E7 contamination | `{runs: 2}` | original *and* paraphrased set scored | `E:245` "**Compare scores.**" |
| E8 multi-benchmark | `{benchmarks: 3}` | ranks on 3+ benchmarks | `E:278` "Collect ranks on **3+** benchmarks" — confirms S10's lookup read |
| E2 metric–outcome | `{release_history_available: true}` ⚠ | 6–10 releases of score+KPI pairs | `E:74` — range, so a boolean; **interpreted**, see §6 |
| E5 harder set | `{}` | production failures → **a capability** | `E:174`; covered by `required_tools: [production_logs]` |
| E3 length-controlled | `{}` | **none needed** | diagnoses one A-vs-B comparison, not a change over time |
| E6 oracle run | `{}` | **none allowed** | `E:210` "**Run it before running any model.**" |

**Two findings worth stating:**

1. **The history splits into evidence and capability.** Where it is *repeat eval runs*, it is accumulated evidence and belongs in `requires`, so the planner marks the record pending on a first run with a reason. Where it is *production data* (E2's traffic mix, E5's failure mining), it is a **capability** and already lives in `required_tools` as `production_logs`. E2 straddles both: its traffic half is a tool, its release half is evidence. Putting production history in `requires` would double-encode what the capability check already handles.

2. **"Most" E records need history, not all — and E6's exception is a positive statement.** `E:210` says the oracle runs *before any model*, so E6 **must** fire at n = 1; any readiness bound there would be wrong. E3 likewise needs no history. Recording this so a later stage does not "complete" these two by inventing bounds.

---

## 5. Schema findings

S13 raised F1–F4, S14 raised F5. One new one.

### F6 — a diagnostic record has no field for its first action ← *new*

The ticket asked for every E record's first action, and said to report it if the schema has no home. **It has none.**

Section E is organised by symptom and its single most actionable content is the first check per symptom. The deep dive states it twice for each record — once in the symptom box (`E:11`–`E:18`) and once as step 1 of "How to do it properly". Nothing holds it:

- `name` holds the **technique** ("Per-item diff, then read the flipped items" — close, but it is the name, not an instruction, and `E6`'s name is "Oracle run: execute a known-correct solution through the harness first" while its first action is "Build an oracle for every new eval").
- `rule_of_thumb` is defined as "any stated formula, verbatim" — "do this first" is not a formula, and for E1/E4/E7 the field is already occupied by the section's three genuine rules of thumb (`E:22`–`E:24`).
- `required_signals` are preconditions, not actions.

All eight are captured verbatim in `extraction_notes`, where a human can read them and the planner cannot:

| record | first check (`E:11`–`18`) | step 1 |
|---|---|---|
| E1 | "per-item diff, read the flips" | `E:37` "Diff at item level: make two lists, newly passing and newly failing." |
| E2 | "eval-vs-traffic mix, metric↔KPI link" | `E:72` "Tabulate the slice mix … and of 30 days of traffic side by side." |
| E3 | "length-controlled win rate" | `E:106` "Log the token count of every output in every eval run." |
| E4 | "A/A noise band" | `E:140` "Run A/A 3–5 times and compute the SD. The noise band is ±2 SD." |
| E5 | "harder set from real failures" | `E:174` "Mine production failures: escalations, thumbs-down, human corrections, re-asks." |
| E6 | "oracle run through the harness" | `E:209` "Build an oracle for every new eval…" |
| E7 | "paraphrase / contamination check" | `E:243` "Paraphrase 200–300 items, keeping the answers identical…" |
| E8 | "3+ benchmarks + your own set" | `E:278` "Collect ranks on 3+ benchmarks relevant to your task type." |

**Proposal:** `first_action: str | None`, verbatim from the source, non-null for diagnostics. Cheaper than finding F5's `prohibits` — it is prose, not a reference, so nothing has to resolve — but it is still a 23rd required field touching all 73 files, so it wants the same ruling. **Not implemented**, per `CLAUDE.md` §7.5.

### Earlier findings, with this stage's new instances

- **F3 (`requires` has no direction or range)** — hit **four** more times, three in F alone: F2's two κ bounds and F3's two α bounds (two keys for one metric, the condition encoded in key *names*), F9's "at least 0.6 (at least 0.7 for high-stakes work)" (a second bound conditioned on stakes), and **F4's flip-rate ceiling**, where encoding it would invert the rule (§3). This finding now has instances in every enriched section.
- **F5 (no field naming what a constraint forbids)** — **F5 the record is the worst case yet.** What it forbids is a *configuration* — a judge sharing a model family with a candidate — not a metric name. So even the `prohibits: tuple[str, ...]` proposal, sized for D1's "accuracy", would not hold it cleanly. Worth weighing before that proposal is ratified.
- **F4 (no `wraps`/`modifies` edge)** — gained a concrete cost. `F:284` points F8 at F9 ("They went to the codebook (F9)") when majority voting cannot fix consistent errors, but F9 already unlocks F1 which unlocks F8, so writing that edge would make `unlocks` **cyclic** — and `integrity.py` does not check for cycles. The pointer is in `extraction_notes` instead. One edge type is doing duty for both *ordering* and *remediation*, and they run in opposite directions.
- **F2 (no field for a trust bar on a produced metric)** — gained E2's "r below about 0.3" (`E:74`), F3's "removing one person raises α by more than 0.1" (`F:108`), F6's 75% histogram mass (`F:207`), F7's "r = 0.91 between dimensions" (`F:251`), F4's 60/40 lean (`F:142`).

---

## 6. Interpreted thresholds — **FLAGGED FOR HUMAN REVIEW**

Two, both in E, both about history.

### 1. `E4 requires.runs: 3` — and it **overturns S10's call on this record**

`E:140` says "Run A/A **3–5 times**". A range, and not phrased as "at least". S10 left `requires` empty and said so explicitly in the old `extraction_notes`. S15 records `{runs: 3}`, the lower end read as the floor.

Why, rather than following the range policy:

- **An SD cannot be computed from one run.** E4 *is* the noise-floor record; an empty `requires` lets the planner fire it on a single run and report a band computed from nothing. That is the precise dishonesty this project exists to prevent, and it is worse than the range-policy violation.
- **`C:103` states 3 independently as a hard floor for the lighter use**: "Run k = 5 for decisions and **k = 3 for daily iteration**." E4 is the lighter use — measuring a band, not deciding — so 3 is anchored outside E4's own range, the same way D5's 50 was anchored by D6's.

*If overruled:* `requires` returns to `{}` and the n = 1 problem returns with it. There is no third option that avoids both.

### 2. `E2 requires.release_history_available: true`

`E:74` needs "your last **6–10** releases" of score-and-KPI pairs — a range, so the count is not copied. But the record is meaningless without release history, so the precondition is carried as a boolean. Same prose-to-boolean move S13 flagged for B5 and B7.

*If overruled:* E2 fires on the first release, when there is no correlation to compute.

**Everything else in E and F is verbatim or null.** Ranges deliberately left out: `E:243` 200–300 paraphrased items, `E:279` 200–300 internal set, `E:108` 50–100 spot-check pairs, `F:30` 150–200 gold labels, `F:105` 20–30% overlap, `F:201` 4–8 checks, `F:239` 1–2 examples, `F:268` 3–5 error types, `F:269` 6–10 examples, `F:272` "about 10 examples".

---

## 7. The two edges the ticket asked for

### Judge score ⇔ length bias — **three records now name E3**

`AGENT.md` §5: "Any judge score is reported with output length | Length bias companion". The edge is written on the **judge** records, not on E3, because `companion_checks` is directional and the judge is what pulls E3 in.

| record | authority |
|---|---|
| `A4_judge_binary_criteria` | S13, on `AGENT.md` §5 |
| `B2_pairwise_preference` | S13, on its **own source line** — `B:75` "Check whether length explains the win **(see Section E3)** before announcing it" |
| `F4_position_swap_consistency` | **S15**, on `AGENT.md` §5 — F4 produces a win rate from a judge, and §5 admits no exception |

F4's edge rests on §5 rather than on a line in F. The ticket permits §5 for *finding a missed edge* but not as a source for a number, which is exactly how it was used — the edge carries no figure.

### Cross-family constraint — **confirmed, not changed**

`F5_cross_family_panel` was already typed `constraint` with `required_tools: [llm_api_cross_family]` from S11, and the deep dive bears both out:

- **Reason** — `F:170`: "**Self-preference bias inflates results for the judge's own model family.** Judges prefer outputs whose style, phrasing and structure resemble their own."
- **Prohibition** — `F:191`: "Using one vendor's model to judge a contest that includes that vendor's model."
- `AGENT.md` §5: "Never same-family judging | Self-preference bias".

Added this stage: `requires {judge_families: 3}` from `F:167` ("three judges from different model families (vendors)") and `F:173` ("Choose judges from three different vendors"), both verbatim; and `companion_checks: [F1_gold_label_validation]` from `F:174` ("Validate each judge on the gold set (F1) and exclude any below κ 0.6").

Also verified against the loaded registry, since the ticket asked: F1, F2, F3, F8 and F9 all carry `human_labels`; F3 triggers on `multiple_annotators`; F9 on `annotators_disagree`. All four were already correct from S11.

---

## 8. The calibration stack as F's edge authority

`F:11`–`F:15` is explicitly ordered and explicitly directional — "**fix from the bottom up**" — so it is F's `unlocks` authority the way D's numbered pipeline box was for section D:

```
4  Judge accuracy boosters   few-shot from disagreements, majority-of-3  (F8)
3  Judge bias controls       position swap, cross-family panel           (F4, F5)
2  Judge design              binary criteria, one call per criterion     (F6, F7)
1  Judge validation          150–200 gold labels; κ + per-class P/R      (F1, F2)
0  Human gold quality        codebook, calibration rounds; κ / α         (F9, F3)
```

`F:17` states the hard precondition at the bottom, in the strongest terms the corpus uses anywhere: "**Human–human agreement is the ceiling. No judge can be validated above it.**" That is why `F9 unlocks F1` and why F9's `gates` is `absolute`.

**Two deliberate restraints.** The level transitions were *not* mechanically expanded into four edges apiece — only edges the corpus states in words are written. And the "validate each X against…" relations are `companion_checks` pointing **down** the stack, which is how the source phrases them (`F:174`, `F:209`, `F:240`, `F:270`) and which keeps `unlocks` **acyclic**. I verified that across all 73 records: 19 `unlocks` edges, no cycles.

The resulting F edges, each with its line:

| edge | kind | source |
|---|---|---|
| F9 → F1 | unlocks | `F:17`, `F:297` — humans are the ceiling |
| F9 → F8 | unlocks | `F:304` "Give the codebook to the judge as well. Its rulings make good few-shot material (F8)" |
| F1 → F8 | unlocks | `F:47` "After adding violation-specific few-shot examples (F8), recall on the held-out 60 reached 88%" |
| F2 → F9, F3 → F9 | unlocks | `F:333` "κ < 0.6 or α < 0.667 → calibration rounds + codebook (F9). STOP until fixed." |
| F4 → F6, F4 → F7 | unlocks | `F:140` "Sharpen the criteria or switch to per-criterion binary judging", carried out at `F:154` |
| **F6 → A4** | unlocks | `F:201` "(The rubric design is covered in Section A4. This subsection covers the diagnosis.)" — the only F-to-A edge in the registry |
| F1 → F2 | companion | `F:336` "Report κ AND per-class recall on 'fail' (F2)" |
| F2 → B6 | companion | `F:74` "Bootstrap κ (Section B6)" |
| F5 → F1, F6 → F2, F7 → F2, F8 → F1 | companion | `F:174`, `F:209`, `F:240`, `F:270` |
| F9 → F2, F9 → F3 | companion | `F:300` "Measure the starting agreement (κ or α)" |

And E's three, which all point **out** of the section at the remedy: `E2 → I8` and `E5 → I8` from `E:75` ("Refresh the eval set from recent logs every quarter (see Section I8)") — E5's resolves the cross-reference S11 left in prose — and `E8 → J2` from `E:279` ("Add your own 200–300 item internal set (Section J)"). Plus `E4 → E1` from `E:143` ("If a move is outside the band, diff the provenance first, then do the per-item diff (E1)").

---

## 9. Smaller things, recorded so they are not silent

- **A second corpus-internal disagreement.** `E:279` tells you to add "your own **200–300** item internal set (Section J)", and J2 — the own-data eval record it must mean — is titled "FULL DOMAIN EVAL (**300–500** ITEMS)". Two rows, two sizes, same set. The edge is written and the figure is not recorded (it is a range either way). Left as found, like S14's C2 905-vs-920 discrepancy. S16/S17 should expect more of these.
- **`AGENT.md` §5 audited for missed edges**, as the ticket directed. Of the fourteen non-negotiables, the E/F-relevant ones are now all encoded or explicitly reported: *never same-family judging* → F5 ✓; *any judge score with output length* → three records ✓; *never accuracy on a rare class* → D1 (S14) ✓; *execution beats judging* → four edges (S13) ✓; *precision only at a stated recall level* → D2/D3 (S14) ✓; *violation rate with over-refusal rate* → **still not encodable**, no such record exists (S14 §7). *Within-noise delta is never an improvement* is served by E4 and C3 but is **not** enforced by either record — see the next point.
- **E4's `gates` stays `false`** although `E:306`'s decision flow says "move inside band? → STOP. It's noise." What E4 stops is an *investigation*, not a release, and `gates` describes blocking a change. So `AGENT.md` §5's "within-noise delta is never an improvement" is enforced by whoever reads the band, not by a record. If that rule is meant to be machine-enforced, it needs a mechanism this schema does not have.
- **E6's `required_tools` is empty, and that is the weaker call in E.** Both scenarios are agent sandboxes and would need `sandbox`, but the "returns the gold answer" form of an oracle needs nothing, and the `Tool` enum has no way to say "whatever the system under test needs". Noted rather than resolved.
- **F7 and F8's vocabulary gap is unchanged by the deep dive.** "Judge grades the wrong dimension" and "Want better judge accuracy" are both "the judge I already built is not good enough", which no `grader_trust` member names. Both stay mapped to `new_judge_built`, so F1, F7 and F8 all fire together for a session that has just built a judge — defensible for the planner, still wrong as vocabulary. First reported in S11; the deep dives gave no new basis to change it.
- **`produces` left alone throughout**, as in S13 and S14, since it is outside the enrichment field list. F2 would gain the per-class bands; E4 would gain the provenance diff.
- **`gates` confirmed, not re-derived.** E's eight are all `false` (a diagnostic is reported; the decision it informs is gated by whatever produced the number). F1, F5 and F9 are `absolute` — F1 from its title's "before use", F9 from `F:17`'s ceiling, F5 from the prohibition. F2 and F3 are `statistical`. F4, F6, F7 and F8 are `false`.
