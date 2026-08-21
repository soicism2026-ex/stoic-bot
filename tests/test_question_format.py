"""F3 "THE QUESTION" — the owner picked this one out of the four.

One hard question, plain type, near-black, in SILENCE for two seconds, then
the voice answers. In a feed engineered to be loud, silence plus a direct
question is the pattern interrupt.

The two ways this fails silently: the silence not actually being silent (a
render that merely delays text over a normal audio track), and the hook being
spoken aloud while the viewer reads it — which destroys the pause the whole
format is built on.
"""
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import content  # noqa: E402
import tts  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed")


def _rotation(n=12):
    return [content._pick_format([0] * i) for i in range(n)]


# ----------------------------------------------------------- the rotation

def test_question_runs_alongside_the_control():
    """Concurrent control beats the blocked design in format_test.md: the same
    week, weekday and algorithm mood hit both arms."""
    r = _rotation()
    c = Counter(r)
    assert c["question"] > 0
    assert set(r) - {"question"}, "control formats were replaced, not kept"


def test_question_is_roughly_every_third_post():
    r = _rotation(12)
    assert 3 <= r.count("question") <= 5, r


def test_no_format_repeats_back_to_back():
    r = _rotation(18)
    assert not [a for a, b in zip(r, r[1:]) if a == b]


# --------------------------------------------------------- the instructions

def test_hook_must_be_the_question_alone():
    assert 'FORMAT "question" rules' in content.SYSTEM
    assert "ending in a question mark" in content.SYSTEM


def test_question_must_not_give_away_the_answer():
    """If the viewer can guess where it lands, the silence is dead air."""
    assert "must NOT contain the answer" in content.SYSTEM


def test_answer_comes_immediately_after_the_silence():
    """They have already waited two seconds; do not make them wait longer."""
    assert "ANSWERING the question directly in the first" in content.SYSTEM


# ------------------------------------------------------------- the audio

@needs_ffmpeg
def test_the_silence_is_real(tmp_path, monkeypatch):
    """Measured on decoded samples. A render that merely delays the text over
    a normal audio track would pass any config-level check and fail here."""
    np = pytest.importorskip("numpy")

    def fake(text, out, voice_id=None):
        secs = max(1.0, len(text.split()) * 0.4)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", f"sine=f=200:d={secs}", "-c:a", "libmp3lame",
                        str(out)], check=True)
        w = text.split()
        step = secs / max(1, len(w))
        return out, [(x, i * step, (i + 1) * step) for i, x in enumerate(w)]
    monkeypatch.setattr(tts, "synthesize_voice", fake)

    lead = 2.0
    out, timings, boundary = tts.synthesize_two_part(
        "Answer first. Then the scene.", "Quote here. The turn.",
        tmp_path / "q.mp3", lead_silence=lead)
    sr = 44100
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "f32le",
                          "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)

    def rms(a, b):
        seg = x[int(a * sr):int(b * sr)]
        return float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0

    assert rms(0.1, lead - 0.1) < 1e-3, "the lead is not silent"
    assert rms(lead + 0.3, boundary - 0.3) > 1e-3, "the answer never arrives"


@needs_ffmpeg
def test_timings_shift_past_the_lead(tmp_path, monkeypatch):
    def fake(text, out, voice_id=None):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "sine=f=200:d=2", "-c:a", "libmp3lame", str(out)],
                       check=True)
        w = text.split()
        return out, [(x, i * 0.2, i * 0.2 + 0.2) for i, x in enumerate(w)]
    monkeypatch.setattr(tts, "synthesize_voice", fake)
    _, timings, _ = tts.synthesize_two_part("a b c", "d e f",
                                            tmp_path / "q.mp3", lead_silence=2.0)
    assert min(t[1] for t in timings) >= 1.99, "timings ignore the lead silence"


def test_zero_lead_is_the_default():
    """Every other format must be untouched by this."""
    import inspect
    sig = inspect.signature(tts.synthesize_two_part)
    assert sig.parameters["lead_silence"].default == 0.0


# --------------------------------------------------------------- the wiring

def test_hook_is_not_spoken_for_the_question_format():
    """Reading the question aloud while the viewer reads it destroys the pause
    the format exists for."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "is_question" in src
    assert 'act1 = content["voiceover_story"]' in src


def test_question_posts_are_tagged_for_the_test():
    """Untagged, the test would run and be unmeasurable."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert 'exp_name = "ftest:the_question"' in src


def test_the_cinematic_defaults_are_turned_off():
    """Motion, atmosphere, captions and the hook sound all work against a
    still, silent, near-black first frame."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    block = src.split('"question": {')[1].split("}")[0]
    for off in ('"REEL_MOTION": "0"', '"REEL_ATMOSPHERE": "0"',
                '"REEL_CAPTIONS": "0"', '"REEL_HOOK_SOUND": "0"'):
        assert off in block, f"{off} missing — the interrupt is diluted"


def test_hook_holds_through_the_whole_silence():
    """If it vanishes at the default 2.2s the viewer may never finish reading."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "QUESTION_LEAD_SILENCE + 1.4" in src
