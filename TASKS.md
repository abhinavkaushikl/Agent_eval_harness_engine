# TASKS.md — EvalLoop Task Breakdown

Small, focused tasks, each verifiable in one sitting. Work **top to bottom**. Each task has a **Done when** line, and nothing is done until it passes.

**Universal done criteria (apply to every task):** `pytest` exit 0 · `mypy --strict evalloop/` exit 0 · no invented numbers · report back (what was done, gaps, interpretations).

**Compact shared context (prepend to any task prompt):**
> Project: EvalLoop, an autonomous evaluation system. Current phase: registry + planner only. No execution, no file watching, no LLM calls, no stats implementation.
> Source corpus (read-only, in-repo): `knowledge rules/evals-situation-to-technique.md` (master lookup, ~70 techniques) and `knowledge rules/A-choosing-how-to-grade.md … J-choosing-a-model.md` (deep dives per section). Filenames are declared once in `tests/conftest.py`; import them, never retype them.
> Sections: A grading · B comparison · C statistics · D rare events · E diagnostics · F judge trust · G RAG · H agents · I production · J model selection.
> Rules: Python 3.12+, stdlib only (pytest dev-only OK). Type hints, mypy --strict clean. Never invent a number. Thresholds are verbatim from source or null.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

# MILESTONE 0 — The Brain (23 stages)

## Group 1 — Scaffold *(T0)*

### [x] S1 — Project skeleton
- Create `pyproject.toml`: `requires-python >= 3.12`, no runtime deps, dev extras `pytest`, `mypy`. Add ruff-equivalent settings only if trivial.
- Package dirs `evalloop/{vocab,registry,plan}/`, each with `__init__.py`.
- `tests/`, `.gitignore` (Python standard), `README.md` (≤ 15 lines: what it is, current phase, how to run tests).
- `tests/test_scaffold.py` with one trivial passing test.
- Do NOT create `grade/`, `capture/`, `stats/`.
- **Done when:** `pytest` exits 0; `mypy --strict evalloop/` exits 0.

### [x] S2 — Corpus path fixture
- `tests/conftest.py` with a `corpus_dir` fixture defaulting to the repo's `knowledge rules` directory (resolved from the repo root), overridable by env var `EVALLOOP_CORPUS`.
- No absolute user paths anywhere in test code.
- Tests asserting every corpus file in the mapping exists and carries its section header. A missing file **fails**, naming each one; it only skips when `EVALLOOP_CORPUS` points at a different corpus.
- **Done when:** tests pass against the in-repo corpus, with no skips.

## Group 2 — Vocabularies *(T1)*

### [ ] S3 — Situations enum
- `evalloop/vocab/situations.py`: `StrEnum Situation` with five-plus comment-grouped families: ARTIFACT, MEASUREMENT, COMPARISON, GRADER_TRUST, DATA, LIFECYCLE.
- Populate from the Situation column of the master lookup. Starting set is in `CLAUDE.md §6`.
- Read all source files; every distinct "Situation" value and every "You are here when…" framing maps to exactly one member.
- Member value == lowercase member name. Enum only, with no parse helpers yet.
- Justify every addition beyond the starting set in a module docstring note.
- **Done when:** enum imports; report lists any source situation that could not be represented.

### [ ] S4 — Tools enum + parsers
- `evalloop/vocab/tools.py`: `StrEnum Tool`: sandbox, test_runner, repo_read, source_doc_read, llm_api, llm_api_cross_family, vector_store, db_connection, ocr, vision_model, trace_capture, snapshot_restore, cost_api, human_labels, production_logs.
- `evalloop/vocab/__init__.py` re-exports both, plus `parse_situation(str)` and `parse_tool(str)` raising `ValueError` that names the bad value and lists valid options.
- **Done when:** both parsers round-trip every member and reject an unknown string with a helpful message.

### [ ] S5 — Vocab tests
- `tests/test_vocab.py`:
  - every member value == lowercase name
  - no duplicate values
  - `parse_*` raises with the offending value in the message
  - coverage test: a hardcoded list of ~20 situation strings taken **verbatim** from the master lookup all parse successfully
- **Done when:** all pass.

