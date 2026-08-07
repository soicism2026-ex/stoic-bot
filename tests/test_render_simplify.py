"""The owner's verdict on the published shorts (2026-08-07):
"I don't even know what to read first, there's too much going on" and
"the background is way too dark because of the filters".

The frame carried five competing text layers, two of which said the SAME
WORDS (karaoke caption + narration subtitle), and generated stills were
darkened three separate times. These pin the simplification.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _reload(monkeypatch, **env):
    import importlib
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import render
    return importlib.reload(render)


def test_captions_off_by_default(monkeypatch):
    """The quote card is the identity. The karaoke duplicated the narration."""
    r = _reload(monkeypatch, REEL_CAPTIONS=None)
    assert r.CAPTIONS_ON is False


def test_captions_can_still_be_forced_on(monkeypatch):
    """caption_only styles need them — there is no quote card there."""
    r = _reload(monkeypatch, REEL_CAPTIONS="1")
    assert r.CAPTIONS_ON is True


def test_mission_strapline_off_by_default(monkeypatch):
    """It sat at y=265, exactly where YouTube's auto-CC box lands."""
    r = _reload(monkeypatch, REEL_MISSION=None)
    assert r.MISSION_ON is False


def test_mission_can_be_restored(monkeypatch):
    r = _reload(monkeypatch, REEL_MISSION="1")
    assert r.MISSION_ON is True


def test_generated_brightness_lift_raised(monkeypatch):
    r = _reload(monkeypatch)
    assert r.GEN_BRIGHT_LIFT >= 0.20, "still too dark for generated stills"


def test_lift_still_bounded(monkeypatch):
    """A lift larger than the darkest grade would wash footage out."""
    r = _reload(monkeypatch)
    assert r.GEN_BRIGHT_LIFT <= abs(min(g[0] for g in r._GRADES)) + 0.02


# ------------------------------------------------------------------- motion

def test_motion_is_per_clip_not_one_slow_drift(monkeypatch):
    """The old zoom was applied AFTER concat, spreading 0.08 of zoom across the
    whole video — about 0.013 per clip, which is invisible."""
    r = _reload(monkeypatch)
    assert r.MOTION_ON is True
    assert r.MOTION_AMP >= 0.10


def test_consecutive_clips_get_different_moves(monkeypatch):
    r = _reload(monkeypatch)
    moves = [r._MOVES[i % len(r._MOVES)] for i in range(5)]
    for a, b in zip(moves, moves[1:]):
        assert a != b, f"consecutive clips share the move {a!r}"


def test_hook_clip_pushes_in(monkeypatch):
    """Clip 0 is the hook — a push-in is the strongest 'something is
    happening' signal in the 1.5s that decides everything."""
    r = _reload(monkeypatch)
    assert r._MOVES[0] == "push"


def test_easing_is_not_linear(monkeypatch):
    r = _reload(monkeypatch)
    e = r._ease(90)
    assert "3-2*" in e, "smoothstep missing — linear motion reads mechanical"


@pytest.mark.parametrize("idx", range(6))
def test_every_move_builds_a_zoompan(monkeypatch, idx):
    r = _reload(monkeypatch)
    m = r._motion(idx, 90)
    assert m.startswith("zoompan=") and "fps=30" in m


def test_motion_can_be_disabled(monkeypatch):
    r = _reload(monkeypatch, REEL_MOTION="0")
    assert r.MOTION_ON is False


def test_atmosphere_defaults_on_and_is_subtle(monkeypatch):
    r = _reload(monkeypatch, REEL_ATMOSPHERE=None)
    assert r.ATMOS_ON is True
    assert 0 < r.ATMOS_OPACITY <= 0.20, "haze must not fog the image"


def test_atmosphere_graph_wires_labels(monkeypatch):
    r = _reload(monkeypatch)
    g = r._atmosphere_graph("enh", "atmos", 12.0)
    assert "[enh]" in g and "[atmos]" in g and "blend=all_mode=screen" in g
