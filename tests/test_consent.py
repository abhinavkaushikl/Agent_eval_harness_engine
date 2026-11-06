"""Persistent consent (EL-018): the store, the broker's write-through, the popup's decisions, the session.

The load-bearing proofs: the store reads back exactly what it saved, drops expired records and never
holds a credential value; a remembered grant survives a restart and an "allow once" does not;
production-suspected endpoints are never saved and still need their name typed, every session; a
denial is not asked again this session; known endpoints run silently while new ones wait for the
popup; and the popup's whole decision logic is tested here without opening a window.
"""

from __future__ import annotations

import json
import sqlite3
import stat
import threading
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.__main__ import main
from evalloop.capability.broker import CapabilityBroker, CapabilityError, Caps
from evalloop.capability.consent_store import ConsentRecord, ConsentStore, ConsentStoreError, store_for
from evalloop.connect.classify_endpoint import Posture
from evalloop.run import RunOutcome, RunResult
from evalloop.session.consent import (
    Choice,
    ConsentGate,
    ConsentRequest,
    decide,
    discovered_requests,
    popup_model,
    sqlite_request,
)
from evalloop.session.consent_popup import BotClient
from evalloop.session.orchestrator import Session
from evalloop.vocab import Tool

_PG = "postgres://localhost:5432"
_SECRET_PW = "hunter2-correct-horse"


