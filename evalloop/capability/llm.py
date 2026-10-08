"""The LLM client: EvalLoop's one stdlib-HTTP door to a model, and the rules at that door.

``AGENT.md`` §4 gives the capability layer "LLM routing by job", "Credentials", "Cost tracking"
and "Rate limits", and says "LLM client is stdlib HTTP with retry + backoff. No SDK wrappers."
This module is the client. Routing, the cross-family rule and cost are ``router.py``.

M1 runs under option (b): no outbound call on an uncleared artifact
--------------------------------------------------------------------
This is the first code in EvalLoop that can send a developer's code to another company's
servers. The guard for that is fixture 20's PHI gate, and fixture 20 is blocked on a ruling. Its
recommended option puts redaction in the M2 capability broker (``ARCHITECTURE.md`` §7,
component 11), and ``ARCHITECTURE.md`` §9 requires "no outbound LLM call on PHI without an
explicit grant".

So this client redacts nothing and decides nothing about what may leave. Every call through a
transport that leaves the machine needs a :class:`Clearance`, an explicit named grant. Without
one, the call raises :class:`EgressRefused` before a byte is sent. Nothing in M1 issues a
clearance: there is no broker yet, and ``tests/test_llm_router.py`` fails if any module under
``evalloop/`` constructs one. Until a ruling says otherwise, M1's model calls run against a fake
transport only. That is EL-209's option (b), made a property of the code rather than a promise.

Credentials
-----------
The API key is read in exactly one place, :meth:`AnthropicHTTPTransport.from_environment`, from
``ANTHROPIC_API_KEY``. ``ARCHITECTURE.md`` §9: "Credentials in a grader: impossible by
construction." The key lives in one name-mangled attribute. It is never repr'd, logged or put in
an error message, and the test suite fails if any other module under ``evalloop/`` reads the
environment.

Only the API-key path is supported here. The claude-api skill lists other real credential
sources — ``ANTHROPIC_AUTH_TOKEN``, ``ant auth`` profiles, workload identity — and those belong to
the M2 broker.

Protocol facts, and where they come from
----------------------------------------
From the claude-api skill (``curl/examples.md`` and ``shared/error-codes.md``, read 2026-10-09):

- ``POST https://api.anthropic.com/v1/messages``, with ``x-api-key``,
  ``anthropic-version: 2023-06-01`` and ``Content-Type: application/json``.
- Retryable: 429 ``rate_limit_error``, 500 ``api_error`` and 529 ``overloaded_error``. The SDKs
  also retry 408, 409 and every other 5xx, and so does this client.
- Not retryable: 400, 401, 402, 403, 404 and 413.
- ``retry-after`` is in seconds, and the request id arrives in the ``request-id`` header.

No retry number is a default
----------------------------
How many attempts to make, how long to back off, the per-request timeout and the total-time cap
are operational policy, not methodology, and the corpus states none of them. Under decision
EL-015, such numbers are supplied by whoever grants the capability; they are never defaulted
here. :class:`RetryPolicy` therefore has no defaults.

For reference only: the official SDKs choose 2 retries and a 10-minute timeout (claude-api
skill, "Client config"). This client does not adopt them.

Determinism
-----------
- **Backoff jitter** is "full jitter": a uniform draw in ``[0, ceiling)``, where the ceiling
  doubles each attempt as in the skill's retry example. The draw comes from
  ``random.Random(jitter_seed)``, and the seed is recorded with every response.
- **Clock and sleep** are injected, so no test ever waits.
- **Sampling parameters.** Most current models reject ``temperature`` with a 400, and none
  accepts a seed (claude-api skill, Thinking & Effort table). So a model's output usually cannot
  be pinned by parameters at all. ``ARCHITECTURE.md`` §9's fallback, "repeat and report variance,
  never a single number", is the caller's job. This client records exactly what was sent;
  ``seed`` is always ``None`` because the API has no seed.

What is deliberately not here
-----------------------------
- **Server-side refusal fallbacks**, a skill default for some models. They would answer with a
  different model than the one configured, in the middle of an evaluation.
- **Streaming, tools, thinking configuration, effort and prompt caching.** No M1 job needs them.
- **Rate-limit policy and consent.** Those are M2's.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal, Protocol, cast

__all__ = [
    "ANTHROPIC_MESSAGES_URL",
    "ANTHROPIC_VERSION",
    "API_KEY_VARIABLE",
    "APIError",
    "AnthropicHTTPTransport",
    "AuthenticationFailed",
    "Clearance",
    "EgressRefused",
    "HTTPReply",
    "LLMClient",
    "LLMError",
    "LLMRequest",
    "LLMResponse",
    "MalformedResponse",
    "Message",
    "MissingCredential",
    "Overloaded",
    "RateLimited",
    "RejectedRequest",
    "RetriesExhausted",
    "RetryPolicy",
    "RetryableAPIError",
    "ServerError",
    "TotalTimeExceeded",
    "Transport",
    "TransportError",
    "Usage",
]

#: claude-api skill, ``curl/examples.md``: the Messages endpoint and its required version header.
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

#: The one environment variable this package reads, in one function.
API_KEY_VARIABLE = "ANTHROPIC_API_KEY"

# claude-api skill, shared/error-codes.md: 429, 500 and 529 are retryable, and the SDKs also
# retry 408, 409 and every other 5xx. These are protocol status codes, not chosen values.
_RATE_LIMITED = 429
_OVERLOADED = 529
_RETRYABLE_CLIENT_STATUSES = (408, 409)
_AUTHENTICATION_STATUSES = (401, 403)


# -- errors ------------------------------------------------------------------------


class LLMError(Exception):
    """The base of every error the capability layer raises."""


class EgressRefused(LLMError):
    """A call would leave the machine without a :class:`Clearance`. M1 runs under option (b)."""


class MissingCredential(LLMError):
    """``ANTHROPIC_API_KEY`` is not set, or is empty."""


class TransportError(LLMError):
    """The request did not complete: network, DNS, TLS or a socket timeout. Retried."""


class MalformedResponse(LLMError):
    """A success reply whose body is not the documented message shape. Not retried."""


class APIError(LLMError):
    """The API answered with an error status. ``retryable`` says whether trying again can help."""

    retryable: ClassVar[bool] = False

    def __init__(
        self,
        status: int,
        error_type: str | None,
        message: str,
        request_id: str | None,
        retry_after: float | None,
    ) -> None:
        detail = f"HTTP {status} {error_type or 'unknown_error'}: {message}"
        if request_id is not None:
            detail += f" (request-id {request_id})"
        super().__init__(detail)
        self.status = status
        self.error_type = error_type
        self.message = message
        self.request_id = request_id
        self.retry_after = retry_after


class RetryableAPIError(APIError):
    """A status the documentation says to retry."""

    retryable = True


class RateLimited(RetryableAPIError):
    """429 ``rate_limit_error``."""


class Overloaded(RetryableAPIError):
    """529 ``overloaded_error``."""


class ServerError(RetryableAPIError):
    """500 and every other 5xx, plus 408 and 409, which the SDKs also retry."""


class RejectedRequest(APIError):
    """400, 402, 404, 413 or any other 4xx: the request itself is wrong, so retrying cannot help."""


class AuthenticationFailed(RejectedRequest):
    """401 ``authentication_error`` or 403 ``permission_error``."""


class RetriesExhausted(LLMError):
    """Every attempt the policy allows has failed. ``last`` is the final failure."""

    def __init__(self, attempts: int, last: LLMError) -> None:
        super().__init__(f"gave up after {attempts} attempt(s); last error: {last}")
        self.attempts = attempts
        self.last = last


class TotalTimeExceeded(LLMError):
    """The policy's wall-clock cap would be crossed by another attempt or another wait."""

    def __init__(self, attempts: int, elapsed: float, last: LLMError | None) -> None:
        reason = f"; last error: {last}" if last is not None else ""
        super().__init__(f"total-time cap reached after {attempts} attempt(s), {elapsed:.3f}s{reason}")
        self.attempts = attempts
        self.elapsed = elapsed
        self.last = last


