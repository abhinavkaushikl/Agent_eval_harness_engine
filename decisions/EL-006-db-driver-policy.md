# EL-006 — Postgres and MySQL connectivity policy

## Decision

**The connection mechanism is resolved at runtime, not fixed in advance.** A connector asks the capability broker for a database mechanism; the broker probes what the machine already has, picks the best available by a fixed preference order, and when nothing is available it **asks the user for permission to install a driver**, installs it into an EvalLoop-owned isolated runtime on approval, and retries once. On refusal, or where installation is impossible, the capability returns `UNAVAILABLE` naming what is missing and how to supply it.

The preference order is fixed even though the mechanism is not:

| | Mechanism | Condition | Why here |
|---|---|---|---|
| 1 | **Native Python driver already importable** | `psycopg` / `mysqlclient` or `PyMySQL` resolves in the runtime | Best result fidelity, and zero friction because nothing is installed |
| 2 | **CLI client already on `PATH`** | `psql` / `mysql` runs | Zero friction, and inherits TLS, Kerberos, IAM and SSH config the developer already has working |
| 3 | **Consent-gated driver install → retry** | user approves a named, pinned package | Recovers fidelity when neither 1 nor 2 exists |
| 4 | **`UNAVAILABLE`** | refused, offline, or non-interactive | Fail safe and explain |

Two invariants hold regardless of which rung is used, and they are what make the flexibility safe: **the EL-305 read-only envelope sits above the mechanism, so there is exactly one code path to any database**, and **every mechanism normalises into one canonical typed row form**, so results are comparable across mechanisms and EL-311 does not inherit the transport's formatting quirks.

`pyproject.toml` is **not** modified by this decision: `dependencies` stays `[]`. A driver is a *consent-acquired runtime capability*, not a declared install-time dependency — see `## The dependency question` for why that distinction is real rather than a dodge, and for the `CLAUDE.md §3` amendment this policy requires.

## Status

Decided — policy only, four months ahead of EL-308 — 2026-10-06.

**Supersedes the earlier CLI-only draft of this decision** (same date), which fixed the mechanism as subprocess `psql`/`mysql` and ruled a driver permanently out. That draft's safety analysis survives almost intact and is reused below; what changes is that the mechanism became a runtime choice with a consent-installed fallback, and that the driver path is now the preferred one when it is available. No code was written.

## Context

`CLAUDE.md:43` permits the standard library only in shipped code, naming NumPy as the one external dependency that may ever be permitted. `psycopg`, `mysqlclient` and `PyMySQL` are all third-party, so none is available as a declared dependency.

The decision sits beneath the safety architecture, which is why mechanism flexibility is tractable at all. `ARCHITECTURE.md:276` places the connector layer in `evalloop/connect/`, depending on the capability broker (`evalloop/capability/`). Discovery (EL-303), `production-suspected` classification (EL-304) and the read-only envelope (EL-305) all run before a byte reaches the mechanism, and `ARCHITECTURE.md:194` fixes the order as `DISCOVER → PROPOSE → CONSENT → PROBE (read-only envelope)`. So the mechanism question is about **result fidelity and installation friction**, not about whether the database is protected — that is settled independently, and must stay settled whichever rung is taken.

## Options considered

Evaluated on reliability, security, result fidelity, maintainability, installation requirements and fit.

