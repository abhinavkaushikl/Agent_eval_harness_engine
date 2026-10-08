"""The LLM client and router: retries, the egress gate, credentials, the cross-family rule, cost.

No test touches the network, and the suite runs with no credentials. Two autouse fixtures make
that a fact rather than a hope:

- ``no_network`` makes every socket connection, and ``urllib.request.urlopen``, raise.
- ``no_credentials`` removes ``ANTHROPIC_API_KEY`` before every test.

A model is reached through a scripted transport that never leaves the machine. The real HTTP
transport is exercised against a fake ``opener``, or a patched ``urlopen``. Times, budgets and
token counts below are test inputs, not shipped defaults: the shipped code has none.
"""

from __future__ import annotations

import email.message
import io
import json
import os
import re
import socket
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.capability.llm import (
    ANTHROPIC_MESSAGES_URL,
    ANTHROPIC_VERSION,
    API_KEY_VARIABLE,
    AnthropicHTTPTransport,
    AuthenticationFailed,
    Clearance,
    EgressRefused,
    HTTPReply,
    LLMClient,
    LLMRequest,
    MalformedResponse,
    Message,
    MissingCredential,
    Overloaded,
    RateLimited,
    RejectedRequest,
    RetriesExhausted,
    RetryPolicy,
    ServerError,
    TotalTimeExceeded,
    TransportError,
    _urlopen,
)
from evalloop.capability.models import CATALOG
from evalloop.capability.router import (
    BudgetExhausted,
    CostLedger,
    Job,
    ModelConfig,
    NoRoute,
    Router,
    SameFamilyJudge,
    UnknownGeneratorFamily,
    UnpricedUsage,
    UnsupportedParameter,
)

EVALLOOP = Path(__file__).resolve().parent.parent / "evalloop"


# -- the two guarantees, as fixtures ------------------------------------------------------


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_VARIABLE, raising=False)


# -- test doubles ----------------------------------------------------------------------------


