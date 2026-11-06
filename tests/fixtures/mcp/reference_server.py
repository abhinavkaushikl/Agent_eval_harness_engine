"""A standard-library MCP server (revision 2026-07-28) for testing the client. No network, no SDK.

Speaks newline-delimited JSON-RPC over stdio: reads one JSON object per line from stdin, writes one
per line to stdout, logs nothing (stderr reserved). A mode argument drives the failure paths the
test exercises:

    good (default) · bad-version · no-resulttype · malformed · chatty

It validates the per-request ``_meta`` the spec requires and rejects a request missing the protocol
version with ``-32602``. Tools: ``echo``, ``add``, ``reflect_meta`` (returns the protocol version it
was sent, proving the client attached it), and ``boom`` (returns a JSON-RPC error). Prompts (EL-310):
``summarize`` (one required argument), ``greeting`` (none, and carries a planted credential so the
redactor is exercised over a real server) and ``picture`` (an image block, so a non-text prompt is
skipped).
"""

from __future__ import annotations

import json
import sys

PROTOCOL = "2026-07-28"
META_PROTOCOL = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"


def _send(obj: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _ok(request_id: object, result: dict[str, object], mode: str) -> dict[str, object]:
    if mode != "no-resulttype":
        result = {"resultType": result.get("resultType", "result"), **result}
    else:
        result.pop("resultType", None)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _discover(mode: str) -> dict[str, object]:
    versions = ["2099-01-01"] if mode == "bad-version" else [PROTOCOL]
    return {
        "resultType": "discover",
        META_SERVER_INFO: {"name": "reference", "version": "1.0"},
        "protocolVersions": versions,
        "capabilities": {"prompts": {}, "tools": {}},
    }


_TOOLS = [
    {"name": "echo", "description": "echo text", "inputSchema": {"type": "object"}},
    {"name": "add", "description": "add two ints", "inputSchema": {"type": "object"}},
    {"name": "reflect_meta", "description": "return the protocol version received", "inputSchema": {"type": "object"}},
    {"name": "boom", "description": "always errors", "inputSchema": {"type": "object"}},
]


_PROMPTS = [
    {
        "name": "summarize",
        "description": "summarize a document",
        "arguments": [{"name": "document", "description": "the text to summarize", "required": True}],
    },
    {"name": "greeting", "description": "a fixed system greeting"},
    {"name": "picture", "description": "an image-only prompt"},
]


def _get_prompt(params: dict[str, object], request_id: object, mode: str) -> dict[str, object]:
    name = params.get("name")
    args = params.get("arguments") or {}
    assert isinstance(args, dict)
    if name == "summarize":
        if "document" not in args:
            return _error(request_id, -32602, "missing required argument: document")
        messages = [
            {"role": "user", "content": {"type": "text", "text": f"Summarize in one sentence:\n{args['document']}"}}
        ]
    elif name == "greeting":
        messages = [
            {"role": "user", "content": {"type": "text", "text": "You are a helpful support agent."}},
            {"role": "assistant", "content": {"type": "text", "text": "Use api_key=sk-test-0123456789abcdefghij to call."}},
        ]
    elif name == "picture":
        messages = [{"role": "user", "content": {"type": "image", "data": "AAAA", "mimeType": "image/png"}}]
    else:
        return _error(request_id, -32602, f"no such prompt: {name}")
    return _ok(request_id, {"resultType": "prompt", "description": f"the {name} prompt", "messages": messages}, mode)


def _call(params: dict[str, object], meta: dict[str, object], request_id: object, mode: str) -> dict[str, object]:
    name = params.get("name")
    args = params.get("arguments") or {}
    if name == "echo":
        content = [{"type": "text", "text": str(args.get("text", ""))}]
    elif name == "add":
        content = [{"type": "text", "text": str(int(args.get("a", 0)) + int(args.get("b", 0)))}]
    elif name == "reflect_meta":
        content = [{"type": "text", "text": str(meta.get(META_PROTOCOL, "<none>"))}]
    elif name == "boom":
        return _error(request_id, -32603, "boom")
    else:
        return _ok(request_id, {"resultType": "toolResult", "content": [{"type": "text", "text": "no such tool"}], "isError": True}, mode)
    return _ok(request_id, {"resultType": "toolResult", "content": content, "isError": False}, mode)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "good"
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8").strip()
        if not line:
            continue
        message = json.loads(line)
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        meta = params.get("_meta") or {}

        if mode == "malformed":
            sys.stdout.write("this is not json\n")
            sys.stdout.flush()
            return
        if mode == "chatty":
            _send({"jsonrpc": "2.0", "method": "notifications/message", "params": {}})

        if META_PROTOCOL not in meta:
            _send(_error(request_id, -32602, f"missing required {META_PROTOCOL}"))
            continue
        if method == "server/discover":
            _send(_ok(request_id, _discover(mode), mode))
        elif method == "tools/list":
            _send(_ok(request_id, {"resultType": "toolList", "tools": _TOOLS}, mode))
        elif method == "tools/call":
            _send(_call(params, meta, request_id, mode))
        elif method == "prompts/list":
            _send(_ok(request_id, {"resultType": "promptList", "prompts": _PROMPTS}, mode))
        elif method == "prompts/get":
            _send(_get_prompt(params, request_id, mode))
        else:
            _send(_error(request_id, -32601, f"method not found: {method}"))


if __name__ == "__main__":
    main()
