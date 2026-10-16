"""Turn any external MCP server into a read-only :class:`~evalloop.connect.protocol.Connector`.

An MCP-exposed database or tool becomes an eval input through the same probe / describe / read
contract as the local SQLite connector (EL-306). Two decisions shape this file:

  * **EL-007 — only the typed façade is touched.** Everything here imports from
    :mod:`evalloop.mcp` (``StdioClient``, ``Tool``, ``ToolResult``, ``ToolCaller``, …). No wire
    concept — the RPC framing, the per-request protocol metadata, the typed result tags — appears
    outside ``evalloop/mcp/``, and a grep test keeps it that way.
  * **EL-008 — this is the MCP *client*.** EvalLoop consumes someone else's read-only server. The
    EvalLoop MCP *server* (``evaluate`` / ``verify_claim``) is gated behind Gate 3 and is not here.

An MCP tool is not a hole in the read-only contract: ``read(query)`` carries the query through the
envelope's three layers (EL-305) *before* any tool call leaves the process, so a write-shaped query
is rejected before it is sent. The capability itself (an MCP-exposed database, vector store, …) is
granted through the broker (EL-302); MCP is only the transport, never a capability of its own
(decision EL-002).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from evalloop.capability.broker import CapabilityBroker
from evalloop.connect.envelope import AuditEntry, AuditLog, Caps, ReadOnlyEnvelope, Result
from evalloop.connect.protocol import Column, ConnectorError, NotAuthorized, ProbeResult, Schema, Table
from evalloop.mcp import Discoverable, McpError, ServerInfo, Tool as McpTool, ToolCaller, ToolResult
from evalloop.vocab import Tool

__all__ = ["MCPConnector", "McpClient"]


@runtime_checkable
class McpClient(Discoverable, ToolCaller, Protocol):
    """What this connector needs of a server: discover it, list its tools, call one. The EL-301 seam."""


class _McpExecutor:
    """Adapts an MCP read tool to the envelope's ``Executor`` protocol.

    ``read_only`` is ``True`` because this executor only ever calls the one read tool it was given;
    the envelope's layer 1 is what guarantees the query itself carries no write.
    """

    read_only = True

    def __init__(self, caller: ToolCaller, *, read_tool: str, query_arg: str) -> None:
        self._caller = caller
        self._read_tool = read_tool
        self._query_arg = query_arg

    def run(self, sql: str, *, max_rows: int | None) -> Sequence[Sequence[object]]:
        result = self._caller.call_tool(self._read_tool, {self._query_arg: sql})
        if result.is_error:
            raise ConnectorError(f"the MCP read tool {self._read_tool!r} returned an error: {result.text}")
        return _result_to_rows(result)


def _result_to_rows(result: ToolResult) -> Sequence[Sequence[object]]:
    """Turn a tool result into rows. A JSON array of rows if the tool speaks that; else one text cell."""
    text = result.text
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return [(text,)]
    if isinstance(parsed, list):
        rows: list[Sequence[object]] = []
        for item in parsed:
            if isinstance(item, (list, tuple)):
                rows.append(tuple(item))
            elif isinstance(item, dict):
                rows.append(tuple(item.values()))
            else:
                rows.append((item,))
        return rows
    return [(parsed,)]


class MCPConnector:
    """probe / describe / read against an external MCP server, through the broker and the envelope."""

    def __init__(
        self,
        client: McpClient,
        *,
        broker: CapabilityBroker,
        endpoint: str,
        envelope: ReadOnlyEnvelope | None = None,
        tool: Tool = Tool.db_connection,
        read_tool: str = "query",
        query_arg: str = "sql",
    ) -> None:
        self.endpoint = endpoint
        self._client = client
        self._broker = broker
        self._tool = tool
        self._envelope = envelope if envelope is not None else ReadOnlyEnvelope(AuditLog())
        self._executor = _McpExecutor(client, read_tool=read_tool, query_arg=query_arg)

    # -- authorisation: the broker, before anything is sent -----------------------------

    def _authorize(self) -> Caps:
        decision = self._broker.check(self._tool, endpoint=self.endpoint)
        if not decision.granted or decision.grant is None:
            raise NotAuthorized(decision.reason or f"{self._tool.value} is not granted for {self.endpoint!r}")
        return decision.grant.caps

    # -- the three operations -----------------------------------------------------------

    def probe(self) -> ProbeResult:
        """Reachable, and read-only? Authorised, then the server's own discovery. No tools called."""
        self._authorize()
        try:
            info: ServerInfo = self._client.discover()
        except McpError as exc:
            self._log("probe", error=repr(exc))
            return ProbeResult(reachable=False, read_only=True, detail=f"unreachable: {exc}")
        self._log("probe")
        return ProbeResult(
            reachable=True,
            read_only=True,  # we only ever call the read tool; the envelope enforces it
            detail=f"MCP server {info.name} v{info.version}",
        )

    def describe(self) -> Schema:
        """The server's tools and their inputs, as structure. Lists tools; reads no rows."""
        self._authorize()
        tools: tuple[McpTool, ...] = self._client.list_tools()
        tables = tuple(Table(name=t.name, columns=_columns_of(t.input_schema)) for t in tools)
        self._log("describe")
        return Schema(tables=tables)

    def read(self, sql: str) -> Result:
        """Run a read-only query through the envelope, which gates it before any tool call is sent."""
        caps = self._authorize()
        return self._envelope.execute(sql, endpoint=self.endpoint, caps=caps, executor=self._executor)

    # -- helpers ------------------------------------------------------------------------

    def _log(self, operation: str, *, error: str | None = None) -> None:
        self._envelope.audit.append(
            AuditEntry(
                endpoint=self.endpoint,
                redacted_sql=f"<{operation}>",
                statement_kinds=(operation,),
                caps=Caps(),
                write_scope=None,
                result=None,
                error=error,
            )
        )


def _columns_of(input_schema: Mapping[str, object]) -> tuple[Column, ...]:
    """A tool's input parameters, as columns. A server stating no properties yields no columns."""
    properties = input_schema.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    columns: list[Column] = []
    for name, spec in properties.items():
        declared = ""
        if isinstance(spec, Mapping):
            value = spec.get("type")
            declared = str(value) if value is not None else ""
        columns.append(Column(name=str(name), type=declared))
    return tuple(columns)
