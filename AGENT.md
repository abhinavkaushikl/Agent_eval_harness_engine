# AGENT.md — The EvalLoop Backend Agent

This describes the autonomous agent that runs between **START** and **STOP**: what it observes, how it decides, and how it stays honest. It is the target design across all milestones. M0 builds only the Classifier→Planner "brain" in pure, non-executing form.

---

## 1. Mission

Observe a developer's work, infer what is being built, pick the right evaluations from a codified methodology, run them, and report **statistically honest** results. The developer writes no evals.

Two principles override everything else:
1. **Picking the wrong evaluation is the most expensive mistake.** So the decision core is built and verified first.
2. **Never claim more than the evidence supports.** Every check has a readiness threshold. Below it, the agent reports *pending, with the reason* and does not guess.

---

## 2. Pipeline

```
● START ─────────────────────────────────────── ■ STOP
                 │
┌───────────────────────────────────────────────┐
│ CAPTURE                                       │
│ poller (1Hz stat+hash) · git state · AI       │
│ transcripts on disk · shell · runtime traces  │
└───────────────────────────────────────────────┘
                 │
        event buffer → debounce
                 │
┌───────────────────────────────────────────────┐
│ COHERENCE DETECTOR                            │
│ "is this change complete enough to judge?"    │
└───────────────────────────────────────────────┘
                 │
┌───────────────────────────────────────────────┐
│ CLASSIFIER   heuristics → LLM only if unclear │
│ → [(situation, confidence), ...]  multi-label │
└───────────────────────────────────────────────┘
                 │
┌───────────────────────────────────────────────┐
│ PLANNER                                       │
│ registry.match(situations) → ordered evals    │
│ readiness gate → ready | pending              │
│ capability check → permission request         │
└───────────────────────────────────────────────┘
                 │
┌───────────────────────────────────────────────┐
│ ORACLE LAYER                                  │
│ harvest existing (HIGH) → author new (LOW)    │
└───────────────────────────────────────────────┘
                 │
┌───────────────────────────────────────────────┐
│ GRADER LADDER     (parallel across artifacts) │
│ 1 execution · 2 end-state · 3 deterministic   │
│ 4 judge · 5 human                             │
└───────────────────────────────────────────────┘
                 │
┌───────────────────────────────────────────────┐
│ STATISTICS → DIAGNOSTICS                      │
│ CI · noise floor · McNemar   jump · length    │
│ bootstrap · Wilson           ceiling · floor  │
└───────────────────────────────────────────────┘
                 │
┌───────────────────────────────────────────────┐
│ MEMORY    metric (JSONL) · episodic (SQLite)  │
│           cases: generated | permanent        │
└───────────────────────────────────────────────┘
                 │
dashboard (localhost) · session report · notifications
```

---

## 3. Components

### 3.1 Capture  *(M2)*
- **Poller:** walks the working tree at ~1 Hz using `stat` + content hash and is gitignore-aware. It is our own implementation, with no watchdog or third-party watcher. Target: detects changes across 5k files in < 20 ms.
- **Git state reader:** baseline, staged, committed, branch.
- **AI transcript reader:** reads AI-assistant transcripts on disk (e.g. Claude Code JSONL) to extract the developer's *stated intent*.
- **Shell + runtime traces:** commands run, outputs, traces when available.

### 3.2 Event buffer + debouncer  *(M2)*
Collapses bursts of file events into single change units.

### 3.3 Coherence detector  *(M2)*
Asks "is this change complete enough to judge?" It fires on complete units, never mid-edit. It prevents grading half-written code.

### 3.4 Classifier  *(M1 heuristics, LLM fallback later)*
- Heuristics first (Python-only at M1). An LLM is called **only if heuristics are unclear**.
- Output is multi-label: `[(Situation, confidence), …]`.
- Done-when (M1): correctly labels 10 sample files.

### 3.5 Planner — "The Brain"  *(M0)*
Pure function. Runs nothing.

**Where `records` come from.** The codified methodology is the corpus committed at
`knowledge rules/` — one flat directory, the master lookup plus ten deep dives
(decision `decisions/EL-001-corpus-location.md`). It is read at **authoring time**,
when records are extracted and enriched, not at runtime: the agent loads
`TechniqueRecord`s from `evalloop/registry/records/`, never from Markdown. Each record
carries a `source_ref` back into the corpus, so every threshold is traceable to a file
that exists in the tree. Corpus filenames are declared once, in `tests/conftest.py`;
a missing or renamed corpus file fails the suite by name rather than skipping.

```python
plan(records, situations, available_tools, evidence) -> Plan
```

**Resolution order** (fixed, deterministic):
1. `match` records whose `triggers_on_situation` intersects the input (multi-label merges without duplication)
2. Apply `constraint` records. Anything they prohibit is removed from `ready` and listed in `prohibited` with the reason.
3. Capability check → `unavailable` (id → missing tools)
4. Readiness check → `pending` (id → unmet-requirement reason)
5. Apply `conflicts_with`. A higher-priority grader suppresses a conflicting lower one (execution suppresses judging the same property).
6. Resolve `companion_checks`. If a record is ready, its companions must also appear.
7. Order deterministically: graders by `ladder_priority` ascending, then non-graders grouped by `type`, then `id` alphabetically.

