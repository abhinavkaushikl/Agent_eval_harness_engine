# DEVELOPMENT_PLAN.md — EvalLoop

The delivery plan: phases, dates, gates and tickets, in the order they get built.
It combines `PLAN.md` (M0–M5), `ARCHITECTURE.md` (Tracks O, V, L, X) and the MCP + enterprise plug-in work.

**Assumptions**
- **Team:** 1 full-time engineer working with a coding agent. With 2 engineers, Tracks V and O run in parallel and the end date moves about 4 weeks earlier.
- **Start:** Monday 5 Oct 2026. Weeks are 5 working days.
- **Estimates:** M0–M4 effort comes from `PLAN.md`. Tracks V, O and L, the MCP tickets and the enterprise tickets are new estimates and should be re-checked after M0.
- **Done:** every ticket shares the definition of done in `TASKS.md`: `pytest` exit 0, `mypy --strict evalloop/` exit 0, no invented numbers, and a report-back.

---

## 1. Development flow

```
 E0 Decisions
     │
     ▼
 E1 M0 The Brain ──🔒G0──► E2 M1 First Grading ──🔒G1──┐
 (registry + planner)      (sandbox, graders, stats)    │
                                                        ▼
                           E3 Track V: Connectors + MCP client ──🔒GV──┐
                           (DB, vector store, files, prompts)          │
                                                                       ▼
                           E4 Track O: Observe + MCP gateway ──🔒G2/GO─┐
                           (sensors, agent tool-call capture, session) │
                                                                       ▼
                           E5 M3 Honesty layer ──🔒G3──────────────────┐
                                                                       ▼
                           E6 M4 Judge, summarization, agent evals ──🔒G4
                                                                       ▼
                           E7 Track L: Loop closure + MCP server ──🔒GL
                                                                       ▼
                           E8 M5 Enterprise ──🔒Beta
                                                                       ▼
                           E9 Track X: Screen sensor (optional)
```

**Why this order**
- **The Brain comes first,** because picking the wrong evaluation is the most expensive mistake the system can make.
- **Connectors (V) come before Observe (O)** so enterprise data sources (DB, prompts, files) plug in early. This is decision D5 below and can be flipped.
- **The MCP server comes last (L),** after the honesty layer. An agent iterating against a noisy grader learns to game it.

---

## 2. Timeline

| # | Epic | Weeks | Dates | Gate | Gate date |
|---|---|---|---|---|---|
| E0 | Decisions | — | 5 Oct (runs alongside E1) | — | — |
| E1 | M0 The Brain | 1–2 | 5 Oct – 16 Oct 2026 | 🔒 G0: 20 plans reviewed and agreed | 16 Oct |
| E2 | M1 First Grading | 3–5 | 19 Oct – 6 Nov | 🔒 G1: broken function caught with zero setup | 6 Nov |
| E3 | Track V: Connectors + MCP client | 6–9 | 9 Nov – 4 Dec | 🔒 GV: discovers DB + vector store, validates SQL and RAG | 4 Dec |
| E4 | Track O: Observe + MCP gateway | 10–15 | 7 Dec – 15 Jan 2027 | 🔒 G2/GO: one-hour session gives an accurate timeline and report | 15 Jan |
| E5 | M3 Honesty layer | 16–17 | 18 Jan – 29 Jan | 🔒 G3: refuses noise as a win; catches a planted reward hack | 29 Jan |
| E6 | M4 Judge, summarization, agent evals | 18–20 | 1 Feb – 19 Feb | 🔒 G4: calibrated cross-family judge; agent pass^k | 19 Feb |
| E7 | Track L: Loop closure + MCP server | 21–22 | 22 Feb – 5 Mar | 🔒 GL: agent is contradicted with evidence and can't game the test | 5 Mar |
| E8 | M5 Enterprise | 23–27 | 8 Mar – 9 Apr | 🔒 Beta: installed at a pilot team | 9 Apr |
| E9 | Track X: Screen sensor | optional | after 9 Apr | 🔒 GX: proves it fixes misclassifications, or is deleted | — |

