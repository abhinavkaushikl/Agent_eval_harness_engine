"""The episodic store: every decision with its reasoning, read back unchanged, days later.

The round trips run the **real planner** on the live planner fixtures, so the
store is tested against the plans M0 actually produces -- D1 in two states,
companions that are pending, tools that are missing -- not against plans built
to suit it. Concurrency, schema versions and the pinned SQLite behaviour are
tested on real files in ``tmp_path``, because an in-memory database has
neither a lock to contend for nor a file to reopen.

Confidences of 1.0 below are test inputs, not thresholds: a label needs some
number in [0, 1], and the store's job is to return whichever one it was given.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from evalloop.memory import episodic
from evalloop.memory.episodic import (
    SCHEMA_VERSION,
    EpisodicStore,
    EpisodicStoreBusy,
    EpisodicStoreError,
    Label,
    PlanEntry,
    PlanSnapshot,
    PlanState,
    Trigger,
    Verdict,
)
from evalloop.plan.planner import Plan, plan
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.registry.schema import TechniqueRecord
from evalloop.vocab import Situation, Tool
from tests.planner_fixture import PlannerFixture, load_fixture
from tests.test_planner_fixtures import LIVE_PATHS

RECORDS: tuple[TechniqueRecord, ...] = load_records(RECORDS_DIR)
KNOWN_IDS = frozenset(record.id for record in RECORDS)


def _fixture(number: str) -> PlannerFixture:
    (path,) = [path for path in LIVE_PATHS if path.name.startswith(f"{number}_")]
    return load_fixture(path, KNOWN_IDS)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "episodes.sqlite3"


@pytest.fixture
def store(path: Path) -> Iterator[EpisodicStore]:
    with EpisodicStore.open(path) as opened:
        yield opened


def _classify(store: EpisodicStore, episode: str, situations: Sequence[Situation]) -> None:
    store.record_classification(
        episode, [Label(s, 1.0, f"the artifact reads as {s.value}") for s in situations]
    )


def _episode(store: EpisodicStore, episode: str = "e1", artifact: str = "src/pricing.py") -> None:
    if "s1" not in store.sessions():
        store.open_session("s1")
    store.open_episode(episode, session_id="s1", artifacts=[artifact])


def _planned(store: EpisodicStore, fixture: PlannerFixture, episode: str = "e1") -> Plan:
    """Classify as the fixture's situations, plan with the real planner, record the plan."""
    _episode(store, episode)
    _classify(store, episode, fixture.situations)
    produced = plan(RECORDS, fixture.situations, fixture.available_tools, fixture.evidence)
    store.record_plan(episode, produced, situations=fixture.situations, records=RECORDS)
    return produced


def _raw(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=0.0, isolation_level=None)


# -- the schema version lives in the file ------------------------------------------


