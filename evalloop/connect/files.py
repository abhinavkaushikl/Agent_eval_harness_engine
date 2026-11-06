"""The directory connector: a folder of source documents as read-only, size-capped eval inputs.

``ARCHITECTURE.md``: source docs are the raw material for a RAG question set, reached through the
``source_doc_read`` capability. This connector reads a directory **whole** — it is not queried, so it
implements :class:`~evalloop.connect.protocol.InputSource` (``probe`` / ``inputs``) rather than the
SQL-shaped :class:`~evalloop.connect.protocol.Connector`. The same walk serves EL-310's prompt files
(:mod:`evalloop.connect.prompts`), with a different filter and kind.

What it refuses to read, and how
--------------------------------
The ticket's gotcha: "keep the read gitignore-aware and size-capped so it doesn't ingest
``node_modules`` or a 2 GB dump." So, in order, a file is skipped **with a stated reason** when it:

1. is under a pruned directory — a dot directory, ``__pycache__``, ``node_modules``,
   ``site-packages``, ``dist-packages``, or a virtualenv (a directory holding ``pyvenv.cfg``). A
   pruned directory is one :class:`~evalloop.connect.protocol.Skipped` entry, not one per file;
2. is matched by a ``.gitignore`` (the root's and every nested one; see below) — an ignored
   directory is pruned whole, as git does;
3. is a symlink, or a dotfile (``.env`` lives here, and it is never a source document);
4. is larger than ``max_file_bytes`` — decided from ``stat`` **before the file is opened**, so an
   oversized file is never read into memory;
5. would push the total past the grant's ``Caps.max_bytes``;
6. is binary — a NUL byte in its first 8 KiB (only that sniff is read) — or is not UTF-8 text.

Everything that is read crosses the redactor (:func:`~evalloop.connect.redact.redact_secrets`)
before it is returned. Nothing is written, and the audit log records the call by shape only.

The gitignore subset
--------------------
No ``pathspec`` (``CLAUDE.md``: stdlib only), so this is a minimal matcher for what ``.gitignore``
files actually contain: blank lines and ``#`` comments, ``!`` negation, a trailing ``/`` for
directory-only, a leading or inner ``/`` anchoring the pattern to the ``.gitignore``'s directory,
``*``, ``?``, ``[...]`` and ``**``. Rules apply from the root down and the last match wins. Not
supported: escaped trailing spaces and ``$GIT_DIR/info/exclude`` / the global excludes file — the
connector reads the repository, not the user's git config.

``DEFAULT_MAX_FILE_BYTES`` is an engineering cap on memory, not a methodology threshold; the corpus
states no figure for it, and a grant's caps or the constructor override it.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from evalloop.capability.broker import CapabilityBroker
from evalloop.connect.envelope import AuditEntry, AuditLog, Caps, ResultShape
from evalloop.connect.protocol import (
    ConnectorError,
    EvalInput,
    InputKind,
    InputSet,
    Message,
    NotAuthorized,
    ProbeResult,
    Skipped,
)
from evalloop.connect.redact import redact_secrets
from evalloop.vocab import Tool

__all__ = ["DEFAULT_MAX_FILE_BYTES", "DirectoryConnector", "GitIgnore", "make_input"]

DEFAULT_MAX_FILE_BYTES = 1024 * 1024
_SNIFF_BYTES = 8192
_PRUNED_DIRS = frozenset({"__pycache__", "node_modules", "site-packages", "dist-packages"})
_VENV_MARKER = "pyvenv.cfg"


# -- the gitignore subset ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rule:
    base: str  # the root-relative directory of the .gitignore holding this rule ("" for the root)
    regex: re.Pattern[str]
    negate: bool
    dir_only: bool


def _translate(pattern: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("/.*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        elif char == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                out.append(re.escape(char))
                i += 1
            else:
                body = pattern[i + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = end + 1
        else:
            out.append(re.escape(char))
            i += 1
    return "".join(out)


def _parse_rule(line: str, base: str) -> _Rule | None:
    line = line.rstrip("\n").rstrip()
    if not line or line.startswith("#"):
        return None
    negate = line.startswith("!")
    if negate:
        line = line[1:]
    if line.startswith("\\"):
        line = line[1:]
    dir_only = line.endswith("/")
    line = line.rstrip("/")
    if not line:
        return None
    anchored = "/" in line
    line = line.lstrip("/")
    body = _translate(line)
    regex = re.compile(f"^{body}$" if anchored else f"^(?:.*/)?{body}$")
    return _Rule(base, regex, negate, dir_only)


class GitIgnore:
    """The ``.gitignore`` rules found so far in a walk, root first. Add each directory's as you enter it."""

    def __init__(self) -> None:
        self._rules: list[_Rule] = []

    def add_file(self, path: Path, base: str) -> None:
        """Load ``path`` (a ``.gitignore``) whose patterns are relative to the root-relative ``base``."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for line in text.splitlines():
            rule = _parse_rule(line, base)
            if rule is not None:
                self._rules.append(rule)

    def ignored(self, rel: str, *, is_dir: bool) -> bool:
        """Whether the root-relative POSIX path ``rel`` is ignored. The last matching rule decides."""
        verdict = False
        for rule in self._rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.base:
                if not rel.startswith(rule.base + "/"):
                    continue
                local = rel[len(rule.base) + 1 :]
            else:
                local = rel
            if rule.regex.match(local):
                verdict = not rule.negate
        return verdict


# -- turning text into an input ------------------------------------------------------------


def make_input(
    kind: InputKind,
    name: str,
    source: str,
    messages: Sequence[Message],
    *,
    parameters: Sequence[str] = (),
) -> EvalInput:
    """Redact every message, then build the :class:`EvalInput`. The only way inputs are built."""
    redacted: list[Message] = []
    total = 0
    for message in messages:
        text, count = redact_secrets(message.text)
        total += count
        redacted.append(Message(message.role, text))
    text = "\n\n".join(m.text for m in redacted)
    encoded = text.encode("utf-8")
    return EvalInput(
        kind=kind,
        name=name,
        source=source,
        text=text,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        size_bytes=len(encoded),
        redactions=total,
        messages=tuple(redacted),
        parameters=tuple(parameters),
    )


def _human(size: int) -> str:
    return f"{size} bytes" if size < 1024 else f"{size / 1024:.1f} KiB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MiB"


# -- the connector ---------------------------------------------------------------------------


class DirectoryConnector:
    """probe / inputs over a directory: every readable text file, redacted, with a reason for the rest.

    ``include`` narrows which root-relative paths are candidates at all (a non-candidate is not
    reported as skipped — it was never asked for); ``kind`` labels what is read. Both exist so the
    prompt-file connector is this walk with a different filter.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        broker: CapabilityBroker,
        endpoint: str | None = None,
        tool: Tool = Tool.source_doc_read,
        kind: InputKind = InputKind.document,
        include: Callable[[str], bool] | None = None,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        audit: AuditLog | None = None,
    ) -> None:
        if max_file_bytes <= 0:
            raise ConnectorError(f"max_file_bytes must be positive, got {max_file_bytes!r}")
        self.root = Path(root)
        self.endpoint = endpoint if endpoint is not None else f"dir:{self.root.as_posix()}"
        self._broker = broker
        self._tool = tool
        self._kind = kind
        self._include = include
        self._max_file_bytes = max_file_bytes
        self.audit = audit if audit is not None else AuditLog()

    def _authorize(self) -> Caps:
        decision = self._broker.check(self._tool, endpoint=self.endpoint)
        if not decision.granted or decision.grant is None:
            raise NotAuthorized(decision.reason or f"{self._tool.value} is not granted for {self.endpoint!r}")
        return decision.grant.caps

    def probe(self) -> ProbeResult:
        """Is the root a readable directory? Authorised first; lists nothing and reads nothing."""
        caps = self._authorize()
        if not self.root.is_dir():
            self._log("probe", caps, None, error="not a directory")
            return ProbeResult(reachable=False, read_only=True, detail=f"{self.root.as_posix()} is not a directory")
        self._log("probe", caps, None)
        return ProbeResult(reachable=True, read_only=True, detail=f"directory {self.root.as_posix()} (read-only)")

    def inputs(self) -> InputSet:
        """Walk the root deterministically and read every eligible file, under the caps."""
        caps = self._authorize()
        if not self.root.is_dir():
            raise ConnectorError(f"{self.root.as_posix()} is not a directory")
        found: list[EvalInput] = []
        skipped: list[Skipped] = []
        total = 0
        truncated = False
        ignore = GitIgnore()
        for directory, dirnames, filenames in os.walk(self.root):
            here = Path(directory)
            base = here.relative_to(self.root).as_posix()
            base = "" if base == "." else base
            if base and _VENV_MARKER in filenames:
                skipped.append(Skipped(base + "/", "a virtualenv; not walked"))
                dirnames[:] = []
                continue
            if ".gitignore" in filenames:
                ignore.add_file(here / ".gitignore", base)

            kept: list[str] = []
            for name in sorted(dirnames):
                rel = f"{base}/{name}" if base else name
                if os.path.islink(here / name):
                    skipped.append(Skipped(rel + "/", "a symlinked directory; not followed"))
                elif name.startswith(".") or name in _PRUNED_DIRS:
                    skipped.append(Skipped(rel + "/", "a hidden, cache or vendored directory; not walked"))
                elif ignore.ignored(rel, is_dir=True):
                    skipped.append(Skipped(rel + "/", "ignored by .gitignore; not walked"))
                else:
                    kept.append(name)
            dirnames[:] = kept

            for name in sorted(filenames):
                rel = f"{base}/{name}" if base else name
                if self._include is not None and not self._include(rel):
                    continue
                path = here / name
                reason = self._refusal(path, rel, name, ignore)
                if reason is not None:
                    skipped.append(Skipped(rel, reason))
                    continue
                size = path.stat().st_size
                if caps.max_bytes is not None and total + size > caps.max_bytes:
                    skipped.append(Skipped(rel, f"the grant's byte cap ({caps.max_bytes} bytes) is reached; not read"))
                    truncated = True
                    continue
                text, reason = _read_text(path)
                if text is None:
                    skipped.append(Skipped(rel, reason or "unreadable"))
                    continue
                total += size
                found.append(make_input(self._kind, rel, rel, [Message("user", text)]))
        self._log("inputs", caps, ResultShape(len(found), total, truncated))
        return InputSet(tuple(found), tuple(skipped))

    def _refusal(self, path: Path, rel: str, name: str, ignore: GitIgnore) -> str | None:
        if path.is_symlink():
            return "a symlink; not followed"
        if name.startswith("."):
            return "a hidden file (this is where .env lives); not read"
        if ignore.ignored(rel, is_dir=False):
            return "ignored by .gitignore; not read"
        size = path.stat().st_size
        if size > self._max_file_bytes:
            return f"oversized ({_human(size)} > the {_human(self._max_file_bytes)} per-file cap); not read"
        return None

    def _log(self, operation: str, caps: Caps, shape: ResultShape | None, *, error: str | None = None) -> None:
        self.audit.append(
            AuditEntry(
                endpoint=self.endpoint,
                redacted_sql=f"<{operation}>",
                statement_kinds=(operation,),
                caps=caps,
                write_scope=None,
                result=shape,
                error=error,
            )
        )


def _read_text(path: Path) -> tuple[str | None, str | None]:
    """The file's text, or ``None`` and why. Sniffs 8 KiB for a NUL before decoding the rest."""
    try:
        with path.open("rb") as handle:
            head = handle.read(_SNIFF_BYTES)
            if b"\x00" in head:
                return None, "binary (a NUL byte in its first 8 KiB); not read"
            data = head + handle.read()
    except OSError as error:
        return None, f"could not be opened ({error.strerror or error})"
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "not UTF-8 text; not read"
