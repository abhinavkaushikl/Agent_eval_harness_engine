# E3 / Track V Ã¢ÂÂ Connectors + MCP client Ã¢ÂÂ tickets and developer prompts

*Written for: the engineer(s) building Track V. Read ÃÂ§0 and ÃÂ§2 before any ticket Ã¢ÂÂ every ticket
below leans on the safety spine described there, and two of them contradict a committed decision in
ways you must resolve before you write code.*

**Window:** 9 Nov Ã¢ÂÂ 4 Dec ÃÂ· ~18.5 days. **Theme:** the generated code is run against the *real*
world Ã¢ÂÂ a real database, a real vector store Ã¢ÂÂ which `ARCHITECTURE.md` ÃÂ§1 calls "the single most
dangerous capability in the product." Track V is the discovery Ã¢ÂÂ consent Ã¢ÂÂ read-only envelope Ã¢ÂÂ
validation subsystem that makes that safe.

---

## 0. Inherited context Ã¢ÂÂ trust this over the doc text, and say in each report which way you went

The seven M0/M1 warnings still hold (Gate 0 open; F2; F8; blocked fixtures 11/14/20; `PLAN.md` ÃÂ§5
not a spec; six dead situations; EL-014 timeout semantics settled). Track V adds four of its own:

1. **Track V cannot start until Gate 1 is signed off (EL-212) and Gate 0 is closed.** Every ticket
   here `Depends on EL-212`. Gate 1's packet is written but **awaiting human sign-off**, and it
   passed under "Reading A" (re-ran an existing test). Do not build on top of an unsigned gate.
