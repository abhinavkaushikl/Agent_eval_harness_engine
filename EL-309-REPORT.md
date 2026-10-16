# EL-309 — Vector store (Qdrant over HTTP)

**⚠ Depends on EL-306 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_qdrant_connector.py` 9 passed; `mypy --strict evalloop/` clean on
57 files; standard library only (`urllib`, `http.server` in the test); **no vendor SDK imported**.
Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/vector_qdrant.py` | `QdrantConnector`, `reject_vector_writes` (the vector guard) |
| `evalloop/connect/protocol.py` | extended: a `Collection` type + `Schema.collections` (the EL-306 report flagged this) |
| `tests/test_qdrant_connector.py` | 9 tests against a loopback stdlib HTTP server — no live Qdrant, no network |

`QdrantConnector` implements the EL-306 `Connector` contract (`isinstance` tested), so a vector store
flows through the **same** probe/describe/read as SQLite, MCP and the SQL-CLI backends.

## 2. The result — five requirements
| # | Requirement | How |
|---|---|---|
| 1 | probe/describe/read over HTTP via urllib, through broker + envelope | `urllib.request` only; each op authorises via `broker.check` first; `read()`/`search()` route through `envelope.execute(...)` with a `_HttpExecutor` |
| 2 | describe enumerates collections AND the embedding model in use | `describe()` GETs `/collections` then each `/collections/{name}`, returning `Collection(name, vector_size, distance, embedding_model)`. The model is read from the collection's vector config when the store records it; **`None` when it does not — unknown, never invented** (corpus G1). Tested both ways: `docs` reports `BAAI/bge-small-en-v1.5`, `faqs` reports `None` |
| 3 | read() is a read-only search; a write/delete verb is rejected by the envelope | the envelope's layer-1 guard is `reject_vector_writes`: a GET or a POST to a known query endpoint is a read; PUT/DELETE/PATCH, or a POST that writes points/collections, raises `ReadOnlyViolation` **before the request is sent** — tested, and the fake server records zero such requests |
| 4 | the test runs against a fake HTTP server fixture, no net | a `ThreadingHTTPServer` on `127.0.0.1:0` in a daemon thread stands in for Qdrant |
| 5 | a source scan proves no vendor SDK import | a scan asserts no `import qdrant_client` / `from qdrant_client` / `qdrant-client` under `evalloop/connect/` |

## 3. Calls I made
1. **The envelope's injectable guard carried the whole weight.** EL-305 made `static_guard`
   pluggable; here it is `reject_vector_writes`, which classifies an HTTP *operation*
   (`{"method","path","body"}`) rather than SQL. So "the safety is the envelope's, not Qdrant's" holds
   for a non-SQL backend with no change to the envelope. Read-only POST endpoints are whitelisted
   (`/points/search`, `/points/query`, `/points/scroll`, `/points/recommend`, `/points/count`,
   `/points/search/batch`); everything else is a write.
2. **Every untrusted op goes through one chokepoint** (`_operation` / `_search`), so a write verb is
   impossible to issue — the write-rejection test drives `_operation("DELETE"/"PUT"/"POST-upsert")`
   and watches the envelope stop each before the wire. `describe()`/`probe()` issue only GETs (trusted
   read-only introspection, audited), consistent with the other connectors.
3. **The embedding model is read, never guessed.** It comes from the collection's vector config where
   Qdrant records it (inference metadata); absent that, `describe()` reports `None`. Surfacing
   "unknown" is the honest, useful answer — it tells you to confirm the model yourself before trusting
   a recall@k, which is exactly the G1 failure the field exists to prevent.
4. **No credentials, no environment.** The connector takes `base_url` only and reads neither a
   credential nor the environment (ARCHITECTURE.md §9). An authenticated Qdrant would have its API-key
   header injected by the capability layer later; it is not stored here.
5. **`Schema` extended, not replaced.** `Schema.collections` defaults to `()`, so the relational
   connectors are unaffected; the vector connector returns `tables=()` with populated `collections`.

## 4. Full-suite note (not an EL-309 regression)
`pytest` reports 1298 passed, 2 skipped, 1 failed — the F-G1a `testcases running/` demo-folder
finding, unrelated to EL-309.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **Read-only POST whitelist** (§3.1): confirm the query-endpoint list is complete for the Qdrant
   version you target, or name any additional read endpoint to whitelist.
3. **Embedding-model source** (§3.3): I read it from the collection config. If your deployment records
   the model elsewhere (a payload field, a sidecar), tell me where and I will read that instead of
   reporting `None`.
