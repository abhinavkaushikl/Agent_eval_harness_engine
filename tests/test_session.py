"""The session tool: the poller detects change, the orchestrator evaluates only on change, and the
mascot/state reflect the outcome. The engine is injected so these tests never do real grading.
"""

from __future__ import annotations

from pathlib import Path

from evalloop.memory.case import Verdict
from evalloop.run import RunOutcome, RunResult
from evalloop.session.dashboard import dashboard_html
from evalloop.session.orchestrator import Session
from evalloop.session.poller import changed_files, snapshot
from evalloop.session.state import MascotState


def _fake_result(outcome: RunOutcome, run_id: str = "r1") -> RunResult:
    return RunResult(
        run_id=run_id,
        summary_path=Path("summary.md"),
        outcome=outcome,
        cases=(),
        graded_artifacts=(),
        skipped=(),
        permission_requests=(),
        situations=(),
        notes=(),
    )


def test_poller_detects_add_modify_remove(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    s1 = snapshot(tmp_path)
    (tmp_path / "a.py").write_text("x = 2\n")
    (tmp_path / "b.py").write_text("y = 1\n")
    s2 = snapshot(tmp_path)
    assert changed_files(s1, s2) == ("a.py", "b.py")
    (tmp_path / "a.py").unlink()
    s3 = snapshot(tmp_path)
    assert "a.py" in changed_files(s2, s3)


def test_poller_ignores_dotdirs_and_non_python(tmp_path: Path) -> None:
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "c.py").write_text("z = 1\n")
    (tmp_path / "notes.txt").write_text("hello\n")
    assert snapshot(tmp_path) == {}


