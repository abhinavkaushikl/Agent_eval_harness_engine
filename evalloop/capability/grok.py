"""An OpenAI-compatible chat transport (Groq, xAI Grok, …) behind the Anthropic transport seam.

The LLM client speaks the Anthropic Messages wire format: :meth:`LLMRequest.body` serialises it, and
the client parses an Anthropic-shaped reply. Groq and xAI are OpenAI-chat-shaped instead. Rather
than fork the client, this transport conforms to the ``Transport`` protocol and **translates in both
directions**, so ``LLMClient``, ``Router``, ``LLMRequest`` and ``LLMResponse`` stay unchanged and no
Anthropic-only code is touched:

* a request arrives as Anthropic JSON (``model`` / ``max_tokens`` / ``messages`` / optional
  ``system``); it is reshaped into an OpenAI chat request (``system`` folded in as a leading
  ``role: "system"`` message) and POSTed with ``Authorization: Bearer``;
* the reply (``choices[0].message.content`` + ``usage.prompt_tokens/completion_tokens``) is reshaped
  into the Anthropic reply the client already parses (``content: [{type, text}]`` +
  ``usage: {input_tokens, output_tokens}``).

Groq (``api.groq.com``, keys ``gsk_…``) and xAI Grok (``api.x.ai``, keys ``xai-…``) are different
services that happen to share this wire format; pick the endpoint + credential that match your key.
Standard library only (``urllib``). The credential is read in exactly one place,
:meth:`OpenAICompatibleTransport.from_environment` — mirroring the Anthropic transport's
one-credential rule (``ARCHITECTURE.md`` §9).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from decimal import Decimal, InvalidOperation

from evalloop.capability.llm import HTTPReply, LLMClient, MissingCredential, RetryPolicy
from evalloop.capability.router import CostLedger, Job, ModelConfig, Router

__all__ = [
    "GROQ_MESSAGES_URL",
    "GROQ_API_KEY_VARIABLE",
    "XAI_MESSAGES_URL",
    "XAI_API_KEY_VARIABLE",
    "OpenAICompatibleTransport",
    "AuthoringUnavailable",
    "build_groq_router",
]

GROQ_MESSAGES_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY_VARIABLE = "GROQ_API_KEY"
XAI_MESSAGES_URL = "https://api.x.ai/v1/chat/completions"
XAI_API_KEY_VARIABLE = "XAI_API_KEY"

# Groq sits behind Cloudflare, which rejects the default "Python-urllib/x.y" agent with a 1010
# "banned" error. A plain application agent (no "python-urllib" substring) clears it; real SDKs all
# send one of their own.
_USER_AGENT = "evalloop/0.0.1"

Opener = Callable[[urllib.request.Request, float], HTTPReply]

# xAI finish reasons -> the Anthropic stop_reason the client understands. Only "refusal" is special
# to the parser; anything non-refusal just lets the text through, so the mapping stays minimal.
_STOP = {"stop": "end_turn", "length": "max_tokens", "max_tokens": "max_tokens", "content_filter": "refusal"}


def _urlopen(request: urllib.request.Request, timeout: float) -> HTTPReply:
    """Perform the request and return an :class:`HTTPReply`, including for 4xx/5xx (status-keyed)."""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            return HTTPReply(status=response.status, headers=headers, body=response.read())
    except urllib.error.HTTPError as error:
        headers = {k.lower(): v for k, v in (error.headers or {}).items()}
        return HTTPReply(status=error.code, headers=headers, body=error.read())


def _anthropic_request_to_xai(body: bytes) -> bytes:
    payload: Any = json.loads(body)
    messages = list(payload.get("messages") or [])
    system = payload.get("system")
    if system:
        messages = [{"role": "system", "content": system}, *messages]
    xai = {"model": payload["model"], "max_tokens": payload["max_tokens"], "messages": messages}
    return json.dumps(xai).encode("utf-8")


def _xai_reply_to_anthropic(reply: HTTPReply) -> HTTPReply:
    if not (200 <= reply.status < 300):
        return reply  # errors are classified by status, not body; pass through untranslated
    try:
        doc: Any = json.loads(reply.body)
        choice = doc["choices"][0]
        text = choice["message"]["content"] or ""
        usage = doc.get("usage") or {}
        anthropic = {
            "id": str(doc.get("id", "")),
            "model": str(doc.get("model", "")),
            "stop_reason": _STOP.get(str(choice.get("finish_reason")), "end_turn"),
            "content": [{"type": "text", "text": str(text)}],
            "usage": {
                "input_tokens": int(usage.get("prompt_tokens", 0)),
                "output_tokens": int(usage.get("completion_tokens", 0)),
            },
        }
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return reply  # leave it; the client raises MalformedResponse rather than guess at the shape
    return HTTPReply(status=reply.status, headers=reply.headers, body=json.dumps(anthropic).encode("utf-8"))


class OpenAICompatibleTransport:
    """An OpenAI-compatible chat API behind the Anthropic seam. Holds the API key, nothing else does."""

    def __init__(self, api_key: str, *, url: str = GROQ_MESSAGES_URL, opener: Opener = _urlopen) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise MissingCredential("an API key is required")
        if not url.startswith(("https://", "http://")):
            raise ValueError(f"the transport speaks HTTP(S) only, got {url!r}")
        self.__api_key = api_key
        self.url = url
        self._opener = opener

    @classmethod
    def from_environment(
        cls, *, variable: str = GROQ_API_KEY_VARIABLE, url: str = GROQ_MESSAGES_URL, opener: Opener = _urlopen
    ) -> "OpenAICompatibleTransport":
        """Read ``variable`` (default ``GROQ_API_KEY``) — the only environment read for this provider."""
        key = os.environ.get(variable, "")
        if not key.strip():
            raise MissingCredential(f"{variable} is not set")
        return cls(key, url=url, opener=opener)

    @classmethod
    def groq(cls, *, opener: Opener = _urlopen) -> "OpenAICompatibleTransport":
        return cls.from_environment(variable=GROQ_API_KEY_VARIABLE, url=GROQ_MESSAGES_URL, opener=opener)

    @classmethod
    def xai(cls, *, opener: Opener = _urlopen) -> "OpenAICompatibleTransport":
        return cls.from_environment(variable=XAI_API_KEY_VARIABLE, url=XAI_MESSAGES_URL, opener=opener)

    @property
    def leaves_machine(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"OpenAICompatibleTransport(url={self.url!r}, api_key=<redacted>)"

    def post(self, body: bytes, *, timeout: float) -> HTTPReply:
        request = urllib.request.Request(
            self.url,
            data=_anthropic_request_to_xai(body),
            method="POST",
            headers={
                "authorization": f"Bearer {self.__api_key}",
                "content-type": "application/json",
                "user-agent": _USER_AGENT,
            },
        )
        return _xai_reply_to_anthropic(self._opener(request, timeout))


# -- wiring Groq into the router ---------------------------------------------------------

#: Model defaults, overridable by environment. The author job wants the capable model; the
#: classify ("intent detection") job is cheap and small.
AUTHOR_MODEL_VARIABLE = "EVALLOOP_GROQ_AUTHOR_MODEL"
CLASSIFY_MODEL_VARIABLE = "EVALLOOP_GROQ_CLASSIFY_MODEL"
PRICE_IN_VARIABLE = "EVALLOOP_GROQ_PRICE_IN"
PRICE_OUT_VARIABLE = "EVALLOOP_GROQ_PRICE_OUT"
_DEFAULT_AUTHOR_MODEL = "openai/gpt-oss-120b"
_DEFAULT_CLASSIFY_MODEL = "openai/gpt-oss-20b"


class AuthoringUnavailable(Exception):
    """Authoring cannot run, with a reason the driver can print verbatim. Never a silent skip."""


def _price(variable: str) -> Decimal:
    """A per-million-token price, supplied by whoever grants the call. Never defaulted or guessed.

    ``CLAUDE.md``'s rule is that a number is copied from its source or is absent; EvalLoop does not
    know a third party's price list, so it refuses to invent one and names the variable instead.
    """
    raw = os.environ.get(variable, "").strip()
    if not raw:
        raise AuthoringUnavailable(
            f"{variable} is not set. EvalLoop will not invent a price, so authoring is off. "
            f"Set {PRICE_IN_VARIABLE} and {PRICE_OUT_VARIABLE} to the provider's per-million-token "
            "input/output prices (see your provider's pricing page), e.g. export "
            f"{PRICE_IN_VARIABLE}=0.15 {PRICE_OUT_VARIABLE}=0.75"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise AuthoringUnavailable(f"{variable}={raw!r} is not a decimal number") from exc
    if not value.is_finite() or value <= 0:
        raise AuthoringUnavailable(f"{variable}={raw!r} must be a positive price")
    return value


def build_groq_router(
    *,
    budget_usd: Decimal = Decimal("1.00"),
    jitter_seed: int = 0,
    request_timeout: float = 60.0,
) -> Router:
    """A :class:`Router` that sends the author and classify jobs to Groq. Raises if it cannot.

    Reads ``GROQ_API_KEY`` for the credential and the two price variables for the ledger. Every
    failure is an :class:`AuthoringUnavailable` carrying a reason the driver prints, so a missing
    key or price is a stated refusal rather than a quiet fallback to "no evals".
    """
    try:
        transport = OpenAICompatibleTransport.groq()
    except MissingCredential as exc:
        raise AuthoringUnavailable(
            f"{exc}. Set it to your Groq key to let EvalLoop author tests: export GROQ_API_KEY=..."
        ) from exc

    price_in, price_out = _price(PRICE_IN_VARIABLE), _price(PRICE_OUT_VARIABLE)
    source = f"supplied by {PRICE_IN_VARIABLE}/{PRICE_OUT_VARIABLE}"

    def model(variable: str, default: str) -> ModelConfig:
        return ModelConfig(
            model_id=os.environ.get(variable, "").strip() or default,
            family="gpt-oss",          # not "claude": a cross-family judge stays possible
            provider="groq",
            input_usd_per_mtok=price_in,
            output_usd_per_mtok=price_out,
            accepts_sampling=False,
            source=source,
        )

    client = LLMClient(
        transport,
        RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=4.0,
                    request_timeout=request_timeout, total_timeout=request_timeout * 2.5),
        jitter_seed=jitter_seed,
    )
    return Router(
        routes={
            Job.author: model(AUTHOR_MODEL_VARIABLE, _DEFAULT_AUTHOR_MODEL),
            Job.classify: model(CLASSIFY_MODEL_VARIABLE, _DEFAULT_CLASSIFY_MODEL),
        },
        client=client,
        ledger=CostLedger(budget_usd),
    )