## Group 3 — Record format & schema *(T2)*

### [ ] S6 — Format decision + parser
- Decide the on-disk record format. YAML is most readable but needs a hand-written parser (no PyYAML). JSON needs none but reads worse.
- If YAML: minimal subset of scalars, lists, one level of nested maps, block strings.
- Implement `evalloop/registry/format.py` with `load(text) -> dict` and tests.
- State the reasoning in the module docstring.
- **Done when:** parser tests cover every construct used by records; reasoning documented.

### [ ] S7 — TechniqueRecord dataclass
- `evalloop/registry/schema.py`: StrEnums `RecordType` (grader/metric/statistic/diagnostic/procedure/constraint), `Gate` (absolute/statistical/false), `Cost` (low/medium/high), and frozen dataclass `TechniqueRecord` with all fields from `CLAUDE.md §6`.
- `__post_init__` must raise on:
  - empty `triggers_on_situation`
  - `ladder_priority` set when `type != grader`
  - `ladder_priority` outside 1–6
  - `id` not matching `<SECTION><N>_<snake>`
  - `worked_example` with no digit
  - empty `source_ref`
- Unit test each rule with hand-built records.
- **Done when:** each validation rule has a passing positive and negative test.

### [ ] S8 — Loader
- `evalloop/registry/loader.py`: `load_records(dir) -> tuple[TechniqueRecord, ...]`.
- Parses each file via `format.py`; validates situation/tool strings through the vocab parsers.
- Raises `RegistryError` aggregating **all** problems across **all** files, not just the first.
- Test with a deliberately malformed fixture record.
- **Done when:** a malformed record produces a message naming the record and the specific problem; multiple errors are all reported.

### [ ] S9 — Integrity checker
- `evalloop/registry/integrity.py`: `check_integrity(records) -> list[str]` (human-readable problems).
- Detect:
  - duplicate ids
  - `companion_checks` / `unlocks` / `conflicts_with` pointing at unknown ids
  - self-references
  - graders missing `ladder_priority`
  - non-graders carrying one
  - section outside A–J
  - id prefix disagreeing with the `section` field
- Test each rule individually, plus a test that `check_integrity()` over `records/` is empty.
- **Done when:** all rule tests pass.

## Group 4 — Skeleton extraction *(T3)*

Each stage reads **only** its sections of the master lookup and emits records filling `id · section · name · type · triggers_on_situation · anti_pattern · worked_example · source_ref · gates · analysis_cost`. Everything else stays null/empty, with no guessing.

**Field mapping:** `Use` → `name` · `Situation` → `triggers_on_situation` (a row may map to several) · `What it technically is` → informs `type` and `produces` · `Why this one` → `anti_pattern` (phrased as the failure that occurs without it) · `Example` → `worked_example` (keep concrete numbers) · `source_ref` → `evals-situation-to-technique.md § <letter>`.

**Rules:** most records are NOT graders. Do not merge two techniques into one record. Do not deduplicate across sections.

### [ ] S10 — Sections A, B, C
- Extract A (grading), B (comparison), C (statistics) into `evalloop/registry/records/` (`A_grading`, `B_comparison`, `C_statistics`). ~20 records.
- Wilson, McNemar and bootstrap are `type=statistic`. `ladder_priority` null for all non-graders.
- **Done when:** `load_records()` succeeds; `check_integrity()` empty.

### [ ] S11 — Sections D, E, F
- D (rare events), E (diagnostics), F (judge trust). ~23 records.
- E is almost entirely `diagnostic`. D contains constraints ("never accuracy on rare class"). F contains procedures (calibration) and constraints (never same-family judging).
- **Done when:** loads; integrity empty.

### [ ] S12 — Sections G, H, I, J
- G (RAG), H (agents), I (production), J (model selection). ~30 records.
- **Done when:** loads; integrity empty; report total count per section and any lookup row that could not be represented.

## Group 5 — Enrichment *(T4)*

Each stage reads the deep-dive files and fills what S10–S12 left empty: `requires · required_tools · required_signals · ladder_priority · companion_checks · unlocks · conflicts_with · capture_cost · rule_of_thumb`. It also updates `source_ref` to the deep-dive location (e.g. `A-choosing-how-to-grade.md § A1`). Run `check_integrity()` + tests after **each** stage. Expect a schema change after S13. Raise it; don't work around it.

