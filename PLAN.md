# PLAN.md — EvalLoop Execution Plan

High-level roadmap: milestones, gates, sequence and critical path. Small, verifiable work items are in `TASKS.md`.

---

## 1. Milestones at a glance

| Week | Milestone | Output |
|---|---|---|
| 1 | **M0 — The Brain** | Registry + planner. *Does situation→technique matching actually work?* |
| 2–3 | **M1 — First Grading** | Grades real code. Catches a real bug. |
| 4 | **M2 — The Session Tool** | It's a tool you can start and use. |
| 5 | **M3 — Honesty Layer** | Its numbers are trustworthy. |
| 6–7 | **M4 — Judge & Second Situation** | Judge + second situation. Architecture validated by reuse. |
| 8+ | **M5 — Reach** | Connectors, languages, situations. |

Every milestone ends in a **gate**. Nothing downstream starts until the gate passes.

---

## 2. Milestone detail

### M0 — The Brain *(no execution; proves the premise)*
| # | Task | Done when | Effort |
|---|---|---|---|
| T0 | Repo scaffold, conventions, test harness | `pytest` runs green on an empty suite | 0.5d |
| T1 | Freeze vocabularies: situations + tools as enums | Enums committed; loader rejects unknown terms | 0.5d |
| T2 | Registry schema + loader + integrity tests | Loads records, validates vocab, rejects dupes/bad refs | 1d |
| T3 | Extract skeleton from master lookup (~70 records) | 70 records load and validate | 1d |
| T4 | Enrich from A–J (thresholds, tools, ladder, examples) | Every record has `source_ref`; thresholds verbatim or null | 2d |
| T5 | Write 20 planner fixtures by hand | 20 (situation, evidence) → expected plan files | 1d |
| T6 | Planner: match → order → readiness-filter → capability-check | All 20 fixtures pass; you agree with all 20 plans | 2d |

🔒 **GATE 0:** Read the 20 generated plans. If you disagree with any, fix before proceeding. *Nothing downstream matters if this is wrong.*

### M1 — First Grading *(code generation, end to end)*
| # | Task | Done when | Effort |
|---|---|---|---|
| T7 | Metric store: JSONL writer/reader, full schema day one | Two runs written, diffed per-case | 1d |
| T8 | Episodic store: SQLite schema + write/query | Situation decisions and reasoning persisted | 1d |
| T9 | Classifier heuristics (Python only) | Correctly labels 10 sample files | 1.5d |
| T10 | Oracle harvester: find existing tests, schemas, type hints | Returns HIGH-confidence oracles from a real repo | 1.5d |
| T11 | Sandbox runner: subprocess + rlimits + timeout + tempdir | Runs a command safely; timeout → INCONCLUSIVE | 1.5d |
| T12 | Execution grader: hidden-test isolation, partial credit, compile/logic split | Catches a deliberately broken function | 2d |
| T13 | Deterministic grader: schema/regex/exact + cascade hook | Validates output shape; cascade stub in place | 1d |
| T14 | LLM client (stdlib HTTP, retry, backoff) + router | One call works; router selects by job | 1d |
| T15 | Test author: isolated generation, confidence tagging | Generates tests from signature only; tags HIGH/LOW correctly | 2d |
| T16 | Statistics module: Wilson, bootstrap, cluster bootstrap, McNemar, permutation, noise floor, power | Unit tests match corpus worked examples | 1d |
| T17 | Markdown report renderer | Readable `summary.md` per run | 0.5d |

🔒 **GATE 1:** Point at a toy repo with a deliberately broken function. It gets caught, with zero instruction from you.

### M2 — The Session Tool
| # | Task | Done when | Effort |
|---|---|---|---|
| T18 | Poller: walk + stat + hash, gitignore-aware | Detects changes in 5k files in < 20 ms | 1d |
| T19 | Event buffer + debouncer | Bursts collapse into single change units | 0.5d |
| T20 | Git state reader | Baseline, staged, committed, branch | 0.5d |
| T21 | AI transcript reader (Claude Code JSONL) | Extracts stated intent from disk | 1d |
| T22 | Coherence detector | Fires on complete units, not mid-edit | 2d |
| T23 | Session orchestrator: start/stop, async worker pool, queue | `evalloop start` → works → `evalloop stop` → report | 2d |
| T24 | Content-hash cache | Unchanged diff never re-evaluated | 0.5d |
| T25 | Local API (stdlib HTTP or asyncio) | `/status` `/results` `/pending` respond | 1d |
| T26 | Dashboard: live HTML + SSE | Updates during a session without refresh | 1.5d |

