"""The painted picture (src/painter.py): cast, look, template, exposure, bars,
motion and grade. Everything here runs offline (ffmpeg only)."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import painter  # noqa: E402
import prompt_lint  # noqa: E402

BANK = json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=120)


# ------------------------------------------------------------------ the flag

def test_off_unless_asked(monkeypatch):
    monkeypatch.delenv("REEL_PICTURE", raising=False)
    assert painter.enabled() is False
    monkeypatch.setenv("REEL_PICTURE", "")
    assert painter.enabled() is False
    monkeypatch.setenv("REEL_PICTURE", "painted")
    assert painter.enabled() is True


# ------------------------------------------------------------------ the cast

def test_every_cast_token_has_a_fixed_look_and_seed():
    assert set(painter.CAST) == {"man", "marcus", "seneca", "epictetus"}
    seeds = [c["seed"] for c in painter.CAST.values()]
    assert len(set(seeds)) == 4 and all(isinstance(s, int) for s in seeds)
    for key, c in painter.CAST.items():
        text, named = painter.expand_cast("{%s} stands by a column at dusk" % key)
        assert named == [key]
        assert c["look"] in text and "{" not in text


def test_the_young_man_is_the_viewers_stand_in():
    look = painter.CAST["man"]["look"]
    for part in ("late twenties", "short dark beard", "plain undyed wool tunic"):
        assert part in look


def test_a_possessive_token_still_reads():
    text, _ = painter.expand_cast("Close-up of {man}'s hand gripping a stone post")
    assert text.startswith("Close-up of a young Roman man's hand gripping")
    assert "tunic's" not in text


def test_a_second_mention_is_not_described_twice():
    text, named = painter.expand_cast("{man} looks up; {man} smiles")
    assert named == ["man"]
    assert text.count("late twenties") == 1 and "the young Roman man smiles" in text


def test_a_scene_naming_a_person_paints_on_their_seed():
    s = "{marcus} reading a letter by lamplight"
    assert painter.seed_for(s, "q1", 3, True) == painter.CAST["marcus"]["seed"]
    assert painter.seed_for(s, "q2", 5, True) == painter.CAST["marcus"]["seed"]


def test_other_seeds_are_stable_and_never_shared_between_quotes():
    s = "{man} walking alone, in ancient Rome"
    a = painter.seed_for(s, "q1", 2, False)
    assert a == painter.seed_for(s, "q1", 2, False)       # rehearsal == live
    assert a != painter.seed_for(s, "q2", 2, False)       # same template line, other quote
    assert a != painter.seed_for(s, "q1", 3, False)
    assert 0 <= a < 2_000_000_000


def test_unknown_tokens_refuse_the_scene():
    assert painter.unknown_tokens("{senca} at a desk") == ["{senca}"]
    assert "unknown cast token" in painter.refused("{senca} at a desk, lit by a lamp")


# ------------------------------------------------------------------ the look

def test_the_style_never_negates_a_colour():
    for light in ("dawn light", "nothing"):
        assert not painter.negates_colour(painter.style_for(light))
    assert painter.negates_colour("a toga, not red")
    assert painter.negates_colour("no blue tint")
    assert painter.negates_colour("without any gold")
    assert not painter.negates_colour("a red cloak in golden light")


def test_the_style_carries_the_brief():
    s = painter.style_for("a bare room").lower()
    for part in ("painterly", "greco-roman", "colour", "warm", "middle third",
                 "detail kept in the shadows", "full-bleed"):
        assert part in s, part
    assert "sunlight" in s                               # a named warm light


def test_a_scene_with_its_own_light_keeps_it_as_the_only_one():
    assert painter.DEFAULT_LIGHT not in painter.style_for("a man by a torch")
    assert painter.DEFAULT_LIGHT in painter.style_for("a man on a road")


def test_no_word_that_paints_letterbox_bars():
    p = painter.build_prompt("{man} on a quay in the rain, lit by a break of sun")
    assert not painter.BAR_WORDS.search(p)
    assert "film still" not in p.lower()


def test_prompt_is_scene_first_with_the_guards_and_fits_every_model():
    p = painter.build_prompt("{seneca} writing at a desk, lit by a clay lamp")
    assert p.startswith("Seneca writing at a desk")
    assert prompt_lint.SAFE_POSITIVE in p and painter.ERA in p
    assert len(p) < 2048                                 # schnell's limit


# ------------------------------------------------------------------ scenes

def test_the_scene_writers_shots_all_pass_the_prompt_check():
    with_scenes = [q for q in BANK if q.get("scenes")]
    for q in with_scenes:
        assert 6 <= len(q["scenes"]) <= 8, q["id"]
        for s in q["scenes"]:
            assert not painter.refused(s), (q["id"], s, painter.refused(s))


def test_every_visual_on_the_shelf_becomes_a_paintable_scene(monkeypatch):
    """Quotes without scenes still get the painted look: every stock keyword
    goes through the template, and anything the prompt check refuses falls to
    the theme's own scene, which always passes."""
    for k in list(__import__("os").environ):
        if k.startswith(("REEL_PAINT_SCENE", "REEL_BG_FLAVOR")):
            monkeypatch.delenv(k)
    for q in BANK:
        for i, v in enumerate(q["visuals"]):
            monkeypatch.setenv(f"REEL_BG_FLAVOR{i if i else ''}", v)
            scene, handwritten, _ = painter.slot_scene(i, q["theme"])
            assert not handwritten
            assert not painter.refused(scene), (q["id"], v, scene)
            assert not painter.negates_colour(painter.build_prompt(scene))


