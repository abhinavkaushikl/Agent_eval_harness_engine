"""The text redactor at the connector boundary: credential-shaped strings out, before anything leaves.

Track V's safety spine: "Everything crosses the **redactor** at the boundary; nothing unredacted is
persisted." The envelope already redacts SQL for its audit log (:func:`~evalloop.connect.envelope.
redact_sql`). Documents and prompts (EL-310) are different: their text *is* the eval input, so it
cannot be reduced to structure. What must not pass is a credential sitting in it — a key pasted into
a prompt, a connection string in a design doc.

What it catches, and what it does not
-------------------------------------
Pattern-based, deliberately narrow, so prose survives intact:

* PEM private-key blocks;
* well-known key shapes — ``sk-…`` (OpenAI / Anthropic), ``gsk_…`` (Groq), AWS ``AKIA…`` access key
  ids, GitHub ``ghp_``/``gho_``/``ghs_``/``ghu_``/``github_pat_`` tokens, Slack ``xox?-`` tokens;
* the password in a URL's userinfo (``postgres://user:<redacted>@host``);
* the value of a ``key = value`` / ``key: value`` assignment whose key names a secret
  (``password``, ``secret``, ``token``, ``api_key``, …) and whose value is a single token of eight or
  more characters — the length floor keeps ``token: none`` and ``password: TBD`` readable.

It is **not** a PHI/PII detector. The PHI gate (fixture 20's open ruling) is not decided and is not
implemented here; a document carrying patient data passes through this redactor unchanged. Each
replacement is counted so the caller can report that redaction happened.
"""

from __future__ import annotations

import re

__all__ = ["REDACTED", "redact_secrets"]

REDACTED = "<redacted>"

_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)
_KEY_SHAPES = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|gsk_[A-Za-z0-9]{16,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r")"
)
_URL_PASSWORD = re.compile(r"(?P<head>\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)(?P<secret>[^\s@/]+)(?P<tail>@)")
_ASSIGNMENT = re.compile(
    r"(?P<head>\b[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)"
    r"[\w.-]*[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<secret>[^\s\"',;]{8,})",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace each credential-shaped span with ``<redacted>``. Returns the text and the count replaced."""
    count = 0

    def whole(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return REDACTED

    def keep_head(match: re.Match[str]) -> str:
        nonlocal count
        if match.group("secret") == REDACTED:
            return match.group(0)
        count += 1
        tail = match.groupdict().get("tail") or ""
        return f"{match.group('head')}{REDACTED}{tail}"

    text = _PEM.sub(whole, text)
    text = _KEY_SHAPES.sub(whole, text)
    text = _URL_PASSWORD.sub(keep_head, text)
    text = _ASSIGNMENT.sub(keep_head, text)
    return text, count
