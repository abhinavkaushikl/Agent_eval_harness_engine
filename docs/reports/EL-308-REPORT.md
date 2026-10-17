# EL-308 — Postgres + MySQL via CLI (no driver)

**⚠ Depends on EL-306 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_sql_cli_connector.py` 8 passed, 1 skipped (clean, no local DB);
`mypy --strict evalloop/` clean on 56 files; standard library only; **no database driver imported**.
Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/sql_cli.py` | `PostgresConnector`, `MySQLConnector` (shared `_SqlCliConnector` base), `MechanismUnavailable` |
| `tests/test_sql_cli_connector.py` | 9 tests; the live-server read skips cleanly when no Postgres is present |

Both implement the EL-306 `Connector` contract (`isinstance` tested), so Postgres/MySQL flow through
the **same** probe/describe/read as SQLite (EL-306) and MCP (EL-307).

## 2. The result — five requirements
| # | Requirement | How |
|---|---|---|
| 1 | Postgres + MySQL as Connectors invoking `psql`/`mysql` as subprocesses, through envelope + broker | each op authorises via `broker.check` first; `read()` runs `envelope.execute(...)` with a `_CliExecutor` that `subprocess.run`s the client; describe/probe run the CLI directly |
| 2 | `psql` absent → UNAVAILABLE naming psql + how to supply it, not a traceback | `shutil.which` miss → `MechanismUnavailable("psql", remedy)`; `probe()` returns `reachable=False` with the remedy in `detail`, `read()` raises the typed, named error (tested with `which` stubbed to `None`) |
| 3 | A read against a local fixture Postgres returns rows; skips cleanly with no server | the test skips if `psql` is off PATH or `probe()` is not reachable (set `EVALLOOP_PG_DSN` to run it). **CI needs no database** |
| 4 | No `psycopg`/`mysqlclient`/`PyMySQL` import under `evalloop/connect/` | a source scan over `evalloop/connect/*.py` asserts no `import`/`from` of `psycopg`/`psycopg2`/`mysqlclient`/`pymysql`/`MySQLdb`/`sqlalchemy` |
| 5 | The CLI path inherits the developer's TLS/Kerberos/SSH config for free | `subprocess.run` is called with **no `env=` override**, so the child inherits the parent environment (`PGSSLMODE`, `~/.pgpass`, `KRB5CCNAME`, SSH agent, …). Proven by capturing the call and asserting `env` was never passed |

## 3. Calls I made
1. **Caught an architectural conflict and fixed the design, not the test.** My first cut copied
   `os.environ` to inject a read-only `PGOPTIONS`. That tripped
   `test_llm_router::test_no_other_module_reads_the_environment` — ARCHITECTURE.md §9's invariant that
   **only `capability/llm.py` reads the environment**, so credentials can't reach a grader. The right
   fix made the connector *more* faithful to requirement 5: pass no `env=` at all (the child inherits
   everything for free) and set read-only via SQL instead. EvalLoop code now never reads the
   environment, and the invariant holds untouched.
2. **Read-only is set in the argv, three layers deep.** Postgres uses two `--command` flags in one
   session — `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` then the query; MySQL prefixes
   `SET SESSION TRANSACTION READ ONLY;`. This is envelope layer 2 at the server, on top of layer 1
   (the envelope rejects a write *before the subprocess starts* — tested with `subprocess.run` stubbed
   to blow up) and layer 3 (the envelope caps rows/bytes).
3. **`describe()` reads `information_schema`** (`public` schema for Postgres, `DATABASE()` for MySQL)
   — catalog, never row data — via the CLI, grouping columns by table.
4. **Connection target via `connect_args`, never a password.** The developer supplies a DSN/URI
   (Postgres) or `--host/--database` flags (MySQL); the secret comes from the inherited env /
   `~/.pgpass` / `~/.my.cnf`, matching EL-006 (credential *sources*, never values, in EvalLoop).
5. **Output parsing is string cells.** Postgres: `--no-align --tuples-only` with an ASCII unit
   separator; MySQL: `--batch --skip-column-names` (tab-separated). The envelope caps afterward.
6. **Driver auto-install is the broker's** (EL-006), out of scope. This file is only the CLI
   mechanism; it reports UNAVAILABLE and stops.

## 4. Full-suite note (not an EL-308 regression)
`pytest` reports 1289 passed, 2 skipped, 1 failed — the extra skip is the no-local-Postgres test
behaving as designed; the failure is the F-G1a `testcases running/` demo-folder finding, unrelated to
EL-308.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **Read-only via SQL rather than `PGOPTIONS`** (§3.1/§3.2): confirm `SET SESSION CHARACTERISTICS AS
   TRANSACTION READ ONLY` (Postgres) and `SET SESSION TRANSACTION READ ONLY` (MySQL) are the belt you
   want at the server layer, given the connector deliberately no longer touches the environment.
3. **`connect_args` shape** (§3.4): a free-form argv tail today. If you'd rather the connector take a
   structured target (host/port/db) and build the flags per dialect, say so and I'll add it.
