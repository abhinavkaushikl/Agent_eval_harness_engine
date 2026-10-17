# EL-306 — V5 Connector protocol + SQLite

**⚠ Depends on EL-305 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_sqlite_connector.py` 10 passed; `mypy --strict evalloop/` clean
on 54 files; standard library only (`sqlite3`, no driver, no network). Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/protocol.py` | the `Connector` Protocol (`probe` / `describe` / `read`) + value types `Column`, `Table`, `Schema`, `ProbeResult`; errors `ConnectorError`, `NotAuthorized` |
| `evalloop/connect/sqlite.py` | `SqliteConnector` — the first, driverless implementation |
| `tests/test_sqlite_connector.py` | 10 tests against a fixture SQLite file built in `tmp_path` |

One additive change to EL-305: `ReadOnlyEnvelope.audit` is now a read-only property, so a connector
can record its probe/describe calls in the same append-only log.

## 2. The result — five requirements
| # | Requirement | How |
|---|---|---|
| 1 | A backend-agnostic `Connector` Protocol so EL-307/308/309 are thin | `protocol.py` declares `probe()/describe()/read()` + value types only; it opens nothing and imports no driver. `SqliteConnector` satisfies it (`isinstance(conn, Connector)` tested) |
| 2 | SQLite, every call through the broker (EL-302) and envelope (EL-305) | each operation calls `broker.check(tool, endpoint)` first; `read()` runs `envelope.execute(...)` under the **granted** caps (not caller-supplied); probe/describe are recorded in the envelope's audit |
| 3 | `describe()` returns tables + columns, reads NO rows | `sqlite_master` (catalog) for table names, `PRAGMA table_info` for columns — both read schema, never table data. Tested: no fixture row value (`alice`/`bob`/`999`) appears in the schema |
| 4 | A write through `read()` is rejected by the ENVELOPE, even when SQLite would allow it | the proof opens the connector over a **writable** backend (after confirming SQLite itself runs the same `UPDATE` on that file), and `read("UPDATE …")` still raises `ReadOnlyViolation` at layer 1 — before the backend is touched — and the row is unchanged |
| 5 | probe/describe/read all succeed and are read-only against a fixture DB | tested; `read()` honours the granted `max_rows` cap (truncates + flags) |

## 3. Calls I made
1. **probe/describe do not pass untrusted-SQL layer 1.** They issue the connector's *own* trusted
   introspection (`SELECT 1`, `sqlite_master`, `PRAGMA table_info`) — and `PRAGMA` would be rejected
   by the envelope's write gate, correctly, since that gate is for model-written SQL. So "routed
   through the envelope" is honoured for probe/describe as **read-only execution + audit**, while the
   three-layer SQL gate applies to `read(sql)`, the only path carrying untrusted SQL. Flagged for
   your ruling.
2. **Caps come from the grant, not the caller.** `read(sql)` takes only the SQL; the row/byte caps
   are the broker grant's caps (EL-006). The caller cannot widen them, which is the point of routing
   through the broker.
3. **Read-only is belt *and* suspenders.** Default opens `file:…?mode=ro` + `PRAGMA query_only = ON`
   (a real read-only transaction, EL-305 layer 2), *and* the envelope's layer 1 rejects writes before
   the backend. `backend_read_only=False` exists only so a test can strip the belt and prove the
   envelope holds alone; production uses the default. A second test shows the read-only backend
   independently refuses a write when layer 1 is disabled.
4. **`Schema` carries `tables` only.** Vector-store "collections" (EL-309) will extend the structure;
   `Table`/`Column` are named generically so that backend can reuse them.

## 4. Full-suite note (not an EL-306 regression)
`pytest` reports 1271 passed, 1 skipped, 1 failed — the F-G1a finding from the `testcases running/`
demo folders, unrelated to EL-306. Relocating those folders to a dot-dir clears it.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **probe/describe vs the envelope** (§3.1): confirm trusted introspection bypassing the layer-1 SQL
   gate (while staying read-only + audited) is the contract you want, or should describe's catalog
   queries also be whitelisted through the envelope explicitly?
3. **`close()` / connection lifetime**: the connector holds its SQLite connection open for its
   lifetime and exposes `close()`. If you want a per-call open/close (no held handle) for the CLI
   backends in EL-308, say so and I will shape the protocol for it now.
