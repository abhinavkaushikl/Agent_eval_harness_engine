"""The dancing avatars: every character dances every dance, feet stay planted, nothing jumps, the
choice is kept, and the page's JavaScript engine draws exactly what the Python one draws.

All without a window: the engine produces polygons and lines in figure space, and these tests check
those. The parity test runs the page's own script in Node (skipped when Node is not installed).
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from evalloop.run import RunOutcome, RunResult
from evalloop.session import avatars as av
from evalloop.session.consent_popup import BotClient
from evalloop.session.dashboard import dashboard_html
from evalloop.session.orchestrator import Session

STATES = ("idle", "evaluating", "happy", "alarmed", "unsure", "errored")
HEX = re.compile(r"^#[0-9a-f]{6}$")


def _points(prims: list[dict[str, object]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for prim in prims:
        p = prim["p"]
        assert isinstance(p, list)
        out += [(float(p[i]), float(p[i + 1])) for i in range(0, len(p), 2)]
    return out


# -- every character, every dance -----------------------------------------------------------------


def test_the_cast_and_the_dances() -> None:
    cat = av.catalog()
    assert cat["order"] == ["smooth", "zuri", "mira", "luz"]
    assert cat["dance_order"] == ["moonwalk", "twerk", "bharatanatyam", "salsa"]
    assert {c["dance"] for c in cat["characters"].values()} == set(cat["dance_order"])  # one signature each
    for dance in cat["dances"].values():
        for key in dance["keys"]:
            assert set(key) <= set(av.REST), set(key) - set(av.REST)


@pytest.mark.parametrize("dance", ["moonwalk", "twerk", "bharatanatyam", "salsa"])
@pytest.mark.parametrize("character", ["smooth", "zuri", "mira", "luz"])
def test_any_character_can_dance_any_dance_in_any_mood(character: str, dance: str) -> None:
    animator = av.Animator()
    for state in STATES:
        for _ in range(24):
            prims = av.pose_prims(character, animator.advance(1 / 30, av.catalog()["dances"][dance], state))
            assert prims and all(math.isfinite(v) for xy in _points(prims) for v in xy)
            for prim in prims:
                colours = [prim.get(k) for k in ("f", "o", "c") if prim.get(k)]
                assert all(isinstance(c, str) and HEX.match(c) for c in colours), colours
            xs = [x for x, _ in _points(prims)]
            assert max(xs) - min(xs) < 120 and min(y for _, y in _points(prims)) > -4  # on the floor, in frame


def test_planted_feet_stay_on_the_floor_through_a_squat() -> None:
    dance = av.catalog()["dances"]["bharatanatyam"]
    body = av.BODIES["dancer"]
    for i in range(40):
        ch = av.channels(dance, i * 0.4, 1.0)
        _, legs = av._skeleton(body, ch)
        for side in ("l", "r"):
            hip, knee, foot = legs[side]
            if ch[f"ft_{side}_y"] == 0.0:
                assert foot[1] == pytest.approx(body["ankle_y"])
            if ch["knee_out"] == 1.0 and hip[1] - foot[1] < body["thigh"] + body["shin"]:
                assert math.dist(hip, knee) == pytest.approx(body["thigh"], abs=1e-6)  # the IK keeps bone lengths
                assert math.dist(knee, foot) == pytest.approx(body["shin"], abs=1e-6)


def test_the_aramandi_opens_the_fan_and_the_knees() -> None:
    standing = av.pose_prims("mira", dict(av.REST))
    aramandi = av.pose_prims("mira", av.channels(av.catalog()["dances"]["bharatanatyam"], 0.0, 1.0))
    fan = lambda prims: next(p for p in prims if p["k"] == "poly" and p["o"] == av.look_palette("mira")["gold"]  # noqa: E731
                             and len(p["p"]) == 8)
    def width(prim: dict[str, object]) -> float:
        xs = [x for x, _ in _points([prim])]
        return max(xs) - min(xs)
    assert width(fan(aramandi)) > 2.5 * width(fan(standing))


def test_the_salsa_turn_shows_her_back() -> None:
    dance = av.catalog()["dances"]["salsa"]
    facing = [av.channels(dance, k / 4, 1.0)["sx"] for k in range(64)]
    assert min(facing) < -0.3, "the turn never faces away"
    front = av.pose_prims("luz", av.channels(dance, 0.0, 1.0))
    back_phase = next(k / 4 for k in range(64) if facing[k] < -0.3)
    back = av.pose_prims("luz", av.channels(dance, back_phase, 1.0))
    ink = av.look_palette("luz")["ink"]
    eyes = lambda prims: [p for p in prims if p["k"] == "poly" and p["f"] == ink and len(p["p"]) == 28]  # noqa: E731
    assert len(eyes(front)) == 2 and eyes(back) == []
    # a gentle (idle) performance never spins
    assert all(av.channels(dance, k / 4, 0.5)["sx"] == 1.0 for k in range(64))


def test_mudras_change_the_hands() -> None:
    dance = av.catalog()["dances"]["bharatanatyam"]
    used = {int(av.channels(dance, k, 1.0)["mudra_l"]) for k in range(len(dance["keys"]))}
    assert {1, 2, 3} <= used  # pataka, alapadma, and the fist at the waist
    counts = {m: len(av.catalog()["mudras"][str(m)]) for m in range(4)}
    assert counts[2] > counts[1] > counts[0]  # the lotus has its five fingers


def test_the_moonwalk_is_the_classic_one() -> None:
    dance = av.catalog()["dances"]["moonwalk"]
    glides = [av.channels(dance, k / 2, 1.0)["x"] for k in range(32)]
    classic = [av.pose("evaluating", t / 40).glide for t in range(60)]
    assert max(glides) == pytest.approx(max(classic), abs=1.0) and min(glides) == pytest.approx(min(classic), abs=1.0)


# -- motion is smooth, moods ease -----------------------------------------------------------------------


def test_no_frame_jumps_even_when_the_mood_changes() -> None:
    for character, dance in (("zuri", "twerk"), ("mira", "bharatanatyam"), ("luz", "salsa"), ("smooth", "moonwalk")):
        animator = av.Animator()
        d = av.catalog()["dances"][dance]
        previous = _points(av.pose_prims(character, animator.advance(0.0, d, "idle")))
        for frame in range(240):
            state = "idle" if frame < 80 else ("evaluating" if frame < 160 else "happy")
            current = _points(av.pose_prims(character, animator.advance(1 / 60, d, state)))
            if len(current) == len(previous):  # a hand shape or mouth may switch; positions must not jump
                worst = max(math.dist(a, b) for a, b in zip(previous, current))
                assert worst < 9.0, (character, frame, state, worst)
            previous = current


def test_the_mood_sets_how_hard_they_dance() -> None:
    d = av.catalog()["dances"]["twerk"]

    def depth(state: str) -> float:
        animator = av.Animator()
        return max(animator.advance(1 / 30, d, state)["drop"] for _ in range(300))

    assert depth("evaluating") > 1.6 * depth("idle") > 0.0


# -- the choice ---------------------------------------------------------------------------------------


def test_a_bad_choice_falls_back_to_defaults() -> None:
    kept = av.normalize_choice({"pet": "nobody", "stage": ["mira", "ghost", 3],
                                "chars": {"mira": {"dance": "salsa", "skin": 99, "outfit": 2}, "ghost": {}}})
    assert kept["pet"] == "smooth" and kept["stage"] == ["mira"]
    assert kept["chars"]["mira"] == {"dance": "salsa", "skin": None, "outfit": 2}
    assert av.normalize_choice("garbage") == av.default_choice()


def test_cycling_and_the_pet() -> None:
    choice = av.default_choice()
    assert av.pet_of(choice) == ("smooth", "moonwalk", None, None)
    choice = av.cycle(choice, "character")
    assert av.pet_of(choice)[:2] == ("zuri", "twerk")
    choice = av.cycle(choice, "dance")
    assert av.pet_of(choice)[:2] == ("zuri", "bharatanatyam")


def test_the_choice_is_saved_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "avatar.json"
    saved = av.save_choice(path, {"pet": "luz", "stage": ["luz", "mira"]})
    assert av.load_choice(path) == saved and saved["stage"] == ["mira", "luz"]  # catalog order
    path.write_text("{broken", encoding="utf-8")
    assert av.load_choice(path) == av.default_choice()


def test_the_page_and_the_pets_share_the_choice_through_the_session(tmp_path: Path) -> None:
    def evaluator(_p: str, _s: str) -> RunResult:
        return RunResult(run_id="r", summary_path=Path("s.md"), outcome=RunOutcome.clean, cases=(),
                         graded_artifacts=(), skipped=(), permission_requests=(), situations=(), notes=())

    path = tmp_path / "avatar.json"
    session = Session(tmp_path, store_dir=tmp_path / "store", evaluator=evaluator, avatar_path=path)
    server = session.serve(port=0)
    try:
        client = BotClient(port=server.server_address[1])
        import urllib.request

        with urllib.request.urlopen(f"{client.base}/avatars.json", timeout=3) as response:
            served = json.loads(response.read())
        assert served["order"] == av.catalog()["order"]
        assert client.status()["avatar"] == av.default_choice()
        reply = client.set_avatar({"pet": "mira", "stage": ["mira"], "chars": {"mira": {"dance": "twerk"}}})
        assert reply["avatar"]["pet"] == "mira"
        assert client.status()["avatar"]["chars"]["mira"]["dance"] == "twerk"
        assert av.load_choice(path)["pet"] == "mira"  # it survives a restart
    finally:
        server.shutdown()


def test_the_page_has_a_dance_floor() -> None:
    html = dashboard_html()
    assert 'id="stage"' in html and 'id="crew"' in html and "/avatars.json" in html and "/avatar" in html


# -- the page's JavaScript engine draws exactly what Python draws ---------------------------------------


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_the_page_engine_matches_the_python_engine(tmp_path: Path) -> None:
    engine = re.search(r"/\*AVATAR-ENGINE-START\*/(.*?)/\*AVATAR-ENGINE-END\*/", dashboard_html(), re.S)
    assert engine is not None
    cases = [(c, d, phase, amp, skin, outfit)
             for c in av.catalog()["order"] for d in av.catalog()["dance_order"]
             for phase, amp, skin, outfit in ((0.0, 1.0, None, None), (3.37, 1.0, 2, 5), (9.91, 0.5, None, 1),
                                              (13.2, 1.0, 4, None), (5.5, 0.85, 0, 8))]
    (tmp_path / "cat.json").write_text(json.dumps(av.catalog()), encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    script = tmp_path / "run.js"
    script.write_text(engine.group(1) + """
