# EL-211 — `summary.md` renderer (stage S41)

**⚠ Depends on Gate 0.** Stated dependencies are EL-213 (done) and EL-207 (not built). Section 4
renders readiness, so it inherits F2 and sits behind Gate 0 — built ahead of sign-off like the rest
of Group 3/5. See §5 for how I built it without EL-207 existing.

**Status: done.** `pytest` passes 1161 + 1 skipped on 3.12 (23 new tests; the skip is the
Linux-only sandbox memory test). `mypy --strict evalloop/` clean on 40 files. Standard library only.
Not re-run on 3.10 (no 3.10 interpreter here).

---

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/report/summary.py` | `render_summary(session) -> str`, the `Session` input, and `format_rate` |
| `evalloop/report/__init__.py` | Re-exports |
| `tests/test_summary.py` | 23 tests, three golden scenarios |
| `tests/fixtures/report/{empty,clean,rich}.md` | The golden files |
| `tests/conftest.py` | `REPORT_FIXTURES_DIR`, declared once |

## 2. The six sections, in order

Rendered exactly as `USER_EXPERIENCE.md` §3.4 names them: (1) What you built, (2) What was
evaluated and how, (3) Findings with per-item flips in both directions, (4) What is not yet
answerable and what would unlock it, (5) What was prohibited and why, (6) Cost. A test asserts the
six headers appear in order in every scenario.

## 3. The rules with teeth

| Rule | How it is met |
|---|---|
| **Reuse `Plan.render()`; don't reimplement the four states** | `Plan.render()` is embedded verbatim as the plan block in §2. Sections 4 and 5 reuse the planner's own reason strings — `Plan.pending`, `Plan.unavailable`, `Plan.prohibition_reasons` — so nothing re-derives which record is ready/pending/unavailable/prohibited, or why. A test asserts every `Plan.pending` reason appears verbatim in the output |
| **A rate never without its interval** | `format_rate` computes the Wilson interval (EL-203) from the counts and is the *only* path from counts to a percentage. It **raises** if asked for a rate with no conclusive case, so a bare percentage cannot be printed. `format_rate(7, 5) == "58.3% [32.0, 80.7]"` — it reproduces EL-014's own illustration. A test scans every finding line and asserts an interval follows the `%` |
| **Oracle confidence on every finding; LOW looks low** | Each finding carries `[HIGH oracle]` or `[LOW oracle — generated, not ground truth]`, and the §2 table shows HIGH/LOW per technique. A LOW oracle is visibly marked as not ground truth |
| **INCONCLUSIVE apart from fail (EL-014)** | A timeout is a failure of class `timeout`, counted in the rate and listed in the failure breakdown (`failed 2: wrong_result 1, timeout 1 (wall_clock)`); an inconclusive case is counted in neither, shown as `· inconclusive N` (even when 0), and listed on its own line with its reason |
| **Byte-stable** | Three golden files; a test asserts identical bytes on re-render. Every ordering is explicit |

**Mutation-checked.** Four rules broken one at a time, each caught: dropping the interval from a
rate, allowing a bare rate (no raise), rendering a LOW oracle as HIGH, and folding inconclusive
into the rate denominator.

## 4. The two common cases, written first

S23-REPORT §3 says the common day-one outcomes are an **empty plan** and a **clean run**, so I wrote
those first and made them read as an honest account rather than a blank scoreboard:

- **Empty plan** (a dead situation such as `classification`): §2 reads "No technique applied to the
  inferred situation(s), so nothing was evaluated.", §3 "Nothing was evaluated, so there are no
  findings.", §4 "Nothing is waiting on more evidence or a missing tool.", §5 "Nothing was
  prohibited here." No tables, no numbers, no "%". The golden is `empty.md`.
- **Clean run**: §2 lists the ready technique with its rung and HIGH oracle, §3 shows
  `100.0% [43.9, 100.0]  n=3 · inconclusive 0`, and the rest read as "nothing outstanding". The
  golden is `clean.md`.

Every "no" states its reason in plain language (`USER_EXPERIENCE.md` §4.3): a missing tool is
glossed (`H8_flaky_classification` needs "a restorable environment snapshot", not the bare
`snapshot_restore`), and a pending reason is the planner's own "needs runs: 5, have 0".

## 5. Building without EL-207, and what Section 4 actually reads

**EL-207 (the execution grader) is not built, but EL-211 does not need its code** — only the data it
will produce, which already has a defined type. The renderer takes a `Session` of already-stored
facts: the `Plan` (planner, done), the run's `CaseResult`s (the metric store's schema, EL-201,
done), the classified situations, a prior run's cases for the flips, and the cost. EL-214 will fill
a `Session` from the live grader; the renderer is a pure function of it. The `rich.md` golden shows
a full findings section built from hand-made `CaseResult`s, so the rendering is proven before a real
grader exists.

**Section 4's content is EL-213's readiness reasons.** EL-213 assembles the evidence, `plan()`
consumes it, and the result is the exact strings in `Plan.pending` — `needs runs: 5, have 0`. §4
renders those verbatim, never a restatement of the threshold, which is the ticket's requirement and
the F2-relevant honesty: the bar is the methodology's, the count is this run's.

## 6. Calls I made — please check

1. **`Plan.render()` is embedded in §2, and §4/§5 reuse the planner's reason strings.** The
   six-section layout distributes the four states across sections 2/4/5, so one monolithic block
   cannot be the whole story; I reuse the Plan's *data* (its computed reasons and membership) rather
   than recompute any of it. §2's plan block and §4/§5's narrative therefore overlap in content on
   purpose — the plan view and the report are separate artifacts in `USER_EXPERIENCE.md` itself
   (§3.1 vs §3.4). If you want the four states shown in exactly one place, say which.
2. **Cost is a single session total** (`cost_usd`), not a per-model breakdown. In M1 it is `$0.0000`
   with the reason "M1 grades by execution, which makes no model call", because every M1 case has
   `cost_usd = None` (EL-201/`case.py`). A per-model table waits for M4's judge.
3. **The confidence is 0.95**, the stats module's default (C1). It is a `Session` field, so a
   caller can change it, but I did not invent a different one.
4. **A record in two states is shown in both** — `D1_pr_curve_never_accuracy` in the `rich` golden
   is both pending and prohibited (fixture 12's case), and it appears in §4 and §5. That is honest,
   not a bug.
5. **`intent` is rendered when supplied, else "No stated intent (M1 does not read transcripts)."**
   Intent comes from M2's transcript reader, so in M1 it is normally absent.

## 7. Warnings touched (M0 preamble)
- **#1 (Gate 0):** depended on; flagged at the top.
- **#2 (F2):** §4 renders readiness reasons from EL-213/`Plan.pending`; it shows the "needs X, have
  Y" strings without taking a side on which kind of bar they are — that is EL-213's finding and the
  Gate 0 ruling.
- **#6 (six dead situations):** the empty-plan case is exactly a dead situation reaching no record;
  §4 of this ticket is where that now reads as an honest "no method applied" rather than a blank.
- **#7 (EL-014):** a timeout is rendered as `failed`/`timeout` inside the rate and apart from wrong
  answers; inconclusive is shown distinctly — the decision, applied at the one place a user sees it.

## 8. Scope held
No dashboard, SSE or live timeline (M2); no trend lines (M3); no PR comment (M5). The renderer is a
pure function; it reads nothing and writes nothing (EL-214 owns writing the file).

## 9. Rulings I need
1. **Accept building ahead of Gate 0** (as for the other Group 2/3 work).
2. **The §2-vs-§4/§5 overlap** (§6.1): is embedding `Plan.render()` in §2 *and* narrating
   pending/prohibited in §4/§5 the shape you want, or should the four states appear once?
3. **Confirm EL-214 fills the `Session`** from the live grader, classifier and router ledger — the
   renderer deliberately takes a plain input and does no I/O.
