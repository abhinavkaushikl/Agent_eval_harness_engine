# EL-311 — SQL execution grading (result sets, never text)

**⚠ Depends on EL-305 + EL-306 (both done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_sql_execution_grader.py` 13 passed; `mypy --strict evalloop/`
clean on 58 files; standard library only. Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/grade/sql_execution.py` | `grade_sql(...)`, `Snapshot`, `build_snapshot`, `summarize`, `SqlGrade`, `SqlExecutionSummary`, `SqlJudge` |
| `tests/test_sql_execution_grader.py` | 13 tests over a seeded snapshot built in `tmp_path` |

## 2. The result — seven requirements
| # | Requirement | How |
|---|---|---|
| 1 | Schema-grounding: a hallucinated column is a HARD FAIL, `unknown_column`, separate from wrong-rows | the query runs on the snapshot and SQLite's own error decides: `no such column`/`no such table` → `unknown_column` (rung `schema`); a wrong-rows mismatch is `wrong_result` (rung `result_set`) — two different classes, two different rungs |
| 2 | Execute generated AND reference on a frozen snapshot; compare result sets, multiset unless ORDER BY | both run read-only on the snapshot; `_result_sets_equal` is `Counter`-equality, or ordered list-equality when the **reference** has `ORDER BY` |
| 3 | Reordered joins / renamed aliases that return the same rows → PASS; a bad column → hard fail | proven: a swapped-order, renamed-alias join matching the reference passes; `SELECT refund_total …` hard-fails `unknown_column` |
| 4 | Seed distinguishing rows so a plausible wrong query differs (A:36) | the snapshot seeds a **5,000** refund; `amount > 5000` vs `>= 5000` return different rows → caught as `wrong_result`. `build_snapshot` documents that the distinguishing rows are the caller's to seed |
| 5 | No reference → parse/execute/schema-grounded/non-empty/type-consistent, then a CROSS-FAMILY judge as the LOWEST rung, never the only one | structural gates run first; only if they pass is the injected `SqlJudge` consulted; with no judge the case is `inconclusive` (not a pass). A schema failure never reaches the judge (tested: `calls == 0`) |
| 6 | NEVER compare query text | correctness is result sets only; a source scan asserts no `difflib`/`SequenceMatcher`/`levenshtein`/`.ratio(`/`fuzz`/`jaccard`/`edit_distance` appears in the module |
| 7 | Carries `A1_execution_based`; the pass rate travels with its Wilson interval (C1) | every `SqlGrade.record_id == "A1_execution_based"`, `ladder_rung == 1`; `summarize` returns the pass rate over *decided* cases with `wilson_interval` |

## 3. Calls I made
1. **Schema-grounding by execution, not parsing.** No SQL parser is allowed (and no text comparison
   is wanted), so I run the query and read SQLite's error. This is exactly the ticket's intent — the
   database, not a guess, says a column is hallucinated — and it keeps `unknown_column` cleanly apart
   from `wrong_result`.
2. **A revealing envelope interaction, classified honestly.** EL-305's default-deny rejects any
   non-read leader *before* the DB, so a misspelled `SELCT …` surfaces as `ReadOnlyViolation`, not a
   SQLite syntax error. I split that branch on the offending keyword: a genuine write verb
   (`DELETE`, `DROP`, …) → `runtime_error` ("generated a write, not a read"); anything else (a
   malformed/unknown leader) → `syntax_error`. A SELECT-led malformed query still reaches SQLite and
   is classified `syntax_error` from its error.
3. **Inconclusive is never a failure.** No-reference-no-judge, an empty no-reference result, and a
   reference that will not run are all `inconclusive` with a reason. `summarize` computes the Wilson
   pass rate over `passed + failed` only and reports `inconclusive` separately — a false pass or a
   charged-as-failed inconclusive would both be the dishonesty EvalLoop exists to prevent.
4. **Everything runs under EL-305 on a snapshot.** `Snapshot` reaches the DB through the EL-306
   SQLite connector and the read-only envelope, with an uncapped grant (a truncated result would be a
   false mismatch when comparing sets). Writes/end-state (EL-314) and RAG (EL-312/313) are out of
   scope.

## 4. Full-suite note
`pytest` 1331 passed, 2 skipped, 1 failed — the F-G1a `testcases running/` demo-folder finding,
unrelated to EL-311. (Count is the full suite after EL-311/EL-312/EL-313 landed in the same session.)

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **Empty result, no reference → `inconclusive`** (§3.3): confirm. An answerable question whose true
   answer is genuinely empty would need a reference or a judge to confirm; I refuse to score it a pass
   on its own.
3. **Cross-family enforcement** (§2, requirement 5): `SqlJudge` carries a `family` string but this
   module does not verify it differs from the generator's family — that pairing is the caller's
   (M4's) responsibility. Say if you want the grader to assert it.
