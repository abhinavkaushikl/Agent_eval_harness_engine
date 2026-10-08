# EL-202 — Episodic store (stage S32)

**Status: done.** `pytest` 874 passed on 3.12, and 873 passed + 1 skipped on 3.10
(the skip is the existing 3.11-only `StrEnum` comparison in `test_compat.py`).
`mypy --strict evalloop/` clean on 23 files. The store is built on the stdlib
`sqlite3` module alone.

**Gate 0:** EL-202 does not depend on it (§0.1 warning 1). It consumes `Plan` as
it stands today.

---

## 1. What exists

| File | What it holds |
|---|---|
| `evalloop/memory/episodic.py` | `EpisodicStore` and its value types, schema v1, the migration runner, and the pinned SQLite settings |
| `evalloop/memory/__init__.py` | Package docstring and re-exports. The ticket didn't list it; the package needs it |
| `tests/test_episodic_store.py` | 72 tests: round trips over all 17 live planner fixtures, schema versions, concurrency, verbatim text |

**The API.**
- Write methods, one transaction each: `open_session`, `open_episode`,
  `record_classification`, `record_plan`, `record_verdict`.
- Read methods, for a human asking later: `sessions`, `episodes`,
  `classification`, `plan_snapshot`, `rendered_plan`, `why`, `verdicts`.

**Schema v1** has 12 tables. Each decision is chained to the one before it by a
foreign key:

```
session ─< episode ─< episode_artifact ─────────────────────────────┐
              ├─< classification ─< plan_situation ─< plan_trigger  │
              ├── abstention                                        │
              └── plan ─< plan_entry ─< plan_missing_tool           │
                   └─< plan_companion       plan_entry(ready) ─< verdict >─┘
```

**The chain holds by construction.** A plan can only use situations the
classification recorded, and a verdict can only come from a technique the plan
made **ready**, on one of the episode's own artifacts.

**`why(episode, record)` walks that chain in one SQL statement.** It returns
three things:
- the record's entry or entries, with their reasons;
- the planned situations that triggered it, joined to the classification's
  reason for each;
- the ready records that named it as a companion.

---

## 2. Acceptance criteria

