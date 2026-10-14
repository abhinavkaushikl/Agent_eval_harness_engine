"""MCP protocol core (decision EL-007): the only package that knows the wire.

Standard library only, no SDK. Pinned to revision **2026-07-28**, stdio transport only (HTTP is a
later ticket). Downstream code imports the typed façade from here and never a wire concept:

    from evalloop.mcp import StdioClient, Tool, ToolResult, ToolCaller, McpError

This is the MCP **client** — EvalLoop consuming a server. The EvalLoop MCP *server*
(``evaluate``/``verify_claim``) is gated behind Gate 3 (decision EL-008) and is not here.
"""

from __future__ import annotations

from evalloop.mcp.client import PROTOCOL_REVISION, StdioClient
from evalloop.mcp.facade import (
    Content,
    Discoverable,
    McpError,
    ProtocolViolation,
    ProtocolVersionMismatch,
    ServerInfo,
    Tool,
    ToolCaller,
    ToolFailed,
    ToolResult,
    TransportClosed,
)

__all__ = [
    "PROTOCOL_REVISION",
    "Content",
    "Discoverable",
    "McpError",
    "ProtocolViolation",
    "ProtocolVersionMismatch",
    "ServerInfo",
    "StdioClient",
    "Tool",
    "ToolCaller",
    "ToolFailed",
    "ToolResult",
    "TransportClosed",
]
