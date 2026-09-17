"""
Generated MOTION backgrounds (Kling 3.0 via the Higgsfield REST API).

This module spends real money on an endpoint whose pricing Higgsfield does not
publish, and it sits in the middle of the render path. So the tests here are
mostly about what it must REFUSE to do: never run unless switched on, never
outspend its cap, never hang, and never break a render when it fails.

Nothing here touches the network. Every HTTP call is faked.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import kling  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    kling.reset()
    monkeypatch.delenv("REEL_KLING_BG", raising=False)
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.delenv("HF_KEY", raising=False)
    yield
    kling.reset()


# --------------------------------------------------------- off by default

def test_off_by_default():
    assert kling.enabled() is False


def test_a_key_alone_does_not_switch_it_on(monkeypatch):
    """Adding the secret must not start billing. The flag is the switch."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id:secret")
    assert kling.enabled() is False


def test_the_flag_alone_does_not_switch_it_on(monkeypatch):
    monkeypatch.setenv("REEL_KLING_BG", "1")
    assert kling.enabled() is False


def test_both_together_switch_it_on(monkeypatch):
    monkeypatch.setenv("REEL_KLING_BG", "1")
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id:secret")
    assert kling.enabled() is True


def test_a_half_pasted_key_is_refused_not_sent(monkeypatch):
    """The API wants KEY_ID:KEY_SECRET. A key missing the secret half would
    otherwise fail as an opaque 401 in the middle of a render."""
    monkeypatch.setenv("REEL_KLING_BG", "1")
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "just_the_id")
    assert kling.api_key() == ""
    assert kling.enabled() is False


