"""Tests for the git state reader (T20)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from evalloop.session.git_state import GitState, commit_message, diff_stat, git_state


def _init_repo(tmp: Path) -> None:
    """Create a minimal git repo with one commit."""
    subprocess.run(["git", "init"], cwd=tmp, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, capture_output=True, check=True)
    (tmp / "initial.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "initial.py"], cwd=tmp, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp, capture_output=True, check=True)


class TestGitState:
    def test_reports_branch_and_sha(self, tmp_path: Path) -> None:
        """T20 done-when: reports baseline, branch."""
        _init_repo(tmp_path)
        state = git_state(tmp_path)
        assert state.is_repo
        assert state.branch  # typically "main" or "master"
        assert len(state.sha) == 40  # full SHA
        assert state.clean

    def test_reports_staged_files(self, tmp_path: Path) -> None:
        """T20 done-when: reports staged."""
        _init_repo(tmp_path)
        (tmp_path / "new.py").write_text("y = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "new.py"], cwd=tmp_path, capture_output=True, check=True)
        state = git_state(tmp_path)
        assert "new.py" in state.staged
        assert not state.clean

    def test_reports_working_changes(self, tmp_path: Path) -> None:
        """T20 done-when: reports committed (working tree changes)."""
        _init_repo(tmp_path)
        (tmp_path / "initial.py").write_text("x = 2\n", encoding="utf-8")
        state = git_state(tmp_path)
        assert "initial.py" in state.working
        assert not state.clean

    def test_reports_untracked(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "untracked.py").write_text("z = 3\n", encoding="utf-8")
        state = git_state(tmp_path)
        assert "untracked.py" in state.untracked

    def test_dirty_files_union(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "initial.py").write_text("x = 2\n", encoding="utf-8")
        (tmp_path / "new.py").write_text("y = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "new.py"], cwd=tmp_path, capture_output=True, check=True)
        (tmp_path / "untracked.txt").write_text("", encoding="utf-8")
        state = git_state(tmp_path)
        assert "initial.py" in state.dirty_files
        assert "new.py" in state.dirty_files
        assert "untracked.txt" in state.dirty_files

    def test_non_repo_returns_empty(self, tmp_path: Path) -> None:
        state = git_state(tmp_path)
        assert not state.is_repo
        assert state.branch == ""
        assert state.sha == ""
        assert state.clean

    def test_commit_message(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        msg = commit_message(tmp_path)
        assert msg == "initial"

    def test_diff_stat_on_clean_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        stat = diff_stat(tmp_path)
        assert stat == ""  # no uncommitted changes

    def test_diff_stat_with_changes(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "initial.py").write_text("x = 999\n", encoding="utf-8")
        stat = diff_stat(tmp_path)
        assert "initial.py" in stat
