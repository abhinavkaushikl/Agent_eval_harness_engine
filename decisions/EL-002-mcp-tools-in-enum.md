# EL-002 — MCP tools in the `Tool` enum

## Decision

No. `mcp_gateway` and `mcp_client` are not added to the `Tool` enum, now or later; MCP is transport, and it is owned by the capability broker (EL-302) and the gateway (EL-408).

## Status

Rejected — the proposed enum members are not added — 2026-10-04.

This overturns the recommendation on the `DEVELOPMENT_PLAN.md:87` table ("Yes, while the enum is still cheap to change"). The counter-argument in the ticket is correct, and the stated rationale for the recommendation rests on a cost claim that does not survive checking. See `## Consequences`.

## Context

`DEVELOPMENT_PLAN.md:87` proposes adding `mcp_gateway` and `mcp_client` to `Tool`, blocking EL-104 (S4, the enum itself). The argument offered is temporal: an enum is cheap to change now and expensive once 70 records cite it.

Two things make this decidable rather than a matter of taste.

First, the `Tool` enum has a single, unbroken meaning today. Every one of the 15 members in `CLAUDE.md:153` answers *what must exist in the world for this technique to be runnable at all*. `required_tools` is a precondition on reality (`CLAUDE.md:166`), and when one is missing the agent raises a permission request rather than skipping (`AGENT.md §3.6`, capability check). None of the 15 answers *how the thing is reached*. Adding MCP would make these the first transport members, and the enum would no longer mean one thing.

Second, the methodology is silent. The corpus is the authority for what a technique requires, and it does not mention MCP at all.

Note also that `evalloop/vocab/tools.py` does not yet exist — EL-104 creates it. "Adding the members now" is not a small edit to existing code; it is pre-committing EL-104's content.

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **Do not add; MCP stays in the broker and gateway (chosen)** | EL-301/EL-302/EL-408 must name the words themselves, four months out | The enum keeps one meaning: every member is a precondition on reality. No transport leaks into the methodology layer | — |
| Add both now | Two members cited by zero records for ~4 months; the enum means two things | Reserves the words; EL-104 unblocks with them in place | The words are not needed to reserve: nothing competes for them. Dead vocabulary in an enum that record authors read as a menu invites miscitation (see Consequences) |
| Add only `mcp_client` (the connector half) | Same category break, half the surface | Narrower | `mcp_client` is the clearer transport of the two — it is the wire to a DB or vector store the enum already names |
| Add a separate `Transport` enum in M0 | A second vocabulary with no consumer until E3 | Keeps `Tool` clean while reserving the words | Builds M0 vocabulary for an M5 concern. The broker needs grant types, not a methodology vocabulary; EL-302 is the right place and the right time |

## Consequences

**What it actually costs to add a `Tool` member after 70 records exist.** The recommendation rests on this being high. It is not. Concretely, adding a member is:

1. one line in `evalloop/vocab/tools.py`;
2. one docstring justification note, per the standing rule at `CLAUDE.md:155`;
3. nothing else.

No existing record changes. `required_tools` is a per-record tuple (`CLAUDE.md:166`), so a record that does not need the new tool simply does not name it. Enum widening is **monotone**: `parse_tool` accepts a strict superset of what it accepted before, so no previously-valid record can become invalid. The round-trip test in S5 enumerates the enum, so it covers a new member without being edited.

One correction to the ticket's premise: `check_integrity()` does **not** validate `required_tools`. Its rule list (`TASKS.md:88-95`) covers duplicate ids, dangling cross-references, self-references, ladder-priority consistency and section/id agreement — no tool rule. Tool strings are validated at parse time by the loader (`TASKS.md:81`, "validates situation/tool strings through the vocab parsers"). This makes the addition cost *lower* than the ticket assumed, not higher: there is no cross-record invariant over tools to re-establish.

So the cost of adding is **O(1) in the number of records** — the same whether 0 or 70 records exist. The timing argument is therefore empty.

What is genuinely O(number of citing records) is **renaming or removing** a member, because that narrows the accepted set and breaks every record that cites it. This inverts the recommendation: adding two speculative members today is what *creates* the expensive-to-reverse condition. If E3 lands and MCP turns out to belong in the broker after all — which this decision concludes it does — removing the members is the expensive operation, and we would have paid it for nothing.

Timing is also favourable: `required_tools` is left empty by skeleton extraction and filled during enrichment (`TASKS.md:123`). Any tool genuinely discovered in a deep dive gets added at the moment the record that needs it is being written.

**Made easy.** The enum keeps one testable invariant: every member is a precondition on reality, so "is this a `Tool`?" has a mechanical answer for future additions. `required_tools` stays answerable from the corpus alone.

**Made hard.** EL-301, EL-302 and EL-408 cannot express an MCP requirement in `required_tools`. They should not need to: a record requires `db_connection`, and the broker decides whether that is satisfied by a local socket or an MCP server.

**Risk accepted.** If E3 discovers a technique that is genuinely MCP-specific, we add the member then, at the cost established above: one line and a docstring note.

**Foreclosed.** Nothing. This decision is reversible for the price of the addition it declines.

## Evidence

### Capability versus transport, all 15 current members

Source: `CLAUDE.md:153`. The discriminating test applied to each: *if the delivery mechanism changed but the resource stayed the same, would the technique's requirement change?* If no, the member names a capability.

