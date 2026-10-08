# TASKS.md — EvalLoop Task Breakdown

Small, focused tasks, each verifiable in one sitting. Work **top to bottom**. Each task has a **Done when** line, and nothing is done until it passes.

**Universal done criteria (apply to every task):** `pytest` exit 0 · `mypy --strict evalloop/` exit 0 · no invented numbers · report back (what was done, gaps, interpretations).

**Compact shared context (prepend to any task prompt):**
> Project: EvalLoop, an autonomous evaluation system. Current phase: registry + planner only. No execution, no file watching, no LLM calls, no stats implementation.
> Source corpus (read-only, in-repo): `knowledge rules/evals-situation-to-technique.md` (master lookup, 73 techniques) and `knowledge rules/A-choosing-how-to-grade.md … J-choosing-a-model.md` (deep dives per section). Filenames are declared once in `tests/conftest.py`; import them, never retype them.
> Sections: A grading · B comparison · C statistics · D rare events · E diagnostics · F judge trust · G RAG · H agents · I production · J model selection.
> Rules: Python 3.10+, stdlib only (pytest dev-only OK). Type hints, mypy --strict clean. Never invent a number. Thresholds are verbatim from source or null.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

# MILESTONE 0 — The Brain (23 stages)

## Group 1 — Scaffold *(T0)*

### [x] S1 — Project skeleton
- Create `pyproject.toml`: `requires-python >= 3.10`, no runtime deps, dev extras `pytest`, `mypy`. Add ruff-equivalent settings only if trivial.
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

### [x] S3 — Situations enum
- `evalloop/vocab/situations.py`: `StrEnum Situation` (import from `evalloop/_compat`, not `enum` -- EL-012) with five-plus comment-grouped families: ARTIFACT, MEASUREMENT, COMPARISON, GRADER_TRUST, DATA, LIFECYCLE.
- Populate from the Situation column of the master lookup. Starting set is in `CLAUDE.md §6`.
- Read all source files; every distinct "Situation" value and every "You are here when…" framing maps to exactly one member.
- Member value == lowercase member name. Enum only, with no parse helpers yet.
- Justify every addition beyond the starting set in a module docstring note.
- **Done when:** enum imports; report lists any source situation that could not be represented.

### [x] S4 — Tools enum + parsers
- `evalloop/vocab/tools.py`: `StrEnum Tool` (from `evalloop/_compat`): sandbox, test_runner, repo_read, source_doc_read, llm_api, llm_api_cross_family, vector_store, db_connection, ocr, vision_model, trace_capture, snapshot_restore, cost_api, human_labels, production_logs.
- `evalloop/vocab/__init__.py` re-exports both, plus `parse_situation(str)` and `parse_tool(str)` raising `ValueError` that names the bad value and lists valid options.
- **Done when:** both parsers round-trip every member and reject an unknown string with a helpful message.

### [x] S5 — Vocab tests
- `tests/test_vocab.py`:
  - every member value == lowercase name
  - no duplicate values
  - `parse_*` raises with the offending value in the message
  - coverage test: a hardcoded mapping of ~20 situation strings taken **verbatim** from the master lookup, each to the `Situation` member a record author must cite for that row, spanning all ten sections. The strings cannot be passed to `parse_situation` as S5 first read: the lookup's Situation cells are prose ("Output is code / SQL / an API call"), and prose normalisation is a classifier's job (M1), not a vocabulary's. The test also asserts each phrase is still a verbatim cell in the corpus, and that no cell is silently skipped.
- **Done when:** all pass.

## Group 3 — Record format & schema *(T2)*

### [x] S6 — Format decision + parser
- Decide the on-disk record format. YAML is most readable but needs a hand-written parser (no PyYAML). JSON needs none but reads worse.
- If YAML: minimal subset of scalars, lists, one level of nested maps, block strings.
- Implement `evalloop/registry/format.py` with `load(text) -> dict` and tests.
- State the reasoning in the module docstring.
- **Done when:** parser tests cover every construct used by records; reasoning documented.

### [x] S7 — TechniqueRecord dataclass
- `evalloop/registry/schema.py`: StrEnums `RecordType` (grader/metric/statistic/diagnostic/procedure/constraint), `Gate` (absolute/statistical/false), `Cost` (low/medium/high), and frozen dataclass `TechniqueRecord` with all fields from `CLAUDE.md §6`.
- `__post_init__` must raise on:
  - empty `triggers_on_situation`
  - `ladder_priority` set when `type != grader`
  - `ladder_priority` outside 1–5 (five is the maximum; decision `EL-004` removed the distilled rung)
  - `id` not matching `<SECTION><N>_<snake>`
  - `worked_example` with no digit
  - empty `source_ref`
- Unit test each rule with hand-built records.
- **Done when:** each validation rule has a passing positive and negative test.

### [x] S8 — Loader
- `evalloop/registry/loader.py`: `load_records(dir) -> tuple[TechniqueRecord, ...]`, sorted by `id` so the result never depends on directory order.
- Parses each file via `format.py`; validates situation/tool strings through the vocab parsers, surfacing their `ValueError` verbatim with the file, record id and field attached.
- Raises `RegistryError` aggregating **all** problems across **all** files, not just the first. `RegistryError.problems` is the structured list; the message is the same list, one line each.
- File shape settled here and for all 73 records: **one file per section, records keyed by id, `.yaml`**, with the id *not* repeated inside the body (decision `EL-013`, which closes open question 7).
- Tested with `tests/fixtures/registry/`: `good/` (two files, three records, declared out of id order) and `broken/` (four files, thirteen distinct problems at four layers — parse, top-level key, field shape, schema).
- **Done when:** a malformed record produces a message naming the record and the specific problem; multiple errors are all reported. ✅ 324 passed, `mypy --strict` clean.

### [x] S9 — Integrity checker
- `evalloop/registry/integrity.py`: `check_integrity(records) -> list[str]` (human-readable problems). Takes any iterable of records; `[]` means the graph is consistent.
- Detects all seven:
  - duplicate ids
  - `companion_checks` / `unlocks` / `conflicts_with` pointing at unknown ids
  - self-references
  - section-A graders missing `ladder_priority` (scoped during S13 — see below)
  - non-graders carrying one
  - section outside A–J
  - id prefix disagreeing with the `section` field
