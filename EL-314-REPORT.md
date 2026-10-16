# EL-314 — End-state verification

**⚠ Depends on EL-306 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_end_state.py` 7 passed; `mypy --strict evalloop/` clean on 61
files; standard library only. Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/grade/end_state.py` | `verify_end_state`, `restore_snapshot`, checks (`RowsEqual`, `NoRows`, `FileExists`, `FileAbsent`, `FileContains`), `AgentClaim`, `EndStateGrade` |
| `tests/test_end_state.py` | 7 tests over a seeded snapshot built in `tmp_path` |

It reuses EL-311's read-only `Snapshot` (envelope + SQLite connector), so the end state is read
through the same read-only path as the SQL grader.

## 2. The result — five requirements
| # | Requirement | How |
|---|---|---|
| 1 | A verdict from the REAL resulting state, read through a read-only connector | `RowsEqual`/`NoRows` read rows via the read-only `Snapshot`; `FileExists`/`FileAbsent`/`FileContains` stat disk. The verdict is `passed` iff every check matches the real state |
| 2 | A false "done" / "tests pass" while the state is wrong is CAUGHT | `test_a_false_done_is_caught`: `AgentClaim(done=True, "all orders shipped")` but two orders still open → `failed` / `wrong_result`. The verdict comes from the rows, not the claim |
| 3 | The transcript's self-report is never used as evidence | the `AgentClaim` is echoed into `claim_ignored` ("…not used") but never read by the verdict logic — `test_the_claim_does_not_change_the_verdict` shows the verdict is identical for `done=True` and `done=False` |
| 4 | Setup/writes run in a scratch schema / restored snapshot; the audit proves the live schema was untouched | `restore_snapshot(live, scratch)` copies the DB; the agent mutates the scratch copy, the live DB is unchanged, and the verifier reads the scratch copy read-only. The envelope's audit shows **every statement is a `read`** (no write/DDL kind) |
| 5 | Carries `A2_end_state_verification` and honours its requires (resettable environment) | every grade is tagged `A2_end_state_verification`, rung 2; A2's own requires is honoured via `evaluate_readiness`, and the resettable-environment precondition is enforced — no reset → `inconclusive` with reason |

## 3. Calls I made
1. **A ticket/registry seam, flagged not papered over.** The ticket says A2 "requires (resettable
   environment)", but in the registry `A2_end_state_verification.requires` is **empty** — the
   `environment_resets_per_run` precondition is authored on the *agent* records **H2–H8**, not A2. I
   did both: carried A2 and honoured A2's own (empty) requires through `evaluate_readiness`, **and**
   enforced the resettable-environment precondition explicitly (the ticket's intent / H's rule),
   returning `inconclusive` when the environment is not resettable. `require_resettable=False` waives
   it deliberately for a caller who knows the environment is clean by other means.
2. **The claim is recorded, never consulted.** `AgentClaim` exists so the run keeps a record of what
   the agent *said*, but the verdict function reads only the checks. This is the "transcript is never
   evidence" rule made structural: there is no code path from the claim to the verdict.
3. **Read-only, provably.** The verifier reaches the DB only through the EL-305 envelope, so it
   cannot write, and the audit log makes that checkable (the test asserts `kinds <= {"read"}`). The
   scratch/restored snapshot is where any setup or agent write lands.
4. **`wrong_result` for a wrong end state.** A state that does not match is a logic failure, classed
   `wrong_result` (EL-014), listing which checks failed. A missing DB/files root makes the relevant
   check fail with a clear reason rather than crashing.

## 4. Full-suite note
`pytest` 1338 passed, 2 skipped, 1 failed — the F-G1a `testcases running/` demo-folder finding,
unrelated to EL-314.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **The resettable-environment seam** (§3.1): I enforce `environment_resets_per_run` as an explicit
   precondition even though A2's registry `requires` is empty, because end-state verification on a
   dirty environment is untrustworthy. Confirm that is the behaviour you want, or say if A2's record
   should instead carry `requires: {environment_resets_per_run: true}` (a registry change I would
   raise separately, not make inside this ticket).
3. **Check vocabulary**: five check types today (row-set equality, no-rows, file exists/absent/
   contains). Name any other end-state assertion you want as a first-class check (e.g. a scalar
   aggregate, a file hash).