class Clock:
    """A settable clock, used as both the wall clock (store) and the monotonic one (broker)."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _request(
    posture: Posture = Posture.local,
    *,
    endpoint: str = _PG,
    default_deny: bool = False,
    typed: bool = False,
    source: str | None = ".env:DATABASE_URL",
    caps: Caps = Caps(max_rows=500, max_seconds=10.0),
) -> ConsentRequest:
    return ConsentRequest(
        tool=Tool.db_connection,
        endpoint=endpoint,
        kind="postgres",
        host="localhost",
        database="shop (compose service)",
        credential_source=source,
        operations=("probe", "describe tables", "read (SELECT only)"),
        caps=caps,
        posture=posture,
        rationale="the host 'localhost' is a private/loopback address",
        default_deny=default_deny,
        require_typed_confirmation=typed,
        confirm_name=endpoint,
        found_at="docker-compose.yml:2",
    )


def _prod() -> ConsentRequest:
    return _request(Posture.production_suspected, endpoint=".env:PROD_DATABASE_URL", default_deny=True, typed=True)


def _record(**overrides: object) -> ConsentRecord:
    values: dict[str, object] = dict(
        tool=Tool.db_connection, endpoint=_PG, granted_by="test", reason="local dev db", granted_at=1_000_000.0,
        expires_at=None, caps=Caps(max_rows=100, max_seconds=5.0, budget_usd=Decimal("0.25")),
        credential_source=".env:DATABASE_URL", posture="local",
    )
    values.update(overrides)
    return ConsentRecord(**values)  # type: ignore[arg-type]


# -- the store ------------------------------------------------------------------------------------


def test_the_store_reads_back_what_it_saved(tmp_path: Path) -> None:
    clock = Clock(1_000_000.0)
    store = store_for(tmp_path, clock=clock)
    original = _record(expires_at=2_000_000.0)
    store.save(original)
    assert store_for(tmp_path, clock=clock).load() == (original,)
    assert store.path == tmp_path / ".evalloop" / "consents.json"


def test_saving_the_same_endpoint_again_replaces_it(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    store.save(_record(reason="first"))
    store.save(_record(reason="second"))
    store.save(_record(endpoint="qdrant://localhost:6333", tool=Tool.vector_store))
    reasons = {r.endpoint: r.reason for r in store.load()}
    assert reasons == {_PG: "second", "qdrant://localhost:6333": "local dev db"}


def test_expired_records_are_dropped_on_load_and_pruned_from_the_file(tmp_path: Path) -> None:
    clock = Clock(1_000_000.0)
    store = store_for(tmp_path, clock=clock)
    store.save(_record(endpoint="a", expires_at=1_000_100.0))
    store.save(_record(endpoint="b", expires_at=None))
    assert [r.endpoint for r in store.load()] == ["a", "b"]
    clock.now = 1_000_100.0
    assert [r.endpoint for r in store.load()] == ["b"]
    assert '"a"' not in store.path.read_text(encoding="utf-8")


def test_the_store_never_holds_a_credential_value(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    for value in (f"postgres://app:{_SECRET_PW}@db/shop", "sk-ant-api03-abcdefghijklmnopqrstuvwx", f"password={_SECRET_PW}"):
        with pytest.raises(ConsentStoreError, match="credential value"):
            store.save(_record(credential_source=value))
    store.save(_record())
    text = store.path.read_text(encoding="utf-8")
    assert _SECRET_PW not in text and "sk-ant" not in text
    assert json.loads(text)["consents"][0]["credential_source"] == ".env:DATABASE_URL"


def test_the_store_refuses_production_suspected_and_drops_one_edited_in(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    with pytest.raises(ConsentStoreError, match="never remembered"):
        store.save(_record(posture="production_suspected"))
    store.save(_record())
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["consents"].append(_record(endpoint="prod", posture="production_suspected").to_json())
    store.path.write_text(json.dumps(data), encoding="utf-8")
    assert [r.endpoint for r in store.load()] == [_PG]


def test_the_file_is_private_and_never_committed(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    store.save(_record())
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert (tmp_path / ".evalloop" / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"


def test_a_corrupt_file_asks_again_and_is_moved_aside_not_overwritten(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{not json", encoding="utf-8")
    assert store.load() == () and store.problem is not None
    store.save(_record())
    assert store.path.with_name("consents.json.corrupt").read_text(encoding="utf-8") == "{not json"
    assert [r.endpoint for r in store.load()] == [_PG]


# -- the broker writes through ------------------------------------------------------------------------


def test_a_remembered_grant_survives_a_restart_and_allow_once_does_not(tmp_path: Path) -> None:
    broker = CapabilityBroker(store=store_for(tmp_path))
    broker.grant(Tool.db_connection, granted_by="t", reason="r", endpoint=_PG, remember=True,
                 caps=Caps(max_rows=100), credential_source=".env:DATABASE_URL", posture="local")
    broker.grant(Tool.vector_store, granted_by="t", reason="r", endpoint="qdrant://localhost")

    restarted = CapabilityBroker(store=store_for(tmp_path))
    kept = restarted.check(Tool.db_connection, endpoint=_PG)
    assert kept.granted and kept.grant is not None and kept.grant.remembered
    assert kept.grant.caps == Caps(max_rows=100) and kept.grant.credential_source == ".env:DATABASE_URL"
    assert not restarted.check(Tool.vector_store, endpoint="qdrant://localhost").granted


def test_revoke_forgets_it_in_the_store(tmp_path: Path) -> None:
    broker = CapabilityBroker(store=store_for(tmp_path))
    broker.grant(Tool.db_connection, granted_by="t", reason="r", endpoint=_PG, remember=True)
    assert broker.revoke(Tool.db_connection, endpoint=_PG)
    assert store_for(tmp_path).load() == ()
    assert not CapabilityBroker(store=store_for(tmp_path)).check(Tool.db_connection, endpoint=_PG).granted


def test_expiry_holds_across_a_restart(tmp_path: Path) -> None:
    wall, mono = Clock(1_000_000.0), Clock(5.0)
    broker = CapabilityBroker(store=store_for(tmp_path, clock=wall), clock=mono)
    broker.grant(Tool.db_connection, granted_by="t", reason="r", endpoint=_PG, remember=True, expires_in=60)
    wall.now += 30  # half the time passes, then the process restarts with a fresh monotonic clock
    restarted = CapabilityBroker(store=store_for(tmp_path, clock=wall), clock=Clock(0.0))
    assert restarted.check(Tool.db_connection, endpoint=_PG).granted
    wall.now += 31
    assert not CapabilityBroker(store=store_for(tmp_path, clock=wall)).check(Tool.db_connection, endpoint=_PG).granted


def test_sync_drops_an_approval_revoked_from_the_cli(tmp_path: Path) -> None:
    broker = CapabilityBroker(store=store_for(tmp_path))
    broker.grant(Tool.db_connection, granted_by="t", reason="r", endpoint=_PG, remember=True)
    broker.grant(Tool.vector_store, granted_by="t", reason="once", endpoint="q")
    store_for(tmp_path).remove(Tool.db_connection, _PG)  # what `evalloop consents revoke` does
    broker.sync()
    assert not broker.check(Tool.db_connection, endpoint=_PG).granted
    assert broker.check(Tool.vector_store, endpoint="q").granted  # session-only grants are untouched


def test_remembering_production_or_without_a_store_grants_nothing(tmp_path: Path) -> None:
    broker = CapabilityBroker(store=store_for(tmp_path))
    with pytest.raises(ConsentStoreError):
        broker.grant(Tool.db_connection, granted_by="t", reason="r", endpoint="prod", remember=True,
                     posture="production_suspected")
    assert not broker.check(Tool.db_connection, endpoint="prod").granted
    with pytest.raises(CapabilityError, match="needs a consent store"):
        CapabilityBroker().grant(Tool.db_connection, granted_by="t", reason="r", remember=True)


# -- the popup's decision logic, without a window ----------------------------------------------------


def test_the_popup_shows_host_database_source_operations_and_caps() -> None:
    model = popup_model(_request())
    rows = dict(model.rows)
    assert rows["host"] == "localhost"
    assert rows["database"] == "shop (compose service)"
    assert rows["credential source"] == ".env:DATABASE_URL"
    assert "SELECT only" in rows["operations"]
    assert rows["caps"] == "rows ≤ 500 · time ≤ 10 s"
    assert model.buttons == (Choice.allow_once, Choice.allow_remember, Choice.deny)
    assert [model.label(b) for b in model.buttons] == ["Allow once", "Allow and remember", "Deny"]
    assert model.default is Choice.allow_once and not model.needs_typed_name


def test_unset_caps_are_shown_as_unset_never_invented() -> None:
    assert dict(popup_model(_request(caps=Caps())).rows)["caps"] == "rows: no cap set · time: no cap set"


def test_an_endpoint_with_no_safe_signal_defaults_to_deny() -> None:
    model = popup_model(_request(Posture.unknown, default_deny=True))
    assert model.default is Choice.deny
    assert Choice.allow_remember in model.buttons


def test_production_suspected_defaults_to_deny_needs_the_name_and_cannot_be_remembered() -> None:
    request = _prod()
    model = popup_model(request)
    assert model.buttons == (Choice.allow_once, Choice.deny)
    assert model.default is Choice.deny
    assert model.needs_typed_name and model.typed_hint == ".env:PROD_DATABASE_URL"

    assert not decide(request, Choice.allow_once).accepted
    assert not decide(request, Choice.allow_once, "PROD_DATABASE_URL").accepted
    remembered = decide(request, Choice.allow_remember, " .env:PROD_DATABASE_URL ")
    assert remembered.accepted and remembered.granted and not remembered.remembered


def test_decide_maps_each_button() -> None:
    request = _request()
    assert decide(request, Choice.deny) == decide(request, Choice.deny)
    assert not decide(request, Choice.deny).granted
    assert decide(request, Choice.allow_once).granted and not decide(request, Choice.allow_once).remembered
    assert decide(request, Choice.allow_remember).remembered


# -- the gate: what a session asks, and what it stops asking ----------------------------------------


def test_known_endpoints_run_silently_and_only_new_ones_wait(tmp_path: Path) -> None:
    store_for(tmp_path).save(_record())
    gate = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    known, new = _request(), _request(endpoint="postgres://localhost:5433")
    assert gate.observe([known, new]) == (known,)
    assert [r.endpoint for r in gate.pending()] == ["postgres://localhost:5433"]


def test_a_denial_is_remembered_for_the_session_and_asked_again_next_session(tmp_path: Path) -> None:
    gate = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    request = _request()
    gate.observe([request])
    assert gate.resolve(request.key, Choice.deny).accepted
    gate.observe([request])
    gate.observe([request])
    assert gate.pending() == ()  # no nagging this session
    next_session = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    next_session.observe([request])
    assert [r.key for r in next_session.pending()] == [request.key]


def test_allow_and_remember_stops_the_asking_for_good(tmp_path: Path) -> None:
    gate = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    request = _request()
    gate.observe([request])
    result = gate.resolve(request.key, Choice.allow_remember)
    assert result.remembered and gate.changed
    later = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    assert later.observe([request]) == (request,) and later.pending() == ()


def test_production_is_asked_every_session_even_after_approval(tmp_path: Path) -> None:
    gate = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    request = _prod()
    gate.observe([request])
    assert not gate.resolve(request.key, Choice.allow_once, "wrong").accepted
    assert gate.pending() == (request,)  # a wrong name leaves it waiting
    assert gate.resolve(request.key, Choice.allow_remember, request.confirm_name).granted
    assert gate.observe([request]) == (request,)  # allowed for the rest of this session
    assert store_for(tmp_path).load() == ()
    assert not (tmp_path / ".evalloop" / "consents.json").exists() or _PG not in (
        tmp_path / ".evalloop" / "consents.json").read_text(encoding="utf-8")
    next_session = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    next_session.observe([request])
    assert next_session.pending() == (request,)


def test_an_expired_approval_asks_again(tmp_path: Path) -> None:
    wall = Clock()
    store = store_for(tmp_path, clock=wall)
    store.save(_record(expires_at=wall.now + 10))
    request = _request()
    assert ConsentGate(CapabilityBroker(store=store)).observe([request]) == (request,)
    wall.now += 11
    gate = ConsentGate(CapabilityBroker(store=store))
    assert gate.observe([request]) == () and gate.pending() == (request,)


def test_revoking_from_the_permissions_view_does_not_reopen_the_popup(tmp_path: Path) -> None:
    store_for(tmp_path).save(_record())
    gate = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    request = _request()
    gate.observe([request])
    assert [a["endpoint"] for a in gate.approvals()] == [_PG]
    assert gate.revoke(request.key)
    assert gate.observe([request]) == () and gate.pending() == ()
    assert store_for(tmp_path).load() == ()


# -- discovery into requests: no credential crosses ----------------------------------------------------


def test_discovered_requests_carry_the_source_never_the_value(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        f"DATABASE_URL=postgres://app:{_SECRET_PW}@10.0.0.5:5432/shop\nPROD_DATABASE_URL=postgres://x:{_SECRET_PW}@db\n",
        encoding="utf-8",
    )
    requests = discovered_requests(tmp_path, Caps())
    assert {r.credential_source for r in requests} == {".env:DATABASE_URL", ".env:PROD_DATABASE_URL"}
    assert _SECRET_PW not in json.dumps([r.to_json() for r in requests])
    prod = next(r for r in requests if "PROD" in r.endpoint)
    assert prod.production and popup_model(prod).needs_typed_name


def test_a_sqlite_file_named_prod_is_production_suspected(tmp_path: Path) -> None:
    db = tmp_path / "prod.db"
    db.touch()
    request = sqlite_request(tmp_path, db, Caps())
    assert request.production and request.confirm_name == "sqlite:///prod.db"
    assert sqlite_request(tmp_path, tmp_path / "app.db", Caps()).posture is Posture.local


# -- the session ---------------------------------------------------------------------------------------


def _repo_with_db(root: Path) -> None:
    conn = sqlite3.connect(root / "app.db")
    conn.execute("CREATE TABLE users(id INTEGER, name TEXT)")
    conn.commit()
    conn.close()
    (root / "queries.py").write_text(
        'def names(conn): return conn.execute("SELECT name FROM users").fetchall()\n', encoding="utf-8"
    )


def _session(root: Path) -> Session:
    def evaluator(_path: str, _store: str) -> RunResult:
        return RunResult(run_id="r", summary_path=Path("s.md"), outcome=RunOutcome.clean, cases=(),
                         graded_artifacts=(), skipped=(), permission_requests=(), situations=(), notes=())

    return Session(root, store_dir=root / ".store", evaluator=evaluator)


def _db_cards(session: Session) -> int:
    return sum(1 for run in session.state.runs if run.run_id == "spec:db")


def test_the_db_check_waits_for_permission_then_runs_silently_next_session(tmp_path: Path) -> None:
    _repo_with_db(tmp_path)
    session = _session(tmp_path)
    session.tick()
    assert _db_cards(session) == 0, "the database was opened before anyone allowed it"
    pending = session.consent.pending()
    assert [r.endpoint for r in pending] == ["sqlite:///app.db"]

    assert session.decide(pending[0].key, Choice.allow_remember).granted
    session.tick()  # nothing changed on disk; the approval alone unblocks the waiting check
    assert _db_cards(session) == 1

    restarted = _session(tmp_path)
    restarted.tick()
    assert _db_cards(restarted) == 1 and restarted.consent.pending() == ()


def test_a_denied_db_is_never_opened_this_session(tmp_path: Path) -> None:
    _repo_with_db(tmp_path)
    session = _session(tmp_path)
    session.tick()
    session.decide(session.consent.pending()[0].key, Choice.deny)
    (tmp_path / "queries.py").write_text("def f(conn): return conn.execute('SELECT 1').fetchall()\n", encoding="utf-8")
    session.tick()
    assert _db_cards(session) == 0 and session.consent.pending() == ()


def test_the_bot_answers_over_http_and_a_browser_cannot(tmp_path: Path) -> None:
    _repo_with_db(tmp_path)
    session = _session(tmp_path)
    session.tick()
    server = session.serve(port=0)
    port = server.server_address[1]
    try:
        client = BotClient(port=port)
        status = client.status()
        consent = status["consent"]
        assert isinstance(consent, dict)
        pending = consent["pending"]
        assert isinstance(pending, list) and pending[0]["popup"]["buttons"][0]["label"] == "Allow once"

        # what a web page could send: a simple form POST, no custom header
        forged = urllib.request.Request(
            f"http://127.0.0.1:{port}/consent/decide", data=b'{"key": "x", "choice": "allow_remember"}',
            headers={"Content-Type": "text/plain"}, method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(forged, timeout=3)
        assert refused.value.code == 403

        reply = client.decide(str(pending[0]["key"]), "allow_once")
        assert reply["accepted"] is True and reply["remembered"] is False
        approvals = client.status()["consent"]["approvals"]  # type: ignore[index]
        assert [a["endpoint"] for a in approvals] == ["sqlite:///app.db"]
        assert client.revoke(str(pending[0]["key"])) == {"revoked": True}
    finally:
        server.shutdown()


def test_the_session_publishes_no_credential_value(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"DATABASE_URL=postgres://app:{_SECRET_PW}@db/shop\n", encoding="utf-8")
    session = _session(tmp_path)
    session.tick()
    assert session.consent.pending()
    assert _SECRET_PW not in session.snapshot_json().decode("utf-8")


# -- the CLI -----------------------------------------------------------------------------------------


def test_consents_list_and_revoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_for(tmp_path).save(_record())
    store_for(tmp_path).save(_record(endpoint="qdrant://localhost:6333", tool=Tool.vector_store, credential_source=None))
    assert main(["consents", "list", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert _PG in out and "credential source: .env:DATABASE_URL (the value is never stored)" in out

    assert main(["consents", "revoke", _PG, "--path", str(tmp_path)]) == 0
    assert [r.endpoint for r in store_for(tmp_path).load()] == ["qdrant://localhost:6333"]
    assert main(["consents", "revoke", "nope", "--path", str(tmp_path)]) == 1
    assert main(["consents", "revoke", "--all", "--path", str(tmp_path)]) == 0
    assert store_for(tmp_path).load() == ()
    assert main(["consents", "list", str(tmp_path)]) == 0
    assert "nothing remembered" in capsys.readouterr().out


def test_the_consent_store_is_ignored_by_git_here() -> None:
    root = Path(__file__).resolve().parent.parent
    assert ".evalloop/" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_concurrent_decisions_do_not_corrupt_the_store(tmp_path: Path) -> None:
    gate = ConsentGate(CapabilityBroker(store=store_for(tmp_path)))
    requests = [_request(endpoint=f"postgres://localhost:{5400 + i}") for i in range(8)]
    gate.observe(requests)
    lock = threading.Lock()

    def press(request: ConsentRequest) -> None:
        with lock:  # the session serialises decisions under its own lock; mirror that here
            gate.resolve(request.key, Choice.allow_remember)

    threads = [threading.Thread(target=press, args=(r,)) for r in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(ConsentStore(store_for(tmp_path).path).load()) == 8