**Total: 27 weeks to enterprise beta (9 Apr 2027).** E4 spans the year-end holidays, and one week of its six is buffer for that.

```
            Oct       Nov        Dec        Jan        Feb        Mar        Apr
E1 M0       ██
E2 M1         ███
E3 V              ████
E4 O                  ██████
E5 M3                       ██
E6 M4                         ███
E7 L                             ██
E8 M5                              █████
```

---

## 3. Tickets

**Key:** `EL-<epic><nn>`. **Type:** Story · Task · Spike · Decision · Gate. **Est.** is in engineer-days. **Status:** ✅ Done, otherwise To Do.

### E0 — Decisions *(owner: product lead. Each one blocks the ticket listed)*

| Key | Decision | Recommendation | Blocks |
|---|---|---|---|
| EL-001 | Corpus location and file names (in-repo `knowledge rules/` vs an external directory, real names vs the names CLAUDE.md used to claim) | ✅ Decided: `knowledge rules/` is canonical, using the real names — `decisions/EL-001-corpus-location.md` | EL-103, EL-113 |
| EL-002 | Add MCP tools to the `Tool` enum (`mcp_gateway`, `mcp_client`) | ❌ Decided **No**, overturning the original "yes, while the enum is cheap": MCP is transport, not capability; it belongs to the broker (EL-302) and gateway (EL-408). Adding a member stays O(1) at any record count — `decisions/EL-002-mcp-tools-in-enum.md` | EL-104 |
| EL-003 | New situations (`claim_unverified`, `live_endpoint_available`, `agent_tool_call`) | Add them in M0 | EL-103 |
| EL-004 | Topics in CLAUDE.md that the corpus doesn't cover (reward hacking, Fleiss' κ, distilled rung, over-refusal) | Add them to the knowledge files or drop them from CLAUDE.md | EL-113 |
| EL-005 | Order of Track V and Track O after G1 | V first (enterprise plug-ins) | E3, E4 |
| EL-006 | DB driver policy | Subprocess CLI, with no driver dependencies | EL-308 |
| EL-007 | MCP implementation | Standard-library JSON-RPC, no SDK | EL-301 |
| EL-008 | MCP server timing | After G3 | EL-703 |
| EL-009 | Shell capture mechanism | zsh precmd hook plus commands the agent reports | EL-413 |
| EL-010 | Is Track X in scope? | Out, unless G2 shows gaps in intent capture | E9 |

### E1 — M0 The Brain *(5 Oct – 16 Oct · ~8 days)*

