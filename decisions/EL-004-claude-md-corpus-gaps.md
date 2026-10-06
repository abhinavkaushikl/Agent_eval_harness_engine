# EL-004 — `CLAUDE.md` section-coverage claims that the corpus does not support

## Decision

`CLAUDE.md §4` and `§6` are corrected to match the corpus. Six topics are dropped outright, seven are renamed to the corpus's own name, and five are reassigned to the section that actually teaches them. Nothing is added to `knowledge rules/`.

The **distilled grading rung does not exist in the corpus**, so `ladder_priority` now tops out at 5, not 6. That is a schema-affecting change and is flagged as such below, per `CLAUDE.md §7` rule 5.

## Status

Applied — `CLAUDE.md:90-99` and `CLAUDE.md:169` edited — 2026-10-06.

The ticket offered two outs: add the missing topics to the knowledge files, or drop them from `CLAUDE.md`. Add was available only where the concept is already in the corpus under a different name and the edit is a rename. Six topics failed that bar and were dropped. Authoring the methodology instead would have meant inventing thresholds, which `CLAUDE.md §3` forbids.

## Method

Every topic named in the `§4` coverage table was grepped case-insensitively over `knowledge rules/`, then checked against the owning section's technique headers (`grep -n "^# <L>[0-9]"`) and its decision flow. A phrase-level miss was not treated as absence: each one was re-checked for the concept under another name before a Drop was recorded. All ten sections' headers were enumerated, so the audit is against the corpus's actual technique list (A1–A7, B1–B7, C1–C6, D1–D6, E1–E8, F1–F9, G1–G8, H1–H8, I1–I9, J1–J5) rather than against the table's own wording.

## Audit

Verdicts: **Present** · **Mis-sectioned** (concept is in the corpus, in a different section) · **Rename** (corpus teaches it under another name) · **Drop** (absent).

### Section A — grading ladder

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| execution | A | `A:11` "It runs (code, SQL, API call) → A1 Execution-based grading" | Present |
| end-state | A | `A:12` "It changes a system (agent action) → A2 End-state verification" | Present |
| deterministic | A | `A:13` A3 normalised exact match; `A:14` A5 schema + field-level, both "₹0, deterministic" | Present |
| judge | A | `A:15` "It's open-ended text → A4 LLM judge, binary rubric" | Present |
| human | A | `A:16` "It's high-stakes and final → A6 Double-annotated expert review" | Present |
| **distilled** | A | **NONE** — `"distill"` returns zero hits across all twelve corpus files | **Drop** |

The corpus ladder is five rungs plus a wrapper. `A:18` places A7 outside the ladder: "It's live production traffic → A7 Tiered online scoring (**wraps all of the above**)".

### Section B — comparison

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| paired items | B | `B:26` "# B1 – PAIRED EVALUATION + PAIRED BOOTSTRAP CI" | Present |
| win rate | B | `B:74` "**Report the win rate with a CI** from a bootstrap over pairs, and state the tie rate." | Present |
| McNemar | B | `B:97` "# B3 – McNEMAR'S TEST" | Present |
| Bradley-Terry | B | `B:131` "# B4 – BRADLEY–TERRY (OR ELO) WITH BOOTSTRAP CIs" | Present |
| bootstrap | B | `B:200` "# B6 – BOOTSTRAP CONFIDENCE INTERVAL FOR \"WEIRD\" METRICS" | Present |
| cluster bootstrap | B | `B:235` "# B7 – CLUSTER BOOTSTRAP" | Present |

B5 was unlisted in `§4` and has been added to the B row — see the C section below for why.

### Section C — statistics

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| CI ≈ 100/√n | C | `B:22` "**Rule of thumb:** *the worst-case 95% margin on a percentage is about 100/√n points.*" — in **B5**, not C | **Mis-sectioned → B** |
| power n = 16/gap² | C | `C:19` "*Sample size per arm ≈ 16·p(1−p) / δ²* (α = 0.05, 80% power)"; `C:69` "**Unpaired:** n ≈ 16·p(1−p)/δ² per arm." | **Rename → `n ≈ 16·p(1−p)/δ²`** |
| noise floor | C | `C:97` "For stochastic systems … "; `E:137` "**Without a noise floor, you chase ghosts**" | Present |
| Wilson | C | `C:25` "# C1 – REPORT A 95% CI ON EVERY SCORE (WILSON FOR PROPORTIONS)" | Present |
| multiple comparisons | C | `C:163` "# C5 – MULTIPLE-COMPARISON CORRECTION" | Present |
| permutation | C | `C:198` "# C6 – PERMUTATION TEST" | Present |

