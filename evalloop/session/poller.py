"""A stdlib filesystem poller: walk + stat + content-hash, and report what changed since last time.

This is the cheapest, most exact sensor (``ARCHITECTURE.md`` §4.1): reading a file from disk is
free and precise, where a screen frame is a lossy, costly guess. It walks a working tree skipping
dot-directories, virtualenvs and the usual build noise, hashes each Python source file, and diffs
two snapshots. No ``watchdog``, no OS file-event API — a poll loop over ``os.scandir``, per the
project's standalone/stdlib-first rule.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

__all__ = ["Snapshot", "snapshot", "changed_files"]

# A snapshot maps a repo-relative POSIX path to the hash of that file's bytes.
Snapshot = dict[str, str]

_VENV_MARKER = "pyvenv.cfg"
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "build", "dist", ".git", ".evalloop"})


def _hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def snapshot(root: str | os.PathLike[str]) -> Snapshot:
    """Hash every evaluable source file under ``root``. Deterministic, dot-dirs and venvs skipped."""
    base = Path(root)
    result: Snapshot = {}
    for directory, dirnames, filenames in os.walk(base):
        if _VENV_MARKER in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = Path(directory) / name
            digest = _hash(path)
            if digest is not None:
                rel = path.relative_to(base).as_posix()
                result[rel] = digest
    return result


def changed_files(before: Snapshot, after: Snapshot) -> tuple[str, ...]:
    """The files that were added, removed or modified between two snapshots, sorted and stable."""
    changed = {path for path, digest in after.items() if before.get(path) != digest}
    changed |= {path for path in before if path not in after}
    return tuple(sorted(changed))
