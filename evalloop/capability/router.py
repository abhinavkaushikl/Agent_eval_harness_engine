"""Routing by job, the cross-family rule, and what a session may spend.

``AGENT.md`` §4: the capability layer owns "LLM routing by job: classify / author / judge /
diagnose", and "a judge must be from a different model family than the generator". ``AGENT.md``
§5 makes that a non-negotiable: "Never same-family judging", because of self-preference bias. The
corpus backs it as ``F5_cross_family_panel``.

The cross-family rule raises; it never warns
--------------------------------------------
A warning would make self-preference bias discouraged; the point is to make it impossible. So
:meth:`Router.select` raises :class:`SameFamilyJudge` for a judge whose family matches the
generator's, naming both. It also raises :class:`UnknownGeneratorFamily` when the generator's
family is not known, because "probably different" is exactly the guess the rule exists to
forbid.

Every model in ``models.CATALOG`` is family ``claude``. So with that catalog alone, judging an
artifact a Claude model wrote always raises. A cross-family judge needs a second provider's
transport, and that comes with the judge itself in M4.

Cost
----
Each call is priced from the model's configured per-million-token rates and the usage the API
reports. The cost is recorded on the call's :class:`RoutedResponse` and added to the session's
:class:`CostLedger`. Money is ``Decimal``, so repeated additions never drift.

``ARCHITECTURE.md`` §9 lists "Cost runaway" with the guard "Per-session budget, hard stop". The
stop works in two steps:

- **Before a call:** the call is refused if the session is already at its budget, or if the
  call's worst-case *output* — ``max_tokens`` at the output rate — would cross the budget.
- **After a call:** the actual cost is charged.

The input side cannot be priced before the call, because counting input tokens needs another API
request. So a session can end above its budget, by at most the last call's input cost. That
overshoot is the documented limit of this stop, not a hidden one.

The budget has no default; whoever grants the capability sets it. If the API reports usage this
layer has no price for (prompt-cache tokens, which these requests never ask for), the spend is no
longer known. The ledger then stops the session rather than carry on with a number it cannot
support.

Sampling parameters
-------------------
``temperature`` is refused before any call or charge when the routed model does not accept it.
Most current models reject it with a 400, according to the catalog's source. Failing locally
saves a round trip and an error that would look like the API's fault.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from evalloop._compat import StrEnum
from evalloop.capability.llm import (
    Clearance,
    LLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    Usage,
)

__all__ = [
    "BudgetExhausted",
    "CostLedger",
    "Job",
    "ModelConfig",
    "NoRoute",
    "RoutedResponse",
    "Router",
    "SameFamilyJudge",
    "UnknownGeneratorFamily",
    "UnpricedUsage",
    "UnsupportedParameter",
    "call_cost",
]

#: Prices are quoted per million tokens (claude-api skill, Current Models table: "$/1M").
_PER_MILLION = Decimal(1_000_000)


class Job(StrEnum):
    """What a call is for. ``AGENT.md`` §4: "classify / author / judge / diagnose"."""

    classify = "classify"
    author = "author"
    judge = "judge"
    diagnose = "diagnose"


class SameFamilyJudge(LLMError):
    """A judge from the generator's own family. ``AGENT.md`` §5: never same-family judging."""


class UnknownGeneratorFamily(LLMError):
    """A judge was asked for without saying which family generated the artifact."""


class NoRoute(LLMError):
    """No model is configured for this job."""


class UnsupportedParameter(LLMError):
    """A parameter the routed model rejects, for example ``temperature``."""


class BudgetExhausted(LLMError):
    """The session's budget cannot cover the next call. ``ARCHITECTURE.md`` §9: hard stop."""


class UnpricedUsage(LLMError):
    """The API reported usage this layer has no price for, so the session's spend is unknown.

    The response is attached as ``response``, because the call happened and was paid for.
    """

    def __init__(self, message: str, response: LLMResponse) -> None:
        super().__init__(message)
        self.response = response


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string, got {value!r}")
    return value


def _require_price(name: str, value: object) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive, finite Decimal, got {value!r}")
    return value


@dataclass(frozen=True)
class ModelConfig:
    """One model the router may use: its id, its family, its prices, and where those came from."""

    model_id: str
    family: str
    provider: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    accepts_sampling: bool
    source: str

    def __post_init__(self) -> None:
        for name, value in (
            ("model_id", self.model_id),
            ("family", self.family),
            ("provider", self.provider),
            ("source", self.source),
        ):
            _require_text(name, value)
        _require_price("input_usd_per_mtok", self.input_usd_per_mtok)
        _require_price("output_usd_per_mtok", self.output_usd_per_mtok)
        if not isinstance(self.accepts_sampling, bool):
            raise ValueError(f"accepts_sampling must be a bool, got {self.accepts_sampling!r}")


