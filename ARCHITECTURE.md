# ARCHITECTURE.md — EvalLoop: Autonomous Observation → Evaluation

How EvalLoop becomes genuinely autonomous: how it *observes* what you are building, how it *plugs into your coding agent*, and how it *connects to live systems* to validate real results.

This document sits **above** `AGENT.md` (which describes the evaluation pipeline) and **extends** `PLAN.md` / `TASKS.md` (which schedule it). It does not change Milestone 0. Nothing here is built until the gate it depends on has passed.

Items marked **(proposed)** are engineering choices, not methodology. Methodology thresholds remain verbatim-from-corpus or `null`, per `CLAUDE.md §3`.

---

## 1. The delta from the current docs

The existing design already has the hard part: a codified methodology registry and a planner that picks techniques. What it does not yet have is the thing that makes it feel autonomous.

| Current docs say | This document adds | Why |
|---|---|---|
| AI transcript reader (T21) reads Claude Code JSONL | A **sensor layer** with one adapter per coding agent, plus **push hooks**, normalised onto one event bus | Polling one vendor's log file is a feature. A sensor protocol is an architecture. |
| Classifier consumes file content | Classifier consumes an **Intent Bus** (what changed + what you *said* you wanted + what the agent *claimed*) | Code tells you *what*. The prompt tells you *why*. Only the prompt gives you eval criteria. |
| MCP **client** in M5 | MCP **server** — the coding agent calls EvalLoop | Inverts the integration: evaluation results flow *back into the agent* that wrote the code. This is the actual loop. |
| Connectors in M5 ("GitHub → DB → Databricks") | **Discovery → consent → read-only envelope → validation** as a first-class subsystem with a safety contract | "Auto-login to the vector DB" is the single most dangerous capability in the product. It needs a design, not a bullet point. |
| — | **Claim verification**: the agent says "done, tests pass"; EvalLoop independently re-checks | This is the actual user complaint ("people don't test it properly") turned into a falsifiable assertion. |
| — | **Screen sensor**, ranked last and optional | Pixels are the weakest, costliest, most invasive signal. It has real uses. It is not the foundation. |

---

## 2. The one hard problem

Everything downstream of "which situation is this?" is mechanics that `AGENT.md` already specifies. The hard problem is **intent inference**, and it has exactly one failure mode that matters:

> Picking the wrong evaluation is more expensive than running no evaluation, because a confident wrong number gets shipped.

So the architecture is organised around *how much evidence of intent we have*, and the system degrades honestly as that evidence thins:

```
strong intent evidence   → specific techniques, named criteria, high-confidence oracles
weak intent evidence     → generic ladder (execution → deterministic), no judge
no intent evidence       → observe only, report "situation unclear", run nothing
```

The system is never allowed to guess a situation and act on it silently. Low classifier confidence is itself a reportable state, exactly like `PENDING`.

---

## 3. High-level architecture

```
┌─ SENSORS (push + poll, each independently toggleable) ──────────────────┐
│  S0 filesystem·git     S1 coding-agent hooks + transcripts              │
│  S2 shell/command      S3 runtime + live-system probes                  │
│  S4 window titles → screen frames (opt-in, last resort)                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  normalised Event(kind, ts, payload,
                               │  provenance, confidence, redaction_state)
┌──────────────────────────────▼──────────────────────────────────────────┐
│ INTENT BUS                                                              │
│  append-only, in-process queue + JSONL spool; dedupe; debounce;         │
│  secret redaction at the boundary (nothing unredacted is persisted)     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│ EPISODE BUILDER                  (replaces "event buffer + debouncer")  │
│  groups events into an EPISODE: one unit of developer work              │
│  = stated intent + touched artifacts + agent claim + commands run       │
│  closes on: coherence + quiet window + claim-of-done + test invocation  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│ CLASSIFIER        heuristics → LLM only if unclear → multi-label        │
│  signals: code shape · imports · stated intent · touched paths · data   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ [(Situation, confidence), ...]
┌──────────────────────────────▼──────────────────────────────────────────┐
│ PLANNER = M0 "The Brain"       registry.match → constraints →           │
│  capability → readiness → conflicts → companions → deterministic order  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ Plan(ready, pending, unavailable, prohibited)
┌──────────────────────────────▼──────────────────────────────────────────┐
│ CAPABILITY BROKER   the only component holding credentials              │
│  tool grants · connector discovery · consent · cost budget · rate limit │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│ ORACLE LAYER → GRADER LADDER → STATISTICS → DIAGNOSTICS   (AGENT.md)    │
│  harvested HIGH / authored LOW   1 exec · 2 end-state · 3 det · 4 judge │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│ MEMORY   metric JSONL · episodic SQLite · case store · journey ledger   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│ SURFACES                                                                │
│  dashboard + timeline · summary.md · CLI · local API                    │
│  ► MCP server: the coding agent reads verdicts and fixes its own code   │
└─────────────────────────────────────────────────────────────────────────┘
```

