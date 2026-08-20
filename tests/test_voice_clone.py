"""Local voice cloning — the legal, free version of "a real person's voice".

The Replicate path already accepted a reference clip; the FREE local path did
not, so the self-hosted engine could only ever use Chatterbox's stock voice —
the one the owner rejected outright. That is why this whole engine sat disabled.

The reference is meant to be the OWNER'S OWN voice: same authenticity benefit,
no one else's likeness, monetisable, and impossible for a competitor to copy.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tts  # noqa: E402


def test_reference_defaults_into_the_repo():
    assert tts.CHATTERBOX_VOICE_FILE.endswith("assets/voice/reference.wav")


def test_no_reference_when_the_file_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CHATTERBOX_VOICE_FILE", str(tmp_path / "nope.wav"))
    assert tts._reference_clip() == ""


def test_a_truncated_recording_is_ignored(monkeypatch, tmp_path):
    """A half-uploaded file would clone noise into every post. Better to fall
    back to edge-tts than to ship a broken voice 3x a day."""
    p = tmp_path / "reference.wav"
    p.write_bytes(b"\0" * 500)
    monkeypatch.setattr(tts, "CHATTERBOX_VOICE_FILE", str(p))
    assert tts._reference_clip() == ""


def test_a_real_recording_is_used(monkeypatch, tmp_path):
    p = tmp_path / "reference.wav"
    p.write_bytes(b"\0" * 200_000)
    monkeypatch.setattr(tts, "CHATTERBOX_VOICE_FILE", str(p))
    assert tts._reference_clip() == str(p)


def test_local_path_passes_the_reference_to_the_model():
    """The bug this fixes: model.generate() was called with no audio_prompt, so
    the free path could never clone anything."""
    src = (ROOT / "src" / "tts.py").read_text()
    assert "audio_prompt_path" in src
    assert "**_clone_kwargs" in src, "reference never reaches model.generate()"


def test_cloning_is_optional():
    """No reference committed must still synthesize — just in the stock voice."""
    src = (ROOT / "src" / "tts.py").read_text()
    assert '{"audio_prompt_path": ref} if ref else {}' in src


def test_the_readme_steers_to_the_owners_own_voice():
    """Cloning a public figure is someone else's likeness: it risks the
    channel, cannot be monetised, and puts words in a real person's mouth."""
    rd = (ROOT / "assets" / "voice" / "README.md").read_text().lower()
    assert "your own voice" in rd
    assert "monetis" in rd or "monetiz" in rd