| Option | What it costs | What it buys | Install / dependency implication | Verdict |
|---|---|---|---|---|
| **Native Python driver** (`psycopg` 3, `mysqlclient` or `PyMySQL`) | A third-party package must be present. `psycopg[binary]` and `mysqlclient` carry compiled artifacts; `mysqlclient` needs a C toolchain or `libmysqlclient` unless a wheel matches. Two more CVE feeds. `mypy --strict` and `pytest` must still pass with the package absent, which forces a typed Protocol boundary and fakes | **Highest fidelity, and fidelity is the criterion that matters most here.** Typed values, so `NULL` is `None` and unambiguous; real bind parameters; `Decimal` for exact numerics; streaming cursors; pooling; machine-readable SQLSTATE; session and transaction continuity across calls | Declared dependency: **not acceptable** (`CLAUDE.md:43`). Consent-installed runtime capability: **acceptable**, and is how it is used here | **Chosen as rung 1 and rung 3** |
| **Subprocess CLI** (`psql`, `mysql`) | Everything arrives as text, so types are recovered from catalog metadata. No bind parameters, no pooling, no streaming cursors, no cross-call transaction. MySQL batch output cannot distinguish `NULL` from the string `'NULL'` (see below) — a genuine fidelity defect, not a nuisance | Frequently already installed, so no consent prompt and no install. Inherits TLS, Kerberos, IAM, SSH tunnels, `~/.pgpass` and `my.cnf` for free. One process per query is trivially killable and sandboxable. Zero maintenance and no CVE surface we own | **None.** Nothing is installed and nothing is imported | **Chosen as rung 2** |
| **Bundled pure-Python wire protocol** | Weeks of work for the Postgres v3 and MySQL protocols, then permanent maintenance of authentication (SCRAM-SHA-256, `caching_sha2_password`), TLS, type OIDs and protocol revisions. Every defect is ours, in code that talks to customer databases | Driver-grade fidelity with no external package and no install prompt. Fully self-contained | None, which is its whole appeal | **Rejected.** `ARCHITECTURE.md:221` — "Weeks of work and a permanent maintenance liability. No." The security argument is decisive on its own: hand-rolled authentication and TLS against production databases is the last code this project should own, and a consent-installed, widely-audited driver is strictly safer than a bespoke one |
| **MCP database server** (EL-307) | Requires a server to exist and be configured; fidelity is whatever the server exposes, typically JSON-shaped text | Reuses EL-301 and needs no database-specific code at all | None beyond EL-301 | **Out of scope here,** and deliberately so: EL-307 already covers it, and the ticket excludes MCP-era code from M0. Worth noting as a future rung 2.5 once EL-307 lands |

The pure-Python protocol is the only option rejected outright. The other three are complementary rather than competing, which is the substance of this decision.

## The dependency question

The directive is to stop treating a driver as permanently forbidden, and `CLAUDE.md:43` as written does forbid it. That contradiction should be resolved explicitly rather than left for EL-308 to discover, so here is the distinction the policy rests on:

- A **declared dependency** is one in `pyproject.toml`. It installs for every user whether they touch a database or not, it must exist for the package to import, and it is what `CLAUDE.md:43` is protecting against. This policy adds none.
- A **consent-acquired runtime capability** is a package the shipped code never imports unconditionally, which lives in an EvalLoop-owned directory outside the user's environment, which the user explicitly approved, and whose absence is a normal, handled outcome.

Three testable properties keep the second honest, and EL-308 should be gated on them:

1. `pip install evalloop` installs nothing third-party; `dependencies` remains `[]`.
2. `pytest` and `mypy --strict evalloop/` both pass with **zero** third-party packages present, exercising the driver path through fakes behind a Protocol. Real-driver tests are opt-in and marked.
3. No import of a driver at module scope anywhere in `evalloop/`; resolution is behind the broker.

This is materially weaker than "stdlib only" and should not be presented as compliant with §3 as written. The required amendment is in `## Follow-up`; **it should be applied before EL-308 starts**, because an unamended §3 plus this policy means the first person to implement rung 3 is violating a hard constraint.

## How the chosen approach works

Five things EL-308 inherits as a contract.

### 1. Unavailable mechanism: detection, the permission request, and `UNAVAILABLE`

**Detection** runs at probe time, before any connection attempt, and never by a bare import. A driver is tested with `importlib.util.find_spec` against the EvalLoop runtime, which avoids executing module-level side effects; a CLI is tested with `shutil.which` and then an actual `--version` run with a short timeout, because `which` also succeeds on a broken symlink or an unexecutable wrapper. Results are cached per session, so a missing mechanism is reported once rather than once per technique, and the outcome of the ladder is recorded as provenance (below).

**The permission request** is a broker grant, not an ad-hoc prompt, so it inherits EL-302's consent record, scope and expiry. It must state the package name and pinned version, the resolved hash, the exact directory it will be written to, that the user's project environment and `site-packages` are untouched, and which techniques become runnable if approved. It is a plain yes/no — EL-304's type-to-confirm is reserved for `production-suspected` endpoints, which is a different and more dangerous act than installing a library. A decision is remembered for the project so the question is asked once, not every session.