def test_first_tick_evaluates_then_only_on_change(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    calls: list[str] = []

    def evaluator(path: str, _store: str) -> RunResult:
        calls.append(path)
        return _fake_result(RunOutcome.clean, run_id=f"r{len(calls)}")

    session = Session(tmp_path, store_dir=tmp_path / "store", evaluator=evaluator, clock=lambda: 1.0)

    first = session.tick()
    assert first is not None and first.outcome == "clean"          # first look always evaluates
    assert session.tick() is None                                   # nothing changed -> no run
    (tmp_path / "a.py").write_text("x = 2\n")
    third = session.tick()
    assert third is not None and third.trigger == ("a.py",)         # change -> evaluate, trigger named
    assert len(calls) == 2


def test_mascot_tracks_outcome(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    outcomes = iter([RunOutcome.problem, RunOutcome.clean])

    def evaluator(path: str, _store: str) -> RunResult:
        return _fake_result(next(outcomes))

    session = Session(tmp_path, store_dir=tmp_path / "store", evaluator=evaluator, clock=lambda: 1.0)
    session.tick()
    assert session.state.mascot is MascotState.alarmed
    (tmp_path / "a.py").write_text("x = 2\n")
    session.tick()
    assert session.state.mascot is MascotState.happy


def test_state_json_is_serialisable_and_newest_first(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    ids = iter(["old", "new"])

    def evaluator(path: str, _store: str) -> RunResult:
        return _fake_result(RunOutcome.clean, run_id=next(ids))

    session = Session(tmp_path, store_dir=tmp_path / "store", evaluator=evaluator, clock=lambda: 2.0)
    session.tick()
    (tmp_path / "a.py").write_text("x = 2\n")
    session.tick()
    payload = session.state.to_json()
    assert [r["run_id"] for r in payload["runs"]] == ["new", "old"]
    assert payload["mascot"] == "happy"


def test_a_failed_evaluation_does_not_kill_the_watcher(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")

    def boom(path: str, _store: str) -> RunResult:
        raise RuntimeError("engine blew up on this repo")

    session = Session(tmp_path, store_dir=tmp_path / "store", evaluator=boom, clock=lambda: 1.0)
    card = session.tick()
    assert card is not None
    assert card.outcome == "errored"
    assert "engine blew up" in card.error
    assert session.state.mascot is MascotState.errored
    # the watcher is still alive: another change ticks again rather than raising
    (tmp_path / "a.py").write_text("x = 2\n")
    assert session.tick() is not None
    assert session.state.to_json()["runs"][0]["outcome"] == "errored"


def test_signal_line_is_always_truthful() -> None:
    """The pet's bubble shows what he is testing NOW, or last tested + result, never a blank."""
    from evalloop.session.overlay import signal_line

    # in flight: the current target, while the mood is evaluating
    text, _ = signal_line({"current": ["connecttodb.py"], "runs": []}, "evaluating")
    assert text == "testing connecttodb.py"

    # not in flight: the last file graded and how it went (the common case a 1s poll actually sees)
    data = {"root": "/x/kaycee", "current": [], "runs": [
        {"outcome": "problem", "trigger": ["connecttodb.py"]},
        {"outcome": "clean", "trigger": ["other.py"]},
    ]}
    text, accent = signal_line(data, "alarmed")
    assert "connecttodb.py" in text and text.startswith("⚠")
    assert accent == "#ff453a"

    # before the first run: still a signal, never empty
    text, _ = signal_line({"root": "/x/kaycee", "current": [], "runs": []}, "idle")
    assert text == "watching kaycee"

    # a run with no trigger (the first look) does not count as "last tested"; fall through to watching
    text, _ = signal_line({"root": "/x/kaycee", "runs": [{"outcome": "clean", "trigger": []}]}, "happy")
    assert text == "watching kaycee"


def test_dashboard_is_self_contained(tmp_path: Path) -> None:
    html = dashboard_html()
    assert "status.json" in html            # it polls live state
    assert "EvalLoop" in html               # it is the right page
    assert "cdn" not in html.lower()        # no external CDN
    assert "<script src" not in html.lower()  # no external script


def test_bot_pose_is_a_continuous_dance_without_a_window() -> None:
    import math

    from evalloop.session.overlay import MOOD, PALETTE, pose

    # the dance leans far; idling barely sways at all (sample finely to hit the true peak)
    dance = max(abs(pose("evaluating", t / 100).lean) for t in range(2000))
    idle = max(abs(pose("idle", t / 100).lean) for t in range(2000))
    assert dance > 10 and idle < 5 and dance > 3 * idle, (dance, idle)

    # it is continuous: a small step in time is a small change in lean (no frame jumps)
    for t in (0.0, 0.7, 1.9, 3.3):
        assert abs(pose("evaluating", t).lean - pose("evaluating", t + 0.005).lean) < 1.0

    # deterministic, and the glove hand stays within its travel
    assert pose("evaluating", 1.23) == pose("evaluating", 1.23)
    for state in ("idle", "evaluating", "happy", "alarmed", "unsure", "errored"):
        assert state in MOOD
        p = pose(state, 0.4)
        assert 0.0 <= p.arm <= 1.0 and math.isfinite(p.lean) and math.isfinite(p.bob)

    # the figure is drawn from named colours, not pixel glyphs
    assert {"suit", "hair", "skin", "shirt", "tie", "ink"} <= set(PALETTE)


def test_the_lean_is_anchored_at_the_shoes() -> None:
    """The signature lean, now drawn by the avatar engine: the top of the body travels, the feet do not."""
    from evalloop.session.avatars import REST, pose_prims

    def xs_at(lean: float) -> tuple[float, float]:
        channels = {**REST, "hip_x": 0.36 * lean, "pelvis": -lean * 0.57, "knee_out": 0.25}
        points = [(p["p"][i], p["p"][i + 1]) for p in pose_prims("smooth", channels) for i in range(0, len(p["p"]), 2)]
        bottom = [x for x, y in points if y < 2.0]      # at the shoes
        top = [x for x, y in points if y > 90.0]        # up at the hat
        return (sum(bottom) / len(bottom), sum(top) / len(top))

    foot_0, hat_0 = xs_at(0.0)
    foot_lean, hat_lean = xs_at(15.0)
    assert abs(foot_lean - foot_0) < 1.0, "the shoes must stay planted"
    assert hat_lean - hat_0 > 8.0, "the hat must travel with the lean"


def test_the_session_passes_native_calibration_through_to_the_run(tmp_path: Path) -> None:
    """`start --calibrate-native`: a failure only the sandbox causes is withheld on the bot's card too."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "scale.py").write_text("def scale(x, k):\n    return x * k\n", encoding="utf-8")
    (tmp_path / "tests" / "factor.txt").write_text("3\n", encoding="utf-8")
    (tmp_path / "tests" / "test_scale.py").write_text(
        "from pathlib import Path\nfrom scale import scale\n\n"
        "def test_uses_data_beside_it():\n"
        "    assert scale(2, int((Path(__file__).parent / 'factor.txt').read_text())) == 6\n",
        encoding="utf-8",
    )
    plain = Session(tmp_path, store_dir=tmp_path / ".s1").tick()
    calibrated = Session(tmp_path, store_dir=tmp_path / ".s2", calibrate_native=True).tick()
    assert plain is not None and plain.outcome == "problem"
    assert calibrated is not None and calibrated.outcome != "problem"
    assert all(case.verdict != "failed" for case in calibrated.cases)