| Key | Summary | Type | Est. | Depends on | Done when | Status |
|---|---|---|---|---|---|---|
| EL-101 | S1 Project skeleton | Task | 0.5 | — | pytest + mypy green | ✅ |
| EL-102 | S2 Corpus path fixture | Task | — | EL-101 | Passes with the corpus, skips without it | ✅ |
| EL-103 | S3 `Situation` enum | Story | 0.25 | EL-001, EL-003 | Every source situation maps to exactly one member | |
| EL-104 | S4 `Tool` enum + parsers | Story | 0.15 | EL-002 ✅ | Round-trips every member; rejects unknowns with a helpful message. **Exactly the 15 members in `CLAUDE.md` §6 — no MCP members** (EL-002) | |
| EL-105 | S5 Vocab tests | Task | 0.1 | EL-103, EL-104 | ~20 verbatim source strings parse | |
| EL-106 | S6 Record format + parser | Story | 0.3 | EL-105 | Every construct tested; trade-off documented | |
| EL-107 | S7 `TechniqueRecord` schema | Story | 0.25 | EL-106 | Each validation rule has a positive and a negative test | |
| EL-108 | S8 Loader with aggregated errors | Story | 0.25 | EL-107 | Every error in every file reported | |
| EL-109 | S9 Integrity checker | Story | 0.2 | EL-108 | Every rule tested | |
| EL-110 | S10 Extract A, B, C | Task | 0.3 | EL-109 | Loads; integrity check empty | |
| EL-111 | S11 Extract D, E, F | Task | 0.3 | EL-110 | Loads; integrity check empty | |
| EL-112 | S12 Extract G, H, I, J | Task | 0.4 | EL-111 | Counts per section reported | |
| EL-113 | S13 Enrich A + B | Task | 0.4 | EL-112, EL-004 | Ladder, conflicts, McNemar threshold filled | |
| EL-114 | S14 Enrich C + D | Task | 0.4 | EL-113 | Verbatim rules of thumb; rare-class constraint | |
| EL-115 | S15 Enrich E + F | Task | 0.4 | EL-114 | κ / flip-rate thresholds; cross-family constraint | |
| EL-116 | S16 Enrich G + H | Task | 0.4 | EL-115 | Recall-before-faithfulness; env-before-agent | |
| EL-117 | S17 Enrich I + J | Task | 0.4 | EL-116 | Every record has a deep-dive `source_ref` | |
| EL-118 | S18 Fixture format + fixtures 1–5 | Task | 0.4 | EL-117 | 5 fixtures load | |
| EL-119 | S19 Fixtures 6–20 | Task | 0.6 | EL-118 | 20 fixtures load | |
| EL-120 | S20 `match()` | Story | 0.4 | EL-119 | Multi-label merge; deterministic order | |
| EL-121 | S21 Readiness | Story | 0.4 | EL-120 | "needs X, have Y" reasons | |
| EL-122 | S22 Capability, conflicts, companions | Story | 0.5 | EL-121 | Each one unit-tested | |
| EL-123 | S23 Planner + `render()` | Story | 0.7 | EL-122 | All 20 fixtures pass | |
| EL-124 | 🔒 Gate 0: human review of 20 plans | Gate | 0.5 | EL-123 | Every plan agreed | |

### E2 — M1 First Grading *(19 Oct – 6 Nov · ~14.5 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-201 | T7 Metric store (JSONL) | Story | 1 | EL-124 | Two runs diffed case by case |
| EL-202 | T8 Episodic store (SQLite) | Story | 1 | — *(can run in parallel)* | Decisions and reasoning persisted |
| EL-203 | T16 Statistics module (Wilson, bootstrap, cluster, McNemar, permutation, power) | Story | 1 | — *(can run in parallel)* | Matches the corpus worked examples |
| EL-204 | T9 Classifier heuristics | Story | 1.5 | EL-124 | Labels 10 sample files correctly |
| EL-205 | T10 Oracle harvester | Story | 1.5 | EL-204 | HIGH oracles from a real repo |
| EL-206 | T11 Sandbox runner | Story | 1.5 | EL-201 | Timeout → failed, class `timeout` (EL-014) |
| EL-207 | T12 Execution grader | Story | 2 | EL-206, EL-205 | Catches the broken function |
| EL-208 | T13 Deterministic grader | Story | 1 | EL-206 | Schema / regex / exact checks |
| EL-209 | T14 LLM client + router (stdlib HTTP) | Story | 1 | — | Routes by job; cost counted |
| EL-210 | T15 Test author (signature-only) | Story | 2 | EL-209, EL-205 | HIGH/LOW confidence tagging |
| EL-211 | T17 `summary.md` renderer | Task | 0.5 | EL-207 | Readable report per run |
| EL-212 | 🔒 Gate 1: toy repo with a broken function | Gate | 0.5 | EL-211 | Caught with zero instruction |

