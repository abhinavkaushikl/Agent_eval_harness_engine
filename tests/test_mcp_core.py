"""The MCP protocol core against a stdlib reference server — no network, no SDK, no external server.

Built to revision 2026-07-28 (decision EL-007), which removed the ``initialize`` handshake the
ticket describes; see EL-301-REPORT.md for that discrepancy. These tests exercise the real
2026-07-28 shape: ``server/discover``, per-request ``_meta``, and a required ``resultType``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from evalloop.mcp import (
    PROTOCOL_REVISION,
    ProtocolViolation,
    ProtocolVersionMismatch,
    ServerInfo,
    StdioClient,
    Tool,
    ToolCaller,
    ToolFailed,
)

_SERVER = Path(__file__).resolve().parent / "fixtures" / "mcp" / "reference_server.py"
_EVALLOOP = Path(__file__).resolve().parent.parent / "evalloop"


def _client(mode: str = "good") -> Iterator[StdioClient]:
    with StdioClient.launch([sys.executable, str(_SERVER), mode]) as client:
        yield client


@pytest.fixture
def client() -> Iterator[StdioClient]:
    yield from _client("good")


# -- the pinned revision ---------------------------------------------------------------


def test_the_revision_is_pinned() -> None:
    assert PROTOCOL_REVISION == "2026-07-28"


# -- discover replaces the (removed) handshake -----------------------------------------


def test_discover_reports_the_server_and_its_revision(client: StdioClient) -> None:
    info = client.discover()
    assert isinstance(info, ServerInfo)
    assert info.name == "reference" and info.version == "1.0"
    assert PROTOCOL_REVISION in info.protocol_versions
    assert "tools" in info.capabilities


def test_a_server_without_our_revision_fails_naming_both() -> None:
    for client in _client("bad-version"):
        with pytest.raises(ProtocolVersionMismatch) as caught:
            client.discover()
    message = str(caught.value)
    assert PROTOCOL_REVISION in message and "2099-01-01" in message  # both named


# -- tool listing and calls (the done-when) --------------------------------------------


def test_list_tools(client: StdioClient) -> None:
    names = {t.name for t in client.list_tools()}
    assert {"echo", "add", "reflect_meta", "boom"} <= names
    assert all(isinstance(t, Tool) for t in client.list_tools())


def test_call_tool_echo(client: StdioClient) -> None:
    result = client.call_tool("echo", {"text": "hello"})
    assert result.text == "hello" and result.is_error is False


def test_call_tool_add(client: StdioClient) -> None:
    assert client.call_tool("add", {"a": 2, "b": 3}).text == "5"


def test_every_request_carries_the_protocol_version_in_meta(client: StdioClient) -> None:
    # The server reflects back the _meta protocol version it received, proving the client attached it.
    assert client.call_tool("reflect_meta", {}).text == PROTOCOL_REVISION


def test_a_client_satisfies_the_tool_caller_seam(client: StdioClient) -> None:
    assert isinstance(client, ToolCaller)  # downstream (EL-307) depends only on this Protocol


# -- errors become typed, never a crash or a bare dict ---------------------------------


def test_a_server_error_object_is_a_typed_error(client: StdioClient) -> None:
    with pytest.raises(ToolFailed) as caught:
        client.call_tool("boom", {})
    assert caught.value.code == -32603 and "boom" in caught.value.message


def test_an_unknown_tool_is_an_error_result_not_a_crash(client: StdioClient) -> None:
    result = client.call_tool("does_not_exist", {})
    assert result.is_error is True


def test_a_result_missing_result_type_is_rejected() -> None:
    for client in _client("no-resulttype"):
        with pytest.raises(ProtocolViolation, match="resultType"):
            client.discover()


def test_a_malformed_frame_is_rejected() -> None:
    for client in _client("malformed"):
        with pytest.raises(ProtocolViolation):
            client.discover()


def test_a_notification_before_the_reply_is_skipped() -> None:
    for client in _client("chatty"):
        assert client.call_tool("echo", {"text": "still works"}).text == "still works"


# -- lifecycle -------------------------------------------------------------------------


def test_the_context_manager_reaps_the_process() -> None:
    with StdioClient.launch([sys.executable, str(_SERVER)]) as client:
        client.discover()
        proc = client._process
    assert proc.poll() is not None  # exited, not orphaned


# -- the EL-007 seam: wire concepts live only under evalloop/mcp/ ----------------------


def test_wire_concepts_appear_only_under_evalloop_mcp() -> None:
    pattern = re.compile(r"jsonrpc|_meta|resultType", re.IGNORECASE)
    leaked = [
        str(path.relative_to(_EVALLOOP))
        for path in _EVALLOOP.rglob("*.py")
        if path.parts[path.parts.index("evalloop") + 1 :][:1] != ("mcp",)
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert leaked == [], f"wire concepts leaked outside evalloop/mcp/: {leaked}"


def test_the_mcp_package_imports_only_the_standard_library() -> None:
    banned = re.compile(r"^\s*(?:import|from)\s+(?!evalloop|__future__)([a-zA-Z0-9_]+)", re.MULTILINE)
    stdlib_ok = {"json", "os", "subprocess", "typing", "dataclasses", "collections", "types", "enum", "sys"}
    for path in (_EVALLOOP / "mcp").rglob("*.py"):
        for mod in banned.findall(path.read_text(encoding="utf-8")):
            assert mod in stdlib_ok, f"{path.name} imports non-stdlib {mod!r}"