- Sorted by record id then rule, so a diff between two runs is meaningful. Rule 3 is skipped when rule 2 already fired: one defect, one line. An unknown reference names the closest loaded id (`difflib`, computed over a sorted id list so ties are stable) and says what the dangling edge costs the planner.
- `evalloop/registry/records/` is addressed as `loader.RECORDS_DIR`, resolved relative to the package, and is tracked empty via `records/.gitkeep` so "not authored yet" (a trivial pass) is distinguishable from "the directory vanished" (a loud failure).
- Tested per rule with hand-built record sets, each violating exactly that rule and nothing else (`_only` asserts a single problem, so a spurious second finding fails too).
- **Rule 4 is all-or-nothing** (changed during S10, by decision): it stays silent while no grader carries a rung and fires for every unrunged grader as soon as one does. The strict form made S10's two requirements — `ladder_priority: null` throughout *and* an empty `check_integrity()` — impossible together, and asserted something `CLAUDE.md` §6 never says (§6 states only "None unless type is grader", the one-way rule the schema already enforces).
- **Rule 4 was then scoped to section A** (changed during S13, by decision): all-or-nothing *within section A*, which is the only section the corpus gives a ladder (`A-choosing-how-to-grade.md:11-18`). All-or-nothing over every grader survived only while no grader had a rung; S13 assigns A1 rung 1, at which point the rule fired on `B2_pairwise_preference`, a section-B grader the corpus never places on the ladder. The alternatives were to invent a rung (forbidden by §3) or retype the record to silence the checker (forbidden by §7.5). The converse is deliberately *not* asserted: a rung on a non-A grader is not made a defect, because §6 states no such prohibition. `A7_tiered_online_scoring` needs no exemption at all — it is typed `procedure`, so no grader rule sees it.
- **Done when:** all rule tests pass. ✅ `mypy --strict` clean.
- Two findings for the record, neither fixed here: **non-graders carrying a `ladder_priority` is already unreachable** — `schema._check_ladder_priority` raises on it, so the integrity rule is defence in depth and its test has to use `object.__setattr__` to build a violating record. And **four cross-record invariants are unguarded** and named in the module docstring rather than added: unreciprocated `conflicts_with`, an id in both `companion_checks` and `conflicts_with`, `unlocks` cycles, and a companion that can never be ready. A fifth was listed here — two graders in one section sharing a rung — and S13 removed it from the list rather than guarding it: A3 and A5 genuinely share rung 3, so the rule would have rejected the corpus.

## Group 4 — Skeleton extraction *(T3)*

### [x] S10 — Extract A, B, C (20 records)
### [x] S11 — Extract D, E, F (23 records)
### [x] S12 — Extract G, H, I, J (30 records)
- All 73 records live in `evalloop/registry/records/`, ten files, one per section: A 7, B 7, C 6, D 6, E 8, F 9, G 8, H 8, I 9, J 5.
- Extracted from `evals-situation-to-technique.md` **only**. Deep dives were read for id numbering (`^# [A-J][0-9]+ `) and nothing else, so every `source_ref` is `evals-situation-to-technique.md § <letter>`; the deep-dive thresholds, orderings and edges are S13–S17's.
- `requires` is empty except where the lookup states a **single** bound verbatim: C3 `{runs: 5}`, E8 `{benchmarks: 3}`, H8 `{trials: 5}`. Stated *ranges* were deliberately left empty, because picking a value out of a range is the invented number `CLAUDE.md` §3 forbids: F1 150–200 gold labels, E4 3–5 runs, F6 4–8 checks, H5 5–10 sub-goals, H7 50–100 traces, J2 300–500 items, J5 100–200 items.
- `companion_checks` / `unlocks` / `conflicts_with` are empty throughout; the lookup has no column for them. `ladder_priority` is null throughout.
- `gates`, `analysis_cost` and `capture_cost` have no lookup column and no null member, so they are **derived, not copied**. Section I is the exception and records which rows state a gate (I1, I2, I4, I7, I9) and which do not (I3, I5, I6, I8).
- **Done when:** 73 records load, `check_integrity()` returns `[]`. ✅ 415 passed, `mypy --strict` clean.
- `tests/test_records.py` guards the content: per-section counts and every record's `anti_pattern`, `worked_example` and `domain_scenario` diffed against its own lookup row. Verified to fail on a single changed digit.

## Group 5 — Enrichment *(T4)*

Each stage reads the deep-dive files and fills what S10–S12 left empty: `requires · required_tools · required_signals · ladder_priority · companion_checks · unlocks · conflicts_with · capture_cost · rule_of_thumb`. It also updates `source_ref` to the deep-dive location (e.g. `A-choosing-how-to-grade.md § A1`). Run `check_integrity()` + tests after **each** stage. Expect a schema change after S13. Raise it; don't work around it.

**If the source states no number, use null.** Flag every threshold you had to interpret from prose.

### [x] S13 — Enrich A + B
- Read `A-choosing-how-to-grade.md`, `B-comparing-two-things.md`.
- `ladder_priority` filled from A's ladder (1 execution, 2 end-state, 3 deterministic, 4 judge, 5 human). **Five rungs.** There is no rung 6: decision `EL-004` removed the distilled rung, and `schema.py` now rejects it.
- **A3 and A5 share rung 3.** The line that decided it is the ladder box's cost/variance column: `A:13` and `A:14` carry the identical annotation "₹0, deterministic", and the source never orders them because the decision flow reaches them from mutually exclusive branches (`A:299` short fact vs `A:304` structured output). EL-004's own audit row reads them as one rung too.
- **A7 `ladder_priority` stays null** and the open question stays open. `A:18` puts it outside the ladder ("wraps all of the above"); rung 0 and rung 6 were both declined as reintroducing a rung no source states.
- `conflicts_with` encodes execution-beats-judging as **four one-way edges into A4**, from A1, A2, A3 and A5. The ticket's "if there is any way to execute, execute" is a paraphrase and **is not in the corpus**; the verbatim lines used instead are `00-INDEX.md:34` (principle 1, "A judge is the fallback"), `A:54`, `A:127`, `A:130` and A4's own `A:166` "When NOT to use it".
- McNemar's threshold is **25, copied not chosen**: `B:107` states "At least 25 discordant pairs (b + c ≥ 25)". The "~25" above was the loose form; the corpus has no tilde. Cluster-bootstrap grouping is split across `requires` (`cluster_id_recorded`, from `B:246`) and `required_signals`.
- **Done when:** integrity empty; interpreted thresholds flagged. ✅ 418 passed, `check_integrity()` `[]`, `mypy --strict` clean.
- **One change was required and made:** integrity rule 4 scoped to section A — see S9's note above, and `S13-REPORT.md` for the reasoning and the alternative that was declined.
- **Three thresholds are INTERPRETED, not copied**, and need a human ruling: `A6 items: 200` (`A:217` says "Draw 200 items", read here as a readiness floor), `B5 sample_size_stated: true` (`B:175` states a consequence, not a flag), `B7 cluster_id_recorded: true` (`B:246` gives an instruction, not a flag). Every other number in A and B is verbatim or null.
- **Four schema gaps raised, none worked around** (`S13-REPORT.md` §4): no field for a technique to fall back to when a readiness bound is not met (B3 → exact binomial); no field for a trust bar on a *produced* metric (eight instances in A and B); `requires` cannot express a range or an upper bound (A4's two κ bounds, B2's 10–15% flip rate); no `wraps`/`modifies` edge (A7 over the ladder, B7 over B6), and `conflicts_with` has no artifact scope, so the A1→A4 edge only fires when both situations are present.

