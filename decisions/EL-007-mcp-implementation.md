# EL-007 — MCP implementation and the protocol isolation boundary

## Decision

MCP is implemented against the standard library, with no SDK, as `CLAUDE.md:45` requires ("No third-party frameworks or wrappers anywhere in the project"). That part was never open.

What this decision actually fixes is **the seam**: a single package, `evalloop/mcp/`, is the only place in the project that knows JSON-RPC, `_meta`, wire error codes or `resultType`. EL-307, EL-408 and EL-703 touch a typed façade — frozen dataclasses and two `Protocol`s — that contains no wire concept at all. **If the spec revs, one module changes, not three tracks.**

Pinned revision: **`2026-07-28`**. Transport before Gate V: **stdio only**; Streamable HTTP is deferred to a named ticket.

## Status

Decided — design note, no code — 2026-10-06. M0 forbids MCP code and none was written.

**Two findings in here invalidate assumptions in the plan**, and should be read before the rest:

1. **The spec revision the plan was written against is two revisions old, and the `initialize` handshake no longer exists.** `DEVELOPMENT_PLAN.md:147` gives EL-301's done-when as "**Handshake**, tool listing and calls work against a reference MCP server". MCP is stateless as of `2026-07-28`; there is no handshake to make work. That done-when needs rewording before EL-301 starts.
2. **The risk at `DEVELOPMENT_PLAN.md:278` ("MCP spec changes during the build → isolate the protocol in EL-301") has already fired, before the build began.** It is not a hypothetical to mitigate; it is the observed behaviour of this specification, which is why the seam below is specified tightly rather than left to EL-301's author.

## The pinned revision