### E3 — Track V: Connectors + MCP client *(9 Nov – 4 Dec · ~18.5 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-301 | **MCP protocol core:** JSON-RPC 2.0 over stdio + HTTP, stdlib only | Story | 2 | EL-007, EL-212 | Handshake, tool listing and calls work against a reference MCP server |
| EL-302 | V1 Capability broker (grants, consent, expiry, budget) | Story | 1.5 | EL-212 | Ungranted tool → UNAVAILABLE, naming the missing tool |
| EL-303 | V2 Connector discovery with provenance | Story | 1.5 | EL-302 | Candidates cite file and line; zero connections attempted |
| EL-304 | V3 Production-suspected classification | Story | 1 | EL-303 | `prod` host → default deny + type-to-confirm |
| EL-305 | V4 Read-only envelope + audit log | Story | 1.5 | EL-304 | `DROP TABLE` rejected before it's sent |
| EL-306 | V5 `Connector` protocol + SQLite | Story | 1 | EL-305 | probe / describe / read work |
| EL-307 | **MCP client connector:** any MCP server becomes a read-only Connector | Story | 1.5 | EL-301, EL-306 | An external MCP DB server is queried through the envelope |
| EL-308 | V6 Postgres + MySQL via CLI | Story | 1 | EL-306, EL-006 | Missing CLI → UNAVAILABLE, not a crash |
| EL-309 | V7 Vector store (Qdrant, HTTP) | Story | 1 | EL-306 | Collections enumerated read-only |
| EL-310 | **File + prompt-registry connectors** (dirs, prompt files, MCP prompts) | Story | 1 | EL-307 | Prompts and files are usable as eval inputs |
| EL-311 | V8 SQL validator (execution match) | Story | 1.5 | EL-308 | Reordered JOINs pass; hallucinated column hard-fails |
| EL-312 | V9 RAG stage 1: recall@k | Story | 1 | EL-309 | Faithfulness refuses to run before recall |
| EL-313 | V10 RAG stage 2 (gold context, attribution, faithfulness, distractors, unanswerables) | Story | 1.5 | EL-312 | Each stage reported separately |
| EL-314 | V11 End-state verification | Story | 1 | EL-306 | A false "done" is caught against real state |
| EL-315 | 🔒 Gate V | Gate | 0.5 | EL-311, EL-313, EL-314 | DB + vector store discovered and validated unprompted |

### E4 — Track O: Observe + MCP gateway *(7 Dec – 15 Jan · ~26 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-401 | O1 `Event` + `Sensor` protocols | Story | 1 | EL-315 | Two fake sensors, one deterministic bus |
| EL-402 | O2 Redactor (secrets, PII, `.env`) | Story | 1.5 | EL-401 | Planted secrets replaced with stable placeholders |
| EL-403 | O3 Intent Bus (spool, dedupe, crash-resume) | Story | 1.5 | EL-401 | Killed mid-stream: nothing lost or duplicated |
| EL-404 | O4 Filesystem sensor | Story | 1 | EL-403 | 5k files in < 20 ms |
| EL-405 | O5 Git sensor | Story | 1 | EL-403 | Branch switch re-baselines |
| EL-406 | O6 Claude Code transcript adapter | Story | 1 | EL-403 | Intent, claim and files extracted |
| EL-407 | O7 Hook receiver (`UserPromptSubmit`, `PostToolUse`, `Stop`) | Story | 1 | EL-406 | Live session events in causal order |
| EL-408 | **MCP gateway:** proxy between the agent and its MCP tool servers | Story | 2 | EL-301, EL-403 | Agent tool calls pass through unchanged |
| EL-409 | **Gateway recorder:** every tool call (name, args, result, latency, cost) → bus, redacted | Story | 1 | EL-408, EL-402 | A full agent trajectory is reconstructed from the bus |
| EL-410 | **Gateway policy:** allowlist, read-only, forbidden actions, audit | Story | 1.5 | EL-409 | A forbidden call is blocked and logged |
| EL-411 | **Gateway install:** generate agent configs (Claude Code, Cursor) that route through the gateway | Task | 1 | EL-408 | One command wires an agent to the gateway |
| EL-412 | O8 Second agent adapter + graceful degradation | Story | 1 | EL-406 | Unknown format → weak-intent mode; session survives |
| EL-413 | O9 Command sensor | Story | 1 | EL-403, EL-009 | Failing `pytest` lands on the bus with its exit code |
| EL-414 | O10 Episode builder (debounce + coherence) | Story | 2 | EL-404, EL-405 | 40 saves → one episode; never closes mid-edit |
| EL-415 | O11 Classifier upgrade (code + intent + tool calls) | Story | 1.5 | EL-414, EL-409 | 10 episodes classified; `unclear` plans nothing |
| EL-416 | O12 Session orchestrator + timeline | Story | 2 | EL-415 | `evalloop start` → `evalloop stop` → report |
| EL-417 | T24 Content-hash cache | Task | 0.5 | EL-416 | An unchanged diff is never re-evaluated |
| EL-418 | T25 Local API (`/status`, `/results`, `/pending`) | Story | 1 | EL-416 | All three respond |
| EL-419 | T26 Dashboard (HTML + SSE) | Story | 1.5 | EL-418 | Updates live without a refresh |
| EL-420 | O13 Trust Center (toggles, grants, spend, pause) | Story | 1.5 | EL-419 | Pause stops all sensors within one tick |
| EL-421 | 🔒 Gate 2 / Gate O: one-hour real session | Gate | 0.5 | EL-420 | Accurate timeline + useful report, zero config |

