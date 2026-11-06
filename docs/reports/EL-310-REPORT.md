# EL-310 — File + prompt-registry connectors

**⚠ Depends on EL-307 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_file_prompt_connectors.py` 47 passed; `mypy --strict evalloop/`
clean on 79 files; standard library only; the MCP tests run the EL-301 reference server over stdio,
**no network**. Full suite: 1464 passed, 2 skipped, 1 failed. The failure is pre-existing and not
EL-310's (§5).

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/protocol.py` | **added** the `InputSource` contract (`probe()` / `inputs()`) and its value types: `EvalInput`, `InputKind` (`document` / `prompt`), `Message`, `Skipped`, `InputSet` |
| `evalloop/connect/files.py` | `DirectoryConnector`: a directory of source docs as eval inputs. Gitignore-aware, size-capped, binary-skipping, redacted. Also a minimal stdlib `GitIgnore` matcher and `make_input`, the one place inputs are built |
| `evalloop/connect/prompts.py` | `PromptFileConnector` (prompt files on disk) and `MCPPromptConnector` (an MCP server's prompts); both implement `InputSource` |
| `evalloop/connect/redact.py` | `redact_secrets`, the text redactor at the boundary (credential shapes only; see §3.4) |
| `evalloop/mcp/facade.py`, `client.py`, `__init__.py` | **added** `Prompt`, `PromptArgument`, `PromptMessage`, `PromptResult`, the `PromptLister` protocol, and `StdioClient.list_prompts()` / `get_prompt()` (`prompts/list`, `prompts/get`) |
| `tests/fixtures/mcp/reference_server.py` | **added** three prompts: `summarize` (one required argument), `greeting` (a planted credential), `picture` (an image block) |
| `tests/test_file_prompt_connectors.py` | 47 tests |

## 2. Acceptance criteria
| # | Criterion | How |
|---|---|---|
| 1 | A docs directory and a prompt file are both read and exposed as eval inputs | `DirectoryConnector(docs).inputs()` returns `EvalInput(kind=document)` per file. `PromptFileConnector(repo).inputs()` returns `prompts/support.md` as `EvalInput(kind=prompt)`, with its `{{ }}` placeholders as `parameters` |
| 2 | An MCP-served prompt is usable through the same interface | `MCPPromptConnector` over a live `StdioClient` returns `summarize` and `greeting` as `EvalInput(kind=prompt)`, role-tagged messages kept. One test iterates `list[InputSource]` holding a file connector and an MCP connector and cannot tell them apart |
| 3 | Binary and oversized files are skipped with a reason, not read | NUL in the first 8 KiB → `binary …`; failed UTF-8 decode → `not UTF-8 text`; over `max_file_bytes` → `oversized (4.9 KiB > the 4.0 KiB per-file cap)`. A 2 GiB sparse file is proven **never opened** (a `Path.open` spy sees only the small file) |
| — | Gitignore-aware; no `node_modules` or 2 GB dump (the gotcha) | Root and nested `.gitignore` files, negation, anchoring, dir-only and `**` are all tested. Ignored directories, dot directories, `node_modules`, `site-packages` and virtualenvs (`pyvenv.cfg`) are pruned whole, as one `Skipped` entry each. Dotfiles (`.env`) and symlinks are skipped. The grant's `Caps.max_bytes` bounds the total |
| — | Everything routed through the broker and the redactor | Each `probe`/`inputs` call does `broker.check` first. An ungranted source raises `NotAuthorized` before any file is opened or any server is contacted. Every text passes `redact_secrets` inside `make_input`, so nothing unredacted is returned. The audit log records shape only (tested: no secret and no body text in any entry). Nothing in the root is written (mtimes unchanged) |

Out of scope, and not done: computing any metric from these inputs (EL-312/313, M4).

## 3. Calls I made
1. **A second contract, `InputSource`, beside `Connector`.** `Connector.read(sql)` is a query. Files
   and prompts are read whole, and forcing them through a SQL-shaped `read` would be a lie in the
   types. So `InputSource` has `probe()` + `inputs()`, and all three EL-310 connectors implement it.
   The SQL `Connector`s are unchanged.
2. **Capabilities.** Docs: `source_doc_read` (the ticket names it). Prompt files: `repo_read`, since
   they live in the repository. MCP prompts: **`source_doc_read`, an interpretation.** No `Tool`
   member names a prompt registry. MCP is transport, not a capability (EL-002), and `source_doc_read`
   (read-only documents outside the repo) is the nearest fit. Both are constructor arguments. I added
   no new member, since by EL-104 that is a decision ticket.
3. **MCP prompts.** A required argument is never guessed: if the caller supplies no value, the prompt
   is skipped with `requires the argument(s) document …`. A prompt with a non-text block (an image)
   is skipped, not flattened to its text. A server error on one prompt skips only that prompt. This
   needed `prompts/list` / `prompts/get` in the EL-301 client, added behind the façade, and the
   wire-leak grep tests still pass.
4. **The redactor is credential-only, and it is new.** The safety spine says "everything crosses the
   redactor", but the only redactor in the tree was `redact_sql` (literals → `?`), which would destroy
   a document. `redact_secrets` replaces PEM private keys, known key shapes (`sk-`, `gsk_`, `AKIA`,
   `ghp_`/`github_pat_`, `xox?-`), URL passwords, and `password|secret|token|api_key… = <8+ chars>`
   values. Prose like `token: none` passes. **It is not a PHI/PII detector.** Fixture 20's PHI ruling
   is still open, and a document holding patient data passes through unchanged. `content_hash` is of
   the *redacted* text, so a short secret can't be recovered from it by guessing.
5. **What makes a file a prompt:** `*.prompt`, `*.prompt.md`, `*.prompt.txt`, `*.prompty`, or a text
   template (`.md .txt .j2 .jinja .jinja2 .tmpl`) under a directory named `prompts`. This is a
   convention I picked, not one from the corpus.
6. **Numbers.** `DEFAULT_MAX_FILE_BYTES` = 1 MiB and the 8 KiB binary sniff are engineering limits on
   memory, not methodology thresholds. The corpus states neither, and both are overridable (the
   per-file cap via the constructor, the total via the grant's `Caps.max_bytes`).
7. **Gitignore subset, stated.** No `pathspec`. Not supported: escaped trailing spaces,
   `.git/info/exclude`, and the user's global excludes file. The connector reads the repository, not
   the user's git config.

## 4. Vocabulary gap
- No `Tool` member for a **prompt registry** (§3.2). Raised, not added.

## 5. Full-suite note (not an EL-310 regression)
`tests/test_oracle_harvest.py::test_the_virtualenvs_vendored_tests_are_not_this_repositorys` fails
identically on a clean `main` with these changes stashed (verified). The harvester finds 56 test
files where `tests/` holds 53. The three extra `test_*.py` live outside `tests/` (the example
folders), so this is a test-expectation issue, not a harvester bug and not EL-310's.

## 6. Rulings I need
1. Accept building ahead of Gate 1.
2. **MCP prompts under `source_doc_read`** (§3.2), or open a decision ticket for a prompt-registry member.
3. **The prompt-file convention** (§3.5): keep it, or make it configurable per repository.
4. **Redactor scope** (§3.4): confirm that credential-only redaction is enough until the PHI gate is ruled.
