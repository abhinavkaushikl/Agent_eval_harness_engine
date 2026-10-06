# CLAUDE.md — EvalLoop

Guidance for Claude (or any coding agent) working in this repository. Read this first, every session.

---

## 1. What this project is

**EvalLoop** is an autonomous evaluation system, built as a **standalone session tool**.

You click **start** and work however you normally work, in any editor and with any AI assistant. A backend agent observes what you're building, infers the *situation*, and selects the right evaluation techniques from a codified methodology registry. It then generates and runs those evaluations and accumulates evidence. Each statistical check fires **only when there is enough data to be honest**.

> Two clicks per session. Everything else is the agent.
> The developer never writes an eval.

It is deliberately **not** built on existing file-watchers or eval frameworks (no watchdog, no PyYAML, no LangChain-style wrappers). Everything is standalone and stdlib-first.

---

## 2. Current phase

**Milestone 0 — "The Brain"** (registry + planner only).

The library answers one question: *"What should be evaluated here, and what can't be answered yet?"*

Do **NOT** build in this phase:
- execution / sandbox
- file watching / polling
- LLM calls
- statistics implementation
- storage (JSONL / SQLite)
- dashboard or API

Those belong to later milestones (see `PLAN.md`). Do not create `grade/`, `capture/`, `stats/` or any later-milestone directories yet.

---

## 3. Hard constraints (never break these)

| Rule | Detail |
|---|---|
| Python | **3.12+** |
| Dependencies | **Standard library only** in shipped code. `pytest` and `mypy` are dev-only and allowed. NumPy is the only external dependency that may ever be permitted, and it is **not** needed in M0. |
| No PyYAML | Write a minimal parser for the YAML subset we use, or use JSON. State the choice and trade-off in a module docstring. |
| No frameworks | No third-party frameworks or wrappers anywhere in the project. |
| Types | Type hints everywhere. `mypy --strict evalloop/` must exit 0. |
| Tests | `pytest` must exit 0 before any task is called done. |
| Paths | The corpus is the in-repo `knowledge rules/` directory; `EVALLOOP_CORPUS` overrides it. **Never hardcode an absolute user path.** Corpus filenames live only in `tests/conftest.py`. |
| Numbers | **Never invent a number.** Thresholds are copied verbatim from the source or set to `null`. No "reasonable defaults." |
| Stubs | No placeholder modules with bare `pass` bodies beyond `__init__.py`. |

---

## 4. Source corpus (read-only input)

The methodology being codified is versioned **inside this repo**, in one flat directory
(decision `decisions/EL-001-corpus-location.md`). Filenames are lowercase after the section
letter, and there is no subdirectory:

```
knowledge rules/evals-situation-to-technique.md        master lookup — ~70 techniques
                                                       as a table, ten sections A–J
knowledge rules/00-INDEX.md                            index + five cross-cutting principles
knowledge rules/A-choosing-how-to-grade.md
knowledge rules/B-comparing-two-things.md
knowledge rules/C-deciding-whether-a-result-is-real.md
knowledge rules/D-rare-events.md
knowledge rules/E-when-a-number-looks-wrong.md
knowledge rules/F-trusting-your-grader.md
knowledge rules/G-rag-systems.md
knowledge rules/H-agents.md
knowledge rules/I-production.md
knowledge rules/J-choosing-a-model.md
```

`EVALLOOP_CORPUS` still overrides the directory, but it no longer needs to be set: it
defaults to the `knowledge rules` directory resolved relative to the repo root. The
filenames above are declared **once** in code, in `tests/conftest.py`
(`MASTER_LOOKUP`, `INDEX_FILE`, `SECTION_FILES`, `CORPUS_FILES`). Import them from there.
Never write a corpus filename as a literal anywhere else — a single silent mismatch makes
every extraction stage read nothing. A missing or misnamed file **fails** the suite and
names the file; it does not skip.

- **Master lookup** is the skeleton. It is already tabular, with columns `Situation | Use | What it technically is | Why this one | Example`, and has one row per technique.
- **Deep dives** (~3.5k words each) hold the details: thresholds, formulas, orderings, required tools, and a decision flow per section.

