# EL-201 — Metric store (stages S30–S31)

**Status: done.**

- `pytest` passes: 986 tests on 3.12, and 985 plus one skip on 3.10. The skip is the existing
  3.11-only `StrEnum` check.
- `mypy --strict evalloop/` is clean on 29 files, and the new test file is clean too.
- The package uses the standard library only. 55 tests are new.

**Gate 0 is not signed off, and the board lists it as this ticket's dependency.** I built EL-201
because you asked for it. Gate 0's two big rulings, F2 and F8, change what the planner emits
(readiness and unlocks). They don't change what a judged case is, so the risk to this schema is
low. EL-213 and EL-211 still inherit both rulings.

**EL-014 is decided**, so the blocking note did not fire. The verdict vocabulary is EL-014's.

---

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/memory/case.py` | One judged case (`CaseResult`), a promoted case (`PermanentCase`), EL-014's enums, and the schema's field order (`CASE_FIELDS`) |
| `evalloop/memory/metric_store.py` | The append-only writer, the reader, permanent cases, the content-hash lookup, and `diff_runs` |
| `evalloop/memory/__init__.py` | Re-exports both stores, but not `case.Verdict` (§6, finding 1) |
| `tests/test_metric_store.py` | 55 tests, every one on real files in `tmp_path` |

```
<store>/runs/<run_id>.jsonl    a header line, then one case per line
<store>/permanent.jsonl        a header line, then one promoted case per line
```

---

## 2. The eight results

| # | You asked for | How it is met |
|---|---|---|
| 1 | Append-only, a version in the file, and an unknown version rejected loudly | A run file is created in exclusive mode, so an existing run can't be rewritten. Line 1 is `{"schema_version": 1, "store": …, "run_id": …}`. The reader refuses anything except the integer `1`, and says it "will not guess". Tests cover `2`, `0`, `true`, `1.0`, `"1"` and `null` |
| 2 | Stable field order, one case per line | Keys follow `CASE_FIELDS`. `run_id` is in the header, not on each line, so identical cases in two runs are identical lines. A test shows that a raw `diff` of two run files shows exactly the cases that changed, and a golden-line test pins the format |
| 3 | Per-case flips in both directions, never a net delta | `RunDiff` lists regressions, improvements, failure-class changes, cases that became or stopped being inconclusive, and cases that are in only one run. It has **no net or total field**, and a test asserts its field list |
| 4 | A test that writes two runs, diffs them, and asserts both lists | `test_two_runs_diff_case_by_case_in_both_directions`. A second test shows a "+4" that is really six improvements and two regressions, and asserts both lists |
| 5 | Permanent cases survive a run that doesn't regenerate them | They live in `permanent.jsonl`, outside every run. `missing_permanent(run)` names each permanent case that a run skipped |
| 6 | A lossless round-trip, and no absolute path | Round-trip equality is tested with a `Decimal` cost, U+2028, a newline, `₹`, a timeout, a null rung and a reused result. `MetricStore(directory)` has no default; the directory must exist, and the store creates only `runs/` inside it. A source check confirms the modules never look up the home directory, the environment or the working directory |
| 7 | Read `USER_EXPERIENCE.md` §3.4 first | Done. Its premise doesn't hold; see §4 |
| 8 | Report every null and who fills it | §3 |

---

## 3. The schema, and every field that can be null

| Field | In M1 | Filled by |
|---|---|---|
| `record_id` | always | the grader (EL-207, EL-208) |
| `case_id` | always | the oracle (EL-205 harvests, EL-210 authors) |
| `case_kind` | always | the run driver (EL-214) |
| `artifact_id` | always | the run driver |
| `oracle_id` | always | the oracle |
| `oracle_confidence` | always | EL-205 → `high`, EL-210 → `low` |
| `ladder_rung` | **null for any record that is not a grader, permanently** | the record (`CLAUDE.md` §6: `None` unless the record is a grader) |
| `verdict` | always | the grader |
| `failure_class` | set if and only if the case failed (EL-014) | the grader |
| `timeout` | set if and only if the class is `timeout`: which cap was hit, and its limit | the sandbox (EL-206) |
| `inconclusive_reason` | set if and only if the case is inconclusive | the grader or the sandbox |
| `score` | **null for a pure pass/fail technique** | EL-207 (partial credit) or EL-208, where the technique produces a score |
| `evidence` | null when the grader has nothing to say | the grader |
| `artifact_hash` | always | the run driver |
| `oracle_hash` | always | the oracle |
| `reused_from` | null unless the result was reused | the run driver, through `reused_in` |
| `seed` | **null until EL-206** records the seed it sets for the child, and null if nothing is random | EL-206 or the grader |
| `cost_usd` | **null for every M1 case** | M4's judge, through the router |
| `duration_seconds` | always | the grader or the sandbox |

**Only three nulls are "not yet":** `seed` (EL-206), `score` (EL-207 and EL-208), and `cost_usd`
(M4). The others are null by rule, under EL-014 or `CLAUDE.md` §6, and wait on nothing. **No field
is filled with a guessed default.**

**Why `cost_usd` stays null throughout M1.** It is the cost of a model call that judged this one
case alone, and no M1 call does that. EL-210's authoring call writes one file that serves several
cases. Dividing its cost among them would be an invented allocation, so that spend belongs to the
session, in the router's `CostLedger`.

**Fields beyond your floor, and why each exists:**

- **Two hashes instead of one.** `artifact_hash` drives EL-214's skip. `oracle_hash` stops a
  changed test from reusing an old result (`ARCHITECTURE.md` §9, "Test weakened to pass").
- **`ladder_rung` and `evidence`**, because §3.4's sections 2 and 3 display them.
- **`timeout` and `inconclusive_reason`**, because EL-014 requires them.
- **`reused_from`.** When EL-214 skips an unchanged case, the run must say so (E2 line 1765).
  Without this field, a skipped case either vanishes, and `diff_runs` reports it as gone, or is
  copied in and claims a judgement that never happened.
  - A reused case stays in its run and names the run that actually judged it.
  - An inconclusive result is never reused.

**Five failure classes, not four.** Your prompt says to use A:39's four. EL-014, decided after the
prompt was written, adds `timeout`. The enum is A:39's four classes verbatim, plus `timeout`.

---

## 4. §3.4: EL-211 cannot render the report from this store alone

EL-201's prompt says EL-211 renders `summary.md` "from this store alone". Taking the six sections
one at a time:

| §3.4 section | Source | In this store? |
|---|---|---|
| 1. What you built | the classifier, recorded in the episodic store | No |
| 2. What was evaluated and how | `record_id`, `ladder_rung`, `oracle_confidence` | **Yes** |
| 3. Findings, with flips in both directions | `diff_runs`, `evidence` | **Yes** |
| 4. What is not yet answerable | the `Plan`'s pending queue (the planner, fed by EL-213) | No |
| 5. What was prohibited, and why | the `Plan` | No |
| 6. Cost | the session's `CostLedger` | Only per-case cost, and M1 has none |

Copying sections 1, 4 and 5 into this store would duplicate the episodic store, which already
records the classification and the plan. So I didn't. EL-211's ticket now names its four inputs.

**One gap is left: nothing persists a session's LLM spend.** That is fine for EL-214's one-shot
run, where the driver can hand the ledger to the renderer. It is a gap for M2's dashboard.

---

## 5. Schema v1 against EL-213: 34 keys, and fewer of them are countable

**There are 34 distinct `requires` keys, not 33.** The registry loader counts 34. The E2 document
missed E8's `benchmarks`. I fixed the count in all seven places, including §7, the inherited state
every ticket carries.

E2 also said EL-201 "holds" 12 count keys. Schema v1 can count four of them, and the other eight
fall into two groups:

| Group | Keys | Notes |
|---|---|---|
| Counted from the v1 store | `runs`, `failures`, `discordant_pairs`, `trials` | I:100 includes "failed evals" among real failures. A trial is one run that contains the case |
| Need a field v1 doesn't have | `positives` (D1), `attempts_per_category` (D5, D6), `candidates` (B4), `smoke_items` (J1), `benchmarks` (E8) | None of these techniques runs in M1, so I added no speculative fields |
| Judge or human-review trust (M4) | `items` (A6), `fail_cases` (F1), `calibration_items` (F9), `majority_samples` (F8) | A6's `items: 200` means items reviewed by two experts |

- **Counting stored cases as `items` would be a false claim.** That is exactly what `CLAUDE.md` §3
  forbids.
- **Adding a field later means schema v2.** The version header makes that a migration, not lost
  data: a v2 reader can keep reading v1 files.
- **Trials within a single run can't be represented,** because a case appears once per run. Trials
  across runs work.

I corrected E2's EL-213 table and prompt to match.

---

## 6. Findings

1. **Two different things are named `Verdict`.**
   - `evalloop.memory.Verdict` is the episodic store's record (EL-202).
   - `evalloop.memory.case.Verdict` is EL-014's enum.

   mypy caught the clash. The package re-exports the record, not the enum, and its docstring says
   to import the enum from `case`. I recommend renaming the record to `VerdictRecord` as an EL-202
   follow-up.
2. **EL-014's types live in `memory/case.py`, not `grade/verdict.py`.** EL-014 says EL-206 "writes"
   them, but the store persists them first. EL-206's ticket now says to import them and never to
   define a second copy. I left EL-014's decision record as written.
3. **EL-206's prompt quoted a line from before EL-014:** "wall-clock cap -> INCONCLUSIVE". That is
   the opposite of the decision. I replaced it with the current `ARCHITECTURE.md` text.
4. **No E2 ticket calls `promote()`.** The mechanism exists and is tested. What triggers I:273's
   flywheel ("Add every past incident as a permanent item") is not assigned. It could be:
   - EL-214;
   - a person, in M2's interface;
   - automatic promotion of every failure, which is a policy decision, so it's yours.
5. **The cache and repeated runs pull against each other.** `AGENT.md:161` says "an unchanged diff
   is never re-evaluated". But C3's noise floor (`runs`) and H3's `trials` both need an unchanged
   case to run again. `lookup` is opt-in, so the store supports both; EL-214 has to decide when to
   skip.
6. **A permanent case keeps its oracle's id and hash, not the oracle's content.** If EL-210
   generated the oracle and its file is later deleted, the case can't run again. EL-210 or EL-214
   must keep the file of any generated oracle that gets promoted.
7. **Harvested repo tests are recorded as `generated`.** `AGENT.md` §3.9 defines only two kinds of
   case. A harvested test is re-derived on every run and disappears if the repo deletes it, and
   `oracle_confidence: high` already records that a person wrote it. This is an interpretation.
8. **`CLAUDE.md` §2 still describes M0 and lists storage under "do NOT build".** This is the third
   ticket to note it, after EL-202 and EL-203. The replacement text is in E2 §0. It's your file,
   so I haven't edited it.

---

## 7. Interpretations, flagged for review

- **`failed` to `failed` with a different class counts as a change.** A wrong answer that became a
  hang is not a fix.
- **`inconclusive` to `inconclusive` with a different reason is not a flip.**
- **Moves into and out of `inconclusive` are listed separately,** with both outcomes shown, and are
  never counted as a regression or an improvement. EL-014 treats them as evidence lost or gained.
- **`lookup` matches four things:** the technique, the oracle id, the artifact hash and the oracle
  hash. It does not match the artifact's path.
- **`case_kind` is not checked against `permanent.jsonl`.** A case can be promoted after the run
  that generated it, and that run's line correctly says `generated`.
- **Run ids must match `[A-Za-z0-9][A-Za-z0-9._-]*`,** because each one names a file.
- **A store has one writer, the run driver.** Two `promote` calls at the same time could interleave
  their lines.
- **A crash during promotion leaves a partial last line in `permanent.jsonl`.** The store then
  refuses to read the file or append to it until someone removes that line. That is deliberate.

---

## 8. How it was verified

- **The ticket's gate:** `pytest` (986 tests on 3.12; 985 plus one skip on 3.10) and
  `mypy --strict evalloop/` (29 files).
- **Mutation checks: 22 of 22 caught.** I broke each guarantee in the source one at a time,
  confirmed that a test failed, and restored the source byte for byte. The broken guarantees were:
  - diff direction, and failure-class changes;
  - exclusive creation, and the strict version check;
  - repeated keys, splitting at U+2028, unterminated lines, and reporting every bad line;
  - the header's run id, flushing, and the line format;
  - the permanent-case gap, and promoting a case only once;
  - both `lookup` rules;
  - EL-014's failure-class rule, and the hash format;
  - all four `reused_from` rules.
- **The statistics boundary.** One test parses every `evalloop/memory` module's imports. It also
  imports the package in a fresh interpreter. Together these show that `evalloop.stats` is never
  loaded, whether directly, lazily or through another module.

---

## 9. Doc lines changed (all in `E2-M1-TICKETS-AND-PROMPTS.md`)

| Where | Change |
|---|---|
| Board | EL-201 is marked ✅ Done, ahead of 🔒G0 |
| §2, §7, and EL-213 (five places) | 33 → 34 `requires` keys |
| EL-213's table and prompt | Shows which keys schema v1 can count, adds `benchmarks`, and moves `items` to judge trust |
| EL-206's subtask and prompt | Import the outcome types from `memory/case.py`; replace the stale "→ INCONCLUSIVE" quote; mark EL-014 as settled |
| EL-211's subtasks | Names its four inputs |

---

## 10. Rulings I need

1. **Gate 0.** Unchanged.
2. **Who promotes a case** (finding 4).
3. **When to move to schema v2** for the five keys M1 doesn't use. I recommend doing it when the
   first D, B4, J1 or E8 technique lands, rather than reserving fields now.
4. **The M1 text for `CLAUDE.md` §2.** Make the edit yourself, or ask me to.
5. **Whether to rename the episodic `Verdict` to `VerdictRecord`** (finding 1).
6. **Where session data lives** (open question 10). Still open; the store takes its location as an
   argument.
