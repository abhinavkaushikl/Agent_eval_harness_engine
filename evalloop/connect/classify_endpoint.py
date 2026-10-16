"""Decide an endpoint's posture — local / staging / unknown / production-suspected — and the consent it needs.

``ARCHITECTURE.md`` §6.1 / §9: "Connector points at production → production-suspected
classification, type-to-confirm, default deny." This module decides that posture from a discovered
:class:`~evalloop.connect.discover.Candidate`. It **opens nothing** — connecting and probing are
EL-305/EL-306; this ticket is posture only.

The heuristics, and the one rule that orders them
-------------------------------------------------
The fail-safe direction is toward **production-suspected**: a false "local" that was really
production is the catastrophe this gate exists to prevent, while a false "production-suspected"
costs one typed keystroke. So the production checks run first, and any one of them is enough:

1. **A secrets-manager credential** (the source is a vault / AWS-SM / GCP-SM / SSM / 1Password, not a
   plain ``.env``) → production-suspected. Dev data rarely lives behind a secrets manager.
2. **A ``prod`` / ``live`` / ``www`` token** in the host, the name, or the credential key →
   production-suspected (this fires even on ``localhost`` — a local ``prod_db`` is one keystroke, not
   a risk worth reclassifying away).
3. **A public (non-RFC1918) host IP** → production-suspected.

Only after those: a **private / loopback** host is ``local`` (no type-to-confirm); a
``staging``/``dev``/``test``/``uat`` token is ``staging``; anything with no signal is ``unknown`` —
which **also defaults to deny**, because "no idea" is not "safe."

A hostname that is not an IP literal is never assumed private — this module does **not** resolve
DNS (that is a network op), so a bare hostname with no token lands in ``unknown``, not ``local``.

The classification rides on consent
-----------------------------------
:class:`Classification` carries the posture, a plain-language ``rationale`` naming the heuristic that
fired, whether the consent default is **deny**, and whether granting **requires typing the endpoint
name**. The capability broker's consent request (EL-302) shows this, so the user sees *why* before
they grant. :meth:`Classification.confirms` checks a typed confirmation.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from evalloop._compat import StrEnum
from evalloop.connect.discover import Candidate

__all__ = ["Posture", "Classification", "classify"]

_PROD_TOKENS = ("prod", "live", "www")
_STAGING_TOKENS = ("staging", "stage", "uat", "qa", "sandbox", "dev", "test", "preview")
# Credential-source prefixes that mean a secrets manager rather than a local .env file.
_SECRETS_MANAGER = ("vault", "aws-secret", "awssecrets", "secretsmanager", "ssm:", "gcp-secret", "gcpsecret", "1password", "op://", "azure-keyvault", "keyvault")


class Posture(StrEnum):
    """How much to fear an endpoint, lowest to highest risk."""

    local = "local"
    staging = "staging"
    unknown = "unknown"
    production_suspected = "production_suspected"


@dataclass(frozen=True, slots=True)
class Classification:
    """An endpoint's posture and the consent it demands. Decided without opening anything."""

    posture: Posture
    rationale: str
    default_deny: bool
    require_typed_confirmation: bool
    endpoint_name: str

    def confirms(self, typed: str) -> bool:
        """Whether a typed confirmation lets the grant proceed. Production-suspected needs the exact name."""
        if not self.require_typed_confirmation:
            return True
        return typed.strip() == self.endpoint_name


def _host_is_public_ip(host: str | None) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False  # a hostname, not an IP literal; we do not resolve it
    return not (address.is_private or address.is_loopback or address.is_link_local)


def _host_is_private(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() in ("localhost", "localhost.localdomain"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _has_token(text: str, tokens: tuple[str, ...]) -> str | None:
    low = text.lower()
    for token in tokens:
        if token in low:
            return token
    return None


def _from_secrets_manager(credential_source: str | None) -> bool:
    if not credential_source:
        return False
    low = credential_source.lower()
    if low.startswith(".env") or ".env:" in low:
        return False
    return any(marker in low for marker in _SECRETS_MANAGER)


def classify(candidate: Candidate) -> Classification:
    """The posture of one discovered endpoint, and the consent it needs. Opens nothing."""
    host = candidate.host
    name_blob = " ".join(part for part in (host, candidate.detail, candidate.credential_source, candidate.kind) if part)
    endpoint_name = host or candidate.credential_source or candidate.detail

    # 1. secrets-manager credential → production-suspected
    if _from_secrets_manager(candidate.credential_source):
        return Classification(
            Posture.production_suspected,
            f"its credential comes from a secrets manager ({candidate.credential_source}), which is "
            "typically production, not a local .env",
            default_deny=True,
            require_typed_confirmation=True,
            endpoint_name=endpoint_name,
        )
    # 2. a prod/live/www token anywhere → production-suspected (fires even on localhost)
    token = _has_token(name_blob, _PROD_TOKENS)
    if token is not None:
        return Classification(
            Posture.production_suspected,
            f"its name contains {token!r}, which usually means production",
            default_deny=True,
            require_typed_confirmation=True,
            endpoint_name=endpoint_name,
        )
    # 3. a public (non-RFC1918) host IP → production-suspected
    if _host_is_public_ip(host):
        return Classification(
            Posture.production_suspected,
            f"the host {host!r} is a public (non-RFC1918) address, so it is not a local service",
            default_deny=True,
            require_typed_confirmation=True,
            endpoint_name=endpoint_name,
        )
    # 4. a private / loopback host → local
    if _host_is_private(host):
        return Classification(
            Posture.local,
            f"the host {host!r} is a private/loopback address",
            default_deny=False,
            require_typed_confirmation=False,
            endpoint_name=endpoint_name,
        )
    # 5. a staging/dev/test token → staging
    staging = _has_token(name_blob, _STAGING_TOKENS)
    if staging is not None:
        return Classification(
            Posture.staging,
            f"its name contains {staging!r}, which usually means a non-production environment",
            default_deny=False,
            require_typed_confirmation=False,
            endpoint_name=endpoint_name,
        )
    # 6. no signal → unknown, and "no idea" is not "safe"
    return Classification(
        Posture.unknown,
        "no host or name signal to place this endpoint, so it is treated with caution",
        default_deny=True,
        require_typed_confirmation=False,
        endpoint_name=endpoint_name,
    )