### E5 — M3 Honesty layer *(18 Jan – 29 Jan · ~7 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-501 | T27 Readiness gate + pending queue | Story | 1 | EL-421 | Shows "need 25, have 8" |
| EL-502 | T28 Noise floor across runs | Story | 1 | EL-501 | A within-noise delta is never called an improvement |
| EL-503 | T29 Per-item diff, both directions | Story | 1 | EL-501 | Flips listed both ways |
| EL-504 | T30 Diagnostics: jump, length, ceiling, floor | Story | 1.5 | EL-503 | Synthetic reward hack flagged |
| EL-505 | T31 Journey ledger + trends | Story | 1 | EL-503 | Trend lines per field and slice |
| EL-506 | T32 Self-canary | Story | 1 | EL-502 | Detects its own degradation |
| EL-507 | 🔒 Gate 3 | Gate | 0.5 | EL-504–506 | Noise refused; reward hack caught |

### E6 — M4 Judge, summarization, agent evals *(1 Feb – 19 Feb · ~14 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-601 | T33 Judge grader (single criterion, reasoning first) | Story | 2 | EL-507 | Per-criterion verdicts |
| EL-602 | T34 Cross-family hard assertion | Task | 0.5 | EL-601 | Same-family judge refused |
| EL-603 | T35 Position swap + flip rate | Story | 1 | EL-601 | Flip rate reported; flips count as ties |
| EL-604 | T36 Calibration set + Cohen's κ gate (≥ 0.6) | Story | 2 | EL-601 | Uncalibrated judge can't gate |
| EL-605 | T37 Summarization situation (+ length companion) | Story | 2 | EL-604 | Summaries judged end to end |
| EL-606 | H1 Resettable environment (snapshot restore) | Story | 1.5 | EL-314 | Same task, same start state every run |
| EL-607 | H3/H8 pass^k + always/flaky/never | Story | 1 | EL-606 | Reliability reported per task |
| EL-608 | H4 Cost per successful task | Task | 0.5 | EL-409 | ₹ per success from gateway costs |
| EL-609 | H5/H7 Milestones + trajectory taxonomy (loops, wrong args, premature done) | Story | 1.5 | EL-409 | Failure categories counted from traces |
| EL-610 | H6 Prompt-injection suite (ASR + utility) | Story | 1.5 | EL-410 | Hijack rate measured alongside task success |
| EL-611 | 🔒 Gate 4 | Gate | 0.5 | EL-605, EL-607–610 | Calibrated judge + agent pass^k, no architecture rewrites |

### E7 — Track L: Loop closure + MCP server *(22 Feb – 5 Mar · ~8.5 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-701 | L1 Claim extractor | Story | 1.5 | EL-611 | Typed claims from a real transcript |
| EL-702 | L2 Claim verifier (clean re-run, transcript never used as evidence) | Story | 1.5 | EL-701 | Mocked "passing" suite caught |
| EL-703 | L3 **MCP server:** `report_intent`, `plan`, `evaluate`, `verify_claim`, `findings` | Story | 1.5 | EL-301, EL-008 | An agent calls all five |
| EL-704 | L4 Feedback channel to the agent | Story | 1 | EL-703 | Agent fixes code unprompted |
| EL-705 | L5 Anti-Goodhart guards (held-out cases, oracle-change detection) | Story | 1.5 | EL-704 | Weakening a test gets flagged |
| EL-706 | L6 Failures-as-tests flywheel | Story | 1 | EL-702 | Caught bug becomes a permanent case |
| EL-707 | 🔒 Gate L | Gate | 0.5 | EL-705, EL-706 | Agent contradicted, fixes it, can't game the test |

