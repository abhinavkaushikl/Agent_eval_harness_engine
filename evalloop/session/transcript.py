"""AI transcript reader: locate and parse coding-agent transcripts (T21).

Claude Code writes conversation transcripts as JSONL files under
``~/.claude/projects/<project-id>/``.  This module finds the most recent
transcript for a project, parses the messages, and extracts the developer's
stated intent.

The module is deliberately agent-agnostic: it looks for JSONL files whose lines
have ``role`` and ``content`` keys, so any agent that writes the same shape works.
Claude Code is the first; Cursor, Copilot, etc. would each get a locator that
returns the same ``TranscriptMessage`` sequence.

What counts as "intent"
-----------------------
An intent is any user message (``role == "user"`` or ``role == "human"``) whose
content looks like a task description: more than a few words, not a bare "yes"
or "ok".  The *last* such message is the current stated intent, because the
developer may refine their ask several times in one conversation.

Privacy
-------
Transcripts are read from the developer's own disk, the same files their agent
already wrote.  Nothing is sent anywhere.  The content is used only to infer
intent (a one-line summary) and is not persisted verbatim by this module.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "TranscriptMessage",
    "read_transcript",
    "find_transcripts",
    "extract_intent",
]


@dataclass(frozen=True, slots=True)
class TranscriptMessage:
    """One message from a coding-agent conversation."""

    role: str  # "user", "human", "assistant", "system", etc.
    content: str
    ts: float | None  # epoch seconds if the transcript carries a timestamp
    index: int  # 0-based position in the transcript


def _parse_line(line: str, index: int) -> TranscriptMessage | None:
    """Parse one JSONL line into a message, or None if it doesn't look like one."""
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    role = obj.get("role")
    if not isinstance(role, str):
        return None
    # Content can be a string or a list of content blocks (Claude API style).
    raw_content = obj.get("content", "")
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        content = "\n".join(parts)
    elif isinstance(raw_content, str):
        content = raw_content
    else:
        content = str(raw_content)
    ts_raw = obj.get("timestamp") or obj.get("ts") or obj.get("created_at")
    ts: float | None = None
    if isinstance(ts_raw, (int, float)):
        ts = float(ts_raw)
    return TranscriptMessage(role=role, content=content, ts=ts, index=index)


def read_transcript(path: str | Path) -> tuple[TranscriptMessage, ...]:
    """Read a JSONL transcript file and return its messages in order."""
    p = Path(path)
    if not p.is_file():
        return ()
    messages: list[TranscriptMessage] = []
    try:
        raw = p.read_bytes()
    except OSError:
        return ()
    for i, line in enumerate(raw.split(b"\n")):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            text = stripped.decode("utf-8")
        except UnicodeDecodeError:
            continue
        msg = _parse_line(text, i)
        if msg is not None:
            messages.append(msg)
    return tuple(messages)


def find_transcripts(
    project_root: str | Path,
    *,
    claude_home: str | Path | None = None,
) -> tuple[Path, ...]:
    """Find transcript files that may belong to ``project_root``.

    Claude Code stores transcripts under ``~/.claude/projects/<hash>/``.  This
    scans for JSONL files there, sorted by modification time (newest first).
    Returns an empty tuple if the directory doesn't exist or has no transcripts.
    """
    if claude_home is None:
        claude_home = Path.home() / ".claude"
    else:
        claude_home = Path(claude_home)
    projects_dir = claude_home / "projects"
    if not projects_dir.is_dir():
        return ()
    # Claude Code uses the absolute path of the project as part of the directory
    # name (with slashes replaced by hyphens).  Look for directories that contain
    # the project root's name.
    root_abs = str(Path(project_root).resolve())
    root_name = Path(project_root).resolve().name
    candidates: list[Path] = []
    try:
        for entry in os.scandir(projects_dir):
            if not entry.is_dir():
                continue
            # Match by: the directory name contains the project folder name, or
            # the full path encoded with hyphens replacing slashes.
            encoded = root_abs.replace(os.sep, "-").lstrip("-")
            if root_name in entry.name or encoded in entry.name:
                for sub in Path(entry.path).iterdir():
                    if sub.suffix == ".jsonl" and sub.is_file():
                        candidates.append(sub)
    except OSError:
        return ()
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return tuple(candidates)


# Intent extraction heuristics.
_TRIVIAL = re.compile(
    r"^(y(es)?|no?|ok(ay)?|sure|thanks?|thank you|lgtm|done|k|yep|nope|stop|go|continue|proceed)\s*[.!?]*$",
    re.IGNORECASE,
)
_MIN_INTENT_WORDS = 4


def _is_intent(msg: TranscriptMessage) -> bool:
    """True if this message looks like a task description, not a bare acknowledgement."""
    if msg.role not in ("user", "human"):
        return False
    text = msg.content.strip()
    if not text or _TRIVIAL.match(text):
        return False
    return len(text.split()) >= _MIN_INTENT_WORDS


def extract_intent(messages: tuple[TranscriptMessage, ...]) -> str | None:
    """The developer's most recent stated intent, or None if none was found.

    Returns the full text of the last user message that looks like a task
    description (at least ``_MIN_INTENT_WORDS`` words, not a bare "yes"/"ok").
    """
    for msg in reversed(messages):
        if _is_intent(msg):
            return msg.content.strip()
    return None


def latest_intent(
    project_root: str | Path,
    *,
    claude_home: str | Path | None = None,
) -> str | None:
    """Convenience: find the newest transcript and extract its intent."""
    transcripts = find_transcripts(project_root, claude_home=claude_home)
    for t in transcripts:
        messages = read_transcript(t)
        intent = extract_intent(messages)
        if intent is not None:
            return intent
    return None