Two properties hold across the whole diagram:

1. **Sensors are replaceable; the bus is the contract.** Adding Cursor support, or screen capture, or a Databricks probe, must never change the classifier, planner or graders.
2. **One component owns credentials.** The capability broker. A grader never reads an env var.

---

## 4. The sensor layer, ranked by value per unit of cost

This is the honest ranking. Build top-down and stop whenever the next tier stops paying.

| Tier | Sensor | What it uniquely tells you | Cost / risk | Verdict |
|---|---|---|---|---|
| **S0** | Filesystem poller + git state | Ground truth on *what changed* and a baseline to diff against | Free, stdlib | Foundation. Already planned (T18, T20). |
| **S1** | Coding-agent hooks + transcripts | **Stated intent, the agent's claim, and the exact artifact set** | Near-free, one adapter per agent | **Highest value in the system.** Build immediately after S0. |
| **S2** | Shell / command observation | What was actually run, exit codes, test output, repeated failures | Low; needs a shell wrapper or hook, not a keylogger | Build. Cheap source of "it's broken" truth. |
| **S3** | Runtime + live-system probes | Does the generated code actually work against the real DB / vector store / API | Medium; requires consent and a safety envelope | Build (Track V). This is what the user asked for by name. |
| **S4** | Window titles → screen frames | Intent when work happens in a GUI nobody can read from disk: a Databricks notebook, Postman, pgAdmin, a model playground | High: privacy, CPU, vision-model spend | Last. Opt-in. Window titles first; pixels only on demand. |

### 4.1 Why not "screen recorder first"

The screen is a *rendering* of state that mostly already exists in cheaper, exact, structured form. Reading `app.py` from disk is free, exact and diffable; OCR-ing a screenshot of `app.py` costs a vision-model call and returns a lossy guess. Screen capture only earns its place where the signal exists **nowhere else**.

### 4.2 The 90/1 insight

Most of what a screen recorder would tell you is in the **frontmost window title**, which costs effectively nothing:

- `Chrome — Databricks: notebook_etl_v3` → the dev is in a notebook, not the repo
- `TablePlus — analytics_prod` → **a production DB is open; raise the safety posture now**
- `Chrome — Qdrant Dashboard` → a vector store exists; start connector discovery
- `Postman — POST /v1/extract` → an API artifact is in play

Proposed policy: sample the frontmost app + window title at **1 Hz**; sample pixels **only** when all three hold — (a) the title changed to an unknown app, (b) the Intent Bus has no high-confidence situation for the current episode, and (c) the user granted `vision_model`. Frames are perceptually hashed so near-duplicates are never sent anywhere. Both `ocr` and `vision_model` already exist in the `Tool` enum, so the planner can already mark a technique UNAVAILABLE when they are not granted — no vocabulary change needed.

### 4.3 Redaction is a boundary, not a filter

Every sensor writes through one redactor before anything is buffered or persisted. It strips high-entropy strings, known key formats, `.env` values, `Authorization` headers, and anything matching PHI/PII patterns, and replaces them with stable placeholders (`<SECRET:a3f1>`) so the same secret is still *correlatable* across events without ever being stored. Screen frames are redacted by **not being stored at all** by default: a frame is hashed, optionally sent for one classification, and dropped.

---

## 5. Coding-agent integration (the part that makes it feel magic)

### 5.1 What a prompt gives you that code cannot

| From the prompt/response pair | Used as |
|---|---|
| "Write a function that converts NL questions to SQL over the orders table" | **The spec** → situation `sql_generation`, and eval criteria derived from the stated requirement |
| "Done — added tests, all 14 pass" | **The claim** → a falsifiable assertion. Re-verify independently in a clean sandbox. |
| Edit/Write tool calls | **The artifact boundary** → exactly which files are under evaluation, with no guessing |
| "it's still failing" ×3 | **A difficulty signal** → this episode deserves the full ladder, not a smoke test |
| "just make the test pass" | **A reward-hacking risk flag** → route to E-section diagnostics; check whether the test was weakened |

That last row is worth stating plainly: the phrase *"just make the test pass"* appearing in a transcript is one of the strongest reward-hacking predictors available, and it is invisible from the filesystem.

### 5.2 Adapter protocol

