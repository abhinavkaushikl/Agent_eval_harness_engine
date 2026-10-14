"""The capability broker: nothing granted by default, UNAVAILABLE names what is missing, grants expire.

`ARCHITECTURE.md` §9 rests "credentials in a grader: impossible by construction" on this component,
so these tests pin the guarantees: an ungranted capability is refused with a reason, a grant can be
revoked and expires on its own, caps are carried, the budget has a hard stop, and the broker itself
reads no credential.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.capability import Availability, Caps, CapabilityBroker, CapabilityError, Grant
from evalloop.capability.router import BudgetExhausted
from evalloop.vocab import Tool


class _Clock:
    """A clock that only moves when a test moves it, so expiry is deterministic."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# -- nothing is granted by default -----------------------------------------------------


def test_an_ungranted_capability_is_unavailable_and_names_the_tool() -> None:
    broker = CapabilityBroker()
    result = broker.check(Tool.db_connection)
    assert isinstance(result, Availability)
    assert result.granted is False and result.grant is None
    assert "db_connection" in (result.reason or "") and "grant it" in (result.reason or "")


def test_nothing_is_granted_until_it_is_granted() -> None:
    broker = CapabilityBroker()
    assert broker.available_tools() == frozenset()


# -- consent, revocation, expiry -------------------------------------------------------


def test_a_granted_capability_is_available_with_its_grant() -> None:
    broker = CapabilityBroker()
    grant = broker.grant(Tool.sandbox, granted_by="tests", reason="run the artifact")
    result = broker.check(Tool.sandbox)
    assert result.granted and result.grant == grant and isinstance(grant, Grant)
    assert broker.available_tools() == frozenset({Tool.sandbox})


def test_a_grant_records_who_and_why_and_refuses_a_blank() -> None:
    broker = CapabilityBroker()
    with pytest.raises(CapabilityError, match="who granted it and why"):
        broker.grant(Tool.sandbox, granted_by="  ", reason="x")


def test_a_revoked_grant_becomes_unavailable() -> None:
    broker = CapabilityBroker()
    broker.grant(Tool.sandbox, granted_by="tests", reason="run")
    assert broker.revoke(Tool.sandbox) is True
    assert broker.check(Tool.sandbox).granted is False
    assert broker.revoke(Tool.sandbox) is False  # nothing left to revoke


def test_a_grant_expires_without_a_restart() -> None:
    clock = _Clock()
    broker = CapabilityBroker(clock=clock)
    broker.grant(Tool.sandbox, granted_by="tests", reason="run", expires_in=30.0)
    assert broker.check(Tool.sandbox).granted is True
    clock.now += 31.0
    lapsed = broker.check(Tool.sandbox)
    assert lapsed.granted is False and "expired" in (lapsed.reason or "")
    assert broker.available_tools() == frozenset()  # the expired grant is gone


# -- endpoint scoping ------------------------------------------------------------------


def test_an_endpoint_grant_covers_only_that_endpoint() -> None:
    broker = CapabilityBroker()
    broker.grant(Tool.db_connection, endpoint="postgres://localhost/shop", granted_by="tests", reason="read")
    assert broker.check(Tool.db_connection, endpoint="postgres://localhost/shop").granted is True
    assert broker.check(Tool.db_connection, endpoint="postgres://localhost/other").granted is False
    assert broker.check(Tool.db_connection).granted is False  # no blanket grant


def test_a_blanket_grant_covers_every_endpoint() -> None:
    broker = CapabilityBroker()
    broker.grant(Tool.db_connection, granted_by="tests", reason="read any")
    assert broker.check(Tool.db_connection, endpoint="postgres://anywhere/db").granted is True


# -- caps are carried, unset by default (EL-006) ---------------------------------------


def test_caps_default_to_unset_and_validate() -> None:
    assert Caps() == Caps(None, None, None, None)
    grant = CapabilityBroker().grant(
        Tool.db_connection, granted_by="tests", reason="read", caps=Caps(max_rows=1000)
    )
    assert grant.caps.max_rows == 1000 and grant.caps.max_bytes is None
    with pytest.raises(CapabilityError, match="max_rows"):
        Caps(max_rows=0)


def test_a_grant_records_a_credential_source_never_a_value() -> None:
    grant = CapabilityBroker().grant(
        Tool.db_connection, granted_by="tests", reason="read", credential_source=".env:DATABASE_URL"
    )
    assert grant.credential_source == ".env:DATABASE_URL"  # a source, not a secret


# -- the session budget has a hard stop ------------------------------------------------


def test_the_budget_stops_the_session() -> None:
    broker = CapabilityBroker(budget_usd=Decimal("0.10"))
    broker.spend(Decimal("0.07"))
    assert broker.budget_exhausted is False
    with pytest.raises(BudgetExhausted):
        broker.spend(Decimal("0.05"))  # 0.07 + 0.05 > 0.10
    assert broker.ledger is not None and broker.ledger.spent_usd == Decimal("0.07")


def test_spending_without_a_budget_is_a_misuse() -> None:
    with pytest.raises(CapabilityError, match="no session budget"):
        CapabilityBroker().spend(Decimal("0.01"))


# -- the broker reads no credential ----------------------------------------------------


def test_the_broker_reads_no_environment_variable() -> None:
    source = Path(__file__).resolve().parent.parent / "evalloop" / "capability" / "broker.py"
    text = source.read_text(encoding="utf-8")
    assert not re.search(r"\bos\.environ\b|\bgetenv\(|\benviron\[", text)
    # The repo-wide scan in test_llm_router asserts only capability/llm.py reads the environment;
    # the broker holds grants and credential *sources*, never reading a secret itself.
