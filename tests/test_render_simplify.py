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


# ----------------------------------------------------- hook motion curve

def test_hook_uses_ease_out_not_smoothstep(monkeypatch):
    """Smoothstep eases IN, so it gave the hook the SLOWEST part of the move —
    measured at 2.6% of its zoom in the first second, which is invisible. QA
    scored pacing 3.5 and said "the candle flame barely moves"."""
    r = _reload(monkeypatch)
    hook = r._motion(0, 100)
    body = r._motion(2, 100)
    assert "(1-(1-" in hook, "hook is not front-loaded"
    assert "3-2*" in body, "body clips should keep smoothstep"


def test_hook_gets_a_bigger_push_than_body_clips(monkeypatch):
    r = _reload(monkeypatch)
    assert r.HOOK_MOTION_AMP > r.MOTION_AMP


def test_hook_moves_visibly_within_the_first_second(monkeypatch):
    """The scroll decision happens in ~1s. Anything under ~5% of zoom travel
    in that window reads as a frozen frame."""
    r = _reload(monkeypatch)
    frames = 100                      # ~3.3s clip at 30fps
    t = min(30 / frames, 1)           # one second in
    travel = r.HOOK_MOTION_AMP * (1 - (1 - t) ** 2)
    assert travel >= 0.05, f"only {travel:.3f} of zoom in the first second"


def test_quote_has_an_outline_not_a_backing_box(monkeypatch):
    """Generated backgrounds put a candle flame behind centre frame and the
    drop shadow alone lost the lower lines. An outline hugs the glyphs; a box
    would reintroduce the black-slab look just removed."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "borderw=3:bordercolor=black@0.55" in src
    assert "box=0:borderw=3" in src, "must not switch the quote to a filled box"


# --------------------------------------------------- generated-source grading

def test_generated_sources_skip_the_contrast_bump(monkeypatch):
    """increase_contrast deepens shadows — a fifth darkening pass on stills
    that already arrive dark and graded."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "if not _generated_backgrounds_active():" in src
    assert 'pre_parts.append("curves=preset=increase_contrast")' in src


def test_generated_curve_lifts_shadows_instead_of_crushing(monkeypatch):
    """The stock S-curve maps 0.22 -> 0.13, which crushes blacks. Measured on a
    dark test source the full stock stack produced mean luma 0.00 — every pixel
    black. The generated curve lifts that point instead."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "0.22/0.26" in src, "generated curve must lift, not crush"
    assert "gamma=1.10" in src, "generated tone must open midtones"
    # the stock crushing curve must still exist for real footage
    assert "0.22/0.13" in src


# ---------------------------------------------------------------- voice depth

def test_voice_depth_probes_the_real_sample_rate():
    """Hardcoding 44100 played Chatterbox's 24 kHz output 1.81x too fast — the
    chipmunk the owner heard. asetrate must come from the file."""
    # Strip comments first — the bug is documented in a comment there on
    # purpose, and matching prose would make this test fail on the explanation
    # rather than on the code.
    src = (ROOT / "src" / "tts.py").read_text()
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    assert "asetrate=44100*" not in code, "hardcoded rate is the chipmunk bug"
    assert "_sample_rate(audio_path)" in code


def test_sample_rate_probe_falls_back_safely(tmp_path):
    import tts
    assert tts._sample_rate(tmp_path / "missing.mp3") == 44100


def test_voice_depth_is_off_by_default():
    """REVERSED 2026-08-07. Two rounds of pitch manipulation produced a
    chipmunk and then a voice the owner still disliked. Processing cannot
    recast a performance — pick a voice that is already deep. The machinery
    stays correct and tested; it just does not run by default."""
    import tts
    assert tts.VOICE_DEPTH == 1.0


def test_voice_depth_still_works_when_asked_for(monkeypatch):
    """Kept alive for a chosen voice that needs a nudge."""
    import importlib, tts
    monkeypatch.setenv("REEL_VOICE_DEPTH", "0.9")
    m = importlib.reload(tts)
    assert m.VOICE_DEPTH == 0.9
    monkeypatch.delenv("REEL_VOICE_DEPTH")
    importlib.reload(tts)
