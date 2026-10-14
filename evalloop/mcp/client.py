"""The stdio MCP client: launch a server as a subprocess, speak 2026-07-28 over its pipes.

Standard library only (``subprocess`` + ``json`` via ``wire``), stdio transport only — HTTP is
deferred to its own ticket (EL-007, and the discrepancy reported with EL-301). The client translates
the wire (``wire.py``, dicts) into the façade (``facade.py``, dataclasses); callers see only the
façade.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import IO, Any

from evalloop.mcp import wire
from evalloop.mcp.facade import (
    Content,
    Discoverable,
    McpError,
    ProtocolVersionMismatch,
    ProtocolViolation,
    ServerInfo,
    Tool,
    ToolCaller,
    ToolFailed,
    ToolResult,
    TransportClosed,
)

__all__ = ["StdioClient", "PROTOCOL_REVISION"]

PROTOCOL_REVISION = wire.PROTOCOL_REVISION

# What this client advertises about itself on every request (EL-007: clientCapabilities required,
# clientInfo SHOULD). EvalLoop consumes read-only; it offers no capabilities of its own.
_CLIENT_CAPABILITIES: Mapping[str, object] = {}
_CLIENT_INFO: Mapping[str, str] = {"name": "evalloop", "version": "0"}
_MAX_SKIPPED = 1000  # notifications/other frames tolerated before a response, so a chatty server can't hang us


class StdioClient(ToolCaller, Discoverable):
    """A live connection to one MCP server over stdio. Use as a context manager; it reaps the process."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process
        self._next_id = 0

    @classmethod
    def launch(
        cls,
        command: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> StdioClient:
        """Start ``command`` as an MCP server subprocess wired to its stdin/stdout."""
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # the spec reserves stderr for the server's own logging
            cwd=os.fspath(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
        )
        return cls(process)

    # -- lifecycle --------------------------------------------------------------

    def __enter__(self) -> StdioClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the pipe and reap the process; terminate it if it does not exit promptly."""
        process = self._process
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()

    # -- the wire, kept entirely inside this module -----------------------------

    def _request(self, method: str, params: Mapping[str, object] | None = None) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        stdin = self._require(self._process.stdin, "stdin")
        stdout = self._require(self._process.stdout, "stdout")
        frame = wire.encode_request(
            request_id, method, params, capabilities=_CLIENT_CAPABILITIES, client_info=_CLIENT_INFO
        )
        try:
            stdin.write(frame)
            stdin.flush()
        except (BrokenPipeError, ValueError) as error:
            raise TransportClosed(f"could not send {method!r}: the server stream is closed ({error})") from error

        for _ in range(_MAX_SKIPPED):
            line = stdout.readline()
            if line == b"":
                raise TransportClosed(f"the server ended before replying to {method!r}")
            try:
                message = wire.decode_message(line)
            except wire.MalformedMessage as error:
                raise ProtocolViolation(str(error)) from error
            if not wire.is_response(message):
                continue  # a notification or a server-initiated frame; not our reply
            try:
                return wire.result_of(message, request_id)
            except wire.ServerError as error:
                raise ToolFailed(error.code, error.message, error.data) from error
            except wire.MalformedMessage as error:
                raise ProtocolViolation(str(error)) from error
        raise ProtocolViolation(f"server sent {_MAX_SKIPPED} frames without replying to {method!r}")

    @staticmethod
    def _require(stream: IO[bytes] | None, name: str) -> IO[bytes]:
        if stream is None:
            raise McpError(f"the subprocess has no {name} pipe")
        return stream

    # -- the façade -------------------------------------------------------------

    def discover(self) -> ServerInfo:
        """``server/discover`` — the 2026-07-28 replacement for ``initialize``. Checks the revision."""
        result = self._request("server/discover")
        info = result.get(wire.META_SERVER_INFO) or result.get("serverInfo") or {}
        versions = tuple(str(v) for v in result.get("protocolVersions", []))
        if PROTOCOL_REVISION not in versions:
            raise ProtocolVersionMismatch(PROTOCOL_REVISION, versions)
        capabilities = tuple(sorted(str(k) for k in result.get("capabilities", {})))
        return ServerInfo(
            name=str(info.get("name", "")),
            version=str(info.get("version", "")),
            protocol_versions=versions,
            capabilities=capabilities,
        )

    def list_tools(self) -> tuple[Tool, ...]:
        result = self._request("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise ProtocolViolation("tools/list did not return a 'tools' array")
        found: list[Tool] = []
        for raw in tools:
            if not isinstance(raw, dict) or "name" not in raw:
                raise ProtocolViolation(f"a tool entry is malformed: {raw!r}")
            schema = raw.get("inputSchema")
            found.append(
                Tool(
                    name=str(raw["name"]),
                    description=raw.get("description"),
                    input_schema=schema if isinstance(schema, dict) else {},
                )
            )
        return tuple(found)

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolResult:
        result = self._request("tools/call", {"name": name, "arguments": dict(arguments)})
        blocks_raw = result.get("content")
        if not isinstance(blocks_raw, list):
            raise ProtocolViolation("tools/call result has no 'content' array")
        blocks: list[Content] = []
        for raw in blocks_raw:
            if not isinstance(raw, dict) or "type" not in raw:
                raise ProtocolViolation(f"a content block is malformed: {raw!r}")
            kind = str(raw["type"])
            text = raw.get("text") if kind == "text" else None
            blocks.append(Content(kind=kind, text=str(text) if text is not None else None))
        return ToolResult(content=tuple(blocks), is_error=bool(result.get("isError", False)))