| # | Member | Answers | Category |
|---|---|---|---|
| 1 | `sandbox` | an isolated place to execute output | capability |
| 2 | `test_runner` | the ability to run a suite and read pass/fail | capability |
| 3 | `repo_read` | access to the source under evaluation | capability |
| 4 | `source_doc_read` | access to the reference spec or doc | capability |
| 5 | `llm_api` | access to a model | capability |
| 6 | `llm_api_cross_family` | access to a model of a *different family* — a provenance property F requires of judges | capability |
| 7 | `vector_store` | a retrieval index that can be queried | capability |
| 8 | `db_connection` | a database that can be read | capability |
| 9 | `ocr` | text recoverable from images | capability |
| 10 | `vision_model` | an image can be interpreted | capability |
| 11 | `trace_capture` | agent steps are observable | capability |
| 12 | `snapshot_restore` | the environment can be reset to a fixed state | capability |
| 13 | `cost_api` | per-run cost is obtainable | capability |
| 14 | `human_labels` | gold labels from people exist | capability |
| 15 | `production_logs` | real traffic is available | capability |

**Capabilities: 15. Transports: 0.** The invariant is unbroken.

Two members are worth testing explicitly, because their names sound like transport. `llm_api` names an API and `db_connection` names a connection — but apply the test: reach the same database over a Postgres socket, an HTTP proxy, or an MCP server, and every record requiring `db_connection` is unchanged. The member denotes the resource, not the wire. `mcp_client` fails that same test in the opposite direction: it denotes *only* the wire, and the resource behind it is already named by members 7 and 8.

`mcp_gateway` is subsumed by member 11. What the gateway produces is a trajectory — `EL-409` reconstructs "a full agent trajectory from the bus" (`DEVELOPMENT_PLAN.md:175`) — and `trace_capture` is exactly the capability "agent steps are observable". The gateway is one implementation of it.

### Corpus hits requiring an MCP transport

Searched all 12 files in `knowledge rules/` for `MCP`, `model context protocol`, `JSON-RPC`, `wire protocol`, `transport`, `gateway`.

| Pattern | Hits |
|---|---|
| `MCP` / `model context protocol` | **0** |
| `JSON-RPC` / `wire protocol` / `gateway` | **0** |
| `transport` | 1 — a false positive: "40% of volume from small transporters" (`J-choosing-a-model.md:197`), meaning trucking firms in an invoice-OCR example |

**Corpus hits that would require an MCP transport: 0.**

### The decisive test, answered with a named technique

*Is there any record in A–J that can run with `mcp_client` and cannot run without it?*

**No.** The strongest candidate is **H1 — "Sandboxed, resettable environment + full trajectory logging"** (`H-agents.md:27`), the technique most likely to need the gateway, since EL-408/EL-409 exist to reconstruct trajectories. Its stated preconditions are a containerised mock "reset to a fixed snapshot before every run, with every tool call, argument, response and timing logged" (`H-agents.md:29-30`), and its procedure requires "Snapshot the environment … restore it before every task" and "Log everything: tool name, arguments, response, latency and token counts, per step" (`H-agents.md:36-39`).

That is `snapshot_restore` + `trace_capture`, and nothing else. H1 is satisfied identically whether the log arrives through an MCP gateway, an SDK callback, a proxy, or a file on disk. The corpus specifies *that* every tool call is logged, never *how* the log is obtained. H6 (prompt-injection suite) and H7 (trajectory review) inherit the same preconditions and give the same answer.

No record passes the test, so the answer is no.

### Which layer owns MCP instead

The plan already places it outside the vocabulary, in three places:

- `AGENT.md:172` — the Cross-cutting Capability layer already owns "Tool + MCP connections", alongside credentials, cost tracking and rate limits. MCP is listed as plumbing the capability layer manages, not as a methodology term.
- `DEVELOPMENT_PLAN.md:153` — EL-307 makes "any MCP server … a read-only Connector", i.e. behind the existing Connector concept.
- `DEVELOPMENT_PLAN.md:174` — EL-408 is a "proxy between the agent and its MCP tool servers", feeding EL-409's recorder, i.e. behind the existing trace/bus concept.

EL-302, the capability broker, is where a grant is checked and an ungranted tool becomes `UNAVAILABLE` "naming the missing tool" (`DEVELOPMENT_PLAN.md:148`). That is the layer that must distinguish an MCP-backed grant from a local one; the methodology layer must not.

## Follow-up

**Where the words live instead:** `mcp_gateway` and `mcp_client` become capability-broker grant kinds and connector kinds, introduced by **EL-301** (MCP protocol core) with **EL-307** (client connector) and **EL-408** (gateway) — never as `Tool` members.

**Unblocks:** EL-104 (S4) proceeds with exactly the 15 members listed in `CLAUDE.md:153`.

**Code changed by this ticket:** none, as required. `evalloop/vocab/tools.py` is still EL-104's to create.

**Docs changed:** `DEVELOPMENT_PLAN.md:87` (EL-002 row marked decided, answer inverted); `CLAUDE.md` §6 (the standing rule now states the capability-not-transport test); `AGENT.md` §4 (the capability layer explicitly owns transports, and the `Tool` enum does not).

**Standing test for future additions:** a candidate `Tool` member must answer "what must exist for this technique to run". If changing the delivery mechanism while keeping the resource would not change any record, the candidate is transport and belongs to the broker.
