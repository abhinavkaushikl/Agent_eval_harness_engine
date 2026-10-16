"""The Qdrant connector: read-only over HTTP via urllib, against a fake server fixture (no network).

The load-bearing proofs: probe/describe/read work over HTTP through the broker and envelope; describe
enumerates collections AND the embedding model (reporting None honestly when the store omits it); a
write/delete verb is rejected by the envelope before any request is sent; and no qdrant-client is
imported. A stdlib HTTP server on loopback stands in for Qdrant — no live server, no network.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.envelope import ReadOnlyViolation
from evalloop.connect.protocol import Connector, NotAuthorized
from evalloop.connect.vector_qdrant import QdrantConnector, reject_vector_writes
from evalloop.vocab import Tool

_ENDPOINT = "qdrant://localhost"

_COLLECTIONS = {"result": {"collections": [{"name": "docs"}, {"name": "faqs"}]}, "status": "ok"}
_DOCS = {"result": {"config": {"params": {"vectors": {"size": 384, "distance": "Cosine", "model": "BAAI/bge-small-en-v1.5"}}}}}
_FAQS = {"result": {"config": {"params": {"vectors": {"size": 768, "distance": "Dot"}}}}}  # no model recorded
_SEARCH = {"result": [{"id": 1, "score": 0.9, "payload": {"text": "a"}}, {"id": 2, "score": 0.8, "payload": {"text": "b"}}]}


class _FakeQdrant(BaseHTTPRequestHandler):
    requests: list[tuple[str, str]] = []

    def log_message(self, *args: object) -> None:  # silence the handler
        pass

    def _reply(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record_and_route(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        type(self).requests.append((method, self.path))
        if method == "GET" and self.path == "/collections":
            self._reply(_COLLECTIONS)
        elif method == "GET" and self.path == "/collections/docs":
            self._reply(_DOCS)
        elif method == "GET" and self.path == "/collections/faqs":
            self._reply(_FAQS)
        elif method == "POST" and self.path.endswith("/points/search"):
            self._reply(_SEARCH)
        else:
            self._reply({"result": True})  # a write would land here — but the envelope must block it first

    def do_GET(self) -> None:
        self._record_and_route("GET")

    def do_POST(self) -> None:
        self._record_and_route("POST")

    def do_PUT(self) -> None:
        self._record_and_route("PUT")

    def do_DELETE(self) -> None:
        self._record_and_route("DELETE")


@pytest.fixture
def server() -> Iterator[str]:
    _FakeQdrant.requests = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeQdrant)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _granted() -> CapabilityBroker:
    broker = CapabilityBroker()
    broker.grant(Tool.vector_store, granted_by="test", reason="read-only vector search", endpoint=_ENDPOINT, caps=Caps(max_rows=100))
    return broker


def _conn(server: str, **kw: object) -> QdrantConnector:
    return QdrantConnector(server, broker=_granted(), endpoint=_ENDPOINT, **kw)  # type: ignore[arg-type]


# -- the contract, over HTTP -----------------------------------------------------------


def test_is_a_connector(server: str) -> None:
    assert isinstance(_conn(server), Connector)


def test_probe_reaches_qdrant_over_http(server: str) -> None:
    result = _conn(server).probe()
    assert result.reachable is True and result.read_only is True


def test_read_is_a_vector_search_returning_rows(server: str) -> None:
    res = _conn(server, collection="docs").read(json.dumps({"vector": [0.1, 0.2], "limit": 2}))
    assert [tuple(r) for r in res.rows] == [(1, 0.9, {"text": "a"}), (2, 0.8, {"text": "b"})]
    assert ("POST", "/collections/docs/points/search") in _FakeQdrant.requests


def test_search_respects_the_cap(server: str) -> None:
    broker = CapabilityBroker()
    broker.grant(Tool.vector_store, granted_by="t", reason="r", endpoint=_ENDPOINT, caps=Caps(max_rows=1))
    conn = QdrantConnector(server, broker=broker, endpoint=_ENDPOINT)
    res = conn.search("docs", {"vector": [0.1], "limit": 10})
    assert res.shape.row_count == 1 and res.shape.truncated is True


# -- describe enumerates collections AND the embedding model ---------------------------


def test_describe_enumerates_collections_and_the_embedding_model(server: str) -> None:
    schema = _conn(server).describe()
    by_name = {c.name: c for c in schema.collections}
    assert set(by_name) == {"docs", "faqs"}
    assert by_name["docs"].embedding_model == "BAAI/bge-small-en-v1.5"
    assert by_name["docs"].vector_size == 384 and by_name["docs"].distance == "Cosine"
    # faqs records no model: reported as unknown, never invented (corpus G1)
    assert by_name["faqs"].embedding_model is None
    assert by_name["faqs"].vector_size == 768


# -- a write/delete verb is rejected by the envelope, before the wire ------------------


def test_a_write_or_delete_verb_is_rejected_before_any_request(server: str) -> None:
    conn = _conn(server)
    conn.describe()  # a legitimate read, to show the server is reachable
    reads_so_far = len(_FakeQdrant.requests)
    for method, path, body in [
        ("DELETE", "/collections/docs", None),
        ("PUT", "/collections/docs/points", {"points": []}),
        ("POST", "/collections/docs/points", {"points": []}),  # upsert: a POST that is not a search
    ]:
        with pytest.raises(ReadOnlyViolation):
            conn._operation(method, path, body)
    # not one of those reached the fake server
    assert len(_FakeQdrant.requests) == reads_so_far
    assert not any(m in ("PUT", "DELETE") for m, _ in _FakeQdrant.requests)
    assert not any(m == "POST" and not p.endswith("/points/search") for m, p in _FakeQdrant.requests)


def test_reject_vector_writes_classifies_verbs() -> None:
    assert reject_vector_writes(json.dumps({"method": "GET", "path": "/collections"}))
    assert reject_vector_writes(json.dumps({"method": "POST", "path": "/collections/docs/points/search", "body": {}}))
    for op in [
        {"method": "DELETE", "path": "/collections/docs"},
        {"method": "PUT", "path": "/collections/docs/points"},
        {"method": "POST", "path": "/collections/docs/points"},
        {"method": "DELETE", "path": "/collections/docs/points/search"},  # delete to a read path is still a delete
    ]:
        with pytest.raises(ReadOnlyViolation):
            reject_vector_writes(json.dumps(op))


# -- the broker gates every call -------------------------------------------------------


def test_an_ungranted_endpoint_is_refused(server: str) -> None:
    conn = QdrantConnector(server, broker=CapabilityBroker(), endpoint=_ENDPOINT, collection="docs")
    with pytest.raises(NotAuthorized):
        conn.describe()
    with pytest.raises(NotAuthorized):
        conn.read(json.dumps({"vector": [0.1]}))


# -- EL-006: no qdrant-client import ---------------------------------------------------


def test_no_qdrant_client_imported() -> None:
    root = Path(__file__).resolve().parent.parent / "evalloop" / "connect"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        low = path.read_text(encoding="utf-8").lower()
        if "import qdrant_client" in low or "from qdrant_client" in low or "qdrant-client" in low:
            offenders.append(path.name)
    assert offenders == [], f"qdrant-client imported under evalloop/connect/: {offenders}"
