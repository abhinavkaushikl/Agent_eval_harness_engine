"""Tests for the coherence detector (T22)."""

from __future__ import annotations

from pathlib import Path

from evalloop.session.coherence import (
    CoherenceResult,
    check_coherence,
    check_imports,
    check_syntax,
)


class TestCheckSyntax:
    def test_valid_python(self, tmp_path: Path) -> None:
        f = tmp_path / "good.py"
        f.write_text("x = 1\ndef f():\n    return x\n", encoding="utf-8")
        ok, reason = check_syntax(f)
        assert ok
        assert reason == ""

    def test_invalid_python(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def f(\n", encoding="utf-8")
        ok, reason = check_syntax(f)
        assert not ok
        assert "syntax error" in reason

    def test_non_python_always_ok(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text("{bad json", encoding="utf-8")
        ok, _ = check_syntax(f)
        assert ok


class TestCheckImports:
    def test_imports_resolve(self, tmp_path: Path) -> None:
        (tmp_path / "helpers.py").write_text("def h(): pass\n", encoding="utf-8")
        main = tmp_path / "main.py"
        main.write_text("import helpers\nhelpers.h()\n", encoding="utf-8")
        ok, _ = check_imports(main, tmp_path)
        assert ok

    def test_missing_local_import(self, tmp_path: Path) -> None:
        """A file that exists but isn't importable (e.g. a directory without __init__.py)."""
        (tmp_path / "broken_pkg").mkdir()  # no __init__.py
        main = tmp_path / "main.py"
        main.write_text("import broken_pkg\n", encoding="utf-8")
        ok, reason = check_imports(main, tmp_path)
        assert not ok
        assert "broken_pkg" in reason

    def test_stdlib_imports_ignored(self, tmp_path: Path) -> None:
        main = tmp_path / "main.py"
        main.write_text("import os\nimport json\n", encoding="utf-8")
        ok, _ = check_imports(main, tmp_path)
        assert ok


class TestCheckCoherence:
    def test_coherent_state(self, tmp_path: Path) -> None:
        """T22 done-when: fires on complete units, not mid-edit."""
        (tmp_path / "app.py").write_text("def run():\n    return 42\n", encoding="utf-8")
        result = check_coherence(("app.py",), tmp_path)
        assert result.coherent
        assert result.syntax_ok
        assert result.imports_ok
        assert "syntax" in result.signals

    def test_mid_edit_not_coherent(self, tmp_path: Path) -> None:
        """T22 done-when: does NOT fire mid-edit."""
        (tmp_path / "app.py").write_text("def run(\n", encoding="utf-8")
        result = check_coherence(("app.py",), tmp_path)
        assert not result.coherent
        assert not result.syntax_ok
        assert "syntax error" in result.reason

    def test_transcript_signal_detected(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

        class _Msg:
            def __init__(self, role: str, content: str) -> None:
                self.role = role
                self.content = content

        messages = (_Msg("assistant", "I've finished. All tests pass."),)
        result = check_coherence(("app.py",), tmp_path, transcript_messages=messages)  # type: ignore[arg-type]
        assert result.coherent
        assert result.transcript_signal

    def test_no_transcript_signal(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        result = check_coherence(("app.py",), tmp_path)
        assert result.coherent
        assert not result.transcript_signal

    def test_empty_changes_coherent(self, tmp_path: Path) -> None:
        result = check_coherence((), tmp_path)
        assert result.coherent

    def test_non_py_files_always_coherent(self, tmp_path: Path) -> None:
        (tmp_path / "data.json").write_text("{bad", encoding="utf-8")
        result = check_coherence(("data.json",), tmp_path)
        assert result.coherent

    def test_multiple_files_all_must_parse(self, tmp_path: Path) -> None:
        (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "bad.py").write_text("def(\n", encoding="utf-8")
        result = check_coherence(("good.py", "bad.py"), tmp_path)
        assert not result.coherent
        assert "bad.py" in result.reason