```python
@dataclass(frozen=True)
class Plan:
    ready: tuple[TechniqueRecord, ...]
    pending: Mapping[str, str]                 # id -> unmet-requirement reason
    unavailable: Mapping[str, tuple[Tool, ...]]  # id -> missing tools
    companions: Mapping[str, tuple[str, ...]]
    prohibited: tuple[str, ...]                # constraint records that fired
    def render(self) -> str: ...               # human-readable pending-queue view
```

**Readiness:** `evaluate_readiness(record, evidence) -> Readiness(met: bool, reason: str | None)`
- Empty `requires` → always met.
- Missing evidence counts as zero/absent.
- Reason format: `"needs <key>: <threshold>, have <actual>"`.
- Boolean requirements (e.g. `requires_pre_instrumentation`) are handled distinctly from numeric thresholds.

**Capability:** `check_capability(record, available_tools) -> Capability(available: bool, missing: tuple[Tool, ...])`. When a tool is missing, the session-level agent turns it into a **permission request** to the user. It does not silently skip.

### 3.6 Oracle layer  *(M1)*
- **Harvest existing (HIGH confidence):** existing tests, schemas, type hints in the repo.
- **Author new (LOW confidence):** tests generated from signature only, in isolation from the implementation. These are tagged LOW so they are never confused with ground truth.

### 3.7 Grader ladder  *(M1, M4)*
Always prefer the highest rung that can answer the question:
1. **Execution:** sandboxed run, hidden-test isolation, partial credit, compile vs logic split.
2. **End-state:** verify resulting state (agents, DB, files).
3. **Deterministic:** schema / regex / exact match, plus a cascade hook.
4. **Judge (LLM):** single-criterion, named categories, reasoning-first. Must be **cross-family** (hard assertion in router), with position swap + flip-rate tracking, and calibrated with Cohen's kappa where `kappa_manual ≥ 0.6` is a runtime gate.
5. **Human:** queued for the developer when nothing lower can decide.
6. **Distilled:** classifier distilled from judge/human labels.

Runs parallel across artifacts. Sandbox: subprocess + rlimits + timeout + tempdir, where timeout → **INCONCLUSIVE** (never pass/fail).

### 3.8 Statistics → Diagnostics  *(M1 stats, M3 diagnostics)*
- **Statistics:** Wilson interval, bootstrap, cluster bootstrap, McNemar, permutation test, noise floor, power. Rules of thumb kept verbatim: `margin ≈ 100/√n` (B5), `n ≈ 16·p(1−p)/δ²` (C2), noise floor from `k ≥ 5` repeat runs (C3; `k = 3` is for daily iteration only).
- **Diagnostics:** E1 score jump, E3 length bias, E5 ceiling, E6 floor, reward-hacking detection.
- **Honesty layer (M3):** readiness gate + pending queue, noise floor across repeat runs (refuses to call a within-noise delta an improvement), per-item diff (flips in both directions), journey ledger + trends, **self-canary** (detects its own degradation on a fixed known-answer set).

### 3.9 Memory  *(M1)*
- **Metric store:** JSONL with full schema from day one. Two runs can be diffed per case.
- **Episodic store:** SQLite. Situation decisions *and the reasoning* are persisted.
- **Cases:** `generated` (ephemeral) vs `permanent` (promoted, e.g. failures-as-tests).
- **Content-hash cache:** an unchanged diff is never re-evaluated.

### 3.10 Outputs  *(M1–M2)*
Markdown `summary.md` per run, live localhost dashboard (HTML + SSE), session report, notifications. See `USER_EXPERIENCE.md`.

---

## 4. Cross-cutting: Capability layer

One place owns:
- **LLM routing by job:** `classify` / `author` / `judge` / `diagnose`. Hard rules for judges: a judge must be from a **different model family** than the generator.
- Tool + MCP connections (MCP client in M5). **Transports live here, never in the `Tool` enum.** A record requires
  `db_connection`, not the wire used to reach it; this layer decides whether that is satisfied by a local socket or
  an MCP server, and `mcp_client` / `mcp_gateway` are grant kinds here rather than vocabulary members
  (decision `decisions/EL-002-mcp-tools-in-enum.md`).
- Credentials
- Cost tracking
- Rate limits
- LLM client is stdlib HTTP with retry + backoff. No SDK wrappers.

---

## 5. Non-negotiable agent behaviours

| Rule | Why |
|---|---|
| Never invent a threshold; use the source value or `null` | Fabricated rigor is worse than none |
| Every threshold traces to a `source_ref` that resolves in `knowledge rules/` | An unresolvable citation is an invented number with extra steps |
| Below readiness → `pending` with "need X, have Y" | Honest about what can't be answered yet |
| Never accuracy on a rare class | Constraint record; "flag nothing" scores 97% at 3% prevalence (D:32, D:45) |
| Never same-family judging | Self-preference bias |
| Any judge score is reported with output length | Length bias companion |
| Violation rate always reported with over-refusal rate | Never alone |
| Precision only at a stated recall level | Otherwise meaningless |
| Retrieval recall@k before faithfulness (RAG) | Build order from G |
| Resettable environment before any agent eval (H) | Otherwise non-reproducible |
| Execution beats judging when execution is possible | A's ladder |
| Within-noise delta is never an "improvement" | Noise floor |
| Timeout = INCONCLUSIVE | Not a failure, not a pass |
| Missing tool → ask permission, don't skip silently | User stays in control |
| Self-canary every session | The agent must detect its own drift |
