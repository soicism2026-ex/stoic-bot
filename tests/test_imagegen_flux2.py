"""Painted stills from FLUX.2 [klein] on Cloudflare Workers AI (imagegen.generate_still).

This container cannot reach Cloudflare (no key), so the HTTP layer is mocked,
built from the published API (developers.cloudflare.com, Workers AI FLUX.2
changelog and pricing, 2026-11): multipart/form-data with prompt, width,
height and seed; base64 PNG in result.image; error 4006 when the free day's
10,000 neurons are used up."""
import base64
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import imagegen  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 4000
JPG = b"\xff\xd8\xff\xe0" + b"\1" * 4000
KLEIN = "@cf/black-forest-labs/flux-2-klein-4b"
SCHNELL = "@cf/black-forest-labs/flux-1-schnell"


class Resp:
    def __init__(self, payload=None, status=200, content=b"", ctype="application/json"):
        self._p, self.status_code, self.content = payload, status, content
        self.headers = {"Content-Type": ctype}

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p


def ok(raw=PNG):
    return Resp({"result": {"image": base64.b64encode(raw).decode()}, "success": True})


@pytest.fixture
def ig(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-secret-123")
    monkeypatch.setenv("REEL_STILL_CACHE", str(tmp_path / "cache"))
    for k in ("REEL_PAINT_MODELS", "REEL_PAINT_SIZE", "REEL_PAINT_MAX_PER_RUN",
              "REEL_PAINT_DAILY_NEURONS", "REEL_PAINT_GUIDANCE"):
        monkeypatch.delenv(k, raising=False)
    m = importlib.reload(imagegen)
    monkeypatch.setattr(m._time, "sleep", lambda s: None)
    return m


def test_costs_follow_the_published_prices(ig):
    assert ig.neuron_cost(KLEIN, 1024, 1920) == 208.4          # 8 tiles x 26.05
    assert ig.neuron_cost(SCHNELL, 1024, 1024) == 96.0         # 4 x 4.8 + 8 steps x 9.6
    assert ig.neuron_cost("@cf/black-forest-labs/flux-2-klein-9b", 1024, 1920) == 1545.46
    assert ig.neuron_cost("@cf/black-forest-labs/flux-2-dev", 1024, 1920) == 6000.0
    # the budget: two Shorts of 8 stills a day fit the free 10,000 twice over
    assert 16 * ig.neuron_cost(KLEIN, 1024, 1920) < 10_000 / 2
    assert 16 * ig.neuron_cost("@cf/black-forest-labs/flux-2-klein-9b", 1024, 1920) > 10_000


def test_portrait_size_is_asked_for_directly(ig, monkeypatch):
    assert ig.paint_size(KLEIN) == (1024, 1920)
    assert ig.paint_size(SCHNELL) == (1024, 1024)               # schnell takes no size
    monkeypatch.setenv("REEL_PAINT_SIZE", "1090x2000")
    assert ig.paint_size(KLEIN) == (1088, 1920)                 # multiples of 16, max 1920


def test_flux2_is_a_multipart_request(ig, monkeypatch):
    seen = {}

    def post(url, headers=None, files=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, files=files, json=json)
        return ok()

    monkeypatch.setattr(ig.requests, "post", post)
    got = ig.generate_still("a quay in the rain", seed=410170)
    assert got and got["model"] == KLEIN and not got["cached"]
    assert seen["url"].endswith("/accounts/acct123/ai/run/" + KLEIN)
    assert seen["headers"]["Authorization"] == "Bearer tok-secret-123"
    assert seen["json"] is None
    f = seen["files"]
    assert f["prompt"] == (None, "a quay in the rain")
    assert f["width"] == (None, "1024") and f["height"] == (None, "1920")
    assert f["seed"] == (None, "410170")
    assert "steps" not in f                                     # klein: fixed 4 steps


def test_raw_image_and_jpeg_responses_are_accepted(ig, monkeypatch):
    monkeypatch.setattr(ig.requests, "post", lambda *a, **k: Resp(None, content=JPG, ctype="image/jpeg"))
    got = ig.generate_still("x", seed=1)
    assert got and got["path"].endswith(".jpg")


def test_used_up_free_day_stops_every_further_call(ig, monkeypatch):
    calls = []

    def post(*a, **k):
        calls.append(1)
        return Resp({"success": False, "errors": [{"code": 4006, "message":
                     "you have used up your daily free allocation of 10,000 neurons"}]}, 429)

    monkeypatch.setattr(ig.requests, "post", post)
    assert ig.generate_still("a", seed=1) is None
    assert ig.generate_still("b", seed=2) is None
    assert len(calls) == 1 and ig.paint_stats()["exhausted"]


def test_a_failing_model_hands_over_to_schnell(ig, monkeypatch):
    calls = []

    def post(url, headers=None, files=None, json=None, timeout=None):
        calls.append(url.rsplit("/", 1)[-1])
        if files is not None:
            return Resp({"success": False, "errors": [{"code": 5006, "message": "bad input"}]}, 400)
        assert len(json["prompt"]) <= 2048
        return ok()

    monkeypatch.setattr(ig.requests, "post", post)
    got = ig.generate_still("p" * 3000, seed=3)
    assert got["model"] == SCHNELL
    assert calls == ["flux-2-klein-4b", "flux-1-schnell"]


def test_transient_errors_get_one_more_try(ig, monkeypatch):
    n = []

    def post(*a, **k):
        n.append(1)
        return Resp({"errors": [{"message": "busy"}]}, 503) if len(n) == 1 else ok()

    monkeypatch.setattr(ig.requests, "post", post)
    assert ig.generate_still("x", seed=1)["model"] == KLEIN and len(n) == 2


def test_timeouts_and_garbage_fall_back_to_stock(ig, monkeypatch):
    def boom(*a, **k):
        raise ig.requests.exceptions.Timeout("slow")

    monkeypatch.setattr(ig.requests, "post", boom)
    assert ig.generate_still("x", seed=1) is None
    monkeypatch.setattr(ig.requests, "post", lambda *a, **k: Resp({"result": {"weird": 1}}))
    assert ig.generate_still("y", seed=1) is None


def test_errors_never_print_the_key_or_account(ig, monkeypatch, capsys):
    monkeypatch.setattr(ig.requests, "post", lambda *a, **k: Resp(
        {"success": False, "errors": [{"message": "denied for acct123 tok-secret-123"}]}, 403))
    assert ig.generate_still("x", seed=1) is None
    out = capsys.readouterr()
    assert "tok-secret-123" not in out.out + out.err and "acct123" not in out.out + out.err


def test_cache_serves_the_rehearsals_still_to_the_live_run(ig, monkeypatch, tmp_path):
    monkeypatch.setattr(ig.requests, "post", lambda *a, **k: ok())
    first = ig.generate_still("scene", seed=7)
    cache = tmp_path / "cache"
    assert Path(first["path"]).parent == cache
    meta = json.loads((cache / f"{first['key']}.json").read_text())
    assert meta["model"] == KLEIN and meta["seed"] == 7 and meta["neurons"] == 208.4
    assert json.loads((cache / "neurons.json").read_text())["neurons"] == 208.4
    # a new process (the live run) with the same cache: no request at all
    ig2 = importlib.reload(imagegen)
    monkeypatch.setattr(ig2.requests, "post", lambda *a, **k: pytest.fail("asked again"))
    again = ig2.generate_still("scene", seed=7)
    assert again["cached"] and again["path"] == first["path"]


def test_cache_finds_a_still_painted_by_the_fallback_model(ig, monkeypatch, tmp_path):
    """The rehearsal fell back to schnell; the live run must air THAT picture,
    not paint a different one on klein."""
    raw = tmp_path / "cache"
    raw.mkdir(parents=True, exist_ok=True)
    k = ig.still_key(SCHNELL, "scene", 9, 1024, 1024)
    (raw / f"{k}.png").write_bytes(PNG)
    monkeypatch.setattr(ig.requests, "post", lambda *a, **k: pytest.fail("asked again"))
    got = ig.generate_still("scene", seed=9)
    assert got["model"] == SCHNELL and got["cached"]


def test_the_key_is_everything_that_decides_the_picture(ig):
    base = ig.still_key(KLEIN, "p", 1, 1024, 1920)
    assert base == ig.still_key(KLEIN, "p", 1, 1024, 1920)
    for other in (ig.still_key(SCHNELL, "p", 1, 1024, 1920), ig.still_key(KLEIN, "q", 1, 1024, 1920),
                  ig.still_key(KLEIN, "p", 2, 1024, 1920), ig.still_key(KLEIN, "p", 1, 1088, 1920)):
        assert other != base


def test_per_run_cap(ig, monkeypatch):
    monkeypatch.setenv("REEL_PAINT_MAX_PER_RUN", "2")
    monkeypatch.setattr(ig.requests, "post", lambda *a, **k: ok())
    assert ig.generate_still("a", 1) and ig.generate_still("b", 1)
    assert ig.generate_still("c", 1) is None


def test_daily_neuron_budget_from_the_ledger(ig, monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir(exist_ok=True)
    (cache / "neurons.json").write_text(json.dumps({"day": ig._today_utc(), "neurons": 7850}))
    asked = []

    def post(url, **k):
        asked.append(url.rsplit("/", 1)[-1])
        return ok()

    monkeypatch.setattr(ig.requests, "post", post)
    got = ig.generate_still("a", 1)              # klein (208) would pass 8000; schnell (96) fits
    assert got["model"] == SCHNELL and asked == ["flux-1-schnell"]
    assert ig.generate_still("b", 1) is None     # 7946 + 96 > 8000
    (cache / "neurons.json").write_text(json.dumps({"day": "2020-01-01", "neurons": 7999}))
    assert ig.neurons_spent_today(cache) == 0.0  # a new UTC day starts at zero


def test_no_key_no_request(monkeypatch, tmp_path):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("REEL_STILL_CACHE", str(tmp_path))
    m = importlib.reload(imagegen)
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("no key, no call"))
    assert m.generate_still("x", 1) is None


def test_old_stills_are_pruned_from_the_cache(ig, tmp_path):
    import os
    import time
    cache = tmp_path / "old"
    cache.mkdir()
    old, new = cache / "a.png", cache / "b.png"
    for f in (old, new, cache / "a.json", cache / "neurons.json"):
        f.write_bytes(PNG)
    past = time.time() - 30 * 86400
    for f in (old, cache / "a.json", cache / "neurons.json"):
        os.utime(f, (past, past))
    assert ig.prune_still_cache(cache, days=21) == 2
    assert new.exists() and (cache / "neurons.json").exists() and not old.exists()