**On approval** the broker creates or reuses an isolated runtime (`python -m venv` under an EvalLoop-owned directory, mode `0700`), installs the pinned version with hash checking, re-probes, and retries the connection **once**. A failed install is terminal for the session and reported as the install error, not as a connection error. **On refusal, offline, or non-interactive** the capability returns `UNAVAILABLE`. Non-interactive contexts default to **deny** without prompting, because a CI run must never block on a question, and an org policy file (EL-803) may pre-authorise or forbid installs outright.

```
UNAVAILABLE  db_connection (postgres)
  tried:     psycopg      not importable in the EvalLoop runtime
             psql         not found on PATH
             install      declined by you on 2026-12-09 (remembered for this project)
  to enable, either:
    install a client    macOS   brew install libpq && brew link --force libpq
                        Debian  apt install postgresql-client
                        RHEL    dnf install postgresql
    or re-run and approve the one-time install of psycopg[binary]==<pinned>
                        into ~/.evalloop/runtime/ — your project environment is not touched
  dropped:   A1_execution_based, V8 SQL validator — not planned this session
```

Four properties matter more than the layout: it lists **every rung that was tried** and why each failed, so the user can see the ladder rather than guess at it; it offers both self-service routes; it names the **techniques dropped**, so the consequence is visible rather than a warning; and it is deterministic, per `CLAUDE.md §7` rule 8.

### 2. Read-only enforcement, and which layer is the real guarantee

**The real guarantee is the server-side read-only transaction,** because it is the only layer not enforced by our own code — a bug in EvalLoop cannot write through it. Postgres: `BEGIN TRANSACTION READ ONLY`, with `default_transaction_read_only=on` set on the session as well (via `PGOPTIONS` on the CLI path, via connection configuration on the driver path). MySQL: `START TRANSACTION READ ONLY`. The driver path makes this *better* rather than merely equivalent, because the refusal comes back as a structured SQLSTATE (`25006` on Postgres) instead of a string to be matched on stderr.

**EL-305's AST rejector and the caps are defence in depth, and the AST layer is the weakest of the three.** There is no SQL parser in the standard library, so EL-305's rejector is hand-written and therefore incomplete by construction — which is exactly why it must not be the guarantee. Its real value is different and still worth having: it rejects `DROP TABLE` *before transmission*, so the audit log records a refusal rather than a server error, satisfying EL-305's done-when; and it rejects multi-statement input, which protects the transaction wrapper itself from a trailing `COMMIT;`.

The structural requirement that mechanism flexibility adds: **the envelope must be mechanism-independent.** Every mechanism implements one narrow internal interface, and EL-305 wraps that interface, so there is a single code path to any database and no mechanism can offer a convenience API that bypasses it. Two residual gaps to state rather than paper over, both of which EL-308 must verify against the server versions in the Gate V fixture rather than trust from documentation: a read-only transaction blocks standard DML and DDL but does not make a statement side-effect-free, since a volatile function reaching outside the transaction (`COPY … TO PROGRAM`, `dblink`, an extension) is a different class of problem, mitigated by the caps and by EL-304's default-deny; and MySQL read-only transactions are understood to still permit temporary-table writes, harmless here but worth confirming. The genuinely strongest control is neither layer — it is connecting as a read-only database role, which the consent step should offer and prefer but cannot require of a developer's local database.

### 3. Injection safety across both mechanisms

**Shell injection is eliminated structurally on the CLI path.** Every invocation is `subprocess.run([...], shell=False)` with an argv list, so no string is ever handed to a shell and `;`, backticks and `$()` have no meaning. The SQL goes on **stdin** rather than via `-c`, which also removes option injection, since no attacker-influenced string can land where a leading `-` is read as a flag. The driver path has no shell and no argv at all, so the question does not arise.

**The statement under test is untrusted by design and is not an injection problem.** Model-generated SQL is the artifact being evaluated; we execute it wholesale on purpose, and the envelope in §2 exists for precisely that. The narrow real exposure is the SQL *EvalLoop itself* builds for `describe` and for capped reads.

