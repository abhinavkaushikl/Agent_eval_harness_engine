"""The autonomous "what data systems is this repo talking to?" pass, as one call.

This binds the Track V pieces that are already built into a single, runnable surface:

* :func:`scan` runs EL-303 discovery and EL-304 classification together, so one command can say
  which databases and vector stores a repository talks to and how much each should be feared --
  **without opening any of them**. Discovery never learns a secret's value or a live host (the
  redactor keeps those off the bus), so ``scan`` reports what each candidate still *needs* before
  it can be opened; it does not connect.

* :func:`inspect_sqlite` is the one end-to-end read that needs no server and no credentials: a
  local SQLite file. It grants the capability on a fresh broker, then probes and describes the
  file through the EL-305 read-only envelope, proving the validated read-only path. Everything it
  does is a read, and the audit log is returned so a caller can check that.

Opening a remote Postgres/MySQL, a Qdrant store or an MCP server is deliberately *not* here: that
needs a live host plus credentials that this scan never sees, and an explicit consent grant. That
is a separate, consented step, not something a repository scan should do on its own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.classify_endpoint import Classification, Posture, classify
from evalloop.connect.discover import DATABASE, VECTOR_STORE, Candidate, discover
from evalloop.connect.envelope import AuditEntry, AuditLog, ReadOnlyEnvelope
from evalloop.connect.protocol import ProbeResult, Schema
from evalloop.connect.sqlite import SqliteConnector
from evalloop.vocab import Tool

__all__ = ["Finding", "ScanReport", "SqliteInspection", "scan", "inspect_sqlite", "render_scan"]


@dataclass(frozen=True, slots=True)
class Finding:
    """One discovered endpoint, classified, with what it still needs before it can be opened."""

    candidate: Candidate
    classification: Classification
    requirement: str


@dataclass(frozen=True, slots=True)
class ScanReport:
    """Everything a repository scan can say without opening anything."""

    root: str
    findings: tuple[Finding, ...]

    @property
    def databases(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.candidate.category == DATABASE)

    @property
    def vector_stores(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.candidate.category == VECTOR_STORE)


def _requirement(classification: Classification) -> str:
    """Plain language: what still stands between this candidate and a read, honestly."""
    needs: list[str] = ["a live host + credentials (never read from your repo)"]
    if classification.default_deny:
        needs.append("an explicit consent grant (default-deny)")
    if classification.require_typed_confirmation:
        needs.append(f"typing the exact name {classification.endpoint_name!r} to confirm")
    return "; ".join(needs)


def scan(root: str | os.PathLike[str]) -> ScanReport:
    """Discover every database / vector store a repo references and classify each one's risk."""
    findings = tuple(
        Finding(candidate=candidate, classification=(cl := classify(candidate)), requirement=_requirement(cl))
        for candidate in discover(root)
    )
    return ScanReport(root=str(root), findings=findings)


@dataclass(frozen=True, slots=True)
class SqliteInspection:
    """The result of opening a local SQLite file read-only: the proof it was reachable and read-only."""

    endpoint: str
    probe: ProbeResult
    schema: Schema
    audit: tuple[AuditEntry, ...]

    @property
    def read_only(self) -> bool:
        """True iff the file was reachable, reported read-only, and nothing but reads was audited."""
        kinds = {kind for entry in self.audit for kind in entry.statement_kinds}
        return self.probe.reachable and self.probe.read_only and kinds <= {"probe", "describe", "read"}


def inspect_sqlite(path: str | os.PathLike[str], *, endpoint: str | None = None) -> SqliteInspection:
    """Grant, probe and describe a local SQLite file through the broker + read-only envelope.

    The one Track V connector that needs neither a server nor a credential. A fresh broker grants
    read-only ``db_connection`` for exactly this endpoint, and the connector reads through the
    envelope, so every operation is auditable and no write can reach the file.
    """
    resolved = Path(path)
    endpoint_name = endpoint if endpoint is not None else f"sqlite:///{resolved.name}"
    broker = CapabilityBroker()
    broker.grant(
        Tool.db_connection,
        granted_by="evalloop connect",
        reason="local SQLite file, read-only inspection",
        endpoint=endpoint_name,
        caps=Caps(),
    )
    audit = AuditLog()
    connector = SqliteConnector(
        resolved,
        broker=broker,
        endpoint=endpoint_name,
        envelope=ReadOnlyEnvelope(audit),
        backend_read_only=True,
    )
    try:
        probe = connector.probe()
        schema = connector.describe()
    finally:
        connector.close()
    return SqliteInspection(endpoint=endpoint_name, probe=probe, schema=schema, audit=audit.entries())


def render_scan(report: ScanReport) -> str:
    """A deterministic, readable summary of a scan -- what was found and what each one needs."""
    lines = [f"EvalLoop connect: {report.root}"]
    if not report.findings:
        lines.append("  no databases or vector stores referenced in this repository")
        return "\n".join(lines) + "\n"
    for label, group in (("databases", report.databases), ("vector stores", report.vector_stores)):
        if not group:
            continue
        lines.append(f"  {label} ({len(group)}):")
        for finding in group:
            candidate = finding.candidate
            cl = finding.classification
            lines.append(f"    - {candidate.detail}")
            lines.append(f"        found at {candidate.provenance} ({candidate.provenance.reason})")
            lines.append(f"        posture: {cl.posture.value} -- {cl.rationale}")
            lines.append(f"        to open: {finding.requirement}")
    return "\n".join(lines) + "\n"
