"""The capability broker: the one place that holds grants and, in time, credentials.

`ARCHITECTURE.md` §9 hangs a hard claim on this component — "Credentials in a grader: impossible by
construction: only the capability broker holds them" — and §6 makes every reach into the real world
go through consent. This is V1: grants with consent, expiry and a session budget. Nothing is granted
by default; an ungranted capability resolves to **UNAVAILABLE naming what is missing**, which is
exactly the string the planner's UNAVAILABLE state and EL-214's permission request already expect.

What a grant is
---------------
A :class:`Grant` names a :class:`~evalloop.vocab.Tool` (optionally scoped to one endpoint, e.g.
``postgres://localhost/shop``), who granted it and why, an optional expiry, and caps (rows / bytes /
time / budget). Caps are the grant parameters EL-006 insists on — ``None`` until a grant supplies
them, never defaulted. Consent is explicit and revocable; a lapsed grant reverts to UNAVAILABLE on
the next check, with no restart.

Credentials
-----------
This V1 holds the *shape* of credentials — a grant records a credential **source** (``.env`` key,
secrets-manager path), never a value. Resolving a source to a secret is the capability layer's alone
(EL-209 already reads the one credential there, and a repo-wide source scan enforces that no other
module reads the environment; when ``evalloop/connect/`` lands it is covered by the same scan). This
module reads no environment variable itself.

Budget
------
The session budget reuses EL-209's :class:`~evalloop.capability.router.CostLedger` — one ledger, one
hard stop (``ARCHITECTURE.md`` §9, "cost runaway"). The broker exposes it so a connector charges
through the same books a model call does.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from evalloop.capability.router import BudgetExhausted, CostLedger
from evalloop.vocab import Tool

__all__ = ["Availability", "Caps", "CapabilityBroker", "CapabilityError", "Grant"]


class CapabilityError(Exception):
    """A misuse of the broker (a bad cap, a non-Tool). A denied capability is not this — that is an
    :class:`Availability` with ``granted=False``, which the caller is meant to read, not catch."""


@dataclass(frozen=True, slots=True)
class Caps:
    """The grant parameters a capability runs under. ``None`` means unset (EL-006), never a default."""

    max_rows: int | None = None
    max_bytes: int | None = None
    max_seconds: float | None = None
    budget_usd: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("max_rows", "max_bytes"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                raise CapabilityError(f"{name} must be a positive int or None, got {value!r}")
        if self.max_seconds is not None and not (isinstance(self.max_seconds, (int, float)) and self.max_seconds > 0):
            raise CapabilityError(f"max_seconds must be a positive number or None, got {self.max_seconds!r}")
        if self.budget_usd is not None and (not isinstance(self.budget_usd, Decimal) or self.budget_usd < 0):
            raise CapabilityError(f"budget_usd must be a non-negative Decimal or None, got {self.budget_usd!r}")


@dataclass(frozen=True, slots=True)
class Grant:
    """One capability granted: a tool (maybe an endpoint), who granted it, why, when it lapses, its caps."""

    tool: Tool
    endpoint: str | None
    granted_by: str
    reason: str
    expires_at: float | None  # monotonic deadline; None = no expiry
    caps: Caps
    credential_source: str | None = None  # the *source* of a secret, never the secret


@dataclass(frozen=True, slots=True)
class Availability:
    """The answer to "can I use this capability right now?" — granted with its grant, or not, with why."""

    granted: bool
    reason: str | None
    grant: Grant | None


def _key(tool: Tool, endpoint: str | None) -> tuple[Tool, str | None]:
    return (tool, endpoint)


class CapabilityBroker:
    """Holds the session's grants and answers availability. Nothing is granted until it is granted."""

    def __init__(self, *, budget_usd: Decimal | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._grants: dict[tuple[Tool, str | None], Grant] = {}
        self._clock = clock
        self._ledger = CostLedger(budget_usd) if budget_usd is not None else None

    # -- consent ----------------------------------------------------------------

    def grant(
        self,
        tool: Tool,
        *,
        granted_by: str,
        reason: str,
        endpoint: str | None = None,
        expires_in: float | None = None,
        caps: Caps | None = None,
        credential_source: str | None = None,
    ) -> Grant:
        """Record explicit consent for ``tool`` (optionally one endpoint). The only way to make it granted."""
        if not isinstance(tool, Tool):
            raise CapabilityError(f"{tool!r} is not a Tool")
        if not granted_by.strip() or not reason.strip():
            raise CapabilityError("a grant records who granted it and why — both are required")
        if expires_in is not None and not (isinstance(expires_in, (int, float)) and expires_in > 0):
            raise CapabilityError(f"expires_in must be a positive number of seconds or None, got {expires_in!r}")
        expires_at = None if expires_in is None else self._clock() + expires_in
        record = Grant(tool, endpoint, granted_by, reason, expires_at, caps or Caps(), credential_source)
        self._grants[_key(tool, endpoint)] = record
        return record

    def revoke(self, tool: Tool, *, endpoint: str | None = None) -> bool:
        """Withdraw a grant. Returns whether one was there to withdraw."""
        return self._grants.pop(_key(tool, endpoint), None) is not None

    # -- the question everything asks -------------------------------------------

    def check(self, tool: Tool, *, endpoint: str | None = None) -> Availability:
        """Is ``tool`` (for ``endpoint``) usable right now? Expired or never-granted → not, with a reason.

        An endpoint-scoped check accepts an exact ``(tool, endpoint)`` grant, or a blanket
        ``(tool, None)`` grant that covers every endpoint.
        """
        if not isinstance(tool, Tool):
            raise CapabilityError(f"{tool!r} is not a Tool")
        grant = self._grants.get(_key(tool, endpoint))
        if grant is None and endpoint is not None:
            grant = self._grants.get(_key(tool, None))
        if grant is None:
            where = f" for {endpoint!r}" if endpoint else ""
            return Availability(
                False,
                f"the capability {tool.value!r} is not granted{where}; grant it before this can run",
                None,
            )
        if grant.expires_at is not None and self._clock() >= grant.expires_at:
            del self._grants[_key(grant.tool, grant.endpoint)]
            return Availability(
                False,
                f"the grant for {tool.value!r} has expired; grant it again before this can run",
                None,
            )
        return Availability(True, None, grant)

    def available_tools(self) -> frozenset[Tool]:
        """The tools the planner may treat as present: those with at least one live grant."""
        tools = {tool for (tool, _endpoint) in self._grants}
        return frozenset(tool for tool in tools if self._any_live(tool))

    def _any_live(self, tool: Tool) -> bool:
        for (grant_tool, endpoint) in list(self._grants):
            if grant_tool is tool and self.check(tool, endpoint=endpoint).granted:
                return True
        return False

    # -- budget -----------------------------------------------------------------

    @property
    def ledger(self) -> CostLedger | None:
        """The session's cost ledger, or ``None`` if no budget was set. One ledger, one hard stop."""
        return self._ledger

    def spend(self, cost_usd: Decimal) -> None:
        """Charge the session budget, refusing (``BudgetExhausted``) when it cannot cover the spend."""
        if self._ledger is None:
            raise CapabilityError("no session budget was set, so there is nothing to spend against")
        self._ledger.reserve(cost_usd)
        self._ledger.charge(cost_usd)

    @property
    def budget_exhausted(self) -> bool:
        if self._ledger is None:
            return False
        try:
            self._ledger.reserve(Decimal(0))
        except BudgetExhausted:
            return True
        return False
