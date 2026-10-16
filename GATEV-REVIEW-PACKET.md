# 🔒 Gate V — Review Packet

**For the human reviewer. Read this and agree, or send it back.** This is not a code ticket. It is
the evidence that EvalLoop can discover a real database and a real vector store, obtain consent,
connect **read-only**, and validate against them — unprompted and safely. Every number and transcript
below is verbatim output from running the **already-built** `evalloop` code against the
`gatev-sample/` repo. No product code was written or changed to produce it, and no finding it raises
was fixed. The driver that produced it calls built functions only; it is reproducible (see §9).

**Gate V done-when (from the board):** *DB + vector store discovered and validated unprompted.*

---

## 0. The one-paragraph verdict (read this, then decide whether to read the rest)

EvalLoop **does** discover both systems with file:line provenance, classify a production endpoint as
dangerous and refuse it without a typed name, connect to a real database **read-only** with an audit
log that proves zero writes, reject a `DROP TABLE` before it reaches the wire, validate SQL by
execution-match (reordered JOINs pass, a hallucinated column hard-fails), and report RAG stage by
stage with recall@k gating faithfulness through the **readiness** mechanism, not the dead `unlocks`
edge. The oracle passed at 100%, so the harness is sound and these results mean what they say. **It
is weakest in three honest places, none of which the green hides:** (1) only the **SQLite** database
was connected to a live backend — Postgres was discovered and classified but never opened (no live
server in this environment), and the **vector store was exercised over a loopback HTTP server
speaking Qdrant's protocol, not the Qdrant binary**; (2) **faithfulness was scored by a lexical
judge double, not M4's calibrated cross-family judge** (M4 has not landed), so the faithfulness
*numbers* demonstrate the plumbing, not a trustworthy measurement; (3) the recall→faithfulness
ordering is enforced **by `requires` at readiness-check time, but nothing in this slice forces a
runner to consult readiness before calling the grader** — the gate is correct, its automatic
enforcement is not yet wired. My recommendation: **conditional pass** of the safety-and-discovery
spine; **do not** read the RAG faithfulness numbers as validated until M4 and a readiness-enforcing
runner exist.

---

## 1. The oracle first (E6) — if this is not 100%, everything below is void

Per the instruction, the oracle ran **before** any claim: a known-correct SQL statement and a
known-good RAG retrieval + answer pushed through the *same* pipeline. If a thing known to be right
does not score 100%, the harness is broken and the gate is void regardless of anything else.

```
0. ORACLE (E6) — a known-correct SQL and a known-good RAG answer. Must be 100%.
  known-correct SQL      -> PASSED       (result set matches reference (2 rows, multiset))
  known-good retrieval   -> recall@3 1.000 (must be 1.000)
  known-good faithfulness-> mean 1.000 (must be 1.000; judge κ=0.74 ≥ 0.6)

  ORACLE VERDICT: PASS — harness is sound, gate may proceed
```

**Oracle passed.** The pipeline scores a known-correct artifact at 100% on all three axes. The gate
may proceed. (Caveat carried forward: the faithfulness oracle used the same lexical judge double as
§5; it proves the grader returns 100% on an entailed claim, not that a real judge would.)

---

## 2. Discover → consent → read-only probe → validate (verbatim, zero instruction)

EvalLoop was pointed at `gatev-sample/` with no further input. Discovery opens nothing; it reads
config and reports every endpoint with a real `file:line` and a plain-language reason.

```
2. DISCOVER (file:line provenance) — zero instruction, nothing opened
  [database    ] configured via .env key DATABASE_URL
      provenance : .env:3  (.env:3 sets DATABASE_URL)
      posture    : unknown  default_deny=True typed_confirm=False
  [vector_store] configured via .env key QDRANT_URL
      provenance : .env:4  (.env:4 sets QDRANT_URL)
      posture    : unknown  default_deny=True typed_confirm=False
  [vector_store] configured via .env key QDRANT_COLLECTION
      provenance : .env:5  (.env:5 sets QDRANT_COLLECTION)
      posture    : unknown  default_deny=True typed_confirm=False
  [database    ] configured via .env key PROD_DATABASE_URL
      provenance : .env:8  (.env:8 sets PROD_DATABASE_URL)
      posture    : production_suspected  default_deny=True typed_confirm=True
  [database    ] create_engine(...) call site in app/db.py
      provenance : app/db.py:12  (app/db.py:12 calls create_engine(...))
      posture    : unknown  default_deny=True typed_confirm=False
  [database    ] postgres service 'postgres' in docker-compose.yml
      provenance : docker-compose.yml:2  (docker-compose.yml:2 defines service 'postgres')
      posture    : local  default_deny=False typed_confirm=False
  [vector_store] qdrant service 'qdrant' in docker-compose.yml
      provenance : docker-compose.yml:8  (docker-compose.yml:8 defines service 'qdrant')
      posture    : local  default_deny=False typed_confirm=False
```

