"""ElevenLabs is credited only when it really spoke.

posts.csv logs tts.LAST_VOICE_NAME, and the owner's voice decisions are read
off that column. A failed paid call (the key 401'd from July to October) used
to fall back to edge-tts INSIDE _synthesize_elevenlabs, so the free voice's
read was logged as "Brian". The edit-preview voice test relies on this too.
"""
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tts  # noqa: E402


class _Rejected:
    status_code = 401

    def raise_for_status(self):
        raise RuntimeError("401 Client Error: Unauthorized")


class _Spoke:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "audio_base64": base64.b64encode(b"ID3 not really audio").decode(),
            "alignment": {
                "characters": list("Hi you"),
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            },
        }


def _paid_voice_on(monkeypatch):
    """Paid voice switched on, every engine ahead of it off, and edge-tts
    replaced by a recorder so nothing touches the network."""
    monkeypatch.setattr(tts, "_CB_LOCAL", False)
    monkeypatch.setattr(tts, "_CB_TOKEN", "")
    monkeypatch.setattr(tts, "_EL_KEY", "test-key")
    monkeypatch.setattr(tts, "_EL_VOICE_ID", tts._EL_BRIAN_VOICE)
    monkeypatch.setattr(tts, "_el_budget_allows", lambda text: True)
    edge_calls = []

    def fake_edge(text, out_path, voice_id):
        edge_calls.append(voice_id)
        Path(out_path).write_bytes(b"x")
        return out_path, []

    monkeypatch.setattr(tts, "_synthesize_edge", fake_edge)
    return edge_calls


def test_a_rejected_key_is_credited_to_the_free_voice_not_brian(monkeypatch, tmp_path):
    edge_calls = _paid_voice_on(monkeypatch)
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _Rejected())
    tts.synthesize_voice("Hi you", tmp_path / "v.mp3")
    narrator = tts.VOICE_POOL[0]
    assert edge_calls == [narrator["id"]]          # the free voice read it, once
    assert tts.LAST_VOICE_NAME == narrator["name"]  # and gets the credit


def test_a_working_key_is_credited_to_brian(monkeypatch, tmp_path):
    edge_calls = _paid_voice_on(monkeypatch)
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _Spoke())
    monkeypatch.setattr(tts, "_audio_ok", lambda p: True)
    _, timings = tts.synthesize_voice("Hi you", tmp_path / "v.mp3")
    assert edge_calls == []
    assert tts.LAST_VOICE_NAME == "Brian"
    assert [w for w, *_ in timings] == ["Hi", "you"]   # real word timings


def test_brian_narrates_every_live_post():
    """Owner's pick by ear in the HQ, 2026-10-21: Brian (ElevenLabs) reads
    every post. The daily allocation must cover the daily cap plus a same-day
    backup render, or the second post (or a backup) airs in a second voice."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    el = int(re.search(r'ELEVENLABS_POSTS_PER_DAY:\s*"(\d+)"', wf).group(1))
    cap = int(re.search(r"MAX_POSTS_PER_DAY:\s*\$\{\{[^}]*'(\d+)'", wf).group(1))
    assert el >= cap + 1, (el, cap)
    # nothing ahead of ElevenLabs in the voice chain is switched on live
    assert "CHATTERBOX_LOCAL: ${{ vars.CHATTERBOX_LOCAL || '0' }}" in wf


def test_the_owners_clone_reads_when_brian_fails(monkeypatch, tmp_path):
    """Owner, 2026-10-21: a cloned voice of their own as Brian's backup."""
    edge_calls = _paid_voice_on(monkeypatch)
    monkeypatch.setattr(tts, "_EL_BACKUP_VOICE_ID", "clone123")
    monkeypatch.setattr(tts, "_EL_BACKUP_VOICE_NAME", "Owner clone")
    monkeypatch.setattr(tts, "_audio_ok", lambda p: True)
    asked = []

    def post(url, *a, **k):
        asked.append(url.split("/text-to-speech/")[1].split("/")[0])
        return _Rejected() if tts._EL_BRIAN_VOICE in url else _Spoke()
    monkeypatch.setattr(tts.requests, "post", post)
    tts.synthesize_voice("Hi you", tmp_path / "v.mp3")
    assert tts.LAST_VOICE_NAME == "Owner clone" and edge_calls == []
    assert asked[0] == tts._EL_BRIAN_VOICE and asked[-1] == "clone123"


def test_without_a_clone_brian_failing_goes_straight_to_the_free_voice(monkeypatch, tmp_path):
    edge_calls = _paid_voice_on(monkeypatch)
    monkeypatch.setattr(tts, "_EL_BACKUP_VOICE_ID", "")
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _Rejected())
    tts.synthesize_voice("Hi you", tmp_path / "v.mp3")
    assert tts.LAST_VOICE_NAME == tts.VOICE_POOL[0]["name"] and len(edge_calls) == 1