```python
class AgentSensor(Protocol):
    name: str
    def available(self) -> bool: ...
    def backfill(self, since: float) -> Iterator[Event]: ...   # read history from disk
    def stream(self) -> Iterator[Event]: ...                   # tail live
```

| Agent | Mechanism | Notes |
|---|---|---|
| **Claude Code** | `UserPromptSubmit` / `PostToolUse` / `Stop` hooks POST to `localhost`; JSONL transcripts as backfill and fallback | Push gives exact prompt↔edit↔claim causality with timestamps. Richest adapter; build first. |
| **Cursor / Windsurf** | Local workspace store on disk, tailed; adapter normalises | Format is undocumented and will drift — version-detect and degrade to S0 rather than crash |
| **Copilot / JetBrains AI** | No reliable local record | Degrade: S0 + S2 only. Report "intent evidence: weak" in the session report. |
| **Any MCP-capable agent** | EvalLoop's own **MCP server** (§5.3) | The portable path. No reverse-engineering. |

Hard rule: **an unparseable or newly-versioned agent log degrades the session to weak-intent mode. It never crashes the session and never guesses.**

### 5.3 EvalLoop as an MCP server — closing the loop

Instead of EvalLoop only reading the agent, the agent talks to EvalLoop:

| Tool exposed | Purpose |
|---|---|
| `evalloop.report_intent(text, artifacts)` | The agent declares what it is building. Perfect intent, zero inference. |
| `evalloop.evaluate(artifacts?)` | "I think I'm done" → run the plan now, don't wait for the quiet window |
| `evalloop.verify_claim(claim)` | "All tests pass" → independently checked, verdict returned |
| `evalloop.plan()` | Returns the Plan view, so the agent *knows what evidence is missing* and can generate more cases |
| `evalloop.findings(since)` | Verdicts flow back; the agent fixes its own bug before the human reads the diff |

This is the strongest argument for the whole product: the eval result becomes an **input** to code generation, not a report nobody opens. Note the ordering dependency — the MCP server is only safe once the honesty layer (M3) exists, because an agent iterating against a noisy grader will Goodhart it within minutes. `I-production.md`'s flywheel and `E-when-a-number-looks-wrong.md` both apply here.

---

## 6. Live-system validation (Track V) — "auto-connect and check the real result"

The user's examples: *"if some code says RAG it should auto-login to the vector DB and validate"*, *"I am building text-to-SQL and my results are coming — it should automatically validate that."* This is exactly `A-choosing-how-to-grade.md`'s first rule — *if you can execute the output or check it against the real world, do that instead of judging it* — so it is methodologically required, not a nice-to-have.

### 6.1 Four stages, never skipped

```
DISCOVER → PROPOSE → CONSENT → PROBE (read-only envelope)
```

1. **Discover (no connection, no credentials read).** Scan for *evidence* of endpoints: `.env` / `.env.example` keys, `docker-compose.yml` services, `settings.py` / config modules, client constructor call sites in code (`chromadb.HttpClient`, `psycopg.connect`, `QdrantClient`, `create_engine`), `alembic.ini`, listening local ports, and window titles from S4. Output: candidate endpoints with provenance ("because `docker-compose.yml:14` defines `qdrant:6333`").
2. **Propose.** One permission request per endpoint, stating: host, database/collection, credential *source* (not value), operations requested, row/time caps, and what will be read. Classified `local` / `staging` / `unknown` / **`production-suspected`**.
3. **Consent.** Explicit, per-endpoint, revocable, with a session-only default. `production-suspected` requires typing the endpoint name to confirm, and defaults to **deny**. Heuristics: hostname or db name matching `prod|live|www`, a non-RFC1918 host, or a credential from a secrets manager rather than `.env`.
4. **Probe, inside the envelope.** Below.

### 6.2 The read-only envelope (non-negotiable)

| Guard | Implementation |
|---|---|
| Read-only transaction | `BEGIN TRANSACTION READ ONLY` (Postgres), `SET SESSION TRANSACTION READ ONLY` (MySQL), `?mode=ro` (SQLite) |
| Statement AST check | Parse the generated statement; **reject** DDL/DML/`COPY`/`GRANT`/multi-statement before it is sent, instead of relying on the server |
| Caps | Statement timeout, `LIMIT` injection, max rows, max bytes, max queries per episode |
| Isolation for writes | Any technique needing writes (end-state verification, agent evals) gets a **scratch schema or a restored snapshot**, never the live schema. Per `H-agents.md`, a resettable environment precedes all agent evaluation. |
| Audit | Every statement sent to any endpoint is logged into the session report, verbatim |
| Blast radius | One connector process, no ambient credentials, grants expire with the session |