**The power formula as `§4` stated it was wrong, not merely differently worded.** The corpus formula carries a `p(1−p)` factor that `§4`'s `16/gap²` dropped; at p = 0.5 the two differ by 4×. This is the one correction here that would have produced a wrong number in a record, so it is a Rename to the verbatim corpus form rather than a cosmetic fix. C4 was also unlisted and has been added.

### Section D — rare events

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| recall not accuracy | D | `D:26` "# D1 – PRECISION–RECALL CURVE AND PR-AUC, NEVER ACCURACY" | Present |
| **precision@fixed-recall** | D | `D:60` "# D2 – PRECISION AT A FIXED **FLOOR** (OR F0.5)"; master lookup `:55` "Require precision ≥ X, then maximise recall under that constraint" | **Rename → "precision at a fixed floor"** |
| PR curves | D | `D:26` D1; `D:94` "# D3 – AVERAGE PRECISION (PR-AUC) FOR THRESHOLD-FREE COMPARISON" | Present |
| **capacity thresholds** | D | **No technique.** The word appears once, inside D1's worked example: `D:45` "At the operating point matching the team's capacity (200 alerts a day)". D's threshold technique is cost-based: `D:127` "# D4 – COST-BASED THRESHOLD ON VALIDATION, REPORTED ON TEST" | **Drop** (D4 named instead) |
| violation | D | `D:164` "# D5 – TARGETED RED-TEAM SET + ATTACK SUCCESS RATE PER CATEGORY" | **Rename → "red-team ASR per category"** |
| **over-refusal** | D | **NONE in D.** Present in **G6**: `G:195` "Report the false-answer rate on unanswerables *and* the **over-abstention rate** on answerables. Refusing everything scores 0% on the first and fails on the second" | **Mis-sectioned → G** |
| **worst slice** | D | **NONE.** `"slice"` returns **zero hits in `D-rare-events.md`**. Slices appear in C1 (`C:37` "**Put CIs on slices too.**"), C5 and J2 — never as a worst-slice technique | **Drop** |

On over-refusal: the concept survives, but as G6's over-abstention, scoped to RAG answerables rather than to safety over-blocking. `§4`'s G row already covered G6 as "unanswerable", so the G row now names both halves explicitly and the D row loses the claim. D6 was unlisted and has been added.

### Section E — diagnostics

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| **reward hacking** | E | **NONE.** `"reward hack"` zero hits. The single `"hacking"` hit is a different concept: `C:72` "Collecting until the result looks significant is **p-hacking**" | **Drop** |
| criterion validity | E | `E:63` "# E2 – SCORE IMPROVED BUT USERS DIDN'T NOTICE → DISTRIBUTION + **METRIC–OUTCOME CHECK**" | **Rename → "metric–outcome check"** |
| length bias | E | `E:97` "# E3 – SCORE IMPROVED AND ANSWERS GOT LONGER → **LENGTH-CONTROLLED WIN RATE**" | **Rename → "length-controlled win rate"** |
| silent model update | E | `I:139` "**Providers update model aliases silently**, so behaviour can shift without any code change" → I4 | **Mis-sectioned → I** |
| ceiling | E | `E:165` "# E5 – ALL MODELS SCORE 90%+ → BUILD A HARDER SET" | Present |
| floor | E | `E:200` "# E6 – NOTHING COMPLETES AT ALL → ORACLE RUN THROUGH THE HARNESS" | Present |
| contamination | E | `E:234` "# E7 – PUBLIC BENCHMARK SCORE LOOKS TOO GOOD → CONTAMINATION CHECK" | Present |
| **Goodhart** | E | **NONE.** Zero hits. E8 is `E:269` "# E8 – ONE MODEL DOMINATES ONE BENCHMARK ONLY → 3+ BENCHMARKS + YOUR OWN SET" | **Drop** |

