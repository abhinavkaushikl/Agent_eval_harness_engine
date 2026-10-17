# EL-307 — MCP client connector

**⚠ Depends on EL-301 + EL-306 (both done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_mcp_connector.py` 10 passed; `mypy --strict evalloop/` clean on
55 files; standard library only; the read/probe/describe test runs the EL-301 reference server over
stdio, **no network**. Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/mcp_connector.py` | `MCPConnector` — any external MCP server as a read-only `Connector`; `McpClient` seam (`Discoverable` + `ToolCaller`) |
| `tests/test_mcp_connector.py` | 10 tests; a live `StdioClient` + reference server, plus in-process fakes for the gating proofs |

`MCPConnector` implements the EL-306 `Connector` contract (`isinstance(conn, Connector)` tested), so
the MCP-exposed resource flows through the **same** probe/describe/read as SQLite.

## 2. The result — four requirements
| # | Requirement | How |
|---|---|---|
| 1 | External MCP server wrapped as a Connector, through broker (EL-302) + envelope (EL-305) | `MCPConnector(client, broker=…, endpoint=…, envelope=…)`; each op authorises via `broker.check` first; `read()` runs `envelope.execute(...)` under the granted caps |
| 2 | A read-only query returns rows through `read()`, using the stdlib reference server, no net | the reference server's `echo` is the read tool; `read("SELECT 1 FROM anywhere")` passes the envelope, is echoed back, and returns `[("SELECT 1 FROM anywhere",)]`. JSON-array tool output is parsed into real rows (separate test) |
| 3 | A write-shaped MCP tool call is rejected by the envelope **before it is sent** | `read("DROP TABLE users")` raises `ReadOnlyViolation` at envelope layer 1; the fake client records **zero** `call_tool` invocations — the query never left the process. A read-shaped query, by contrast, does reach the tool (`calls == ["query"]`) |
| 4 | Only the EL-307 façade is used; wire terms stay under `evalloop/mcp/` | everything imports from `evalloop.mcp` (the typed façade); two tests assert no `jsonrpc` / `_meta` / `resultType` string appears in any `.py` outside `evalloop/mcp/` (one via file scan, one via `grep`) |

## 3. Calls I made
1. **MCP is transport, not a capability** (decision EL-002). The broker capability is the *resource*
   the server exposes — `MCPConnector(tool=Tool.db_connection)` by default — not an "mcp" tool. The
   test grants `db_connection` for the endpoint; there is no MCP-specific grant.
2. **`read(sql)` carries the query; the envelope gates it before the tool call.** The connector
   adapts the MCP read tool into an envelope `Executor` whose `run()` calls
   `call_tool(read_tool, {query_arg: sql})`. Layer 1 runs first, so a write-shaped query is rejected
   before `call_tool` is reached — "an MCP tool is not a hole in the read-only contract." `read_tool`
   and `query_arg` are configurable (default `query` / `sql`); the live test uses `echo` / `text`.
3. **`describe()` maps the server's tools to structure.** A generic MCP server exposes *tools*, not
   tables, so each tool becomes a `Table` (name = tool name, columns = its input-schema properties).
   It lists tools only — reads no rows. For an MCP-exposed database that fronts real tables, this
   surfaces the query tool's parameters; richer table introspection is the server's to expose.
4. **Row parsing is tolerant.** A tool whose text is a JSON array yields real rows (lists → tuples,
   dicts → value tuples); anything else becomes a single text cell. The envelope then caps.
5. **This is strictly the client (EL-008).** Nothing here implements an MCP *server*;
   `evaluate`/`verify_claim` stay behind Gate 3. HTTP transport is out of scope — stdio only.

## 4. Full-suite note (not an EL-307 regression)
`pytest` reports 1281 passed, 1 skipped, 1 failed — the F-G1a finding from the `testcases running/`
demo folders, unrelated to EL-307. Relocating those folders to a dot-dir clears it.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **`describe()` = the server's tools** (§3.3): is tools-as-structure the right shape for an
   MCP-exposed database, or do you want the connector to call a dedicated schema tool when the server
   offers one (e.g. a `list_tables` tool), falling back to tools otherwise?
3. **`read_tool`/`query_arg` configuration** (§3.2): per-connector constructor args today. If you want
   this discovered from the server's advertised tools instead of configured, say so.
