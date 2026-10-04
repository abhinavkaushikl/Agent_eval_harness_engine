# USER_EXPERIENCE.md — EvalLoop

What the developer sees, does and gets. The UX promise:

> **Two clicks per session. Everything else is the agent.**
> Work however you normally work, in any editor and with any AI assistant. Never write an eval.

Items marked *(proposed)* are UX details inferred from the design, not stated explicitly in it. Confirm them before building.

---

## 1. Persona

A developer, often pairing with an AI coding assistant, who wants to know *"is what I'm building actually good, and is that claim real?"* They don't want to learn eval methodology, write test harnesses, or babysit a tool. They will not tolerate a tool that cries wolf.

---

## 2. The session lifecycle

```
 ① START  ──►  work normally (any editor / AI)  ──►  ② STOP  ──►  report
               │
               └── dashboard updates live · notifications on real findings
```

### ① Start
- `evalloop start` (CLI) or **Start** in the dashboard. Starts the session orchestrator, async worker pool and queue.
- Agent takes a git baseline, begins polling, and opens `http://localhost:<port>` *(port proposed)*.
- First screen: "Watching `<repo>` · baseline `<sha>` · branch `<name>`."

### During the session (zero interaction required)
- Agent waits for **coherent** change units and never grades mid-edit.
- Dashboard updates live via SSE, with no page refresh.
- **Permission requests** appear only when a technique needs a tool the agent doesn't have (e.g. `sandbox`, `llm_api_cross_family`, `trace_capture`). One click allows or denies. Denied → technique moves to UNAVAILABLE with the reason.
- **Human-review requests** (ladder rung 5) appear only when nothing lower can decide.
- **Notifications** fire for real findings only, such as a caught bug, a flagged reward hack or a regression. They never fire for noise.

### ② Stop
- `evalloop stop` or **Stop**. Agent drains the queue and writes the session report.
- Report = `summary.md` per run plus a session-level report.

---

## 3. Screens / surfaces

### 3.1 Plan view (the core artifact, readable without explanation)
```
READY        A1_execution_based · A3_deterministic
PENDING      B3_mcnemar        needs discordant_pairs: 25, have 8
             C3_noise_floor    needs runs: 3, have 1
UNAVAILABLE  H7_trajectory     missing: trace_capture
PROHIBITED   accuracy          rare_class: "flag nothing" scores 99.8%
```
Four states, always visible:
| State | Meaning to the user |
|---|---|
| **READY** | Running / ran, in priority order |
| **PENDING** | Applies, but not enough evidence yet. Shows exactly what's missing. |
| **UNAVAILABLE** | Needs a tool or permission the agent doesn't have |
| **PROHIBITED** | Methodology forbids it here, with the reason |

### 3.2 Dashboard (localhost, live HTML + SSE)  *(M2)*
- Session header: repo, branch, duration, change units seen.
- Situation panel: inferred situations with confidence (multi-label).
- Plan view (above).
- Results: per-artifact verdicts by grader rung; INCONCLUSIVE shown distinctly from fail.
- Pending queue with "need 25, have 8" reasons (M3).
- Diagnostics flags: score jump, length bias, ceiling, floor, reward hack (M3).
- Trend lines per field and per slice across runs (journey ledger, M3).
- Self-canary status: "agent healthy / degraded" (M3).

### 3.3 Local API  *(M2)*
`/status`, `/results`, `/pending`. Same data as the dashboard, for scripts and the CLI.

### 3.4 Session report (`summary.md`)  *(M1+)*
1. What you built (situations inferred, with stated intent from transcripts)
2. What was evaluated and how (rung, oracle confidence HIGH/LOW)
3. Findings, including per-item flips **in both directions**
4. What is *not yet* answerable and what would unlock it
5. What was prohibited and why
6. Cost (LLM spend) *(proposed)*

### 3.5 CI surface + PR comments  *(M5)*
Same report condensed into a PR comment; absolute gates for safety/schema, statistical gates for quality.

---

## 4. UX principles

1. **Invisible by default.** No config files, no eval authoring, no prompts to answer unless genuinely needed.
2. **Honest over impressive.** It never says "improved" for a within-noise delta. Pending beats a fake number.
3. **Every "no" has a reason.** PENDING, UNAVAILABLE and PROHIBITED always state why, in plain language.
4. **Quiet notifications.** Interrupt only for things worth acting on.
5. **Editor-agnostic.** Works from disk, git and transcripts, with no editor plugin required.
6. **User controls access.** Tools, credentials and connectors are opt-in via permission requests.
7. **Deterministic output.** Same inputs, same plan, same render, so users can trust diffs.

---

## 5. Acceptance moments (user-visible gates)

| Gate | The user experiences… |
|---|---|
| Gate 0 | Reads 20 rendered plans and agrees with every one |
| Gate 1 | Points it at a toy repo with a broken function; it gets caught with zero instruction |
| Gate 2 | Clicks start, works an hour in any editor, gets a useful session report |
| Gate 3 | It refuses to report a noise-level change as a win, and catches a planted reward hack |
| Gate 4 | Judge-graded summarization works and the architecture is reused without rewrites *(inferred)* |

---

## 6. Open UX questions
- Desktop tray / menubar app vs CLI + browser for the "two clicks"?
- Notification channel: OS notifications, terminal bell, or dashboard only?
- Where human-review items live when the dashboard isn't open?
- Session report location (repo `.evalloop/` vs user home)?