def test_the_template_moves_modern_things_into_the_classical_world():
    assert "chariot" in painter.scene_from_visual("luxury car")
    assert "wax tablet" in painter.scene_from_visual("phone scrolling")
    assert painter.scene_from_visual("man boxing").startswith("{man} training as a boxer")
    assert painter.scene_from_visual("man running rain").startswith("{man} running through the rain")
    s = painter.scene_from_visual("sunrise")
    assert "ancient" in s
    # a "still:" line loses its own style words (the look is added by code)
    s = painter.scene_from_visual("still:marble bust of Seneca, dramatic candlelight, black background")
    assert "black background" not in s and "dramatic" not in s and "Seneca" in s
    # nothing classical to paint -> the theme's scene
    assert painter.scene_from_visual("credit card", "desire") == painter.THEME_SCENES["desire"]


def test_theme_scenes_pass_and_name_a_light():
    for t, s in painter.THEME_SCENES.items():
        assert not painter.refused(s), t
        assert painter.LIGHT_WORDS.search(s), t


def test_slot_scene_order_written_then_template_then_theme(monkeypatch):
    monkeypatch.setenv("REEL_PAINT_SCENE2", "{man} at a well at dawn")
    monkeypatch.setenv("REEL_BG_FLAVOR2", "luxury car")
    assert painter.slot_scene(2, "ego") == ("{man} at a well at dawn", True, "")
    monkeypatch.setenv("REEL_PAINT_SCENE2", "{man} reading a letter, words visible")
    scene, written, why = painter.slot_scene(2, "ego")
    assert not written and "chariot" in scene and "refused" in why
    monkeypatch.delenv("REEL_PAINT_SCENE2")
    monkeypatch.delenv("REEL_BG_FLAVOR2")
    assert painter.slot_scene(2, "ego")[0] == painter.THEME_SCENES["ego"]


# ------------------------------------------------------------------ exposure

@pytest.fixture
def stills(tmp_path):
    """Three 1024x1920 stills: dark, bright, already in the band."""
    out = {}
    for name, colour in (("dark", "0x1a1410"), ("bright", "0xd0c8b8"), ("mid", "0x6a5c4c")):
        p = tmp_path / f"{name}.png"
        _ff("-f", "lavfi", "-i", f"color=c={colour}:s=1024x1920:d=1",
            "-vf", "noise=alls=12:allf=u", "-frames:v", "1", str(p))
        out[name] = p
    return out


def test_exposure_brings_every_shot_into_the_band(stills):
    dark = painter.exposure(stills["dark"])
    assert dark["luma"] < painter.LOW_LUMA and dark["k"] > 0
    assert dark["luma_after"] >= 0.30
    bright = painter.exposure(stills["bright"])
    assert bright["k"] < 0 and bright["luma_after"] <= painter.HIGH_LUMA + 0.02
    mid = painter.exposure(stills["mid"])
    assert mid["k"] == 0.0 and mid["luma_after"] == mid["luma"]


def test_exposure_curve_keeps_black_black_and_white_white():
    for k in (-3.0, 0.0, 2.0, painter.MAX_EXPOSURE):
        lut = painter._expo_lut(k)
        assert lut[0] == 0 and lut[255] == 255
        assert all(b >= a for a, b in zip(lut, lut[1:]))   # monotonic: no banding flips