**Values use bind parameters where the mechanism has them, and identifiers never do, because no mechanism binds identifiers.** On the driver path, every value EvalLoop supplies is bound, which is the proper fix and one of the reasons rung 1 is preferred. Identifiers are handled identically on both paths, by allowlisting rather than escaping: introspection uses static catalog queries with no interpolation at all, and the only identifiers ever embedded are ones **read back from the catalog in a previous call** — never from the model, the user or a config file — then quoted with the dialect's own rules (a driver's identifier-composition API where available, otherwise doubled `"` for Postgres and doubled backticks for MySQL) and rejected if they fail to round-trip. Numeric parameters such as a `LIMIT` are cast to `int`; the cap value comes from the grant, not from this document.

### 4. Output format, parsing, and normalisation to one canonical form

**Every mechanism normalises into the same canonical typed row**, and this is the requirement that makes the ladder safe for EL-311: a row is a tuple of `None` for `NULL`, `decimal.Decimal` for exact numerics, `int`, `str`, `bytes` for binary, and date/time values with an explicit zone. Comparison happens only on that form. The driver path produces it almost directly, which is its main advantage. The CLI path reconstructs it from the column types read via `describe`.

**`NULL` versus empty string is where the mechanisms genuinely differ.** On the driver path there is no ambiguity: `NULL` is `None` and `''` is `''`. On the CLI path, Postgres reads go through `COPY (<statement>) TO STDOUT WITH (FORMAT csv, HEADER, NULL '\N')` rather than `psql --csv`, because `--csv` renders `NULL` as an empty field and makes it indistinguishable from `''` — a silent correctness bug in any result comparison — whereas CSV-mode `COPY` emits an empty string quoted as `""` and `NULL` as the unquoted marker, so quoting recovers the difference. **MySQL's CLI has no equivalent fix**: batch mode prints `NULL` as the four characters `NULL`, colliding with the string `'NULL'`. EL-308 mitigates with a per-column `IS NULL` discriminator where a comparison depends on it, and this must be recorded as a known limitation of the MySQL CLI rung — it is also the single strongest argument for preferring a driver for MySQL specifically.

**Embedded delimiters** are a CLI-path concern only, and are safe in both formats provided parsing uses the stdlib `csv` module rather than `str.split` — CSV quotes fields containing commas, quotes and newlines, and MySQL batch mode escapes `\t`, `\n` and `\\`, which `csv` handles with `delimiter='\t'`, `quoting=QUOTE_NONE`, `escapechar='\\'`. Hand-rolled splitting is prohibited, not discouraged. **Type normalisation** matters most for numerics: `1`, `1.0` and `1.00` are one number and three different strings, booleans arrive as `t`/`f` from `COPY` and `0`/`1` from MySQL, timestamps may carry or omit a zone, and `bytea` arrives hex-encoded. Exact numerics go through `Decimal`, never `float`.

### 5. Credential handling

**Never in argv, on either path.** Process arguments are world-visible in `ps`, so `--password=…` and any DSN carrying a password are prohibited; `mysql` warns about this itself, which is a good signal the route is wrong. Credentials are held only by the capability broker, keeping `ARCHITECTURE.md:101` intact — "One component owns credentials. The capability broker. A grader never reads an env var."

**Delivery is per mechanism, and the best outcome is to handle no credential at all.** Where the developer already has a working `~/.pgpass`, a Postgres service file or a `my.cnf`, the connector passes only host, database and service name and lets existing configuration supply the secret. Otherwise the CLI path reads it from a broker-written file at mode `0600` (`PGPASSFILE`, or `--defaults-extra-file=` passed first, as `mysql` requires), unlinked when the grant expires; the driver path passes it as a connection argument in-process, or, when the driver runs in the isolated runtime as a subprocess, over a pipe on a dedicated file descriptor rather than through argv or the environment. An environment variable (`PGPASSWORD`, `MYSQL_PWD`) is the last resort, scoped to the child only and never inherited further. The isolated runtime directory is `0700`, and the connector subprocess does not inherit the parent's full environment.

**The EL-402 redactor never sees the credential, and must not be told it.** The secret appears in neither argv nor the statement text, and the audit log records statements verbatim (`ARCHITECTURE.md §6.2`) — statements do not contain passwords — so nothing on the bus carries it, which is what makes `ARCHITECTURE.md:369` ("Credentials in a grader | Impossible by construction") true. Handing the value to the redactor to be safe would invert the invariant by copying the secret into a second component. The redactor's independent `.env`-value matching already catches a credential that leaks by an unanticipated path, which is the correct division: the broker holds the secret, the redactor recognises it without being given it. The install flow touches no credential at all.

