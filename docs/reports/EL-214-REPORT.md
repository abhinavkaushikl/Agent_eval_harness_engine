# EL-214 — One-shot run driver (stage S41)

**⚠ Depends on Gate 0**, transitively through EL-204/205/207, and on EL-201/202/206/211/213 (all
built). Built ahead of sign-off like the rest of M1's post-Gate-0 work. It is the capstone that
makes Gate 1 possible without a human driving six modules by hand.

**Status: done.** `pytest` 1190 + 1 skipped on 3.12 (11 new tests). `mypy --strict evalloop/` clean
on 43 files. Stdlib only. Not re-run on 3.10 (no 3.10 interpreter here).

**Prerequisite built this turn:** EL-214 cannot grade without the execution grader, which was
unbuilt, so **EL-207 was built first** (`EL-207-REPORT.md`) and EL-214 sits on it.

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/run.py` | `check(path, ...) -> RunResult`, the whole loop; `RunOutcome` (the three exit codes) |
| `evalloop/__main__.py` | `python -m evalloop check <path> --store <dir>` |
| `tests/test_run_driver.py` | 11 tests, including Gate 1's shape end to end |

## 2. The loop, in order
`check` runs: classify (EL-204) → assemble evidence (EL-213) + plan (the planner) → harvest
(EL-205) → grade (EL-207, in EL-206's sandbox) → store (EL-201) → render (EL-211), then writes
`summary.md`. It is **one shot**: a path in, a `RunResult` out, and it returns. No poller,
debouncer, event loop, worker pool, server or dashboard — those are M2 (T23–T26), and I added none.

## 3. The seven results you asked for

| # | Result | How |
|---|---|---|
| 1 | `check(path) -> RunResult`, loop in order, writes `summary.md` | As above; a verified end-to-end test |
| 2 | `Plan.unavailable` → printed, actionable permission request | `_permission_request` turns each unavailable record into "`<id>` needs: `<tools>` — grant it…", tools in the planner's order. §6 on why M1's own classifications don't trigger it |
| 3 | Content-hash skip, and the run says so | Whole-repo: an unchanged repo yields the same `run_id`, already in the store → every verdict reused, nothing graded, a `skipped` note. Per-artifact: `Run.lookup` reuses an unchanged artifact's verdict when other files changed. Tested both ways |
| 4 | Three honest exit codes | `RunOutcome`: `problem` → 1 (a failure), `clean` → 0 (graded, nothing failed), `undecided` → 2 (no oracle, all inconclusive, or an empty/all-pending plan). Mutation-checked that `undecided` is not collapsed into `clean` |
| 5 | `--no-llm`, zero egress, proven | The driver grades harvested oracles only and never constructs a router or clearance. A test runs the whole loop with `socket.connect`/`create_connection` patched to raise, and it completes and still catches the bug |
| 6 | Determinism | `run_id` = hash of the artifacts' contents + the seed, so the same repo and seed give the same id and the same `summary.md` bytes (tested on two fresh stores) |
| 7 | An all-pending / nothing-decided run exits cleanly and says what is missing | A function with no oracle → `undecided`, exit 2, a note naming what was missing, and a `summary.md` that reads as an honest account (EL-211's empty-plan rendering). §6 on the shape this takes in M1 |

**Mutation-checked.** Collapsing `undecided` into `clean`, and disabling the content-hash skip,
each failed the suite.

## 4. Gate 1, demonstrated
`test_a_broken_function_is_caught_with_no_instruction`: a toy repo with `total` that has a
deliberate off-logic bug and a harvested test is pointed at with defaults only (`check(repo,
store_dir=...)`), and the driver returns `problem`/exit 1 with `test_discount` → `failed` and
`test_sum` → `passed`. Zero instruction, caught by running — the 68%, not the 79% (A:31).

## 5. Harvested only, zero egress (option (b), warning #4)
M1 runs under EL-209's option (b): no outbound call without a clearance, and nothing issues one.
So the driver grades **harvested** oracles (EL-205) and never authors (EL-210), which would need a
clearance M1 does not have. `no_llm` defaults to `True` and is the guarantee the no-network test
pins. When EL-210 authoring becomes reachable (M2's capability broker issues clearances), the
driver gains a with-LLM path; today it is harvested-only by construction, not by a flag alone.

## 6. Calls I made — please check

1. **`run_id` is content-derived**, so determinism (req 6) and the whole-repo skip (req 3) are the
   same mechanism: an unchanged repo is the same id, already stored, so it is reused rather than
   re-graded. A changed repo is a new id and a new run. This is why re-running does not collide and
   does not re-grade.
2. **M1's classifiable situations never produce a missing tool, so the permission-request path is
   dormant in practice.** The classifier (EL-204) emits only `code_generation`, `sql_generation`,
   `api_endpoint`, `structured_extraction`; A1 needs `sandbox` + `test_runner` (both granted) and
   A5 needs none. So `Plan.unavailable` is empty for what M1 classifies. The mechanism is built and
   tested on a real `agent_action` plan that *does* have a gap; it will fire when a situation that
   needs a tool M1 lacks becomes reachable. Not a silent skip — there is simply nothing to request.
3. **The "nothing decided" case in M1 is reached by no-oracle or abstention, not an all-pending
   plan.** A1 has no evidence bar, so a classified `code_generation` file is never all-pending;
   the honest undecided outcome is "no runnable oracle" (a function without a test) or the file
   abstaining (a half-written or training-loop file). Both exit 2 and say what is missing, which is
   req 7's intent. A genuinely empty plan (a dead situation, warning #6) cannot arise from the
   classifier, because it never emits those six members — so the driver never silently renders an
   unexplained empty plan; it either grades, or says why it could not.
4. **Grading is scoped to flat top-level functions** (Gate 1's shape): the artifact is placed under
   its file stem and graded against a harvested test that imports it by that stem. A packaged import
   path is not reconstructed — a stated M1 limit. Methods, SQL/API artifacts and authored oracles
   are out of M1 grading scope.
5. **`store_dir` is a required argument.** `USER_EXPERIENCE.md` §6 has not chosen between the repo's
   `.evalloop/` and the user's home (the same open question EL-201/EL-202 flagged), so the driver
   does not choose either; the caller passes it.
6. **`wall_seconds` is the caller's** (A1's `timeout` once EL-015 lands), never a literal in grading
   logic — the same stance as EL-206/EL-207.

## 7. Warnings touched (M0 preamble)
- **#1 (Gate 0):** depended on transitively; flagged.
- **#2 (F2):** §4 of the summary renders readiness reasons from EL-213 via the plan; the driver
  passes them through and takes no side on F2.
- **#6 (six dead situations):** §6.3 — the driver never produces an unexplained empty plan, because
  the classifier cannot emit a dead situation; it reports no-oracle/abstention honestly instead.
- **#7 (EL-014):** a timeout surfaces through EL-207 as `failed`/`timeout` and feeds `problem`;
  inconclusive (a denied capability or an un-collectable oracle) feeds `undecided`, never `problem`.

## 8. Scope held
No `start`/`stop`, no session orchestrator, no worker pool, no queue, no local API, no dashboard or
SSE. One path in, one report out.

## 9. Rulings I need
1. Accept building ahead of Gate 0 (and that EL-207 was built first as the prerequisite).
2. **`store_dir` / summary location** (§6.5) — the `USER_EXPERIENCE.md` §6 question, still open.
3. **The flat-module grading limit** (§6.4): confirm Gate 1's toy repo is flat, or ask for package
   import reconstruction in M1.