# -- request and response ------------------------------------------------------------------

Role = Literal["user", "assistant"]


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string, got {value!r}")
    return value


@dataclass(frozen=True)
class Message:
    """One conversation turn. Text content only: no M1 job sends images or tools."""

    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError(f"role must be 'user' or 'assistant', got {self.role!r}")
        _require_text("message content", self.content)


@dataclass(frozen=True)
class LLMRequest:
    """Everything sent to the model. ``None`` means "not sent", so the model's own default applies."""

    model_id: str
    max_tokens: int
    messages: tuple[Message, ...]
    system: str | None = None
    temperature: float | None = None

    def __post_init__(self) -> None:
        _require_text("model_id", self.model_id)
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int) or self.max_tokens < 1:
            raise ValueError(f"max_tokens must be a positive integer, got {self.max_tokens!r}")
        if not isinstance(self.messages, tuple) or not self.messages:
            raise ValueError("messages must be a non-empty tuple")
        if self.messages[0].role != "user":
            raise ValueError("the first message must be from the user (claude-api skill, error table)")
        if self.system is not None:
            _require_text("system", self.system)
        if self.temperature is not None and (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
        ):
            raise ValueError(f"temperature must be a finite number or None, got {self.temperature!r}")

    def body(self) -> bytes:
        """The request body: fixed key order and compact separators, so equal requests are equal bytes."""
        payload: dict[str, object] = {
            "model": self.model_id,
            "max_tokens": self.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
        }
        if self.system is not None:
            payload["system"] = self.system
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class Clearance:
    """An explicit grant to send an artifact off this machine: who granted it, and why.

    The M2 capability broker is meant to issue these. In M1 nothing does — see the module
    docstring — so any call through a transport that leaves the machine is refused.
    """

    granted_by: str
    reason: str

    def __post_init__(self) -> None:
        _require_text("granted_by", self.granted_by)
        _require_text("reason", self.reason)


