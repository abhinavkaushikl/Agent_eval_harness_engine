"""The bot's chat: what a typed line means, the replies it builds, and the session switching folders.

Everything here runs without a window: the chat's decisions live in ``evalloop.session.chat``, and
the session's ``watch``/``pause`` are exercised directly and over HTTP the way the chat calls them.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from evalloop.__main__ import main
from evalloop.run import RunOutcome, RunResult
from evalloop.session.chat import Action, greeting, interpret, report_text, status_text
from evalloop.session.consent_popup import BotClient
from evalloop.session.orchestrator import Session


def _result(path: str, outcome: RunOutcome = RunOutcome.clean) -> RunResult:
    return RunResult(run_id=Path(path).name, summary_path=Path("s.md"), outcome=outcome, cases=(),
                     graded_artifacts=(), skipped=(), permission_requests=(), situations=(), notes=())


def _session(root: Path | None, seen: list[str]) -> Session:
    def evaluator(path: str, _store: str) -> RunResult:
        seen.append(path)
        return _result(path)

    return Session(root, store_dir=Path("/nonexistent-store"), evaluator=evaluator)


# -- what a line means --------------------------------------------------------------------------------


def test_a_bare_path_or_a_sentence_with_one_watches_it(tmp_path: Path) -> None:
    (tmp_path / "my app").mkdir()
    for said in (str(tmp_path), f"watch {tmp_path}", f"please watch my repo at {tmp_path}/",
                 f'watch "{tmp_path}/my app"', f"can you watch {tmp_path}/my\\ app"):
        command = interpret(said)
        assert command.action is Action.watch and command.error is None, said
        assert Path(command.path or "").is_dir()


def test_home_and_relative_paths_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "proj").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    assert interpret("~/proj").path == str((tmp_path / "proj").resolve())
    assert interpret("watch proj", cwd=tmp_path).path == str((tmp_path / "proj").resolve())
    assert interpret("./proj", cwd=tmp_path).path == str((tmp_path / "proj").resolve())


def test_a_missing_folder_or_a_file_says_so(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    missing = interpret(f"{tmp_path}/nope")
    assert missing.action is Action.watch and "can't find a folder" in (missing.error or "")
    a_file = interpret(str(tmp_path / "app.py"))
    assert "is a file" in (a_file.error or "")


def test_watch_this_repo_without_a_path_asks_for_it() -> None:
    command = interpret("watch my repo i am working on")
    assert command.action is Action.ask_path and "Copy Path" in (command.error or "")


@pytest.mark.parametrize(
    ("said", "action"),
    [("status", Action.status), ("What are you watching?", Action.status), ("report", Action.report),
     ("what did you find", Action.report), ("stop", Action.stop), ("Pause!", Action.stop),
     ("permissions", Action.permissions), ("help", Action.help), ("", Action.help)],
)
def test_the_commands(said: str, action: Action) -> None:
    assert interpret(said).action is action


def test_nonsense_gets_help_not_a_guess() -> None:
    command = interpret("banana")
    assert command.action is Action.help and command.error is not None


# -- the replies -----------------------------------------------------------------------------------------


def test_replies_before_anything_is_watched() -> None:
    assert "What do you want me to watch" in greeting({})
    assert "not watching anything" in status_text({"root": ""})
    assert "No findings yet" in report_text({})


def test_status_and_report_from_a_real_shape() -> None:
    data: dict[str, object] = {
        "root": "/w/shop", "watching": True, "mascot": "alarmed",
        "runs": [{"outcome": "problem", "trigger": ["calc.py"], "cases": [
            {"verdict": "passed", "artifact": "calc.py::mul", "name": "test_mul", "detail": ""},
            {"verdict": "failed", "artifact": "calc.py::add", "name": "test_add", "detail": "assert -1 == 5"},
        ]}],
        "consent": {"pending": [{"key": "k"}]},
    }
    status = status_text(data)
    assert "Watching /w/shop" in status and "PROBLEM on calc.py" in status and "1 permission" in status
    report = report_text(data)
    assert report.startswith("1 failing, 1 passing")
    assert report.index("test_add") < report.index("test_mul")  # failures first
    assert "assert -1 == 5" in report
    assert "I'm watching /w/shop" in greeting(data)


def test_paused_and_switching_are_reported() -> None:
    assert "Paused" in status_text({"root": "/w", "watching": False})
    assert "Switching to /x" in status_text({"root": "/w", "switching_to": "/x"})


# -- the session switches folders --------------------------------------------------------------------


def test_a_session_can_start_with_no_folder_and_be_told_one(tmp_path: Path) -> None:
    seen: list[str] = []
    session = _session(None, seen)
    assert session.tick() is None and seen == []
    resolved = session.watch(tmp_path)
    assert session.tick() is not None
    assert seen == [resolved] and session.state.root == resolved


def test_switching_starts_over_on_the_new_folder(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    seen: list[str] = []
    session = _session(first, seen)
    session.tick()
    assert len(session.state.runs) == 1
    session.watch(second)
    session.tick()
    assert seen[-1] == str(second.resolve())
    assert [r.run_id for r in session.state.runs] == ["b"]  # the old folder's history is gone


def test_a_check_in_flight_finishes_first_and_never_reaches_the_new_folder(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    started, release = threading.Event(), threading.Event()

    def evaluator(path: str, _store: str) -> RunResult:
        if Path(path).name == "a":  # the old folder's check is slow and finds a problem
            started.set()
            release.wait(5)
            return _result(path, RunOutcome.problem)
        return _result(path)

    session = Session(first, store_dir=tmp_path / "s", evaluator=evaluator)
    loop = threading.Thread(target=session.tick)  # the session loop, mid-check on folder a
    loop.start()
    assert started.wait(5)
    session.watch(second)  # the chat asks for b while a is still being checked
    assert session.state.root == str(first)  # nothing switches under a running check
    release.set()
    loop.join(5)
    session.tick()  # the loop's next tick switches
    assert session.state.root == str(second.resolve())
    assert [r.run_id for r in session.state.runs] == ["b"] and session.state.mascot != "alarmed"


def test_pause_stops_checking_until_told_again(tmp_path: Path) -> None:
    seen: list[str] = []
    session = _session(tmp_path, seen)
    session.tick()
    session.pause()
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert session.tick() is None and len(seen) == 1
    session.watch(tmp_path)
    session.tick()
    assert len(seen) == 2


def test_watch_refuses_a_missing_folder_or_a_file(tmp_path: Path) -> None:
    session = _session(None, [])
    with pytest.raises(ValueError, match="no folder"):
        session.watch(tmp_path / "nope")
    (tmp_path / "f.py").touch()
    with pytest.raises(ValueError, match="is a file"):
        session.watch(tmp_path / "f.py")
    with pytest.raises(ValueError, match="which folder"):
        session.watch("  ")


def test_the_chat_watches_and_pauses_over_http(tmp_path: Path) -> None:
    session = _session(None, [])
    server = session.serve(port=0)
    try:
        client = BotClient(port=server.server_address[1])
        assert client.watch(str(tmp_path / "nope"))["ok"] is False
        reply = client.watch(str(tmp_path))
        assert reply == {"ok": True, "root": str(tmp_path.resolve())}
        assert client.status()["switching_to"] == str(tmp_path.resolve())
        session.tick()
        assert client.status()["root"] == str(tmp_path.resolve())
        assert client.pause() == {"ok": True}
        assert client.status()["watching"] is False
    finally:
        server.shutdown()


def test_start_needs_a_folder_unless_the_bot_will_ask(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["start", "--once", "--no-serve"]) == 2
    assert "pass --bot" in capsys.readouterr().err


# -- the dancers ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "character", "dance"),
    [("mira", "mira", None), ("dance salsa", None, "salsa"), ("make luz do the moonwalk", "luz", "moonwalk"),
     ("Zuri twerk!", "zuri", "twerk"), ("bhartnatayam", None, "bharatanatyam"), ("do bharatnatyam", None, "bharatanatyam"),
     ("next dance", None, "+"), ("next character", "+", None)],
)
def test_naming_a_dancer_or_a_dance(said: str, character: str | None, dance: str | None) -> None:
    command = interpret(said)
    assert command.action is Action.avatar
    assert (command.character, command.dance) == (character, dance)


def test_a_dance_command_changes_the_desktop_pet_and_puts_it_on_stage() -> None:
    from evalloop.session import avatars
    from evalloop.session.chat import apply_avatar, avatar_reply, cast_text

    start = {**avatars.default_choice(), "stage": []}
    choice = apply_avatar(start, interpret("make luz do the moonwalk"))
    assert avatars.pet_of(choice)[:2] == ("luz", "moonwalk") and choice["stage"] == ["luz"]
    assert avatar_reply(choice) == "Luz is your desktop pet now, dancing Moonwalk."
    choice = apply_avatar(choice, interpret("dance bhartnatayam"))
    assert avatars.pet_of(choice)[:2] == ("luz", "bharatanatyam")
    assert interpret("characters").action is Action.cast and "Mira — signature: Bharatanatyam" in cast_text()


def test_dance_words_do_not_hijack_other_commands() -> None:
    assert interpret("stop").action is Action.stop
    assert interpret("report").action is Action.report
    assert interpret("banana").action is Action.help


def test_a_folder_with_nothing_to_check_is_looked_at_once_not_every_tick(tmp_path: Path) -> None:
    """Regression: a folder with no .py or eval-spec files snapshots empty, and every tick used to
    count as a first look, re-running the whole check every interval (245 runs in 8 minutes)."""
    (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    seen: list[str] = []
    session = _session(tmp_path, seen)
    for _ in range(5):
        session.tick()
    assert len(seen) == 1 and len(session.state.runs) == 1
    (tmp_path / "new.py").write_text("x = 1\n", encoding="utf-8")
    session.tick()
    assert len(seen) == 2  # a real change is still checked
    other = tmp_path / "other"
    other.mkdir()
    session.watch(other)
    session.tick()
    session.tick()
    assert len(seen) == 3  # a new folder gets exactly one first look


def test_a_run_that_tested_nothing_says_why(tmp_path: Path) -> None:
    """A project with functions but no tests used to show a bare 'undecided'; the reasons the run
    recorded ('app.py::load_data: no test oracle') now reach the card, the chat and the page."""
    from evalloop.session.chat import untested
    from evalloop.session.state import RunCard

    result = RunResult(
        run_id="r", summary_path=Path("s.md"), outcome=RunOutcome.undecided, cases=(), graded_artifacts=(),
        skipped=(), permission_requests=(), situations=(),
        notes=("app.py::get_engine: no test oracle", "app.py::load_data: no test oracle",
               "nothing could be graded: no applicable technique had a runnable oracle"),
    )
    card = RunCard.from_result(result, trigger=("app.py",), at=0.0)
    assert card.to_json()["notes"][0] == "app.py::get_engine: no test oracle"
    assert untested(card.to_json()) == ["get_engine", "load_data"]
    status = status_text({"root": "/w/app", "watching": True, "mascot": "unsure", "runs": [card.to_json()]})
    assert "Nothing was actually tested" in status and "get_engine, load_data" in status and "--author" in status


def test_untested_reads_both_wordings_of_the_note() -> None:
    from evalloop.session.chat import untested

    run = {"notes": ["app.py::home: no oracle available for app.py::home: the repository has no test_*.py file",
                     "app.py::load_data: no test oracle", "nothing could be graded: no applicable technique"]}
    assert untested(run) == ["home", "load_data"]
