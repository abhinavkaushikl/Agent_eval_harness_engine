"""The MCP connector: an external MCP server as a read-only Connector, through broker and envelope.

The load-bearing proofs: the EL-301 stdlib reference server (over stdio, no network) is wrapped as a
Connector whose probe/describe/read all work; a read-only query returns rows through read(); and a
write-shaped query is stopped by the envelope *before* any tool call is sent — an MCP tool is not a
hole in the read-only contract. A grep test keeps every wire concept inside evalloop/mcp/.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.envelope import AuditLog, ReadOnlyEnvelope, ReadOnlyViolation
from evalloop.connect.mcp_connector import MCPConnector
from evalloop.connect.protocol import Connector, NotAuthorized, ProbeResult, Schema
from evalloop.mcp import Content, ServerInfo, StdioClient, Tool as McpTool, ToolResult
from evalloop.vocab import Tool

_SERVER = Path(__file__).resolve().parent / "fixtures" / "mcp" / "reference_server.py"
_ENDPOINT = "mcp://reference"


def _granted_broker(endpoint: str = _ENDPOINT) -> CapabilityBroker:
    broker = CapabilityBroker()
    broker.grant(Tool.db_connection, granted_by="test", reason="read-only MCP server", endpoint=endpoint, caps=Caps(max_rows=100))
    return broker


@pytest.fixture
def live_client() -> Iterator[StdioClient]:
    with StdioClient.launch([sys.executable, str(_SERVER)]) as client:
        yield client


# -- a real reference server, wrapped as a Connector -----------------------------------


def test_wrapped_server_is_a_connector(live_client: StdioClient) -> None:
    conn = MCPConnector(live_client, broker=_granted_broker(), endpoint=_ENDPOINT)
    assert isinstance(conn, Connector)


def test_probe_reaches_the_server(live_client: StdioClient) -> None:
    conn = MCPConnector(live_client, broker=_granted_broker(), endpoint=_ENDPOINT)
    result = conn.probe()
    assert isinstance(result, ProbeResult)
    assert result.reachable is True and result.read_only is True
    assert "reference" in result.detail


def test_describe_lists_the_servers_tools_as_structure(live_client: StdioClient) -> None:
    conn = MCPConnector(live_client, broker=_granted_broker(), endpoint=_ENDPOINT)
    schema = conn.describe()
    assert isinstance(schema, Schema)
    names = {t.name for t in schema.tables}
    assert {"echo", "add", "reflect_meta", "boom"} <= names


def test_read_returns_rows_through_the_server(live_client: StdioClient) -> None:
    # echo is the read tool here; a SELECT-shaped query passes the envelope and the server echoes it.
    conn = MCPConnector(
        live_client, broker=_granted_broker(), endpoint=_ENDPOINT, read_tool="echo", query_arg="text"
    )
    res = conn.read("SELECT 1 FROM anywhere")
    assert [tuple(r) for r in res.rows] == [("SELECT 1 FROM anywhere",)]
    assert res.shape.row_count == 1


# -- an MCP tool is not a hole in the read-only contract -------------------------------


class _CountingClient:
    """A fake MCP client that records whether a tool was ever called. Satisfies the façade seam."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def discover(self) -> ServerInfo:
        return ServerInfo(name="fake", version="0", protocol_versions=("2026-07-28",), capabilities=("tools",))

    def list_tools(self) -> tuple[McpTool, ...]:
        return (McpTool(name="query", description="run SQL", input_schema={"type": "object"}),)

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolResult:
        self.calls.append(name)
        return ToolResult(content=(Content(kind="text", text="[]"),), is_error=False)


def test_a_write_shaped_query_is_rejected_before_any_tool_call() -> None:
    fake = _CountingClient()
    conn = MCPConnector(fake, broker=_granted_broker(), endpoint=_ENDPOINT, read_tool="query", query_arg="sql")
    with pytest.raises(ReadOnlyViolation):
        conn.read("DROP TABLE users")
    assert fake.calls == [], "the write-shaped query reached the MCP server"


def test_a_read_shaped_query_does_reach_the_tool() -> None:
    fake = _CountingClient()
    conn = MCPConnector(fake, broker=_granted_broker(), endpoint=_ENDPOINT, read_tool="query", query_arg="sql")
    conn.read("SELECT * FROM users")
    assert fake.calls == ["query"]


# -- the broker gates every call -------------------------------------------------------


def test_an_ungranted_endpoint_is_refused() -> None:
    fake = _CountingClient()
    conn = MCPConnector(fake, broker=CapabilityBroker(), endpoint=_ENDPOINT)
    with pytest.raises(NotAuthorized):
        conn.read("SELECT 1")
    with pytest.raises(NotAuthorized):
        conn.describe()
    assert fake.calls == []


# -- rows are parsed from a JSON-speaking read tool ------------------------------------


def test_json_rows_are_parsed() -> None:
    class _JsonClient(_CountingClient):
        def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolResult:
            self.calls.append(name)
            return ToolResult(content=(Content(kind="text", text='[[1, "alice"], [2, "bob"]]'),), is_error=False)

    conn = MCPConnector(_JsonClient(), broker=_granted_broker(), endpoint=_ENDPOINT, query_arg="sql")
    res = conn.read("SELECT id, name FROM users")
    assert [tuple(r) for r in res.rows] == [(1, "alice"), (2, "bob")]


# -- EL-007: no wire concept leaks out of evalloop/mcp/ --------------------------------


def test_no_wire_concept_outside_the_mcp_package() -> None:
    root = Path(__file__).resolve().parent.parent / "evalloop"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.parts[path.parts.index("evalloop") + 1] == "mcp":
            continue  # the one package allowed to know the wire
        text = path.read_text(encoding="utf-8")
        for needle in ("jsonrpc", "_meta", "resultType", "json-rpc"):
            if needle in text:
                offenders.append(f"{path}: {needle}")
    assert offenders == [], f"wire concepts leaked outside evalloop/mcp/: {offenders}"


def test_grep_confirms_wire_terms_only_under_mcp() -> None:
    root = Path(__file__).resolve().parent.parent / "evalloop"
    hits = subprocess.run(
        ["grep", "-rln", "--include=*.py", "-e", "jsonrpc", "-e", "resultType", "-e", "_meta", str(root)],
        capture_output=True,
        text=True,
    ).stdout.split()
    assert all("/mcp/" in h for h in hits), f"wire terms found outside evalloop/mcp/: {hits}"