### Section coverage
| | Section | Contents |
|---|---|---|
| A | grading ladder | execution > end-state > deterministic > judge > human. A7 tiered online scoring wraps all of them rather than ranking among them |
| B | comparison | paired items, win rate, McNemar, Bradley-Terry, CI from n (margin ≈ 100/√n), bootstrap, cluster bootstrap |
| C | statistics | Wilson, power n ≈ 16·p(1−p)/δ², noise floor (k ≥ 5 runs), Wilson/Clopper–Pearson near 0 or 100%, multiple comparisons, permutation |
| D | rare events | recall not accuracy, precision at a fixed floor, PR curves, average precision, cost-based threshold, red-team ASR per category, upper confidence bound + per-category counts |
| E | diagnostics | per-item diff, metric–outcome check, length-controlled win rate, A/A baseline, ceiling, floor, contamination, single-benchmark dominance |
| F | judge trust | 150–200 gold labels, Cohen's κ / Krippendorff's α, position bias, cross-family panel, binary criteria, one call per criterion, few-shot from disagreements, calibration rounds |
| G | RAG | recall@k, oracle-context test, faithfulness, nDCG, MRR, unanswerable (false-answer rate + over-abstention), noise robustness, attribution |
| H | agents | resettable env, end-state verification, pass^k, cost/success, step compounding, injection, trajectory, infra-vs-capability |
| I | production | CI gates, statistical gates, error analysis, pinned versions + canary, sampled online eval, business metrics, A/B by user, failures-as-tests, shadow mode |
| J | model selection | benchmarks as filter, own-data eval, Pareto, same-harness, vendor claims |

---

## 5. Target layout (M0)

```
evalloop/
  __init__.py
  vocab/
    __init__.py          re-exports Situation, Tool, parse_situation, parse_tool
    situations.py        StrEnum Situation (5 comment-grouped families)
    tools.py             StrEnum Tool
  registry/
    __init__.py
    format.py            on-disk format parser (minimal YAML subset OR JSON)
    schema.py            TechniqueRecord + RecordType / Gate / Cost enums
    loader.py            load_records(dir) -> tuple[TechniqueRecord, ...]
    integrity.py         check_integrity(records) -> list[str]
    query.py             match(records, situations)
    records/             A_grading.*, B_comparison.*, … J_model_selection.*
  plan/
    __init__.py
    readiness.py         evaluate_readiness(record, evidence) -> Readiness
    capability.py        check_capability(record, available_tools) -> Capability
    rules.py             apply_conflicts(), resolve_companions()
    planner.py           Plan dataclass + plan(...)
tests/
  conftest.py            corpus_dir fixture (EVALLOOP_CORPUS)
  test_scaffold.py
  test_vocab.py
  test_schema.py
  test_loader.py
  test_registry_integrity.py
  test_planner.py
  fixtures/planner/*.yaml   20 hand-written planner fixtures
pyproject.toml
README.md                ≤ 15 lines
.gitignore
```

---

## 6. Core domain vocabulary

### `Situation` (StrEnum, value == lowercase member name)
- **artifact:** code_generation, sql_generation, api_endpoint, structured_extraction, summarization, qa_answer, rag_answer, agent_action, classification, prose_generation, model_training, data_pipeline
- **measurement:** score_jumped, score_up_business_flat, length_increased, no_change_score_moved, all_candidates_high, all_candidates_zero, benchmark_too_good, single_benchmark_dominance
- **comparison:** two_candidates, many_candidates, external_leaderboard, metric_without_formula, items_grouped
- **grader_trust:** new_judge_built, measuring_agreement, multiple_annotators, position_bias_risk, self_preference_risk, scale_compressed, annotators_disagree
- **data:** rare_class, small_sample, grouped_items, contamination_risk, phi_present, distribution_mismatch
- **lifecycle:** pre_development, shipping_change, ci_flaking, debugging_regression, detecting_drift, scoring_live_traffic, measuring_impact, ab_testing, building_eval_set, model_selection

### `Tool` (StrEnum)
sandbox, test_runner, repo_read, source_doc_read, llm_api, llm_api_cross_family, vector_store, db_connection, ocr, vision_model, trace_capture, snapshot_restore, cost_api, human_labels, production_logs

