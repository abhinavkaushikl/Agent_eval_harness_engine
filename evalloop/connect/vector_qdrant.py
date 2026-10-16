"""A read-only Qdrant connector over its HTTP API, ``urllib`` only — no vendor Python SDK.

``ARCHITECTURE.md`` §6: connect read-only to the vector store; enumerate its collections and the
embedding model in use. An HTTP vector store needs no driver exception (decision EL-006 is about
driver *imports*): ``urllib.request`` speaks Qdrant's REST API directly, so there is nothing to
install and nothing to import but the standard library — the vendor's own Python package is never
imported, and a source scan proves it.

The connector satisfies the EL-306 `Connector` contract (probe / describe / read):
  * **probe** — reach the HTTP API and confirm it answers.
  * **describe** — enumerate collections *and* each collection's embedding model. The model matters:
    a recall@k measured against a different embedding than the application uses is a meaningless
    number (corpus G1). When the store does not record the model, describe reports it as ``None`` —
    unknown, never guessed.
  * **read** — a read-only vector search. Every backend call is expressed as an HTTP *operation*
    (method + path + body) and passed through the read-only envelope (EL-305), whose guard rejects
    any write/delete verb **before** the request is sent. The safety is the envelope's, not Qdrant's.

Every call is authorised through the capability broker (EL-302) first. This connector reads no
credentials and no environment (ARCHITECTURE.md §9); an authenticated Qdrant would have its header
injected by the capability layer, not stored here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from evalloop.capability.broker import CapabilityBroker
from evalloop.connect.envelope import (
    AuditEntry,
    AuditLog,
    Caps,
    ReadOnlyEnvelope,
    ReadOnlyViolation,
    Result,
    Statement,
    StatementKind,
    WriteScope,
)
from evalloop.connect.protocol import Collection, ConnectorError, NotAuthorized, ProbeResult, Schema, Table
from evalloop.vocab import Tool

__all__ = ["QdrantConnector", "reject_vector_writes"]

# POST is read-only only to these query endpoints; every other verb/path is a write.
_READ_POST_SUFFIXES = ("/points/search", "/points/query", "/points/scroll", "/points/recommend", "/points/count", "/points/search/batch")


def reject_vector_writes(op: str, write_scope: WriteScope | None = None) -> tuple[Statement, ...]:
    """The envelope's layer-1 guard for a vector store: allow read verbs, reject write/delete verbs.

    ``op`` is a JSON operation ``{"method": ..., "path": ..., "body": ...}``. A GET, or a POST to a
    known query endpoint, is a read; anything else (PUT/DELETE/PATCH, or a POST that writes points or
    collections) is rejected before the request is sent.
    """
    method, path = _method_and_path(op)
    is_read = method == "GET" or (method == "POST" and any(path.endswith(s) for s in _READ_POST_SUFFIXES))
    if is_read:
        return (Statement(index=0, kind=StatementKind.READ, keyword=method, text=op),)
    raise ReadOnlyViolation(
        Statement(index=0, kind=StatementKind.DDL, keyword=method, text=op),
        f"{method} {path} is a write/delete operation on the vector store; it never reaches the wire",
    )


def _method_and_path(op: str) -> tuple[str, str]:
    try:
        parsed = json.loads(op)
        return str(parsed["method"]).upper(), str(parsed["path"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ConnectorError(f"malformed vector operation: {op!r} ({exc})") from exc


class _HttpExecutor:
    """Adapts an HTTP operation to the envelope's ``Executor`` protocol: it performs the request."""

    read_only = True

    def __init__(self, call: Any) -> None:
        self._call = call  # the connector's _http, bound

    def run(self, op: str, *, max_rows: int | None) -> Sequence[Sequence[object]]:
        parsed = json.loads(op)
        payload = self._call(str(parsed["method"]).upper(), str(parsed["path"]), parsed.get("body"))
        return _hits_to_rows(payload)


def _hits_to_rows(payload: Any) -> list[tuple[object, ...]]:
    result = payload.get("result") if isinstance(payload, dict) else None
    hits = result if isinstance(result, list) else []
    rows: list[tuple[object, ...]] = []
    for hit in hits:
        if isinstance(hit, dict):
            rows.append((hit.get("id"), hit.get("score"), hit.get("payload")))
        else:
            rows.append((hit,))
    return rows