| Criterion | Evidence |
|---|---|
| "Situation decisions *and the reasoning*" | Every decision is refused without reasoning: blank labels, abstentions and verdict reasons all raise. Reasoning is stored as given, whitespace included |
| Schema version in the file, with a migration path | Stored in `PRAGMA user_version`; `_MIGRATIONS[i]` takes a file from version i to i+1. Tests: a v1 file is upgraded by an added step; a failing step leaves the file at v1 with its data intact; files from a newer EvalLoop and non-store databases are refused and left untouched |
| Multi-label means rows, not a joined string | One `classification` row per situation, each with its confidence |
| Every write parameterised | Quotes, an SQL-comment injection, newlines, tabs, `₹`, `−`, `≥` and a NUL byte round-trip byte for byte, and all 12 tables survive. **See §5.1: record ids cannot hold a quote** |
| "Why was A1 chosen" in one call | A trace callback counts the statements `why()` executes: exactly 1 |
| Round trip: write, close, reopen, read | All **17 live fixture plans**, from the real planner, read back equal to `PlanSnapshot.of(plan)`. The rendered text is identical too |
| Concurrency stated and tested | One writer by design, with a busy timeout of zero. Four tests:<br>• a second writer fails at once<br>• a commit that meets a reader is rolled back, and the store stays usable<br>• a reader can open the store while a writer holds the lock<br>• a store object is refused from another thread |
| No absolute path | The location is a required argument with **no default**. See §5.2 |
| sqlite3 defaults pinned, not inherited | Settings are set and then read back. Unsafe features are avoided:<br>• `isolation_level=None`, explicit `BEGIN IMMEDIATE`/`COMMIT`, no `executescript`<br>• `detect_types=0`, `timeout=0.0`, `check_same_thread=True`, `uri=False`<br>• `foreign_keys = ON`, verified (SQLite's default is **off**)<br>• `synchronous = FULL`; journal mode and encoding verified<br>• no `STRICT` or `RETURNING`: 3.10 builds link older SQLite, so types are enforced with `CHECK (typeof(…))` |

**The four key behaviours were mutation-checked.** I broke each one in the source
and confirmed its test caught it:
- no rollback after a refused commit;
- `match` instead of `fullmatch`;
- no selection-basis check;
- foreign keys left off.

A fifth mutation, inheriting Python's default 5-second busy timeout, **slipped past
at first**. A second writer still fails after the wait, so a test that only checks
for the failure can't tell. The pinned-settings test now reads `PRAGMA
busy_timeout` directly, and catches it.

---

## 3. Calls I made — please check these

1. **"Ready" gets a reason here that the planner never gives.** `Plan` has a reason
   for every "no" and none for a "yes". To answer "why was A1 chosen", the store
   records the *selection basis*, derived from the plan without re-running any of it:
   the planned situations the record triggers on, and the ready records that named it
   as a companion. **Every planner entry has at least one of the two.** So an entry
   with neither means the plan wasn't computed from the recorded situations, and the
   store refuses it (tested).
2. **Append-only.** Nothing is updated or deleted, and each decision is recorded once
   per episode. An abstention gets its own table instead of a column filled in later.
3. **Busy timeout is zero.** Any wait would be a number I'd have invented. A second
   writer gets `EpisodicStoreBusy` immediately.
4. **No clock.** The store never reads the time and never generates an id; everything
   in it was passed in by the caller. Identical writes produce an identical
   `iterdump` (tested).
5. **An episode is defined by its set of artifacts**, following `ARCHITECTURE.md` §9.
   A verdict must name one of the episode's own artifacts.
6. **A vocabulary change needs a schema migration.** Reads parse stored situations
   and tools back into the enums. So if a member is removed, old episodes fail to read,
   loudly, until a migration step rewrites them. They never come back silently
   mislabelled.

---

## 4. The seven inherited warnings — which way I went

| # | Warning | What I did |
|---|---|---|
| 1 | Gate 0 | Not a dependency of this ticket |
| 2 | F2 | Pending reasons are stored verbatim. The store can't tell an evidence bar from a trust bar, because the plan doesn't |
| 3 | F8 | The store never reads `unlocks`. Plans are stored exactly as produced, so fixture 8's B1, ready on a single pair, is recorded as ready |
| 4 | Fixture 20 / egress | Untouched; this module makes no outbound call |
| 5 | `PLAN.md` §5 | Not used as a spec |
| 6 | Six dead situations | Recorded visibly. A `classification` episode stores its label, the situation the plan used, and an empty plan whose render shows "(none)" four times (tested) |
| 7 | Timeout semantics | **Not decided here.** A verdict is stored as the grader words it; both "INCONCLUSIVE" and "timeout, counted as a failure" are accepted (tested). Once EL-014 rules, a v2 migration can constrain it |

---

## 5. Where the ticket was wrong

1. **A record id can't contain a quote.** The ticket asked for a test that stores
   one intact. But `RECORD_ID` only admits `[A-J]`, digits, lowercase letters and
   underscores. So the store validates record ids against that pattern, imported
   rather than retyped, and an injection-shaped id is refused before it reaches SQL.
   Parameterisation is proven on the fields that legitimately carry arbitrary text:
   artifact paths, ids and reasoning.
2. **"A documented default" contradicts "do not decide it here."** The ticket asked
   for both. `USER_EXPERIENCE.md` §6 hasn't chosen between the repo's `.evalloop/`
   and the user's home, so there's no default; the docstring says why. Directories
   aren't created either.
3. **"M1 only writes it."** The store also has read methods: `why()` and the round
   trip are acceptance criteria. All of them serve a human; none of them feeds a
   decision.

---

## 6. Bugs found

- **M0 registry (not fixed; not mine to change):** `TechniqueRecord` checks ids with
  `RECORD_ID.match`, and Python's `$` matches before a trailing newline. So
  `"A1_execution_based\n"` passes as a valid id; I confirmed it. The fix is one
  word: `fullmatch`. The store already uses it.
- **A SQLite trap, handled:** when a `COMMIT` is refused because a reader holds the
  file, SQLite **leaves the transaction open** (I confirmed this by probing). The
  write wrapper rolls back explicitly, and the reader test covers it.

---

## 7. Rulings I need

1. **Should `Plan` carry what conflicts suppressed?** `rules.apply_conflicts` returns
   `suppressed` ("replaced by B7_cluster_bootstrap") and `unapplied`. Its own
   docstring calls an unexplained disappearance "the silent skip this project
   refuses everywhere else". But `plan()` keeps only `.kept`. As a result:
   - "why was B6 not chosen?" has no answer to store;
   - fixture 13's only record of the replacement is a YAML comment (tested as the
     gap it is).

   Adding the field the way `prohibition_reasons` was added would let a schema v2
   step persist it.
2. **Where does session data live?** `USER_EXPERIENCE.md` §6. EL-201's metric store
   needs the same answer.
3. **Should a ready record's reason come from the planner** instead of being derived
   in M1 (§3.1)? The derivation is sound, but it puts an explanation of the plan
   outside the planner.
4. **Fix `RECORD_ID.match` → `fullmatch` in the registry** (§6)?

---

## 8. For later milestones

- **WAL mode, for M2.** In SQLite's default journal mode with a zero timeout, a
  dashboard reading during a commit makes that commit fail. WAL is the usual fix,
  and choosing it belongs to M2.
- **Timestamps, as schema v2.** M2's monotonic session clock (`ARCHITECTURE.md` §9)
  is the natural source; this store deliberately has no clock.
- **Replay.** The plan's other inputs (available tools, evidence) appear only inside
  its reasons. Persist them only if re-running a recorded plan becomes a need.

## 9. Stale doc lines

| Where | What |
|---|---|
| `CLAUDE.md` §2, §5 | Still M0-only; the target layout has no `evalloop/memory/` (also reported in EL-203) |
| `E2-M1-TICKETS-AND-PROMPTS.md`, EL-202 | (a) The quote-in-record-id test is impossible (§5.1). (b) "Documented default" contradicts "do not decide" (§5.2). (c) The file list is missing `memory/__init__.py`. I left the ticket text alone, per scope |