Both a database and a vector store were found, from three independent kinds of evidence (`.env`,
a Python call site, `docker-compose.yml`), each carrying provenance. The consent step then opened
the one backend that needs no server or credential — the real SQLite dev DB — **read-only**:

```
2b. CONSENT + READ-ONLY PROBE + VALIDATE — the real SQLite dev DB
  granted + probed: sqlite file reachable, query_only=on
  read-only (probe + audit): True
  table customers: id:INTEGER, name:TEXT, country:TEXT
  table orders: id:INTEGER, customer_id:INTEGER, total:INTEGER, status:TEXT, refund:INTEGER
```

**Weakness, stated plainly (see §8):** the Postgres and Qdrant services were *discovered and
classified* but not *connected*, because there is no live Postgres or Qdrant server in this
environment. The live read-only connection is proven against SQLite (a genuine, driverless database)
and, for the vector store, against a loopback HTTP server speaking Qdrant's protocol (§5).

---

## 3. The safety envelope, proven

### 3a. A generated `DROP TABLE` is rejected before transmission

The write is fed to the envelope with a **recording executor** that logs any call. If the executor
is never called, the statement never reached the wire.

```
3a. A generated DROP TABLE is rejected BEFORE transmission
  ReadOnlyViolation: statement 0 is schema/permission-changing (DROP); it never reaches the wire
  executor.run called? False  -> the write never reached the wire
```

Layer 1 (`reject_writes`) raised before layer 2/3 ran; the executor was never invoked.

### 3b. Zero writes against any live schema

The audit log over the SQL validation run, by statement kind:

```
3b. Audit log over the whole validation run — zero writes against any live schema
  statements executed: 2   kinds seen: ['read']
  any write/DDL kind?  False
```

Every statement that reached the backend was a `read`. No `write`/`DDL` kind appears.

### 3c. A production endpoint is refused without the typed name

The `PROD_DATABASE_URL` endpoint from §2, classified `production_suspected`:

```
3c. A production-looking endpoint is refused without the typed name
  endpoint: .env:PROD_DATABASE_URL
  posture : production_suspected  (reason: its name contains 'prod', which usually means production)
  wrong typed name 'yes'        -> confirmed? False
  empty typed name ''           -> confirmed? False
  exact name typed              -> confirmed? True
```

A wrong or empty confirmation is refused; only the exact endpoint name unlocks it.

---

## 4. SQL validated by execution match (result sets, never text)

```
4. SQL validated by EXECUTION MATCH (result sets, never text)
  reordered JOIN (same result) -> PASSED       (result set matches reference (2 rows, multiset))
  hallucinated column o.discount-> FAILED       [unknown_column] (hallucinated column: no such column: o.discount)
  pass rate over decided: 1/2  interval=Interval(estimate=0.5, lower=0.0945, upper=0.9055, confidence=0.95, method=wilson)
```

- A query with its JOINs written in the opposite order returns the same rows and **passes** — text
  differs, result set matches, so correctness is on the result set.
