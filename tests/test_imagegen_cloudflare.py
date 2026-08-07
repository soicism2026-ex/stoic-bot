"""Cloudflare Workers AI (FLUX.1 schnell) as the free background provider.

This sandbox cannot reach any cloudflare.com host — the network policy denies
it — so these tests mock the HTTP layer. That is also why the decoder is
written tolerantly: the exact Workers AI response shape could not be confirmed
first-hand, so anything unexpected must fall back to stock rather than break a
render. These tests pin that behaviour in both directions.
"""
import base64
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import imagegen  # noqa: E402

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 4000
B64 = base64.b64encode(FAKE_PNG).decode()


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def cf(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok123")
    monkeypatch.setenv("REEL_IMAGE_BG", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return importlib.reload(imagegen)


# --------------------------------------------------------------- enablement

def test_cloudflare_alone_enables_generation(cf):
    """Previously generation required OPENAI_API_KEY, so the free path could
    never switch on."""
    assert cf.cloudflare_ready() is True
    assert cf.enabled() is True


def test_disabled_without_the_master_switch(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setenv("REEL_IMAGE_BG", "0")
    m = importlib.reload(imagegen)
    assert m.enabled() is False


def test_disabled_with_no_provider_at_all(monkeypatch):
    for k in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REEL_IMAGE_BG", "1")
    m = importlib.reload(imagegen)
    assert m.enabled() is False


# ------------------------------------------------------------------ decoding

@pytest.mark.parametrize("payload", [
    {"result": {"image": B64}, "success": True},
    {"result": B64, "success": True},
    {"result": {"images": [B64]}, "success": True},
])
def test_decoder_accepts_known_response_shapes(cf, payload):
    assert cf._decode_cf_image(payload) == FAKE_PNG


@pytest.mark.parametrize("payload", [
    {"result": {}}, {"result": None}, {},
    {"result": {"image": "not base64 at all !!!"}},
    {"result": {"image": base64.b64encode(b"tiny").decode()}},   # too small
])
def test_decoder_rejects_junk(cf, payload):
    assert cf._decode_cf_image(payload) is None


# ------------------------------------------------------------------ requests

def test_sends_prompt_steps_and_seed(cf, tmp_path, monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update({"url": url, "headers": headers, "body": json})
        return FakeResp({"result": {"image": B64}, "success": True})

    monkeypatch.setattr(cf.requests, "post", fake_post)
    assert cf._generate_image_cloudflare("a statue", tmp_path / "o.png", seed=42)
    assert "acct123" in seen["url"] and "flux-1-schnell" in seen["url"]
    assert seen["headers"]["Authorization"] == "Bearer tok123"
    assert seen["body"]["seed"] == 42
    assert seen["body"]["steps"] == cf.CF_STEPS
    assert "a statue" in seen["body"]["prompt"]


def test_style_block_is_appended_to_every_prompt(cf, tmp_path, monkeypatch):
    """The style block carries the whole look — palette, light source,
    exposure. If it does not reach the model the backgrounds are unbranded."""
    seen = {}
    monkeypatch.setattr(cf.requests, "post",
                        lambda url, headers=None, json=None, timeout=None:
                        (seen.update(json), FakeResp({"result": {"image": B64}}))[1])
    cf._generate_image_cloudflare("a statue", tmp_path / "o.png")
    assert "35mm" in seen["prompt"], "style block did not reach the model"


def test_retries_without_extra_params_on_400(cf, tmp_path, monkeypatch):
    """Some Workers AI models reject extras; losing the image over a param
    would be silly."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return FakeResp({}, status=400)
        return FakeResp({"result": {"image": B64}, "success": True})

    monkeypatch.setattr(cf.requests, "post", fake_post)
    assert cf._generate_image_cloudflare("x", tmp_path / "o.png", seed=1)
    assert "steps" in calls[0] and "steps" not in calls[1]


def test_api_level_failure_raises(cf, tmp_path, monkeypatch):
    monkeypatch.setattr(cf.requests, "post",
                        lambda *a, **k: FakeResp(
                            {"success": False, "errors": [{"message": "no quota"}]}))
    with pytest.raises(RuntimeError, match="refused"):
        cf._generate_image_cloudflare("x", tmp_path / "o.png")


def test_unknown_shape_raises_rather_than_writing_garbage(cf, tmp_path, monkeypatch):
    monkeypatch.setattr(cf.requests, "post",
                        lambda *a, **k: FakeResp({"result": {"surprise": 1}}))
    with pytest.raises(RuntimeError, match="unrecognised"):
        cf._generate_image_cloudflare("x", tmp_path / "o.png")


# ------------------------------------------------------------ provider chain

def test_cloudflare_failure_never_breaks_the_render(cf, tmp_path, monkeypatch):
    """The contract for the whole module: any failure returns None so the
    caller falls back to stock."""
    monkeypatch.setattr(cf.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert cf.generate_clip("x", tmp_path / "o.mp4") is None


def test_falls_back_to_openai_when_cloudflare_fails(cf, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    m = importlib.reload(imagegen)
    monkeypatch.setattr(m.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    called = {}
    monkeypatch.setattr(m, "_generate_image_openai",
                        lambda p, o: called.setdefault("yes", True) or True)
    assert m._generate_image("x", tmp_path / "o.png") is True
    assert called.get("yes") is True


# --------------------------------------------------- the recurring character

def test_guide_slots_get_a_fixed_seed(monkeypatch, tmp_path):
    """Same seed + same prompt = the same statue daily. This is what replaces
    the paid video tool."""
    import backgrounds
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    seeds = {}

    def fake_clip(prompt, out, seed=None, **kw):
        seeds[kw.get("idx", len(seeds))] = seed
        return None

    monkeypatch.setattr(backgrounds, "_fetch_from_pixabay",
                        lambda *a, **k: tmp_path / "x.mp4")
    (tmp_path / "x.mp4").write_bytes(b"\0" * 5000)

    import imagegen as ig
    monkeypatch.setattr(ig, "generate_clip",
                        lambda prompt, out, seed=None, **kw: seeds.update(
                            {prompt: seed}) or None)

    backgrounds.fetch_background("discipline", tmp_path / "a.mp4", clip_idx=0)
    backgrounds.fetch_background("discipline", tmp_path / "b.mp4", clip_idx=2)
    vals = list(seeds.values())
    assert backgrounds.GUIDE_SEED in vals, "guide slot must pass the fixed seed"
    assert None in vals, "b-roll slots must stay unseeded so they vary"


# ----------------------------------------------------------------- budgeting

def test_generation_is_capped_per_run(cf, tmp_path, monkeypatch):
    """The QA loop can demand 30 images for one post. Unbounded, that
    threatens the job timeout and burns the daily free allowance; past the cap
    the module must fall back to stock rather than keep going."""
    monkeypatch.setattr(cf, "MAX_IMAGES_PER_RUN", 3)
    monkeypatch.setattr(cf, "_generated", 0)
    calls = {"n": 0}

    def fake_gen(prompt, png, seed=None):
        calls["n"] += 1
        return False          # forces the None path without touching ffmpeg

    monkeypatch.setattr(cf, "_generate_image", fake_gen)
    for _ in range(10):
        cf.generate_clip("x", tmp_path / "o.mp4")
    assert calls["n"] == 3, "budget must stop further provider calls"


def test_budget_exhaustion_returns_none_not_an_error(cf, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "MAX_IMAGES_PER_RUN", 0)
    assert cf.generate_clip("x", tmp_path / "o.mp4") is None


# ------------------------------------------------- palette / grade / bookends

def test_style_uses_no_colour_negation(cf):
    """Diffusion text encoders have no reliable "not". Naming forbidden
    colours put those tokens in the prompt and the model rendered them anyway
    — measured twice on real Cloudflare output. Colour must be fixed by
    describing a physical light source, never by denial."""
    s = cf.STYLE.lower()
    for banned in ("not red", "not magenta", "not purple", "not neon", "no red"):
        assert banned not in s, f"{banned!r} is negation — it backfires here"
    assert "candle" in s or "lantern" in s, "no physical light source named"
    assert "amber" in s or "honey" in s or "golden" in s


def test_guide_queries_name_a_light_source_not_a_style(cf):
    """'dramatic chiaroscuro' + marble bust lands on the red/cyan gel look."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    block = src.split("STATUE_GUIDE = [")[1].split("]")[0].lower()
    assert "chiaroscuro" not in block, "style word invites the wrong palette"
    assert any(w in block for w in ("candlelight", "lantern", "firelight",
                                    "window light"))


def test_style_asks_for_retained_shadow_detail(cf):
    """render.py darkens on top; a crushed still becomes murky."""
    assert "rather than crushed" in cf.STYLE.lower()


def test_closing_bookend_varies_the_shot_but_not_the_seed(monkeypatch, tmp_path):
    import backgrounds
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    seen = {}
    import imagegen as ig
    monkeypatch.setattr(ig, "generate_clip",
                        lambda prompt, out, seed=None, **kw:
                        seen.update({out.name: (prompt, seed)}) or None)
    monkeypatch.setattr(backgrounds, "_fetch_from_pixabay",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(backgrounds, "_fetch_from_pexels",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(backgrounds, "_fetch_synthetic",
                        lambda t, o: o if o.write_bytes(b"\0" * 5000) is None else o)
    backgrounds.fetch_background("discipline", tmp_path / "open.mp4", clip_idx=0)
    backgrounds.fetch_background("discipline", tmp_path / "close.mp4", clip_idx=5)
    (p_open, s_open) = seen["open.mp4"]
    (p_close, s_close) = seen["close.mp4"]
    assert s_open == s_close == backgrounds.GUIDE_SEED, "same statue"
    assert p_open != p_close, "identical prompt+seed gives an identical image"
    assert backgrounds.GUIDE_CLOSING_SHOT in p_close


def test_render_lifts_brightness_only_for_generated_backgrounds(monkeypatch):
    import render
    monkeypatch.setenv("REEL_IMAGE_BG", "1")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    importlib.reload(imagegen)
    assert render._generated_backgrounds_active() is True
    monkeypatch.setenv("REEL_IMAGE_BG", "0")
    importlib.reload(imagegen)
    assert render._generated_backgrounds_active() is False


def test_brightness_lift_is_smaller_than_the_darkening():
    """A lift bigger than the grade would wash the footage out instead."""
    import render
    assert 0 < render.GEN_BRIGHT_LIFT < min(abs(g[0]) for g in render._GRADES) + 0.05
