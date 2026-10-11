"""The signature-only test author: isolation proved structurally, LOW that cannot be overridden.

The suite is offline. The author is LLM-facing, so under EL-209's option (b) it makes no outbound
call without a ``Clearance`` and nothing issues one; here a fake in-process transport stands in for
the model, and a socket guard proves no test reaches the network.

The load-bearing test is ``test_the_body_never_reaches_the_request``: a unique string is placed in
a function's body and asserted absent from the assembled request. Everything else is secondary to
that, as the ticket says.
"""

from __future__ import annotations

import json
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.capability.llm import HTTPReply, LLMClient, RetryPolicy
from evalloop.capability.router import BudgetExhausted, CostLedger, Job, ModelConfig, Router
from evalloop.grade import run_sandboxed
from evalloop.grade.oracles import Artifact
from evalloop.grade.oracles import author as author_module
from evalloop.grade.oracles.author import (
    WHY_LOW,
    AuthoredOracle,
    AuthorError,
    author_test,
    render_messages,
    signature_view,
)
from evalloop.grade.verdict import Limits
from evalloop.memory.case import CaseKind, OracleConfidence

_MODEL = ModelConfig("claude-opus-5-5", "claude", "anthropic", Decimal("4"), Decimal("20"), False, "test catalog")
_LIMITS = Limits(wall_seconds=30.0)


# -- offline, always --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class _FakeTransport:
    """Returns scripted model replies in order, never leaving the machine. Records every body sent."""

    def __init__(self, *texts: str, leaves_machine: bool = False) -> None:
        self._texts = list(texts)
        self._i = 0
        self._leaves = leaves_machine
        self.sent: list[bytes] = []

    @property
    def leaves_machine(self) -> bool:
        return self._leaves

    def post(self, body: bytes, *, timeout: float) -> HTTPReply:
        self.sent.append(body)
        text = self._texts[min(self._i, len(self._texts) - 1)]
        self._i += 1
        document = {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_details": None,
            "usage": {"input_tokens": 50, "output_tokens": 30},
        }
        return HTTPReply(200, {"request-id": "req_1"}, json.dumps(document).encode())


def _router(*texts: str, budget: str = "1.00", leaves_machine: bool = False) -> tuple[Router, _FakeTransport]:
    transport = _FakeTransport(*texts, leaves_machine=leaves_machine)
    client = LLMClient(
        transport,
        RetryPolicy(max_attempts=2, base_delay=0.0, max_delay=0.0, request_timeout=5.0, total_timeout=10.0),
        jitter_seed=1,
    )
    return Router(routes={Job.author: _MODEL}, client=client, ledger=CostLedger(Decimal(budget))), transport


_GOOD = "from pricing import total\n\ndef test_sum():\n    assert total([1.0, 2.0]) == 3.0\n\ndef test_discount():\n    assert total([10.0], 0.5) == 5.0\n"
_FENCED = "Here is the test:\n```python\n" + _GOOD + "```\nThat tests the contract.\n"
_VACUOUS = "from pricing import total\n\ndef test_exists():\n    assert callable(total)\n"
_NO_TESTS = "from pricing import total\n\nx = total  # no test functions here\n"
_BROKEN_TEST = "from pricing import total\n\ndef test_x(:\n    assert total([1.0])\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pricing.py").write_text(
        'def total(prices: list[float], discount: float = 0.0) -> float:\n'
        '    """Sum the prices, then apply a fractional discount."""\n'
        '    marker = "SENTINEL_BODY_9f8e7d"  # lives only in the body\n'
        '    return sum(prices) * (1 - discount)\n',
        encoding="utf-8",
    )
    return tmp_path


TOTAL = Artifact("pricing.py", "total")


# -- isolation: the whole ticket --------------------------------------------------------


def test_the_body_never_reaches_the_request(repo: Path) -> None:
    """The acceptance criterion that matters: the implementation is not in what is sent."""
    view = signature_view(TOTAL, root=repo)
    # Structural: the view carries no body.
    assert "SENTINEL_BODY_9f8e7d" not in view.signature
    assert "SENTINEL_BODY_9f8e7d" not in (view.docstring or "")
    assert all("SENTINEL_BODY_9f8e7d" not in line for line in view.imports)
    # The rendered prompt, a pure function of the view, carries no body.
    system, messages = render_messages(view)
    blob = system + "\n" + "\n".join(m.content for m in messages)
    assert "SENTINEL_BODY_9f8e7d" not in blob and "return sum" not in blob
    # End to end: the body is not in the bytes actually sent to the model.
    router, transport = _router(_GOOD)
    author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert transport.sent and all(b"SENTINEL_BODY_9f8e7d" not in body for body in transport.sent)


def test_the_view_shows_only_what_is_allowed(repo: Path) -> None:
    view = signature_view(TOTAL, root=repo)
    assert view.qualname == "total"
    assert view.signature == "(prices: list[float], discount: float = 0.0) -> float"
    assert view.docstring == "Sum the prices, then apply a fractional discount."
    assert view.import_module == "pricing"


def test_author_py_never_constructs_a_clearance() -> None:
    """The egress grant is the caller's; this module passes it through and never issues one."""
    source = Path(author_module.__file__).read_text(encoding="utf-8")
    assert "Clearance(" not in source


# -- LOW, and nothing can make it HIGH --------------------------------------------------