🔒 **GATE 2:** Click start, work an hour in any editor, get a useful session report.

### M3 — Honesty Layer
| # | Task | Done when | Effort |
|---|---|---|---|
| T27 | Readiness gate + pending queue rendering | Shows "need 25, have 8" with reasons | 1d |
| T28 | Noise floor across repeat runs | Refuses to call a within-noise delta an improvement | 1d |
| T29 | Per-item diff report | Lists flips in both directions | 1d |
| T30 | Diagnostics: E1 jump, E3 length, E5 ceiling, E6 floor | Flags a synthetic reward-hack scenario | 1.5d |
| T31 | Journey ledger + trends | Per-field, per-slice trend lines over runs | 1d |
| T32 | Self-canary | Detects its own degradation on a fixed known-answer set | 1d |

🔒 **GATE 3:** It correctly refuses to report a noise-level change as a win, and catches a planted reward hack.

### M4 — Judge & Second Situation
| # | Task | Effort |
|---|---|---|
| T33 | Judge grader: single-criterion, named categories, reasoning-first | 2d |
| T34 | Cross-family hard assertion in router | 0.5d |
| T35 | Position swap + flip-rate tracking | 1d |
| T36 | Calibration set + Cohen's kappa + `kappa_manual ≥ 0.6` runtime gate | 2d |
| T37 | Summarization situation (faithfulness + length companion) | 2d |

🔒 **GATE 4** *(inferred, not visible in source)*: Summarization is judged end-to-end by a calibrated cross-family judge, reusing M0–M3 components without architectural changes.

### M5 — Reach
| # | Task | Effort |
|---|---|---|
| T38 | MCP client | 3–5d |
| T39 | Connectors: GitHub → DB → Databricks | 2d each |
| T40 | Node language adapter | 1d |
| T41 | CI surface + PR comments | 2d |
| T42 | Extraction situation + perturbation engine | 1w |
| T43 | Agents: resettable env, trace capture, pass^k | 2–3w |

---

## 3. Critical path

```
T1 → T2 → T3 → T4 → T6      (registry → planner: nothing works without this)
               ↓
        T5 (fixtures — write BEFORE T6)
               ↓
T7 → T11 → T12              (storage → sandbox → execution grader: first real value)
               ↓
T18 → T22 → T23             (poller → coherence → orchestrator: makes it a tool)
```

**Parallelizable:** T16 (statistics) and T8 (episodic store) have no dependencies. Do them whenever there's a gap.

---

## 4. Where we start

**T1: freeze the vocabularies.** It takes half a day, and every subsequent record depends on it. Getting it wrong is cheap to fix now and expensive to fix after 70 records exist.

M0 is broken into **23 small stages (S1–S23)** in `TASKS.md`, each focused and verifiable in one sitting.

| Group | Stages | Maps to |
|---|---|---|
| 1 Scaffold | S1–S2 | T0 |
| 2 Vocabularies | S3–S5 | T1 |
| 3 Record format & schema | S6–S9 | T2 |
| 4 Skeleton extraction | S10–S12 | T3 |
| 5 Enrichment | S13–S17 | T4 |
| 6 Fixtures | S18–S19 | T5 |
| 7 Planner | S20–S23 | T6 |

---

## 5. M0 definition of done
- `pytest` green, `mypy --strict` clean
- ~70 records load; integrity check returns nothing
- All 20 fixtures pass
- Sanity queries give sensible answers:
  - summarization → faithfulness, with the length check attached
  - code generation → execution first, judging deprioritised or excluded
  - RAG → retrieval recall ordered before faithfulness
  - rare class → recall ready, accuracy prohibited
  - "what works on a single observation?" → only facts
  - "what needs 200+ samples?" → significance tests, judge agreement
- All 20 rendered plans printed for human review. **That review is the gate.**

---

## 6. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Vocabulary drift (`summarization` vs `text_summary`) | Frozen StrEnums; loader rejects unknown terms; coverage test against verbatim source strings |
| Invented thresholds | `null` rule; enrichment reports anything interpreted from prose |
| Fixtures shaped by code | Fixtures written before the planner; never edited to pass |
| Schema doesn't fit A–J | Enrich one file at a time; expect and raise a schema change after the first two |
| YAML parsing cost (no PyYAML) | Minimal subset parser, or JSON with readability trade-off documented |
| Scope creep into later milestones | CLAUDE.md "Do NOT build" list; no later-milestone dirs |
| Agent grades half-written code | Coherence detector (M2) |
| False "wins" | Noise floor, readiness gates, self-canary (M3) |