def test_prepare_still_fills_the_frame_at_the_measured_exposure(stills, tmp_path):
    got = painter.prepare_still(stills["dark"], tmp_path / "x.paint.mp4")
    assert got and painter.probe_size(got["clip"]) == (1080, 1920)
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", str(got["clip"]), "-frames:v", "1",
                          "-vf", "signalstats,metadata=print", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    yavg = float(next(l for l in out.splitlines() if "YAVG" in l).split("=")[-1])
    assert abs(yavg / 255 - got["luma_after"]) < 0.04


# ------------------------------------------------------------------ bars

def _letterbox(tmp_path, top, bottom, left=0, right=0, name="lb.png", base="0x7a6a58"):
    p = tmp_path / name
    boxes = []
    if top:
        boxes.append(f"drawbox=x=0:y=0:w=1024:h={top}:color=black:t=fill")
    if bottom:
        boxes.append(f"drawbox=x=0:y={1920 - bottom}:w=1024:h={bottom}:color=black:t=fill")
    if left:
        boxes.append(f"drawbox=x=0:y=0:w={left}:h=1920:color=black:t=fill")
    if right:
        boxes.append(f"drawbox=x={1024 - right}:y=0:w={right}:h=1920:color=black:t=fill")
    vf = ",".join(["noise=alls=20:allf=u"] + boxes)
    _ff("-f", "lavfi", "-i", f"color=c={base}:s=1024x1920:d=1", "-vf", vf, "-frames:v", "1", str(p))
    return p


def test_a_letterboxed_still_is_found_and_cropped(tmp_path):
    p = _letterbox(tmp_path, 230, 230)
    bars = painter.still_bars(p)
    assert 225 <= bars["top"] <= 260 and 225 <= bars["bottom"] <= 260
    crop = painter.crop_filter(bars, 1024, 1920)
    assert crop.startswith("crop=1024:")
    got = painter.prepare_still(p, tmp_path / "lb.paint.mp4")
    assert got["crop"] == crop
    assert painter.check_frame_fill(got["clip"]) == []


def test_a_pillarboxed_still_is_found(tmp_path):
    bars = painter.still_bars(_letterbox(tmp_path, 0, 0, 120, 120, "pb.png"))
    assert bars["left"] >= 115 and bars["right"] >= 115


def test_a_dark_band_on_one_side_is_a_picture_not_a_bar(tmp_path):
    """Three of the six real FLUX stills in samples/frames have a black wall
    on one side; cropping it would cut the picture."""
    assert not any(painter.still_bars(_letterbox(tmp_path, 400, 0, name="sky.png")).values())
    for f in sorted((ROOT / "samples" / "frames").glob("*.jpg")):
        assert not any(painter.still_bars(f).values()), f.name


def test_a_letterboxed_stock_clip_is_cropped_before_the_frame_is_filled(tmp_path):
    """The live edit of 2026-11-10: a sky clip uploaded with its own black
    bars (22% of rows); cover-scaling keeps them. Content moves, bars don't."""
    clip = tmp_path / "stock.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=720x1280:d=3:r=30", "-vf",
        "drawbox=x=0:y=0:w=720:h=150:color=black:t=fill,"
        "drawbox=x=0:y=1130:w=720:h=150:color=black:t=fill",
        "-c:v", "libx264", "-preset", "ultrafast", str(clip))
    bars = painter.clip_bars(clip)
    assert 145 <= bars["top"] <= 175 and 145 <= bars["bottom"] <= 175
    assert painter.source_crops([clip])[0].startswith("crop=720:")
    clean = tmp_path / "clean.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=720x1280:d=3:r=30", "-c:v", "libx264",
        "-preset", "ultrafast", str(clean))
    assert painter.source_crops([clean]) == [""]
    painter.PAINTED_CLIPS.add(str(clip))
    try:
        assert painter.source_crops([clip]) == [""]                     # painted: already clean
    finally:
        painter.PAINTED_CLIPS.discard(str(clip))


def test_the_finished_render_check_finds_bars_and_names_the_slot(tmp_path):
    v = tmp_path / "render.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:d=4:r=30", "-vf",
        "drawbox=x=0:y=0:w=1080:h=200:color=black:t=fill:enable='gte(t,2)',"
        "drawbox=x=0:y=1720:w=1080:h=200:color=black:t=fill:enable='gte(t,2)'",
        "-c:v", "libx264", "-preset", "ultrafast", str(v))
    hits = painter.check_frame_fill(v, [0.0, 2.0, 4.0])
    assert hits and {h["side"] for h in hits} == {"top", "bottom"}
    assert {h["slot"] for h in hits} == {1}
    assert all(h["t"] >= 2.0 for h in hits)