**If the source states no number, use null.** Flag every threshold you had to interpret from prose.

### [ ] S13 — Enrich A + B
- Read `A-choosing-how-to-grade.md`, `B-comparing-two-things.md`.
- Fill `ladder_priority` from A's ladder (1 execution, 2 end-state, 3 deterministic, 4 judge, 5 human, 6 distilled).
- Add `conflicts_with` where A says execution beats judging ("if there is any way to execute, execute").
- Add B's McNemar discordant-pair threshold (~25) and cluster-bootstrap grouping requirement to `requires`.
- **Done when:** integrity empty; interpreted thresholds flagged.

### [ ] S14 — Enrich C + D
- Read `C-deciding-whether-a-result-is-real.md`, `D-rare-events.md`.
- Verbatim: `margin ≈ 100/√n` · `n ≈ 16/gap²` · noise floor 3–5 runs · Wilson's near-boundary condition.
- D companion pairings: violation rate ⇔ over-refusal rate; precision ⇔ stated recall.
- Encode "accuracy prohibited on rare_class" as a constraint record's effect.
- **Done when:** integrity empty.

### [ ] S15 — Enrich E + F
- Read `E-when-a-number-looks-wrong.md`, `F-trusting-your-grader.md`.
- E: each diagnostic needs a first action and typically requires history (baseline runs). Put that in `requires`. Add the length-bias ⇔ judge-score companion pairing.
- F: kappa above 0.6 · flip rate unreliable above 10–15% · calibration 50–100 labels · cross-family as a hard constraint · `required_tools` includes `llm_api_cross_family` and `human_labels`.
- **Done when:** integrity empty.

### [ ] S16 — Enrich G + H
- Read `G-rag-systems.md`, `H-agents.md`.
- G: encode build order, where recall@k precedes faithfulness (use `unlocks`/`requires`). `required_tools`: `vector_store`, `source_doc_read`.
- H: resettable environment precedes all agent evaluation. Trajectory capture needs `requires_pre_instrumentation: true` and unlocks cost-per-success, step compounding, infra-vs-capability, reward-hacking detection. `required_tools`: `trace_capture`, `snapshot_restore`.
- **Done when:** integrity empty.

### [ ] S17 — Enrich I + J
- Read `I-production.md`, `J-choosing-a-model.md`.
- I: gates are absolute for safety/schema and statistical for quality. Canary needs history *(remaining I/J details were cut off in the source screenshot; extract from the files)*. Cover per-item diff, tiered scoring, A/B by user, failures-as-tests, shadow mode, and `production_logs` tool.
- J: benchmarks as filter, own-data eval, Pareto, same-harness, vendor claims.
- **Done when:** every record has a resolvable deep-dive `source_ref`; every threshold verbatim or null; integrity empty; `pytest` green. **Report per file:** fields you could not fill · thresholds stated in prose you had to interpret (flag for human review) · any ordering constraint the schema couldn't express.

## Group 6 — Fixtures *(T5)*, written BEFORE the planner

**Fixture format** (one file per fixture in `tests/fixtures/planner/`):
```yaml
name: summarization_first_run
given:
  situations: [summarization]
  available_tools: [source_doc_read, llm_api_cross_family]
  evidence: {samples: 1, runs: 1}
expect:
  ready: [G3_faithfulness, E3_length_bias]   # order matters
  pending:
    B3_mcnemar: "needs paired_runs: 2, have 1"
  unavailable: []
  companions:
    G3_faithfulness: [E3_length_bias]
  prohibited: []
```
**Rules:** derive expectations from the **source methodology**, not from imagined code. `pending` entries state the unmet requirement in human-readable form. Where the sources prohibit something, assert its absence explicitly. Keep `evidence` minimal, containing only what the fixture tests.

### [ ] S18 — Format + first 5 fixtures
1. `code_generation`, first run, sandbox + test_runner available
2. `code_generation`, no sandbox → execution unavailable; what remains?
3. `summarization`, first run
4. `rag_answer` → recall@k must order before faithfulness
5. `agent_action`, no trace capture → trajectory family unavailable, and it says so
- **Done when:** 5 files load via the format parser.

