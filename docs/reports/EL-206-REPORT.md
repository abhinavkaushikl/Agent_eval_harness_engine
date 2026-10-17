# EL-206 — Sandbox runner (stage S35)

**Status: done.** `pytest` passes 1098 + 1 skipped on 3.12 (33 new sandbox tests; the skip is the
Linux-only memory-cap test). `mypy --strict evalloop/` is clean on 36 files. Standard library
only. Verified on **macOS 26.6, arm64, CPython 3.12** — this repo's platform. Not re-run on 3.10
(no 3.10 interpreter here) or on Linux (no Linux host here; Linux rows are stated as unverified —
see §5).

**Depends on EL-201 (done) and EL-014 (decided).** It does **not** depend on Gate 0.

---

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/grade/verdict.py` | `Limits`, `SandboxResult`, `Outcome`. Imports EL-014's `Verdict`/`FailureClass`/`TimeoutCap`/`Timeout` from `memory/case.py` — **no second copy** |
| `evalloop/grade/sandbox.py` | `run_sandboxed(...) -> SandboxResult`, `SandboxError` |
| `evalloop/grade/__init__.py` | Re-exports the sandbox alongside the oracle layer |
| `tests/test_sandbox.py` | 33 tests, each a proof against a real child process |

## 2. The seven results you asked for

| # | Result | How it is met |
|---|---|---|
| 1 | A result record: stdout, stderr, exit, duration, limits, command, seed | `SandboxResult`, frozen. Outcome via `.classify()` using EL-014's types, imported not redefined |
| 2 | CPU, address space, file size, open files, no network, wall-clock, tempdir, scrubbed env | All present. Address space is enforced on Linux and **reported unenforceable on macOS** (§5) — the honest finding, not a silent no-op |
| 3 | Tests that **prove** each, not assume | infinite loop killed at the cap; a write outside the tempdir refused and the file never appears; a network call fails closed and is **inconclusive**, distinct from a logic failure; the child's env holds no planted credential; a grandchild does not outlive the group kill |
| 4 | Clean teardown on timeout/signal/exception | `start_new_session=True` + `killpg(SIGKILL)` in a `finally`; the workdir is `rmtree`d in every return path |
| 5 | Limits inspectable, so a report can say **which** cap was hit | `SandboxResult.killing_cap`, `.enforced_limits`, `.unenforceable_limits`, `.limits` |
| 6 | Byte-identical across two runs, or nondeterminism recorded | Same command twice → identical stdout/stderr/exit/signal/outcome (tested). `PYTHONHASHSEED` pinned to `seed` and recorded; env built from scratch; `duration_seconds` is the one recorded nondeterminism and is never compared |
| 7 | A stated platform section, and what a sandbox **cannot** contain | The module docstring's two sections (§5 summarises) |

**Mutation-checked.** I broke four guarantees one at a time; each failed the suite: dropping the
"not timed-out" guard on network detection (1 fail), removing the kill-on-network signal (3),
allowing file-writes (1), and failing open instead of closed (1). The orphan-reaping guarantee has
its own test and a separate manual verification; I did not mutate `start_new_session`, because with
it off `killpg` would target the test runner's own process group.

## 3. EL-014, enforced as decided

- **A timeout is a failure.** Wall-clock → `failed`/`timeout`/`wall_clock`; CPU cap (SIGXCPU) →
  `failed`/`timeout`/`cpu_time`. Both carry the cap and the limit in force.
- **A denied capability is inconclusive.** A refused network egress → `inconclusive` with a reason,
  never `runtime_error`, so a missing grant is never charged to the artifact (`ARCHITECTURE.md` §9).
- **The sandbox does not guess a pass/fail it cannot see.** A process that merely exited (0 or an
  ordinary non-zero) gets `Outcome(verdict=None)` — "it ran, the grader decides". Whether exit 1
  means a failed assertion (`wrong_result`) or an import error (`syntax_error`) is EL-207's reading
  of the test framework, not the sandbox's.

## 4. The blocking dependency EL-015 — and how I did not hard-code around it

**EL-015 is decided but not implemented: there is no `parameters` field** on the schema or on
`A1_execution_based` (I checked). The ticket says read the 10-second timeout from
`A1_execution_based.parameters` and "do not write `timeout=10` in this module." I did neither: I did
not read a field that does not exist, and I did not invent the number. Instead:

- `Limits.wall_seconds` is a **required argument**. The caller supplies it — from
  `record.parameters["timeout"]` once EL-015 lands, and from a test value until then. There is no
  `10` anywhere in `sandbox.py` or `verdict.py`.
- The other caps are the sandbox capability's own grant parameters (EL-015's own words: "null until
  granted; never defaulted; reported as unset"). They default to `None`, and the sandbox enforces
  only the ones that have a value. `deny_network` is the one exception — egress is denied **by
  default** per `ARCHITECTURE.md` §9.

**This is the raise-don't-work-around path (`CLAUDE.md` §7.5): EL-015 must be implemented before
EL-207 can read these numbers off the record.** Until then, EL-207/EL-214 pass them explicitly.

## 5. Platform honesty — what is actually enforced

Verified on macOS 26.6 / arm64 / CPython 3.12. Linux rows are documented behaviour, **not verified
on this machine**, and the module says so rather than claiming it.

| cap | macOS (verified) | Linux (documented, unverified) |
|---|---|---|
| wall-clock | parent kills the group | same |
| CPU time | `RLIMIT_CPU` → SIGXCPU | same |
| file size | `RLIMIT_FSIZE` → SIGXFSZ / EFBIG | same |
| open files | `RLIMIT_NOFILE` → EMFILE | same |
| core dumps | `RLIMIT_CORE` = 0 | same |
| **address space** | **not enforceable** — `RLIMIT_AS`/`DATA`/`RSS` cannot be lowered below the current value and the hard limit is unlimited; memory is bounded only by the wall-clock cap | `RLIMIT_AS` enforced |
| network egress | Seatbelt `(deny network* (with send-signal SIGKILL))` → killed on any network op | **not contained here** — needs a network namespace (`unshare`), not attempted |
| file writes | Seatbelt confines writes to the workdir | **not confined** — only `RLIMIT_FSIZE` |

If a platform cannot contain the network and `deny_network` is set, the sandbox **fails closed**:
it does not run, and returns `inconclusive` ("cannot be contained"). It never runs untrusted code
with the network open while reporting it denied (tested).

### What a subprocess sandbox CANNOT contain — stated plainly
It runs the child **as the current user**. So:
- **It does not stop the child *reading* the developer's files** — only writes are confined, and
  only on macOS. A secret on disk is not protected; a secret in the parent's environment is,
  because the child's environment is built from scratch and never copied.
- **Seatbelt is deprecated by Apple** and is best-effort, not a guaranteed boundary. No VM/container
  (out of scope, `PLAN.md` T11).
- **Kernel/sandbox escapes, privilege escalation, hardware side channels** are out of reach.
- **Output volume before the wall-clock cap is only loosely bounded** — captured output is
  truncated to `max_output_bytes`, but a chatty child is bounded by time, not that cap.
- **On macOS, memory is not capped**, so a memory bomb is stopped only by the clock.
- **One network-attribution ambiguity on macOS:** a network op kills with SIGKILL; so does an OS
  out-of-memory kill (memory is uncapped here). Both are reported as a halted run, never as a wrong
  answer, so the ambiguity never charges the artifact — it only mislabels a rare OS-OOM as "network
  denied". The unified sandbox-violation **log is deliberately not used**: macOS samples those
  reports, so a missing entry would be a false negative (I confirmed the sampling — a denied
  external connection produced no log entry while a localhost one did).

## 6. Calls I made — please check

1. **Network containment is Seatbelt `sandbox-exec`.** It is Apple-deprecated but present and
   working on 26.6. It is the only stdlib-reachable way to deny egress and confine writes on macOS
   without root. The alternative (a `unshare` network namespace) is Linux-only and needs user
   namespaces. I used Seatbelt on macOS and documented the Linux gap rather than pretending.
2. **Distinguishing a denied network from a logic failure is done by a kill signal, not the log.**
   `(with send-signal SIGKILL)` kills the child the instant it touches the network; the parent
   knows it did not send that kill and it is not a resource signal, so it attributes it to the
   network. This is reliable where the log is not.
3. **The child's environment is built from scratch, not scrubbed.** The module reads *no* parent
   variable, so "credentials in a grader: impossible by construction" is literal, and it satisfies
   EL-209's "only the capability layer reads the environment" source scan without an exception.
4. **The sandbox returns `verdict=None` for an ordinary exit** (see §3). If you expected the result
   to always carry a resolved verdict, this is where I drew the line and why.
5. **`max_output_bytes` (10 MiB default) is a harness safety constant, not a corpus number** —
   EL-015 explicitly scopes such harness constants out of the registry. It is an argument.

## 7. Out of scope (untouched)
Grading, hidden-test isolation, partial credit, the compile/logic split, the mutation self-check
and the Wilson CI are **EL-207** — the sandbox runs a command and reports facts; it does not grade.
SQL/API execution (Track V), judging (M4), containers/VMs (`PLAN.md` T11). The row cap stays
unenforced: it is `null` until a database grant supplies it (Track V).

## 8. Rulings I need
1. **EL-015 must land before EL-207.** Confirm EL-207 should read `timeout`, `float_tolerance` and
   the 5% mutation bar from `record.parameters` (per EL-015), and that until then the caller passes
   them explicitly — not a literal in grader logic.
2. **The macOS memory gap.** Accept that on macOS a memory limit is reported unenforceable (and a
   memory bomb is bounded only by the clock), or require the capability broker to refuse to grade
   on a platform that cannot cap memory. I recommend accepting it for M1 and revisiting in M2.
3. **Linux is unverified here.** Someone should run the suite on Linux before Track V relies on the
   namespace/`RLIMIT_AS` rows.
