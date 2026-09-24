"""Storyboard generator: request shapes per the Higgsfield model docs, and the
failure paths. No network — every HTTP call is faked."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import hfgen  # noqa: E402


class R:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self._d


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id123:secret456")
    sent = []

    def post(url, json=None, headers=None, timeout=None):
        assert timeout, "every call needs a timeout"
        sent.append((url.rsplit("api.higgsfield.ai/", 1)[-1], json))
        if "soul" in url:
            return R({"status": "completed", "request_id": "s",
                      "images": [{"url": "https://img/x.png"}]})
        return R({"status": "completed", "request_id": "v",
                  "video": {"url": "https://vid/x.mp4"}})
    monkeypatch.setattr(hfgen.requests, "post", post)
    monkeypatch.setattr(hfgen, "_download", lambda u, o: o)
    monkeypatch.setattr(hfgen, "_normalise", lambda s, o, sec: o)
    return sent


def test_wan_is_vertical_silent_and_billed_for_its_own_length(api, tmp_path):
    assert hfgen.wan("a tent", 3.5, tmp_path / "a.mp4") is not None
    model, p = api[0]
    assert model == "alibaba/wan-3.0/text-to-video"
    assert p["aspect_ratio"] == "9:16" and p["generate_audio"] is False
    assert p["duration"] == 5 and 2 <= p["duration"] <= 30   # 3.5s + 1.5s handle


def test_kling_starts_from_a_vertical_soul_still(api, tmp_path):
    """Kling 2.5 text-to-video has no aspect_ratio; image-to-video follows the
    start frame. So the still must be 9:16 and must be what Kling receives."""
    assert hfgen.kling("a man", "he breathes", 3.5, tmp_path / "k.mp4", seed=7)
    (m1, still), (m2, vid) = api
    assert m1 == "higgsfield-ai/soul/standard" and still["aspect_ratio"] == "9:16"
    assert still["seed"] == 7
    assert m2 == "kling-video/v2.5-turbo/standard/image-to-video"
    assert vid["image_url"] == "https://img/x.png" and vid["duration"] in (5, 10)


def test_cast_description_and_seed_are_reused_for_the_same_person(api, tmp_path):
    cast = {"m": {"seed": 99, "look": "a man in a grey t-shirt"}}
    for i in range(2):
        hfgen.shot({"model": "kling", "who": "m", "seconds": 3.5,
                    "picture": f"pose {i}"}, cast, tmp_path / f"{i}.mp4")
    stills = [p for m, p in api if "soul" in m]
    assert all(s["seed"] == 99 and "grey t-shirt" in s["prompt"] for s in stills)


@pytest.mark.parametrize("status", ["failed", "nsfw", "canceled"])
def test_bad_outcomes_are_failures_not_results(monkeypatch, tmp_path, status):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id123:secret456")
    monkeypatch.setattr(hfgen.requests, "post",
                        lambda *a, **k: R({"status": status, "request_id": "r"}))
    assert hfgen.wan("x", 3, tmp_path / "x.mp4") is None


def test_http_errors_and_no_key_return_none(monkeypatch, tmp_path):
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.delenv("HF_KEY", raising=False)
    assert hfgen.wan("x", 3, tmp_path / "x.mp4") is None
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id123:secret456")
    monkeypatch.setattr(hfgen.requests, "post",
                        lambda *a, **k: R({"detail": "nope"}, 422))
    assert hfgen.wan("x", 3, tmp_path / "x.mp4") is None


def test_storyboards_are_well_formed():
    boards = json.loads((ROOT / "data" / "storyboards.json").read_text())
    for sid, b in boards.items():
        if sid.startswith("_"):
            continue
        for s in b["shots"]:
            assert s["model"] in ("kling", "wan")
            assert 2 <= s["seconds"] <= 10
            if s.get("who"):
                assert s["who"] in b["cast"], f"{sid}: unknown cast {s['who']}"
        total = sum(s["seconds"] for s in b["shots"])
        assert 28 <= total <= 42, f"{sid}: {total}s, target is 30-40"
