"""The models the router may use: configuration, not logic.

Model ids appear nowhere else in ``evalloop/``, and ``tests/test_llm_router.py`` fails if one
does. Routing logic takes a :class:`~evalloop.capability.router.ModelConfig` and never names a
model.

Source
------
Everything below comes from the claude-api skill (cached 2026-09-25, read 2026-10-09):

- **Ids and prices** come from its "Current Models" table, copied exactly. The skill says the ids
  "are complete as-is; never append date suffixes".
- **``accepts_sampling``** comes from its Thinking & Effort table, column "Sampling
  (temperature/top_p/top_k)":
  - "Removed - 400" is ``False``.
  - Sonnet 5.5's "Non-default values - 400" is also ``False``: a parameter that can only be sent
    at its default value pins nothing.
  - "Allowed" is ``True``. Only Opus 4.6, Sonnet 4.6 and Haiku 4.5 are in that state.

Claude Mythos 5.1 is left out: the table marks it "Project Glasswing only".

Prices change, so this table must be refreshed from the same source. ``source`` travels with
every response's routing record, so a cost can always be traced to the rates it used.

Which model serves which job is **not** chosen here. That is a policy decision for whoever
configures the :class:`~evalloop.capability.router.Router`, and no default routing ships.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType

from evalloop.capability.router import ModelConfig

__all__ = ["CATALOG"]

_SOURCE = "claude-api skill: Current Models and Thinking & Effort tables (cached 2026-09-25), read 2026-10-09"


def _anthropic(model_id: str, input_usd: str, output_usd: str, *, accepts_sampling: bool) -> ModelConfig:
    return ModelConfig(
        model_id=model_id,
        family="claude",
        provider="anthropic",
        input_usd_per_mtok=Decimal(input_usd),
        output_usd_per_mtok=Decimal(output_usd),
        accepts_sampling=accepts_sampling,
        source=_SOURCE,
    )


_MODELS = (
    _anthropic("claude-fable-5-1", "10.00", "50.00", accepts_sampling=False),
    _anthropic("claude-fable-5", "10.00", "50.00", accepts_sampling=False),
    _anthropic("claude-opus-5-5", "4.00", "20.00", accepts_sampling=False),
    _anthropic("claude-opus-5", "5.00", "25.00", accepts_sampling=False),
    _anthropic("claude-opus-4-8", "5.00", "25.00", accepts_sampling=False),
    _anthropic("claude-opus-4-7", "5.00", "25.00", accepts_sampling=False),
    _anthropic("claude-opus-4-6", "5.00", "25.00", accepts_sampling=True),
    _anthropic("claude-sonnet-5-5", "2.00", "10.00", accepts_sampling=False),
    _anthropic("claude-sonnet-5", "2.00", "10.00", accepts_sampling=False),
    _anthropic("claude-sonnet-4-6", "3.00", "15.00", accepts_sampling=True),
    _anthropic("claude-haiku-4-5", "1.00", "5.00", accepts_sampling=True),
)

#: Model id to configuration. Read-only.
CATALOG: Mapping[str, ModelConfig] = MappingProxyType({model.model_id: model for model in _MODELS})