`p-hacking` is not reward hacking under another name: it is a stopping-rule failure in statistics, already covered by `§4`'s C row, whereas reward hacking is a model exploiting the metric. The grep hit is a word collision, not the concept. E1 (per-item diff, reassigned out of the I row) and E4 (A/A baseline) were unlisted and have been added, which makes the E row E1–E8 in order.

### Section F — judge trust

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| calibration | F | `F:9` "THE CALIBRATION STACK (fix from the bottom up)"; `F:291` "# F9 – HUMAN LABELLERS DISAGREE → FIX THE RUBRIC FIRST" | Present |
| Cohen's kappa | F | `F:62` "# F2 – COHEN'S κ + PER-CLASS PRECISION/RECALL OF THE JUDGE" | Present |
| **Fleiss' kappa** | F | **NONE.** Zero hits. The corpus uses α for 3+ raters: `F:96` "# F3 – KRIPPENDORFF'S α FOR MORE THAN TWO LABELLERS", chosen because it handles "any number of raters, missing labels" (master lookup `:84`) | **Drop** |
| Krippendorff's | F | `F:96` F3; `F:22` "*Krippendorff's α ≥ 0.667* for tentative conclusions and *≥ 0.8* for reliable ones." | Present |
| position bias | F | `F:130` "# F4 – RUN BOTH ORDERS; COUNT ONLY CONSISTENT VERDICTS, TREAT FLIPS AS TIES" | Present |
| cross-family | F | `F:164` "# F5 – CROSS-FAMILY JUDGE PANEL" | Present |
| named categories | F | `F:201` "You replace a 1–10 or 1–5 quality scale with **4–8 yes/no checks**, each for one observable property, and sum them." (F6) | **Rename → "binary criteria"** |
| single-criterion | F | `F:228` "# F7 – ONE JUDGE CALL PER CRITERION, WITH FEW-SHOT EXAMPLES" | Present |
| reasoning-first | F | **NONE in F.** One hit, in A4: `A:145` "Give each criterion its own judge call …, **with reasoning first, then PASS/FAIL**" | **Mis-sectioned → A** |

Fleiss' κ is a Drop rather than a Rename to α: both are named coefficients for 3+ raters, and the corpus deliberately teaches α. Dropping the word leaves "Cohen's κ / Krippendorff's α", which is what the corpus actually contains. `"categor"` in `F` returns only F3's distance-metric note (`F:106`), so "named categories" matched no F technique; F6 is the technique in that slot, and "binary criteria" is its own wording. F1 and F8 were unlisted and have been added.

### Section G — RAG

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| recall@k | G | `G:24` "# G1 – COMPONENT-WISE EVAL: RETRIEVAL RECALL@k + GENERATION WITH GOLD CONTEXT" | Present |
| perfect-context ceiling | G | `G:59` "# G2 – **ORACLE-CONTEXT TEST** + PER-FAILURE STAGE ATTRIBUTION"; `G:62` "You replace retrieval with the gold passages (the oracle context) to find the generator's ceiling" | **Rename → "oracle-context test"** |
| faithfulness | G | `G:90` "# G3 – FAITHFULNESS: CLAIM DECOMPOSITION + NLI ENTAILMENT" | Present |
| nDCG | G | `G:124` "# G4 – nDCG@10 WITH GRADED RELEVANCE" | Present |
| MRR | G | `G:155` "# G5 – MRR AND HIT@k WHEN ONE RIGHT DOCUMENT EXISTS" | Present |
| unanswerable | G | `G:185` "# G6 – UNANSWERABLE-QUESTION SET: FALSE-ANSWER RATE + ABSTENTION PRECISION" | Present |
| noise robustness | G | `G:219` "# G7 – CONTEXT PRECISION + DISTRACTOR-INJECTION ROBUSTNESS" | Present |
| attribution | G | `G:250` "# G8 – CITATION PRECISION AND CITATION RECALL" | Present |