const fs=require("fs");
const cat=JSON.parse(fs.readFileSync(process.argv[2],"utf8")),cases=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));
const out=cases.map(([c,d,ph,amp,skin,outfit])=>{const ch=AV.channels(cat,cat.dances[d],ph,amp);
  return {ch,prims:AV.posePrims(cat,c,ch,skin,outfit)};});
const anim=new AV.Animator();const walk=[];
for(let i=0;i<50;i++)walk.push(anim.advance(cat,1/30,cat.dances.salsa,i<25?"idle":"alarmed"));
process.stdout.write(JSON.stringify({out,walk}));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script), str(tmp_path / "cat.json"), str(tmp_path / "cases.json")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    js = json.loads(result.stdout)

    def same(a: object, b: object, where: str) -> None:
        if isinstance(a, float) or isinstance(b, float):
            assert isinstance(a, (int, float)) and isinstance(b, (int, float)), where
            assert abs(float(a) - float(b)) < 1e-6, (where, a, b)
        elif isinstance(a, dict):
            assert isinstance(b, dict) and set(a) == set(b), (where, set(a) ^ set(b) if isinstance(b, dict) else b)
            for k in a:
                same(a[k], b[k], f"{where}.{k}")
        elif isinstance(a, list):
            assert isinstance(b, list) and len(a) == len(b), (where, len(a), len(b) if isinstance(b, list) else b)
            for i, (x, y) in enumerate(zip(a, b)):
                same(x, y, f"{where}[{i}]")
        else:
            assert a == b or (isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 1e-6), (where, a, b)

    for (c, d, phase, amp, skin, outfit), got in zip(cases, js["out"]):
        ch = av.channels(av.catalog()["dances"][d], phase, amp)
        same(ch, got["ch"], f"{c}/{d}@{phase} channels")
        same(av.pose_prims(c, ch, skin=skin, outfit=outfit), got["prims"], f"{c}/{d}@{phase} prims")
    animator = av.Animator()
    walk = [animator.advance(1 / 30, av.catalog()["dances"]["salsa"], "idle" if i < 25 else "alarmed") for i in range(50)]
    same(walk, js["walk"], "animator")