### E8 — M5 Enterprise *(8 Mar – 9 Apr · ~23.5 days)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-801 | **Plug-in SDK:** stable Protocols for Connector, Sensor, Grader, TechniquePack, Policy + discovery | Story | 2 | EL-707 | A third-party plug-in loads with no core change |
| EL-802 | Custom technique packs (org rules through the same loader + integrity checks) | Story | 1 | EL-801 | An org record plans like a built-in one |
| EL-803 | Org policy file (allowed tools, budgets, data rules) | Story | 1 | EL-801 | Policy overrides enforced |
| EL-804 | Team server mode (shared results, multi-user dashboard) | Story | 2 | EL-803 | Two users see one project's results |
| EL-805 | Workspaces + RBAC | Story | 2 | EL-804 | Viewer can't grant connectors |
| EL-806 | SSO (OIDC, stdlib) | Story | 1.5 | EL-805 | Login through the company IdP |
| EL-807 | Audit export + retention | Story | 1 | EL-805 | Audit log exported; old data purged on schedule |
| EL-808 | T41 CI surface + PR comments | Story | 2 | EL-801 | Absolute + statistical gates on a PR |
| EL-809 | T39 GitHub + Databricks connectors | Story | 2 | EL-801 | Read-only via the envelope |
| EL-810 | T40 Node language adapter | Story | 1 | EL-801 | JS repo graded end to end |
| EL-811 | T42 Extraction situation + perturbation engine | Story | 5 | EL-801 | Field-level scores on perturbed inputs |
| EL-812 | Packaging, install, docs | Task | 1.5 | EL-808 | One-line install on a clean machine |
| EL-813 | Security review + threat model | Task | 1 | EL-805 | Findings closed or accepted |
| EL-814 | 🔒 Enterprise beta | Gate | 0.5 | all E8 | Running at one pilot team |

### E9 — Track X: Screen sensor *(optional, ~2 weeks, only if EL-010 = in)*

| Key | Summary | Type | Est. | Depends on | Done when |
|---|---|---|---|---|---|
| EL-901 | X1 Window-title sensor + denylist | Story | 1 | EL-421 | Titles on the bus; denylisted apps never appear |
| EL-902 | X2 Title → signal rules | Story | 1 | EL-901 | Prod DB client raises safety posture |
| EL-903 | X3 Frame sampler (never persisted) | Story | 1.5 | EL-901 | Duplicates dropped; nothing written to disk |
| EL-904 | X4 Escalation policy | Story | 1 | EL-903 | Budgeted vision calls |
| EL-905 | X5 Measure it | Spike | 1 | EL-904 | Yes/no with numbers. If no, delete the track |

---

## 4. Critical path

```
EL-001..004 → EL-103 → … → EL-123 → 🔒G0 → EL-201 → EL-206 → EL-207 → 🔒G1
   → EL-301 → EL-307 → … → 🔒GV → EL-408 → EL-409 → EL-415 → EL-416 → 🔒G2
   → EL-501 → 🔒G3 → EL-601 → EL-604 → 🔒G4 → EL-703 → 🔒GL → EL-801 → 🔒Beta
```

**Off the critical path, start any time:** EL-202 episodic store, EL-203 statistics, EL-209 LLM client.

---

## 5. Risks to the timeline

| Risk | Impact | Mitigation |
|---|---|---|
| Decisions EL-001 to EL-004 not made this week | M0 stalls at EL-103 | Decide by 7 Oct |
| Gate 0 review finds wrong plans | 2–5 days of rework | Built into M0's buffer; nothing downstream starts until it passes |
| MCP spec changes during the build | Gateway rework | Isolate the protocol in EL-301 |
| Year-end holidays inside E4 | 1 week lost | E4 already carries 1 week of buffer |
| Only one engineer | 27 weeks | A second engineer on Track O cuts about 4 weeks |