### [x] S14 — Enrich C + D
- Read `C-deciding-whether-a-result-is-real.md`, `D-rare-events.md`.
- Verbatim: `n ≈ 16·p(1−p)/δ²` (C:19, C:69 — **not** `16/gap²`, which drops the `p(1−p)` factor and is wrong by 4× at p = 0.5) · noise floor `k ≥ 5` runs (C:94, C:97; `k = 3` is daily iteration only, C:103 — **not** a 3–5 range) · Wilson's near-boundary condition (C:245) · the paired power formula `n ≈ (1.96·√d + 0.84·√(d − δ²))² / δ²` (C:70), which no doc of ours had. `margin ≈ 100/√n` is **not C's** — C never states it; it is B5's (B:22, B:176) and S13 recorded it there.
- D companion pairings. **precision ⇔ recall: done, in both the places the source puts it** — inside D2 (`produces` carries `precision_at_floor` *and* `recall_at_floor`, per D:63 and D:71), and across records as D3 → D2 (D:104 "Show recall at the precision floor"). **violation rate ⇔ over-refusal rate: NOT ENCODABLE** — there is no over-refusal record anywhere in the registry. Grepping the whole corpus for over-refusal / over-blocking / over-abstention hits only G6, scoped to RAG answerables. `AGENT.md` §5 demands the pairing as a non-negotiable and the methodology has no counterpart to pair with; `EL-004` item 5 found the same gap from the other side. Raised, not invented.
- Other D edges, each named by the source: D3 → `B6_bootstrap_ci` (D:103), D5 → `C1_wilson_ci` (D:176) and `F1_gold_label_validation` (D:175), D6 → `C4_near_bounds_interval` (D:202) and `C1` (D:209). `unlocks` follows the deep dive's own numbered pipeline (D:11–15): D1 → D2/D3 → D4, and D5 → D6.
- `requires` added: D1 `{positives: 100}` (D:238 verbatim), D5 and D6 `{attempts_per_category: 50}` (D:210 verbatim for D6; **interpreted** for D5, see below). C3 `{runs: 5}` unchanged and re-cited.
- C's `requires` is empty in five of six records, and that is correct rather than unfinished: C decides whether *other* records' numbers are real, and C2 in particular runs before any data exists.
- "Accuracy prohibited on `rare_class`" — **partially blocked.** D1 is typed `constraint`, triggers on `rare_class`, and carries the reason with the corpus's own figure in `anti_pattern`, so two of the three parts of `USER_EXPERIENCE.md` §3.1's `PROHIBITED` line are renderable. **No field names the forbidden metric**, and there is no "accuracy" record for `conflicts_with` to point at, because accuracy is never codified as a technique anywhere in the corpus. Raised as finding **F5** with a ready-to-apply `prohibits` proposal; nothing was widened to paper over it.
- **Done when:** integrity empty. ✅ 418 passed, `check_integrity()` `[]`, `mypy --strict` clean.
- **Three doc conflicts resolved against the corpus, and a fourth and fifth found.** Full three-row table in `S14-REPORT.md` §2. Fixed in this diff: `TASKS.md` S14 + T16.5, `AGENT.md` §3.8 + §5's constraint table, `USER_EXPERIENCE.md` §3.1, and `TASKS.md` S18's render mock. `CLAUDE.md` §4 was already right on all three. `E1-M0-TICKETS-AND-PROMPTS.md` is left alone on purpose — it is the ticket archive, and editing it would falsify the historical record.
- **One threshold INTERPRETED**, needing a human ruling: D5 `{attempts_per_category: 50}` is the lower end of D:173's "at least 50–100 prompts", read as the floor. What makes it defensible is that D:210 states 50 independently as a hard bound on the same quantity. Overruling it leaves D5 with no per-category floor and the planner unable to mark a thin category pending.
- **Two findings carried forward:** C:175's "re-measure the winner on a held-out set" has **no record** in any section (the winner's curse is uncodified), and C4's near-boundary condition **cannot** go in `requires` — `n < 100` is an upper bound and `requires` reads every value as a floor, so encoding it would invert the record's own trigger. The sharpest case yet of S13's finding F3.