- A query referencing a non-existent column `o.discount` **hard-fails**, classed `unknown_column`
  (schema-grounding read from the DB's own error), not a soft "looks wrong."
- The pass rate carries its Wilson interval, which at n=2 is appropriately enormous
  `[0.09, 0.91]` — the harness refuses to pretend two cases are a measurement.

---

## 5. RAG, stage by stage — faithfulness gated behind recall@k by readiness, not `unlocks`

### 5a. The gate is `requires`, checked at readiness time

The faithfulness record's readiness is evaluated with and without the recall fact:

```
5a. Faithfulness is gated by recall@k through READINESS (requires), not the unlocks edge
  evidence WITHOUT recall fact (recall_at_k_measured absent): met=False
      reason: needs recall_at_k_measured: true, have false; claim_labels: 150, have 0

  recall@3 = 1.000 [0.510, 1.000] (embedding: BAAI/bge-small-en-v1.5; 4/4 gold passages, 95% wilson)
  evidence AFTER recall ran (recall_at_k_measured present): met=False
      reason: needs claim_labels: 150, have 0
```

**This is the single most important thing to read carefully, and it is exactly the spot the brief
warned about (F8).** The ordering is real: before recall ran, readiness fails on
`recall_at_k_measured: true, have false`; after recall@k is measured, **that clause disappears from
the reason** — recall satisfied its gate. The gate is enforced by the record's `requires`, read by
`evaluate_readiness`, **not** by the `unlocks` edge (which no planner step reads). Confirmed working.

**But two honest findings sit right here:**

1. **Faithfulness has a *second* readiness bar that recall@k does not clear:** `claim_labels: 150`
   (the corpus F-section's 150–200 gold labels for a trusted judge). In this run that bar is never
   satisfied (`have 0`), so faithfulness is **PENDING even after recall passes**. This is *correct*
   behaviour — faithfulness genuinely needs both — but it means "faithfulness is gated behind
   recall@k" is only half true: recall@k is necessary, not sufficient.

2. **Nothing forces a runner to consult readiness before grading.** §5b below shows the
   `faithfulness(...)` grader returning a *measured* result (mean 1.000) **while readiness says
   `met=False`**. The grader function and the readiness gate are separate; there is no integrated
   RAG runner in this slice that refuses to call the grader until readiness passes. `evidence_after`
   makes the recall fact available for readiness, but the discipline is the caller's. A reviewer
   must not read a measured faithfulness number as "readiness-approved" — it is not, here.

### 5b. Every stage on its own line — there is deliberately no blended score

```
5b. Every RAG stage on its own line — no blended score
MEASURED  oracle_ceiling: generation_accuracy_given_gold=0.750 [0.301, 0.954]
MEASURED  attribution: not_retrieved=0.500 [0.095, 0.905], ranked_beyond_k=0.000 [0.000, 0.658], misread=0.500 [0.095, 0.905]
MEASURED  faithfulness: mean_faithfulness=1.000 [0.342, 1.000], answers_with_unsupported_claim=0.000 [0.000, 0.658]
MEASURED  distractor_robustness: accuracy_with_distractors=0.750 [0.301, 0.954]
MEASURED  unanswerable: false_answer_rate=0.000 [0.000, 0.658], over_abstention_rate=0.500 [0.095, 0.905]
MEASURED  citation: citation_precision=0.667 [0.208, 0.939], citation_recall=1.000 [0.342, 1.000]
```

Every stage reports separately, every number carries its Wilson interval, and there is no single
"RAG score." Unanswerable is split into false-answer *and* over-abstention; citation into precision
*and* recall — the corpus's refusal to average away a failure.

### 5c. A same-family judge is refused (self-preference) — the other warned-about spot

```
5c. Same-family judge is refused (self-preference)
  generator=anthropic, judge=anthropic -> status=pending
     (the judge family 'anthropic' matches the generator's; faithfulness needs a CROSS-family judge)
```

When the judge family matches the generator's, faithfulness refuses to score. (The numbers in §5b
used a cross-family judge double, `anthropic` judging `openai`, κ=0.71 ≥ gate 0.60.)

---

## 6. A negative control and a false negative

### 6a. Negative control — correct work is not flagged

```
6a. Negative control — a CORRECT query and a FAITHFUL answer are NOT flagged
  correct query            -> PASSED (result set matches reference (1 rows, multiset))  [not flagged]
```

A query identical in result to the reference passes; the harness does not cry wolf.

### 6b. A false negative, shown — not hidden

```
6b. False negative — a WRONG boundary passes when the distinguishing row is absent
  WITH distinguishing row (order 204, refund=5000):    FAILED (wrong rows: generated returned 2, reference 1)  <- caught
  WITHOUT it:                                          PASSED (result set matches reference (1 rows))  <- FALSE NEGATIVE
```

A wrong query (`refund >= 5000` where the reference is `refund > 5000`) differs from the reference
**only** on a row where `refund == 5000`. With the distinguishing row (order 204) seeded, the wrong
query is **caught**. Without it, the wrong query **passes — a false negative**. The defect is not in
the grader; it is the limit of execution-match: a pass is only as strong as the distinguishing rows
in the fixture (corpus A:36). **Reviewer action:** for every reference query, confirm a boundary row
exists that separates it from its likely wrong neighbour, or an execution-match pass means less than
it looks.

---

## 7. Findings ledger (EL-301 → EL-314) and cost

Status from the E3 board and each ticket's report. "Built ahead of 🔒 Gate 1" applies to all — Gate 1
is written but **awaiting human sign-off**, so this entire track rests on an unsigned gate.

| Ticket | What | Status | Exercised in this packet |
|---|---|---|---|
| EL-301 | MCP protocol core (JSON-RPC, stdio) | ✅ report | indirectly (client seam) |
| EL-302 | Capability broker (grants/consent/expiry) | ✅ report | §2b, §3c grants |
| EL-303 | Connector discovery + provenance | ✅ report | **§2** |
| EL-304 | Production-suspected classification | ✅ report | **§3c** |
| EL-305 | Read-only envelope + audit log | ✅ report | **§3a, §3b** |
| EL-306 | Connector protocol + SQLite | ✅ report | **§2b, §4, §6** |
| EL-307 | MCP client connector | ✅ report | boundary only (§8) |
| EL-308 | Postgres/MySQL over CLI | ✅ report | discovered not connected (§8) |
| EL-309 | Vector store (Qdrant over HTTP) | ✅ report | **§5** via loopback stand-in |
| **EL-310** | **File + prompt-registry connectors** | **❌ not built (no report)** | not exercised |
| EL-311 | SQL execution grading | ✅ report | **§1, §4, §6** |
| EL-312 | RAG recall@k + faithfulness gate | ✅ report | **§5a** |
| EL-313 | RAG ladder stages (separate) | ✅ report | **§5b** |
| EL-314 | End-state verification | ✅ report | not in this packet's path |
| EL-315 | 🔒 Gate V | this packet | — |

**Cost.** This run made **zero external/model calls** (`$0.00`). The SQL and recall paths touch only
local SQLite and a loopback socket; the judges are in-process doubles, so no judge API was billed.
The only quantities produced are statistical, and **every one carries its 95% Wilson interval**
(shown in §4–§6). The honest cost caveat: a *real* faithfulness run would bill M4 judge calls per
claim — that cost is **not** measured here because that judge does not yet exist.

---

## 8. Where this is weakest (a green Gate V you do not understand is worse than a red one)

1. **Only SQLite was connected to a live backend.** Postgres was discovered and classified but never
   opened (no server). The vector store was exercised against a **loopback HTTP server speaking
   Qdrant's wire protocol**, through the real `QdrantConnector` and its envelope — faithful at the
   protocol boundary, but **not the Qdrant binary** and not over a network. The read-only, audit, and
   provenance guarantees are proven; "works against your actual production Postgres/Qdrant" is **not**
   proven by this packet.
2. **Faithfulness numbers are plumbing, not measurement.** The judge is a lexical entailment double.
   Real faithfulness needs M4's calibrated, cross-family judge (κ gate), which has not landed. §5b's
   `mean_faithfulness=1.000` demonstrates the grader wiring; it is **not** a trustworthy faithfulness
   score. Do not cite it as one.
3. **The recall→faithfulness gate is correct but not auto-enforced.** The ordering lives in `requires`
   and readiness reads it (§5a) — the `unlocks` edge is correctly *not* the mechanism. But no runner
   in this slice forces "check readiness, then grade," and the grader will compute when called
   directly (§5b, measured while `met=False`). EL-312's report claims the RAG runner must set the
   recall fact only after recall runs and let readiness gate; **that runner is not demonstrated here.**
4. **The MCP boundary is correct — verified, not assumed.** A search for a server exposing
   `evaluate` / `verify_claim` / `findings` returns nothing; `mcp_connector.py` is a **client** that
   routes every call through the envelope before it leaves the process, and its own docstring states
   the server is gated behind Gate 3 (EL-008). This is the right call and it holds. The residual risk
   is simply that the *client* was exercised only at its seam in this packet, not against a live
   external MCP server.
5. **EL-310 is not built**, and the whole track sits on an **unsigned Gate 1**. Neither blocks the
   Gate V done-when ("DB + vector store discovered and validated unprompted"), but a green here does
   not mean the track is complete.

---

## 9. Reproduce it

The evidence driver calls only built `evalloop` code against `gatev-sample/` and the loopback
stand-ins; it writes nothing into `evalloop/`. From the repo root, with the venv active:

```
PYTHONPATH=. python gatev_gate.py
```

(The driver sits at the repo root, **not** inside `gatev-sample/`, so it is not part of the fixture
repo that discovery scans — discovery is pointed at `gatev-sample/` only. Nothing in the sample was
softened to make the gate pass — the production endpoint, the hallucinated column, and the
false-negative boundary are all there on purpose.)

---

## 10. Recommendation

**Conditional pass.** The Gate V done-when is met: a database and a vector store are discovered with
provenance and validated unprompted, read-only, with the safety envelope proven. Grant the gate on
the **discovery + consent + read-only + SQL-execution** spine. **Withhold** trust in the RAG
faithfulness *numbers* and the live-remote-connector claim until: (a) M4's calibrated cross-family
judge lands, (b) a RAG runner enforces readiness-before-grade, and (c) the connectors are run once
against a live Postgres and a live Qdrant. If you disagree with the conditional framing — in
particular if you read finding §8.3 as a blocker rather than a condition — send it back and I will
re-run with whatever additional evidence you name.