2. **Connectors shell out; they never import a database driver.** `ARCHITECTURE.md` ÃÂ§6.3 and the
   `CLAUDE.md` rule it recommends: Postgres/MySQL go through `psql`/`mysql` on `PATH` (decision
   `EL-006`), SQLite and HTTP vector stores (Qdrant/Weaviate/Chroma) need no driver at all. A
   `psycopg`/`qdrant-client` import in `evalloop/connect/` is a review failure. The one escape hatch
   (EL-006's "ask to install a native driver into an EvalLoop-owned runtime") is the broker's, not a
   connector's.
3. **F8 bites hardest here.** `unlocks` is read by **no planner step**, so "faithfulness is blocked
   until recall@k is measured" is **not** enforced by the registry's `unlocks` edges. The RAG build
   order must be enforced some other way Ã¢ÂÂ `G3_faithfulness` already carries
   `requires: {recall_at_k_measured: true, Ã¢ÂÂ¦}`, which *is* a readiness bar (EL-213 produces that
   key), so the RAG runner must set `recall_at_k_measured` only after recall@k actually runs, and
   let readiness do the gating. If you rely on `unlocks`, faithfulness will run first and the gate
   is a lie. Say in your report which mechanism you used.
4. **The MCP *server* is not Track V.** Decision `EL-008`: `evaluate`/`verify_claim`/`findings` stay
   gated behind Gate 3 (E7), because an agent that can call the grader in a loop will Goodhart it.
   EL-307 here is an MCP **client** connector (EvalLoop *consumes* someone else's read-only MCP
   server). Do not build the server in this track.

**Two conflicts with committed decisions Ã¢ÂÂ resolve before coding, don't silently pick one:**

- **EL-301 vs EL-007 on transport.** The board summary says "JSON-RPC over stdio **+ HTTP**."
  Decision `EL-007` says transport **before Gate V is stdio only**; Streamable HTTP is "deferred to a
  named ticket." Follow the decision: build **stdio**, and split HTTP into its own later ticket,
  unless the ruling is reversed. Flag it.
- **EL-302 vs the M1 driver.** EL-214 already surfaces `Plan.unavailable` as a permission request
  with no real broker behind it. EL-302 is the real broker; make the M1 driver route through it
  rather than keeping a second, poorer copy of the logic.

Where two of our own docs disagree on a number, **the corpus file decides** Ã¢ÂÂ open it, copy
verbatim, and report which doc was wrong.

---

## 1. Board

| Key | Summary | Type | Est | Depends on | Done when |
|---|---|---|---|---|---|
| EL-301 | MCP protocol core (JSON-RPC 2.0, stdlib) | Story | 2 | EL-007, EL-212 | Ã¢ÂÂ Done ahead of Ã°ÂÂÂG1 Ã¢ÂÂ `EL-301-REPORT.md` (built to 2026-07-28; "handshake" reworded Ã¢ÂÂ see report) |
| EL-302 | V1 Capability broker (grants, consent, expiry, budget) | Story | 1.5 | EL-212 | â Done ahead of ðG1 â `EL-302-REPORT.md` |
| EL-303 | V2 Connector discovery with provenance | Story | 1.5 | EL-302 | ✅ Done ahead of 🔒G1 — `EL-303-REPORT.md` |
| EL-304 | V3 Production-suspected classification | Story | 1 | EL-303 | ✅ Done ahead of 🔒G1 — `EL-304-REPORT.md` (prod host → default deny + type-to-confirm) |
| EL-305 | V4 Read-only envelope + audit log | Story | 1.5 | EL-304 | ✅ Done ahead of 🔒G1 — `EL-305-REPORT.md` (`DROP TABLE` rejected before it is sent) |
| EL-306 | V5 Connector protocol + SQLite | Story | 1 | EL-305 | ✅ Done ahead of 🔒G1 — `EL-306-REPORT.md` (probe / describe / read work, all read-only) |
| EL-307 | MCP client connector | Story | 1.5 | EL-301, EL-306 | ✅ Done ahead of 🔒G1 — `EL-307-REPORT.md` (external MCP server queried through the envelope) |
| EL-308 | Postgres/MySQL over CLI (no driver) | Story | 1.5 | EL-306 | ✅ Done ahead of 🔒G1 — `EL-308-REPORT.md` (psql/mysql shelled out; missing CLI = clean UNAVAILABLE) |
| EL-309 | Vector store (Qdrant over HTTP) | Story | 1.5 | EL-306 | ✅ Done ahead of 🔒G1 — `EL-309-REPORT.md` (urllib only; collections + embedding model enumerated) |
| EL-310 | File + prompt-registry connectors | Story | 1 | EL-307 | Prompts and files usable as eval inputs |
| EL-311 | SQL execution grading (result sets) | Story | 2 | EL-306 | ✅ Done ahead of 🔒G1 — `EL-311-REPORT.md` (runs SQL vs a snapshot; never compares text) |
| EL-312 | RAG recall@k + faithfulness gate | Story | 1.5 | EL-309 | ✅ Done ahead of 🔒G1 — `EL-312-REPORT.md` (recall@k w/ CI; faithfulness gated via requires, not unlocks) |
| EL-313 | RAG ladder stages (separate) | Story | 2 | EL-312 | ✅ Done ahead of 🔒G1 — `EL-313-REPORT.md` (ceiling/attribution/faithfulness/robustness/unanswerable/citation, no blended score) |
| EL-314 | End-state verification | Story | 1 | EL-306 | ✅ Done ahead of 🔒G1 — `EL-314-REPORT.md` (verdict from real state; a false "done" is caught) |
| EL-315 | Ã°ÂÂÂ Gate V | Gate | 0.5 | EL-311, EL-313, EL-314 | DB + vector store discovered and validated unprompted |

**Critical path:** `EL-302 Ã¢ÂÂ EL-303 Ã¢ÂÂ EL-304 Ã¢ÂÂ EL-305 Ã¢ÂÂ EL-306 Ã¢ÂÂ {EL-308 Ã¢ÂÂ EL-311, EL-309 Ã¢ÂÂ EL-312 Ã¢ÂÂ EL-313, EL-314} Ã¢ÂÂ EL-315`. EL-301/EL-307 (MCP) run in parallel off EL-306.

---

## 2. The safety spine (every ticket depends on this)

`ARCHITECTURE.md` ÃÂ§6: **DISCOVER Ã¢ÂÂ PROPOSE Ã¢ÂÂ CONSENT Ã¢ÂÂ PROBE (read-only envelope)**, and ÃÂ§9's
guards. In one paragraph so you don't re-derive it fifteen times:

- **Discover** scans for *evidence* of endpoints and **makes no connection and reads no credential**.
- **Propose** states, per endpoint: host, database/collection, credential **source** (never value),
  operations requested, and row/time caps.
- **Consent** is explicit, per-endpoint, revocable, session-default; `production-suspected` requires
  typing the endpoint name and defaults to **deny**.
- **Probe** happens only inside the **read-only envelope**: DDL/DML (`DROP`/`DELETE`/`UPDATE`/Ã¢ÂÂ¦)
  rejected by AST *before transmission*, a read-only transaction, and row/byte caps Ã¢ÂÂ three
  independent layers. Any technique that genuinely needs to write gets a **scratch schema or a
  restored snapshot, never the live schema**.
- **One component owns credentials** Ã¢ÂÂ the capability broker. A grader never reads an env var
  (`ARCHITECTURE.md` ÃÂ§9: "Credentials in a grader: impossible by construction"). Everything crosses
  the **redactor** at the boundary; nothing unredacted is persisted, and the PHI gate (fixture 20's
  open ruling) lives here.

Files: everything new lives under **`evalloop/connect/`** (component 16) and **`evalloop/mcp/`**
(the protocol seam, EL-007). The core stays stdlib-only; connectors shell out.

---

## 3. Tickets

### EL-301 Ã¢ÂÂ MCP protocol core (JSON-RPC 2.0, stdlib)
**Type:** Story ÃÂ· **Est:** 2 ÃÂ· **Depends:** EL-007, EL-212 ÃÂ· **Blocks:** EL-307 ÃÂ·
**Done when:** handshake, tool listing and tool calls work against a reference MCP server.

**Files** Ã¢ÂÂ `evalloop/mcp/{__init__,wire,client,facade}.py` ÃÂ· `tests/test_mcp_core.py`,
`tests/fixtures/mcp/reference_server.py`

**Subtasks**
- [ ] JSON-RPC 2.0 over **stdio** (framing, ids, request/response/notification, error objects) Ã¢ÂÂ stdlib only
- [ ] Protocol revision pinned to **`2026-07-28`** (EL-007); the handshake negotiates it
- [ ] `initialize` Ã¢ÂÂ `tools/list` Ã¢ÂÂ `tools/call`, with `_meta` and wire error codes handled
- [ ] A **typed faÃÂ§ade**: frozen dataclasses + two `Protocol`s that contain **no wire concept** Ã¢ÂÂ the only module that knows JSON-RPC is `evalloop/mcp/`
- [ ] A stdlib **reference MCP server** fixture to test against (no network, no SDK)

**Acceptance criteria**
- [ ] Handshake, `tools/list`, and a `tools/call` round-trip succeed against the reference server
- [ ] A malformed frame and a wire error code surface as typed errors, not a crash
- [ ] `grep` proves JSON-RPC/`_meta`/`resultType` appear in `evalloop/mcp/` and **nowhere else**
- [ ] No third-party import anywhere (`CLAUDE.md` ÃÂ§1)

**Out of scope** The MCP **server** (`evaluate`/`verify_claim`, gated behind Gate 3 Ã¢ÂÂ EL-008).
Streamable HTTP transport (deferred by EL-007 Ã¢ÂÂ see ÃÂ§0).

**Gotchas** The board says "stdio + HTTP"; EL-007 says **stdio only before Gate V**. Build stdio,
split HTTP into its own ticket, and get the conflict ruled on before you start.

````text
WHAT I WANT
evalloop/mcp/: the JSON-RPC 2.0 core for talking to MCP servers, standard library only, with a
typed faÃÂ§ade so the rest of the project never sees a wire concept.

WHAT IS IN THE TICKET
Decision EL-007: MCP is stdlib, no SDK. ONE package, evalloop/mcp/, is the only place that knows
JSON-RPC, _meta, wire error codes or resultType. Pinned revision 2026-07-28. Transport before
Gate V is stdio ONLY -- Streamable HTTP is deferred to a named ticket.

THE RESULT I WANT TO SEE
1. A stdio JSON-RPC client: framing, request/response/notification, ids, error objects -- urllib/
   subprocess/json only, no SDK, no third-party import.
2. initialize -> tools/list -> tools/call working against a REFERENCE MCP SERVER you write as a
   stdlib fixture. The test needs no network and no external server.
3. A typed faÃÂ§ade: frozen dataclasses and two Protocols that carry NO wire concept. A grep proves
   "JSON-RPC", "_meta", "resultType" appear only under evalloop/mcp/. If the spec revs, one module
   changes, not three tracks -- that is the whole point of the seam.
4. A malformed frame and a server error code become a TYPED error, never a crash or a bare dict.
5. The revision is negotiated in the handshake and pinned to 2026-07-28; a server offering only a
   different revision fails cleanly, naming both.

THE CONFLICT YOU MUST RESOLVE FIRST
The board summary says "stdio + HTTP". EL-007 says stdio only before Gate V. Follow the decision --
build stdio, put HTTP in its own later ticket -- and report the discrepancy rather than quietly
building HTTP.

OUT OF SCOPE: the EvalLoop MCP SERVER (evaluate/verify_claim/findings -- Gate 3, EL-008), Streamable
HTTP, and wrapping an MCP server as a Connector (that is EL-307).
````

---

### EL-302 Ã¢ÂÂ V1 Capability broker (grants, consent, expiry, budget)
**Type:** Story ÃÂ· **Est:** 1.5 ÃÂ· **Depends:** EL-212 ÃÂ· **Blocks:** EL-303 ÃÂ·
**Done when:** an ungranted tool resolves to UNAVAILABLE, naming the missing tool.

**Files** Ã¢ÂÂ `evalloop/capability/broker.py` (extends the EL-209 capability layer) ÃÂ·
`tests/test_capability_broker.py`

**Subtasks**
- [ ] A grant: a tool/endpoint, who granted it, why, an **expiry**, and caps (rows/time/budget)
- [ ] `check(tool) -> granted | UNAVAILABLE(reason)`; the planner's `Tool` enum is the vocabulary
- [ ] **Only this component reads a credential** Ã¢ÂÂ the source scan from EL-209 is extended to cover `evalloop/connect/`
- [ ] Consent is explicit, per-endpoint, **revocable**, session-default; nothing is granted by default
- [ ] A session **budget** with a hard stop (reuse EL-209's `CostLedger` shape)
- [ ] Expiry: a lapsed grant reverts to UNAVAILABLE without a restart

**Acceptance criteria**
- [ ] An ungranted tool Ã¢ÂÂ `UNAVAILABLE`, naming the tool and how to grant it; a test proves it
- [ ] A granted-then-expired tool reverts to UNAVAILABLE
- [ ] A source scan proves no module outside the capability layer reads a credential (incl. `connect/`)
- [ ] The M1 run driver (EL-214) routes `Plan.unavailable` through this broker, not a private copy

**Out of scope** Discovery (EL-303), the read-only envelope (EL-305). The PHI gate's *policy* is
fixture 20's open ruling; wire the hook, don't invent the policy.

**Gotchas** This is the component `ARCHITECTURE.md` ÃÂ§9 hangs "credentials in a grader: impossible by
construction" on. If a connector can reach an env var, the whole safety claim is void.

````text
WHAT I WANT
evalloop/capability/broker.py: the ONE component that holds credentials and hands out grants --
with consent, expiry and a budget -- so that no grader, connector or sensor ever reads a secret.

WHY THIS IS THE LOAD-BEARING SAFETY COMPONENT
ARCHITECTURE.md section 9: "Credentials in a grader: impossible by construction -- only the
capability broker holds them." Everything in Track V reaches the real world THROUGH this. If a
connector can read os.environ, the claim is a lie. EL-209 already established "only the capability
layer reads the environment" and has a source scan to enforce it; extend that scan to connect/.

THE RESULT I WANT TO SEE
1. A grant record: the tool/endpoint, who granted it, the reason, an EXPIRY, and caps (rows, time,
   budget). Frozen, auditable.
2. check(tool) -> granted or UNAVAILABLE(reason). UNAVAILABLE names the missing tool and how to
   supply it -- the exact string the planner's UNAVAILABLE state and EL-214's permission request
   already expect. Test that an ungranted tool is UNAVAILABLE, not a crash and not a silent allow.
3. Consent is explicit, per-endpoint, revocable, with a session-only default. NOTHING is granted by
   default.
4. An expired grant reverts to UNAVAILABLE on the next check, no restart.
5. A session budget with a hard stop, reusing EL-209's ledger shape.
6. The M1 driver (EL-214) is switched to ask THIS broker, deleting its stand-in logic -- one broker,
   not two.
7. The source scan proves no module under evalloop/ outside the capability layer reads a credential.

OUT OF SCOPE: discovering endpoints (EL-303), the read-only SQL envelope (EL-305), and deciding the
PHI gate's policy (fixture 20, open). Wire the PHI hook; do not rule on it.
````

---

### EL-303 Ã¢ÂÂ V2 Connector discovery with provenance
**Type:** Story ÃÂ· **Est:** 1.5 ÃÂ· **Depends:** EL-302 ÃÂ· **Blocks:** EL-304 ÃÂ·
**Done when:** candidates are listed with file-and-line provenance and **zero connections** are attempted.

**Files** Ã¢ÂÂ `evalloop/connect/discover.py` ÃÂ· `tests/test_connector_discovery.py`,
`tests/fixtures/connect/sample_repo/`

**Subtasks**
- [ ] Scan for *evidence* only: `.env`/`.env.example` keys, `docker-compose.yml` services, `settings.py`/config modules, client call sites (`psycopg.connect`, `create_engine`, `QdrantClient`, `chromadb.HttpClient`), `alembic.ini`, listening local ports
- [ ] Each candidate carries **provenance**: "because `docker-compose.yml:14` defines `qdrant:6333`"
- [ ] **No connection, no credential read** Ã¢ÂÂ text/`ast` scan only
- [ ] Deterministic ordering

**Acceptance criteria**
- [ ] Run on `tests/fixtures/connect/sample_repo/`: every candidate cites the file and line it came from
- [ ] A network guard (sockets patched to raise) is live during the whole test and nothing trips it
- [ ] A credential *value* never appears in a candidate Ã¢ÂÂ only its source

**Out of scope** Connecting, classifying prod (EL-304), probing (EL-306).

**Gotchas** This is "auto-login to the vector DB," the capability ÃÂ§1 names most dangerous, done
safely: the trick is that discovery is **inert** Ã¢ÂÂ it finds *evidence*, never opens anything.

````text
WHAT I WANT
evalloop/connect/discover.py: find the databases and vector stores a repo talks to, each with
provenance, WITHOUT opening a single connection or reading a single credential.

WHAT IS IN THE TICKET
ARCHITECTURE.md section 6.1, the DISCOVER step: scan for evidence of endpoints -- .env /
.env.example keys, docker-compose services, config modules, client constructor call sites
(psycopg.connect, create_engine, QdrantClient, chromadb.HttpClient), alembic.ini, listening ports --
and output candidates WITH PROVENANCE, e.g. "because docker-compose.yml:14 defines qdrant:6333".

THE RESULT I WANT TO SEE
1. A list of candidate endpoints from a sample repo, each citing the file and line it came from.
2. ZERO connections attempted and ZERO credentials read -- proven by a socket guard that raises on
   any connect, live for the whole test, that nothing trips.
3. A credential VALUE never appears in a candidate; only its source ("from .env key DATABASE_URL").
4. ast/text scanning only -- never import or run the repo's code to discover an endpoint (a repo's
   conftest or settings import must not execute).
5. Deterministic ordering: same repo, same candidate list.

OUT OF SCOPE: connecting (EL-306), production classification (EL-304), the read-only envelope
(EL-305). Discovery is inert by design -- it reports evidence, it does not touch anything.
````

---

### EL-304 Ã¢ÂÂ V3 Production-suspected classification
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-303 ÃÂ· **Blocks:** EL-305 ÃÂ·
**Done when:** a prod host defaults to deny and requires typing the endpoint name to confirm.

**Files** Ã¢ÂÂ `evalloop/connect/classify_endpoint.py` ÃÂ· `tests/test_endpoint_classification.py`

**Subtasks**
- [ ] Classify each candidate `local` / `staging` / `unknown` / **`production-suspected`**
- [ ] Heuristics (`ARCHITECTURE.md` ÃÂ§6.1): host/db name matching `prod|live|www`, a non-RFC1918 host, a credential from a secrets manager rather than `.env`
- [ ] `production-suspected` Ã¢ÂÂ default **deny** + **type-to-confirm** (type the endpoint name)
- [ ] The classification travels with the consent request (EL-302)

**Acceptance criteria**
- [ ] A `prod`-named / non-RFC1918 / secrets-manager endpoint classifies `production-suspected`, defaults to deny, and needs the typed name
- [ ] A localhost RFC1918 endpoint classifies `local` and does not demand type-to-confirm
- [ ] Each classification states the heuristic that fired, in plain language

**Out of scope** The read-only envelope (EL-305), any probe.

**Gotchas** Err toward `production-suspected`. A wrong `local` that was really prod is the failure
the type-to-confirm exists to prevent; a wrong `production-suspected` costs one extra keystroke.

````text
WHAT I WANT
evalloop/connect/classify_endpoint.py: decide whether a discovered endpoint is local, staging,
unknown, or production-suspected -- and make production-suspected default to DENY with type-to-
confirm.

WHAT IS IN THE TICKET
ARCHITECTURE.md section 6.1 / section 9: "Connector points at production -> production-suspected
classification, type-to-confirm, default deny." Heuristics: hostname or db name matching
prod|live|www, a non-RFC1918 host, or a credential from a secrets manager rather than .env.

THE RESULT I WANT TO SEE
1. Each candidate classified local / staging / unknown / production-suspected, with the heuristic
   that fired named in plain language.
2. A prod-named host, a non-RFC1918 host, and a secrets-manager credential each -> production-
   suspected -> default DENY, and granting requires typing the endpoint name.
3. A localhost RFC1918 endpoint -> local, no type-to-confirm.
4. The classification rides on the consent request, so the user sees WHY before they grant.
5. The fail-safe direction is toward production-suspected: a false local that was really prod is the
   catastrophe; a false production-suspected is one keystroke.

OUT OF SCOPE: connecting or probing (EL-305/EL-306). This ticket decides posture, it does not open
anything.
````

---

### EL-305 Ã¢ÂÂ V4 Read-only envelope + audit log
**Type:** Story ÃÂ· **Est:** 1.5 ÃÂ· **Depends:** EL-304 ÃÂ· **Blocks:** EL-306 ÃÂ·
**Done when:** `DROP TABLE` is rejected before it is sent.

**Files** Ã¢ÂÂ `evalloop/connect/envelope.py`, `evalloop/connect/audit.py` ÃÂ·
`tests/test_readonly_envelope.py`

**Subtasks**
- [ ] **Three independent layers** (`ARCHITECTURE.md` ÃÂ§9): reject DDL/DML by AST **before transmission**, open a **read-only transaction**, and enforce **row/byte caps** (grant parameters, EL-006)
- [ ] Any write-needing technique gets a **scratch schema or restored snapshot**, never the live schema
- [ ] An **audit log**: every statement sent, its endpoint, caps in force, and the result shape Ã¢ÂÂ append-only, redacted
- [ ] The statement-safety check is dialect-aware enough to catch `DROP`/`DELETE`/`UPDATE`/`INSERT`/`ALTER`/`TRUNCATE`/`GRANT`

**Acceptance criteria**
- [ ] `DROP TABLE Ã¢ÂÂ¦`, a `DELETE`, and an `UPDATE` are each rejected **before** any bytes leave, with a named reason Ã¢ÂÂ tested
- [ ] A read-only transaction is proven (a write that slips the AST check still fails at the DB)
- [ ] A query over the row cap is truncated/err'd per the cap, and the cap is recorded
- [ ] Every sent statement appears in the audit log, redacted

**Out of scope** The connector protocol (EL-306), SQL *correctness* grading (EL-311).

**Gotchas** AST-before-send is layer one of three, not the only one Ã¢ÂÂ a parser miss must still hit
a read-only transaction and a cap. "Three independent layers" is the contract.

````text
WHAT I WANT
evalloop/connect/envelope.py: the read-only envelope that makes it safe to run UNTRUSTED, AI-written
SQL against a real database -- plus an audit log of everything sent.

WHY THIS IS NON-NEGOTIABLE
The code being run was written by a model and not read by the developer. ARCHITECTURE.md section 9:
"Generated SQL contains DROP -> AST reject before transmission, plus read-only transaction, plus
caps. Three INDEPENDENT layers." And: writes "only in a scratch schema or restored snapshot, never
the live schema." A live connection does not remove the need for this; it is the reason for it.

THE RESULT I WANT TO SEE
1. Layer 1: AST rejection of DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/GRANT and any DDL/DML BEFORE a
   byte is sent, naming the statement. Test that DROP TABLE never reaches the wire.
2. Layer 2: a read-only transaction, so a statement that slips layer 1 still fails at the database.
3. Layer 3: row/byte caps, from the grant (EL-006), recorded with the result.
4. Any technique that must write gets a scratch schema or a restored snapshot -- never the live
   schema.
5. An append-only, redacted audit log: every statement, its endpoint, the caps in force, the result
   shape. Nothing unredacted is persisted.
6. The three layers are independent: a test disables layer 1 and shows layer 2 still blocks the write.

OUT OF SCOPE: the connector protocol (EL-306) and SQL result grading (EL-311). This is the safety
envelope only.
````

---

### EL-306 Ã¢ÂÂ V5 Connector protocol + SQLite
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-305 ÃÂ· **Blocks:** EL-307, EL-308, EL-309, EL-314 ÃÂ·
**Done when:** `probe` / `describe` / `read` work.

**Files** Ã¢ÂÂ `evalloop/connect/protocol.py`, `evalloop/connect/sqlite.py` ÃÂ·
`tests/test_connector_sqlite.py`

**Subtasks**
- [ ] A `Connector` `Protocol`: `probe()` (reachable, read-only), `describe()` (schema/collections), `read(query)` (through the envelope)
- [ ] First implementation: **SQLite** (stdlib Ã¢ÂÂ the no-driver case), under the EL-305 envelope
- [ ] `describe()` returns tables/columns (or collections) with no data read
- [ ] Everything routed through the broker (EL-302) and the envelope (EL-305)

**Acceptance criteria**
- [ ] `probe`/`describe`/`read` succeed against a fixture SQLite DB, all read-only
- [ ] A write attempted through `read()` is rejected by the envelope, not the DB alone
- [ ] `describe()` reads structure, never rows

**Out of scope** Postgres/MySQL (EL-308), vector stores (EL-309), MCP (EL-307).

**Gotchas** SQLite is the reference because it needs no driver and no network Ã¢ÂÂ it proves the
protocol and the envelope without the connection questions. Keep the protocol driver-agnostic so
EL-308/309/307 are thin.

````text
WHAT I WANT
evalloop/connect/protocol.py + sqlite.py: the Connector contract (probe / describe / read) and its
first, driverless implementation on SQLite, all inside the read-only envelope.

WHAT IS IN THE TICKET
ARCHITECTURE.md section 6: a connector exposes probe (reachable, read-only), describe (schema /
collections), read (a read-only query through the envelope). SQLite is stdlib, so it needs no driver
and no network -- the clean place to pin the protocol.

THE RESULT I WANT TO SEE
1. A Connector Protocol with probe / describe / read, driver-agnostic, so EL-307/308/309 are thin.
2. SQLite implementing it, every call routed through the broker (EL-302) and the envelope (EL-305).
3. describe() returns tables and columns (structure) and reads NO rows.
4. A write sent through read() is rejected by the ENVELOPE, proven even when SQLite itself would
   allow it -- the safety is the envelope's, not the backend's.
5. probe/describe/read all succeed against a fixture SQLite DB and are all read-only.

OUT OF SCOPE: Postgres/MySQL (EL-308, via CLI), vector stores (EL-309), MCP connectors (EL-307).
Keep SQLite driverless and the protocol backend-agnostic.
````

---

### EL-307 Ã¢ÂÂ MCP client connector
**Type:** Story ÃÂ· **Est:** 1.5 ÃÂ· **Depends:** EL-301, EL-306 ÃÂ· **Blocks:** EL-310 ÃÂ·
**Done when:** an external MCP DB server is queried through the envelope.

**Files** Ã¢ÂÂ `evalloop/connect/mcp_connector.py` ÃÂ· `tests/test_mcp_connector.py`

**Subtasks**
- [ ] Wrap an external MCP server (via EL-301's client + faÃÂ§ade) as a `Connector` (probe/describe/read)
- [ ] Every call goes through the EL-305 envelope and EL-302 broker Ã¢ÂÂ an MCP tool that writes is rejected like any other write
- [ ] Only the EL-307 faÃÂ§ade is touched; no wire concept leaks out (EL-007)

**Acceptance criteria**
- [ ] A read-only query against the reference MCP server returns rows through `read()`
- [ ] A write-shaped MCP tool call is rejected by the envelope before it is sent
- [ ] `grep` still shows no JSON-RPC concept outside `evalloop/mcp/`

**Out of scope** The EvalLoop MCP **server** (EL-008 / Gate 3). HTTP transport (EL-007).

**Gotchas** EL-008: this is a **client**. EvalLoop *consuming* a read-only MCP server is safe now;
*exposing* `evaluate`/`verify_claim` to an agent is not, and is not this ticket.

````text
WHAT I WANT
evalloop/connect/mcp_connector.py: turn ANY external MCP server into a read-only Connector, so an
MCP-exposed database or tool becomes an eval input through the same probe/describe/read contract.

WHAT IS IN THE TICKET
Decision EL-007: a typed faÃÂ§ade is the only thing outside evalloop/mcp/ that is touched; no wire
concept leaks. Decision EL-008: this is the MCP CLIENT (we consume someone else's read-only server),
NOT the EvalLoop MCP server, which stays gated behind Gate 3.

THE RESULT I WANT TO SEE
1. An external MCP server (the EL-301 reference fixture) wrapped as a Connector with probe/describe/
   read, routed through the broker (EL-302) and the envelope (EL-305).
2. A read-only query returns rows through read(); the test uses the stdlib reference server, no net.
3. A write-shaped MCP tool call is rejected by the envelope BEFORE it is sent -- an MCP tool is not
   a hole in the read-only contract.
4. Only the EL-307 faÃÂ§ade is used; a grep still shows JSON-RPC / _meta / resultType only under
   evalloop/mcp/.

OUT OF SCOPE: the EvalLoop MCP SERVER (evaluate/verify_claim -- Gate 3, EL-008) and HTTP transport.
We are the client here, never the server.
````

---

### EL-308 Ã¢ÂÂ V6 Postgres + MySQL via CLI
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-306, EL-006 ÃÂ· **Blocks:** EL-311 ÃÂ·
**Done when:** a missing CLI resolves to UNAVAILABLE, not a crash.

**Files** Ã¢ÂÂ `evalloop/connect/sql_cli.py` ÃÂ· `tests/test_sql_cli_connector.py`

**Subtasks**
- [ ] Postgres/MySQL connectors that **shell out to `psql`/`mysql`** Ã¢ÂÂ never import a driver (EL-006, `CLAUDE.md` rule)
- [ ] The broker resolves the mechanism by EL-006's preference order; a missing CLI Ã¢ÂÂ **UNAVAILABLE** naming it and how to supply it
- [ ] Inherits the developer's existing TLS/Kerberos/SSH config via the CLI
- [ ] Row caps from the grant; everything through the envelope (EL-305)

**Acceptance criteria**
- [ ] With `psql` absent, the connector returns `UNAVAILABLE` naming `psql`, not a traceback
- [ ] A read-only query against a local fixture Postgres returns result sets (skipped cleanly if no local server in CI)
- [ ] No `psycopg`/`mysqlclient`/`PyMySQL` import exists in `evalloop/connect/` Ã¢ÂÂ a source scan proves it

**Out of scope** SQL correctness grading (EL-311), driver auto-install (the broker's, EL-006).

**Gotchas** The "no driver" rule is the one that keeps "stdlib only" from eroding. Shelling out also
inherits the TLS/IAM/SSH the developer already has working Ã¢ÂÂ a feature, not a workaround.

````text
WHAT I WANT
evalloop/connect/sql_cli.py: Postgres and MySQL connectors that shell out to psql/mysql and NEVER
import a driver.

WHAT IS IN THE TICKET
Decision EL-006: connectors shell out; they never import a database driver. The broker resolves the
mechanism (native driver if already importable, else CLI on PATH, else ask to install into an
EvalLoop-owned runtime). A missing mechanism returns UNAVAILABLE naming what is missing and how to
supply it -- never a crash. Row/byte caps are grant parameters.

THE RESULT I WANT TO SEE
1. Postgres and MySQL as Connectors (probe/describe/read) that invoke psql / mysql as subprocesses,
   through the envelope (EL-305) and broker (EL-302).
2. psql absent -> UNAVAILABLE naming psql and how to supply it -- a test asserts a clean UNAVAILABLE,
   not a traceback.
3. A read-only query against a local fixture Postgres returns result sets; the test skips cleanly
   (not fails) when no local server is present, so CI needs no database.
4. A source scan proves NO psycopg / mysqlclient / PyMySQL import under evalloop/connect/.
5. The CLI path inherits the developer's TLS/Kerberos/SSH config for free.

OUT OF SCOPE: SQL result grading (EL-311) and the driver-auto-install path (the broker owns that,
EL-006).
````

---

### EL-309 Ã¢ÂÂ V7 Vector store (Qdrant, HTTP)
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-306 ÃÂ· **Blocks:** EL-312 ÃÂ·
**Done when:** collections are enumerated read-only.

**Files** Ã¢ÂÂ `evalloop/connect/vector_qdrant.py` ÃÂ· `tests/test_vector_connector.py`

**Subtasks**
- [ ] Qdrant over its **HTTP API via `urllib`** Ã¢ÂÂ no SDK (HTTP vector stores need no driver exception)
- [ ] `describe()` enumerates collections and the **embedding model in use**; `read()` is a read-only search
- [ ] Through the broker and envelope; a mutating HTTP verb is rejected

**Acceptance criteria**
- [ ] `describe()` lists collections and the embedding model against a fake HTTP server fixture, read-only
- [ ] A write/delete HTTP call is rejected by the envelope
- [ ] No `qdrant-client` import; `urllib` only

**Out of scope** RAG metrics (EL-312/313), other stores (Weaviate/Chroma Ã¢ÂÂ same shape, later).

**Gotchas** `describe()` must surface the **embedding model**, because a recall@k computed against
a different embedding than the app uses is meaningless (G1).

````text
WHAT I WANT
evalloop/connect/vector_qdrant.py: a read-only Qdrant connector over its HTTP API, urllib only, no
SDK.

WHAT IS IN THE TICKET
ARCHITECTURE.md section 6: connect read-only to the vector store; enumerate collections and the
embedding model in use. HTTP vector stores need no driver exception -- urllib, not qdrant-client.

THE RESULT I WANT TO SEE
1. probe/describe/read on Qdrant over HTTP via urllib, through the broker and envelope.
2. describe() enumerates collections AND the embedding model in use -- the latter matters because a
   recall@k measured against a different embedding than the app uses is a meaningless number (G1).
3. read() is a read-only search; a write/delete HTTP verb is rejected by the envelope.
4. The test runs against a fake HTTP server fixture -- no live Qdrant, no network.
5. A source scan proves no qdrant-client import.

OUT OF SCOPE: RAG metrics (EL-312/313) and other vector stores (Weaviate/Chroma -- same shape,
later tickets).
````

---

### EL-310 Ã¢ÂÂ File + prompt-registry connectors
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-307 ÃÂ· **Blocks:** Ã¢ÂÂ ÃÂ·
**Done when:** prompts and files are usable as eval inputs.

**Files** Ã¢ÂÂ `evalloop/connect/files.py`, `evalloop/connect/prompts.py` ÃÂ·
`tests/test_file_prompt_connectors.py`

**Subtasks**
- [ ] A directory connector (source docs via `source_doc_read`) Ã¢ÂÂ read-only, gitignore-aware, size-capped
- [ ] A prompt-registry connector: prompt files on disk **and** MCP prompts (via EL-307)
- [ ] Both expose content as eval inputs (a RAG question set's source docs; a prompt under test)

**Acceptance criteria**
- [ ] A docs directory and a prompt file are both read and exposed as eval inputs
- [ ] An MCP-served prompt is usable through the same interface
- [ ] Binary/oversized files are skipped with a reason, not read

**Out of scope** Using them in a metric (that's EL-312/313 and the judge track).

**Gotchas** Source docs are the raw material for a RAG question set Ã¢ÂÂ keep the read gitignore-aware
and size-capped so it doesn't ingest `node_modules` or a 2 GB dump.

````text
WHAT I WANT
evalloop/connect/files.py + prompts.py: connectors that make a directory of documents and a prompt
registry (files on disk or MCP prompts) usable as eval inputs.

WHAT IS IN THE TICKET
ARCHITECTURE.md: source docs feed a RAG question set via source_doc_read; prompts under test come
from files or from MCP prompts (EL-307). These are read-only inputs, not live systems.

THE RESULT I WANT TO SEE
1. A directory connector that reads source docs read-only, gitignore-aware and size-capped, exposing
   them as eval inputs.
2. A prompt-registry connector for prompt files on disk AND MCP prompts (through EL-307's faÃÂ§ade),
   both usable through one interface.
3. A binary or oversized file is skipped with a stated reason, never read into memory.
4. Everything routed through the broker and the redactor at the boundary.

OUT OF SCOPE: computing any metric from them (EL-312/313 and the M4 judge). This ticket makes the
inputs available; it does not score anything.
````

---

### EL-311 Ã¢ÂÂ V8 SQL validator (execution match)
**Type:** Story ÃÂ· **Est:** 1.5 ÃÂ· **Depends:** EL-308 ÃÂ· **Blocks:** EL-315 ÃÂ·
**Done when:** reordered JOINs pass and a hallucinated column hard-fails.

**Files** Ã¢ÂÂ `evalloop/grade/sql_execution.py` ÃÂ· `tests/test_sql_validator.py`

**Subtasks**
- [ ] **Schema-ground** the statement: every table/column must exist. A hallucinated column is a **hard fail, reported separately** from a logic failure (`A:39` classes incl. `unknown_column`)
- [ ] Execute generated and reference SQL on a **frozen snapshot**; compare **result sets** Ã¢ÂÂ multiset equality, **order-insensitive unless the query has `ORDER BY`** (`ARCHITECTURE.md` ÃÂ§6.4)
- [ ] **Seed distinguishing rows** so plausible wrong answers diverge (`A:36` Ã¢ÂÂ the `>`/`>=` row)
- [ ] No-reference path: parses Ã¢ÂÂ / executes Ã¢ÂÂ / schema-grounded Ã¢ÂÂ / non-empty + type-consistent, then a cross-family judge as the **lowest** rung
- [ ] **Never** report string similarity to a reference query as correctness (`A1` anti-pattern)
- [ ] Carries `A1_execution_based`; pass rate travels with its Wilson interval (C1)

**Acceptance criteria**
- [ ] Two SQL statements that differ only by JOIN order / aliases return equal result sets Ã¢ÂÂ **pass**
- [ ] A query selecting a non-existent column Ã¢ÂÂ **hard fail, class `unknown_column`**, distinct from a wrong-rows logic failure
- [ ] An `ORDER BY` query is graded order-sensitively; a non-`ORDER BY` query is not
- [ ] No code path compares query *text* for correctness Ã¢ÂÂ a source check
- [ ] The corpus's own figure is honoured: a reading that would reproduce exact-match's 41% over execution's 68% is the bug, not the target

**Out of scope** Writes, end-state (EL-314), RAG (EL-312/313).

**Gotchas** `A:31`: exact match 41%, execution match 68%, judge 79% (22 wrong queries approved). The
68% is the number that is true. A validator built to agree with a plausible reading of the SQL
reproduces the 79%.

````text
WHAT I WANT
evalloop/grade/sql_execution.py: grade generated SQL by RUNNING it against a frozen snapshot and
comparing result sets -- never by comparing query text.

THE WARNING THIS TICKET IS BUILT AROUND
A:31 / ARCHITECTURE 6.4: on 200 text-to-SQL items, exact match scored 41%, execution match 68%, an
LLM judge 79% -- and the judge "passed 22 queries that returned the wrong rows." The 68% is the
number that is true. String similarity to a reference query is the exact failure the corpus row
exists to prevent.

THE RESULT I WANT TO SEE
1. Schema-grounding: every table and column must exist. A hallucinated column is a HARD FAIL, class
   unknown_column, reported SEPARATELY from a wrong-rows logic failure (A:39).
2. Execute generated AND reference SQL on a frozen snapshot; compare RESULT SETS -- multiset
   equality, order-insensitive UNLESS the query has ORDER BY.
3. Reordered JOINs and renamed aliases that return the same rows -> PASS (equivalent-but-different is
   not wrong). A selected non-existent column -> hard fail.
4. Seed distinguishing rows so a plausible wrong query returns different rows (A:36: a refund of
   exactly 5,000 to separate > from >=). Without them, wrong queries pass by coincidence.
5. No reference query? parses / executes / schema-grounded / non-empty + type-consistent, then a
   CROSS-FAMILY judge on question-vs-rows as the LOWEST rung -- never the only rung.
6. NEVER compare query text as correctness -- a source check proves no string-similarity path.
7. Carries A1_execution_based into every case; the pass rate travels with its Wilson interval (C1).

OUT OF SCOPE: writes and end-state (EL-314), RAG (EL-312/313). Everything runs under EL-305's
read-only envelope on a snapshot, never live data.
````

---

### EL-312 Ã¢ÂÂ V9 RAG stage 1: recall@k
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-309 ÃÂ· **Blocks:** EL-313 ÃÂ·
**Done when:** faithfulness refuses to run before recall@k is measured.

**Files** Ã¢ÂÂ `evalloop/grade/rag_recall.py` ÃÂ· `tests/test_rag_recall.py`

**Subtasks**
- [ ] Compute **recall@k at the k the generator actually receives** (`G1`: recall@20 is irrelevant if the prompt gets 5)
- [ ] Set the readiness fact `recall_at_k_measured = true` **only after** recall@k runs Ã¢ÂÂ so `G3_faithfulness`'s `requires` gates it (see F8 below)
- [ ] Report recall@k with its interval; name the embedding model and the k used

**Acceptance criteria**
- [ ] recall@k computed against a fixture index at the real k, reported with a confidence interval
- [ ] `G3_faithfulness` evaluated **before** recall@k has run resolves to **PENDING** `needs recall_at_k_measured: true, have false` Ã¢ÂÂ a test proves the ordering holds
- [ ] After recall@k runs, faithfulness is no longer blocked on that key

**Out of scope** Faithfulness itself, attribution, distractors, unanswerables (all EL-313).

**Gotchas Ã¢ÂÂ F8, read this.** `unlocks` is read by **no planner step**, so the "recall before
faithfulness" edge in the registry **does not gate anything**. You must enforce the order through
`requires`/readiness: faithfulness carries `requires: {recall_at_k_measured: true}`, and this
ticket is the only thing that sets that fact true. If you lean on `unlocks`, faithfulness runs first.

````text
WHAT I WANT
evalloop/grade/rag_recall.py: measure retrieval recall@k, and make faithfulness UNABLE to run until
recall@k has been measured.

WHAT IS IN THE TICKET
G1: compute recall@k at the k you actually pass to the generator -- recall@20 is irrelevant if the
prompt receives 5. The corpus build order is recall@k -> gold-context ceiling -> attribution ->
faithfulness, and "end-to-end accuracy is about recall@k times generator-given-gold, so fix the
lower factor first."

THE RULE THAT MATTERS MOST -- AND THE TRAP
Faithfulness must refuse to run before recall@k. BUT F8: `unlocks` is read by no planner step, so
the registry's recall->faithfulness edge gates NOTHING. Enforce it through readiness instead:
G3_faithfulness carries requires: {recall_at_k_measured: true}; THIS ticket sets that fact true only
after recall@k actually runs; EL-213 already turns that fact into a PENDING reason. If you rely on
unlocks, faithfulness will run first and the gate is a lie. Report which mechanism you used.

THE RESULT I WANT TO SEE
1. recall@k at the real k (the number the generator receives), reported with its confidence
   interval, naming the embedding model and k.
2. G3_faithfulness evaluated before recall@k -> PENDING "needs recall_at_k_measured: true, have
   false", proven by a test.
3. After recall@k runs, the fact is set and faithfulness is no longer blocked on it.
4. recall@k computed against a fixture index -- no live vector store needed in the test.

OUT OF SCOPE: faithfulness, oracle-context ceiling, attribution, distractor robustness,
unanswerables -- all EL-313.
````

---

### EL-313 Ã¢ÂÂ V10 RAG stage 2
**Type:** Story ÃÂ· **Est:** 1.5 ÃÂ· **Depends:** EL-312 ÃÂ· **Blocks:** EL-315 ÃÂ·
**Done when:** each stage is reported separately.

**Files** Ã¢ÂÂ `evalloop/grade/rag_stages.py` ÃÂ· `tests/test_rag_stages.py`

**Subtasks**
- [ ] **Oracle-context ceiling** (`G2`): replace retrieval with gold passages to find the generator's ceiling
- [ ] **Per-failure stage attribution** (`G2`): tag each failure **not retrieved / ranked beyond k / misread**
- [ ] **Faithfulness** (`G3`): atomic-claim decomposition + NLI/validated judge; report **mean faithfulness AND % of answers with Ã¢ÂÂ¥1 unsupported claim**
- [ ] **Distractor robustness** (`G7`) and **unanswerables** (`G6`: false-answer rate + over-abstention); **citation precision/recall** (`G8`)
- [ ] **Each stage reported separately** Ã¢ÂÂ never one blended RAG score
- [ ] The judge used for faithfulness must be **cross-family** and calibrated (ÃÂº gate) Ã¢ÂÂ depends on the M4 judge

**Acceptance criteria**
- [ ] A run reports recall@k, gold-context ceiling, stage attribution, faithfulness (both numbers), distractor robustness, and unanswerable behaviour as **separate** lines, each with its interval
- [ ] Faithfulness does not run until EL-312's fact is set (inherited gate)
- [ ] The faithfulness judge is proven cross-family; it refuses to gate below the ÃÂº threshold

**Out of scope** Building the judge itself (M4 / T33Ã¢ÂÂT36) and the ÃÂº calibration gate Ã¢ÂÂ this
*consumes* them.

**Gotchas** This ticket has a **cross-track dependency on M4's judge**: faithfulness (`G3`) needs a
validated cross-family judge, and `G3`'s own ÃÂº bar is a readiness gate. If M4 isn't landed, the
faithfulness stage is `PENDING`/`UNAVAILABLE`, not skipped Ã¢ÂÂ surface that honestly.

````text
WHAT I WANT
evalloop/grade/rag_stages.py: the rest of the RAG ladder -- gold-context ceiling, per-failure stage
attribution, faithfulness, distractor robustness, unanswerables, citation P/R -- each stage reported
SEPARATELY.

WHY SEPARATE STAGES
G1/G2: "without attribution, every fix is a guess." The corpus's own cases -- a team that rewrote
prompts for three weeks when the fix was re-chunking a table (recall), and another that cancelled a
6-week vector-DB migration when the fix was a prompt (generation) -- are the reason one blended RAG
number is useless. Each stage must stand alone.

THE RESULT I WANT TO SEE
1. Oracle-context ceiling (G2): feed gold passages, measure the generator's ceiling.
2. Per-failure attribution (G2): every failure tagged not-retrieved / ranked-beyond-k / misread, as
   SHARES of actual failures, so the backlog ranks by impact.
3. Faithfulness (G3): atomic claims, NLI/validated-judge entailment; report BOTH mean faithfulness
   AND % of answers with >=1 unsupported claim (the second is what users feel).
4. Distractor robustness (G7), unanswerables (G6: false-answer rate AND over-abstention), citation
   precision/recall (G8).
5. Each stage its own line, each number with its interval. No single blended RAG score.
6. The faithfulness judge is CROSS-FAMILY and calibrated; below the kappa gate it does not gate.

THE CROSS-TRACK DEPENDENCY, STATED HONESTLY
Faithfulness needs M4's judge and its kappa calibration gate. If M4 has not landed, the faithfulness
stage is PENDING/UNAVAILABLE with that reason -- NOT silently skipped, and NOT a bare number.

OUT OF SCOPE: building the judge and the kappa gate (M4). This ticket consumes them; it does not
build them.
````

---

### EL-314 Ã¢ÂÂ V11 End-state verification
**Type:** Story ÃÂ· **Est:** 1 ÃÂ· **Depends:** EL-306 ÃÂ· **Blocks:** EL-315 ÃÂ·
**Done when:** a false "done" is caught against real state.

**Files** Ã¢ÂÂ `evalloop/grade/end_state.py` ÃÂ· `tests/test_end_state.py`

**Subtasks**
- [ ] Verify the **resulting state** (DB rows, files) through a read-only connector Ã¢ÂÂ **not** the transcript's claim (`A2`/`H2`)
- [ ] A write-needing setup runs against a **scratch schema or restored snapshot** (`ARCHITECTURE.md` ÃÂ§6.2), never live
- [ ] Carries `A2_end_state_verification`; honours its `requires` (resettable env Ã¢ÂÂ `H`)

**Acceptance criteria**
- [ ] An agent/script that *claims* "done" / "tests pass" but left the DB or files in the wrong state Ã¢ÂÂ **caught**, verdict from the real state
- [ ] The transcript's self-report is never used as evidence (`A` end-state rule)
- [ ] Setup/writes happen only in a scratch schema or snapshot; the live schema is untouched (audit log proves it)

**Out of scope** Full agent evals / pass^k / trace capture (M5, T43).

**Gotchas** `ARCHITECTURE.md` ÃÂ§9: "Agent's 'tests pass' is false Ã¢ÂÂ independent re-run in a clean
sandbox; the transcript is never evidence." The claim is the thing under suspicion, not the source
of truth.

````text
WHAT I WANT
evalloop/grade/end_state.py: verify what actually happened to the DB/files, not what the agent said
happened.

WHAT IS IN THE TICKET
A2 / H2 end-state verification, and ARCHITECTURE.md section 9: "Agent's 'tests pass' is false ->
independent re-run in a clean sandbox; the transcript is never evidence." A resettable environment
precedes agent evaluation (H); writes go to a scratch schema or restored snapshot, never live.

THE RESULT I WANT TO SEE
1. A verdict computed from the REAL resulting state -- rows in the DB, files on disk -- read through
   a read-only connector.
2. An agent/script that claims "done" or "tests pass" while leaving the state wrong is CAUGHT, and
   the verdict comes from the state, not the claim. A test proves the false "done" fails.
3. The transcript's self-report is never used as evidence.
4. Any setup/writes run in a scratch schema or a restored snapshot; the audit log proves the live
   schema was never touched.
5. Carries A2_end_state_verification and honours its requires (resettable environment).

OUT OF SCOPE: full agent evaluation, pass^k, trajectory/trace capture -- that is M5 (T43). This
ticket verifies end state for a single run.
````

---

### EL-315 Ã¢ÂÂ Ã°ÂÂÂ Gate V
**Type:** Gate ÃÂ· **Est:** 0.5 ÃÂ· **Depends:** EL-311, EL-313, EL-314 ÃÂ· **Blocks:** (Track V complete) ÃÂ·
**Done when:** a DB **and** a vector store are discovered and validated **unprompted**.

**Deliverable** Ã¢ÂÂ `GATEV-REVIEW-PACKET.md` + the sample repo it ran against (a committed fixture,
placed so EvalLoop's own harvester does not ingest it Ã¢ÂÂ see Gate 1's F-G1a).

**What the packet must contain** (a document read in one sitting, every number with its interval):
- [ ] The **oracle run first** (`E6`): a known-correct SQL statement and a known-good RAG answer through the same pipeline must score 100%, or the gate is void
- [ ] Verbatim transcript of pointing EvalLoop at a repo with a Postgres (or SQLite) **and** a Qdrant endpoint, with **zero** instruction: discovery (with provenance) Ã¢ÂÂ consent Ã¢ÂÂ read-only probe Ã¢ÂÂ validation
- [ ] **The safety envelope proven**: a generated `DROP TABLE` rejected before transmission; the audit log showing zero writes to a live schema
- [ ] **Production default-deny demonstrated**: a prod-looking endpoint refused without the typed name
- [ ] SQL validated by **execution match** (reordered JOINs pass, hallucinated column hard-fails); RAG reported **stage by stage** with faithfulness gated behind recall@k
- [ ] A **negative control** (a correct query / faithful answer not flagged) and a **false negative** shown or its absence explained
- [ ] The findings ledger EL-301Ã¢ÂÂEL-314: nulls, interpreted thresholds, corpus-unsupported items, stale docs, open rulings
- [ ] One paragraph: does this safely validate against real systems, and where is it weakest

**Gotchas** Like Gate 1, do not write product code in the gate, do not fix a finding (report it),
and do not make the sample repo easier so the gate passes. The MCP-server-after-Gate-3 line (EL-008)
and the F8 ordering (EL-312) are the two most likely places a green gate would be hiding a real gap.

````text
WHAT I WANT
GATEV-REVIEW-PACKET.md plus the sample repo it ran against: the proof that EvalLoop can discover a
real database and a real vector store, get consent, connect READ-ONLY, and validate against them --
unprompted and safely. Not a code ticket; the deliverable is something you read and agree with or
send back.

THE THING THAT COMES BEFORE THE CLAIM
Run the ORACLE first (E6): push a known-correct SQL statement and a known-good RAG answer through
the same pipeline. If they do not score 100%, the harness is broken and the gate is void, whatever
it says about anything else.

THE RESULT I WANT TO SEE
1. The oracle run's result, first.
2. The verbatim transcript of pointing EvalLoop at a repo with a DB AND a vector store, with zero
   instruction: discover (with file:line provenance) -> consent -> read-only probe -> validate.
3. THE SAFETY ENVELOPE PROVEN: a generated DROP TABLE rejected before transmission; the audit log
   showing zero writes against any live schema; a production-looking endpoint refused without the
   typed name.
4. SQL validated by execution match: reordered JOINs pass, a hallucinated column hard-fails.
5. RAG reported stage by stage, with faithfulness provably gated behind recall@k (F8 -- via
   readiness, not unlocks).
6. A negative control (a correct query / faithful answer NOT flagged) and a false negative shown, or
   its absence explained.
7. The findings ledger EL-301 -> EL-314, and the cost, with every number carrying its interval.
8. One paragraph: does this safely validate against real systems, and where is it weakest? A green
   Gate V I do not understand is worse than a red one.

DO NOT: write product code, fix a finding the packet raises, or make the sample repo easier so the
gate passes. The two likeliest places a green gate hides a gap are the MCP-server boundary (EL-008 --
you built a client, not a server) and the recall->faithfulness ordering (EL-312 -- enforced by
readiness, not by the dead `unlocks` edge).
````

---

## 4. Dependencies to settle before Track V starts (raised, not decided)

1. **Sign off Gate 1 and close Gate 0.** Every ticket here `Depends on EL-212`; both gates are open.
2. **Rule EL-301 transport** (stdio-only per EL-007 vs the board's "stdio + HTTP").
3. **Confirm EL-302 supersedes** the M1 driver's stand-in permission logic (one broker).
4. **The F8 mechanism** (EL-312/313): readiness-gated RAG ordering, since `unlocks` gates nothing Ã¢ÂÂ
   this is a correctness decision, not a preference.
5. **M4 judge availability** for EL-313 faithfulness Ã¢ÂÂ Track V consumes it; if M4 hasn't landed,
   faithfulness is honestly `PENDING`, and the Gate V schedule should know that.
6. **fixture 20 / PHI** Ã¢ÂÂ Track V is the first code to read real customer data; the redactor and the
   PHI gate policy must be settled, because this is where they finally bite.