### Section H — agents

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| resettable env | H | `H:27` "# H1 – SANDBOXED, RESETTABLE ENVIRONMENT + FULL TRAJECTORY LOGGING" | Present |
| end-state verification | H | `H:62` "# H2 – OUTCOME-BASED SUCCESS ON END STATE" | Present |
| pass^k | H | `H:93` "# H3 – pass^k (ALL k TRIALS SUCCEED), NOT pass@k" | Present |
| cost/success | H | `H:127` "# H4 – COST PER SUCCESSFUL TASK" | Present |
| step compounding | H | `H:21` "*Compounding:* task success ≈ (per-step success)^steps"; `H:158` "# H5 – MILESTONE CHECKPOINTS + STEP-LEVEL FAILURE LOCALISATION" | Present |
| injection | H | `H:189` "# H6 – PROMPT-INJECTION TEST SUITE: ASR ALONGSIDE TASK UTILITY" | Present |
| trajectory | H | `H:223` "# H7 – TRAJECTORY REVIEW WITH OPEN CODING → FAILURE TAXONOMY" | Present |
| infra-vs-capability | H | `H:255` "# H8 – k ≥ 5 TRIALS PER TASK → ALWAYS / FLAKY / NEVER" | Present |

Section H's row was accurate as written and is unchanged.

### Section I — production

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| CI gates | I | `I:30` "# I1 – CI REGRESSION GATE: FIXED SUITE + MUST-PASS GOLDEN SET" | Present |
| statistical gates | I | `I:65` "# I2 – SPLIT DETERMINISTIC TESTS FROM STATISTICAL EVALS; GATE ON A MULTI-RUN MEAN" | Present |
| per-item diff | I | **NONE in I.** It is E1: `E:28` "# E1 – SCORE JUMPED SUDDENLY → PER-ITEM DIFF, THEN READ THE FLIPPED ITEMS" | **Mis-sectioned → E** |
| canary | I | `I:133` "# I4 – PINNED MODEL VERSIONS + DAILY CANARY EVAL WITH DRIFT ALERTS" | Present |
| tiered scoring | I | **NONE in I.** It is A7: master lookup `:19` "**Tiered online scoring**: deterministic checks + a small classifier on 100%, a frontier judge on a 1–2% sample" | **Mis-sectioned → A** |
| business metrics | I | `I:197` "# I6 – BUSINESS OUTCOME METRIC TIED TO THE EVAL + GUARDRAILS" | Present |
| A/B by user | I | `I:231` "# I7 – PRE-REGISTERED ONLINE A/B TEST" | Present |
| failures-as-tests | I | `I:263` "# I8 – EVAL SET FROM STRATIFIED LOGS + PAST FAILURES + ADVERSARIAL ITEMS" | Present |
| shadow mode | I | `I:299` "# I9 – SHADOW MODE → STAGED CANARY WITH AUTO-ROLLBACK" | Present |

I3 (`I:97` "# I3 – ERROR ANALYSIS: SAMPLE 100 FAILURES, OPEN-CODE, COUNT") and I5 (`I:165` "# I5 – SAMPLED ONLINE EVAL: REFERENCE-FREE JUDGE + IMPLICIT SIGNALS") were unlisted and have been added in place of the two reassigned entries.

### Section J — model selection

| Claimed topic | Claimed § | Corpus hits | Verdict |
|---|---|---|---|
| benchmarks as filter | J | `J:33` "# J1 – HARD-CONSTRAINT FILTER → 50-ITEM SMOKE TEST" | Present |
| own-data eval | J | `J:68` "# J2 – FULL DOMAIN EVAL (300–500 ITEMS) WITH PAIRED STATS + HUMAN PAIRWISE ON THE TOP 2" | Present |
| Pareto | J | `J:108` "# J3 – COST–QUALITY PARETO FRONTIER: THE CHEAPEST MODEL WITHIN THE BEST MODEL'S CI" | Present |
| same-harness | J | `J:143` "# J4 – SAME BENCHMARK VERSION, SAME SHOTS/CoT, SAME HARNESS, OR RERUN IT YOURSELF" | Present |
| vendor claims | J | `J:177` "# J5 – REPLICATE VENDOR CLAIMS ON YOUR OWN 100–200 ITEM HELD-OUT SET" | Present |

Section J's row was accurate as written and is unchanged.

## Schema-affecting change: the grading ladder

Flagged per `CLAUDE.md §7` rule 5 rather than renumbered quietly.

`ladder_priority` reserved 6 for a distilled grader. `"distill"` has zero corpus hits, so **no record will ever carry `ladder_priority = 6`**. The field is now documented as 1–5.

Two consequences for S6 and EL-113:

