"""Frozen vocabularies: situations and tools.

``Situation`` and ``Tool`` are the two spellings every record file, every
``match()`` call and every rendered plan line share. The parsers here are the
only sanctioned way to turn a string from a record file into a member, so that a
misspelling fails at load time with a message naming the bad value, rather than
matching nothing silently -- the failure ``CLAUDE.md`` section 6 calls the most
important correctness decision in M0.

The parsers are strict by design: exact value match, no case folding, no
whitespace tolerance and no prose normalisation. The master lookup's situation
cells are English prose ("Output is code / SQL / an API call"), and mapping prose
to a member is a classifier's job (M1), not a vocabulary's.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from evalloop.vocab.situations import Situation
from evalloop.vocab.tools import Tool

__all__ = ["Situation", "Tool", "parse_situation", "parse_tool"]

_SITUATIONS: Mapping[str, Situation] = MappingProxyType(
    {member.value: member for member in Situation}
)
_TOOLS: Mapping[str, Tool] = MappingProxyType({member.value: member for member in Tool})


def _unknown(kind: str, raw: object, valid: Mapping[str, object]) -> ValueError:
    """The message a human reads while debugging a record file at 2am."""
    options = ", ".join(sorted(valid))
    return ValueError(
        f"unknown {kind} {raw!r}. The {len(valid)} valid {kind} values are: {options}"
    )


def parse_situation(value: str) -> Situation:
    """Return the ``Situation`` whose value is exactly ``value``.

    Raises ``ValueError`` naming ``value`` and every valid option, sorted.
    """
    try:
        return _SITUATIONS[value]
    except (KeyError, TypeError):
        raise _unknown("situation", value, _SITUATIONS) from None


def parse_tool(value: str) -> Tool:
    """Return the ``Tool`` whose value is exactly ``value``.

    Raises ``ValueError`` naming ``value`` and every valid option, sorted.
    """
    try:
        return _TOOLS[value]
    except (KeyError, TypeError):
        raise _unknown("tool", value, _TOOLS) from None
