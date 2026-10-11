"""Classification: what kind of thing the developer built (``AGENT.md`` §3.4).

M1 holds the heuristics only (``heuristics``): Python files, ``ast`` only, and
an explicit abstention whenever the heuristics cannot say. The LLM fallback
for unclear cases is a later ticket.
"""

from __future__ import annotations

from evalloop.classify.heuristics import (
    EMITTABLE,
    UNDETECTED,
    WITHHELD,
    Abstention,
    ClassifierResult,
    Finding,
    classify_file,
    classify_source,
)

__all__ = [
    "EMITTABLE",
    "UNDETECTED",
    "WITHHELD",
    "Abstention",
    "ClassifierResult",
    "Finding",
    "classify_file",
    "classify_source",
]
