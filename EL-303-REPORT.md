# EL-303 — V2 Connector discovery with provenance

**⚠ Depends on EL-302 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_connector_discovery.py` 9 passed; `mypy --strict evalloop/`
clean on 50 files; standard library only. Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/__init__.py` | the connector layer package (`ARCHITECTURE.md` §6, component 16) |
| `evalloop/connect/discover.py` | `discover(root) -> tuple[Candidate, ...]`, `Candidate`, `Provenance` |
| `tests/test_connector_discovery.py` | 9 tests; the sample repo is built in `tmp_path` (nothing committed) |

## 2. The five results
| # | Result | How |
|---|---|---|
| 1 | Candidates with file:line provenance | each `Candidate` carries a `Provenance(path, line, reason)` — "docker-compose.yml:6 defines service 'qdrant'". Sources: `.env*` keys, `docker-compose` services, `create_engine`/`psycopg.connect`/`QdrantClient`/`chromadb.HttpClient`/… call sites, `alembic.ini` |
| 2 | Zero connections, zero credentials | a socket guard (connect/connect_ex/create_connection patched to raise) is live across the whole scan and nothing trips it |
| 3 | A credential value never in a candidate | from `.env` only the **key** is kept (`.env:DATABASE_URL`); the value after `=` is split off and dropped. A planted secret never appears in any candidate field — tested, and a mutation that puts the raw line in a candidate fails that test |
| 4 | ast/text only; never import or run repo code | Python files are `ast.parse`d; a `settings.py` that would write a sentinel and raise on import does neither — proven |
| 5 | Deterministic ordering | sorted by (path, line, kind, detail); `discover(repo) == discover(repo)` |

A database-shaped source maps to `Tool.db_connection`, a vector store to `Tool.vector_store`; a
non-endpoint secret like `OPENAI_API_KEY` is **not** reported (tested).

## 3. Calls I made
1. **Listening-port discovery is deferred, and said so.** `ARCHITECTURE.md` §6.1 lists "listening
   local ports" as a source, but that is a live system probe, not a text scan, and result 4 says
   "ast/text scanning only." I scan files only and flagged the gap in the module docstring rather
   than quietly probe the OS.
2. **One candidate per piece of evidence, not merged across sources.** A Postgres that appears in
   `.env`, `docker-compose`, a `create_engine` call and `alembic.ini` yields four candidates, each
   with its own provenance — matching §6.1's per-evidence example ("because docker-compose.yml:14
   …"). Cross-source consolidation is a later refinement, not silent de-duplication.
3. **docker-compose is parsed line-by-line, not with a YAML library** (no PyYAML, `CLAUDE.md` §1).
   It reads services, images and `ports:` for *evidence*; it is not a full compose parser, which is
   all discovery needs.
4. **Host/port only from non-secret sources.** A compose `ports:` line yields `localhost:6333`; a
   connection string is never parsed for host/port, because that means reading the secret.

## 4. Full-suite note (not an EL-303 regression)
`pytest` reports 1227 passed, 1 skipped, 1 failed — the F-G1a finding from the `testcases running/`
demo folders, unrelated to EL-303.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **Listening-port discovery** (§3.1): keep deferred (text-scan only), or add a live port probe as
   a separate, clearly-consented step?
3. **Per-evidence vs consolidated candidates** (§3.2): is per-evidence the shape you want for the
   consent UI, or should EL-304 group them before proposing?
