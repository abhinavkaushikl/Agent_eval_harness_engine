"""Git state reader: baseline SHA, branch, staged/committed/working diffs (T20).

Uses ``subprocess`` to call git; nothing is imported from gitpython or similar.
Every call is read-only and cannot change the repository.  A directory that is
not a git repository returns a :class:`GitState` with empty fields and
``is_repo`` False, never an exception -- the session may watch a non-git folder.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["GitState", "git_state"]


@dataclass(frozen=True, slots=True)
class GitState:
    """A snapshot of the git working tree's state at one point in time."""

    is_repo: bool
    branch: str  # current branch name, or "" if detached/not a repo
    sha: str  # HEAD commit SHA (full), or ""
    staged: tuple[str, ...]  # paths with staged changes
    working: tuple[str, ...]  # paths with unstaged working-tree changes
    untracked: tuple[str, ...]  # untracked files (not in .gitignore)

    @property
    def clean(self) -> bool:
        """True if there are no staged, unstaged, or untracked changes."""
        return not self.staged and not self.working and not self.untracked

    @property
    def dirty_files(self) -> frozenset[str]:
        """All files that differ from HEAD, regardless of staging state."""
        return frozenset(self.staged) | frozenset(self.working) | frozenset(self.untracked)


_EMPTY = GitState(is_repo=False, branch="", sha="", staged=(), working=(), untracked=())


def _run(root: Path, *args: str, timeout: float = 5.0) -> str | None:
    """Run a git command and return its stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _lines(text: str | None) -> tuple[str, ...]:
    """Split git output into non-empty lines."""
    if not text:
        return ()
    return tuple(line for line in text.strip().splitlines() if line)


def git_state(root: str | Path, *, timeout: float = 5.0) -> GitState:
    """Read the git state of the working tree at ``root``.

    Returns :data:`_EMPTY` (with ``is_repo=False``) when ``root`` is not inside a
    git repository, git is not installed, or any git command fails.
    """
    root_path = Path(root)
    # Check if this is a git repo at all.
    check = _run(root_path, "rev-parse", "--is-inside-work-tree", timeout=timeout)
    if check is None or check.strip() != "true":
        return _EMPTY

    branch_raw = _run(root_path, "rev-parse", "--abbrev-ref", "HEAD", timeout=timeout)
    branch = (branch_raw or "").strip()

    sha_raw = _run(root_path, "rev-parse", "HEAD", timeout=timeout)
    sha = (sha_raw or "").strip()

    staged = _lines(_run(root_path, "diff", "--cached", "--name-only", timeout=timeout))
    working = _lines(_run(root_path, "diff", "--name-only", timeout=timeout))
    untracked = _lines(
        _run(root_path, "ls-files", "--others", "--exclude-standard", timeout=timeout)
    )

    return GitState(
        is_repo=True,
        branch=branch,
        sha=sha,
        staged=staged,
        working=working,
        untracked=untracked,
    )


def diff_stat(root: str | Path, ref: str = "HEAD", *, timeout: float = 5.0) -> str:
    """A human-readable ``git diff --stat`` against ``ref``, or empty on failure."""
    result = _run(Path(root), "diff", "--stat", ref, timeout=timeout)
    return (result or "").strip()


def commit_message(root: str | Path, ref: str = "HEAD", *, timeout: float = 5.0) -> str:
    """The commit message at ``ref``, or empty on failure."""
    result = _run(Path(root), "log", "-1", "--format=%B", ref, timeout=timeout)
    return (result or "").strip()
