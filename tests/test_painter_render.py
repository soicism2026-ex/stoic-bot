"""The painted picture inside render.py, and proof that it is invisible when off.

1. Flag off: the ffmpeg command render_reel builds for today's live edit and
   for a classic post is IDENTICAL to the one render.py built before the
   painter existed (tests/golden/, captured by tests/render_capture.py).
2. Flag on: every segment moves by ffmpeg's perspective filter (sub-pixel),
   the painted grade replaces the date-rotated one, no black-and-white.
3. Smoothness, measured on a rendered move: per-frame displacement by a
   Lucas-Kanade estimate (pure Python) is steady, and the same meter catches
   zoompan's whole-pixel judder (the owner's "shaking images", 2026-10-01).
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import painter  # noqa: E402
import render  # noqa: E402
import render_capture as rc  # noqa: E402


@pytest.mark.parametrize("case", sorted(rc.CASES))
def test_flag_off_renders_exactly_as_before(case, monkeypatch):
    """If this fails after a deliberate change to today's look, re-capture
    with: python3 tests/render_capture.py golden src/render.py"""
    monkeypatch.delenv("REEL_PICTURE", raising=False)
    with tempfile.TemporaryDirectory() as d:
        now = rc.capture(render, Path(d), case)
    gold = json.loads((rc.GOLDEN / f"render_cmd_{case}.json").read_text())
    assert now == gold


def _painted_graph(monkeypatch, extra=None):
    env = {**rc.LIVE_EDIT, "REEL_PICTURE": "painted", "REEL_MONO": "0",
           "REEL_ATMOSPHERE": "0", **(extra or {})}
    monkeypatch.setitem(rc.CASES, "painted", (env, True))
    with tempfile.TemporaryDirectory() as d:
        cmd = rc.capture(render, Path(d), "painted")
    return cmd[cmd.index("-filter_complex") + 1]


def test_flag_on_moves_every_shot_sub_pixel_and_grades_in_colour(monkeypatch):
    g = _painted_graph(monkeypatch)
    assert g.count("perspective=") == 8 and "zoompan" not in g
    assert "eval=frame" in g and "interpolation=cubic" in g
    assert "hue=s=0" not in g                                  # colour
    assert "curves=master='0/0.035" in g                       # the painted grade
    assert "colorbalance=rs=-0.08" not in g                    # not the cinematic teal-orange
    for move in set(painter.MOVES):
        assert any(painter.motion_filter(i, 1)[:20] for i, m in enumerate(painter.MOVES) if m == move)


def test_black_and_white_stays_possible_when_asked_for(monkeypatch):
    g = _painted_graph(monkeypatch, {"REEL_MONO": "1"})
    assert g.index("hue=s=0") > g.index("curves=master")       # the last colour step


# ------------------------------------------------------------------ smoothness

W2, H2, N = 540, 960, 45


def _texture(tmp: Path) -> Path:
    p = tmp / "tex.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=0x806040:s={W2}x{H2}:d=1", "-vf",
                    "noise=alls=90:allf=u,gblur=sigma=2.2,eq=contrast=1.6",
                    "-frames:v", "1", str(p)], check=True, timeout=60)
    return p


def _frames(still: Path, vf: str) -> list[bytes]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-framerate", "30", "-loop", "1", "-i",
                          str(still), "-vf", f"format=yuv420p,{vf},format=gray",
                          "-frames:v", str(N), "-f", "rawvideo", "-"],
                         capture_output=True, check=True, timeout=120).stdout
    size = W2 * H2
    return [raw[i * size:(i + 1) * size] for i in range(len(raw) // size)]


def _lk(a: bytes, b: bytes, cx: int, cy: int, r: int = 28) -> float:
    """Lucas-Kanade translation of a patch between two grey frames (px)."""
    sxx = sxy = syy = sxt = syt = 0.0
    for y in range(cy - r, cy + r):
        o = y * W2
        for x in range(cx - r, cx + r):
            i = o + x
            gx = ((a[i + 1] - a[i - 1]) + (b[i + 1] - b[i - 1])) / 4.0
            gy = ((a[i + W2] - a[i - W2]) + (b[i + W2] - b[i - W2])) / 4.0
            gt = b[i] - a[i]
            sxx += gx * gx
            sxy += gx * gy
            syy += gy * gy
            sxt += gx * gt
            syt += gy * gt
    det = sxx * syy - sxy * sxy
    dx = (-syy * sxt + sxy * syt) / det
    dy = (sxy * sxt - sxx * syt) / det
    return math.hypot(dx, dy)


def _series(frames, cx, cy):
    return [_lk(a, b, cx, cy) for a, b in zip(frames, frames[1:])]


def test_a_painted_drift_moves_the_same_distance_every_frame(tmp_path):
    still = _texture(tmp_path)
    s = _series(_frames(still, painter.motion_filter(1, N)), W2 // 2, H2 // 2)   # driftr
    zd = 1 / (1 - painter._amps(1)[1] - 0.01)
    want = painter._amps(1)[1] * W2 / (N - 1) * zd                                 # ~0.65 px
    assert len(s) == N - 1
    mean = sum(s) / len(s)
    assert 0.6 * want < mean < 1.4 * want          # LK is biased on noise; steadiness is the test
    assert min(s) > 0.75 * mean and max(s) < 1.25 * mean, [round(x, 2) for x in s]


def test_a_painted_push_is_steady_off_centre(tmp_path):
    still = _texture(tmp_path)
    s = _series(_frames(still, painter.motion_filter(0, N)), W2 // 4, H2 // 4)
    mean = sum(s) / len(s)
    assert mean > 0.2
    assert min(s) > 0.7 * mean and max(s) < 1.3 * mean, [round(x, 2) for x in s]


def test_the_meter_catches_zoompan_judder(tmp_path):
    """Control: the same drift through zoompan (whole-pixel crops) stalls and
    jumps. If this ever passes as smooth, the meter above proves nothing."""
    still = _texture(tmp_path)
    vf = (f"zoompan=z=1.06:d=1:x='(iw-iw/zoom)/2-14+28*on/{N - 1}':"
          f"y='(ih-ih/zoom)/2':s={W2}x{H2}:fps=30")
    s = _series(_frames(still, vf), W2 // 2, H2 // 2)
    mean = sum(s) / len(s)
    assert min(s) < 0.4 * mean or max(s) > 1.6 * mean, [round(x, 2) for x in s]