## What this forecloses

The headline cost is new, and it is the price of flexibility rather than of any one mechanism:

- **Bit-identical reproducibility across machines is given up.** Two machines can resolve different rungs and therefore different fidelity — most sharply the MySQL `NULL` ambiguity, which exists on the CLI rung and not on the driver rung. Mitigations, all required rather than optional: the resolved mechanism and version are recorded as **provenance** in the audit log and session report; the mechanism is pinned for the life of a session rather than re-resolved per query; an explicit override exists; and a mechanism change between runs is surfaced the way any provenance change is, since it can move a score without any code changing. **Both sides of an EL-311 comparison must use the same mechanism** — comparing a driver result against a CLI result would compare typed values to reconstructed text.
- **Two code paths to build, test and keep correct,** with a correctness matrix rather than a single implementation. The CLI path's limitations persist for whoever lands on it, so they cannot be treated as transitional.
- **A first-run consent prompt on rung 3,** which cuts against `CLAUDE.md §1`'s "two clicks per session". Honest cost; mitigated by remembering the answer per project and by rungs 1 and 2 covering most machines without asking.
- **Air-gapped, offline and non-interactive environments cannot reach rung 3,** so they get rung 2 or `UNAVAILABLE`. Non-interactive defaults to deny.
- **Supply-chain surface,** bounded by a pinned version with hash checking, an isolated `0700` directory, and never writing to the user's environment — but not zero.
- **`mypy --strict` cannot typecheck an absent driver,** forcing a typed Protocol boundary with the driver path behind it, and `pytest` must pass with no third-party package present, forcing fakes. Both are real constraints on EL-308's structure, not incidental.
- **Per-rung capability differences** that callers must not assume away: prepared statements, pooling, streaming cursors, structured SQLSTATE and cross-call session continuity all exist on the driver rung and not on the CLI rung, where each subprocess is its own session. `LISTEN`/`NOTIFY`, `COPY FROM`, binary transfer and full-fidelity arrays, `JSONB` and user-defined types are available only on the driver rung, and flatten to text on the CLI rung.

### Does this give EL-311 enough fidelity, and how must the comparison be done?

**Yes, and more than a CLI-only policy would — but only because comparison happens on the canonical typed form of §4, never on raw output.** That condition belongs in EL-311's contract, not in a comment.

`ARCHITECTURE.md §6.4` sets the requirement: "Execute generated and reference SQL on a **frozen snapshot**, compare **result sets** — multiset equality, order-insensitive unless the query has `ORDER BY`." Four conditions satisfy it:

1. **Both statements run through the same mechanism, in one session** — so the comparison is mechanism-independent and both see the same snapshot. On the CLI rung this means one invocation, since a read-only transaction cannot span two subprocesses.
2. **`NULL` must be recoverable** — automatic on the driver rung; CSV-mode `COPY` on the Postgres CLI rung; the documented discriminator on the MySQL CLI rung.
3. **Values are compared on the canonical form,** exact numerics via `Decimal`. This is the dominant false-mismatch risk, and it is the corpus's own failure mode wearing a new hat: the A1 row exists because exact-match scored 41% where execution-match scored 68%, the gap being equivalent rewrites. Comparing `1.00` against `1.0` as strings would reintroduce exactly that error one layer down — a formatting difference reported as a correctness failure.
4. **Comparison is multiset over canonical rows,** sorted deterministically after normalisation. Diffing raw stdout or raw driver output would make row order and formatting significant, contradicting the requirement outright.

One thing EL-311 must still decide, which this policy does not settle: whether *column* order is significant when the reference query selects the same columns in a different order. Row order is specified; column order is not, and it should be written down before the validator is built rather than falling out of the implementation.

## Reopen trigger

> **This decision reopens if the resolved-mechanism ladder produces a reproducibility failure that provenance cannot explain — two runs on the same fixture disagreeing because of the mechanism rather than the data — or if consent-gated installation proves unworkable in practice (routinely declined, or blocked by policy on the machines EvalLoop actually runs on), observed by the engineer at EL-311 and reported at Gate V (4 Dec 2026, or ~14 Jan 2027 under `decisions/EL-005-track-order.md`).**