| | |
|---|---|
| **Revision** | `2026-07-28` |
| **Status** | Current |
| **Source** | [Versioning](https://modelcontextprotocol.io/docs/learn/versioning.md), read 2026-10-06: "The **current** protocol version is **2026-07-28**" |
| **Previous revision** | `2025-11-25` |
| **Schema of record** | TypeScript at `schema/2026-07-28/schema.ts`, with a generated JSON Schema, per [Overview § Schema](https://modelcontextprotocol.io/specification/2026-07-28/basic/index) |

The version string is `YYYY-MM-DD` and marks "the last date backwards incompatible changes were made", and the version is *not* incremented for backwards-compatible change. So a revision bump always means a break, and the absence of one does not mean the text is stable.

`2026-07-28` is a large break from `2025-11-25`. From the [changelog](https://modelcontextprotocol.io/specification/latest/changelog), the parts that bear on this project: the `initialize`/`notifications/initialized` handshake is **removed** and every request now carries its protocol version and client capabilities in `_meta`; protocol-level sessions and `Mcp-Session-Id` are **removed**; `server/discover` is **added and mandatory for servers**; `ping`, `logging/setLevel` and `notifications/roots/list_changed` are **removed**; the HTTP GET stream and `resources/subscribe`/`unsubscribe` are replaced by `subscriptions/listen`; SSE resumability (`Last-Event-ID`) is **removed**; all results now carry a required `resultType`; server-initiated requests are replaced by the Multi Round-Trip Requests pattern; and Roots, Sampling and Logging are **deprecated**.

For EvalLoop the net effect is favourable. A stateless protocol with no handshake, no sessions and no resumable streams is markedly less code than the one the plan assumed.

## The method subset we implement

Anything not in this table is out; the exclusions are listed in the next section. "Client" means EvalLoop calls it; "server" means EvalLoop answers it. The gateway (EL-408) is both, because it is a server to the coding agent and a client to the upstream tool servers.

| Method | Role | Which ticket needs it |
|---|---|---|
| `server/discover` | both | **EL-703** (servers **MUST** implement it); EL-307 as the up-front version probe; EL-408 in both directions |
| `tools/list` | both | EL-307, EL-408, EL-703 |
| `tools/call` | both | EL-307, EL-408, EL-703 |
| `prompts/list` | client only | **EL-310** — `DEVELOPMENT_PLAN.md:156` includes "MCP prompts" as eval inputs |
| `prompts/get` | client only | EL-310 |
| `notifications/cancelled` | client → server | EL-307 on timeout; EL-408 forwards. stdio only — on Streamable HTTP, closing the response stream *is* the cancellation |
| `notifications/progress` | receive only | EL-408 forwards to the agent; EL-307 ignores |
| `notifications/message` | receive only | EL-408 forwards; emitted only for requests carrying `io.modelcontextprotocol/logLevel` |

Three obligations that come attached to the above rather than as separate methods, and which EL-301 must implement because they are not optional:

- **Per-request `_meta`.** `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` are **required on every request**; `io.modelcontextprotocol/clientInfo` and `io.modelcontextprotocol/logLevel` are optional, and clients **SHOULD** send `clientInfo`. A request missing a required field **MUST** be rejected with `-32602`. Our server **SHOULD** return `io.modelcontextprotocol/serverInfo` in every result's `_meta`.
- **`resultType` on every result.** `"complete"` for ordinary results, `"input_required"` for MRTR. An absent `resultType` from an older server **MUST** be treated as `"complete"`; an unrecognised value **MUST** be treated as invalid.
- **`ttlMs` and `cacheScope`** are required on results from `tools/list`, `prompts/list` and `server/discover` under the `CacheableResult` interface, so EL-703 must emit them. As a client we may ignore them, and initially will.

Pagination (`cursor` / `nextCursor`) must be *handled* by the client — `list_tools()` loops until `nextCursor` is absent — but our own server returns a single page and no cursor.

### Deliberately not implemented

| Excluded | Why |
|---|---|
| `resources/*` — `resources/list`, `resources/read`, `resources/templates/list`, `notifications/resources/updated` | EvalLoop exposes tools, not resources, and EL-307 reads databases through tools inside the EL-305 envelope. A tool result may still carry `resource_link` or embedded `resource` content, which we treat as opaque content |
| `subscriptions/listen`, `notifications/subscriptions/acknowledged`, `notifications/tools/list_changed`, `notifications/prompts/list_changed`, `notifications/resources/list_changed` | A session tool re-lists on demand. Long-lived push streams buy nothing and cost a keep-alive-aware SSE reader. **Deferred to EL-317** |
| `completion/complete` | Argument autocompletion is a UI affordance for interactive clients |
| **Roots, Sampling, Logging** (`roots/list`, `sampling/createMessage`, `logging/setLevel`) | **Deprecated in `2026-07-28`**; the spec says new implementations should not add support. Suggested migrations are what EvalLoop already does: pass paths as tool arguments, call LLM provider APIs directly, log to `stderr` |
| MRTR *driving* — gathering input and retrying with `inputResponses` / `requestState` | EvalLoop's own server never returns `InputRequiredResult`: its five tools need no user input mid-call. As a client, an `input_required` result is surfaced as `ErrorKind.input_required` and the call fails rather than silently prompting. **EL-408 must forward it verbatim**, since the agent is a legitimate MRTR participant |
| The `io.modelcontextprotocol/tasks` extension | Moved out of core into an extension in `2026-07-28`. EvalLoop's own long operations are owned by the session orchestrator, not the protocol |
| The Authorization framework — OAuth 2.0, Dynamic Client Registration, Client ID Metadata Documents, RFC 9207 `iss` validation | The spec says stdio implementations **SHOULD NOT** follow it and should "retrieve credentials from the environment". With stdio-only, this entire surface costs nothing. **Deferred to EL-316** with HTTP |
| `x-mcp-header` / `Mcp-Param-*` mirroring | A Streamable HTTP client **MUST** support it, so it is deferred with the transport, not skipped. **EL-316** |
| HTTP+SSE transport (`2024-11-05`) | Deprecated since `2025-03-26` and now formally Deprecated; "New implementations **SHOULD NOT** adopt it" |
| `initialize`, `notifications/initialized`, `ping`, `Mcp-Session-Id`, `Last-Event-ID` | Removed from the protocol |
| Legacy fallback to the `initialize` handshake for pre-`2026-07-28` servers | A deliberate scope cut, not an oversight — see `## Cost`. EvalLoop supports modern servers only at first; a legacy server surfaces as `ErrorKind.unsupported_revision` with its advertised versions. **EL-318** if a real server forces it |
| JSON-RPC batching | Not available: on stdio each message is one line, and on HTTP the POST body **MUST** be a single request or notification |
| `icons` | Display metadata for interactive UIs |

## The seam

One package, `evalloop/mcp/`, is the protocol. Inside it, exactly one module — `wire.py` — constructs and parses JSON-RPC envelopes, builds and validates `_meta`, maps wire error codes, and interprets `resultType`; one module per transport owns framing and headers; and `types.py` holds the façade. Outside `evalloop/mcp/`, **nothing may know the wire format**: no module may import `json` to talk MCP, reference `jsonrpc`, `_meta`, `params`, a numeric error code, `resultType`, or a method string. EL-307 receives an `McpClient`, EL-703 implements a `ToolProvider`, and EL-408 — which must pass calls through *unchanged* — gets a deliberately lower, opaque seam that forwards bytes verbatim and never re-serialises a parsed message. The revision string lives in exactly one constant. Grepping the repository for `jsonrpc` outside `evalloop/mcp/` is the test, and it should return nothing; it is worth an actual test rather than a convention.

```python
# evalloop/mcp/types.py — the seam. No wire concept appears below this line.

PROTOCOL_REVISION: Final = "2026-07-28"        # the only place this string exists

class ErrorKind(StrEnum):                       # wire codes never escape wire.py
    unsupported_revision = "unsupported_revision"      # -32022
    missing_client_capability = "missing_client_capability"  # -32021
    header_mismatch = "header_mismatch"                # -32020
    method_not_found = "method_not_found"              # -32601
    invalid_params = "invalid_params"                  # -32602, and -32002 from legacy
    input_required = "input_required"                  # MRTR, surfaced not driven
    server_error = "server_error"
    transport_failed = "transport_failed"              # local: spawn, EOF, timeout

class McpError(Exception):
    kind: ErrorKind
    message: str
    retryable: bool
    supported_revisions: tuple[str, ...]        # populated for unsupported_revision

@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, object]          # JSON Schema 2020-12, opaque here
    output_schema: Mapping[str, object] | None = None
    title: str | None = None

@dataclass(frozen=True, slots=True)
class ToolResult:
    content: tuple[Content, ...]                # text / image / audio / resource, tagged
    structured: object | None = None
    is_error: bool = False                      # tool execution error, not protocol error

@dataclass(frozen=True, slots=True)
class ServerIdentity:
    name: str
    version: str
    supported_revisions: tuple[str, ...]
    capabilities: frozenset[str]                # {"tools", "prompts", …}
    instructions: str | None = None

class McpClient(Protocol):                      # EL-307, EL-310 see only this
    def discover(self) -> ServerIdentity: ...
    def list_tools(self) -> tuple[ToolSpec, ...]: ...        # pagination handled inside
    def call_tool(self, name: str, arguments: Mapping[str, object],
                  timeout_s: float) -> ToolResult: ...
    def list_prompts(self) -> tuple[PromptSpec, ...]: ...    # EL-310
    def get_prompt(self, name: str,
                   arguments: Mapping[str, str]) -> PromptText: ...
    def close(self) -> None: ...

class ToolProvider(Protocol):                   # EL-703 implements only this
    def identity(self) -> ServerIdentity: ...
    def tools(self) -> tuple[ToolSpec, ...]: ...
    def invoke(self, name: str,
               arguments: Mapping[str, object]) -> ToolResult: ...

# evalloop/mcp/relay.py — EL-408 only. Forwarding, not interpreting.

@dataclass(frozen=True, slots=True)
class RelayedCall:
    """What the EL-409 recorder needs, read from a frame that is forwarded verbatim."""
    method: str
    tool_name: str | None                       # params.name, when present
    arguments: Mapping[str, object]             # for redaction + audit only
    raw: bytes                                  # forwarded unchanged; never rebuilt

class Relay(Protocol):
    def forward(self, frame: bytes) -> bytes: ...
    def observe(self, frame: bytes) -> RelayedCall | None: ...
```

`Relay` is the part that makes EL-408's done-when ("Agent tool calls pass through unchanged") achievable. The gateway forwards `raw` byte-for-byte and uses `observe()` only to read what the recorder needs. It never rebuilds a message from the parsed form, so a field added in a future revision — or any method EvalLoop does not implement — passes through untouched. A gateway built on the typed `McpClient` seam instead would silently drop unknown fields and would have to be revised on every spec bump.

**If the spec revs, which files change?** `evalloop/mcp/wire.py`, the `PROTOCOL_REVISION` constant in `types.py`, and — only if framing or headers changed — the one transport module. EL-307, EL-310, EL-408 and EL-703 change only if the *façade's* semantics change, which a revision alone does not do: the `2026-07-28` break, had it landed mid-build, would have touched `wire.py` and nothing else, because the handshake, sessions and `resultType` are all wire concerns that never reach the seam.

## Transports

### stdio — the only one needed before Gate V

EL-307's done-when is "An external MCP DB server is queried through the envelope", and local MCP servers are overwhelmingly stdio subprocesses. EL-408's gateway can itself be a stdio server that the agent launches, since EL-411 generates the agent's config. So **stdio alone clears Gate V**, and it is also the cheaper transport: per the [stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) the framing is one JSON-RPC message per line, messages "**MUST NOT** contain embedded newlines", and all request metadata is carried inline in `_meta` — "There is no header layer."

What EL-301 must get right here is lifecycle rather than parsing. The server **MAY** write arbitrary UTF-8 to `stderr` and the client "**SHOULD NOT** assume `stderr` output indicates error conditions", so stderr must be drained concurrently or a chatty server fills the pipe buffer and deadlocks — the likeliest bug in this module. The client **MUST NOT** write responses to the child's stdin, and the server **MUST NOT** write requests to stdout. Shutdown is: close stdin, wait, then escalate `SIGTERM` → `SIGKILL`; servers **SHOULD** exit on EOF. Because the protocol is stateless, an unexpected child exit simply loses in-flight requests and the client restarts and retries — which is far simpler than the session-resumption logic the older revisions needed.

### Streamable HTTP — deferred to EL-316

Needed only when a configured upstream server is a remote HTTP endpoint. Required before EL-408 **only if** the coding agent's configured servers include an HTTP endpoint; otherwise it can slide to M5, where remote servers are an enterprise concern.

**On whether we need streaming: yes, if we implement the HTTP client at all — and no, for our own server.** Per the [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http), for a JSON-RPC request "the server **MUST** return either `Content-Type: application/json` … or `Content-Type: text/event-stream`" and "**The client MUST support both**". A client therefore cannot opt out of SSE parsing, because the choice is the server's. The cost is smaller than it was, though: the GET stream and `Last-Event-ID` resumability are gone, and we exclude `subscriptions/listen`, so SSE reduces to reading one request-scoped stream — accumulate `data:` lines, ignore comment lines beginning with `:` (keep-alives), stop at the final response. Our *server* may always answer with `application/json`, so **EL-703 never needs to emit SSE**.

The rest of EL-316's obligations, noted so the deferral is costed rather than vague: a single POST-only endpoint; `Accept` listing both media types; `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` headers required, with values that **MUST** match the body or the server returns `400` with `-32020`; `x-mcp-header` mirroring, which clients **MUST** support; `Origin` validation **MUST** (403 on mismatch) and binding to localhost **SHOULD**; `202 Accepted` for notifications; `405` for GET or DELETE; and the Authorization framework, which stdio avoids entirely.

## Cost of writing this ourselves, and whether 2 days survives

**It does not.** `DEVELOPMENT_PLAN.md:147` estimates EL-301 at 2 engineer-days for "JSON-RPC 2.0 over stdio + HTTP". Decomposed for stdio only, client and server roles, against `2026-07-28`:

| Work | Estimate (days) |
|---|---|
| JSON-RPC 2.0 envelopes, id allocation and correlation, notification vs request vs response | 0.5 |
| `_meta` construction and validation (2 required keys, 2 optional, `serverInfo` on results) | 0.25 |
| Error taxonomy → `ErrorKind` | 0.25 |
| stdio framing, concurrent stderr drain, process lifecycle, EOF, restart | 0.75 |
| `server/discover` in both roles, version negotiation, `UnsupportedProtocolVersionError` | 0.25 |
| `resultType` handling, pagination loop, `ttlMs`/`cacheScope` emission | 0.25 |
| Seam types and `Protocol`s, including `Relay` | 0.25 |
| Reference-server conformance fixture (below) | 0.75–1.5 |
| **Total** | **3.25–4 days** |

The four cost drivers, as the ticket asked:

**Spec drift** is the largest and is now measured rather than guessed: one breaking revision in roughly eight months, removing a handshake, sessions, three methods and stream resumability. Deprecated-but-present features (Roots, Sampling, Logging, HTTP+SSE, DCR) carry a minimum twelve-month window, so further churn is scheduled, not merely possible. This cost is not avoidable but it is *containable*, which is the entire argument for the seam; the mitigation at `DEVELOPMENT_PLAN.md:278` is correct and should be strengthened from "isolate the protocol" to the grep-testable rule above.

**Auth costs nothing, for now.** This is the one place the work is smaller than feared: stdio implementations "**SHOULD NOT**" follow the Authorization framework and instead "retrieve credentials from the environment". Choosing stdio-first therefore defers OAuth, Dynamic Client Registration, Client ID Metadata Documents and `iss` validation in their entirety. Any later move to HTTP against a remote server re-opens all of it, and EL-316 should be estimated with that in mind rather than as a transport swap.

**Capability negotiation is cheap under the new model** — there is no handshake to get wrong, just two `_meta` keys per request — but it is not free: a server **MUST NOT** rely on an undeclared client capability and **MUST** return `-32021` with `data.requiredCapabilities` when one is missing, and our server declares only `tools`.

**The error taxonomy is fiddlier than it looks,** and is the most likely source of silent non-conformance. We must map the standard JSON-RPC codes plus `-32020`/`-32021`/`-32022`; **must not** emit anything in `-32000`–`-32019`, which is now legacy-only; **must not** emit `-32002` or `-32042`, which are reserved and withdrawn; but **should** still accept `-32002` from an older server, where it means resource-not-found and is now `-32602`.

**The hidden cost is the fixture, not the protocol.** EL-301's done-when requires working "against a reference MCP server", and with no SDK there is no reference implementation in-process. An in-repo fake is the only thing that can run in CI, and it is circular — it shares our reading of the spec, so it proves self-consistency rather than conformance. Honest resolution, which is where the 0.75–1.5 range comes from: build the in-repo fake for CI, and additionally run against a real third-party stdio server as an opt-in, manually-invoked test that is not part of `pytest`'s default run. The real server is what catches a misreading; the fake is what keeps the suite hermetic and dependency-free under `CLAUDE.md:43`.

Recommended revision: **EL-301 to 3.5 days, stdio only**, with Streamable HTTP split out as EL-316. `DEVELOPMENT_PLAN.md:9` already schedules a re-check of Track V estimates after M0, so this is input to that rather than a new exception.

## Reopen trigger

> **This decision reopens if a revision after `2026-07-28` changes stdio framing or the `_meta` request contract, or if a server EvalLoop must reach implements only a handshake-era revision — observed by the engineer at EL-301 or EL-307 and reported at Gate V; a revision that changes only methods we do not implement is absorbed by `wire.py` and is not a reopen.**

## Consequences

- **`DEVELOPMENT_PLAN.md:147` must be reworded before EL-301 starts.** "Handshake, tool listing and calls work against a reference MCP server" describes a protocol that no longer exists.
- **EL-703's five names are tool names, not JSON-RPC methods.** `DEVELOPMENT_PLAN.md:223` lists `report_intent`, `plan`, `evaluate`, `verify_claim`, `findings` in a way that reads as methods; they are tools invoked through `tools/call`, as `ARCHITECTURE.md:177-181` has them (`evalloop.report_intent(...)`). The dotted form is valid — tool names allow letters, digits, `_`, `-` and `.` — and `tools/list` **SHOULD** return them in a deterministic order, which `CLAUDE.md §7` rule 8 already requires of us.
- **EL-310 is a consumer of EL-301 that the dependency graph does not show.** It needs `prompts/list` and `prompts/get`; its stated dependency is EL-307 alone (`DEVELOPMENT_PLAN.md:156`), so either EL-301 ships the prompts pair or EL-310 inherits protocol work.
- **EL-408 must build on `Relay`, not on `McpClient`.** A typed round-trip would drop unknown fields and break "pass through unchanged".
- **Two new tickets are proposed:** EL-316 (Streamable HTTP + Authorization) and EL-317 (`subscriptions/listen`), plus EL-318 held in reserve for handshake-era fallback. Each is a named deferral target so nothing above is merely "later".
- No code was written and `evalloop/` is untouched; the signature sketch lives here, as the ticket requires.

## Follow-up — proposed, not applied

1. **`DEVELOPMENT_PLAN.md:147`** — retitle EL-301 to "**MCP protocol core:** JSON-RPC 2.0 over stdio, stdlib only", change its done-when to "`server/discover`, `tools/list` and `tools/call` work against a third-party stdio MCP server; no module outside `evalloop/mcp/` references the wire format", and re-estimate to 3.5.
2. **`DEVELOPMENT_PLAN.md:92`** — update the EL-007 row to "✅ Decided: stdlib JSON-RPC, no SDK; revision `2026-07-28` pinned; stdio first, HTTP deferred to EL-316 — `decisions/EL-007-mcp-implementation.md`".
3. **New rows in E3** — EL-316 "Streamable HTTP transport + Authorization framework (client)", EL-317 "`subscriptions/listen` push notifications", both depending on EL-301.
4. **`DEVELOPMENT_PLAN.md:156`** — add EL-301 to EL-310's `Depends on`, for `prompts/list` and `prompts/get`.
5. **`DEVELOPMENT_PLAN.md:278`** — strengthen the mitigation to "Isolate the protocol in `evalloop/mcp/`; a test asserts no wire vocabulary outside it".
6. **`ARCHITECTURE.md:275`** — `evalloop/mcp/` is listed as the MCP *server* arriving after M3, but EL-301 creates the package after M1 and the client and gateway both live in it. Correct the row to the package's real scope and date.

## Related

- Spec pages read for this decision, all at revision `2026-07-28` and read 2026-10-06: [Versioning](https://modelcontextprotocol.io/docs/learn/versioning.md) · [Changelog](https://modelcontextprotocol.io/specification/latest/changelog) · [Overview, `_meta` and error codes](https://modelcontextprotocol.io/specification/2026-07-28/basic/index) · [stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) · [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) · [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) · [Discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- `decisions/EL-002-mcp-tools-in-enum.md` — kept MCP out of the `Tool` enum on the grounds that it is transport owned by the broker and the gateway. This record is the other half of that argument: the transport exists, and it is confined to one package.
- `decisions/EL-006-db-driver-policy.md` — EL-307 turns an MCP server into a `Connector`, so an MCP database server is a mechanism beneath the same EL-305 envelope as `psql`.
- `decisions/EL-005-track-order.md` — sets when EL-301, Gate V and EL-408 land, and therefore when the reopen trigger is checked.