def test_an_authored_oracle_is_low_and_generated_with_no_override(repo: Path) -> None:
    router, _ = _router(_GOOD)
    outcome = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    oracle = outcome.oracle
    assert oracle is not None
    assert oracle.confidence is OracleConfidence.low
    assert oracle.case_kind is CaseKind.generated
    # There is no field for either: they are read-only properties.
    assert "confidence" not in {f for f in AuthoredOracle.__dataclass_fields__}
    assert "case_kind" not in {f for f in AuthoredOracle.__dataclass_fields__}
    with pytest.raises((AttributeError, TypeError)):  # frozen + a read-only property: either way, no setting it
        oracle.confidence = OracleConfidence.high  # type: ignore[misc]


def test_the_confidence_reasoning_is_recorded(repo: Path) -> None:
    router, _ = _router(_GOOD)
    oracle = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400).oracle
    assert oracle is not None
    assert oracle.confidence_reasoning == WHY_LOW
    assert "LOW" in WHY_LOW and "HIGH only if a human" in WHY_LOW  # why it is LOW, and what would make it HIGH


# -- a test is kept only if it has teeth ------------------------------------------------


def test_a_test_with_teeth_is_accepted_and_fenced_code_is_unwrapped(repo: Path) -> None:
    router, _ = _router(_FENCED)
    outcome = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert outcome.oracle is not None
    assert outcome.oracle.test_code.startswith("from pricing import total")
    assert "```" not in outcome.oracle.test_code
    assert outcome.attempts[0].detail.startswith("fails against the empty stub")


def test_a_vacuous_test_is_rejected(repo: Path) -> None:
    router, _ = _router(_VACUOUS)
    outcome = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert outcome.oracle is None
    assert "passes against an empty stub" in (outcome.reason or "")


@pytest.mark.parametrize(
    ("reply", "fragment"),
    [(_BROKEN_TEST, "not valid Python"), (_NO_TESTS, "collected no tests")],
)
def test_a_test_that_does_not_run_is_rejected(repo: Path, reply: str, fragment: str) -> None:
    router, _ = _router(reply)
    outcome = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert outcome.oracle is None
    assert fragment in (outcome.reason or "")


def test_the_author_retries_and_records_each_attempt(repo: Path) -> None:
    router, _ = _router(_VACUOUS, _GOOD)  # first vacuous, second has teeth
    outcome = author_test(
        TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400, max_attempts=2
    )
    assert outcome.oracle is not None
    assert [a.accepted for a in outcome.attempts] == [False, True]


# -- the stronger claim: it catches a broken implementation it never saw ----------------


def test_an_authored_test_catches_a_broken_implementation_it_never_saw(repo: Path) -> None:
    router, _ = _router(_GOOD)
    oracle = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400).oracle
    assert oracle is not None
    import sys

    def run(impl: str) -> int | None:
        result = run_sandboxed(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", oracle.test_filename],
            limits=_LIMITS,
            input_files={"pricing.py": impl, oracle.test_filename: oracle.test_code},
        )
        return result.exit_code

    correct = "def total(prices, discount=0.0):\n    return sum(prices) * (1 - discount)\n"
    broken = "def total(prices, discount=0.0):\n    return sum(prices) + discount  # wrong, never seen by the author\n"
    stub = "def total(prices, discount=0.0):\n    raise NotImplementedError\n"
    assert run(correct) == 0  # passes against a correct body
    assert run(broken) == 1  # fails against a wrong body -> caught
    assert run(stub) != 0  # fails against an empty stub -> has teeth


# -- cost and reproducibility -----------------------------------------------------------


def test_cost_is_recorded_per_attempt_and_on_the_session(repo: Path) -> None:
    router, _ = _router(_GOOD)
    outcome = author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert Decimal(outcome.attempts[0].cost_usd) > 0
    assert Decimal(outcome.total_cost_usd) == router.ledger.spent_usd
    assert outcome.oracle is not None and outcome.oracle.served_model == "claude-opus-5-5"


def test_the_same_signature_and_transport_give_the_same_test(repo: Path) -> None:
    first = author_test(TOTAL, root=repo, router=_router(_GOOD)[0], clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    second = author_test(TOTAL, root=repo, router=_router(_GOOD)[0], clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert first.oracle is not None and second.oracle is not None
    assert first.oracle.test_code == second.oracle.test_code
    assert first.attempts[0].request.body() == second.attempts[0].request.body()
    assert first.attempts[0].jitter_seed == second.attempts[0].jitter_seed  # recorded, so variance is visible


def test_a_budget_that_cannot_cover_the_call_stops_before_sending(repo: Path) -> None:
    router, transport = _router(_GOOD, budget="0.0000001")
    with pytest.raises(BudgetExhausted):
        author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
    assert transport.sent == []  # the refusal happened before any call


# -- the egress boundary (option (b)) ---------------------------------------------------


def test_authoring_fails_closed_without_a_clearance(repo: Path) -> None:
    from evalloop.capability.llm import EgressRefused

    router, _ = _router(_GOOD, leaves_machine=True)  # a transport that would leave the machine
    with pytest.raises(EgressRefused):
        author_test(TOTAL, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)


# -- caller mistakes --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("artifact", "match"),
    [
        (Artifact("pricing.py", "Cart.add"), "method"),
        (Artifact("pricing.py", "absent"), "not a top-level function"),
        (Artifact("/abs/pricing.py", "total"), "normalised path"),
        (Artifact("missing.py", "total"), "could not be read"),
    ],
)
def test_the_author_refuses_what_it_cannot_do(repo: Path, artifact: Artifact, match: str) -> None:
    router, _ = _router(_GOOD)
    with pytest.raises(AuthorError, match=match):
        author_test(artifact, root=repo, router=router, clearance=None, sandbox_limits=_LIMITS, max_output_tokens=400)