### 6.3 The stdlib problem — a decision you need to make

`CLAUDE.md §3` forbids third-party packages, but `psycopg`, `mysqlclient`, `qdrant-client` and `chromadb` are all third-party. Three ways out:

| Option | Trade-off |
|---|---|
| **A. Subprocess to the dev's existing CLI clients** (`psql`, `mysql`, `duckdb`, `sqlite3`) + stdlib `urllib` for every vector store's HTTP API | **Recommended.** Keeps stdlib-only intact, reuses credentials/TLS/config the dev already has, trivially sandboxable, zero driver maintenance. Costs: CLI must be installed; result parsing needs care (use `--csv` / `-H`, or `\copy ... TO STDOUT WITH CSV`). |
| B. Scoped exception: third-party drivers allowed only inside `evalloop/connect/`, imported lazily, with the core still stdlib-only | Pragmatic, but the "no dependencies" promise becomes "no dependencies except…" and that line moves again later. |
| C. Implement wire protocols | Weeks of work and a permanent maintenance liability. No. |

Recommendation: **A**, with the rule written into `CLAUDE.md` as "connectors shell out; they never import a driver." SQLite and every HTTP-API vector store (Qdrant, Weaviate, Chroma) then need no exception at all.

### 6.4 Validation recipes, straight from the corpus