@dataclass(frozen=True)
class Usage:
    """Token counts as the API reports them. Cache counts are 0 when the reply omits them."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


@dataclass(frozen=True)
class LLMResponse:
    """A model's answer, with everything needed to know how it was produced.

    ``request`` is the request exactly as sent: the model id and every parameter. ``seed`` is
    always ``None``, because the Messages API has no seed parameter; the field exists so a record
    states that rather than omitting it. ``served_model`` is the API's own report of which model
    answered. ``refusal_category`` is set only when ``stop_reason`` is ``"refusal"``.
    """

    request: LLMRequest
    seed: int | None
    served_model: str
    message_id: str
    request_id: str | None
    text: str
    stop_reason: str | None
    refusal_category: str | None
    usage: Usage
    attempts: int
    jitter_seed: int
    clearance: Clearance | None

    @property
    def refused(self) -> bool:
        """The model declined. Check this before trusting ``text``, as the claude-api skill advises."""
        return self.stop_reason == "refusal"


# -- transports ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class HTTPReply:
    """A finished HTTP exchange. Header names are lowercase; only the two this layer reads are kept."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    """Moves request bytes to a model and brings the reply back. Nothing else."""

    @property
    def leaves_machine(self) -> bool:
        """True when ``post`` sends data off this machine. That is what a :class:`Clearance` guards."""

    def post(self, body: bytes, *, timeout: float) -> HTTPReply:
        """Send ``body`` and return the reply, or raise :class:`TransportError`."""


Opener = Callable[[urllib.request.Request, float], HTTPReply]

_KEPT_HEADERS = ("request-id", "retry-after")


def _kept_headers(items: Iterable[tuple[str, str]]) -> Mapping[str, str]:
    kept = {name.lower(): value for name, value in items if name.lower() in _KEPT_HEADERS}
    return MappingProxyType(kept)


def _urlopen(request: urllib.request.Request, timeout: float) -> HTTPReply:
    """The real network call. The only line in EvalLoop that opens a socket to a model."""
    try:
        # typeshed types urlopen's result as Any; binding it to the concrete class it returns
        # for an http(s) URL keeps Any off everything below.
        opened: http.client.HTTPResponse = urllib.request.urlopen(request, timeout=timeout)
        with opened as response:
            status = response.status
            headers = _kept_headers((name, str(value)) for name, value in response.getheaders())
            body = response.read()
    except urllib.error.HTTPError as error:
        items = [(str(k), str(v)) for k, v in error.headers.items()] if error.headers else []
        return HTTPReply(int(error.code), _kept_headers(items), bytes(error.read()))
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise TransportError(f"{type(error).__name__}: {error}") from error
    return HTTPReply(status, headers, body)


class AnthropicHTTPTransport:
    """The Messages API over ``urllib.request``. Holds the API key, and nothing else does."""

    def __init__(
        self,
        api_key: str,
        *,
        url: str = ANTHROPIC_MESSAGES_URL,
        version: str = ANTHROPIC_VERSION,
        opener: Opener = _urlopen,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise MissingCredential("an API key is required")
        if not url.startswith(("https://", "http://")):
            # Any other scheme would make urlopen read local files or other protocols, and
            # would not return the http.client.HTTPResponse that _urlopen relies on.
            raise ValueError(f"the transport speaks HTTP(S) only, got {url!r}")
        self.__api_key = api_key
        self.url = url
        self.version = version
        self._opener = opener

    @classmethod
    def from_environment(
        cls, *, url: str = ANTHROPIC_MESSAGES_URL, opener: Opener = _urlopen
    ) -> AnthropicHTTPTransport:
        """Read ``ANTHROPIC_API_KEY``. This is the only environment read in EvalLoop."""
        key = os.environ.get(API_KEY_VARIABLE, "")
        if not key.strip():
            raise MissingCredential(f"{API_KEY_VARIABLE} is not set")
        return cls(key, url=url, opener=opener)

    @property
    def leaves_machine(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"AnthropicHTTPTransport(url={self.url!r}, version={self.version!r}, api_key=<redacted>)"

    def post(self, body: bytes, *, timeout: float) -> HTTPReply:
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "x-api-key": self.__api_key,
                "anthropic-version": self.version,
                "content-type": "application/json",
            },
        )
        return self._opener(request, timeout)


# -- decoding ------------------------------------------------------------------------------


def _decode(body: bytes) -> object:
    try:
        decoded: object = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MalformedResponse(f"the reply is not JSON: {error.__class__.__name__}") from error
    return decoded


def _object(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise MalformedResponse(f"{where} is not a JSON object")
    # isinstance narrows to dict[Any, Any]; an annotated binding is the boundary past which
    # nothing is Any. Keys are checked before the mapping is treated as dict[str, object].
    mapping: dict[object, object] = value
    if not all(isinstance(key, str) for key in mapping):
        raise MalformedResponse(f"{where} has a non-string key")
    return cast("dict[str, object]", mapping)


def _string(document: Mapping[str, object], key: str, where: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise MalformedResponse(f"{where}.{key} is not a string")
    return value


def _optional_string(document: Mapping[str, object], key: str, where: str) -> str | None:
    value = document.get(key)
    if value is not None and not isinstance(value, str):
        raise MalformedResponse(f"{where}.{key} is not a string or null")
    return value


def _count(document: Mapping[str, object], key: str, *, required: bool) -> int:
    value = document.get(key)
    if value is None and not required:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MalformedResponse(f"usage.{key} is not a non-negative integer")
    return value


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0.0 else None


def _api_error(reply: HTTPReply) -> APIError:
    error_type: str | None = None
    try:
        envelope = _object(_decode(reply.body), "the error reply")
        detail = _object(envelope.get("error"), "the error reply's error")
        error_type = _optional_string(detail, "type", "error")
        message = _string(detail, "message", "error")
    except MalformedResponse:
        # Not the documented error shape. Report its size, never its content: it may be a
        # proxy's HTML page, and nothing from it is needed to decide what to do.
        message = f"unparseable error body ({len(reply.body)} bytes)"
    status = reply.status
    kind: type[APIError]
    if status == _RATE_LIMITED:
        kind = RateLimited
    elif status == _OVERLOADED:
        kind = Overloaded
    elif status >= 500 or status in _RETRYABLE_CLIENT_STATUSES:
        kind = ServerError
    elif status in _AUTHENTICATION_STATUSES:
        kind = AuthenticationFailed
    else:
        kind = RejectedRequest
    return kind(
        status,
        error_type,
        message,
        reply.headers.get("request-id"),
        _retry_after(reply.headers.get("retry-after")),
    )


# -- the client ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """How hard to try. No field has a default: these are policy, supplied by whoever grants the call.

    ``max_attempts`` counts the first try. ``base_delay`` and ``max_delay`` bound the jittered
    backoff. ``request_timeout`` caps one attempt, and ``total_timeout`` caps every attempt and
    every wait together. All times are in seconds.
    """

    max_attempts: int
    base_delay: float
    max_delay: float
    request_timeout: float
    total_timeout: float

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError(f"max_attempts must be a positive integer, got {self.max_attempts!r}")
        timings: tuple[tuple[str, float], ...] = (
            ("base_delay", self.base_delay),
            ("max_delay", self.max_delay),
            ("request_timeout", self.request_timeout),
            ("total_timeout", self.total_timeout),
        )
        for name, value in timings:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number, got {value!r}")
        if self.base_delay < 0 or self.max_delay < self.base_delay:
            raise ValueError("need 0 <= base_delay <= max_delay")
        if self.request_timeout <= 0 or self.total_timeout <= 0:
            raise ValueError("request_timeout and total_timeout must be positive")


class LLMClient:
    """Sends a request through a transport, with bounded, jittered, time-capped retries."""

    def __init__(
        self,
        transport: Transport,
        policy: RetryPolicy,
        *,
        jitter_seed: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._policy = policy
        self._jitter_seed = jitter_seed
        self._rng = random.Random(jitter_seed)
        self._clock = clock
        self._sleep = sleep

    def complete(self, request: LLMRequest, *, clearance: Clearance | None) -> LLMResponse:
        """One model call. ``clearance`` is required, by keyword, even when it is ``None``.

        Raises :class:`EgressRefused` before anything is sent if the transport leaves the machine
        and no clearance is given. Retries only what the documentation calls retryable, and never
        past ``policy.total_timeout``.
        """
        if self._transport.leaves_machine and clearance is None:
            raise EgressRefused(
                "this call would send data off the machine and has no Clearance. M1 runs under "
                "option (b): no outbound call on an artifact that has not been cleared"
            )
        policy = self._policy
        body = request.body()
        start = self._clock()
        last: LLMError | None = None
        for attempt in range(1, policy.max_attempts + 1):
            elapsed = self._clock() - start
            remaining = policy.total_timeout - elapsed
            if remaining <= 0:
                raise TotalTimeExceeded(attempt - 1, elapsed, last)
            try:
                reply = self._transport.post(body, timeout=min(policy.request_timeout, remaining))
            except TransportError as error:
                last = error
            else:
                if 200 <= reply.status < 300:
                    return self._parse(reply, request, attempt, clearance)
                failure = _api_error(reply)
                if not failure.retryable:
                    raise failure
                last = failure
            if attempt == policy.max_attempts:
                break
            delay = self._backoff(attempt, last)
            elapsed = self._clock() - start
            if elapsed + delay >= policy.total_timeout:
                raise TotalTimeExceeded(attempt, elapsed, last)
            self._sleep(delay)
        assert last is not None  # the loop ran at least once and did not return
        raise RetriesExhausted(policy.max_attempts, last)

    def _backoff(self, attempt: int, last: LLMError) -> float:
        ceiling = min(self._policy.max_delay, self._policy.base_delay * 2.0 ** (attempt - 1))
        delay = self._rng.random() * ceiling
        if isinstance(last, APIError) and last.retry_after is not None:
            delay = max(delay, last.retry_after)
        return delay

    def _parse(
        self, reply: HTTPReply, request: LLMRequest, attempts: int, clearance: Clearance | None
    ) -> LLMResponse:
        document = _object(_decode(reply.body), "the reply")
        content = document.get("content")
        if not isinstance(content, list):
            raise MalformedResponse("the reply's content is not a list")
        blocks: list[object] = content
        texts: list[str] = []
        for index, raw in enumerate(blocks):
            block = _object(raw, f"content[{index}]")
            if block.get("type") == "text":
                texts.append(_string(block, "text", f"content[{index}]"))
        stop_reason = _optional_string(document, "stop_reason", "the reply")
        refusal_category: str | None = None
        if stop_reason == "refusal" and document.get("stop_details") is not None:
            details = _object(document.get("stop_details"), "stop_details")
            refusal_category = _optional_string(details, "category", "stop_details")
        usage = _object(document.get("usage"), "usage")
        return LLMResponse(
            request=request,
            seed=None,
            served_model=_string(document, "model", "the reply"),
            message_id=_string(document, "id", "the reply"),
            request_id=reply.headers.get("request-id"),
            text="".join(texts),
            stop_reason=stop_reason,
            refusal_category=refusal_category,
            usage=Usage(
                input_tokens=_count(usage, "input_tokens", required=True),
                output_tokens=_count(usage, "output_tokens", required=True),
                cache_creation_input_tokens=_count(usage, "cache_creation_input_tokens", required=False),
                cache_read_input_tokens=_count(usage, "cache_read_input_tokens", required=False),
            ),
            attempts=attempts,
            jitter_seed=self._jitter_seed,
            clearance=clearance,
        )