def test_disabled_fetch_returns_none_without_touching_the_network(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("network touched while disabled")
    monkeypatch.setattr(kling.requests, "post", explode)
    assert kling.fetch_clip("an empty chair", Path("/tmp/x.mp4")) is None


# ------------------------------------------------------- the request shape

def test_the_request_matches_the_model_schema():
    p = kling._payload("an empty chair by a rain-streaked window")
    assert p["aspect_ratio"] == "9:16", "portrait, or the Short is letterboxed"
    # The channel mixes its own voiceover and cinematic score; a generated
    # audio bed underneath them is noise we would have to strip out again.
    assert p["sound"] == "off"
    assert p["multi_shots"] is True
    assert 3 <= p["duration"] <= 15, "model bounds"
    assert 0 <= p["cfg_scale"] <= 1
    assert 1 <= len(p["multi_prompt"]) <= 6, "model allows at most 6 sub-shots"
    assert sum(s["duration"] for s in p["multi_prompt"]) == p["duration"]


def test_sub_prompt_length_respects_the_schema_limit():
    """multi_prompt[].prompt is maxLength 512. A long beat description plus the
    style block goes past that, and the API answers 422, not a video."""
    long_beat = "a name written on paper, hand still resting on it " * 20
    for shot in kling._payload(long_beat)["multi_prompt"]:
        assert len(shot["prompt"]) <= 512


def test_every_sub_shot_is_the_same_beat_from_a_different_angle():
    """doctrine 6: the picture follows the script's own image. Three shots of
    one beat, not three unrelated pictures."""
    beat = "a candle burning down to nothing"
    for shot in kling._payload(beat)["multi_prompt"]:
        assert beat in shot["prompt"]


def test_the_credential_is_sent_as_a_key_header(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id:secret")
    assert kling._headers()["Authorization"] == "Key id:secret"


# ------------------------------------------------------------- the spending

class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _wire(monkeypatch, tmp_path, submit=None):
    """Fake a completed generation end to end, counting submissions."""
    calls = {"submit": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["submit"] += 1
        assert timeout, "every network call needs a timeout"
        return _Resp(submit or {"status": "completed", "request_id": "r",
                                "video": {"url": "https://x/v.mp4"}})

    monkeypatch.setattr(kling.requests, "post", fake_post)
    monkeypatch.setattr(kling, "_download",
                        lambda url, out: (out.write_bytes(b"0" * 20_000), out)[1])
    monkeypatch.setattr(kling, "_cut",
                        lambda master, i, out: (out.write_bytes(b"0" * 20_000), out)[1])
    monkeypatch.setenv("REEL_KLING_BG", "1")
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id:secret")
    return calls


def test_one_request_per_beat_not_one_per_slot(monkeypatch, tmp_path):
    """The whole cost argument. daily_post asks for the same beat query in
    three consecutive slots; that must be ONE generation served three ways."""
    calls = _wire(monkeypatch, tmp_path)
    beat = "an empty chair by a rain-streaked window"
    for i in range(3):
        assert kling.fetch_clip(beat, tmp_path / f"s{i}.mp4") is not None
    assert calls["submit"] == 1


def test_a_four_beat_story_costs_four_requests(monkeypatch, tmp_path):
    calls = _wire(monkeypatch, tmp_path)
    beats = ["chair", "paper", "table", "candle"]
    for slot, beat in enumerate(b for b in beats for _ in range(3)):
        assert kling.fetch_clip(beat, tmp_path / f"s{slot}.mp4") is not None
    assert calls["submit"] == 4


def test_the_spend_cap_stops_a_runaway_loop(monkeypatch, tmp_path):
    """Pricing for this endpoint is not published, so a loop bug must not be
    able to bill repeatedly. Past the cap it fails closed to stock."""
    calls = _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(kling, "MAX_BEATS_PER_RUN", 4)
    for i in range(4):
        assert kling.fetch_clip(f"beat {i}", tmp_path / f"a{i}.mp4") is not None
    assert kling.fetch_clip("beat 5", tmp_path / "a5.mp4") is None
    assert calls["submit"] == 4


# ------------------------------------------------- it can never break a render

@pytest.mark.parametrize("boom", [
    ConnectionError("no route"),
    TimeoutError("queued forever"),
    ValueError("garbage json"),
])
def test_any_failure_falls_back_to_stock(monkeypatch, tmp_path, boom):
    _wire(monkeypatch, tmp_path)

    def fake_post(*a, **k):
        raise boom
    monkeypatch.setattr(kling.requests, "post", fake_post)
    assert kling.fetch_clip("a candle", tmp_path / "x.mp4") is None


def test_a_completed_response_with_no_video_is_a_failure(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          submit={"status": "completed", "request_id": "r"})
    assert kling.fetch_clip("a candle", tmp_path / "x.mp4") is None


def test_a_failed_generation_does_not_hang_waiting(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          submit={"status": "queued", "request_id": "r",
                  "status_url": "https://x/status"})
    monkeypatch.setattr(kling.requests, "get",
                        lambda url, headers=None, timeout=None: _Resp(
                            {"status": "failed", "error": "moderation"}))
    assert kling.fetch_clip("a candle", tmp_path / "x.mp4") is None


def test_polling_gives_up_at_the_deadline(monkeypatch, tmp_path):
    """A video model that queues forever is precisely the hazard that cost the
    channel five days (see src/proc.py). The wait must be bounded."""
    _wire(monkeypatch, tmp_path,
          submit={"status": "queued", "request_id": "r",
                  "status_url": "https://x/status"})
    monkeypatch.setattr(kling.requests, "get",
                        lambda url, headers=None, timeout=None: _Resp(
                            {"status": "in_progress"}))
    monkeypatch.setattr(kling, "POLL_EVERY", 0)
    monkeypatch.setattr(kling, "BEAT_DEADLINE", 0.05)
    assert kling.fetch_clip("a candle", tmp_path / "x.mp4") is None


def test_every_timeout_constant_is_finite():
    for name in ("SUBMIT_TIMEOUT", "POLL_TIMEOUT", "DOWNLOAD_TIMEOUT",
                 "BEAT_DEADLINE"):
        v = getattr(kling, name)
        assert 0 < v < 3600, f"{name}={v}"


# ------------------------------------------------------- wiring and secrets

def test_the_background_chain_tries_kling_before_stock():
    """Order inside fetch_background() is the source ranking. A generated
    still with a Ken Burns push is the thing generated motion replaces, so it
    must come first — and both must come before paying-nothing stock."""
    src = (ROOT / "src" / "backgrounds.py").read_text()
    body = src[src.index("def fetch_background("):]
    assert "import kling" in body
    assert body.index("import kling") < body.index("import imagegen"), (
        "generated motion must rank above generated stills")
    assert body.index("import kling") < body.index("_fetch_from_pixabay")


def test_the_workflow_passes_the_secret_but_never_a_literal():
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert "HIGGSFIELD_API_KEY: ${{ secrets.HIGGSFIELD_API_KEY }}" in wf
    assert wf.count("HIGGSFIELD_API_KEY: ${{ secrets.HIGGSFIELD_API_KEY }}") == 2


def test_no_higgsfield_credential_is_committed():
    """Never commit secrets. A KEY_ID:KEY_SECRET pair is easy to paste into a
    module while testing and impossible to unpublish."""
    import re
    for path in list((ROOT / "src").glob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        text = path.read_text()
        for line in text.splitlines():
            if "HIGGSFIELD_API_KEY" in line or "HF_KEY" in line:
                assert not re.search(r'=\s*["\'][A-Za-z0-9_-]{8,}:', line), (
                    f"{path.name}: looks like a hardcoded credential")
