"""The typed façade downstream tracks touch — frozen dataclasses, two Protocols, typed errors.

Nothing here names a wire concept (no JSON-RPC, no ``_meta``, no ``resultType``). EL-307, EL-310 and
later tracks import *only* from here, so a spec revision changes ``wire.py``/``client.py`` and never
them. The two Protocols are the seam: :class:`Discoverable` (who the server is and what it supports)
and :class:`ToolCaller` (list and call tools). The stdio client implements both.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class McpError(Exception):
    """Base of the MCP error taxonomy. Every failure below is one of these, never a bare dict."""


class ProtocolViolation(McpError):
    """The peer sent something the protocol forbids: a malformed frame, a result with no type."""


class ToolFailed(McpError):
    """The server returned an error for a call (a JSON-RPC error object). Carries code and message."""

    def __init__(self, code: int, message: str, data: object = None) -> None:
        super().__init__(f"the server returned an error ({code}): {message}")
        self.code = code
        self.message = message
        self.data = data


class ProtocolVersionMismatch(McpError):
    """The server does not support the revision this client is pinned to. Names both, per the ticket."""

    def __init__(self, required: str, offered: tuple[str, ...]) -> None:
        super().__init__(
            f"this client speaks MCP {required!r}; the server offers {list(offered)!r} and not {required!r}"
        )
        self.required = required
        self.offered = offered


class TransportClosed(McpError):
    """The server process ended, or its stream closed, before a reply arrived."""


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """What ``server/discover`` reports: who the server is, the revisions it speaks, its capabilities."""

    name: str
    version: str
    protocol_versions: tuple[str, ...]
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Content:
    """One block of a tool result. ``kind`` is 'text', 'image', … ; ``text`` is set for text blocks."""

    kind: str
    text: str | None


@dataclass(frozen=True, slots=True)
class Tool:
    """A tool the server offers. ``input_schema`` is the tool's own JSON Schema, passed through as data."""

    name: str
    description: str | None
    input_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of a call: its content blocks, and whether the server marked it an error."""

    content: tuple[Content, ...]
    is_error: bool

    @property
    def text(self) -> str:
        """The text blocks joined — what most tools return and most callers want."""
        return "".join(block.text for block in self.content if block.kind == "text" and block.text is not None)


@runtime_checkable
class Discoverable(Protocol):
    """The server's identity and supported revisions (2026-07-28's ``server/discover``)."""

    def discover(self) -> ServerInfo: ...


@runtime_checkable
class ToolCaller(Protocol):
    """List the tools a server offers, and call one. The seam EL-307 (and the grader) build on."""

    def list_tools(self) -> tuple[Tool, ...]: ...

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolResult: ...
