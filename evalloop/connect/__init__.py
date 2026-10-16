"""The connector layer (``ARCHITECTURE.md`` §6, component 16): discover → consent → envelope → probe.

Reaching a real database or vector store is "the single most dangerous capability in the product"
(§1), so it is staged. This package builds that staging. The first step, :mod:`discover`, is
**inert**: it reports *evidence* of endpoints with provenance and opens nothing. Consent, the
read-only envelope, and the connectors themselves are later tickets (EL-304 onward).

Nothing here imports a database driver (decision EL-006: connectors shell out), and nothing reads a
credential (decision EL-302: only the capability broker does) — a repo-wide source scan enforces
both.
"""

from __future__ import annotations

from evalloop.connect.discover import Candidate, Provenance, discover

__all__ = ["Candidate", "Provenance", "discover"]