class FakeClock:
    """A clock that moves only when something sleeps or a transport says time passed."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedTransport:
    """Replies from a script, never leaving the machine. Records every body and timeout it got."""

    def __init__(
        self,
        *script: HTTPReply | TransportError,
        leaves_machine: bool = False,
        clock: FakeClock | None = None,
        takes: float = 0.0,
    ) -> None:
        self._script = list(script)
        self._leaves_machine = leaves_machine
        self._clock = clock
        self._takes = takes
        self.sent: list[tuple[bytes, float, float]] = []

    @property
    def leaves_machine(self) -> bool:
        return self._leaves_machine

    def post(self, body: bytes, *, timeout: float) -> HTTPReply:
        started = self._clock.now if self._clock else 0.0
        self.sent.append((body, timeout, started))
        if self._clock is not None:
            self._clock.now += self._takes
        if not self._script:
            raise AssertionError("the script ran out: the client made a call nobody expected")
        step = self._script.pop(0)
        if isinstance(step, TransportError):
            raise step
        return step


def message_body(
    text: str = "All good.",
    *,
    model: str = "claude-opus-5-5",
    usage: tuple[int, int] = (120, 40),
    stop_reason: str = "end_turn",
    blocks: list[dict[str, object]] | None = None,
    stop_details: dict[str, object] | None = None,
    usage_extra: dict[str, int] | None = None,
) -> bytes:
    content = blocks if blocks is not None else [{"type": "text", "text": text}]
    return json.dumps(
        {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_details": stop_details,
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1], **(usage_extra or {})},
        }
    ).encode()


def ok(body: bytes | None = None, request_id: str = "req_01") -> HTTPReply:
    return HTTPReply(200, {"request-id": request_id}, body if body is not None else message_body())


def failure(status: int, error_type: str, retry_after: str | None = None) -> HTTPReply:
    headers = {"request-id": f"req_{status}"}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    body = json.dumps({"type": "error", "error": {"type": error_type, "message": "nope"}}).encode()
    return HTTPReply(status, headers, body)


POLICY = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=8.0, request_timeout=30.0, total_timeout=120.0)
REQUEST = LLMRequest(
    model_id="claude-opus-5-5", max_tokens=1024, messages=(Message("user", "Is this function correct?"),)
)


def make_client(transport: object, clock: FakeClock | None = None, seed: int = 7, policy: RetryPolicy = POLICY) -> LLMClient:
    clock = clock if clock is not None else FakeClock()
    return LLMClient(transport, policy, jitter_seed=seed, clock=clock, sleep=clock.sleep)  # type: ignore[arg-type]


# -- a call, and what it records -------------------------------------------------------------------


def test_a_successful_call_records_how_it_was_produced() -> None:
    """The model id, parameters and seed travel with the answer. Thinking blocks are not text."""
    thinking_then_text: list[dict[str, object]] = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "All "},
        {"type": "text", "text": "good."},
    ]
    response = make_client(ScriptedTransport(ok(message_body(blocks=thinking_then_text)))).complete(
        REQUEST, clearance=None
    )
    assert response.text == "All good."
    assert response.request is REQUEST
    assert response.request.model_id == "claude-opus-5-5" and response.request.max_tokens == 1024
    assert response.request.temperature is None
    assert response.seed is None  # the Messages API has no seed parameter
    assert (response.served_model, response.message_id, response.request_id) == ("claude-opus-5-5", "msg_01", "req_01")
    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 40)
    assert (response.attempts, response.jitter_seed, response.clearance) == (1, 7, None)
    assert not response.refused


def test_the_request_body_is_deterministic_and_sends_only_what_was_set() -> None:
    assert REQUEST.body() == (
        b'{"model":"claude-opus-5-5","max_tokens":1024,'
        b'"messages":[{"role":"user","content":"Is this function correct?"}]}'
    )
    with_options = LLMRequest("claude-haiku-4-5", 256, (Message("user", "hi"),), system="Be brief.", temperature=0.0)
    assert json.loads(with_options.body()) == {
        "model": "claude-haiku-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "hi"}],
        "system": "Be brief.",
        "temperature": 0.0,
    }
    assert with_options.body() == LLMRequest(
        "claude-haiku-4-5", 256, (Message("user", "hi"),), system="Be brief.", temperature=0.0
    ).body()


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"max_tokens": 0}, "max_tokens"),
        ({"max_tokens": True}, "max_tokens"),
        ({"messages": ()}, "non-empty"),
        ({"messages": (Message("assistant", "hello"),)}, "first message must be from the user"),
        ({"temperature": float("nan")}, "temperature"),
        ({"model_id": " "}, "model_id"),
    ],
)
def test_malformed_requests_are_refused_before_sending(request_kwargs: dict[str, object], match: str) -> None:
    fields: dict[str, object] = {"model_id": "claude-opus-5-5", "max_tokens": 64, "messages": (Message("user", "x"),)}
    fields.update(request_kwargs)
    with pytest.raises(ValueError, match=match):
        LLMRequest(**fields)  # type: ignore[arg-type]


# -- retries: bounded, jittered, time-capped, and only for what is retryable ---------------------


@pytest.mark.parametrize(
    ("status", "error_type", "kind"),
    [
        (429, "rate_limit_error", RateLimited),
        (529, "overloaded_error", Overloaded),
        (500, "api_error", ServerError),
        (503, "api_error", ServerError),
        (408, "request_timeout", ServerError),
        (409, "conflict", ServerError),
    ],
)
def test_retryable_statuses_are_retried(status: int, error_type: str, kind: type[Exception]) -> None:
    """claude-api skill, error-codes.md: 429, 500 and 529 retryable; the SDKs also retry 408, 409 and 5xx."""
    clock = FakeClock()
    transport = ScriptedTransport(failure(status, error_type), ok())
    response = make_client(transport, clock).complete(REQUEST, clearance=None)
    assert response.attempts == 2 and len(transport.sent) == 2 and len(clock.sleeps) == 1
    with pytest.raises(RetriesExhausted) as caught:
        make_client(ScriptedTransport(*[failure(status, error_type)] * 3)).complete(REQUEST, clearance=None)
    assert isinstance(caught.value.last, kind)


@pytest.mark.parametrize(
    ("status", "error_type", "kind"),
    [
        (400, "invalid_request_error", RejectedRequest),
        (401, "authentication_error", AuthenticationFailed),
        (402, "billing_error", RejectedRequest),
        (403, "permission_error", AuthenticationFailed),
        (404, "not_found_error", RejectedRequest),
        (413, "request_too_large", RejectedRequest),
    ],
)
def test_non_retryable_statuses_fail_at_once(status: int, error_type: str, kind: type[Exception]) -> None:
    clock = FakeClock()
    transport = ScriptedTransport(failure(status, error_type), ok())
    with pytest.raises(kind) as caught:
        make_client(transport, clock).complete(REQUEST, clearance=None)
    error = caught.value
    assert (error.status, error.error_type, error.message, error.request_id) == (  # type: ignore[attr-defined]
        status, error_type, "nope", f"req_{status}",
    )
    assert len(transport.sent) == 1 and clock.sleeps == []


def test_retries_are_bounded() -> None:
    """The client gives up: three attempts allowed, three made, never a fourth."""
    clock = FakeClock()
    transport = ScriptedTransport(*[failure(500, "api_error")] * 3)
    with pytest.raises(RetriesExhausted) as caught:
        make_client(transport, clock).complete(REQUEST, clearance=None)
    assert caught.value.attempts == 3 and len(transport.sent) == 3 and len(clock.sleeps) == 2


def test_transport_failures_are_retried() -> None:
    transport = ScriptedTransport(TransportError("TimeoutError: timed out"), ok())
    assert make_client(transport).complete(REQUEST, clearance=None).attempts == 2


def test_backoff_is_jittered_and_reproducible_from_its_seed() -> None:
    """Full jitter under a doubling ceiling; the same seed gives the same waits."""
    def waits(seed: int) -> list[float]:
        clock = FakeClock()
        policy = RetryPolicy(max_attempts=5, base_delay=1.0, max_delay=8.0, request_timeout=30.0, total_timeout=1_000.0)
        with pytest.raises(RetriesExhausted):
            make_client(ScriptedTransport(*[failure(500, "api_error")] * 5), clock, seed, policy).complete(
                REQUEST, clearance=None
            )
        return clock.sleeps

    first = waits(11)
    assert first == waits(11)
    for attempt, wait in enumerate(first, start=1):
        assert 0.0 <= wait < min(8.0, 1.0 * 2 ** (attempt - 1))


def test_retry_after_is_honoured() -> None:
    """claude-api skill: ``retry-after`` is seconds to wait; the client never waits less."""
    clock = FakeClock()
    make_client(ScriptedTransport(failure(429, "rate_limit_error", retry_after="5"), ok()), clock).complete(
        REQUEST, clearance=None
    )
    assert clock.sleeps[0] >= 5.0


def test_the_total_time_cap_stops_retries_and_shortens_the_last_attempt() -> None:
    clock = FakeClock()
    policy = RetryPolicy(max_attempts=50, base_delay=1.0, max_delay=8.0, request_timeout=30.0, total_timeout=120.0)
    transport = ScriptedTransport(*[failure(500, "api_error")] * 50, clock=clock, takes=30.0)
    with pytest.raises(TotalTimeExceeded):
        make_client(transport, clock, policy=policy).complete(REQUEST, clearance=None)
    for _, timeout, started in transport.sent:
        assert timeout <= 120.0 - started  # no attempt was allowed to run past the cap
    assert transport.sent[-1][1] < 30.0  # the last attempt got only what was left


def test_a_malformed_success_reply_is_not_retried() -> None:
    transport = ScriptedTransport(ok(b"not json"), ok())
    with pytest.raises(MalformedResponse):
        make_client(transport).complete(REQUEST, clearance=None)
    assert len(transport.sent) == 1
    no_usage = json.dumps({"id": "m", "model": "x", "content": [], "stop_reason": "end_turn"}).encode()
    with pytest.raises(MalformedResponse, match="usage"):
        make_client(ScriptedTransport(ok(no_usage))).complete(REQUEST, clearance=None)


def test_a_refusal_is_reported_not_hidden() -> None:
    """claude-api skill: "always check stop_reason before reading content"."""
    body = message_body(blocks=[], stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber"})
    response = make_client(ScriptedTransport(ok(body))).complete(REQUEST, clearance=None)
    assert response.refused and response.refusal_category == "cyber" and response.text == ""


def test_an_unparseable_error_body_is_never_echoed() -> None:
    page = b"<html>internal proxy page: secret-token-123</html>"
    with pytest.raises(RetriesExhausted) as caught:
        make_client(ScriptedTransport(*[HTTPReply(502, {}, page)] * 3)).complete(REQUEST, clearance=None)
    assert "secret-token-123" not in str(caught.value)
    assert f"unparseable error body ({len(page)} bytes)" in str(caught.value)


# -- the egress gate: option (b) ------------------------------------------------------------------


class RecordingOpener:
    """Stands in for urlopen inside the real HTTP transport."""

    def __init__(self, reply: HTTPReply) -> None:
        self.reply = reply
        self.requests: list[tuple[urllib.request.Request, float]] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> HTTPReply:
        self.requests.append((request, timeout))
        return self.reply


def test_egress_without_a_clearance_is_refused_before_anything_is_sent() -> None:
    opener = RecordingOpener(ok())
    transport = AnthropicHTTPTransport("sk-test-key", opener=opener)
    with pytest.raises(EgressRefused, match="option \\(b\\)"):
        make_client(transport).complete(REQUEST, clearance=None)
    assert opener.requests == []


def test_a_clearance_lets_a_call_out_and_is_recorded_with_it() -> None:
    opener = RecordingOpener(ok())
    clearance = Clearance(granted_by="tests", reason="exercising the HTTP path against a fake opener")
    response = make_client(AnthropicHTTPTransport("sk-test-key", opener=opener)).complete(REQUEST, clearance=clearance)
    assert len(opener.requests) == 1 and response.clearance == clearance


@pytest.mark.parametrize(("who", "why"), [("", "a reason"), ("someone", "   ")])
def test_a_clearance_must_say_who_and_why(who: str, why: str) -> None:
    with pytest.raises(ValueError):
        Clearance(granted_by=who, reason=why)


def test_nothing_in_evalloop_issues_a_clearance() -> None:
    """Option (b) as a fact: no module constructs a Clearance, so no call can leave in M1."""
    issuers = sorted(str(path.relative_to(EVALLOOP)) for path in EVALLOOP.rglob("*.py") if "Clearance(" in path.read_text(encoding="utf-8"))
    assert issuers == []


# -- the real HTTP transport, without a network ---------------------------------------------------


def test_the_http_transport_sends_the_documented_request() -> None:
    """claude-api skill, curl/examples.md: POST /v1/messages, x-api-key, anthropic-version, JSON."""
    opener = RecordingOpener(ok())
    AnthropicHTTPTransport("sk-test-key", opener=opener).post(REQUEST.body(), timeout=12.5)
    (request, timeout), = opener.requests
    headers = {name.lower(): value for name, value in request.header_items()}
    assert request.full_url == ANTHROPIC_MESSAGES_URL == "https://api.anthropic.com/v1/messages"
    assert request.get_method() == "POST" and request.data == REQUEST.body() and timeout == 12.5
    assert headers == {"x-api-key": "sk-test-key", "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    assert ANTHROPIC_VERSION == "2023-06-01"


class FakeHTTPResponse:
    def __init__(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
        self.status, self._headers, self._body = status, headers, body

    def getheaders(self) -> list[tuple[str, str]]:
        return self._headers

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_urlopen_replies_and_http_errors_become_replies(monkeypatch: pytest.MonkeyPatch) -> None:
    request = urllib.request.Request(ANTHROPIC_MESSAGES_URL, data=b"{}", method="POST")
    served = FakeHTTPResponse(200, [("Request-Id", "req_9"), ("Retry-After", "3"), ("X-Other", "y")], b"body")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: served)
    assert _urlopen(request, 5.0) == HTTPReply(200, {"request-id": "req_9", "retry-after": "3"}, b"body")

    headers = email.message.Message()
    headers["retry-after"] = "2"

    def overloaded(*a: object, **k: object) -> None:
        raise urllib.error.HTTPError(ANTHROPIC_MESSAGES_URL, 529, "Overloaded", headers, io.BytesIO(b"{}"))

    monkeypatch.setattr(urllib.request, "urlopen", overloaded)
    assert _urlopen(request, 5.0) == HTTPReply(529, {"retry-after": "2"}, b"{}")


@pytest.mark.parametrize("raised", [urllib.error.URLError("no route"), TimeoutError("timed out"), ConnectionResetError("reset")])
def test_network_failures_become_transport_errors(monkeypatch: pytest.MonkeyPatch, raised: Exception) -> None:
    def fail(*a: object, **k: object) -> None:
        raise raised

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(TransportError):
        _urlopen(urllib.request.Request(ANTHROPIC_MESSAGES_URL), 5.0)


def test_the_transport_speaks_http_only() -> None:
    with pytest.raises(ValueError, match="HTTP"):
        AnthropicHTTPTransport("sk-test-key", url="file:///etc/passwd")


# -- credentials ----------------------------------------------------------------------------------


def test_the_suite_runs_without_credentials() -> None:
    assert API_KEY_VARIABLE not in os.environ
    with pytest.raises(MissingCredential):
        AnthropicHTTPTransport.from_environment()


def test_the_key_is_read_from_the_environment_and_never_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-ant-test-DO-NOT-PRINT"
    monkeypatch.setenv(API_KEY_VARIABLE, secret)
    opener = RecordingOpener(failure(401, "authentication_error"))
    transport = AnthropicHTTPTransport.from_environment(opener=opener)
    assert secret not in repr(transport)
    with pytest.raises(AuthenticationFailed) as caught:
        make_client(transport).complete(REQUEST, clearance=Clearance("tests", "a 401 from a fake opener"))
    assert secret not in str(caught.value)
    (request, _), = opener.requests
    assert dict((k.lower(), v) for k, v in request.header_items())["x-api-key"] == secret


_ENVIRONMENT_READ = re.compile(r"\bos\.environ\b|\bgetenv\(|\benviron\[|\benviron\.get\(")


def test_no_other_module_reads_the_environment() -> None:
    """ARCHITECTURE.md section 9: credentials in a grader are impossible by construction."""
    readers = sorted(
        str(path.relative_to(EVALLOOP))
        for path in EVALLOOP.rglob("*.py")
        if _ENVIRONMENT_READ.search(path.read_text(encoding="utf-8"))
    )
    assert readers == ["capability/llm.py"]


def test_the_network_guard_is_live() -> None:
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("example.com", 80))


# -- the catalog: configuration, current, and only there ----------------------------------------------

_MODEL_ID = re.compile(r"\bclaude-(?:opus|sonnet|haiku|fable|mythos)-\d")


def test_model_ids_live_only_in_the_catalog() -> None:
    elsewhere = sorted(
        str(path.relative_to(EVALLOOP))
        for path in EVALLOOP.rglob("*.py")
        if path.name != "models.py" and _MODEL_ID.search(path.read_text(encoding="utf-8"))
    )
    assert elsewhere == []


def test_the_catalog_is_the_skills_table() -> None:
    """Ids, prices and the sampling column as the claude-api skill states them (cached 2026-09-25)."""
    assert set(CATALOG) == {
        "claude-fable-5-1", "claude-fable-5", "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8",
        "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6",
        "claude-haiku-4-5",
    }
    assert {m for m, c in CATALOG.items() if c.accepts_sampling} == {"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"}
    opus = CATALOG["claude-opus-5-5"]
    assert (opus.input_usd_per_mtok, opus.output_usd_per_mtok) == (Decimal("4.00"), Decimal("20.00"))
    assert all(c.family == "claude" and c.provider == "anthropic" and "claude-api skill" in c.source for c in CATALOG.values())


# -- the router: jobs, the cross-family rule, cost and the budget ------------------------------------

OTHER_FAMILY = ModelConfig(
    model_id="vendor-b-judge", family="family_b", provider="vendor_b",
    input_usd_per_mtok=Decimal("1"), output_usd_per_mtok=Decimal("2"), accepts_sampling=True, source="test fixture",
)


def make_router(*script: HTTPReply, budget: str = "10", judge: ModelConfig = CATALOG["claude-opus-5-5"]) -> tuple[Router, ScriptedTransport]:
    transport = ScriptedTransport(*script)
    routes = {Job.classify: CATALOG["claude-haiku-4-5"], Job.author: CATALOG["claude-opus-5-5"], Job.judge: judge}
    return Router(routes=routes, client=make_client(transport), ledger=CostLedger(Decimal(budget))), transport


ASK = (Message("user", "Write a test for add(a, b)."),)


def test_each_job_routes_to_its_model() -> None:
    router, _ = make_router()
    assert router.select(Job.classify, generator_family=None).model_id == "claude-haiku-4-5"
    assert router.select(Job.author, generator_family=None).model_id == "claude-opus-5-5"
    with pytest.raises(NoRoute, match="diagnose"):
        router.select(Job.diagnose, generator_family=None)


def test_a_same_family_judge_raises_naming_both_families() -> None:
    """AGENT.md section 5: never same-family judging. Raised, not warned."""
    router, transport = make_router(ok())
    with pytest.raises(SameFamilyJudge) as caught:
        router.complete(Job.judge, messages=ASK, max_tokens=64, generator_family="claude", clearance=None)
    message = str(caught.value)
    assert "claude-opus-5-5" in message
    assert "is family 'claude'" in message and "generated by family 'claude'" in message
    assert transport.sent == [] and router.ledger.spent_usd == 0


def test_a_judge_needs_the_generators_family() -> None:
    router, _ = make_router(judge=OTHER_FAMILY)
    with pytest.raises(UnknownGeneratorFamily):
        router.select(Job.judge, generator_family=None)


def test_a_cross_family_judge_is_allowed() -> None:
    router, transport = make_router(ok(message_body(model="vendor-b-judge")), judge=OTHER_FAMILY)
    routed = router.complete(Job.judge, messages=ASK, max_tokens=64, generator_family="claude", clearance=None)
    assert routed.model is OTHER_FAMILY and len(transport.sent) == 1


def test_cost_is_counted_per_call_and_per_session() -> None:
    """Opus 5.5 at $4 / $20 per million tokens (the catalog's source)."""
    router, _ = make_router(ok(message_body(usage=(120, 40))), ok(message_body(usage=(1_000, 500))))
    first = router.complete(Job.author, messages=ASK, max_tokens=512, generator_family=None, clearance=None)
    second = router.complete(Job.author, messages=ASK, max_tokens=512, generator_family=None, clearance=None)
    assert first.cost_usd == Decimal("0.00128")  # (120 * 4 + 40 * 20) / 1,000,000
    assert second.cost_usd == Decimal("0.014")  # (1,000 * 4 + 500 * 20) / 1,000,000
    assert second.session_spent_usd == router.ledger.spent_usd == Decimal("0.01528")
    assert router.ledger.charges == (Decimal("0.00128"), Decimal("0.014"))


def test_the_budget_stops_the_session_before_the_next_call() -> None:
    """ARCHITECTURE.md section 9, cost runaway: a hard stop, checked before the request is sent."""
    replies = [ok(message_body(usage=(1_000, 1_000))) for _ in range(5)]
    router, transport = make_router(*replies, budget="0.10")
    for _ in range(4):  # each costs $0.024; each reserves $0.02 of worst-case output first
        router.complete(Job.author, messages=ASK, max_tokens=1_000, generator_family=None, clearance=None)
    assert router.ledger.spent_usd == Decimal("0.096")
    with pytest.raises(BudgetExhausted):
        router.complete(Job.author, messages=ASK, max_tokens=1_000, generator_family=None, clearance=None)
    assert len(transport.sent) == 4


def test_a_call_whose_worst_case_output_cannot_fit_is_never_sent() -> None:
    router, transport = make_router(ok(), budget="0.001")
    with pytest.raises(BudgetExhausted, match="could cost up to"):
        router.complete(Job.author, messages=ASK, max_tokens=1_000, generator_family=None, clearance=None)
    assert transport.sent == []


def test_unpriced_usage_stops_the_session_and_keeps_the_response() -> None:
    body = message_body(usage_extra={"cache_read_input_tokens": 50})
    router, _ = make_router(ok(body), ok())
    with pytest.raises(UnpricedUsage) as caught:
        router.complete(Job.author, messages=ASK, max_tokens=64, generator_family=None, clearance=None)
    assert caught.value.response.usage.cache_read_input_tokens == 50
    with pytest.raises(BudgetExhausted, match="no longer known"):
        router.complete(Job.author, messages=ASK, max_tokens=64, generator_family=None, clearance=None)


def test_temperature_is_refused_for_a_model_that_rejects_it() -> None:
    """claude-api skill: sampling parameters return a 400 on Opus 5.5; Haiku 4.5 accepts them."""
    router, transport = make_router(ok(message_body(model="claude-haiku-4-5")))
    with pytest.raises(UnsupportedParameter, match="claude-opus-5-5"):
        router.complete(Job.author, messages=ASK, max_tokens=64, generator_family=None, clearance=None, temperature=0.0)
    assert transport.sent == [] and router.ledger.spent_usd == 0
    routed = router.complete(Job.classify, messages=ASK, max_tokens=64, generator_family=None, clearance=None, temperature=0.0)
    assert routed.response.request.temperature == 0.0
    assert json.loads(transport.sent[0][0])["temperature"] == 0.0


def test_routed_calls_are_deterministic() -> None:
    def run() -> object:
        router, _ = make_router(failure(529, "overloaded_error"), ok())
        return router.complete(Job.author, messages=ASK, max_tokens=64, generator_family=None, clearance=None)

    assert run() == run()