def test_a_new_store_records_its_schema_version_in_the_file(path: Path) -> None:
    EpisodicStore.open(path).close()
    raw = _raw(path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
    finally:
        raw.close()
    assert SCHEMA_VERSION == 1


def test_a_file_from_a_newer_evalloop_is_refused(path: Path) -> None:
    EpisodicStore.open(path).close()
    raw = _raw(path)
    raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    raw.close()
    with pytest.raises(EpisodicStoreError, match="newer EvalLoop"):
        EpisodicStore.open(path)


def test_a_database_that_is_not_a_store_is_refused_and_left_alone(path: Path) -> None:
    raw = _raw(path)
    raw.execute("CREATE TABLE someone_elses (x)")
    raw.close()
    with pytest.raises(EpisodicStoreError, match="not an episodic store"):
        EpisodicStore.open(path)
    raw = _raw(path)
    try:
        tables = [name for (name,) in raw.execute("SELECT name FROM sqlite_master ORDER BY name")]
        assert tables == ["someone_elses"]
        assert raw.execute("PRAGMA user_version").fetchone() == (0,)
    finally:
        raw.close()


def test_the_migration_path_upgrades_an_existing_file(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stated migration path before there is anything to migrate: a second step, applied to a v1 file."""
    with EpisodicStore.open(path) as store:
        store.open_session("s1")
    second = ("CREATE TABLE note (episode_id TEXT NOT NULL REFERENCES episode (episode_id))",)
    monkeypatch.setattr(episodic, "_MIGRATIONS", (*episodic._MIGRATIONS, second))
    with EpisodicStore.open(path) as store:
        assert store.sessions() == ("s1",)
    raw = _raw(path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone() == (2,)
        assert raw.execute("SELECT count(*) FROM sqlite_master WHERE name = 'note'").fetchone() == (1,)
    finally:
        raw.close()


def test_a_failed_migration_leaves_the_file_at_its_old_version(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with EpisodicStore.open(path) as store:
        store.open_session("s1")
    monkeypatch.setattr(episodic, "_MIGRATIONS", (*episodic._MIGRATIONS, ("CREATE TABLE broken (",)))
    with pytest.raises(sqlite3.OperationalError):
        EpisodicStore.open(path)
    monkeypatch.undo()
    with EpisodicStore.open(path) as store:
        assert store.sessions() == ("s1",)
    raw = _raw(path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone() == (1,)
    finally:
        raw.close()


def test_the_pinned_settings_hold(store: EpisodicStore) -> None:
    """SQLite's foreign keys are off by default; the store turns them on and keeps them on.

    The busy timeout is read from SQLite rather than timed: Python's default
    is five seconds, after which a second writer *also* fails, so only the
    setting itself shows that "at once" means at once.
    """
    connection = store._connection
    assert connection.execute("PRAGMA busy_timeout").fetchone() == (0,)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert connection.execute("PRAGMA synchronous").fetchone() == (2,)  # FULL
    assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    assert connection.isolation_level is None


# -- every decision carries its reasoning ----------------------------------------------


def test_classification_is_one_row_per_situation_with_its_confidence(store: EpisodicStore) -> None:
    _episode(store)
    labels = [
        Label(Situation.api_endpoint, 0.75, "a route decorator on the function"),
        Label(Situation.sql_generation, 0.5, "it builds a SELECT string"),
    ]
    store.record_classification("e1", labels)
    assert store.classification("e1").labels == tuple(labels)
    assert store.classification("e1").abstention is None
    rows = store._connection.execute("SELECT situation FROM classification ORDER BY position").fetchall()
    assert rows == [("api_endpoint",), ("sql_generation",)]


def test_an_abstention_is_a_decision_with_its_reason(store: EpisodicStore) -> None:
    _episode(store)
    store.record_classification("e1", [], abstention="the file does not parse: it is mid-edit")
    assert store.classification("e1").labels == ()
    assert store.classification("e1").abstention == "the file does not parse: it is mid-edit"


@pytest.mark.parametrize(
    ("labels", "abstention", "match"),
    [
        ([], None, "say why nothing could be classified"),
        ([], "   ", "blank"),
        ([Label(Situation.code_generation, 1.0, "\n\t ")], None, "blank"),
        ([Label(Situation.code_generation, 1.0, "a def")], "and also abstained", "did not abstain"),
        (
            [Label(Situation.code_generation, 1.0, "a"), Label(Situation.code_generation, 0.5, "b")],
            None,
            "repeat",
        ),
    ],
)
def test_a_classification_without_reasoning_is_refused(
    store: EpisodicStore, labels: list[Label], abstention: str | None, match: str
) -> None:
    _episode(store)
    with pytest.raises(ValueError, match=match):
        store.record_classification("e1", labels, abstention=abstention)


@pytest.mark.parametrize("confidence", [True, float("nan"), float("inf"), 1.5, -0.1, "0.9"])
def test_a_confidence_outside_zero_to_one_is_refused(store: EpisodicStore, confidence: object) -> None:
    _episode(store)
    label = Label(Situation.code_generation, confidence, "a def")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="confidence"):
        store.record_classification("e1", [label])


def test_each_decision_is_recorded_once(store: EpisodicStore) -> None:
    """Append-only: nothing rewrites a decision that has been recorded."""
    fixture = _fixture("01")
    _planned(store, fixture)
    with pytest.raises(EpisodicStoreError, match="already classified"):
        _classify(store, "e1", fixture.situations)
    produced = plan(RECORDS, fixture.situations, fixture.available_tools, fixture.evidence)
    with pytest.raises(EpisodicStoreError, match="already has a plan"):
        store.record_plan("e1", produced, situations=fixture.situations, records=RECORDS)
    store.record_verdict("e1", artifact="src/pricing.py", record_id="A1_execution_based", verdict="fail", reasoning="3 of 12 hidden tests failed")
    with pytest.raises(EpisodicStoreError, match="already has a verdict"):
        store.record_verdict("e1", artifact="src/pricing.py", record_id="A1_execution_based", verdict="pass", reasoning="again")


# -- the plan, as the planner produced it -------------------------------------------------


@pytest.mark.parametrize("fixture_path", LIVE_PATHS, ids=lambda p: p.stem)
def test_every_live_fixture_plan_reads_back_unchanged(path: Path, fixture_path: Path) -> None:
    """All five states, keyed by record id, written, closed, reopened, read back -- for all 17 plans."""
    fixture = load_fixture(fixture_path, KNOWN_IDS)
    with EpisodicStore.open(path) as store:
        produced = _planned(store, fixture)
    with EpisodicStore.open(path) as store:
        assert store.plan_snapshot("e1") == PlanSnapshot.of(produced, fixture.situations)
        assert store.rendered_plan("e1") == produced.render()


def test_why_a1_execution_based_was_chosen(store: EpisodicStore) -> None:
    """The ticket's question: the state, what selected it, and why that situation was believed."""
    _planned(store, _fixture("01"))
    why = store.why("e1", "A1_execution_based")
    assert why.entries == (PlanEntry("A1_execution_based", PlanState.ready, "triggered by code_generation"),)
    assert why.triggers == (Trigger(Situation.code_generation, 1.0, "the artifact reads as code_generation"),)
    assert why.hosts == ()


def test_why_a_companion_was_chosen(store: EpisodicStore) -> None:
    """C1 is ready in fixture 1 only because A1 names it: no situation selected it."""
    _planned(store, _fixture("01"))
    why = store.why("e1", "C1_wilson_ci")
    assert why.entries == (PlanEntry("C1_wilson_ci", PlanState.ready, "companion of A1_execution_based"),)
    assert why.triggers == ()
    assert why.hosts == ("A1_execution_based",)


def test_why_is_one_sql_statement(store: EpisodicStore) -> None:
    """If answering "why" took three queries, the schema would be wrong."""
    _planned(store, _fixture("08"))
    statements: list[str] = []
    store._connection.set_trace_callback(statements.append)
    try:
        why = store.why("e1", "E1_per_item_diff")
    finally:
        store._connection.set_trace_callback(None)
    assert len(statements) == 1
    assert why.entries == (PlanEntry("E1_per_item_diff", PlanState.pending, "needs runs: 2, have 0"),)
    assert why.hosts == ("B1_paired_evaluation",)


def test_why_pending_carries_the_planners_reason_verbatim(store: EpisodicStore) -> None:
    _planned(store, _fixture("08"))
    why = store.why("e1", "B3_mcnemar")
    assert why.entries == (PlanEntry("B3_mcnemar", PlanState.pending, "needs discordant_pairs: 25, have 8"),)
    assert [trigger.situation for trigger in why.triggers] == [Situation.two_candidates]


def test_why_unavailable_names_the_missing_tool(store: EpisodicStore) -> None:
    _planned(store, _fixture("02"))
    why = store.why("e1", "A1_execution_based")
    assert why.entries == (PlanEntry("A1_execution_based", PlanState.unavailable, "missing: sandbox"),)
    assert store.plan_snapshot("e1").unavailable == (("A1_execution_based", (Tool.sandbox,)),)


def test_a_record_in_two_states_has_two_entries(store: EpisodicStore) -> None:
    """Fixture 12: D1 is ready (the PR curve) and prohibited (never accuracy) at once."""
    produced = _planned(store, _fixture("12"))
    why = store.why("e1", "D1_pr_curve_never_accuracy")
    assert [entry.state for entry in why.entries] == [PlanState.ready, PlanState.prohibited]
    assert why.entries[0].reasoning == "triggered by rare_class"
    assert why.entries[1].reasoning == produced.prohibition_reasons["D1_pr_curve_never_accuracy"]
    assert "D1_pr_curve_never_accuracy  READY  triggered by rare_class" in why.render()


def test_a_record_not_in_the_plan_says_so(store: EpisodicStore) -> None:
    _planned(store, _fixture("01"))
    why = store.why("e1", "A4_judge_binary_criteria")
    assert why.entries == () and why.triggers == () and why.hosts == ()
    assert why.render() == "A4_judge_binary_criteria: not in the plan for episode e1"


def test_a_record_replaced_by_a_conflict_leaves_no_trace(store: EpisodicStore) -> None:
    """Fixture 13: B6 matched and was replaced by B7, and the plan does not say so.

    This asserts what happens, and it is a gap rather than a feature:
    ``rules.apply_conflicts`` returns ``suppressed`` ("replaced by
    B7_cluster_bootstrap"), and ``plan()`` keeps only the survivors, so the
    reason never reaches the store. Raised as a ruling in the EL-202 report.
    """
    _planned(store, _fixture("13"))
    assert store.why("e1", "B6_bootstrap_ci").entries == ()
    assert store.plan_snapshot("e1").ready == ("B7_cluster_bootstrap",)


def test_a_situation_that_reaches_no_record_is_recorded_as_an_empty_plan(store: EpisodicStore) -> None:
    """``classification`` is one of the six situations that reach no record: the dead end stays visible."""
    _episode(store)
    _classify(store, "e1", [Situation.classification])
    produced = plan(RECORDS, [Situation.classification], [], {})
    store.record_plan("e1", produced, situations=[Situation.classification], records=RECORDS)
    snapshot = store.plan_snapshot("e1")
    assert snapshot.situations == (Situation.classification,)
    assert (snapshot.ready, snapshot.pending, snapshot.unavailable, snapshot.prohibited) == ((), (), (), ())
    assert snapshot.rendered.count("(none)") == 4


def test_a_plan_needs_a_classification_first(store: EpisodicStore) -> None:
    _episode(store)
    produced = plan(RECORDS, [Situation.code_generation], [], {})
    with pytest.raises(EpisodicStoreError, match="no classification"):
        store.record_plan("e1", produced, situations=[Situation.code_generation], records=RECORDS)


def test_a_plan_may_only_use_classified_situations(store: EpisodicStore) -> None:
    _episode(store)
    _classify(store, "e1", [Situation.code_generation])
    produced = plan(RECORDS, [Situation.rare_class], [], {})
    with pytest.raises(EpisodicStoreError, match="was not classified as"):
        store.record_plan("e1", produced, situations=[Situation.rare_class], records=RECORDS)


def test_a_plan_computed_from_other_situations_is_refused(store: EpisodicStore) -> None:
    """Recorded as code_generation, computed for rare_class: no entry has a basis, so it is refused."""
    _episode(store)
    _classify(store, "e1", [Situation.code_generation])
    produced = plan(RECORDS, [Situation.rare_class], [], {})
    with pytest.raises(EpisodicStoreError, match="not computed from these situations"):
        store.record_plan("e1", produced, situations=[Situation.code_generation], records=RECORDS)
    assert store._connection.execute("SELECT count(*) FROM plan").fetchone() == (0,)


def test_why_without_a_plan_is_an_error(store: EpisodicStore) -> None:
    _episode(store)
    with pytest.raises(EpisodicStoreError, match="no recorded plan"):
        store.why("e1", "A1_execution_based")


# -- verdicts ---------------------------------------------------------------------------


def test_a_verdict_reads_back_with_its_reasoning(store: EpisodicStore) -> None:
    _planned(store, _fixture("01"))
    store.record_verdict(
        "e1",
        artifact="src/pricing.py",
        record_id="A1_execution_based",
        verdict="fail",
        reasoning="checked the ₹999 threshold before bank-offer discounts; 3 of 12 hidden tests failed",
    )
    assert store.verdicts("e1") == (
        Verdict(
            "src/pricing.py",
            "A1_execution_based",
            "fail",
            "checked the ₹999 threshold before bank-offer discounts; 3 of 12 hidden tests failed",
        ),
    )


def test_the_verdict_vocabulary_is_not_decided_here(store: EpisodicStore) -> None:
    """EL-014 is open, so a timeout's verdict is stored as the grader words it, whichever way it goes."""
    _planned(store, _fixture("01"))
    store.record_verdict("e1", artifact="src/pricing.py", record_id="A1_execution_based", verdict="INCONCLUSIVE", reasoning="hit the 10-second cap")
    store.record_verdict("e1", artifact="src/pricing.py", record_id="C1_wilson_ci", verdict="timeout, counted as a failure", reasoning="hit the cap")
    assert [verdict.verdict for verdict in store.verdicts("e1")] == ["INCONCLUSIVE", "timeout, counted as a failure"]


def test_only_a_ready_technique_can_have_a_verdict(store: EpisodicStore) -> None:
    _planned(store, _fixture("02"))  # A1 is unavailable here
    with pytest.raises(EpisodicStoreError, match="not ready"):
        store.record_verdict("e1", artifact="src/pricing.py", record_id="A1_execution_based", verdict="pass", reasoning="ran")
    with pytest.raises(EpisodicStoreError, match="not ready"):
        store.record_verdict("e1", artifact="src/pricing.py", record_id="C3_repeat_runs", verdict="pass", reasoning="ran")


def test_a_verdict_is_on_one_of_the_episodes_artifacts(store: EpisodicStore) -> None:
    _planned(store, _fixture("01"))
    with pytest.raises(EpisodicStoreError, match="not an artifact"):
        store.record_verdict("e1", artifact="src/other.py", record_id="A1_execution_based", verdict="pass", reasoning="ran")


def test_a_verdict_needs_a_plan(store: EpisodicStore) -> None:
    _episode(store)
    _classify(store, "e1", [Situation.code_generation])
    with pytest.raises(EpisodicStoreError, match="no plan"):
        store.record_verdict("e1", artifact="src/pricing.py", record_id="A1_execution_based", verdict="pass", reasoning="ran")


# -- parameterised, verbatim, and the ids it accepts ----------------------------------------

AWKWARD = "it's \"quoted\"; DROP TABLE episode; --\nsecond line\twith a tab, ₹1,50,000, δ − 0.05 ≥ 0, and a NUL \x00 here"


def test_quotes_unicode_and_control_characters_round_trip_verbatim(path: Path) -> None:
    """Every write is parameterised: hostile text is stored, not executed, and comes back byte for byte."""
    with EpisodicStore.open(path) as store:
        store.open_session("s'1")
        store.open_episode("e'1; --", session_id="s'1", artifacts=["src/it's here/₹ pricing.py"])
        store.record_classification("e'1; --", [Label(Situation.code_generation, 0.5, AWKWARD)])
        produced = plan(RECORDS, [Situation.code_generation], [Tool.sandbox, Tool.test_runner], {})
        store.record_plan("e'1; --", produced, situations=[Situation.code_generation], records=RECORDS)
        store.record_verdict(
            "e'1; --", artifact="src/it's here/₹ pricing.py", record_id="A1_execution_based", verdict="fail", reasoning=AWKWARD
        )
    with EpisodicStore.open(path) as store:
        assert store.sessions() == ("s'1",)
        assert store.episodes("s'1")[0].artifacts == ("src/it's here/₹ pricing.py",)
        assert store.classification("e'1; --").labels[0].reasoning == AWKWARD
        assert store.verdicts("e'1; --")[0].reasoning == AWKWARD
        assert store.why("e'1; --", "A1_execution_based").triggers[0].reasoning == AWKWARD
        (tables,) = store._connection.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()
        assert tables == 12


def test_a_record_id_is_a_registry_id_so_it_cannot_hold_a_quote(store: EpisodicStore) -> None:
    """The ticket asked for a record id with a quote stored intact. The registry makes that impossible.

    ``RECORD_ID`` admits ``[A-J]``, digits, lowercase and underscores, so the
    store validates against it -- in full, so a trailing newline is refused
    too -- and an injection-shaped id is rejected before it reaches SQL.
    Parameterisation is proven on the free-text fields above.
    """
    _planned(store, _fixture("01"))
    for hostile in ("A1_execution_based'", "A1_x' OR '1'='1", "A1_execution_based\n"):
        with pytest.raises(ValueError, match="not a technique record id"):
            store.why("e1", hostile)
        with pytest.raises(ValueError, match="not a technique record id"):
            store.record_verdict("e1", artifact="src/pricing.py", record_id=hostile, verdict="pass", reasoning="ran")


# -- one writer, by design -------------------------------------------------------------------


def test_a_second_writer_fails_at_once(store: EpisodicStore, path: Path) -> None:
    other = _raw(path)
    other.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(EpisodicStoreBusy, match="one writer"):
            store.open_session("s1")
    finally:
        other.execute("ROLLBACK")
        other.close()
    store.open_session("s1")
    assert store.sessions() == ("s1",)


def test_a_commit_that_meets_a_reader_is_rolled_back(store: EpisodicStore, path: Path) -> None:
    """SQLite leaves the transaction open when COMMIT is refused; the store must close it."""
    store.open_session("s1")
    reader = _raw(path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM session").fetchone()
    try:
        with pytest.raises(EpisodicStoreBusy):
            store.open_session("s2")
        assert not store._connection.in_transaction
    finally:
        reader.execute("COMMIT")
        reader.close()
    assert store.sessions() == ("s1",)
    store.open_session("s2")
    assert store.sessions() == ("s1", "s2")


def test_opening_a_current_store_needs_no_write_lock(store: EpisodicStore, path: Path) -> None:
    """Only a migration takes the lock, so a reader can open while a writer is mid-transaction."""
    store.open_session("s1")
    writer = _raw(path)
    writer.execute("BEGIN IMMEDIATE")
    try:
        with EpisodicStore.open(path) as reader:
            assert reader.sessions() == ("s1",)
    finally:
        writer.execute("ROLLBACK")
        writer.close()


def test_two_stores_on_one_file_see_each_others_writes(store: EpisodicStore, path: Path) -> None:
    with EpisodicStore.open(path) as second:
        store.open_session("s1")
        assert second.sessions() == ("s1",)


def test_a_store_belongs_to_one_thread(store: EpisodicStore) -> None:
    errors: list[BaseException] = []

    def attempt() -> None:
        try:
            store.sessions()
        except BaseException as error:  # captured for the assertion below
            errors.append(error)

    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join()
    assert len(errors) == 1 and isinstance(errors[0], sqlite3.ProgrammingError)


# -- determinism and location ------------------------------------------------------------------


def _write_the_same_things(store: EpisodicStore) -> None:
    _planned(store, _fixture("08"))
    store.record_verdict("e1", artifact="src/pricing.py", record_id="B1_paired_evaluation", verdict="pass", reasoning="paired on 400 items")


def test_the_same_writes_give_the_same_dump(tmp_path: Path) -> None:
    dumps = []
    for name in ("a.sqlite3", "b.sqlite3"):
        with EpisodicStore.open(tmp_path / name) as store:
            _write_the_same_things(store)
            dumps.append(list(store._connection.iterdump()))
    assert dumps[0] == dumps[1]


def test_sessions_and_episodes_keep_their_order(store: EpisodicStore) -> None:
    for session in ("s-b", "s-a", "s-c"):
        store.open_session(session)
    for episode, artifacts in (("e2", ["z.py", "a.py"]), ("e1", ["m.py"])):
        store.open_episode(episode, session_id="s-a", artifacts=artifacts)
    assert store.sessions() == ("s-b", "s-a", "s-c")
    assert [(e.episode_id, e.artifacts) for e in store.episodes("s-a")] == [("e2", ("z.py", "a.py")), ("e1", ("m.py",))]


def test_the_location_is_the_callers_and_no_directory_is_created(tmp_path: Path) -> None:
    missing = tmp_path / "not-yet" / "episodes.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        EpisodicStore.open(missing)
    assert not missing.parent.exists()
    with EpisodicStore.open(str(tmp_path / "as-a-string.sqlite3")) as store:
        store.open_session("s1")
    with EpisodicStore.open(":memory:") as store:
        store.open_session("s1")
        assert store.sessions() == ("s1",)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda s: s.open_session(""), "session_id must be"),
        (lambda s: s.open_episode("e1", session_id="nope", artifacts=["a.py"]), "no session"),
        (lambda s: s.open_episode("e1", session_id="s1", artifacts=[]), "at least one artifact"),
        (lambda s: s.open_episode("e1", session_id="s1", artifacts="a.py"), "not one string"),
        (lambda s: s.open_episode("e1", session_id="s1", artifacts=["a.py", "a.py"]), "repeat"),
        (lambda s: s.record_classification("ghost", [Label(Situation.code_generation, 1.0, "x")]), "no episode"),
    ],
)
def test_bad_writes_are_refused(store: EpisodicStore, call: object, match: str) -> None:
    store.open_session("s1")
    assert callable(call)
    with pytest.raises((ValueError, EpisodicStoreError), match=match):
        call(store)


def test_a_duplicate_session_or_episode_is_refused(store: EpisodicStore) -> None:
    _episode(store)
    with pytest.raises(EpisodicStoreError, match="already exists"):
        store.open_session("s1")
    with pytest.raises(EpisodicStoreError, match="already exists"):
        store.open_episode("e1", session_id="s1", artifacts=["src/pricing.py"])
