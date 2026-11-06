"""The saved consent store: approvals that outlive a session, so the bot asks once and then stops asking.

Decision ``EL-018``. The capability broker (EL-302) keeps grants in memory, so before this every
session started with nothing approved and asked again. This module saves the approvals a developer
chose to *remember* as JSON in the project, at ``<repo>/.evalloop/consents.json``, and the broker
loads them when a session starts (:class:`~evalloop.capability.broker.CapabilityBroker`'s ``store``).

What a record holds, and what it never holds
--------------------------------------------
A :class:`ConsentRecord` holds the tool, the endpoint, who approved it and why, when, an optional
expiry, the caps and the credential **source** (``.env:DATABASE_URL``). It never holds a credential
**value**: :meth:`ConsentStore.save` refuses a credential source that the redactor would change (an
``sk-…`` key, a URL with a password in it), so a value cannot be saved even by mistake.

Production-suspected endpoints are never remembered
---------------------------------------------------
``ARCHITECTURE.md`` §9: production-suspected means default-deny and type-to-confirm. The operator's
decision (recorded in EL-018) is that such an approval lasts **one session at most**, so it asks
every session. :meth:`ConsentStore.save` refuses a production-suspected record outright, and
:meth:`ConsentStore.load` drops any that appear in the file (one edited in by hand, for instance).

Expiry, and the two clocks
--------------------------
Expiry is stored as a **wall-clock** epoch time (``time.time``), because it must mean the same thing
after a restart; the broker's own deadlines are monotonic and are converted on load. An expired
record is dropped on load and pruned from the file.

The file
--------
Written atomically (a temporary file, then ``os.replace``) with mode ``0600``. The ``.evalloop/``
directory gets its own ``.gitignore`` of ``*``, so the approvals are never committed in *any* repo
the bot watches, not only this one. A corrupt file is not silently overwritten: it loads as empty
(so everything is asked again, the fail-safe direction), :attr:`ConsentStore.problem` says why, and
the next save moves it aside to ``consents.json.corrupt`` first. Standard library only.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from evalloop.capability.broker import Caps, CapabilityError
from evalloop.connect.redact import redact_secrets
from evalloop.vocab import Tool

__all__ = ["CONSENT_DIR", "CONSENT_FILE", "ConsentRecord", "ConsentStore", "ConsentStoreError", "store_for"]

CONSENT_DIR = ".evalloop"
CONSENT_FILE = "consents.json"
_VERSION = 1
_PRODUCTION = "production_suspected"


class ConsentStoreError(CapabilityError):
    """A record the store refuses to save: production-suspected, or a credential value in disguise."""


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    """One remembered approval. ``expires_at`` and ``granted_at`` are wall-clock epoch seconds."""

    tool: Tool
    endpoint: str | None
    granted_by: str
    reason: str
    granted_at: float
    expires_at: float | None
    caps: Caps
    credential_source: str | None = None
    posture: str | None = None

    @property
    def key(self) -> tuple[Tool, str | None]:
        return (self.tool, self.endpoint)

    def to_json(self) -> dict[str, object]:
        return {
            "tool": self.tool.value,
            "endpoint": self.endpoint,
            "granted_by": self.granted_by,
            "reason": self.reason,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "caps": {
                "max_rows": self.caps.max_rows,
                "max_bytes": self.caps.max_bytes,
                "max_seconds": self.caps.max_seconds,
                "budget_usd": None if self.caps.budget_usd is None else str(self.caps.budget_usd),
            },
            "credential_source": self.credential_source,
            "posture": self.posture,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, object]) -> ConsentRecord:
        """Parse one record. Raises ``ValueError``/``TypeError``/``KeyError`` on anything malformed."""
        caps_raw = raw.get("caps") or {}
        if not isinstance(caps_raw, Mapping):
            raise TypeError("caps is not an object")
        budget = caps_raw.get("budget_usd")
        try:
            budget_usd = None if budget is None else Decimal(str(budget))
        except InvalidOperation as error:
            raise ValueError(f"budget_usd {budget!r} is not a number") from error
        caps = Caps(
            max_rows=_opt_int(caps_raw.get("max_rows")),
            max_bytes=_opt_int(caps_raw.get("max_bytes")),
            max_seconds=_opt_float(caps_raw.get("max_seconds")),
            budget_usd=budget_usd,
        )
        endpoint = raw.get("endpoint")
        source = raw.get("credential_source")
        posture = raw.get("posture")
        expires = raw.get("expires_at")
        return cls(
            tool=Tool(str(raw["tool"])),
            endpoint=None if endpoint is None else str(endpoint),
            granted_by=str(raw["granted_by"]),
            reason=str(raw["reason"]),
            granted_at=float(str(raw["granted_at"])),
            expires_at=None if expires is None else float(str(expires)),
            caps=caps,
            credential_source=None if source is None else str(source),
            posture=None if posture is None else str(posture),
        )


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{value!r} is not an int")
    return value


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{value!r} is not a number")
    return float(value)


def _refusal(record: ConsentRecord) -> str | None:
    if record.posture == _PRODUCTION:
        return (
            f"{record.endpoint!r} is production-suspected; its approval lasts this session only and is "
            "never remembered (EL-018)"
        )
    if record.credential_source is not None:
        redacted, count = redact_secrets(record.credential_source)
        if count:
            return (
                "the credential source looks like a credential value, which is never stored "
                f"(it would redact to {redacted!r}); record where the secret lives, not the secret"
            )
    return None


class ConsentStore:
    """Remembered approvals for one project, saved as JSON. Every read goes back to the file."""

    def __init__(self, path: str | os.PathLike[str], *, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self._clock = clock
        self.problem: str | None = None

    def now(self) -> float:
        return self._clock()

    # -- reading ------------------------------------------------------------------------

    def load(self) -> tuple[ConsentRecord, ...]:
        """Every live record, sorted. Drops (and prunes from the file) expired and refused records."""
        raw = self._read()
        if raw is None:
            return ()
        kept: list[ConsentRecord] = []
        dropped = False
        now = self._clock()
        for item in raw:
            try:
                record = ConsentRecord.from_json(item)
            except (KeyError, TypeError, ValueError, CapabilityError):
                dropped = True
                continue
            if record.expires_at is not None and record.expires_at <= now:
                dropped = True
                continue
            if _refusal(record) is not None:
                dropped = True
                continue
            kept.append(record)
        kept.sort(key=_order)
        if dropped:
            self._write(kept)
        return tuple(kept)

    def get(self, tool: Tool, endpoint: str | None) -> ConsentRecord | None:
        return next((r for r in self.load() if r.key == (tool, endpoint)), None)

    def _read(self) -> list[Mapping[str, object]] | None:
        self.problem = None
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            self.problem = f"could not read {self.path}: {error}"
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            self.problem = f"{self.path} is not valid JSON ({error}); every endpoint will be asked again"
            return None
        records = data.get("consents") if isinstance(data, dict) else None
        if not isinstance(records, list):
            self.problem = f"{self.path} has no 'consents' list; every endpoint will be asked again"
            return None
        return [r for r in records if isinstance(r, Mapping)]

    # -- writing ------------------------------------------------------------------------

    def save(self, record: ConsentRecord) -> None:
        """Add or replace the record for ``(tool, endpoint)``. Refuses production-suspected and values."""
        reason = _refusal(record)
        if reason is not None:
            raise ConsentStoreError(reason)
        records = [r for r in self.load() if r.key != record.key]
        records.append(record)
        records.sort(key=_order)
        self._write(records)

    def remove(self, tool: Tool, endpoint: str | None) -> bool:
        """Forget one approval. Returns whether there was one to forget."""
        records = list(self.load())
        kept = [r for r in records if r.key != (tool, endpoint)]
        if len(kept) == len(records):
            return False
        self._write(kept)
        return True

    def clear(self) -> int:
        """Forget every approval. Returns how many were forgotten."""
        records = self.load()
        if records:
            self._write([])
        return len(records)

    def _write(self, records: list[ConsentRecord]) -> None:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        ignore = directory / ".gitignore"
        if directory.name == CONSENT_DIR and not ignore.exists():
            ignore.write_text("# EvalLoop's local state: approvals are per-machine, never committed.\n*\n", encoding="utf-8")
        if self.problem is not None and self.path.exists():
            os.replace(self.path, self.path.with_name(self.path.name + ".corrupt"))
            self.problem = None
        payload = {"version": _VERSION, "consents": [r.to_json() for r in records]}
        fd, temp = tempfile.mkstemp(prefix=".consents-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.chmod(temp, 0o600)
            os.replace(temp, self.path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise


def _order(record: ConsentRecord) -> tuple[str, str]:
    return (record.tool.value, record.endpoint or "")


def store_for(root: str | os.PathLike[str], *, clock: Callable[[], float] = time.time) -> ConsentStore:
    """The store for the project at ``root``: ``<root>/.evalloop/consents.json``."""
    return ConsentStore(Path(root) / CONSENT_DIR / CONSENT_FILE, clock=clock)
