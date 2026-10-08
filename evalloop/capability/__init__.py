"""The capability layer: the only part of EvalLoop that talks to a model (``AGENT.md`` §4).

``llm`` is the stdlib-HTTP client: retries, the egress gate and credentials. ``router`` picks a
model by job, enforces the cross-family rule and keeps the session's budget. ``models`` is the
configured catalog of models.

In M1 no call leaves the machine: see ``llm``'s module docstring, "option (b)".
"""

from __future__ import annotations

from evalloop.capability.llm import (
    AnthropicHTTPTransport,
    APIError,
    Clearance,
    EgressRefused,
    LLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    RetryPolicy,
    Usage,
)
from evalloop.capability.router import (
    BudgetExhausted,
    CostLedger,
    Job,
    ModelConfig,
    RoutedResponse,
    Router,
    SameFamilyJudge,
    UnknownGeneratorFamily,
)

__all__ = [
    "APIError",
    "AnthropicHTTPTransport",
    "BudgetExhausted",
    "Clearance",
    "CostLedger",
    "EgressRefused",
    "Job",
    "LLMClient",
    "LLMError",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "ModelConfig",
    "RetryPolicy",
    "RoutedResponse",
    "Router",
    "SameFamilyJudge",
    "UnknownGeneratorFamily",
    "Usage",
]
