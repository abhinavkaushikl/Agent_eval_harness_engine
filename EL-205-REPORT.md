# EL-205 — Oracle harvester (stage S34)

**⚠ Depends on Gate 0, which is not signed off.** The dependency is transitive, through EL-204,
which was also built ahead of the gate. Nothing in Gate 0's open rulings touches how an oracle is
found.

**Status: done.** `pytest` passes 1066 tests (40 new) on 3.12. `mypy --strict evalloop/` is clean on
34 files, pinned to 3.10. Standard library only. **Not re-run on 3.10:** no 3.10 interpreter is on
this machine.

---

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/grade/oracles/harvest.py` | `harvest(root, artifact, *, baseline=None) -> Harvest`, plus `Oracle`, `Provenance`, `Component`, `Gap`, `Excluded`, `Unsearched`, `OracleKind`, `Expectation`, `BaselineStatus` and `HarvestError` |
| `evalloop/grade/__init__.py`, `evalloop/grade/oracles/__init__.py` | Package docstrings and re-exports |
| `tests/test_oracle_harvest.py` | 40 tests, almost all on small repositories built in `tmp_path`, plus the real-repo done-when |

**EL-201's types are reused, not duplicated.** Confidence is `memory.case.OracleConfidence`, the
hash is `memory.case.content_hash`, and the baseline is a `memory.metric_store.Run`. An `Oracle`
therefore carries exactly the `oracle_id`, `oracle_confidence` and `oracle_hash` that `CaseResult`
stores.

## 2. The seven requirements

| # | Requirement | How it is met |
|---|---|---|
| 1 | Three kinds, `ast` only | **Tests:** pytest's default collection rules; linked only when the test references the artifact's own symbol, resolved through imports, re-exports, relative imports and attribute chains. **Schemas:** dataclass, `TypedDict` and `BaseModel` classes named in the signature, with nested and inherited schemas; JSON Schema files referenced by path. **Type hints:** the artifact's own signature |
| 2 | Never import or execute repo code | Bytes → PEP 263 decode → `ast.parse`, and nothing else. A test plants a conftest, a package `__init__`, a module and a test file that each write a sentinel file and `raise SystemExit` if imported. The harvest succeeds, the sentinel never appears, and nothing new lands in `sys.modules`. A source scan bans `importlib`, `runpy`, `subprocess`, `__import__`, `exec(`, `eval(`, `compile(` and `pickle` from the module |
| 3 | HIGH, with provenance that resolves | `Oracle.__post_init__` refuses anything but HIGH (tested). `Provenance` is path, line, end line and kind. The real-repo test opens every file and checks that the line holds `def <name>` or `class <Name>` |
| 4 | Nothing is an answer, and the reason reaches the report | Empty `oracles` and a `reason` that names each missing kind and why, ending with ARCHITECTURE.md §9's rule. `render()` includes the reason (tested). Files that could not be parsed are listed in `unsearched`, and the test gap counts them |
| 5 | A test already failing before the change is identified | §4 below |
| 6 | Deterministic ordering | Sorted walk. Oracles ordered by kind, path, line, id. Closures keyed by path and name. Harvesting twice gives equal results and identical `render()` text (tested) |
| 7 | Run against this repository | §3 below |

**Mutation-checked.** I broke ten guarantees one at a time, and each made the suite fail:
- product code followed into test closures (this also made the suite **9.5 s instead of 1.0 s**);
- autouse fixtures allowed to link;
- the baseline ignoring `oracle_hash`;
- skipped tests not excluded;
- virtualenvs walked;
- the hash keyed by line;
- a conditional `xfail` counted as an expected failure;
- fixtures not followed;
- LOW allowed;
- symlinks walked.

## 3. This repository, as the "real repo"

**The ticket's count is stale.** It says 16 test modules; there were 22 before this ticket and 23
after it. The walk also skipped about 40 of mypy's own `test_*.py` files in `.venv`, which a naive
glob would have harvested. Each harvest takes about 0.2 s. None of these harvests left a file
unparsed or excluded a test.

| Function | Tests | Schemas | Type hints |
|---|---|---|---|
| `evalloop/stats/proportions.py::wilson_interval` | **8** (4 in `test_stats_corpus_examples.py`, 4 in `test_stats_properties.py`) | `Interval` (dataclass, return) | `(successes: int, n: int, confidence: float) -> Interval` |
| `evalloop/memory/episodic.py::EpisodicStore.why` | **11**, all in `test_episodic_store.py` | `Why` (dataclass, return; 3 components with nested `PlanEntry` and `Trigger`) | `(episode_id: str, record_id: str) -> Why` |
| `evalloop/classify/heuristics.py::classify_source` | **8**, all in `test_classifier.py` | `ClassifierResult` (dataclass; 2 components with nested `Finding`) | `(source: str \| bytes, *, name: str) -> ClassifierResult` |

**I cross-checked the counts against grep.** There are 11 `.why(` call sites and 11 `why` oracles,
and 8 `classify_source` test functions and 8 oracles.

Three details from the run:
- **`test_proportion_inputs_are_checked` is linked through its decorator.** The reference is a
  lambda inside `parametrize`, at line 122, above the `def` at line 135.
- **Each `why` test is linked by method resolution.** It annotates its `store: EpisodicStore`
  parameter and calls `.why`.
- **One `why` test's closure has 24 components.** These are its `path` and `store` fixtures, four
  helpers, two module constants, the YAML fixture loader in `tests/planner_fixture.py`,
  `LIVE_PATHS` in `test_planner_fixtures.py`, and `require_fixture_dir` in `conftest.py`. **None
  is product code.**

**A fourth function shows the empty case.** `classify/heuristics.py::_sql_shaped` gets a type-hint
oracle only, plus *"no test in the 23 test file(s) searched references _sql_shaped"*. That is
correct: it is covered only through `classify_source`, and a test of one product function is not
an oracle for the functions it happens to call.

## 4. "Already failing before the change"

Whether a test failed on the pre-change code is a fact about *running* it, and this ticket runs
nothing. So the harvester reports the two kinds of evidence that exist without running, and
refuses to guess past them:

- **Declared** (static). An unconditional `pytest.mark.xfail` or `unittest.expectedFailure` makes
  `expectation = expected_failure`. The mark can sit on the test, its class, or a `pytestmark`.
  `skipif`, `skipIf`, `skipUnless` and `xfail(condition)` are `conditional`, because evaluating
  the condition would mean running code; even `skipif(True)` stays conditional. An unconditional
  skip is **excluded**, listed with its marker: a test that never runs decides nothing.
- **Recorded.** `baseline` is a metric-store `Run` judged on the pre-change code. A matching
  `oracle_id` counts **only if `oracle_hash` matches**. A test edited since the baseline is
  reported as `changed`, never as passing or failing. The other statuses are `failed`, `passed`,
  `inconclusive`, `conflicting`, `not_in_baseline` and `no_baseline`.

**`Oracle.already_failing`** is `True` on either kind of evidence, `False` only when the baseline
saw identical content pass, and **`None` — unknown — otherwise.** All of this is tested.

**The contract for EL-207:**
- store each oracle's `oracle_id` and `oracle_hash` exactly as harvested, or no later baseline can
  match them;
- while `already_failing` is `None`, report a failure as failing but **not attributed to the
  change**.

## 5. Carry for M3: can it answer "did this test change between runs?"

**Yes, from what EL-201 already stores.** `oracle_hash` is the hash of the oracle's closure: the
test with its decorators, every fixture, helper and constant it pulls in, autouse fixtures, setup
methods, class and module marks, and unresolved fixture names. Each piece is hashed from its own
source text, keyed by path and name, never by line.

- **The hash changes** for: a weakened assertion, a changed constant, a changed helper, an added
  `xfail`, a changed fixture, and a changed autouse fixture (one test each).
- **It does not change** when code moves down the file, an unrelated test is added, or an unused
  helper is edited (tested).

**It cannot see:**
1. **Data a test reads at run time.** In this repository that is the important hole: the planner
   tests compare against `tests/fixtures/planner/*.yaml`, which *are* expected outputs, and editing
   one changes no hash.
2. **Plugin fixtures** (listed in `unresolved`), pytest configuration and `addopts`, and product
   code. Product code is the artifact, not the oracle.
3. **An import that redirects a test to a different function.** That doesn't change the test's
   text. It **unlinks** the test, so the oracle disappears from the artifact's harvest and
   `diff_runs` reports the case as absent. **M3 must treat a vanished oracle as a signal, not only a
   changed one.**

**What M3 can only say with help.** `Oracle.components` holds each piece's own hash, so it can say
*which* piece changed. But `CaseResult` persists only the composite hash. M3 needs a schema v2 that
stores components, or it has to re-harvest the old revision.

## 6. Calls I made — please check these

1. **HIGH is about who wrote it, not how strong the link is.** How a test reaches the artifact
   (directly, via a fixture, via a helper) is in `evidence`, and it doesn't change the tag.
2. **Method links are a heuristic.** A test is linked when it references the class and accesses
   `.m`. For a common method name (`open`, `close`) on a class the test also uses, that can
   over-link. Direct `C.m` references are exact.
3. **Type hints are HIGH oracles because AGENT.md says so, but they decide almost nothing.** In a
   mypy-strict repository every artifact has one, so "no oracle at all" will be rare here. EL-214
   should ask `of_kind(OracleKind.test)` before claiming an execution oracle exists.
4. **I left `case_id` to EL-207/EL-214.** One test can serve two artifacts, so `case_id` must
   include the artifact as well as the `oracle_id`.
5. **The hash is computed from raw source text** (normalised line endings, dedented), not from
   `ast.dump`, whose output changes between Python versions. Otherwise a Python upgrade would flag
   every test as changed.
6. **The package-level `harvest` (the function) shadows the module `harvest`.** The ticket fixes
   the file name; a test reads the module through `sys.modules`.

## 7. Known limits

- **pytest configuration is not read.** That covers `python_files`, `python_functions`,
  `testpaths` and `addopts`. `tomllib` is 3.11+, and the floor is 3.10. Default rules only.
- **Not seen:** nested test classes; tests generated at run time; `pytest.skip()` called inside a
  test body; per-parameter marks (`pytest.param(..., marks=xfail)`); doctests; aliases made by
  assignment in product code (`match_records = match`).
- **Product code under a `tests/` or `test/` directory** is treated as test-side.
- **`build/` directories are walked.**
- **No file-size cap.** The M2 poller owns that limit (ARCHITECTURE.md §9), and I did not invent
  a number here.

## 8. Rulings I need

1. **Accept or reject building ahead of Gate 0** (as for EL-201 and EL-204).
2. **Where M1's baseline comes from.**
   - (a) The previous `evalloop check` run in the metric store.
   - (b) EL-214 runs the harvested tests on the committed version first. That needs git, and the
     git sensor is T20, in M2.
   - (c) No baseline in M1: every failure is reported as failing but unattributed.

   **Without (a) or (b), M1 can never say "your change caused this", only "this fails".**
3. **Is a type-hint-only harvest "an oracle exists" for the ladder?** I recommend no: decide per
   kind.
4. **Persist `components` in a metric-store schema v2,** so M3 can name the piece of an oracle
   that changed without re-harvesting history.