### [x] S15 — Enrich E + F
- Read `E-when-a-number-looks-wrong.md`, `F-trusting-your-grader.md`.
- E: **first actions captured verbatim in `extraction_notes` for all eight records, because the schema has no field for them** — the deep dive gives each one a FIRST CHECK in its symptom box (E:11–18) plus a step 1, and `name` holds the technique while `rule_of_thumb` holds a stated formula. Raised as S15 finding **F6** with a `first_action` proposal.
- E: **history is in `requires`, split two ways, and the split is the finding.** Where the history is *repeat eval runs* it is evidence: E1 `{runs: 2}` (E:31), E4 `{runs: 3}`, E7 `{runs: 2}` (E:245), E8 `{benchmarks: 3}` (E:278). Where it is *production data* it is a capability and stays in `required_tools` as `production_logs`: E2, E5. **Two records need no history and that is deliberate** — E3 diagnoses a single comparison, and E6 must run *before* any model does (E:210), so a readiness bound there would be wrong.
- E: the length-bias companion edge is live. **Three records now name E3**: `A4_judge_binary_criteria` and `B2_pairwise_preference` (S13, B2's traceable to B:75) and `F4_position_swap_consistency` (S15, on `AGENT.md` §5's authority, since it produces a win rate from a judge).
- F: κ ≥ 0.6 to use a grader and ≥ 0.8 to gate (F:21, F:72) · flip rate unreliable above 10–15% (F:140) — a **range and an upper bound**, so it is `null` in `requires` and verbatim in `rule_of_thumb`; T36 must read it from there · **F1 validates against 150–200 gold labels** (F:27, F:30, F:335), **not 50–100** — the "50–100 labels" above was wrong, and F never says it anywhere. The real 50 in F is F9's calibration batch, exactly 50 items (F:301), and F1's own single bound is "at least 50" **fail cases** (F:36), which is what `requires` records · cross-family as a hard constraint (F5, typed `constraint` since S11) · `required_tools` includes `llm_api_cross_family` (F5) and `human_labels` (F1, F2, F3, F8, F9).
- **Done when:** integrity empty. ✅ 418 passed, `check_integrity()` `[]`, `mypy --strict` clean, `unlocks` verified acyclic across all 73 records.
- **F5 confirmed, not changed:** typed `constraint` with `required_tools: [llm_api_cross_family]` since S11, and the deep dive bears both out (F:170 for self-preference bias, F:191 for the prohibition). `requires {judge_families: 3}` added from F:167/F:173. F1/F2/F3/F8/F9 already carried `human_labels`; F3 already triggered on `multiple_annotators` and F9 on `annotators_disagree`. All verified against the loaded registry.
- **The calibration stack (F:11–15) is the `unlocks` authority for F**, as D's pipeline box was for D: explicitly ordered and explicitly directional ("fix from the bottom up"), with F:17 stating the hard precondition at the bottom — "Human–human agreement is the ceiling. No judge can be validated above it." Level transitions were **not** mechanically expanded into four edges apiece; "validate each X against…" relations are `companion_checks` pointing *down* the stack, which is how the source phrases them and which keeps `unlocks` acyclic.
- **Two thresholds INTERPRETED**, both flagged: E4 `{runs: 3}` (lower end of E:140's "3–5 times", which **overturns S10's call** to leave it empty — an SD cannot be computed from one run, and C:103 states 3 independently as the floor for the lighter use) and E2 `{release_history_available: true}` (E:74's "6–10 releases" is a range, so the count is not copied but the precondition is carried as a boolean).
- **S13 finding F3 hit three more times in F alone** — F2's two κ bounds, F3's two α bounds, F9's 0.6-or-0.7-if-high-stakes — and F4's flip-rate ceiling is the case where encoding it in `requires` would **invert** it, exactly as S14 found for C4.

### [x] S16 — Enrich G + H
- Read `G-rag-systems.md`, `H-agents.md`.
- **Done when:** integrity empty. ✅ 418 passed, `check_integrity()` `[]`, `mypy --strict` clean, `unlocks` verified acyclic across all 73 records. Full report in `S16-REPORT.md`; the two hand-traces the ticket asked for are its §3 and §4.
- **The build order is data.** G: `G1` unlocks G2, G3, G4, G5, G7 and gates all five with `recall_at_k_measured: true`. H: `H1` unlocks all seven of H2–H8 and gates all seven with `environment_resets_per_run: true`. 17 `unlocks` edges, 19 `companion_checks` edges where G and H had none, and 15 boolean requirement entries across 12 records — nearly as many `unlocks` edges as the other eight sections hold between them (19), and five times their boolean gates (3).
- **G's flow is FOUR branches, not one chain** (`G:287-306`): gold labels → split the score (G1) → *and separately* unanswerables (G6) and citations (G8). G6 and G8 are **not** gated on recall@k. `ARCHITECTURE.md` §6.4's numbered RAG recipe reads as a chain and is the version that would have got this wrong; §6.4 is intent, the corpus is the source. Not edited, noted.
- **`unlocks` is read by nothing in `AGENT.md` §3.5** — steps 1–7 never touch it, so a build order recorded only there changes no plan. Every edge is therefore written twice: `unlocks` upstream for the direction, a boolean in `requires` downstream for the readiness check to fail on. Finding **F8** proposes `gated_by` to collapse the two. **D's and F's orderings currently gate nothing** as a result; that needs a decision, not a fix.
- Thresholds verbatim: `G3 claim_labels: 150` (`G:102`, "150+" — a bound, and **not** F's 150–200 range) · `H3 trials: 5` and `H8 trials: 5` (`H:102`, `H:264`; S12 had left H3's empty). H7's "50–100 traces" is genuine and was **not** touched, per the S15 hand-off.
- `requires_pre_instrumentation: true` is on `H5`, `H6`, `H7` — exactly the records whose `required_tools` include `trace_capture`. `H3` and `H8` carry a boolean **and** a numeric bound, so neither kind can be the only one `EL-121` handles. 15 records registry-wide now have a boolean requirement, up from 3.
- **Five schema findings, none worked around** (`S16-REPORT.md` §7): **F7** nothing stops a record gating itself, and `H1`/`G1` must be exempted by hand or the section deadlocks · **F8** `unlocks` unread, and the two directions can drift silently · **F9** two numbers from **one** record cannot be marked never-alone — `D6`, `G6`, `H6`, all three of them `AGENT.md` §5 non-negotiables, zero of them enforceable · **F10** `conflicts_with` cannot hold a conflict conditional on the data (G4-vs-G5, where both records trigger on `rag_answer` alone, so the edge would fire every session) · **F11** the first mutual `companion_checks` pair, `H2` ⇄ `H4`, correct per `H:73`/`H:139`, so `EL-122` step 6 must be a fixed point, not recursion.
- **Two ticket edges could not be written: there is no reward-hacking record in any of the 73**, and `H:236`'s automatic-detector step names none either. A corpus gap, not an authoring omission — `ARCHITECTURE.md` §5.1's "just make the test pass" signal has nothing to route to. `TASKS.md` line 164's other three resolve cleanly: cost-per-success = `H4`, step compounding = `H5`, infra-vs-capability = `H8`, all in `H1.unlocks`.
- **One leak found by the trace, not fixed:** `A2_end_state_verification` also triggers on `agent_action` and carries no gate, so with every tool granted it is READY while `H1` has not run. §5's "resettable environment before any agent eval" holds across H, **not** across the whole agent plan. Section A is S13's and the faithful fix needs finding F4 first; the one-line edit is in `S16-REPORT.md` §4 for a ruling.

### [x] S17 — Enrich I + J  ← **the registry is finished**
- Read `I-production.md`, `J-choosing-a-model.md`. The "cut off in the source screenshot" note is retired: nothing was missing from the repo.
- **Done when:** every record has a resolvable deep-dive `source_ref`; every threshold verbatim or null; integrity empty; `pytest` green. ✅ 419 passed, `check_integrity()` `[]`, `mypy --strict` clean, `unlocks` acyclic, **all 73 `source_ref`s resolve** and a test now asserts it. Full report in `S17-REPORT.md`.
- **All 73 records now cite a deep-dive subsection**; none cites the master lookup. `ENRICHED_SECTIONS` is `"ABCDEFGHIJ"`, which makes that test's lookup branch unreachable — kept as the guard against a regression.
- **New test, mutation-tested:** `test_every_source_ref_resolves_in_the_corpus` opens the cited file and finds the cited heading, aggregating problems across all 73. Two injected faults (`§ I3`→`§ I13`, a misspelled filename) both failed it by name.
- I: `gates` recorded with a deep-dive line each — I1 absolute (`I:33`), I2 statistical (`I:68`), I4 statistical (`I:145`), I7 statistical (`I:240`), I9 absolute (`I:310`); I3/I5/I8 state none. **`I6` moved `false` → `absolute`** (`I:207`, `I:221` "is now a hard guardrail"), the one judgement S17 overturned. History requirements: `I2 {runs: 3}` (`I:76`) · `I3 {failures: 100}` (`I:100`) · **`I4 {baseline_days: 30}`** (`I:145`, the canary baseline the ticket asked for) · `I7 {pre_registration_filed: true}` (`I:240`, boolean).
- J points at B and C instead of restating them: `J1`→B5 (`J:28`'s ±14 is B5's 100/√n at n=50) · `J2`→B1, C1, E5, F4 · `J3`→B1, H4 · `J5`→C1, E7. **`J3` ⇄ `H4` is the registry's only reciprocal cross-section pair** — S16 wrote one direction from H, S17 the other from J, and they agree. Recorded figures: `J1 {smoke_items: 50}` (overturns S12) · `J2 {human_pairwise_judgments: 100}` · `J3 {paired_ci_available: true}`.
- **Two new schema findings:** **F12** — `gates` holds one value and `I2` needs two, since `I:68` states "must pass 100%" (absolute) and "fail only when the 3-run mean" (statistical) in one sentence; `statistical` is kept and the safety half is lost to the planner. **F13** — the production flywheel (`I:9-21`) is a **cycle** and `unlocks` is a DAG; five of six arrows are written and `I9 → I5` is dropped deliberately, being the least gate-like and the only one never stated in a record's prose.
- **Two cross-cutting principles have no record at all.** `00-INDEX.md:37`'s fourth principle, "Slice the results", is codified nowhere — it appears *inside* D5, G5, I8, J2 and J5 and has no row of its own, so `J:120`'s critical-slice check has nothing to point at. With S16's reward-hacking gap, that is two corpus gaps to rule on before M3.
- **🔴 `PLAN.md` §5's sanity queries: three of six come out as stated.** Answered by hand in `S17-REPORT.md` §4. Q3 (RAG) ✅ · Q2 (code gen) ✅ but vacuously, and the no-sandbox plan is **empty** · Q4 (rare class) ⚠ prohibition is structural-only (F5) and recall is pending on 100 positives · **Q1 (summarization) ❌ nothing is ready** — faithfulness is unreachable (`G3` triggers on `rag_answer` only, and no lookup row covers summarization faithfulness) and the length check is blocked behind an unready host · **Q5 ❌** `B1_paired_evaluation` and `C6_permutation_test` fire at n=1 because `B5 → B1` lives in `unlocks`, which nothing reads · **Q6 ❌** not answerable from `requires` at all, because significance is a formula and judge agreement is a range. **`PLAN.md` §5 is not edited** — it is the gate, and moving it is a ruling.
- **The sharpest consequence, raised for a decision:** putting the κ trust bars in `A4.requires` makes **every judge-graded artifact's plan empty on a fresh repo**, and suppresses the length-bias companion with it, because step 6 forces companions only for *ready* records. S13 finding **F2** is therefore not cosmetic — it changes what the product shows on day one.

## Group 6 — Fixtures *(T5)*, written BEFORE the planner

**Fixture format** (one file per fixture in `tests/fixtures/planner/`):
```yaml
name: summarization_first_run
given:
  situations: [summarization]
  available_tools: [source_doc_read, llm_api_cross_family]
  evidence: {samples: 1, runs: 1}
expect:
  ready: [G3_faithfulness, E3_length_controlled_win_rate]   # order matters
  pending:
    B3_mcnemar: "needs discordant_pairs: 25, have 0"
  unavailable: []
  companions:
    G3_faithfulness: [E3_length_controlled_win_rate]
  prohibited: []
```
> ⚠ **This example is illustrative and its `expect` block is NOT achievable** — see `S17-REPORT.md` §9. S17 fixed two outright errors in it that S18 would otherwise have copied: the record id is `E3_length_controlled_win_rate`, not `E3_length_bias`, and B3's key is `discordant_pairs: 25`, not `paired_runs: 2`. Two faults remain and are a **ruling, not a typo**: `G3_faithfulness` triggers on `rag_answer` only, so it is never matched for `summarization`, and `B3_mcnemar` does not trigger on `summarization` either. The real plan for `summarization` on a fresh repo is `ready: []` with `A4_judge_binary_criteria` pending on its κ bars. Copy the *shape* from here and the *expectations* from the records.

**Rules:** derive expectations from the **source methodology**, not from imagined code. `pending` entries state the unmet requirement in human-readable form. Where the sources prohibit something, assert its absence explicitly. Keep `evidence` minimal, containing only what the fixture tests.

### [x] S18 + S19 — the 20 fixtures  *(run together: S18 had never been run, and "20 total" needs its five)*
- **Done when:** files load via the format parser. ✅ 541 passed, 1 skipped (the parked planner comparison), `mypy --strict` clean. Full report in `S19-REPORT.md`.
- **17 live fixtures + 3 BLOCKED on a ruling.** Blocked files carry a `.BLOCKED.yaml` suffix, are excluded from the glob, hold their `given` block and their options, and carry **no `expect` block** — a test enforces that, because asserting either reading pre-empts the ruling. `tests/test_planner_fixtures.py` has nine parametrised checks plus three whole-set ones.
- **A typed loader owns the schema** (`tests/planner_fixture.py`): `PlannerFixture` (frozen, read-only mappings — `CLAUDE.md` §7.4 enforced by the type), `FixtureError` aggregating **every** problem in one raise, and `load_fixture(path, known_ids)`. The three failures the ticket names — unknown record id (including inside a `companions` *value*), unknown situation, unknown tool — are the loader's, so they fire for every consumer rather than only for whoever remembers a helper. Nine tests prove the loader *refuses* each one, against deliberately broken text; before, the checks only proved the fixtures were clean. Situations and tools parse through `parse_situation`/`parse_tool`, never a string compare.
- **Format correction:** `unavailable` and `companions` are **maps**, not lists — `AGENT.md` §3.5 types them `Mapping`. Empty is `{}`. `TASKS.md`'s own example wrote `unavailable: []`.
- **Every `expect` block was authored from the records, then cross-checked** against an independent scratchpad trace of §3.5 steps 1–6. All 17 agreed on `ready` order, `pending` keys and reasons, `unavailable` keys and tools, and `prohibited`. One `companions` slip was caught and fixed (fixture 19's transitive `E1 → E4`).
- **🔴 Fixture 11 is blocked and is yours to decide** (`S19-REPORT.md` §2). `60 labels, κ 0.71 → judge may gate` contradicts the corpus twice over: `F:20` and `F:72` state "κ ≥ 0.6 to use, ≥ 0.8 to gate" in the imperative, so 0.71 **may use and may not gate**; and `F:27` names F1 for 150–200 labels, so 60 is far too few — `F:74` adds that κ on 150 items already has a CI of 0.52–0.77, so at 60 even "may use" is not demonstrated. Four options written out; **A recommended** (fix the expectation, keep the inputs — it becomes the only fixture distinguishing the two bars).
- **🔴 Fixture 20 cannot be written: there is no PHI record.** Nothing triggers on `phi_present`, and the string "PHI" appears **nowhere** in `knowledge rules/`. The nearest thing is I8's `required_signal` "PII is scrubbed…" (`I:277`), a precondition on set-building, not a gate. Four options; **D first** — treat redaction-before-egress as a capability-broker concern per `EL-002`, in which case `phi_present` does not belong in `Situation` at all. Option A would create the first record with no corpus provenance, failing S17's resolution test.
- **🔴 Fixture 14 cannot be written: the margin rule is unreachable.** `B5_ci_from_n` holds "the worst-case 95% margin is about 100/√n" — ±20 points at n=25, exactly what the fixture wants — but B5 triggers on `external_leaderboard` only. And nothing is pending for `small_sample`, because the only record it reaches is `C1_wilson_ci`, whose `requires` is empty. **Recommended: add `small_sample` to `B5.triggers_on_situation`.**
- **🔴 SIX `Situation` MEMBERS REACH NO RECORD AT ALL** (`S19-REPORT.md` §3): `classification`, `data_pipeline`, `model_training`, `contamination_risk`, `distribution_mismatch`, `phi_present`. `match()` returns nothing for six of 57, so a session classified into any of them gets an empty plan with no explanation. **`contamination_risk` is a plain authoring miss** — `E7_contamination_check` exists and triggers on `benchmark_too_good` only; it is a one-line fix to S15's file and was not made, because a trigger change is a decision. `ocr` and `vision_model` are unused `Tool` members.
- **Four fixtures could not assert their stated purpose**, all written as the records actually behave and each flagged in-file: **15** — no reward-hacking record exists anywhere · **19** — both gates reachable from `shipping_change` are *absolute*; the statistical gate I2 needs `ci_flaking` · **18** — both situations reach only A1, so it tests dedup but no breadth · **12** — the word "accuracy" appears nowhere in the plan (S14 finding F5).
- **Fixture 13 needed a second situation.** B7 triggers on `grouped_items`, B6 on `metric_without_formula`, so a plan from `grouped_items` alone never contains B6 and the `conflicts_with` edge never fires. Both situations are stated, and the fixture asserts B6's **absence from all four buckets**.
- **Two more findings:** **tool subsumption does not exist** — A4 requires `llm_api` and `TASKS.md`'s example grants only `llm_api_cross_family`, so the judge is UNAVAILABLE, a third fault in that example beyond S17's two · **fixture 2's answer is "nothing"** — one record triggers on `code_generation`, so with no sandbox the plan is one permission request.
- `prohibited` is excluded from the bucket-disjointness check on purpose: `D1` is both `ready` and `prohibited` in fixture 12, awaiting ruling 14.

### [x] S18 — Format + first 5 fixtures  *(superseded by the entry above; kept for the task list's shape)*
1. `code_generation`, first run, sandbox + test_runner available
2. `code_generation`, no sandbox → execution unavailable; what remains?
3. `summarization`, first run
4. `rag_answer` → recall@k must order before faithfulness. **Grant `llm_api` as well as `vector_store`:** capability (§3.5 step 3) precedes readiness (step 4), so `G3_faithfulness` without `llm_api` lands in `unavailable` and never shows its pending reason. `EL-116`'s acceptance criterion says "vector_store granted … faithfulness PENDING" and those cannot both be true. Trace to copy: `S16-REPORT.md` §3, variant 1b or 1c.
5. `agent_action`, no trace capture → trajectory family unavailable, and it says so. Assert on **`unavailable`**, naming `trace_capture`, not on `pending` — `H5`, `H6`, `H7` are stopped by the tool before the booleans are consulted. Trace to copy: `S16-REPORT.md` §4, variant 2b.
- **Done when:** 5 files load via the format parser.

### [x] S19 — Remaining 15 fixtures  *(see the combined entry above)*
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

### [x] S20 — `match()`
- `evalloop/registry/query.py`: `match(records, situations) -> tuple[TechniqueRecord, ...]`, plus `sort_key` and `TYPE_GROUP_ORDER`.
- **Done when:** tests with hand-built records pass, including a multi-label case. ✅ 580 passed, 1 skipped, `mypy --strict` clean. 22 tests in `tests/test_query.py`, every one building its own records — the registry is loaded in exactly one test, which asserts only that the 73 shipped records do not *contradict* the rule.
- **The type-group order is fixed and justified:** `grader → metric → statistic → diagnostic → procedure → constraint`. The reason is the data flow — each group consumes what the one before it produces (verdict → number → is-it-real → explanation → changed process → prohibition), which is the chain `RecordType`'s own docstring uses to tell the types apart. So a rendered plan reads in the order the work happens. `constraint` is last for a second reason: its content is a prohibition that the planner reports in `Plan.prohibited`, so its appearance in `ready` (as `D1` does) is incidental to what it forbids. `TYPE_GROUP_ORDER` is written out explicitly rather than derived from the enum, and two tests keep it honest: one asserts it covers every `RecordType` (a seventh type fails a test instead of raising inside a plan), one is a tripwire that it still matches the declaration order.
- **An unrunged grader sorts after every runged one**, not at a guessed rung — `B2_pairwise_preference`'s case, and the same refusal EL-113 made in declining to invent a rung for it. The key keeps `None` in a separate element so it never compares as a number.
- **Duplicate ids are returned, not halved.** `check_integrity` owns that defect; `match` would hide it.
- **🟢 All 17 live fixtures' `ready` lists are consistent with the rule — no inconsistency, no stop.** Now asserted permanently by `test_ready_is_in_step_seven_order`, which was mutation-tested: swapping fixture 1's two ids fails it by name. `sort_key` is exported so `evalloop/plan` orders `Plan.ready` with the same function rather than a second copy of the rule.

### [x] S21 — Readiness
- `evalloop/plan/readiness.py`: frozen `Readiness(met, reason)` + pure `evaluate_readiness`. ✅ 19 tests, one per branch (empty requires · numeric met · numeric unmet · missing key · boolean met · boolean unmet · several unmet), plus the contract tests below. The result type refuses a met readiness carrying a reason and an unmet one without — `USER_EXPERIENCE.md` §4 principle 3 enforced by the type.
- **Boolean wording chosen:** `needs recall_at_k_measured: true, have false`. Keeps §3.5's one format (the fixtures assert it) and fixes both faults the ticket names — `True` is Python's spelling, not the corpus's, and `have 0` implies a count where there is none. **The readability was bought in the keys, not the renderer:** the 17 boolean keys were authored as predicates (`recall_at_k_measured`, `environment_resets_per_run`, `pre_registration_filed`, `paired_ci_available`) precisely so the line reads as English with no special-casing.
- **Several unmet → ALL of them**, one leading `needs`, joined by `"; "`, **in `requires` declaration order**. The fixtures decide it: `"needs judge_human_kappa_to_trust: 0.6, have 0; judge_human_kappa_to_gate: 0.8, have 0"`. Not the first (hides the rest), not the worst (nothing defines a comparison between a κ and a count), not alphabetical (scrambles the corpus's order of mention).
- **Every judgement resolves toward NOT ready:** a boolean under a numeric key, a number under a boolean key, and an unusable value all count as absent. A wrongly pending record costs one line in a queue; a wrongly ready one costs a dishonest number.
- **🟢 Every fixture pending string reproduced character for character** — eight distinct strings across five fixtures, asserted by `test_every_fixture_pending_reason_is_reproduced_exactly`. The converse too: nothing in any fixture's `ready` is secretly pending.

### [x] S22 — Capability, conflicts, companions
- `evalloop/plan/capability.py` + `apply_conflicts`/`resolve_companions` in `evalloop/plan/rules.py`. ✅ 28 tests, all hand-built records; the registry is touched in two tests that check the shipped records contradict neither ruling.
- **`Capability.missing` keeps the record's own `required_tools` order**, filtered — not alphabetical, not `Tool` declaration order. H1 lists sandbox, snapshot_restore, trace_capture in the order `H:36-38` introduces them, so a permission request reads in the order the technique's own method needs them. `render()` gives `missing: trace_capture`, as `USER_EXPERIENCE.md` §3.1 prints it.
- **No tool subsumption**, asserted by a test: `llm_api_cross_family` does not satisfy `llm_api`. Deciding one grant covers another is a policy question about what the user agreed to, and `EL-002` puts that in the capability *layer*.
- **🔵 RULING 1 — when neither conflicting record has a rung, the EDGE DIRECTION decides.** §3.5 step 5 covers four of the registry's five edges (A1/A2/A3/A5 → A4, by rung). The fifth, `B7_cluster_bootstrap → B6_bootstrap_ci`, is two statistics with no rungs, so priority cannot decide it. `CLAUDE.md` §6 defines the field as "record ids this **replaces/invalidates**" — a directed claim by the declarer — and the corpus is why: a bootstrap that resamples items when items come in groups understates the interval, so the cluster form corrects it rather than competing with it. Full rule: two runged graders → suppress only when the declarer's rung is strictly better, and **a lower grader claiming to replace a higher one is left unapplied and reported**; anything else → the declarer replaces what it names. Chains are not resolved and none exists (A4 and B6 declare nothing).
- **🔵 RULING 2 — an unready companion joins the plan and is bucketed on its merits; the parent stays ready.** Forcing it into `ready` is rejected outright (it would report a number that has not met its bar). The corpus argues *both* ways: `AGENT.md` §5's never-alone rules and `G:195` argue the parent should go pending, but `I1 → E4` is a *parameter supplier* (`I:41`) and holding I1 back would suppress the must-pass gate `I:33` exists to guarantee. **Both are spelled `companion_checks` and the schema cannot tell them apart** — so the chosen reading is the only one right for both, nothing is hidden, and fixture 19 asserts it. Cost stated plainly: for the judge and safety pairs the registry can place the pair side by side but cannot *enforce* the rule. Same gap as finding F9, from the other side.
- **🔵 RULING 2b — and expansion STOPS at a companion that is not ready, which the fixtures answered before the module existed.** Fixture 10: `F7` ready → `F2` pending (no κ measured) → F2 names `B6` (`F:74`, "Bootstrap κ"), and B6 needs no tool and no threshold, so **a blind closure puts B6 in `ready`** — offering to bootstrap a CI around a κ that does not exist. Same shape in fixtures 7–9 via `E1 → E4`. So a companion edge is followed only from a record that is itself ready: fixture 19 *has* `E1 → E4` because there E1 is ready at two runs; fixtures 7–9 lack it because there E1 is pending. **Hence `resolve_companions` expands one level and the planner loops** — it has neither the evidence nor the grants, so it cannot know what is ready and must not guess. The loop terminates (the ready set only grows, bounded by the registry) and settles the H2⇄H4 mutual pair in two rounds.
- **🟢 All 17 fixtures reproduce exactly** when the four functions are composed with that loop — ready order, every pending string, unavailable tools, companions and prohibited, in 1–2 rounds each. **This found a real defect in my first implementation:** a blind fixed point disagreed with four fixtures, and the fixtures were right. That is `CLAUDE.md` §7.3's "fixtures before planner" paying for itself.

*(superseded)* ### [ ] S21 — Readiness
- `evalloop/plan/readiness.py`: `evaluate_readiness(record, evidence) -> Readiness(met: bool, reason: str | None)`.
- Empty `requires` → met. Missing evidence counts as absent. Numeric thresholds and boolean requirements (`requires_pre_instrumentation`) handled distinctly.
- Reason format: `"needs <key>: <threshold>, have <actual>"`.
- **Done when:** each branch unit-tested.

*(superseded)* ### [ ] S22 — Capability, conflicts, companions
- `evalloop/plan/capability.py`: `check_capability(record, available_tools) -> Capability(available: bool, missing: tuple[Tool, ...])`.
- `evalloop/plan/rules.py` pure helpers:
  - `apply_conflicts(ready)`: a higher-priority grader suppresses a conflicting lower one
  - `resolve_companions(ready, records)`: a ready record pulls in its `companion_checks`
- **Done when:** each unit-tested.

### [x] S23 — Planner assembly + render  ← **M0 is code-complete**
- `evalloop/plan/planner.py`: frozen `Plan` + pure `plan()` + `render()`. ✅ **641 passed, 0 skipped**, `mypy --strict` clean, **all 17 live fixtures pass**, all **20 plans rendered** to `GATE0-RENDERED-PLANS.md`. Full report in `S23-REPORT.md`.
- **The parked test is gone, not skipped.** `test_fixtures_match_the_planner` is superseded by `tests/test_planner.py::test_fixture`, and the suite now has no skips.
- **The fixture runner names the field**: `ready` with order marked significant, and the three mappings split into *only in planner* / *only in fixture* / *differing*, then the rendered plan. That shape localised S22's ruling-2b defect in one read.
- **`GATE0-RENDERED-PLANS.md` cannot go stale**: `tests/test_planner_artifact.py` asserts the committed file equals what the planner renders now, naming the first differing line and the regeneration command. Mutation-tested. Regenerate with `python -m tests.render_gate0`.
- **All 20 are rendered, including the three blocked fixtures** — they have no `expect` but they do have a `given`, and their plan is what the ruling is about. Each is marked ⚠ **BLOCKED ON A RULING** so a reviewer cannot mistake a question for an agreed plan. **Fixture 11's plan now shows, from running code, `F2_cohens_kappa needs judge_human_kappa_to_gate: 0.8, have 0.71`** — the judge may be used and may not gate, the opposite of its specified expectation.
- **🔴 `PLAN.md` §5: three of six sanity queries diverge**, each an explicit test asserting what the planner *does*, with the divergence in its docstring. Nothing was adjusted to make one pass. **Q1 summarization ❌** nothing is ready — faithfulness is unreachable (no lookup row covers entailment against a source document) and the length companion is suppressed with its pending host (**finding F2**) · **Q5 single observation ❌** `B1_paired_evaluation` and `C6_permutation_test` fire at n=1, because `B5 → B1` lives in `unlocks`, which §3.5 never reads (**finding F8**) · **Q6 ❌** true as asked but the only ≥200 bars are `A6`/`A7`, not significance or judge agreement · Q4 ⚠ half · Q2 ✅ vacuously · Q3 ✅ the only one fully met. **`PLAN.md` §5 was not edited** — moving the gate is a ruling.
- **Three surprises worth reading before Gate 0** (`S23-REPORT.md` §4): the PROHIBITED line reads as a **record id** where the mock wants `accuracy`, because no field names the forbidden metric (**F5**) · **step 2's "anything they prohibit leaves ready" is a no-op** against this registry — what D1 forbids has no record to remove, asserted for all three constraints · **`Plan` needed a sixth field**, because §3.5's five cannot render §3.1's PROHIBITED reason; the five are kept exactly and `prohibition_reasons` added, with `__post_init__` refusing a prohibited id without one.
- **Step 6 is a loop** (S22 ruling 2b): resolve one level, bucket, resolve again from the newly *ready* ones. Every fixture settles in 1–2 rounds; `MAX_COMPANION_ROUNDS = 16` guards a future registry, not this one. `pending` and `unavailable` preserve bucketing order, so the pending queue reads in the same priority order as `ready`.

*(superseded)* ### [ ] S23 — Planner assembly + render
- `evalloop/plan/planner.py`: frozen dataclass `Plan(ready, pending, unavailable, companions, prohibited)` with `render() -> str`, and `plan(records, situations, available_tools, evidence) -> Plan`.
- Resolution order: match → apply constraint records (→ prohibited) → capability (→ unavailable) → readiness (→ pending) → conflicts → companions → order.
- `render()` output shape:
  ```
  READY        A1_execution_based · A3_normalised_exact_match
  PENDING      B3_mcnemar        needs discordant_pairs: 25, have 8
               C3_repeat_runs    needs runs: 5, have 1
  UNAVAILABLE  H7_trajectory     missing: trace_capture
  PROHIBITED   accuracy          rare_class: "flag nothing" scores 97% at 3% prevalence
  ```
  Every id and number in that mock is a real record's: S14 corrected `C3_noise_floor`
  (no such id) to `C3_repeat_runs`, `runs: 3` to the corpus's `k ≥ 5`, `A3_deterministic`
  to `A3_normalised_exact_match`, and the 99.8% figure to D1's own 97% (99.8% is D6's
  "% safe" headline from a different scenario). The PROHIBITED line still cannot be
  rendered from the schema — no field names the forbidden metric. See `S14-REPORT.md` F5.
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
- [ ] T16.5 Noise floor + power (`k ≥ 5` runs, `n ≈ 16·p(1−p)/δ²`; `margin ≈ 100/√n` is B5's)
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
  - [ ] T36.1 Collect **150–200** human gold labels, with **at least 50 fail cases** (F:27, F:36) · [ ] T36.2 kappa calc · [ ] T36.3 runtime gate (κ ≥ 0.6 to use, ≥ 0.8 to gate; flip rate > 10–15% unreliable — read these from `rule_of_thumb`, not `requires`)
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
🔒 **GATE 0 — a human reads the 20 rendered plans.** `M0 is code-complete.` `PLAN.md` §5: "Human reads all 20 rendered plans and agrees with every one. Fix anything disputed before M1." The artifact is **`GATE0-RENDERED-PLANS.md`** (20 plans, 301 lines) and a test keeps it current.

Read `S23-REPORT.md` §3 and §4 alongside it: three of `PLAN.md` §5's six sanity queries do not behave as `PLAN.md` says, and three properties of the render will surprise anyone who has only read the mock.

**Fifteen rulings are open and twelve are decisions rather than work** — `S17-REPORT.md` §9 (1–8), `S19-REPORT.md` §7 (9–14), `S23-REPORT.md` §6 (15). The two that change M0's visible output most, both now demonstrated by running code: **F2** (κ trust bars in `requires` empty every judge-graded plan on day one) and **F8** (`unlocks` read by nothing, so `B1` fires on a single pair).

*(superseded)* **S23** (planner assembly + render). The four pure pieces exist and all 17 live fixtures reproduce exactly when they are composed: `match`/`sort_key` (steps 1 and 7), `check_capability` (3), `evaluate_readiness` (4), `apply_conflicts` (5), `resolve_companions` (6). S23 owns step 2 (the `constraint` records), the `Plan` dataclass, `render()`, and **the companion loop ruling 2b puts in the planner** — resolve, bucket, resolve again from the newly *ready* ones, until a round adds nothing. Then unskip `tests/test_planner_fixtures.py::test_fixtures_match_the_planner`.

The composition that reproduces all 17 fixtures is written out in this stage's report; S23 should start from it rather than re-deriving it.

*(superseded)* **S21** (`evalloop/plan/readiness.py` — `evaluate_readiness(record, evidence) -> Readiness`). `match()` is done, so step 1 and step 7 of `AGENT.md` §3.5 exist; steps 2–6 are S21–S23.

For S21 specifically: **17 records carry a boolean requirement** and six of them carry a boolean *and* a numeric bound, so neither kind can be the one that is handled. The reason string for a boolean must not render as a failed comparison — the keys are written as readable predicates (`pre_registration_filed`, `paired_ci_available`, `environment_resets_per_run`, `recall_at_k_measured`) for exactly that. Fixtures 4, 5 and 13 exercise them.

*(superseded)* **S20** (`evalloop/plan/` — `readiness.py`, `capability.py`, `rules.py`, `planner.py`). **The registry and the fixtures are both finished:** 73 records enriched from their deep dives, every citation resolving, and 17 live fixtures + 3 blocked waiting for a planner to compare against. `tests/test_planner_fixtures.py::test_fixtures_match_the_planner` is the parked comparison — unskip it when `evalloop.plan` lands.

🔴 **Fourteen rulings are open and eleven are decisions rather than work** — `S17-REPORT.md` §9 for 1–8, `S19-REPORT.md` §7 for 9–14. The two that change M0's output most: **F2** (κ trust bars in `requires` empty every judge-graded plan on day one) and **F8** (`unlocks` read by nothing, so `B1` fires on a single pair).

*(superseded)* **S18** (the format for planner fixtures, and the first five of them). **Authoring is finished:** S1 → S17 are done — the vocabulary, a strict format parser, a validated 22-field `TechniqueRecord`, an aggregating loader, a seven-rule integrity checker, a citation-resolution sweep, and **all 73 records enriched from their deep dives**, with both build orders and the production flywheel encoded as data.

🔴 **Before S18 writes a fixture, read `S17-REPORT.md` §4 and §9.** Three of `PLAN.md` §5's six sanity queries do not come out as `PLAN.md` says, the "Fixture format" example above is not achievable as written, and three of the first five fixtures have a correction waiting: fixture 2's expected plan is **empty**, fixture 4 needs `llm_api` granted, and fixture 5 asserts on `unavailable` rather than `pending`. A fixture written from the stale expectations will look like a planner bug at `EL-123`.

Notes carried into S18:
- **Eight rulings are open and six of them are decisions rather than work** (`S17-REPORT.md` §9): F2 (trust bars vs readiness bars — the one that empties every judge-graded plan on day one), F8 (`unlocks` read by nothing), F12 (`gates` holding two values), F13 (a cycle in `unlocks`), F5, F4, F3, F9, plus `PLAN.md` §5's own wording and two uncodified cross-cutting principles.
- **Nothing was changed to make a sanity query pass.** Q1, Q5 and Q6 are reported wrong rather than papered over, which is the point of answering them before a planner exists.

Notes carried into S17, kept for the record:
- **`H4.unlocks` already names `J3_cost_quality_pareto`** (`H:139`, "choose on that frontier (Section J3)"). S17 owns J3 and should check the edge reads correctly from the other side. It is the only J record reachable from H.
- **The C1 sweep is one section from closing.** S13 added `companion_checks: [C1_wilson_ci]` on `00-INDEX.md:35`'s authority; S14 carried it through D, S16 through G (G1, G5, G6, G7, G8 — G2/G3/G4 name `F1`/`B6` or nothing, each for a stated reason) and H (H2, H3 only; the rest produce explanations or money, not proportions). After I and J, every section has been decided and the question closes.
- **`E2_metric_outcome_check` is now named by `G4`** (`G:136`) and `E6_oracle_run` by both `H1` (`H:40`) and `H8` (`H:267`). All three were enriched by S15 and were not modified.
- **Finding F8 has a consequence for I and J:** `unlocks` is read by nothing in `AGENT.md` §3.5, so an ordering recorded only there gates nothing. I's canary-needs-history and CI-gate orderings should be written with a `requires` boolean if they are meant to hold back a plan, and left in `unlocks` alone if they are advisory. Decide per edge; do not copy G/H's gating by reflex.
- **`G6` is still the only over-abstention record anywhere** (S14). S16 encoded `G:195`'s pairing as far as the schema allows — all three numbers in `produces` — and it remains scoped to RAG answerables, so it still cannot serve `AGENT.md` §5's safety non-negotiable. Finding F9 is the field that would fix it.
- Line 112's range list is now partly superseded. **E4 `3–5 runs` is no longer empty** — S15 recorded `{runs: 3}` as a flagged interpretation. `F1 150–200 gold labels` and `F6 4–8 checks` are still correctly left empty, and F1 instead records its own single bound, `{fail_cases: 50}` (F:36).
- **Four doc figures have now been traced to cross-contamination between records**: the "3–5 runs noise floor" was E4's A/A figure quoted under C3's name (S14); "50–100 human labels" for F1 is A4's error-analysis sample (A:143) and H7's trace count (H:226, H:232) quoted under F1's name (S15); and F's 150–200 gold labels is **not** G3's "150+" claim labels (`G:102`), which is a single bound and is recorded (S16). H7's 50–100 is genuine and was not touched.

Open rulings **resolved** by S13:
- **Rule 4's residual** — resolved by scoping rule 4 to section A. See S9's note.
- **A7's rung** — still open, deliberately. S13 confirmed the corpus states no ordering for it and declined to invent one.

Open rulings carried into S14:
- **C1 "Any score, ever" is now reachable from A and B.** S13 added `companion_checks: [C1_wilson_ci]` to every A grader and to A7, on the authority of `00-INDEX.md:35` ("Put a confidence interval on every number"). The B statistics do *not* name C1 — they produce intervals of their own — and B2 names `B6_bootstrap_ci` instead, because `B:74` prescribes a bootstrap over pairs, not Wilson. S14–S17 still have to do the same for C–J.
- The three interpreted thresholds and four schema gaps listed under S13.
- **C1 "Any score, ever" has no faithful situation mapping.** `Situation` has no member meaning "a score exists". C1 triggers on the ten measurement members plus `small_sample`, which is deliberately narrower than the row; the real route is `companion_checks` from every grader and metric, which S13 adds.
- **Two vocabulary gaps in F.** F7 "Judge grades the wrong dimension" and F8 "Want better judge accuracy" have no `grader_trust` member; both are mapped to `new_judge_built`.
- **Section G collapses onto one member.** All eight G rows trigger on `rag_answer`, so `match()` cannot discriminate within G. **Mitigated, not closed, by S16:** the build order now yields four distinct plan states from that single member (`S16-REPORT.md` §3), but the eight symptoms the lookup names are still indistinguishable to `match()`.
- **`gates` cannot be null.** The schema types it `Gate`, so "the source states no gate" is written as `Gate.false`. 26 of 73 records are in that state.