If it fires, the fallback is to collapse the ladder to a single mandated rung and accept its limits — CLI-only if installation is the problem, driver-only as a declared dependency if fidelity is. Not to the pure-Python wire protocol, which no observation here would justify.

## Consequences

- **`CLAUDE.md:43` must be amended before EL-308 starts.** This policy is not compliant with §3 as written; the amendment is in `## Follow-up`, and leaving it unapplied means the first implementer of rung 3 breaks a hard constraint.
- **EL-302 gains a new grant type.** The broker currently models endpoint grants ("ungranted tool → UNAVAILABLE, naming the missing tool", `DEVELOPMENT_PLAN.md:148`); it now also needs a *package install* grant, with its own consent record, a remembered decision, and a non-interactive default of deny. This is the largest new piece of work this decision creates and it lands in EL-302, not EL-308.
- **EL-308's scope grows and its summary is now wrong.** `DEVELOPMENT_PLAN.md:154` reads "V6 Postgres + MySQL **via CLI**" at 1 day; it is now two mechanisms plus a resolution ladder plus fakes for the absent-driver test path, and the estimate should be revisited at the post-M0 re-check that `DEVELOPMENT_PLAN.md:9` already schedules.
- **EL-305 gains two constraints:** its AST rejector must reject multi-statement input, because the transaction wrapper depends on it; and the envelope must wrap one mechanism-independent interface so no mechanism can bypass it.
- **EL-311 gains four requirements and one open question,** above. The requirement that comparison never touch raw output is the one most likely to be violated by a quick implementation.
- **EL-306 is untouched.** `sqlite3` is stdlib, and `?mode=ro` already appears in the `ARCHITECTURE.md §6.2` envelope table; SQLite needs no rung.
- `pyproject.toml` is unchanged, and `dependencies` remains `[]`.
- Statement timeouts and row/byte caps are deliberately left unnumbered: they are grant parameters owned by EL-302 and EL-305, and inventing values here would violate `CLAUDE.md:49`.

## Follow-up — proposed, not applied

1. **`CLAUDE.md:43`** — replace the Dependencies row with wording that permits this policy, for example: *"**Standard library only** in shipped code, and `dependencies` in `pyproject.toml` stays empty. `pytest` and `mypy` are dev-only. A third-party package may be acquired at runtime **only** as a consent-granted capability through the capability broker, installed into an EvalLoop-owned runtime, never imported at module scope, and with `pytest` and `mypy --strict` both passing when it is absent (decision `decisions/EL-006-db-driver-policy.md`). NumPy remains the only package that may ever be a declared dependency."* **Apply this before EL-308.**
2. **`CLAUDE.md §3`** — add a row: *"Connectors resolve a mechanism through the broker; no driver is imported at module scope."*
3. **`DEVELOPMENT_PLAN.md:91`** — update the EL-006 row to "✅ Decided: runtime-resolved mechanism (driver → CLI → consent install), no declared dependency — `decisions/EL-006-db-driver-policy.md`".
4. **`DEVELOPMENT_PLAN.md:154`** — retitle EL-308 from "V6 Postgres + MySQL via CLI" to "V6 Postgres + MySQL connectivity (mechanism ladder)", change its done-when to "no mechanism available → consent asked; declined → UNAVAILABLE, not a crash", and re-estimate.
5. **`DEVELOPMENT_PLAN.md:148`** — note the install-grant type on EL-302 and re-estimate it.
6. **`ARCHITECTURE.md:213-223`** (§6.3) — rewrite to the ladder, since it currently presents the CLI as the recommendation and option B as a slippery slope.

## Related

- `ARCHITECTURE.md:187-235` (§6) — the four-stage connector flow, the read-only envelope above the mechanism, and §6.3's original framing of the stdlib problem; `ARCHITECTURE.md §6.4` — the execution-match requirement EL-311 inherits.
- `decisions/EL-002-mcp-tools-in-enum.md` — the boundary this decision respects from the other side: transport stays out of the `Tool` vocabulary, so `Tool.db_connection` names the capability while this record governs how it is reached. The ladder is exactly the broker-owned transport choice EL-002 anticipated.
- `decisions/EL-005-track-order.md` — when EL-308 and Gate V land, and therefore when the reopen trigger is checked.
