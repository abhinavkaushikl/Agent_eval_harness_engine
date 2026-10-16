# EL-305 — V4 Read-only envelope + audit log

**⚠ Depends on EL-304 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_envelope.py` 20 passed; `mypy --strict evalloop/` clean on 52
files; standard library only (`re`, `sqlite3` in the test for a real read-only transaction). Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/envelope.py` | `ReadOnlyEnvelope`, `reject_writes`/`classify_statements` (layer 1), `WriteScope` (layer 4), `AuditLog`/`redact_sql` (layer 5), `Caps`-driven caps (layer 3) |
| `tests/test_envelope.py` | 20 tests; a tiny `sqlite3` executor (`PRAGMA query_only = ON`) gives layer 2 a genuine read-only transaction |

The envelope **opens no connection and imports no database driver** (decision EL-006). The concrete
executor is EL-306; here it is an injected `Executor` protocol (`read_only: bool` + `run(...)`).

## 2. The result — six requirements
| # | Requirement | How |
|---|---|---|
| 1 | Layer 1 rejects DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/GRANT + any DDL/DML before a byte is sent, naming the statement | `reject_writes` splits statements and classifies each *default-deny*: a statement runs only if its leader is a read and no DML/DDL keyword hides outside a string literal. `ReadOnlyViolation` carries the offending `Statement` (kind + keyword). **A `DROP TABLE` never reaches `Executor.run`** — tested, executor call-count 0 |
| 2 | Layer 2 read-only transaction catches what slips layer 1 | the envelope refuses a read unless `executor.read_only`; the DB enforces it too. Proven with SQLite `query_only = ON` |
| 3 | Layer 3 row/byte caps from the grant, recorded | `_enforce_caps` applies `Caps.max_rows`/`max_bytes` (EL-006), returns a `ResultShape(row_count, byte_count, truncated)` recorded with the result and in the audit |
| 4 | Writes get a scratch schema / restored snapshot, never live | DML is rejected unless a `WriteScope.scratch_schema(...)` / `.snapshot(...)` is given; **there is no `live` scope to construct** (`WriteScope("live", …)` raises); destructive DDL is rejected even under a scope |
| 5 | Append-only, redacted audit log | `AuditLog.append` only; no mutate/remove method. `redact_sql` turns every string and numeric literal into `?` **before** the entry is stored, so nothing unredacted is persisted — in memory or in the optional file sink |
| 6 | The three layers are independent | the independence test disables layer 1 (`static_guard` injected as a no-op classifier) and watches layer 2 (the read-only SQLite transaction) block an `UPDATE` on its own — the row is unchanged and the blocked attempt is still audited (redacted) |

## 3. Calls I made
1. **No SQL parser library** (`CLAUDE.md` §1). Layer 1 is a minimal classifier: strip comments, mask
   string literals, split on top-level `;`, then default-deny on the leading keyword with a backstop
   scan for DML/DDL tokens. It is deliberately conservative — an ambiguous statement is **rejected**,
   never waved through. It recognises `WITH…SELECT` and non-executing `EXPLAIN` as reads, and flags
   `SELECT … FOR UPDATE` / `… INTO …` as write-intent.
2. **`SET` is caught as a leader, not as a backstop token**, because `UPDATE … SET …` is legitimate
   DML. A standalone `SET`/`BEGIN`/`START` still falls to default-deny and is rejected — just
   reported as its own leading keyword.
3. **Layer 2 is a precondition plus the DB's own enforcement.** The envelope will not run a read
   against a non-read-only executor; the actual stop for a slipped write is the read-only transaction
   at the wire (SQLite `query_only`, Postgres `SET TRANSACTION READ ONLY` for EL-306). The envelope
   does not itself open the transaction — that is the connector's job.
4. **Caps are enforced post-hoc on the returned rows** (truncate + `truncated=True`). The real
   connector (EL-306) can also push `LIMIT` down; the envelope's guarantee is only that it never
   *returns* more than the cap.
5. **The envelope records the write scope but cannot verify the connection points at scratch.** Its
   guarantee is "no write without a named scratch/snapshot scope"; the connector guarantees the scope
   is a real scratch schema / restored snapshot.

## 4. Full-suite note (not an EL-305 regression)
`pytest` reports 1261 passed, 1 skipped, 1 failed — the F-G1a finding from the `testcases running/`
demo folders, unrelated to EL-305. Relocating those folders to a dot-dir clears it.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **DDL-under-scope** (§2.4): I reject *all* DDL even under a write scope, on the view that untrusted
   AI SQL never issues `CREATE`/`DROP` and that scratch-schema setup is the connector's job. If a
   technique legitimately needs `CREATE TEMP TABLE` in its scratch scope, that is a deliberate
   loosening I want you to sign off, not assume.
3. **Audit sink format** (§2.5): the file sink writes one tab-separated redacted line per statement
   (endpoint, kinds, redacted SQL, ok/error). Confirm that shape before EL-305's log feeds anything
   downstream, or say if you want JSONL.