class QdrantConnector:
    """probe / describe / read against a Qdrant HTTP endpoint, through the broker and the envelope."""

    def __init__(
        self,
        base_url: str,
        *,
        broker: CapabilityBroker,
        endpoint: str,
        envelope: ReadOnlyEnvelope | None = None,
        tool: Tool = Tool.vector_store,
        collection: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = endpoint
        self._base = base_url.rstrip("/")
        self._broker = broker
        self._tool = tool
        self._collection = collection
        self._timeout = timeout
        self._envelope = envelope if envelope is not None else ReadOnlyEnvelope(AuditLog(), static_guard=reject_vector_writes)
        self._executor = _HttpExecutor(self._http)

    # -- authorisation ------------------------------------------------------------------

    def _authorize(self) -> Caps:
        decision = self._broker.check(self._tool, endpoint=self.endpoint)
        if not decision.granted or decision.grant is None:
            raise NotAuthorized(decision.reason or f"{self._tool.value} is not granted for {self.endpoint!r}")
        return decision.grant.caps

    # -- the raw HTTP call (urllib, no SDK) ---------------------------------------------

    def _http(self, method: str, path: str, body: object = None) -> dict[str, object]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as exc:
            raise ConnectorError(f"Qdrant HTTP {method} {path} failed: {exc}") from exc
        decoded: dict[str, object] = json.loads(raw) if raw else {}
        return decoded

    # -- the three operations -----------------------------------------------------------

    def probe(self) -> ProbeResult:
        """Reachable, and read-only? Authorised, then a GET of the collections list. No write verbs."""
        self._authorize()
        try:
            self._http("GET", "/collections")
        except ConnectorError as exc:
            self._log("probe", error=str(exc))
            return ProbeResult(reachable=False, read_only=True, detail=str(exc))
        self._log("probe")
        return ProbeResult(reachable=True, read_only=True, detail=f"Qdrant reachable at {self._base}")

    def describe(self) -> Schema:
        """Enumerate collections and each one's embedding model. GETs only — reads no vectors."""
        self._authorize()
        listing = self._http("GET", "/collections")
        names = _collection_names(listing)
        collections: list[Collection] = []
        for name in names:
            info = self._http("GET", f"/collections/{name}")
            size, distance, model = _vector_config(info)
            collections.append(Collection(name=name, vector_size=size, distance=distance, embedding_model=model))
        self._log("describe")
        return Schema(tables=(), collections=tuple(collections))

    def read(self, sql: str) -> Result:
        """A read-only vector search. ``sql`` is the Qdrant search body (JSON); writes are impossible here."""
        collection = self._collection
        if collection is None:
            raise ConnectorError("no collection set; construct QdrantConnector(collection=...) or use search()")
        body = json.loads(sql) if sql.strip() else {}
        return self._search(collection, body)

    def search(self, collection: str, body: Any) -> Result:
        """Search ``collection`` with a Qdrant search body, routed through the envelope."""
        return self._search(collection, body)

    # -- the single chokepoint: every untrusted op goes through the envelope -------------

    def _search(self, collection: str, body: Any) -> Result:
        caps = self._authorize()
        op = json.dumps({"method": "POST", "path": f"/collections/{collection}/points/search", "body": body})
        return self._envelope.execute(op, endpoint=self.endpoint, caps=caps, executor=self._executor)

    def _operation(self, method: str, path: str, body: object = None) -> Result:
        """Run an arbitrary HTTP operation through the envelope. A write verb is rejected here."""
        caps = self._authorize()
        op = json.dumps({"method": method, "path": path, "body": body})
        return self._envelope.execute(op, endpoint=self.endpoint, caps=caps, executor=self._executor)

    # -- helper -------------------------------------------------------------------------

    def _log(self, operation: str, *, error: str | None = None) -> None:
        self._envelope.audit.append(
            AuditEntry(
                endpoint=self.endpoint,
                redacted_sql=f"<{operation}>",
                statement_kinds=(operation,),
                caps=Caps(),
                write_scope=None,
                result=None,
                error=error,
            )
        )


def _collection_names(listing: dict[str, object]) -> list[str]:
    result = listing.get("result")
    collections = result.get("collections") if isinstance(result, dict) else None
    if not isinstance(collections, list):
        return []
    names: list[str] = []
    for item in collections:
        if isinstance(item, dict) and "name" in item:
            names.append(str(item["name"]))
    return names


def _vector_config(info: dict[str, object]) -> tuple[int | None, str | None, str | None]:
    """Pull (vector_size, distance, embedding_model) from a Qdrant collection-info body.

    The model is read from the collection's vector config when the store records it (Qdrant's
    inference metadata); otherwise it is ``None`` — unknown, not invented.
    """
    result = info.get("result")
    params = result.get("config", {}).get("params", {}) if isinstance(result, dict) else {}
    vectors = params.get("vectors") if isinstance(params, dict) else None
    size: int | None = None
    distance: str | None = None
    model: str | None = None
    # a single unnamed vector config, or the first named one
    config = vectors
    if isinstance(vectors, dict) and "size" not in vectors and vectors:
        first = next(iter(vectors.values()))
        config = first if isinstance(first, dict) else vectors
    if isinstance(config, dict):
        raw_size = config.get("size")
        size = int(raw_size) if isinstance(raw_size, int) else None
        distance = str(config["distance"]) if "distance" in config else None
        model = str(config["model"]) if "model" in config else None
    if model is None and isinstance(params, dict) and "model" in params:
        model = str(params["model"])
    return size, distance, model
