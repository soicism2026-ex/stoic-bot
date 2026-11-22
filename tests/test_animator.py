"""Video backgrounds test (src/animator.py): no network, the API is mocked."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import animator  # noqa: E402
import painter  # noqa: E402


class Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._b, self.content = status, body or {}, content

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=0):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("REEL_STILL_CACHE", str(cache))
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "id:secret")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(animator, "POLL_EVERY", 0)
    animator.reset()
    painter.ANIMATED.clear()
    img = tmp_path / "still.png"
    img.write_bytes(b"png-bytes" * 10)
    calls = {"post": [], "put": 0, "get": 0}

    def post(url, json=None, headers=None, timeout=None):
        calls["post"].append((url, json, headers))
        if url.endswith("/files/generate-upload-url"):
            return Resp(body={"upload_url": "https://up/x", "public_url": "https://cdn/x.png",
                              "upload_headers": {"Content-Type": "image/png"}})
        return Resp(body={"status": "queued", "request_id": "r1",
                          "status_url": "https://api/requests/r1/status"})

    def put(url, data=None, headers=None, timeout=None):
        calls["put"] += 1
        return Resp()

    def get(url, headers=None, timeout=None, stream=False):
        if "status" in url:
            calls["get"] += 1
            return Resp(body={"status": "completed", "video": {"url": "https://cdn/v.mp4"}})
        return Resp(content=b"v" * 20_000)

    monkeypatch.setattr(animator.requests, "post", post)
    monkeypatch.setattr(animator.requests, "put", put)
    monkeypatch.setattr(animator.requests, "get", get)
    monkeypatch.setattr(animator, "_normalise", lambda raw, out: (out.write_bytes(raw.read_bytes()), out)[1])
    return img, calls, tmp_path


def test_request_shape(env):
    img, calls, tmp = env
    clip, how = animator.generate(img, "a marble bust at dawn", 7, tmp)
    assert how == "generated" and clip.exists()
    url, body, headers = calls["post"][1]
    assert url.endswith(animator.MODEL)
    assert set(body) == {"image_url", "prompt", "duration", "resolution", "generate_audio"}
    assert body["image_url"] == "https://cdn/x.png" and body["duration"] == 5 and body["generate_audio"] is False
    assert "a marble bust at dawn" in body["prompt"] and "oil painting stays an oil painting" in body["prompt"]
    assert "no text" in body["prompt"] and "no new people" in body["prompt"]
    assert headers["Authorization"] == "Key id:secret" and headers["Idempotency-Key"].startswith("vbg-")


def test_cache_means_no_second_generation(env):
    img, calls, tmp = env
    a, _ = animator.generate(img, "scene", 1, tmp)
    n = len(calls["post"])
    b, how = animator.generate(img, "scene", 1, tmp)
    assert how == "cache" and b == a and len(calls["post"]) == n
    animator.reset()                                # a new process (the live post) reuses it too
    assert animator.generate(img, "scene", 1, tmp)[1] == "cache"


def test_spend_cap_three_a_day(env):
    img, calls, tmp = env
    for i in range(3):
        assert animator.generate(img, f"scene {i}", i, tmp)[0]
    clip, why = animator.generate(img, "scene 9", 9, tmp)
    assert clip is None and "spend cap" in why
    assert animator.spent_today() == (3, 15.0)
    animator.reset()                                # a new job the same day: the ledger still says 3
    assert animator.generate(img, "scene 10", 10, tmp)[0] is None


def test_no_credits_keeps_stills_and_stops_the_run(env, monkeypatch, capsys):
    img, calls, tmp = env
    monkeypatch.setattr(animator.requests, "post",
                        lambda url, **k: Resp(403, {"detail": "Insufficient balance"})
                        if not url.endswith("upload-url") else Resp(body={"upload_url": "u", "public_url": "p"}))
    clip, why = animator.generate(img, "s1", 1, tmp)
    assert clip is None and why == "no Higgsfield credits: painted stills used"
    assert animator.generate(img, "s2", 2, tmp) == (None, why)       # no further calls this run


@pytest.mark.parametrize("failure", ["failed", "timeout", "nsfw"])
def test_failures_leave_the_still_and_never_raise(env, monkeypatch, failure):
    img, calls, tmp = env
    if failure == "timeout":
        monkeypatch.setattr(animator, "DEADLINE", -1)
    else:
        monkeypatch.setattr(animator.requests, "get",
                            lambda url, **k: Resp(body={"status": failure, "error": "x"}))
    clip, why = animator.generate(img, "s", 3, tmp)
    assert clip is None and why


def test_a_submit_is_never_retried(env, monkeypatch):
    img, calls, tmp = env
    import requests as rq
    seen = []

    def post(url, **k):
        seen.append(url)
        if url.endswith("upload-url"):
            return Resp(body={"upload_url": "u", "public_url": "p"})
        raise rq.ConnectionError("dropped after sending")
    monkeypatch.setattr(animator.requests, "post", post)
    assert animator.generate(img, "s", 4, tmp)[0] is None
    assert sum(1 for u in seen if u.endswith(animator.MODEL)) == 1


def test_date_window_and_one_short_a_day(env, monkeypatch):
    first, last = dt.date(2026, 11, 23), dt.date(2026, 12, 22)
    assert animator.in_window(first) and animator.in_window(last)
    assert not animator.in_window(dt.date(2026, 11, 22)) and not animator.in_window(dt.date(2026, 12, 23))
    monkeypatch.setattr(animator, "_test_running", lambda: True)
    monkeypatch.setattr(animator, "_rows", lambda p: [])
    assert animator.active(first) and animator.active(last)
    assert not animator.active(dt.date(2026, 12, 23))                     # off by itself
    day = first.isoformat()
    assert not animator.first_post_of_day(first, [{"date": day}])         # only the first post
    assert animator.first_post_of_day(first, [{"date": "2026-11-22"}])
    assert animator.already_done(first, [{"date": day, "clips_ok": "2"}])
    assert not animator.already_done(first, [{"date": day, "clips_ok": "0"}])


def test_off_without_the_ledger_test_the_key_or_the_switch(env, monkeypatch):
    monkeypatch.setattr(animator, "_rows", lambda p: [])
    d = dt.date(2026, 12, 1)
    monkeypatch.setattr(animator, "_test_running", lambda: False)
    assert not animator.active(d)
    monkeypatch.setattr(animator, "_test_running", lambda: True)
    monkeypatch.setenv("REEL_VIDEO_BG", "0")
    assert not animator.active(d)
    monkeypatch.delenv("REEL_VIDEO_BG")
    monkeypatch.delenv("HIGGSFIELD_API_KEY")
    monkeypatch.delenv("HF_KEY", raising=False)
    assert not animator.active(d)


def test_the_ledger_test_is_in_the_file_as_the_owner_approved_it():
    t = {x["id"]: x for x in json.loads((ROOT / "data/marketing_tests.json").read_text())["tests"]}["video-bg"]
    assert t["kind"] == "views_before_after" and t["status"] == "running" and t["ask"] == "video-storyboard"
    assert (t["started"], t["end"]) == ("2026-11-23", "2026-12-22") and "test cheapest for 1 month" in t["approved"]
    assert animator.WINDOW == (dt.date(2026, 11, 23), dt.date(2026, 12, 22))


def test_plan_is_the_hook_then_two_spread(env):
    assert animator.plan(8) == [0, 3, 5]
    assert animator.plan(1) == [0] and animator.plan(0) == []


def test_animate_slot_swaps_the_clip_and_marks_it(env, tmp_path):
    img, calls, tmp = env
    clip, _ = animator.generate(img, "s", 5, tmp)
    animator._CLIPS[3] = clip
    out = tmp_path / "x.bg3.mp4"
    out.write_bytes(b"painted")
    painter.SLOTS[3] = {"ok": True}
    assert animator.animate_slot(3, out) and 3 in painter.ANIMATED and painter.SLOTS[3]["animated"]
    assert out.read_bytes() != b"painted"
    assert not animator.animate_slot(4, tmp_path / "y.mp4")                # a failed shot stays painted


def test_record_writes_the_csv(env, monkeypatch, tmp_path):
    monkeypatch.setattr(animator, "CSV_PATH", tmp_path / "video_bg.csv")
    painter.ANIMATED.update({0, 3})
    animator._FAILS = 1
    animator.record("edit-7", "vid123", dt.date(2026, 11, 23))
    row = list(csv.DictReader(open(tmp_path / "video_bg.csv")))[0]
    assert row["date"] == "2026-11-23" and row["edit"] == "edit-7" and row["clips_ok"] == "2" and row["clips_failed"] == "1"
    painter.ANIMATED.clear()


def test_render_graph_gives_animated_shots_no_extra_move_and_a_held_last_frame(monkeypatch):
    """The painted shots keep their sub-pixel move; an animated one gets none
    and holds its last frame (tpad) instead of looping."""
    import tempfile
    sys.path.insert(0, str(ROOT / "tests"))
    import render
    import render_capture as rc
    from test_painter_render import _painted_graph
    base = _painted_graph(monkeypatch)
    assert "tpad=stop_mode=clone" not in base
    painter.ANIMATED.update({0, 3, 5})
    try:
        g = _painted_graph(monkeypatch)
    finally:
        painter.ANIMATED.clear()
    assert g.count("tpad=stop_mode=clone") == 3
    assert g.count("perspective=") == base.count("perspective=") - 3
