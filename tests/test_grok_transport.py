"""The OpenAI-compatible transport (Groq / xAI) as an adapter over the Anthropic client seam.

The load-bearing proofs, all without a network or a key: an Anthropic-format request is translated
to an OpenAI chat request (Bearer auth, system folded into a leading message), the OpenAI reply is
translated back into exactly what the real ``LLMClient`` parser expects, and a full round trip
through that client returns the model's text and token usage. No ``openai``/``groq`` SDK is imported.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from evalloop.capability.llm import (
    Clearance,
    HTTPReply,
    LLMClient,
    LLMRequest,
    Message,
    MissingCredential,
    RetryPolicy,
)
from evalloop.capability.grok import GROQ_API_KEY_VARIABLE, OpenAICompatibleTransport

_OK_REPLY = {
    "model": "llama-3.1-8b-instant",
    "choices": [{"message": {"role": "assistant", "content": "def test_x():\n    assert True\n"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 42, "completion_tokens": 17},
}


class _Capture:
    """A fake opener: records the outgoing request, returns a canned OpenAI-shaped reply."""

    def __init__(self, reply: dict[str, object], status: int = 200) -> None:
        self.reply = reply
        self.status = status
        self.seen_url: str | None = None
        self.seen_headers: Mapping[str, str] = {}
        self.seen_body: dict[str, object] = {}

    def __call__(self, request: object, timeout: float) -> HTTPReply:
        self.seen_url = request.full_url  # type: ignore[attr-defined]
        self.seen_headers = {k.lower(): v for k, v in request.headers.items()}  # type: ignore[attr-defined]
        self.seen_body = json.loads(request.data)  # type: ignore[attr-defined]
        return HTTPReply(status=self.status, headers={}, body=json.dumps(self.reply).encode())


def _anthropic_body() -> bytes:
    return LLMRequest(
        model_id="llama-3.1-8b-instant",
        max_tokens=256,
        messages=(Message(role="user", content="write a test"),),
        system="You are a test author.",
    ).body()


def test_request_is_translated_to_openai_chat_with_bearer_auth() -> None:
    cap = _Capture(_OK_REPLY)
    transport = OpenAICompatibleTransport("gsk_test", opener=cap)
    transport.post(_anthropic_body(), timeout=5.0)
    assert cap.seen_url == "https://api.groq.com/openai/v1/chat/completions"
    assert cap.seen_headers["authorization"] == "Bearer gsk_test"
    # system folded into a leading system message, then the user turn
    roles = [m["role"] for m in cap.seen_body["messages"]]  # type: ignore[index]
    assert roles == ["system", "user"]
    assert cap.seen_body["model"] == "llama-3.1-8b-instant"


def test_reply_is_translated_into_the_anthropic_shape_the_client_parses() -> None:
    cap = _Capture(_OK_REPLY)
    transport = OpenAICompatibleTransport("gsk_test", opener=cap)
    reply = transport.post(_anthropic_body(), timeout=5.0)
    doc = json.loads(reply.body)
    assert doc["content"] == [{"type": "text", "text": "def test_x():\n    assert True\n"}]
    assert doc["usage"] == {"input_tokens": 42, "output_tokens": 17}


def test_full_round_trip_through_the_real_client() -> None:
    cap = _Capture(_OK_REPLY)
    transport = OpenAICompatibleTransport("gsk_test", opener=cap)
    client = LLMClient(
        transport,
        RetryPolicy(max_attempts=1, base_delay=0.0, max_delay=0.0, request_timeout=5.0, total_timeout=5.0),
        jitter_seed=0,
        sleep=lambda _s: None,
    )
    request = LLMRequest(
        model_id="llama-3.1-8b-instant",
        max_tokens=256,
        messages=(Message(role="user", content="write a test"),),
    )
    response = client.complete(request, clearance=Clearance(granted_by="test", reason="unit"))
    assert "assert True" in response.text
    assert response.usage.input_tokens == 42
    assert response.usage.output_tokens == 17


def test_from_environment_requires_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GROQ_API_KEY_VARIABLE, raising=False)
    with pytest.raises(MissingCredential):
        OpenAICompatibleTransport.groq()
    monkeypatch.setenv(GROQ_API_KEY_VARIABLE, "gsk_live")
    transport = OpenAICompatibleTransport.groq()
    assert "api.groq.com" in transport.url
