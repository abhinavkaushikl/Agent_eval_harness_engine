"""JSON-RPC 2.0 over stdio for MCP revision 2026-07-28 — the only module that knows the wire.

Decision EL-007 fixes the seam: ``evalloop/mcp/`` is the single place in the project that knows
JSON-RPC, ``_meta``, wire error codes or ``resultType``. Everything downstream (EL-307, EL-310,
later tracks) touches the typed façade in ``facade.py``, which carries no wire concept, so if the
spec revs, this module changes and nothing else does. A test greps the rest of the tree to prove it.

**This builds revision 2026-07-28, not the handshake the ticket describes.** EL-007: that revision
*removed* ``initialize`` / ``notifications/initialized`` — "MCP is stateless as of 2026-07-28; there
is no handshake to make work," and EL-301's "handshake" done-when "needs rewording before EL-301
starts." So instead of a stateful handshake this module implements what 2026-07-28 actually says:

* **Every request is self-describing.** Its ``params._meta`` carries
  ``io.modelcontextprotocol/protocolVersion`` and ``io.modelcontextprotocol/clientCapabilities``
  (both **required** — a server MUST reject a request missing one with ``-32602``), and SHOULD carry
  ``io.modelcontextprotocol/clientInfo``.
* **Every result carries ``resultType``** (required in 2026-07-28); a result without it is malformed.
* **``server/discover`` replaces ``initialize``** as the mandatory "who are you / what do you
  support" call. Version agreement is checked against what discovery reports, not negotiated in a
  handshake that no longer exists.

Framing is newline-delimited JSON (one UTF-8 JSON object per line, no embedded newlines), the
stdio transport MCP uses. Content-Length framing (that is LSP) is deliberately not used.

**Interpretation flagged for review.** EL-007 names the 2026-07-28 facts above but the exact field
schema of ``server/discover``'s result is in ``schema/2026-07-28/schema.ts``, which this repo does
not carry. The ``server/discover`` payload shape here (``serverInfo`` / ``protocolVersions`` /
``capabilities``) is a reasonable reading used by both this client and the test's reference server,
so the two interoperate; it must be checked against the real schema before talking to a live server.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

PROTOCOL_REVISION = "2026-07-28"
JSONRPC_VERSION = "2.0"

# The required/optional per-request _meta keys (EL-007). Namespaced exactly as the spec writes them.
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# JSON-RPC 2.0 error codes, plus the one the spec singles out for a missing required _meta field.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class WireError(Exception):
    """A problem on the wire. Subclasses are the typed taxonomy the façade re-exports."""


class MalformedMessage(WireError):
    """A frame that is not UTF-8 JSON, not a JSON-RPC object, or missing a required field."""


class ServerError(WireError):
    """The peer returned a JSON-RPC error object. Carries the code and message verbatim."""

    def __init__(self, code: int, message: str, data: object = None) -> None:
        super().__init__(f"server error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


def _meta(capabilities: Mapping[str, object], client_info: Mapping[str, str] | None) -> dict[str, Any]:
    """The ``_meta`` every request carries: the pinned version and client capabilities, info if given."""
    block: dict[str, Any] = {
        META_PROTOCOL_VERSION: PROTOCOL_REVISION,
        META_CLIENT_CAPABILITIES: dict(capabilities),
    }
    if client_info is not None:
        block[META_CLIENT_INFO] = dict(client_info)
    return block


def encode_request(
    request_id: int,
    method: str,
    params: Mapping[str, object] | None,
    *,
    capabilities: Mapping[str, object],
    client_info: Mapping[str, str] | None,
) -> bytes:
    """One newline-delimited JSON-RPC request frame, with the required ``_meta`` attached to params."""
    merged: dict[str, Any] = dict(params or {})
    merged["_meta"] = _meta(capabilities, client_info)
    message = {"jsonrpc": JSONRPC_VERSION, "id": request_id, "method": method, "params": merged}
    return (json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode_message(line: bytes) -> dict[str, Any]:
    """Parse one frame. Raises :class:`MalformedMessage` for anything that is not a JSON-RPC object."""
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MalformedMessage(f"frame is not UTF-8: {error}") from error
    try:
        value = json.loads(text)
    except ValueError as error:
        raise MalformedMessage(f"frame is not JSON: {error}") from error
    if not isinstance(value, dict):
        raise MalformedMessage(f"frame is not a JSON object: {type(value).__name__}")
    if value.get("jsonrpc") != JSONRPC_VERSION:
        raise MalformedMessage(f"frame is not JSON-RPC {JSONRPC_VERSION}: {value.get('jsonrpc')!r}")
    return value


def result_of(message: Mapping[str, Any], expected_id: int) -> dict[str, Any]:
    """The ``result`` of a response, after checking the id, raising on an error object, and
    requiring ``resultType`` (mandatory in 2026-07-28)."""
    if "error" in message:
        error = message["error"]
        if not isinstance(error, dict) or "code" not in error or "message" not in error:
            raise MalformedMessage(f"error object is malformed: {error!r}")
        raise ServerError(int(error["code"]), str(error["message"]), error.get("data"))
    if message.get("id") != expected_id:
        raise MalformedMessage(f"response id {message.get('id')!r} does not match request {expected_id}")
    result = message.get("result")
    if not isinstance(result, dict):
        raise MalformedMessage("response has no result object")
    if "resultType" not in result:
        raise MalformedMessage("result is missing the required 'resultType' (2026-07-28)")
    return result


def is_response(message: Mapping[str, Any]) -> bool:
    """True for a response to a request (has an id and result/error); False for a notification."""
    return "id" in message and message["id"] is not None and ("result" in message or "error" in message)
