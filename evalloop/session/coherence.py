"""Coherence detector: decides when a change is complete enough to evaluate (T22).

A developer editing code produces a stream of partial states -- a half-typed
function, an unsaved file, a commit in progress.  Evaluating mid-edit wastes
compute and produces meaningless results.  The coherence detector gates the
evaluation loop: it fires only when the working tree is in a *coherent* state.

Three signals, any combination
------------------------------
1. **Syntax-valid** -- every changed ``.py`` file parses (``ast.parse`` succeeds).
   A file mid-edit almost certainly fails this.  Files that don't end in ``.py``
   are exempt (JSON, YAML, etc. have their own validity, out of scope here).

2. **Quiet period** -- no filesystem events for ``quiet_seconds``.  This is the
   debouncer's window: if the debouncer has flushed a :class:`ChangeUnit`, the
   quiet period has already elapsed.

3. **Transcript signal** -- the coding agent said something that suggests the
   change is complete: "done", "tests pass", "committed", etc.  Optional; when
   no transcript is available, only (1) and (2) decide.

The detector's output is a :class:`CoherenceResult`: ``coherent`` True/False,
the signals that contributed, and a reason when it's not coherent.  The
orchestrator evaluates only when ``coherent`` is True.

Import resolution (T22.2)
-------------------------
Beyond ``ast.parse``, a coherent state means the file's imports resolve to
existing modules.  A missing import means the developer hasn't finished writing
the companion file.  This is checked for *local* imports only (names that resolve
to files inside the working tree); stdlib and third-party imports are not checked.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CoherenceResult",
    "check_coherence",
    "check_syntax",
    "check_imports",
]


@dataclass(frozen=True, slots=True)
class CoherenceResult:
    """Whether a set of changed files is ready to evaluate."""

    coherent: bool
    syntax_ok: bool
    imports_ok: bool
    transcript_signal: bool
    reason: str  # why it's not coherent, or "" if it is

    @property
    def signals(self) -> tuple[str, ...]:
        """The named signals that are satisfied."""
        out: list[str] = []
        if self.syntax_ok:
            out.append("syntax")
        if self.imports_ok:
            out.append("imports")
        if self.transcript_signal:
            out.append("transcript")
        return tuple(out)


def check_syntax(path: str | Path) -> tuple[bool, str]:
    """Check whether a Python file parses.  Returns (ok, reason)."""
    p = Path(path)
    if not p.suffix == ".py":
        return True, ""
    try:
        source = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"cannot read: {exc}"
    try:
        ast.parse(source, filename=str(p))
    except SyntaxError as exc:
        return False, f"syntax error at line {exc.lineno}: {exc.msg}"
    return True, ""


def _local_imports(source: str) -> set[str]:
    """Top-level absolute import names from a source string."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


_SKIP_DIRS = frozenset({"__pycache__", "node_modules", ".git", ".evalloop", "build", "dist"})


def _repo_modules(root: Path) -> frozenset[str]:
    """The top-level importable names inside ``root``: module files and package dirs."""
    names: set[str] = set()
    try:
        for entry in os.scandir(root):
            if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                continue
            if entry.is_file() and entry.name.endswith(".py"):
                stem = entry.name[:-3]
                if stem.isidentifier():
                    names.add(stem)
            elif entry.is_dir() and (Path(entry.path) / "__init__.py").exists():
                if entry.name.isidentifier():
                    names.add(entry.name)
    except OSError:
        pass
    return frozenset(names)


def check_imports(path: str | Path, root: str | Path) -> tuple[bool, str]:
    """Check whether a Python file's local imports resolve to files in the repo.

    Returns (ok, reason).  Only checks imports that name a module inside ``root``;
    stdlib and third-party imports are ignored.
    """
    p = Path(path)
    if not p.suffix == ".py":
        return True, ""
    try:
        source = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True, ""  # can't read -> syntax check will catch it
    imported = _local_imports(source)
    repo_names = _repo_modules(Path(root))
    # Only check names that *could* be local (exist or would exist in the repo).
    # If a name is not in the repo at all, it's probably stdlib or third-party.
    missing: list[str] = []
    for name in sorted(imported):
        if name in repo_names:
            continue
        # Check if it *looks* local: a sibling file or directory exists but isn't importable,
        # or a file is expected but not yet written.
        sibling = Path(root) / f"{name}.py"
        sibling_dir = Path(root) / name
        if sibling.exists() or sibling_dir.exists():
            missing.append(name)
    if missing:
        return False, f"local import(s) not yet importable: {', '.join(missing)}"
    return True, ""


_DONE_PATTERNS = (
    "done",
    "finished",
    "complete",
    "committed",
    "tests pass",
    "all tests pass",
    "pushed",
    "ready for review",
    "lgtm",
    "ship it",
)


def _has_transcript_signal(transcript_messages: tuple[object, ...] | None) -> bool:
    """Check if the latest assistant message signals completion."""
    if not transcript_messages:
        return False
    # Walk backwards looking for the last assistant message.
    for msg in reversed(transcript_messages):
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)
        if role in ("assistant", "ai") and isinstance(content, str):
            lower = content.lower().strip()
            for pattern in _DONE_PATTERNS:
                if pattern in lower:
                    return True
            # Only check the most recent assistant message.
            return False
    return False


def check_coherence(
    changed_files: tuple[str, ...],
    root: str | Path,
    *,
    transcript_messages: tuple[object, ...] | None = None,
    require_all_syntax: bool = True,
) -> CoherenceResult:
    """Decide whether a set of changed files is coherent (ready to evaluate).

    ``changed_files`` are repo-relative paths.  ``root`` is the working tree root.
    ``transcript_messages`` are :class:`TranscriptMessage` objects (or anything with
    ``role`` and ``content`` attributes).

    Coherence requires:
    - All changed ``.py`` files parse (syntax_ok).
    - All local imports resolve (imports_ok).
    - Optionally, a transcript signal (not required by default).

    When ``require_all_syntax`` is False, a syntax error does not block coherence
    (useful for non-Python projects).
    """
    root_path = Path(root)
    syntax_ok = True
    imports_ok = True
    reasons: list[str] = []

    py_files = [f for f in changed_files if f.endswith(".py")]
    for rel in py_files:
        full = root_path / rel
        sok, sreason = check_syntax(full)
        if not sok:
            syntax_ok = False
            reasons.append(f"{rel}: {sreason}")
        iok, ireason = check_imports(full, root_path)
        if not iok:
            imports_ok = False
            reasons.append(f"{rel}: {ireason}")

    transcript_signal = _has_transcript_signal(transcript_messages)

    if require_all_syntax:
        coherent = syntax_ok and imports_ok
    else:
        coherent = imports_ok  # syntax errors are tolerated

    return CoherenceResult(
        coherent=coherent,
        syntax_ok=syntax_ok,
        imports_ok=imports_ok,
        transcript_signal=transcript_signal,
        reason="; ".join(reasons) if reasons else "",
    )