**Text-to-SQL** (`A` execution-based grading; the corpus's own worked figure is exact-match 41% vs execution-match 68% on 200 items):
1. Schema-ground the statement: every table and column must exist. A hallucinated column is a hard fail, reported separately from a logic failure.
2. Execute generated and reference SQL on a **frozen snapshot**, compare **result sets** — multiset equality, order-insensitive unless the query has `ORDER BY`.
3. No reference query? Then: parses ✓, executes ✓, schema-grounded ✓, result non-empty and type-consistent, plus a cross-family judge on *question ↔ returned rows* as the lowest rung.
4. **Constraint:** never report string similarity to a reference query as correctness. That is the exact failure the corpus row exists to prevent.

**RAG** (`G-rag-systems.md` build order, which the registry enforces via `unlocks`):
1. Connect read-only to the vector store; enumerate collections and the embedding model in use.
2. Build or harvest a question set from the indexed source docs.
3. **recall@k first.** Faithfulness is not reported until retrieval is measured — the corpus is explicit that end-to-end accuracy cannot tell you which stage broke.
4. Then oracle-context (gold-context) ceiling, per-failure stage attribution (not retrieved / ranked too low / misread), faithfulness by claim decomposition, context precision + distractor injection, citation precision.
5. Unanswerable set: questions whose answer is absent must be refused.

**Agents** (`H-agents.md`): resettable environment, then end-state verification against the real system, ignoring the transcript — the corpus's figure is a transcript judge saying 91% complete where the DB check says 74%.

### 6.5 Worked walkthrough — four of the user's own scenarios

| You are building | Sensed | Situation | Auto-connected | Fires | Pending until |
|---|---|---|---|---|---|
| **Text-to-SQL** | prompt mentions SQL; `psycopg.connect` call site; `*.sql` fixtures | `sql_generation` | local Postgres from `docker-compose.yml`, read-only | schema grounding → execution result-set match → per-field diff | a reference set exists; statistical gates need n per `C` |
| **RAG bot** | `qdrant-client` import; docs folder; prompt says "answer from the policy PDFs" | `rag_answer` | Qdrant HTTP, read-only; source docs via `source_doc_read` | recall@k → gold-context ceiling → stage attribution → faithfulness | question set built; faithfulness **blocked** until recall@k is measured |
| **Summarizer** | prompt says "summarize"; function returns prose | `summarization` | none needed | cross-family binary-criteria judge, **always** reported with output length (length-bias companion) | judge calibration (κ ≥ 0.6 per `F`) before the judge may gate |
| **QA endpoint** | FastAPI route; prompt says "answer questions" | `qa_answer` + `api_endpoint` | none / local app | normalised exact match + token-F1 on short facts; schema validation on the response | enough items for a Wilson interval worth reporting |

Note what the right-hand column does: it is the product. The honest "not yet, and here is exactly what's missing" is what separates this from a tool that prints a number.

---

## 7. Component inventory

New components are marked **NEW**; the rest already exist in `AGENT.md` and are unchanged.

| # | Component | Package | Milestone | Depends on |
|---|---|---|---|---|
| 1 | Registry + planner ("The Brain") | `evalloop/registry`, `evalloop/plan` | M0 | — |
| 2 | Metric + episodic store | `evalloop/memory` | M1 | — |
| 3 | Oracle layer, sandbox, graders, statistics | `evalloop/grade`, `evalloop/stats` | M1 | 1, 2 |
| 4 | **Sensor protocol + redactor** **NEW** | `evalloop/sense/` | M2 | — |
| 5 | FS/git sensor (S0) | `evalloop/sense/fs.py`, `git.py` | M2 | 4 |
| 6 | **Agent sensors (S1) + hook receiver** **NEW** | `evalloop/sense/agents/` | M2 | 4 |
| 7 | **Command sensor (S2)** **NEW** | `evalloop/sense/shell.py` | M2 | 4 |
| 8 | **Intent Bus** **NEW** | `evalloop/bus.py` | M2 | 4 |
| 9 | **Episode builder** (absorbs debouncer + coherence) **NEW** | `evalloop/episode.py` | M2 | 8 |
| 10 | Classifier | `evalloop/classify/` | M1→M2 | 9 |
| 11 | **Capability broker** (grants, consent, cost, rate limits) **NEW** | `evalloop/capability/` | M2 | — |
| 12 | Session orchestrator | `evalloop/session.py` | M2 | 8–11, 3 |
| 13 | Local API + dashboard + **timeline** **NEW** | `evalloop/serve/` | M2 | 12 |
| 14 | Honesty layer (readiness, noise floor, diagnostics, self-canary) | `evalloop/honesty/` | M3 | 3 |
| 15 | **MCP server** **NEW** | `evalloop/mcp/` | after M3 | 12, 14 |
| 16 | **Connector layer** (discover / consent / envelope / probe) **NEW** | `evalloop/connect/` | after M1 | 11 |
| 17 | **Live validators** (SQL, RAG, end-state) **NEW** | `evalloop/connect/validate/` | after M1 | 16, 3 |
| 18 | **Screen sensor (S4)** **NEW**, opt-in | `evalloop/sense/screen.py` | last | 4, 11 |

---

## 8. User experience

### 8.1 Still two clicks

```
▶ START ──► work normally, any editor, any agent ──► ■ STOP ──► report
            │
            ├─ timeline fills in live (no refresh)
            ├─ permission request only when a technique needs a tool you haven't granted
            └─ notification only on a real finding
```

### 8.2 Three modes (proposed)

| Mode | Behaviour | For |
|---|---|---|
| **Observe** (default) | Watches, evaluates, reports. Never blocks, never interrupts except for real findings. | Day-to-day |
| **Guard** | Absolute gates (schema, safety, PHI) can block a commit or PR; quality gates stay statistical | Shipping |
| **Teach** | Every verdict shows which technique fired, why it was chosen, and what the alternative would have missed | Learning the methodology |

### 8.3 The recorder, done right: a replayable timeline

The user's instinct — "run like a recorder and see what I'm doing" — is correct about the *experience* and wrong about the *medium*. A video is unsearchable, unverifiable and un-diffable. The same instinct realised as structured events is far better:

```
10:02  ▸ you asked: "write NL→SQL over the orders table"        [Claude Code]
10:04  ▸ 3 files changed · src/nl2sql.py (+112)
10:07  ▸ agent claimed: "all 14 tests pass"
10:07  ⚑ VERIFIED INDEPENDENTLY → 12/14 pass. 2 failures hidden by a mocked cursor.
10:08  ▸ situation: sql_generation (0.91) · api_endpoint (0.44)
10:08  ▸ connected: postgres://localhost/shop_dev (read-only, you approved)
10:09  ✓ execution result-set match 68% (41% exact-match — the gap is equivalent rewrites)
10:09  ⧗ PENDING  statistical gate — needs n ≈ 100, have 31
```

Scrubbable, searchable, linkable, and every line is a fact with provenance. That is what a session recorder should produce.

### 8.4 Trust Center (the price of autonomy)

One screen, always reachable, honest about everything:

- **Sensors:** each one on/off, with "last event 3s ago" and exactly what it reads. Global **Pause** (red dot → grey).
- **Grants:** every tool and endpoint, who asked, what it may do, expiry, one-click revoke.
- **Spend:** LLM cost this session, against a budget you set. Hard stop, not a warning.
- **What left this machine:** a count and a sample of every outbound payload. Default posture: nothing leaves except explicit LLM calls you granted.
- **Privacy mode:** disables S1 prompt capture and S4 entirely; the session continues in weak-intent mode and says so.

### 8.5 Surfaces

| Surface | Content |
|---|---|
| Plan view | `READY / PENDING / UNAVAILABLE / PROHIBITED`, unchanged from `USER_EXPERIENCE.md §3.1` |
| Timeline | §8.3 |
| `summary.md` | What you built · what was evaluated and how · findings with per-item flips both ways · what is not yet answerable and what would unlock it · what was prohibited and why · cost · **every statement sent to every endpoint** |
| Local API | `/status` `/results` `/pending` `/timeline` `/grants` |
| MCP server | §5.3 — the agent's surface |
| CI | Condensed report as a PR comment; absolute gates for safety/schema, statistical gates for quality |

---

## 9. Corner cases and their guards

The request was to cover every corner. These are the ones that actually bite; each needs a test before its stage is called done.

**Observation**
| Case | Guard |
|---|---|
| Code is half-written | Episode closes only on coherence (`ast.parse` ✓) + quiet window; never mid-edit |
| Editor writes via atomic rename / swap files | Hash content, ignore `.swp`/`~`/`.tmp`; treat rename as modify |
| Huge or binary files; `node_modules`; monorepo | gitignore-aware walk, size cap, extension allowlist, per-package scoping |
| 5k-file repo | Poller target < 20 ms (T18); stat-first, hash only on mtime/size change |
| Dev reverts or rebases; `git checkout` mid-session | Git sensor detects HEAD/branch change → close all episodes, re-baseline |
| Two agents editing at once | Episodes keyed by artifact set; overlapping sets merge rather than race |
| Generated/vendored code | Excluded from evaluation unless explicitly named; never graded as the dev's work |
| Session crash mid-eval | Bus spools to JSONL; restart resumes from the last committed offset |
| Clock skew between sensors | All events stamped with one monotonic session clock, not wall time |
| Agent log format changed | Version-detect → degrade to weak-intent mode, warn once, never crash |

**Safety and privacy**
| Case | Guard |
|---|---|
| Secret pasted into a prompt | Redactor at the sensor boundary; only `<SECRET:hash>` is ever persisted |
| PHI/PII in the artifact | PHI gate precedes everything (fixture 20); no outbound LLM call on PHI without an explicit grant |
| Screen frame catches a password manager or a private message | S4 off by default; app denylist; frames hashed and dropped, never stored |
| Connector points at production | `production-suspected` classification, type-to-confirm, default deny |
| Generated SQL contains `DROP` | AST reject before transmission, plus read-only transaction, plus caps. Three independent layers. |
| A grader could mutate real state | Writes only in a scratch schema or restored snapshot |
| Credentials in a grader | Impossible by construction: only the capability broker holds them |

**Evaluation honesty**
| Case | Guard |
|---|---|
| Test weakened to pass | Diff the oracle, not just the code. Oracle change + score rise = reward-hacking flag (`E`) |
| Agent's "tests pass" is false | Independent re-run in a clean sandbox; the transcript is never evidence (`A` end-state rule) |
| Flaky test | Repeat runs → noise floor; a within-noise delta is never an improvement (`C`) |
| Non-deterministic LLM output | Fixed seed/temperature where possible; otherwise repeat and report variance, never a single number |
| Timeout / infinite loop | Wall-clock cap → **INCONCLUSIVE**, distinct from fail |
| Network-dependent code | Egress denied in the sandbox by default; network need is a declared capability |
| No oracle available | Ladder descends; if nothing can decide, it says so and queues a human review item. It does not invent an oracle. |
| Rare class | Accuracy **prohibited** with the reason shown (`D`) |
| Same-family judge | Hard assertion in the router; cross-family or no judge (`F`) |
| Judge uncalibrated | κ ≥ 0.6 runtime gate before a judge may gate anything (`F`) |
| Tiny n | `PENDING` with the margin stated (`margin ≈ 100/√n`), never a bare percentage |
| Cost runaway | Per-session budget, hard stop, cost shown in the Trust Center |
| EvalLoop itself degrades | Self-canary on a fixed known-answer set every session (M3) |

---

## 10. Task breakdown

Three tracks, each gated on existing milestones. **Do not start a track before its gate passes.** Universal done criteria from `TASKS.md` apply to every stage: `pytest` exit 0, `mypy --strict evalloop/` exit 0, no invented numbers, report back.

### Track O — Observe (intent capture). Starts after 🔒 GATE 1. Supersedes T18–T23.

| # | Stage | Done when |
|---|---|---|
| **O1** | `Event` frozen dataclass: kind, session clock ts, payload, provenance, confidence, `redaction_state`. `Sensor` + `AgentSensor` protocols. | Two fake sensors feed one bus in a test; events ordered deterministically |
| **O2** | Redactor: entropy heuristic, known key formats, `.env` value matching, stable `<SECRET:hash>` placeholders | Planted secrets in prompt text, env files and command lines are all replaced; the same secret yields the same placeholder |
| **O3** | Intent Bus: in-process queue + append-only JSONL spool, dedupe, offset commit, crash-resume | Kill mid-stream, restart, zero events lost or duplicated |
| **O4** | S0 filesystem sensor (= T18): `scandir` + stat, hash on mtime/size change, gitignore-aware, rename/atomic-write handling | 5k files < 20 ms; swap/tmp files ignored; rename reported as modify |
| **O5** | S0 git sensor (= T20): baseline, branch, staged/working diff, **HEAD-change detection** | Branch switch and rebase close open episodes and re-baseline |
| **O6** | S1 Claude Code adapter — transcript backfill (= T21) | Stated intent, agent claim and touched-file set extracted from a real transcript |
| **O7** | S1 hook receiver: localhost endpoint + a generated `.claude/settings.json` hook block (`UserPromptSubmit`, `PostToolUse`, `Stop`) | A live Claude Code session pushes prompt↔edit↔claim events with correct causal order |
| **O8** | S1 second adapter (Cursor or Codex CLI) + version-detect degradation | Unknown format → weak-intent mode, warn once, session survives |
| **O9** | S2 command sensor: shell wrapper / hook capturing command, exit code, truncated output | A failing `pytest` run appears on the bus with its exit code |
| **O10** | Episode builder (absorbs T19 + T22): group by artifact set, close on coherence + quiet window + claim-of-done + test invocation | Burst of 40 saves across 6 files → one episode; mid-edit syntax error never closes one |
| **O11** | Classifier upgrade: consume episodes (code signals **plus** stated intent), multi-label with confidence, explicit `unclear` state | 10 labelled episodes classified correctly; low-confidence case reports `unclear` and plans nothing |
| **O12** | Session orchestrator (= T23) + timeline API + timeline view | `evalloop start` → work → `evalloop stop` → report; timeline renders §8.3 live |
| **O13** | Trust Center: sensor toggles, grant list + revoke, spend meter, pause, privacy mode | Pause stops all sensors within one tick; revoke takes effect on the next technique |

🔒 **GATE O:** Work for an hour in your normal editor with your normal agent. The timeline is an accurate account of what you did, with no eval written and no configuration touched.

### Track V — Verify against live systems. Starts after 🔒 GATE 1 (needs the sandbox + execution grader). Independent of Track O.

| # | Stage | Done when |
|---|---|---|
| **V1** | Capability broker: grant model (tool, endpoint, scope, expiry), consent records, cost + rate budget | A technique needing an ungranted tool becomes UNAVAILABLE with the missing tool named; grants expire with the session |
| **V2** | Connector discovery: `.env`, compose files, config modules, client call sites, listening ports, S4 titles → candidates **with provenance** | Candidates listed from a sample repo, each citing the file and line it came from; **zero connections attempted** |
| **V3** | Endpoint classification + `production-suspected` heuristics | A `prod`-named host defaults to deny and demands type-to-confirm |
| **V4** | Read-only envelope: statement AST rejector, read-only transaction, timeout, row/byte caps, audit log | A planted `DROP TABLE` is rejected before transmission; every statement appears in the audit log |
| **V5** | `Connector` protocol + SQLite driver (stdlib) | `probe` / `describe` / `read` work against a fixture DB |
| **V6** | Postgres + MySQL connectors by subprocess CLI (per §6.3 decision) | Schema introspection and a capped read succeed; absent CLI → UNAVAILABLE, not a crash |
| **V7** | Vector-store connector over stdlib HTTP (Qdrant first) | Collections and embedding config enumerated read-only |
| **V8** | SQL validator: schema grounding → execution result-set comparison (order-insensitive unless `ORDER BY`) → per-field diff; string-similarity correctness **prohibited** | A correct-but-different `JOIN` order scores as correct; a hallucinated column hard-fails and is reported separately from a logic failure |
| **V9** | RAG validator stage 1: question-set build + recall@k | recall@k reported; **faithfulness refuses to run until it is** |
| **V10** | RAG validator stage 2: gold-context ceiling, stage attribution, faithfulness, context precision + distractor injection, unanswerable set | Each stage reported separately; corpus build order enforced by the registry, not by hand |
| **V11** | End-state verification: snapshot → act → assert post-conditions in a scratch schema | A false "done" claim is caught against real state |

🔒 **GATE V:** Open a repo containing text-to-SQL and a RAG path. EvalLoop discovers the local DB and vector store, asks once, and reports execution-match and recall@k — without being told either exists.

### Track L — Loop closure. Starts after 🔒 GATE 3 (requires the honesty layer).

| # | Stage | Done when |
|---|---|---|
| **L1** | Claim extractor: pull falsifiable assertions out of agent output ("all tests pass", "endpoint returns 200") | Claims extracted and typed from a real transcript |
| **L2** | Claim verifier: independent re-run in a clean sandbox, transcript never used as evidence | A mocked-out test suite that "passes" is caught |
| **L3** | MCP server: `report_intent`, `plan`, `evaluate`, `verify_claim`, `findings` | A coding agent calls all five over MCP |
| **L4** | Feedback channel: verdicts routed back to the agent with per-item detail | Agent receives a failing verdict and fixes the code unprompted |
| **L5** | Anti-Goodhart guards on the feedback loop: oracle-change detection, held-out cases never exposed, iteration counter | Agent weakening a test to pass is flagged, not rewarded |
| **L6** | Failures-as-tests flywheel: promote a caught failure to a `permanent` case | A caught bug reappears as a permanent case in the next session |

🔒 **GATE L:** An agent writes a subtly broken function, claims success, is contradicted with evidence, fixes it — and cannot make the number move by weakening the test.

### Track X — Screen sensor. **Last. Opt-in. Only if Tracks O/V leave real intent gaps.**

| # | Stage | Done when |
|---|---|---|
| **X1** | Window-title sensor: frontmost app + title at 1 Hz, app denylist | Databricks / TablePlus / Postman titles appear as bus events; denylisted apps never do |
| **X2** | Title → signal rules (GUI DB client open → raise safety posture; vector-store dashboard → discovery hint) | An open prod DB client raises the session's safety posture automatically |
| **X3** | Frame sampler: `screencapture` subprocess, perceptual hash, frames never persisted | Near-duplicate frames are dropped; nothing is written to disk |
| **X4** | Escalation policy: one vision/OCR call only when the title is unknown **and** intent confidence is low **and** `vision_model` is granted | Budgeted calls per session, with spend visible in the Trust Center |
| **X5** | Measure it: does S4 change any classification Tracks O/V got wrong? | A yes/no answer with numbers. **If no, delete the track.** |

🔒 **GATE X:** S4 demonstrably corrects classifications that no cheaper sensor could. If it doesn't, it is removed — not kept because it demos well.

### Ordering

```
M0 ─GATE 0─► M1 ─GATE 1─► ┬─► Track O ─GATE O─► M3 ─GATE 3─► Track L ─GATE L─►
                          └─► Track V ─GATE V─►                      │
                                                   Track X (optional) ◄┘
```

Tracks O and V are parallel and independent — one is about *knowing what you're building*, the other about *checking it against reality*. Build O first if intent inference is the bigger worry; build V first if you want the sharpest demo, because text-to-SQL validation against a live DB is the most convincing thing this system can do early.

---

## 11. Decisions needed from you

1. **§6.3 driver policy** — subprocess CLI (recommended), scoped dependency exception, or neither?
2. ~~**Corpus location**~~ — **Resolved by `decisions/EL-001-corpus-location.md`:** the in-repo `knowledge rules/` directory is canonical, under its real filenames; `EVALLOOP_CORPUS` still overrides. `CLAUDE.md §4` and the `TASKS.md` `source_ref` convention were corrected, and a missing corpus file now fails the suite by name. The sixth column ("Real-world domain scenario"), raised there and left open, is **resolved by `decisions/EL-011-sixth-column-mapping.md`:** it becomes `domain_scenario: str | None` on `TechniqueRecord`, copied verbatim at extraction and read by no planner code. `CLAUDE.md §4`, the `CLAUDE.md §6` field table and the `TASKS.md` field mapping now all account for six columns.
3. **Track order after Gate 1** — O first (intent) or V first (demo)?
4. **MCP server timing** — after Gate 3 as argued, or earlier accepting Goodhart risk?
5. **Is Track X in or out?** It is the only track I would not build on current evidence.
6. **Shell capture mechanism** for O9 — shell wrapper, `zsh` precmd hook, or agent-reported commands only?
7. **New vocabulary** — several situations here (`claim_unverified`, `live_endpoint_available`) have no `Situation` member. Add them in M0 while the enum is cheap to change, or carry them as episode metadata outside the enum?

---

## 12. Deliberately not included

- Video recording or storage of any kind. Structured events beat pixels on every axis that matters.
- Keylogging. S2 captures commands, not keystrokes.
- A cloud service, an account, or telemetry. The session is local; the only egress is LLM calls you granted.
- An editor plugin as a requirement. Disk + git + transcripts keep it editor-agnostic, per `USER_EXPERIENCE.md §4.5`.
- Auto-connecting to anything without consent. "Auto-login to the vector DB" means *auto-discover and ask once*, never *connect silently*.