### [ ] S19 — Remaining 15 fixtures
6. `structured_extraction` with a schema present
7. `two_candidates`, 1 run → McNemar pending
8. `two_candidates`, 2 paired runs, 8 discordant → still pending, threshold not met
9. `two_candidates`, 2 paired runs, 40 discordant → McNemar ready
10. `new_judge_built`, 0 labels → judge cannot gate
11. `new_judge_built`, 60 labels, kappa 0.71 → judge may gate
12. `rare_class` → recall ready, accuracy explicitly prohibited
13. `grouped_items` → cluster bootstrap replaces plain bootstrap
14. `small_sample` (n=25) → statistical comparisons pending with margin stated
15. `score_jumped` → reward-hacking investigation
16. `all_candidates_high` → ceiling remedy
17. `length_increased` + `summarization` → length-bias diagnostic
18. `api_endpoint` + `sql_generation` together → both families, correctly merged
19. `shipping_change` → regression suite + statistical gates
20. `phi_present` + `structured_extraction` → PHI gate precedes everything
- They will all fail until Group 7. That is correct.
- **Done when:** 20 fixtures load; report any fixture where the source was ambiguous about ordering or gating.

## Group 7 — Planner *(T6)*

Make all 20 fixtures pass. **Do not modify a fixture to match the implementation.** If a fixture seems wrong, stop and flag it for human review.

### [ ] S20 — `match()`
- `evalloop/registry/query.py`: `match(records, situations) -> tuple[TechniqueRecord, ...]`.
- Selects records whose `triggers_on_situation` intersects the input; multi-label merges without duplication.
- Deterministic order: graders by `ladder_priority` asc, then non-graders grouped by `type`, then `id` alphabetically.
- **Done when:** tests with hand-built records pass, including a multi-label case.

### [ ] S21 — Readiness
- `evalloop/plan/readiness.py`: `evaluate_readiness(record, evidence) -> Readiness(met: bool, reason: str | None)`.
- Empty `requires` → met. Missing evidence counts as absent. Numeric thresholds and boolean requirements (`requires_pre_instrumentation`) handled distinctly.
- Reason format: `"needs <key>: <threshold>, have <actual>"`.
- **Done when:** each branch unit-tested.

### [ ] S22 — Capability, conflicts, companions
- `evalloop/plan/capability.py`: `check_capability(record, available_tools) -> Capability(available: bool, missing: tuple[Tool, ...])`.
- `evalloop/plan/rules.py` pure helpers:
  - `apply_conflicts(ready)`: a higher-priority grader suppresses a conflicting lower one
  - `resolve_companions(ready, records)`: a ready record pulls in its `companion_checks`
- **Done when:** each unit-tested.

### [ ] S23 — Planner assembly + render
- `evalloop/plan/planner.py`: frozen dataclass `Plan(ready, pending, unavailable, companions, prohibited)` with `render() -> str`, and `plan(records, situations, available_tools, evidence) -> Plan`.
- Resolution order: match → apply constraint records (→ prohibited) → capability (→ unavailable) → readiness (→ pending) → conflicts → companions → order.
- `render()` output shape:
  ```
  READY        A1_execution_based · A3_deterministic
  PENDING      B3_mcnemar        needs discordant_pairs: 25, have 8
               C3_noise_floor    needs runs: 3, have 1
  UNAVAILABLE  H7_trajectory     missing: trace_capture
  PROHIBITED   accuracy          rare_class: "flag nothing" scores 99.8%
  ```
- **Done when:** all 20 fixtures pass; sanity queries in `PLAN.md §5` behave; all 20 rendered plans printed.

### 🔒 GATE 0
- [ ] Human reads all 20 rendered plans and agrees with every one. Fix anything disputed before M1.

---

# MILESTONE 1 — First Grading

### T7 — Metric store (JSONL)
- [ ] T7.1 Define metric row schema (run_id, case_id, technique_id, value, ts, situation, artifact_hash) as a frozen dataclass
- [ ] T7.2 Append-only JSONL writer (atomic line writes)
- [ ] T7.3 Reader with schema validation
- [ ] T7.4 Per-case diff between two runs
- **Done when:** two runs written and diffed per case.