1. **Range.** Any integrity rule on `ladder_priority` must bound it at 1–5. A rule written to allow 6 would permit a value no source can justify.
2. **A7 has no rung, and this is left open.** The corpus places A7 outside the ladder — "wraps all of the above" (`A:18`) — yet A7 renders verdicts, so it reads as a grader, and `CLAUDE.md:169` requires a grader to carry a priority. Assigning it 6 would reintroduce the rung just dropped, under a different name, and the corpus states no ordering for it. This is recorded as an open question rather than resolved here, because resolving it means either inventing an ordering or widening the "None unless type is grader" rule. The `§6` row now says so.

## What the registry will not be able to plan

The shortlist EL-113 needs. For each, no record exists, so `match()` will never return one:

1. **Reward hacking (E).** No record for a model exploiting the metric while the underlying quality falls. The nearest corpus techniques are E2's metric–outcome check and I6's business-outcome guardrails, which detect a metric that stopped tracking value but do not diagnose gaming as a cause.
2. **Goodhart's law (E).** No record, and no general statement that optimising a proxy degrades it.
3. **Fleiss' κ (F).** No record. Three-or-more-rater agreement is served only by Krippendorff's α (F3). A request phrased as "Fleiss" will not match.
4. **A distilled grader (A).** No record, and no sixth ladder rung. A plan can never recommend distilling a judge into a cheaper model.
5. **Safety over-refusal (D).** No record pairing an over-refusal rate with a violation rate. G6's over-abstention is available but is scoped to RAG answerables, so a safety plan will report ASR (D5) with no over-blocking counterpart.
6. **Worst-slice reporting (D).** No record that makes the minimum across slices the headline metric. C1 puts CIs on slices and C5 corrects for checking many, but neither reports the worst.
7. **Capacity-based thresholds (D).** No record. Threshold-setting is cost-based only (D4). An operations team with a fixed review budget expressed in items/day, not rupees, is served only through D2's precision floor.

Items 1, 2 and 4 are the ones most likely to be asked for by name, since they are common eval vocabulary. The registry will be silent on all three, and that silence is correct: the methodology this project codifies does not teach them.

## Consequences

- `CLAUDE.md §4` rows A, B, C, D, E, F, G and I were edited; H and J were already accurate. `§6`'s `ladder_priority` row was edited. The five `Situation` families in `§6` needed no change: the `measurement` family maps one-to-one onto E1–E8, so dropping "reward hacking" and "Goodhart" from the `§4` prose removed no situation.
- Nothing was added to `knowledge rules/`. The corpus is read-only input (`decisions/EL-001-corpus-location.md`) and no verdict here required authoring methodology.
- EL-113 (enrich A and B) is unblocked and is the first stage that would have tripped over the A-row ladder. Section A now lists five rungs plus a wrapper, which is what `A:11-18` shows.
- Six `§4` entries that were *missing* were added while the table was being corrected (B5, C4, D6, E1, E4, F1, F8, I3, I5), so the table now names every technique in the sections it summarises. This was not in the ticket, but a coverage table that under-lists is the same failure mode as one that over-promises.

## Numbers introduced

**Zero.** Every figure now in `§4` is copied verbatim from the corpus, and each is cited above:

| Figure | Source |
|---|---|
| `100/√n` | `B:22` |
| `16·p(1−p)/δ²` | `C:19`, `C:69` |
| `k ≥ 5` runs | `C:94` (C3 header) |
| near `0%` or `100%` | `C:129` (C4 header) |
| `150–200` gold labels | `F:27` (F1 header) |

One figure was **removed** as wrong rather than added: `§4`'s `16/gap²` omitted the `p(1−p)` factor the corpus states. No threshold, sample size or formula was invented, and no value was interpreted from prose — the two Renames that touch numbers (`16·p(1−p)/δ²`, `precision at a fixed floor`) both replace a paraphrase with the source's own words.

## Related

- `decisions/EL-001-corpus-location.md` — the corpus is in-repo and read-only; all line numbers above are against that copy.
- `decisions/EL-003-new-situations.md` — the companion audit of `§6`'s `Situation` vocabulary against the master lookup's situation column. Read together, these two cover both halves of `CLAUDE.md`'s claims about the corpus: which techniques exist, and which situations select them.
