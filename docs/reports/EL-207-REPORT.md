# EL-207 — Execution grader (stage S36–S37)

**⚠ Depends on Gate 0** (through EL-205), and on EL-206 and EL-015. Built ahead of sign-off like
the rest of Group 3. EL-015 is unimplemented, so A1's numbers are arguments, not literals (§4).

**Status: done.** `pytest` 1179 + 1 skipped on 3.12 (18 new tests). `mypy --strict evalloop/` clean
on 41 files. Stdlib only. Not re-run on 3.10 (no 3.10 interpreter here).

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/grade/execution.py` | `grade_execution`, `mutation_self_check`, `attributable_regressions`, `GradeReport`, `MutationReport` |
| `evalloop/grade/sandbox.py` | **extended** with `cwd_subdir` (run the command in a subdir of the workdir — needed for isolation) |
| `tests/test_execution_grader.py` | 13 tests | `tests/test_mutation_selfcheck.py` | 5 tests |

## 2. The nine results
| # | Result | How |
|---|---|---|
| 1 | Grade by running, never reading | `grade_execution` runs the oracle against the artifact in EL-206's sandbox; an injected `conftest.py` reports per-test outcomes on stdout. Nothing inspects the source to form an opinion |
| 2 | Hidden-test isolation, **proved** | §3 — the proof caught a real hole |
| 3 | Partial credit present, headline = full-pass | `GradeReport.partial_credit` is tracked; `full_pass` (all conclusive cases passed) is the headline. A mutation promoting partial credit to the headline fails the suite (H:170) |
| 4 | Compile-vs-logic split | The artifact is parsed first: a syntax error is `failed`/`syntax_error` without running; an assertion is `wrong_result`; any other exception is `runtime_error`. All from A:39, all stored, all distinct |
| 5 | Mutation self-check vs A:38's 5% | `mutation_self_check` mutates the artifact (flip comparisons, swap operators, nudge constants) and runs each mutant through the oracle; a strong oracle catches them (≤5% survive), a weak one does not. The 5% rule is cited in the report |
| 6 | C1 Wilson interval | `GradeReport.pass_rate` returns the Wilson interval from EL-203 and **raises** rather than give a bare rate with no conclusive case |
| 7 | A broken function caught (my fixture) | `test_a_broken_function_is_caught`: a toy off-logic bug comes back `failed`/`wrong_result`, headline not full-pass |
| 8 | Equivalent-but-different not wrong | A loop-based `total` that behaves identically fully passes — execution compares behaviour, not text (A1's anti-pattern) |
| 9 | Pre-existing failure not attributed | `attributable_regressions(report, baseline)` drops a case already failing on the same oracle content in the EL-205 baseline |

**Mutation-checked.** Removing the compile/logic split, collapsing `wrong_result` into `runtime_error`,
promoting partial credit, and dropping the import-mode isolation each failed the suite.

## 3. Hidden-test isolation — the proof found a real bug

The artifact runs with its working directory set to `subject/` (which holds only the artifact); the
oracle is a sibling the artifact is never given a path to. The proof test (`test_the_artifact_cannot
_read_the_oracle_that_grades_it`) runs a **hostile artifact** that lists its cwd, tries
`open("test_oracle.py")`, and tries `import test_oracle`.

**It caught a genuine hole.** pytest's default "prepend" import mode puts the oracle's directory on
`sys.path`, so `import test_oracle` **succeeded** — the artifact could read its own test. The fix is
`--import-mode=importlib`, which does not touch `sys.path`; the proof now shows `import=False`,
`open=False`, and an oracle-free cwd. This is exactly the "a proof, not a convention" the ticket
asked for: a convention would never have surfaced the sys.path leak.

**The honest boundary:** pytest and the artifact share one process, so an artifact that scans the
whole filesystem by absolute path (`../../..`) could still reach the oracle. That is reward-hacking;
full read-isolation needs process separation, which is M3 (the sandbox docstring lists the same
limit). M1 isolates the artifact's environment — its cwd and import graph — not a determined
adversary.

## 4. EL-015 and A:35 — calls I made
- **A1's numbers are arguments.** `float_tolerance` (1e-6) and `max_mutant_pass_rate` (5) are the
  record's `parameters` (EL-015), which is unbuilt, so the caller passes them; there is no literal
  threshold in this module's logic. The 5% appears only as the text of A:38's rule in the report.
- **A:35's tolerant comparison (row order, aliases, float tolerance) is not exercised by pytest
  execution**, because the harvested oracle performs the comparison in its own asserts — which is
  *why* equivalent-but-different passes (req 8). `float_tolerance` is threaded for provenance but
  not consumed here; A:35's comparator belongs to the deterministic grader (EL-208) and Track V's
  SQL grader, where the grader itself compares. Flagging this reading.
- **I extended EL-206 with `cwd_subdir`** (run in a workdir subdir), which the isolation layout
  needs and EL-214 will reuse. It validates the path stays inside the workdir. Please okay it.

## 5. Warnings touched (M0 preamble)
- **#1 (Gate 0):** depended on through EL-205; flagged.
- **#7 (EL-014):** a timeout is `failed`/`timeout`; a wrong answer is `wrong_result`; a denied
  capability or an un-collectable oracle is `inconclusive`, never charged to the artifact.

## 6. Rulings I need
1. Accept building ahead of Gate 0.
2. Accept the `cwd_subdir` addition to the sandbox (§4).
3. **Isolation boundary (§3):** M1 isolates cwd + import graph; full filesystem-read isolation is
   deferred to M3's reward-hack sandboxing. Confirm that split.
4. **A:35 comparator (§4):** confirm it lives in EL-208 / Track V, not here.