Every member names a **capability**: something that must exist in the world for a technique to be runnable. No member names a **transport** — how the thing is reached. The test for a candidate: if the delivery mechanism changed but the resource stayed the same, would any record's requirement change? If not, it is transport, and it belongs to the capability broker, not here (decision `decisions/EL-002-mcp-tools-in-enum.md`, which is why `mcp_client` and `mcp_gateway` are absent).

Verify both against the sources. Add members **only** if genuinely missing, and justify each addition in a module docstring note. A single spelling mismatch (`summarization` vs `text_summary`) makes matching fail silently. That is the most important correctness decision in M0.

### `TechniqueRecord` (frozen dataclass)
| field | type | meaning |
|---|---|---|
| id | str | `<SECTION><N>_<snake_name>`, e.g. `A1_execution_based` |
| section | str | single letter A–J |
| name | str | as named in the source |
| type | RecordType | grader / metric / statistic / diagnostic / procedure / constraint |
| triggers_on_situation | tuple[Situation, …] | non-empty |
| required_signals | tuple[str, …] | free-text preconditions on artifact/data |
| required_tools | tuple[Tool, …] | may be empty |
| ladder_priority | int \| None | 1 execution, 2 end-state, 3 deterministic, 4 judge, 5 human. **None unless type is grader.** 5 is the maximum; there is no distilled rung (decision `decisions/EL-004-claude-md-corpus-gaps.md`). A7 tiered online scoring wraps the ladder and its priority is an open question for S6 |
| requires | Mapping[str, int \| bool] | readiness thresholds; empty = fires at n=1 |
| produces | tuple[str, …] | metric names |
| gates | Gate | absolute / statistical / false |
| companion_checks | tuple[str, …] | record ids that must be reported alongside |
| unlocks | tuple[str, …] | record ids this enables |
| conflicts_with | tuple[str, …] | record ids this replaces/invalidates |
| analysis_cost | Cost | low / medium / high |
| capture_cost | Cost \| None | |
| anti_pattern | str | what going wrong looks like |
| worked_example | str | concrete figures from source — **must contain a digit** |
| rule_of_thumb | str \| None | any stated formula, verbatim |
| source_ref | str | `filename § subsection` |
| extraction_notes | str \| None | anything ambiguous |

Type assignment: **most records are NOT graders.** A grader renders a verdict on an artifact. Wilson, McNemar and bootstrap are *statistics*. Section E is almost entirely *diagnostics*. "Never accuracy on rare class" and "never same-family judging" are *constraints*. Calibration and the failures-as-tests flywheel are *procedures*.

---

## 7. How to work in this repo

1. **One stage at a time.** Follow `TASKS.md` in order and do not jump ahead.
2. **Done means verified.** A stage is done when its "Done when" line passes. That always includes `pytest` exit 0 and `mypy --strict` clean.
3. **Fixtures before planner.** The 20 planner fixtures are written *before* the planner, from the source methodology, not from imagined code.
4. **Never edit a fixture to make a test pass.** If a fixture looks wrong, stop and flag it for human review.
5. **Raise schema problems, don't work around them.** Expect the schema to need a change after enriching the first two deep-dive files. When that happens, report it.
6. **Report back** at the end of every stage. Cover what was done, any source row you couldn't represent, any vocabulary gap, and any threshold you had to interpret from prose.
7. Errors aggregate. Loaders report **all** problems across all files, not just the first, because 70 records are being authored.
8. Deterministic everything. Ordering, rendering and ids must be stable across runs.

## 8. Commands

```bash
pytest                      # all tests
mypy --strict evalloop/     # type check
EVALLOOP_CORPUS="knowledge rules" pytest   # point at a corpus explicitly (optional)
```

## 9. Related docs
- `ARCHITECTURE.md` — system-level architecture: sensors, intent bus, coding-agent integration, live connectors (post-M0 tracks)
- `AGENT.md` — how the autonomous backend agent behaves (full pipeline)
- `USER_EXPERIENCE.md` — what the developer sees and does
- `PLAN.md` — milestones, gates, critical path
- `TASKS.md` — small, verifiable tasks in execution order
