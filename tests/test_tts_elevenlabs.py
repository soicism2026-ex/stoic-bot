"""ElevenLabs is credited only when it really spoke.

posts.csv logs tts.LAST_VOICE_NAME, and the owner's voice decisions are read
off that column. A failed paid call (the key 401'd from July to October) used
to fall back to edge-tts INSIDE _synthesize_elevenlabs, so the free voice's
read was logged as "Brian". The edit-preview voice test relies on this too.
"""
import base64
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


def test_live_posts_still_never_use_the_paid_voice():
    """ElevenLabs stays off on the channel until the owner approves Brian by
    ear (decisions.md, 2026-10-20). Raising this is that approval's change."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert 'ELEVENLABS_POSTS_PER_DAY: "0"' in wf