def call_cost(model: ModelConfig, usage: Usage) -> Decimal:
    """What a call cost in US dollars, from the model's rates and the reported usage.

    Raises ``ValueError`` for usage that has no configured price (prompt-cache tokens); the
    router turns that into :class:`UnpricedUsage`.
    """
    if usage.cache_creation_input_tokens or usage.cache_read_input_tokens:
        raise ValueError(
            "prompt-cache tokens have no configured price: "
            f"{usage.cache_creation_input_tokens} written, {usage.cache_read_input_tokens} read"
        )
    return (
        Decimal(usage.input_tokens) * model.input_usd_per_mtok
        + Decimal(usage.output_tokens) * model.output_usd_per_mtok
    ) / _PER_MILLION


class CostLedger:
    """A session's spend against its budget. One ledger per session; it only ever adds."""

    def __init__(self, budget_usd: Decimal) -> None:
        self._budget = _require_price("budget_usd", budget_usd)
        self._spent = Decimal(0)
        self._charges: list[Decimal] = []
        self._unknown: str | None = None

    @property
    def budget_usd(self) -> Decimal:
        return self._budget

    @property
    def spent_usd(self) -> Decimal:
        return self._spent

    @property
    def charges(self) -> tuple[Decimal, ...]:
        """Each call's cost, in the order the calls were made."""
        return tuple(self._charges)

    def reserve(self, worst_case_output_usd: Decimal) -> None:
        """Refuse the next call unless the budget can cover its worst-case output."""
        if self._unknown is not None:
            raise BudgetExhausted(f"the session's spend is no longer known: {self._unknown}")
        if self._spent >= self._budget:
            raise BudgetExhausted(f"spent ${self._spent} of a ${self._budget} budget")
        if self._spent + worst_case_output_usd > self._budget:
            raise BudgetExhausted(
                f"the next call could cost up to ${worst_case_output_usd} in output, and only "
                f"${self._budget - self._spent} of the ${self._budget} budget is left"
            )

    def charge(self, cost_usd: Decimal) -> None:
        self._spent += cost_usd
        self._charges.append(cost_usd)

    def mark_unknown(self, reason: str) -> None:
        """Stop the session: a call happened whose cost cannot be computed."""
        self._unknown = reason


@dataclass(frozen=True)
class RoutedResponse:
    """A routed call: which job, which model, the response, what it cost, and the session total."""

    job: Job
    model: ModelConfig
    response: LLMResponse
    cost_usd: Decimal
    session_spent_usd: Decimal


class Router:
    """Picks the model for a job, enforces the cross-family rule, and keeps the session's books."""

    def __init__(
        self, *, routes: Mapping[Job, ModelConfig], client: LLMClient, ledger: CostLedger
    ) -> None:
        for job, model in routes.items():
            if not isinstance(job, Job) or not isinstance(model, ModelConfig):
                raise ValueError(f"routes must map Job to ModelConfig, got {job!r}: {model!r}")
        self._routes = MappingProxyType(dict(routes))
        self._client = client
        self._ledger = ledger

    @property
    def ledger(self) -> CostLedger:
        return self._ledger

    def select(self, job: Job, *, generator_family: str | None) -> ModelConfig:
        """The model configured for ``job``. For a judge, it must differ in family from the generator."""
        model = self._routes.get(job)
        if model is None:
            raise NoRoute(f"no model is configured for the {job.value!r} job")
        if job is Job.judge:
            if generator_family is None:
                raise UnknownGeneratorFamily(
                    "a judge needs the generator's model family, so that the cross-family rule "
                    "can be checked rather than assumed"
                )
            if model.family == generator_family:
                raise SameFamilyJudge(
                    f"the judge route {model.model_id!r} is family {model.family!r}, and the "
                    f"artifact was generated by family {generator_family!r}: same-family judging "
                    "is never allowed (AGENT.md section 5; F5_cross_family_panel)"
                )
        return model

    def complete(
        self,
        job: Job,
        *,
        messages: Sequence[Message],
        max_tokens: int,
        generator_family: str | None,
        clearance: Clearance | None,
        system: str | None = None,
        temperature: float | None = None,
    ) -> RoutedResponse:
        """Route, check the budget, call, price, charge. Each refusal happens before any money moves."""
        model = self.select(job, generator_family=generator_family)
        if temperature is not None and not model.accepts_sampling:
            raise UnsupportedParameter(
                f"{model.model_id} does not accept temperature ({model.source}); leave it unset"
            )
        request = LLMRequest(
            model_id=model.model_id,
            max_tokens=max_tokens,
            messages=tuple(messages),
            system=system,
            temperature=temperature,
        )
        self._ledger.reserve(Decimal(max_tokens) * model.output_usd_per_mtok / _PER_MILLION)
        response = self._client.complete(request, clearance=clearance)
        try:
            cost = call_cost(model, response.usage)
        except ValueError as error:
            self._ledger.mark_unknown(str(error))
            raise UnpricedUsage(str(error), response) from error
        self._ledger.charge(cost)
        return RoutedResponse(job, model, response, cost, self._ledger.spent_usd)
