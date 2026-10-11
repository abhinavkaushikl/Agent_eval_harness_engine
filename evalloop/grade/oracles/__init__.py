"""Oracles: what decides whether an artifact is right (``AGENT.md`` §3.6).

``harvest`` returns the oracles a repository already holds -- tests, schemas,
type hints -- each tagged HIGH because a person wrote it. Authored oracles,
tagged LOW, are EL-210's.
"""

from __future__ import annotations

from evalloop.grade.oracles.author import (
    Attempt,
    AuthorError,
    AuthoredOracle,
    AuthoringOutcome,
    SignatureView,
    WHY_LOW,
    author_test,
    signature_view,
)
from evalloop.grade.oracles.harvest import (
    Artifact,
    BaselineStatus,
    Component,
    Excluded,
    Expectation,
    Gap,
    Harvest,
    HarvestError,
    Oracle,
    OracleKind,
    Provenance,
    Unsearched,
    harvest,
)

__all__ = [
    "Artifact",
    "Attempt",
    "AuthorError",
    "AuthoredOracle",
    "AuthoringOutcome",
    "BaselineStatus",
    "Component",
    "Excluded",
    "Expectation",
    "Gap",
    "Harvest",
    "HarvestError",
    "Oracle",
    "OracleKind",
    "Provenance",
    "SignatureView",
    "Unsearched",
    "WHY_LOW",
    "author_test",
    "harvest",
    "signature_view",
]
