"""Endpoint posture classification: production-suspected is the fail-safe, and it costs a typed keystroke.

The classifier opens nothing — it reads a discovered ``Candidate`` and decides local / staging /
unknown / production-suspected. The load-bearing proofs: a prod-named host, a public IP, and a
secrets-manager credential each land in production-suspected with default-deny + type-to-confirm; a
localhost/RFC1918 endpoint is local with no typing; and when the signals conflict the result leans
toward production, never away from it.
"""

from __future__ import annotations

from evalloop.connect.classify_endpoint import Classification, Posture, classify
from evalloop.connect.discover import Candidate, Provenance
from evalloop.vocab import Tool

_PROV = Provenance(path=".env", line=1, reason="test fixture")


def _candidate(
    *,
    kind: str = "postgres",
    tool: Tool = Tool.db_connection,
    detail: str = "postgres",
    credential_source: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> Candidate:
    return Candidate(
        kind=kind,
        tool=tool,
        detail=detail,
        credential_source=credential_source,
        host=host,
        port=port,
        provenance=_PROV,
    )


# -- local: a private/loopback host, no type-to-confirm --------------------------------


def test_localhost_is_local_with_no_typing() -> None:
    c = classify(_candidate(host="localhost", detail="db"))
    assert c.posture is Posture.local
    assert c.require_typed_confirmation is False
    assert c.default_deny is False


def test_rfc1918_host_is_local() -> None:
    for private in ("10.0.0.5", "192.168.1.10", "172.16.0.3", "127.0.0.1"):
        c = classify(_candidate(host=private))
        assert c.posture is Posture.local, private
        assert c.require_typed_confirmation is False


# -- production-suspected: each trigger, with default-deny + type-to-confirm -----------


def test_prod_named_host_is_production_suspected() -> None:
    c = classify(_candidate(host="db.prod.example.com"))
    assert c.posture is Posture.production_suspected
    assert c.default_deny is True
    assert c.require_typed_confirmation is True
    assert "prod" in c.rationale


def test_public_ip_host_is_production_suspected() -> None:
    c = classify(_candidate(host="52.3.1.2"))
    assert c.posture is Posture.production_suspected
    assert c.default_deny is True
    assert c.require_typed_confirmation is True
    assert "RFC1918" in c.rationale or "public" in c.rationale


def test_secrets_manager_credential_is_production_suspected() -> None:
    for source in ("vault:secret/db", "aws-secretsmanager:prod/db", "op://vault/db", "gcp-secret:db"):
        c = classify(_candidate(credential_source=source, host="10.0.0.9"))
        assert c.posture is Posture.production_suspected, source
        assert c.require_typed_confirmation is True


def test_prod_token_in_credential_key_is_production_suspected() -> None:
    c = classify(_candidate(credential_source=".env:PROD_DATABASE_URL"))
    assert c.posture is Posture.production_suspected
    assert c.require_typed_confirmation is True


# -- staging: named non-prod, no type-to-confirm ---------------------------------------


def test_staging_named_host_is_staging() -> None:
    c = classify(_candidate(host="staging-db.internal", detail="db"))
    assert c.posture is Posture.staging
    assert c.require_typed_confirmation is False


# -- unknown: no signal, but still defaults to deny ------------------------------------


def test_no_signal_is_unknown_and_defaults_to_deny() -> None:
    c = classify(_candidate(credential_source=".env:DATABASE_URL", detail="db"))
    assert c.posture is Posture.unknown
    assert c.default_deny is True
    assert c.require_typed_confirmation is False


# -- the fail-safe direction -----------------------------------------------------------


def test_localhost_named_prod_leans_to_production_not_local() -> None:
    # A localhost service named prod_db is physically local, but the prod token wins: one keystroke
    # is cheaper than a false "local" that was really production.
    c = classify(_candidate(host="localhost", detail="prod_db"))
    assert c.posture is Posture.production_suspected


def test_secrets_manager_beats_a_private_host() -> None:
    c = classify(_candidate(credential_source="vault:db", host="192.168.0.5"))
    assert c.posture is Posture.production_suspected


# -- the typed confirmation actually gates ---------------------------------------------


def test_typed_confirmation_must_match_the_endpoint_name() -> None:
    c = classify(_candidate(host="db.prod.example.com"))
    assert c.endpoint_name == "db.prod.example.com"
    assert c.confirms("db.prod.example.com") is True
    assert c.confirms("  db.prod.example.com  ") is True  # trimmed
    assert c.confirms("something-else") is False
    assert c.confirms("") is False


def test_local_confirms_without_typing() -> None:
    c = classify(_candidate(host="localhost"))
    assert c.confirms("") is True
    assert c.confirms("anything") is True


# -- the rationale is plain language naming the heuristic ------------------------------


def test_every_classification_states_why() -> None:
    for c in (
        classify(_candidate(host="localhost")),
        classify(_candidate(host="db.prod.example.com")),
        classify(_candidate(host="52.3.1.2")),
        classify(_candidate(credential_source="vault:db")),
        classify(_candidate(host="staging-db")),
        classify(_candidate(credential_source=".env:DATABASE_URL")),
    ):
        assert isinstance(c, Classification)
        assert c.rationale and c.rationale[0].islower() or c.rationale  # non-empty, human text
        assert len(c.rationale.split()) >= 4


# -- determinism -----------------------------------------------------------------------


def test_classification_is_deterministic() -> None:
    cand = _candidate(host="db.prod.example.com")
    assert classify(cand) == classify(cand)
