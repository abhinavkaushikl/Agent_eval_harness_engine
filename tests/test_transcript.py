"""Tests for the AI transcript reader (T21)."""

from __future__ import annotations

import json
from pathlib import Path

from evalloop.session.transcript import (
    TranscriptMessage,
    extract_intent,
    find_transcripts,
    latest_intent,
    read_transcript,
)


def _write_jsonl(path: Path, messages: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(m) for m in messages]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestReadTranscript:
    def test_reads_simple_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "chat.jsonl"
        _write_jsonl(path, [
            {"role": "user", "content": "fix the login bug"},
            {"role": "assistant", "content": "I'll fix that now."},
        ])
        messages = read_transcript(path)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "fix the login bug"
        assert messages[1].role == "assistant"

    def test_handles_content_blocks(self, tmp_path: Path) -> None:
        """Claude API style: content is a list of blocks."""
        path = tmp_path / "chat.jsonl"
        _write_jsonl(path, [
            {"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]},
        ])
        messages = read_transcript(path)
        assert len(messages) == 1
        assert "hello" in messages[0].content
        assert "world" in messages[0].content

    def test_extracts_timestamp(self, tmp_path: Path) -> None:
        path = tmp_path / "chat.jsonl"
        _write_jsonl(path, [
            {"role": "user", "content": "hello", "timestamp": 1700000000.0},
        ])
        messages = read_transcript(path)
        assert messages[0].ts == 1700000000.0

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "chat.jsonl"
        path.write_text(
            '{"role": "user", "content": "good"}\n'
            'this is not json\n'
            '{"role": "assistant", "content": "also good"}\n',
            encoding="utf-8",
        )
        messages = read_transcript(path)
        assert len(messages) == 2

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        messages = read_transcript(tmp_path / "nonexistent.jsonl")
        assert messages == ()

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        messages = read_transcript(path)
        assert messages == ()


class TestExtractIntent:
    def test_extracts_last_user_message(self) -> None:
        """T21 done-when: extracts stated intent from disk."""
        messages = (
            TranscriptMessage(role="user", content="fix the login bug please", ts=1.0, index=0),
            TranscriptMessage(role="assistant", content="I'll fix that.", ts=2.0, index=1),
            TranscriptMessage(role="user", content="also update the tests for it", ts=3.0, index=2),
        )
        intent = extract_intent(messages)
        assert intent == "also update the tests for it"

    def test_ignores_trivial_messages(self) -> None:
        messages = (
            TranscriptMessage(role="user", content="fix the login bug please", ts=1.0, index=0),
            TranscriptMessage(role="assistant", content="Done.", ts=2.0, index=1),
            TranscriptMessage(role="user", content="ok", ts=3.0, index=2),
        )
        intent = extract_intent(messages)
        assert intent == "fix the login bug please"

    def test_ignores_bare_yes_no(self) -> None:
        messages = (
            TranscriptMessage(role="user", content="yes", ts=1.0, index=0),
            TranscriptMessage(role="user", content="no", ts=2.0, index=1),
            TranscriptMessage(role="user", content="sure", ts=3.0, index=2),
        )
        assert extract_intent(messages) is None

    def test_no_messages(self) -> None:
        assert extract_intent(()) is None

    def test_only_assistant_messages(self) -> None:
        messages = (
            TranscriptMessage(role="assistant", content="I did the thing", ts=1.0, index=0),
        )
        assert extract_intent(messages) is None


class TestFindTranscripts:
    def test_finds_transcripts_in_claude_home(self, tmp_path: Path) -> None:
        project = tmp_path / "myproject"
        project.mkdir()
        claude_home = tmp_path / ".claude"
        projects_dir = claude_home / "projects" / f"-{project.name}"
        projects_dir.mkdir(parents=True)
        t1 = projects_dir / "conv1.jsonl"
        t2 = projects_dir / "conv2.jsonl"
        _write_jsonl(t1, [{"role": "user", "content": "hello from one"}])
        _write_jsonl(t2, [{"role": "user", "content": "hello from two"}])
        found = find_transcripts(project, claude_home=claude_home)
        assert len(found) == 2

    def test_no_claude_home_returns_empty(self, tmp_path: Path) -> None:
        found = find_transcripts(tmp_path / "nope", claude_home=tmp_path / "no-claude")
        assert found == ()


class TestLatestIntent:
    def test_end_to_end(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        claude_home = tmp_path / ".claude"
        t_dir = claude_home / "projects" / f"-{project.name}"
        t_dir.mkdir(parents=True)
        _write_jsonl(t_dir / "latest.jsonl", [
            {"role": "user", "content": "refactor the database layer to use connection pooling"},
            {"role": "assistant", "content": "I'll restructure it now."},
        ])
        intent = latest_intent(project, claude_home=claude_home)
        assert intent == "refactor the database layer to use connection pooling"

    def test_no_transcripts(self, tmp_path: Path) -> None:
        assert latest_intent(tmp_path, claude_home=tmp_path / "nope") is None
