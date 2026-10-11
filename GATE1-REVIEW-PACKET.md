# Gate 1 — Review packet

**Read this first, it changes what the rest of the packet proves.** This gate ran under **Reading A:
EvalLoop re-ran a test that already existed in the toy repo.** It did not author a test from the
function's signature. So what is demonstrated below is an evaluation harness that harvests an
existing human-written test, runs the artifact against it in a sandbox, and reports the result with
its statistics and its three honest states — **a test runner with honest accounting, not yet an
evaluation system that invents the oracle.** The stronger claim ("no test existed, EvalLoop wrote
one from the signature and caught the bug") is **Reading B**, and it cannot run in a live
`evalloop check` in M1: authoring (EL-210) is an outbound model call, and M1 runs under EL-209's
option (b) — no egress without a `Clearance`, and nothing in M1 issues one. Reading B is proven only
in EL-210's test suite against a fake transport (§10). **I am telling you this in the first
paragraph because a gate that quietly ran under Reading A while sounding like Reading B would be the
exact dishonesty this milestone is built against.**

Gate 0 is **not** signed off, and everything this packet exercises was built ahead of it (§9). Every
proportion below carries a 95% Wilson interval; counts and coverage fractions are labelled as such,
because an interval on a raw count would be theatre.

---

## 1. Which reading of "caught"

**Reading A.** The toy repo (`.gate1/broken/`) contains `overlap.py` **and** a human-written
`tests/test_overlap.py`. EvalLoop harvested that test (EL-205, tagged HIGH — a human wrote it), ran
the artifact against it in the sandbox (EL-207), and reported the failures. It re-ran someone else's
test. That demonstrates the harvest → execute → store → render path and the statistics and states
layered on it; it does **not** demonstrate authoring an oracle from a bare signature.

Why Reading B could not run here: EL-214's driver grades harvested oracles only. Authoring would
call a model, which option (b) forbids without a clearance M1 never issues. So a toy repo with **no**
test would, in M1, produce "no runnable oracle → UNDECIDED (exit 2)", not a caught bug. I did not
build a no-test repo and claim a catch it cannot make.

The toy repo lives at **`.gate1/`** (a dot directory) on purpose — see finding **F-G1a** in §9: when
it sat at `gate1/`, EvalLoop's own harvester counted the toy repo's tests as this project's tests and
broke the suite. The relocation is a symptom reported, not fixed.

---

## 2. The oracle run, first (E6_oracle_run)

Before any claim about the broken function: a **known-correct** implementation
(`.gate1/oracle_correct/overlap.py`) was pushed through the same pipeline. If it does not score
100%, the harness is broken and this gate is void, whatever it says downstream
(`E-when-a-number-looks-wrong.md:219` — the team that burned a week on "a weak model" that was really
a 30-second timeout).

**Result: 100.0% [43.9, 100.0], n=3, inconclusive 0 — CLEAN, exit 0.** The harness scores the
correct solution a perfect 3/3. **The gate is not void.** (The interval is wide because n is 3; it is
reported honestly rather than hidden. A wide interval on a correct solution is still a passing oracle
run — the point of E6 is that it is not *below* 100%, and it is not.)

---

## 3. Verbatim transcript of `evalloop check` (no editing)

```
$ evalloop check .gate1/oracle_correct --store .evalloop
EvalLoop: CLEAN (run run-3147e4b0c9224912)
  report: .evalloop/summary.md
(exit code: 0)

$ evalloop check .gate1/broken --store .evalloop
EvalLoop: PROBLEM (run run-97981379e19a8861)
  report: .evalloop/summary.md
(exit code: 1)

$ evalloop check .gate1/negative_equivalent --store .evalloop
EvalLoop: CLEAN (run run-d669aec284380a66)
  report: .evalloop/summary.md
(exit code: 0)

$ evalloop check .gate1/false_negative --store .evalloop
EvalLoop: CLEAN (run run-628f00dd17a55c22)
  report: .evalloop/summary.md
(exit code: 0)
```

The broken function is caught: **exit 1, PROBLEM.** The last two runs matter as much as the first
two — the correct variants (§5, negative control) are CLEAN, and the overfit variant (§7, false
negative) is CLEAN too, which is the honest weakness, not a win.

---

## 4. The verbatim `summary.md` for the broken function

(Shown in a four-backtick block because the summary itself contains a fenced plan view.)

````
# EvalLoop session summary

Run `run-97981379e19a8861`.

## 1. What you built

- `code_generation` (confidence 1.00)

No stated intent (M1 does not read transcripts).

## 2. What was evaluated and how

The plan:

```
READY        A1_execution_based · C1_wilson_ci
PENDING      (none)
UNAVAILABLE  (none)
PROHIBITED   (none)
```

Evaluated:

| Technique | Rung | Oracle |
|---|---|---|
| A1_execution_based | 1 (execution) | HIGH |

## 3. Findings

**A1_execution_based**
- 33.3% [6.1, 79.2]  n=3 · failed 2: wrong_result 2 · inconclusive 0 · [HIGH oracle]

## 4. What is not yet answerable, and what would unlock it

Nothing is waiting on more evidence or a missing tool.

## 5. What was prohibited, and why

Nothing was prohibited here.

## 6. Cost

LLM spend: $0.0000. M1 grades by execution, which makes no model call.
````

The pass rate is **33.3% [6.1, 79.2], n=3** — two of three cases are `wrong_result`, shown apart from
inconclusive (there were none), per EL-014. The classifier's `confidence 1.00` is a **coverage
fraction** (1 of 1 gradeable unit reads as `code_generation`), not a sampled proportion, so it
carries no sampling interval — it is labelled as coverage in EL-204.

The off-by-one being caught: `overlap_days` on inclusive ranges must add 1, and the broken version
does not, so `overlap_days(1,10,5,15)` returns 5 where the test requires 6, and the touching case
returns 0 where it requires 1. The disjoint case returns 0 either way and passes — hence 1/3 pass,
not 0/3.

---

## 5. Negative control — a correct tool must not cry wolf

`USER_EXPERIENCE.md` §1: the developer "will not tolerate a tool that cries wolf." Two correct
implementations were run and **neither was flagged**:

| Variant | Implementation | Result |
|---|---|---|
| `oracle_correct` | the reference (`high - low + 1`) | **100.0% [43.9, 100.0]**, n=3, CLEAN, exit 0 |
| `negative_equivalent` | a different correct method — enumerate the shared days and count them | **100.0% [43.9, 100.0]**, n=3, CLEAN, exit 0 |

The second is the stronger control: a **behaviourally equivalent but textually different**
implementation (a list comprehension over the day range, not arithmetic) passes, because execution
grades what the code *does*, not what it looks like (A1's anti-pattern, "string match marks
correct-but-different as wrong"). **No false positive was produced.**

---

## 6. Mutation self-check — was the catch a coincidence? (EL-207 / A:38)

The reference implementation was mutated and each mutant run through the same harvested test. A:38:
"if the mutant still passes more than 5% of the time, the fixtures aren't discriminating enough."

**0 of 4 mutants survived — survival 0.0% [0.0, 49.0], bar 5%: discriminating.** The four mutants
(subtraction→addition, the `+1`→`-1`, the constant `0`→`1`, the constant `1`→`2`) were each caught by
the test. The test has teeth; the catch in §4 is not a coincidence of a vacuous fixture. The interval
is wide (n=4), so the honest reading is "no evidence the fixtures are weak within these operators,"
not "proven strong" — and §7 shows exactly the kind of bug they miss.

---

## 7. A false positive and a false negative

- **False positive: none, and demonstrated absent** by the negative control (§5) — two correct
  implementations, including a different-but-correct one, both CLEAN.
- **False negative: present, and shown.** `.gate1/false_negative/overlap.py` carries the same
  off-by-one bug as the broken version **everywhere except the three exact `(low, high)` pairs the
  test checks**, which it hard-codes. EvalLoop reports **100.0% [43.9, 100.0], CLEAN, exit 0** — it
  **misses the bug.** This is not a defect in the grader; it is the defining limit of Reading A: a
  harvested test catches only what it covers, so a function that satisfies the test while being wrong
  elsewhere passes. The mutation self-check (§6) is the only M1 defence against this, and it is
  bounded by the mutation operators it tries. This is the honest weakness, and §10 returns to it.

---

## 8. Cost, and whether `--no-llm` could have caught it

**Cost: $0.0000.** Every run above made **no model call** — M1 grades by execution. The gate ran
under **`--no-llm` (the M1 default)**, and a driver test (`test_the_loop_touches_no_network`) runs the
whole loop with the socket layer patched to raise and still catches the bug. So **`--no-llm` did not
merely *could have* catch it — it is the only mode M1 has, and it caught it with zero egress.** A
with-LLM mode (authored oracles, Reading B) does not exist in a live run until M2 issues clearances.

---

## 9. Findings ledger (EL-014 → EL-214)

**Gate 0 is open.** All M1 code below was built ahead of sign-off; `GATE0-REVIEW-PACKET.md` §5 lists
the fifteen open rulings (F2, F8, the three blocked fixtures, the eight interpreted thresholds, the
`PLAN.md` §5 wording, and agreement on the 20 plans).

### Thresholds left `null`, and why
| Where | Value | Why null |
|---|---|---|
| `A1.row_cap` | `null` · grant | The corpus names a row cap with no number; it arrives with a DB grant (Track V), never invented (EL-015) |
| 69 of 73 records' `parameters` | `null` | EL-015 inventoried only A1/A2/A3/A5; the rest stay null until their first reader (EL-015) |
| `evalloop/stats` 5 corpus defaults (conf 0.95, α 0.05, 10 000 shuffles, 5 000 resamples, 25 discordant pairs) | module constants | Cited to the corpus; EL-015 "Forecloses" covers them, ruling pending (EL-203 §10) |

### Thresholds interpreted from prose — the human-review queue
| Item | Interpretation | Source |
|---|---|---|
| 8 M0 thresholds | read from hedged prose | `GATE0-REVIEW-PACKET.md` §4.2 |
| EL-204 classifier **confidence = coverage** | "share of units", not a calibrated probability; no labelled set exists to calibrate against | EL-204 §5 |
| A2's 2% mismatch bar | scoped to "customer-facing agents" (text, not vocabulary) | EL-015 |

### What the corpus would not support
| Item | Note |
|---|---|
| C1 "any score, ever" and H1 "any agent evaluation" | universal records with no faithful `Situation` member; reached via `companion_checks`, not matching |
| Six dead situations (`classification`, `data_pipeline`, `model_training`, `contamination_risk`, `distribution_mismatch`, `phi_present`) | reach no record; EL-204 refuses to emit them rather than produce an unexplained empty plan |
| EL-210 Reading B in a live run | authoring needs egress; option (b) forbids it in M1 |

### Stale doc lines found
| Line | State |
|---|---|
| `CLAUDE.md` §2 "Milestone 0 … Do **NOT** build execution/sandbox/stats/storage" and §5's M0-only target layout | **stale** — M1 shipped `grade/`, `stats/`, `capability/`, `memory/`, `classify/`, `report/`, `run.py`. Not edited (not my call) |
| `AGENT.md:150`, `:199` timeout lines | **corrected** by EL-014 to "failure, logged separately"; verified present |
| `AGENT.md:150`/`:199`, `ARCHITECTURE.md:378`, `PLAN.md:44`, `DEVELOPMENT_PLAN.md:135`, `TASKS.md:356`/`:358` | EL-014 corrected the INCONCLUSIVE→failed/timeout rule across these |

### Rulings still open (raised by M1, not yet decided)
| # | Ruling |
|---|---|
| R1 | **Implement EL-015** so graders read A1's `timeout`/`float_tolerance`/mutant-bar from the record; until then EL-206/207/214 take them as arguments |
| R2 | **Where session data lives** — `.evalloop/` vs user home (`USER_EXPERIENCE.md` §6); EL-201/202/214 all pass it in |
| R3 | **F2** — the produced readiness keys are *evidence* bars + *preconditions*, never *trust* bars; every trust bar is an absent M4 judge key (EL-213) |
| R4 | **Baseline source** for "already failing" — previous run, a git-committed run (needs the M2 git sensor), or none (EL-205/207) |
| R5 | **Isolation boundary** — M1 isolates the artifact's cwd + import graph; full filesystem-read isolation needs process separation (M3 reward-hack) (EL-207 §3) |
| R6 | **`RECORD_ID.match` → `fullmatch`** in the registry — a trailing newline passes as a valid id today (EL-202 §6) |
| R7 | **F-G1a** (new, this packet) — the harvester counts a nested repo's tests as the project's; see below |

### Found this session
- **F-G1a** — `harvest(REPO_ROOT, …)` counts every `test_*.py` in the tree, including a vendored/nested repo's. Committing the toy repo at `gate1/` made the count 34 vs the expected 30 and failed `test_the_virtualenvs_vendored_tests_are_not_this_repositorys`. Reported, not fixed; the toy repo was moved to `.gate1/` (a dot directory the harvester skips) to keep the suite green. The real fix (scope the harvester to the project, or exclude nested repos) is a code change I did not make.

---

## 10. Does this catch real bugs, and where is it weakest?

**Yes — within one honest boundary.** On a function with a genuine off-by-one and a human-written
test that exercises it, EvalLoop ran the code, scored it 33.3% [6.1, 79.2], and exited non-zero with
the two failing cases named as wrong answers — with the harness first proven sound by a 100% oracle
run, the catch shown non-coincidental by a 0/4 mutation survival, and a different-but-correct
implementation left unflagged. That is a real catch, by execution, not by a plausible reading of the
code, and it cost nothing and touched no network.

**Where it is weakest, plainly:**
1. **It only re-ran an existing test (Reading A).** The thing that would make EvalLoop an evaluation
   *system* rather than a test *runner* — authoring the oracle when none exists — cannot run in M1
   (§1). Until M2 issues a clearance, every live catch is a catch of a bug an existing test already
   describes. The weakness is not in the grader; it is that the grader has nothing new to grade with.
2. **A harvested test catches only what it covers (§7).** The false-negative variant — wrong
   everywhere but the tested points — passed, CLEAN. The mutation self-check is the only guard, and
   it is bounded by its operators and by n=4 here (survival interval [0.0, 49.0] is wide).
3. **n is tiny, and the intervals say so.** Every pass rate in this gate spans most of the unit
   interval. The gate proves the mechanism works on one function; it does not prove a rate.
4. **The isolation boundary (R5) and the platform limits** (macOS cannot cap memory; Linux
   unverified — EL-206) are real and documented, not closed.

My recommendation: **this is a Reading-A pass — accept it as proof that the harvest/execute/stat/
report mechanism is sound and honest, and explicitly withhold the "invents its own oracle" claim
until M2 makes Reading B runnable.** Gate 1 passing on the stronger claim, which did not run, would be
worse than not passing at all.
