"""The Connector contract: probe / describe / read, backend-agnostic.

``ARCHITECTURE.md`` §6: a connector exposes **probe** (is it reachable, and read-only?), **describe**
(its schema — tables and columns, no rows), and **read** (a read-only query carried through the
envelope). Pinning the three operations here, independent of any backend, is what keeps the later
connectors thin: the MCP connector (EL-307), the Postgres/MySQL-over-CLI connector (EL-308) and the
vector-store connector (EL-309) each implement this same `Connector` and inherit the safety wiring.

Two invariants every implementation owes the caller:
  * every call is authorised through the capability broker (EL-302) first — an ungranted endpoint is
    refused, not attempted;
  * the untrusted ``read(sql)`` path runs through the read-only envelope (EL-305), so the three
    safety layers — and not the backend — decide what a model-written query may do.

This module declares the contract and its value types only. It opens nothing and imports no driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from evalloop.connect.envelope import Result

__all__ = ["Column", "Table", "Collection", "Schema", "ProbeResult", "Connector", "ConnectorError", "NotAuthorized"]


class ConnectorError(Exception):
    """A connector could not carry out a call."""


class NotAuthorized(ConnectorError):
    """The capability broker has not granted this endpoint; the call was refused, not attempted."""


@dataclass(frozen=True, slots=True)
class Column:
    """One column: its name and declared type (empty string when the backend states none)."""

    name: str
    type: str


@dataclass(frozen=True, slots=True)
class Table:
    """One table (or, for later backends, one collection) and its columns."""

    name: str
    columns: tuple[Column, ...]


@dataclass(frozen=True, slots=True)
class Collection:
    """One vector-store collection: its vector geometry and the embedding model in use (if recorded).

    ``embedding_model`` is ``None`` when the store does not record it — reported as unknown, never
    guessed. It matters because a recall@k measured against a different embedding than the app uses is
    a meaningless number (corpus G1).
    """

    name: str
    vector_size: int | None
    distance: str | None
    embedding_model: str | None


@dataclass(frozen=True, slots=True)
class Schema:
    """Structure only, never any row: relational tables and/or vector-store collections."""

    tables: tuple[Table, ...]
    collections: tuple[Collection, ...] = ()


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The answer to "can I reach it, and is it read-only?" with a plain-language detail."""

    reachable: bool
    read_only: bool
    detail: str


@runtime_checkable
class Connector(Protocol):
    """probe / describe / read against one endpoint. Backend-agnostic; each call is broker-authorised."""

    endpoint: str

    def probe(self) -> ProbeResult:
        """Reachable, and read-only? No schema, no rows."""
        ...

    def describe(self) -> Schema:
        """The structure — tables and columns. Reads no rows."""
        ...

    def read(self, sql: str) -> Result:
        """Run a read-only query through the envelope, under the granted caps."""
        ...