### T8 — Episodic store (SQLite) *(parallelizable)*
- [ ] T8.1 Schema: sessions, decisions, plans, reasoning
- [ ] T8.2 Write API: persist situation decision + reasoning
- [ ] T8.3 Query API: by session, by technique
- [ ] T8.4 Migration/version table
- **Done when:** situation decisions and reasoning are persisted and queryable.

### T9 — Classifier heuristics (Python only)
- [ ] T9.1 Signal extractors: imports, file type, function signatures, SQL strings, HTTP routes
- [ ] T9.2 Rules → `(Situation, confidence)` multi-label
- [ ] T9.3 "Unclear" threshold that marks LLM fallback (fallback itself later)
- [ ] T9.4 10 labelled sample files as tests
- **Done when:** correctly labels 10 sample files.

### T10 — Oracle harvester
- [ ] T10.1 Find existing tests (pytest discovery conventions)
- [ ] T10.2 Find schemas (JSON Schema, dataclasses, pydantic-like declarations)
- [ ] T10.3 Extract type hints as oracles
- [ ] T10.4 Tag all harvested oracles HIGH
- **Done when:** returns HIGH-confidence oracles from a real repo.

### T11 — Sandbox runner
- [ ] T11.1 Tempdir workspace copy
- [ ] T11.2 subprocess with `resource` rlimits (CPU, memory, files)
- [ ] T11.3 Wall-clock timeout → `INCONCLUSIVE`
- [ ] T11.4 Capture stdout/stderr/exit code
- **Done when:** runs a command safely; timeout → INCONCLUSIVE.

### T12 — Execution grader
- [ ] T12.1 Hidden-test isolation (tests not visible to generator)
- [ ] T12.2 Partial credit per test case
- [ ] T12.3 Compile/import error vs logic failure split
- [ ] T12.4 Toy repo with deliberately broken function
- **Done when:** catches the broken function.

### T13 — Deterministic grader
- [ ] T13.1 Schema validator (stdlib)
- [ ] T13.2 Regex + exact match
- [ ] T13.3 Cascade hook interface (stub)
- **Done when:** validates output shape; cascade stub in place.

### T14 — LLM client + router
- [ ] T14.1 stdlib `urllib` HTTP client
- [ ] T14.2 Retry + exponential backoff
- [ ] T14.3 Router by job: classify / author / judge / diagnose
- [ ] T14.4 Credential loading from env; cost counter
- **Done when:** one call works; router selects by job.

### T15 — Test author
- [ ] T15.1 Generate tests from signature only (isolated from implementation)
- [ ] T15.2 Confidence tagging: harvested HIGH, authored LOW
- [ ] T15.3 Store authored cases as `generated`
- **Done when:** generates tests from signature only; tags HIGH/LOW correctly.

### T16 — Statistics module *(parallelizable)*
- [ ] T16.1 Wilson interval
- [ ] T16.2 Bootstrap + cluster bootstrap
- [ ] T16.3 McNemar
- [ ] T16.4 Permutation test
- [ ] T16.5 Noise floor + power (`n ≈ 16/gap²`, `margin ≈ 100/√n`)
- **Done when:** unit tests match corpus worked examples.

### T17 — Markdown report renderer
- [ ] T17.1 `summary.md` template: situations, plan, results, pending, prohibited
- [ ] T17.2 Render per run
- **Done when:** readable `summary.md` per run.

### 🔒 GATE 1
- [ ] Point at a toy repo with a deliberately broken function. It gets caught with zero instruction.

---

# MILESTONE 2 — The Session Tool

### T18 — Poller
- [ ] T18.1 `os.scandir` walk + stat
- [ ] T18.2 Content hash on mtime/size change only
- [ ] T18.3 `.gitignore` parser (stdlib)
- [ ] T18.4 Benchmark on 5k files
- **Done when:** detects changes in 5k files in < 20 ms.

### T19 — Event buffer + debouncer
- [ ] T19.1 Event queue
- [ ] T19.2 Quiet-window debounce → change unit
- **Done when:** bursts collapse into single change units.

