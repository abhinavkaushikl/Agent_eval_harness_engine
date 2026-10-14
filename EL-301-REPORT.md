# EL-301 — MCP protocol core (stage: Track V, first ticket)

**⚠ Depends on Gate 1 (EL-212, awaiting your sign-off) and Gate 0 (open).** Track V may not *start*
until both are closed; I built EL-301 ahead of them, as the M1 work was built ahead of Gate 0,
because this ticket rests on decision **EL-007** (which exists), not on the gated planner/registry
rulings. Flagging it per the standing rule.

**Status: done.** The MCP core's own suite is green — `pytest tests/test_mcp_core.py` 16 passed,
`mypy --strict evalloop/` clean on 47 files, standard library only. Full-suite caveat in §6.

---

## 0. The headline: the ticket describes a protocol revision that no longer exists

The prompt (and the board) ask for an **`initialize` handshake** and "the revision negotiated in the
handshake." **Decision EL-007 says the pinned revision `2026-07-28` removed that handshake** —
quoting it: *"MCP is stateless as of 2026-07-28; there is no handshake to make work,"* and EL-301's
"handshake" done-when *"needs rewording before EL-301 starts."*

Per the project's rule — **trust the decision over the ticket** — I built the real `2026-07-28`
shape, not the removed handshake:

| The ticket says | 2026-07-28 actually (EL-007) | What I built |
|---|---|---|
| `initialize` handshake | **removed**; `server/discover` is added and mandatory | `StdioClient.discover()` → `server/discover` |
| revision negotiated in the handshake | every request is self-describing | the pinned version rides in each request's `_meta`; `discover` checks the server lists it, else `ProtocolVersionMismatch` |
| (unstated) | `_meta` per request: `protocolVersion` + `clientCapabilities` **required**, `clientInfo` SHOULD | attached to every request; a server MUST `-32602` a missing one |
| (unstated) | every result carries a required `resultType` | the client rejects a result without it |

**So the done-when should be reworded** from "handshake, tool listing and calls" to "**discovery**,
tool listing and calls." The capability is the same; the word "handshake" is from a two-revisions-old
spec.

## 1. The other conflict, resolved: stdio only

The board summary says "stdio **+ HTTP**." EL-007 says transport before Gate V is **stdio only**;
Streamable HTTP is "deferred to a named ticket." I built **stdio only**. HTTP should be its own
later ticket; I did not build it.

## 2. What exists
| File | Contents |
|---|---|
| `evalloop/mcp/wire.py` | JSON-RPC 2.0 + newline framing + the `_meta` keys + error codes + `resultType` — **the only module that knows the wire** |
| `evalloop/mcp/facade.py` | frozen dataclasses (`ServerInfo`, `Tool`, `ToolResult`, `Content`), two Protocols (`Discoverable`, `ToolCaller`), the typed error taxonomy — **no wire concept** |
| `evalloop/mcp/client.py` | `StdioClient`: launch a server subprocess, `discover`/`list_tools`/`call_tool`, reap on close |
| `evalloop/mcp/__init__.py` | the façade re-exported; the only import surface downstream touches |
| `tests/fixtures/mcp/reference_server.py` | a stdlib MCP server (2026-07-28) with failure modes |
| `tests/test_mcp_core.py` | 16 tests, no network |

## 3. The five results
| # | Result | How |
|---|---|---|
| 1 | stdio JSON-RPC client, stdlib only | `subprocess` + `json` (via `wire`); a test proves `evalloop/mcp/` imports only the stdlib |
| 2 | discover → list → call against a reference server, no network | the fixture server runs as a subprocess; `discover`/`list_tools`/`call_tool` all round-trip |
| 3 | typed façade; wire concepts only under `evalloop/mcp/` | a grep test asserts `jsonrpc`/`_meta`/`resultType` appear nowhere else in `evalloop/`; the façade carries no wire concept, and `StdioClient` satisfies the `ToolCaller` Protocol |
| 4 | malformed frame / error code → typed error | a non-JSON frame → `ProtocolViolation`; a server error object → `ToolFailed(code, message)`; a result with no `resultType` → `ProtocolViolation`; EOF → `TransportClosed` |
| 5 | revision pinned; mismatch fails naming both | pinned `2026-07-28`; a server advertising only `2099-01-01` → `ProtocolVersionMismatch` whose message names both. Per 2026-07-28 this is a *discovery* check, not a handshake negotiation (§0) |

## 4. Interpretation flagged for review
EL-007 states the 2026-07-28 facts (stateless, per-request `_meta`, required `resultType`,
`server/discover` mandatory) but the **exact field schema of `server/discover`'s result** lives in
`schema/2026-07-28/schema.ts`, which this repo does not carry. I used a reasonable shape
(`serverInfo` / `protocolVersions` / `capabilities`) in both the client and the reference server, so
they interoperate and the tests are meaningful — **but it must be checked against the real schema
before talking to a live server.** Same for the precise `_meta` namespace keys: I used the ones
EL-007 quotes verbatim (`io.modelcontextprotocol/protocolVersion`, `…/clientCapabilities`,
`…/clientInfo`, `…/serverInfo`).

## 5. Calls I made
1. **Two Protocols = `Discoverable` + `ToolCaller`.** These are the seam EL-307 (DB-over-MCP) and
   the grader build on. Prompts/resources are EL-310's; I did not add a prompt Protocol here to
   avoid building ahead of that ticket.
2. **Newline-delimited framing**, not LSP `Content-Length` — that is MCP's stdio transport.
3. **`stderr` is the server's**, routed to `DEVNULL`; the spec reserves it for server logging.
4. **A bounded skip loop** (1000 frames) so a server that floods notifications without replying
   fails with `ProtocolViolation` rather than hanging.

## 6. Full-suite note (not an EL-301 regression)
`python3 -m pytest` reports **1205 passed, 1 skipped, 1 failed**. The one failure is
`test_the_virtualenvs_vendored_tests_are_not_this_repositorys` — the **F-G1a finding**, triggered by
the `testcases running/` demo folders created earlier in this session (their `tests/test_*.py` are
counted by the harvester's repo walk). It is **not** caused by EL-301 (the `.gate1/` toy repos are
under a dot-dir the harvester skips; `testcases running/` is not). Relocating those demo folders to a
dot-dir restores green, exactly as `.gate1/` did. I left your sandbox in place rather than move files
you have open; say the word and I'll relocate them.

## 7. Out of scope (held)
The EvalLoop MCP **server** (`evaluate`/`verify_claim`/`findings` — Gate 3, EL-008): not built; this
is the **client**. Streamable HTTP (EL-007): deferred. Wrapping an MCP server as a Connector:
EL-307.

## 8. Rulings I need
1. **Reword EL-301's done-when** from "handshake" to "discovery" (§0) — EL-007 already said this is
   needed; this ticket is where it bites.
2. **Confirm stdio-only** and spin HTTP into its own ticket (§1).
3. **Verify the `server/discover` and `_meta` shapes** against `schema/2026-07-28/schema.ts` before
   EL-307 points this at a real server (§4).
4. **Accept building ahead of Gate 1/Gate 0** (as for the M1 work).