def test_frame_fill_failures_ban_the_slot_for_the_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(painter, "check_frame_fill",
                        lambda v, b: [{"t": 1.0, "side": "top", "px": 200, "slot": 4}])
    painter.BANNED_SLOTS.clear()
    assert painter.frame_fill_failures(tmp_path / "v.mp4", [0, 1, 2])
    assert painter.BANNED_SLOTS == {4}
    assert painter.fetch_slot(4, tmp_path / "x.mp4") is None
    painter.BANNED_SLOTS.clear()
    monkeypatch.setenv("REEL_FRAME_CHECK", "0")
    assert painter.frame_fill_failures(tmp_path / "v.mp4", [0, 1]) == []


# ------------------------------------------------------------------ motion

@pytest.mark.parametrize("slot", range(8))
def test_the_window_never_leaves_the_picture(slot):
    """zoom >= 1 and the drift inside its margin: the edge of the still is
    never on screen, so a move can never show a black edge."""
    for frames in (30, 45, 75):
        for i in range(frames):
            x0, y0, x1, y1 = painter.window(slot, i, frames)
            assert x0 >= -1e-6 and y0 >= -1e-6, (slot, i)
            assert x1 <= painter.W + 1e-6 and y1 <= painter.H + 1e-6, (slot, i)
            assert abs((x1 - x0) / (y1 - y0) - painter.W / painter.H) < 1e-9


@pytest.mark.parametrize("slot", range(8))
def test_every_shot_moves_at_a_steady_sub_pixel_pace(slot):
    """Steady in what the viewer sees: a zoom changes scale by the same ratio
    every frame (every point then moves at one speed), a drift moves the
    window by the same distance every frame."""
    frames = 42
    path = [painter.window(slot, i, frames) for i in range(frames)]
    zooms = [painter.W / (x1 - x0) for x0, _, x1, _ in path]
    centres = [((x0 + x1) / 2, (y0 + y1) / 2) for x0, y0, x1, y1 in path]
    if painter.MOVES[slot] in ("push", "pull"):
        ratios = [b / a for a, b in zip(zooms, zooms[1:])]
        assert max(ratios) - min(ratios) < 1e-9
        assert abs(ratios[0] - 1) > 1e-4                      # it moves
        edge = [abs(r - 1) * painter.H / 2 for r in ratios]   # px/frame at the frame edge
    else:
        assert max(zooms) - min(zooms) < 1e-9
        edge = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(centres, centres[1:])]
        assert max(edge) - min(edge) < 1e-6
    assert 0.3 < min(edge) and max(edge) < 3.0                # slow, and never still


def test_neighbouring_shots_never_share_a_move_and_the_hook_pushes_in():
    moves = painter.MOVES
    assert moves[0] == "push"
    assert all(a != b for a, b in zip(moves, moves[1:] + moves[:1]))
    x0, _, _, _ = painter.window(0, 0, 40)
    x0e, _, _, _ = painter.window(0, 39, 40)
    assert x0e > x0                               # the window shrinks: a push in


def test_motion_is_perspective_not_zoompan():
    f = painter.motion_filter(3, 42)
    assert f.startswith("perspective=") and "eval=frame" in f and "interpolation=cubic" in f
    assert "zoompan" not in f
    assert "(in-1)/41" in f                       # perspective counts frames from 1
    assert "pow(" in painter.motion_filter(0, 42)    # exponential zoom


# ------------------------------------------------------------------ grade

def test_the_grade_is_colour_warm_and_light_handed(monkeypatch):
    for k in ("REEL_PAINT_SAT", "REEL_PAINT_WARM", "REEL_PAINT_VIGNETTE"):
        monkeypatch.delenv(k, raising=False)
    g = ",".join(painter.grade_parts())
    assert "hue=s=0" not in g and "saturation=1.080" in g
    assert "curves=master='0/0.035" in g          # black point lifted: detail in the shadows
    e = painter.enhance_graph("a", "b")
    angle = float(e.split("vignette=angle=")[1].split("[")[0])
    assert angle < math.pi / 5                    # lighter than ffmpeg's default vignette
    assert "c1_expr=A:c2_expr=A" in e             # bloom is luma-only: it never tints
    assert "noise=alls=3:allf=t" in e             # fine grain
