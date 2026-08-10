"""Three-act format (owner's change, 2026-08-07).

"Can we wait until the story is said before showing the quote on screen? And
then after the quote is shown can we have a voice over of it as a lesson... I
have a hard time reading the quote while also listening to the dialogue."

Reading and listening compete for the same attention, so the quote card always
lost. The fix is structural:

    ACT 1  hook + story narrated, quote NOT on screen
    BEAT   quote appears, narration STOPS — silence to read it
    ACT 3  narration returns, speaks the quote aloud, lands the lesson
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import content  # noqa: E402
import tts  # noqa: E402


def _fake_engine(monkeypatch):
    """Stub the synthesiser: what is under test is the EDIT, not edge-tts."""
    def fake(text, out, voice_id=None):
        secs = max(1.0, len(text.split()) * 0.4)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", f"sine=f=200:d={secs}", "-c:a", "libmp3lame",
                        str(out)], check=True)
        w = text.split()
        step = secs / max(1, len(w))
        return out, [(x, i * step, (i + 1) * step) for i, x in enumerate(w)]
    monkeypatch.setattr(tts, "synthesize_voice", fake)


needs_ffmpeg = pytest.mark.skipif(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed")


# --------------------------------------------------------------- the content

def test_schema_requires_both_halves():
    src = (ROOT / "src" / "content.py").read_text()
    assert '"voiceover_story"' in src and '"voiceover_lesson"' in src


def test_single_script_is_split_rather_than_failing():
    """A model that returns the old shape, or a backup written before this
    change, must still post."""
    d = {"voiceover_text": "One. Two. Three. Four. Five."}
    content._repair_script_split(d)
    assert d["voiceover_story"] and d["voiceover_lesson"]
    assert d["voiceover_lesson"] == "Four. Five."


def test_existing_split_is_left_alone():
    d = {"voiceover_story": "S", "voiceover_lesson": "L", "voiceover_text": "x"}
    content._repair_script_split(d)
    assert (d["voiceover_story"], d["voiceover_lesson"]) == ("S", "L")


def test_split_survives_a_one_sentence_script():
    d = {"voiceover_text": "Only one sentence here"}
    content._repair_script_split(d)
    assert d["voiceover_story"] and d["voiceover_lesson"]


def test_split_handles_an_empty_script():
    d = {"voiceover_text": ""}
    content._repair_script_split(d)          # must not raise


# ----------------------------------------------------------------- the audio

@needs_ffmpeg
def test_narration_stops_for_the_reading_beat(tmp_path, monkeypatch):
    """The whole point. Measured on real samples, not asserted from config."""
    np = pytest.importorskip("numpy")
    _fake_engine(monkeypatch)
    out, timings, boundary = tts.synthesize_two_part(
        "Story sentence one. Story sentence two.",
        "Lesson sentence one. Lesson sentence two.",
        tmp_path / "v.mp3")
    sr = 44100
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "f32le",
                          "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)

    def rms(a, b):
        seg = x[int(a * sr):int(b * sr)]
        return float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0

    assert rms(0.2, boundary - 0.2) > 1e-3, "act 1 should be speaking"
    assert rms(boundary + 0.3, boundary + tts.READ_BEAT - 0.3) < 1e-3, \
        "the reading beat must be SILENT — this is the entire feature"
    after = boundary + tts.READ_BEAT
    assert rms(after + 0.3, after + 1.0) > 1e-3, "act 3 should be speaking"


@needs_ffmpeg
def test_boundary_is_where_the_story_ends(tmp_path, monkeypatch):
    _fake_engine(monkeypatch)
    _, _, boundary = tts.synthesize_two_part(
        "One two three four five six", "Lesson here", tmp_path / "v.mp3")
    assert 2.0 < boundary < 3.5, boundary       # 6 words * 0.4s


@needs_ffmpeg
def test_lesson_timings_are_offset_past_the_beat(tmp_path, monkeypatch):
    """Captions/callouts must still line up if they are switched back on."""
    _fake_engine(monkeypatch)
    _, timings, boundary = tts.synthesize_two_part(
        "Story words here", "Lesson words here", tmp_path / "v.mp3")
    late = [t for t in timings if t[1] >= boundary + tts.READ_BEAT - 0.01]
    assert late, "lesson timings were not shifted past the silence"


@needs_ffmpeg
def test_missing_half_falls_back_to_one_take(tmp_path, monkeypatch):
    """A degraded edit beats a failed post."""
    _fake_engine(monkeypatch)
    out, timings, boundary = tts.synthesize_two_part(
        "Only a story", "", tmp_path / "v.mp3")
    assert boundary == 0.0 and out.exists()


def test_read_beat_is_long_enough_to_read_but_not_a_stall():
    assert 1.5 <= tts.READ_BEAT <= 4.0


# ---------------------------------------------------------------- the render

def test_render_uses_the_boundary_when_given_one(monkeypatch):
    import importlib
    monkeypatch.setenv("REEL_QUOTE_APPEAR", "5.5")
    import render
    m = importlib.reload(render)
    assert m.QUOTE_APPEAR == 5.5
    monkeypatch.delenv("REEL_QUOTE_APPEAR")
    importlib.reload(render)


def test_render_falls_back_to_hook_handoff_when_unset(monkeypatch):
    import importlib
    monkeypatch.delenv("REEL_QUOTE_APPEAR", raising=False)
    import render
    m = importlib.reload(render)
    assert m.QUOTE_APPEAR == 0.0


def test_daily_post_passes_the_boundary_through():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert 'pack["REEL_QUOTE_APPEAR"]' in src
    assert "synthesize_two_part" in src