### T20 — Git state reader
- [ ] T20.1 Baseline sha, branch
- [ ] T20.2 Staged vs committed vs working diff
- **Done when:** reports baseline, staged, committed, branch.

### T21 — AI transcript reader
- [ ] T21.1 Locate Claude Code JSONL transcripts on disk
- [ ] T21.2 Parse messages; extract stated intent
- [ ] T21.3 Link intent to change units by time
- **Done when:** extracts stated intent from disk.

### T22 — Coherence detector
- [ ] T22.1 Syntax-valid check (e.g. `ast.parse`)
- [ ] T22.2 Quiet period + import resolution
- [ ] T22.3 Transcript signal ("done", tests run)
- **Done when:** fires on complete units, not mid-edit.

### T23 — Session orchestrator
- [ ] T23.1 `evalloop start` / `evalloop stop` CLI
- [ ] T23.2 Async worker pool + queue
- [ ] T23.3 Wire capture → coherence → classifier → planner → graders → stats → memory
- [ ] T23.4 Report on stop
- **Done when:** `evalloop start` → works → `evalloop stop` → report.

### T24 — Content-hash cache
- [ ] T24.1 Key = artifact hash + technique id
- **Done when:** unchanged diff is never re-evaluated.

### T25 — Local API
- [ ] T25.1 stdlib `http.server` or asyncio server
- [ ] T25.2 `/status`, `/results`, `/pending`
- **Done when:** all three respond.

### T26 — Dashboard
- [ ] T26.1 Static HTML page served by T25
- [ ] T26.2 SSE stream endpoint
- [ ] T26.3 Plan view, results, permission requests
- **Done when:** updates during a session without refresh.

### 🔒 GATE 2
- [ ] Click start, work an hour in any editor, get a useful session report.

---

# MILESTONE 3 — Honesty Layer

- [ ] **T27** Readiness gate + pending queue rendering. Shows "need 25, have 8" with reasons.
- [ ] **T28** Noise floor across repeat runs. Refuses to call a within-noise delta an improvement.
- [ ] **T29** Per-item diff report. Lists flips in both directions.
- [ ] **T30** Diagnostics: E1 jump, E3 length, E5 ceiling, E6 floor. Flags a synthetic reward-hack scenario.
  - [ ] T30.1 E1 jump · [ ] T30.2 E3 length · [ ] T30.3 E5 ceiling · [ ] T30.4 E6 floor · [ ] T30.5 synthetic reward-hack test
- [ ] **T31** Journey ledger + trends. Per-field, per-slice trend lines over runs.
- [ ] **T32** Self-canary. Detects its own degradation on a fixed known-answer set.

### 🔒 GATE 3
- [ ] Refuses to report a noise-level change as a win; catches a planted reward hack.

---

# MILESTONE 4 — Judge & Second Situation

- [ ] **T33** Judge grader: single-criterion, named categories, reasoning-first (2d)
- [ ] **T34** Cross-family hard assertion in router (0.5d)
- [ ] **T35** Position swap + flip-rate tracking (1d). Unreliable above 10–15% flip rate.
- [ ] **T36** Calibration set + Cohen's kappa + `kappa_manual ≥ 0.6` runtime gate (2d)
  - [ ] T36.1 Collect 50–100 human labels · [ ] T36.2 kappa calc · [ ] T36.3 runtime gate
- [ ] **T37** Summarization situation: faithfulness + length companion (2d)

### 🔒 GATE 4 *(inferred)*
- [ ] Summarization judged end-to-end by a calibrated cross-family judge, reusing earlier components unchanged.

---

# MILESTONE 5 — Reach

- [ ] **T38** MCP client (3–5d)
- [ ] **T39** Connectors: GitHub → DB → Databricks (2d each)
- [ ] **T40** Node language adapter (1d)
- [ ] **T41** CI surface + PR comments (2d)
- [ ] **T42** Extraction situation + perturbation engine (1w)
- [ ] **T43** Agents: resettable env, trace capture, pass^k (2–3w)

---

## Next action
**S1 → S5** (scaffold + vocabularies). Freezing the vocabularies first is half a day of work and saves rework across all ~70 records.
