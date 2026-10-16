"""End-state verification: the verdict comes from the real state, never from the agent's claim.

The load-bearing proofs: a false "done" is caught because the verdict reads rows/files, not the
transcript; the verdict is identical whether the agent claims done or not; writes land on a restored
snapshot while the live DB is untouched and the audit shows only reads; and the resettable-environment
precondition gates the whole thing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from evalloop.connect.envelope import AuditLog, ReadOnlyEnvelope
from evalloop.grade.end_state import (
    RECORD_ID,
    RESETTABLE_FACT,
    AgentClaim,
    FileAbsent,
    FileExists,
    NoRows,
    RowsEqual,
    restore_snapshot,
    verify_end_state,
)
from evalloop.grade.sql_execution import Snapshot, build_snapshot
from evalloop.memory.case import FailureClass, Verdict

_RESETTABLE = {RESETTABLE_FACT: True}

_SETUP = """
CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT);
INSERT INTO orders VALUES (1, 'open');
INSERT INTO orders VALUES (2, 'open');
"""


@pytest.fixture
def snapshot(tmp_path: Path) -> Snapshot:
    return build_snapshot(tmp_path / "state.db", _SETUP)


# -- the verdict is the real state, not the claim -------------------------------------


def test_a_false_done_is_caught(snapshot: Snapshot) -> None:
    # The agent claims it shipped every order, but the state still has two open ones.
    claim = AgentClaim(done=True, message="all orders shipped, tests pass")
    grade = verify_end_state(
        [RowsEqual("no_open_orders", "SELECT id FROM orders WHERE status = 'open'", expected=[])],
        db=snapshot,
        claim=claim,
        session_facts=_RESETTABLE,
    )
    assert grade.verdict is Verdict.failed
    assert grade.failure_class is FailureClass.wrong_result
    assert grade.claim_ignored is not None and "not used" in grade.claim_ignored


def test_the_claim_does_not_change_the_verdict(snapshot: Snapshot) -> None:
    check = [RowsEqual("two_open", "SELECT id FROM orders WHERE status = 'open'", expected=[(1,), (2,)])]
    claimed_done = verify_end_state(check, db=snapshot, claim=AgentClaim(True, "done"), session_facts=_RESETTABLE)
    claimed_not = verify_end_state(check, db=snapshot, claim=AgentClaim(False, "gave up"), session_facts=_RESETTABLE)
    # identical verdict: the transcript's self-report is never evidence
    assert claimed_done.verdict is Verdict.passed and claimed_not.verdict is Verdict.passed


def test_a_true_end_state_passes(snapshot: Snapshot) -> None:
    grade = verify_end_state(
        [RowsEqual("both_present", "SELECT id FROM orders ORDER BY id", expected=[(1,), (2,)], ordered=True)],
        db=snapshot,
        session_facts=_RESETTABLE,
    )
    assert grade.verdict is Verdict.passed and grade.record_id == RECORD_ID and grade.ladder_rung == 2


# -- file end state --------------------------------------------------------------------


def test_file_checks_read_disk_not_the_claim(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("result: 42\n", encoding="utf-8")
    grade = verify_end_state(
        [FileExists("made_output", "out.txt"), FileAbsent("no_tmp", "scratch.tmp")],
        root=tmp_path,
        claim=AgentClaim(True, "wrote everything"),
        session_facts=_RESETTABLE,
    )
    assert grade.verdict is Verdict.passed

    bad = verify_end_state([FileExists("made_report", "report.pdf")], root=tmp_path, session_facts=_RESETTABLE)
    assert bad.verdict is Verdict.failed


# -- writes go to a restored snapshot; the live DB is untouched; audit shows only reads -


def test_writes_land_on_the_restored_snapshot_and_audit_shows_only_reads(tmp_path: Path) -> None:
    live = tmp_path / "live.db"
    build_snapshot(live, _SETUP).close()
    original = sqlite3.connect(live).execute("SELECT count(*) FROM orders WHERE status='open'").fetchone()[0]

    # Restore a scratch copy and let "the agent" mutate THAT, never the live DB.
    scratch = restore_snapshot(live, tmp_path / "scratch.db")
    writer = sqlite3.connect(scratch)
    writer.execute("UPDATE orders SET status = 'shipped'")
    writer.commit()
    writer.close()

    # live DB is unchanged
    assert sqlite3.connect(live).execute("SELECT count(*) FROM orders WHERE status='open'").fetchone()[0] == original == 2

    # verify the end state on the scratch copy, read-only, with an audit we can inspect
    audit = AuditLog()
    snap = Snapshot(scratch, envelope=ReadOnlyEnvelope(audit))
    grade = verify_end_state(
        [NoRows("nothing_open", "SELECT id FROM orders WHERE status = 'open'")],
        db=snap,
        session_facts=_RESETTABLE,
    )
    assert grade.verdict is Verdict.passed
    # the verifier only read: every audited statement is a read, none a write/DDL
    kinds = {k for entry in audit.entries() for k in entry.statement_kinds}
    assert kinds <= {"read"}, f"the verifier issued a non-read statement: {kinds}"


# -- the resettable-environment precondition gates it ----------------------------------


def test_without_a_resettable_environment_it_is_inconclusive(snapshot: Snapshot) -> None:
    grade = verify_end_state(
        [RowsEqual("x", "SELECT id FROM orders", expected=[(1,), (2,)])],
        db=snapshot,
        session_facts={},  # environment_resets_per_run absent
    )
    assert grade.verdict is Verdict.inconclusive
    assert grade.pending_reason is not None and RESETTABLE_FACT in grade.pending_reason


def test_resettable_can_be_waived_explicitly(snapshot: Snapshot) -> None:
    grade = verify_end_state(
        [RowsEqual("x", "SELECT id FROM orders", expected=[(1,), (2,)])],
        db=snapshot,
        session_facts={},
        require_resettable=False,
    )
    assert grade.verdict is Verdict.passed
