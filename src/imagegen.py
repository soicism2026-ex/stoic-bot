"""
Text-to-image background generation — the PIVOT away from stock search.

Stock footage has a hard relevance ceiling (Pixabay ranks by popularity not
relevance; the library is finite). When REEL_IMAGE_BG=1 and OPENAI_API_KEY is
set, each background clip becomes an AI-generated cinematic STILL that depicts
the exact narration beat, animated with a slow Ken Burns push — far more
relevant and on-brand than any stock clip, at a per-image API cost.

DESIGN — safe by default:
  * OFF unless REEL_IMAGE_BG=1 AND an image API key is present.
  * Any failure (no key, API error, bad image) returns None, and the caller
    falls straight back to the normal stock -> synthetic chain. It can NEVER
    break a render.

Provider: OpenAI Images API (gpt-image-1) via OPENAI_API_KEY by default. Model
and style are env-tunable; other providers can be added behind the same
generate_clip() interface.

Cost note: ~$0.04-0.08 per image. At 6 clips x 3 posts/day that's ~$4-8/day if
every clip is generated; caching the recurring guide image and reusing it trims
that. Enable deliberately.
"""
import base64
import os
import subprocess
import sys
from pathlib import Path

import requests

# Appended to every prompt so generated stills share ONE cinematic identity —
# the channel's look, and (critically) NO on-screen text/watermarks that would
# fight the quote card and captions.
STYLE = os.environ.get(
    "REEL_IMAGE_STYLE",
    # NO NEGATION. Diffusion text encoders have no reliable mechanism for
    # "not": writing "NOT red, NOT magenta" puts those tokens in the prompt and
    # the model renders them anyway — measured, twice, on real Cloudflare
    # output (samples/frames, 2026-08-07). The fix is not a stronger denial, it
    # is to describe a PHYSICAL LIGHT SOURCE, because a named source implies
    # its own colour temperature and leaves the model nothing to invent.
    # "Dramatic chiaroscuro" plus "stoic marble bust" sits right on top of the
    # red/cyan gel-lit look that floods this aesthetic online, so the light has
    # to be specified or that association wins by default.
    #
    # Exposure is stated too: render.py applies its own darkening grade on top
    # (tuned for bright stock footage), so a still that arrives already crushed
    # comes out murky. Ask for controlled midtones; let the grade darken.
    "cinematic film still, lit by a single warm candle flame just out of "
    "frame, low golden lantern light, honey and amber tones on the lit side, "
    "soft neutral grey-blue shade on the unlit side, gentle light falloff "
    "into a dark neutral background, detail retained in the shadows rather "
    "than crushed to black, controlled midtones, shallow depth of field, "
    "subtle volumetric haze, photorealistic, shot on 35mm film, natural "
    "colour, muted and restrained palette.",
)
MODEL = os.environ.get("REEL_IMAGE_MODEL", "gpt-image-1")
_SIZE = os.environ.get("REEL_IMAGE_SIZE", "1024x1536")  # portrait ~2:3

# ---------------------------------------------------------------------------
# PROVIDER 1 — Cloudflare Workers AI (FLUX.1 [schnell]).
# The whole reason generated backgrounds can finally be turned on: Cloudflare's
# free allowance is 10,000 neurons/day and a schnell image costs roughly 43, so
# ~230 images/day are free. This channel needs 18 (6 clips x 3 posts). No
# watermark. OpenAI's gpt-image-1 does the same job at $22-43/month, so
# Cloudflare is tried FIRST and OpenAI only if its key happens to be present.
# ---------------------------------------------------------------------------
CF_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
CF_MODEL = os.environ.get("CLOUDFLARE_IMAGE_MODEL",
                          "@cf/black-forest-labs/flux-1-schnell")
# schnell is a distilled model: 4-8 steps is its whole design point.
CF_STEPS = int(os.environ.get("CLOUDFLARE_IMAGE_STEPS", "8"))
# schnell generates in ~1-2s, so 45s is already ten times generous. The old
# 180s was a latent job-killer: 6 images per render x 5 QA attempts = 30 calls,
# and at 180s each a hung provider would burn 90 minutes and blow past the
# job timeout — turning "the background API is slow" into "no post today".
CF_TIMEOUT = float(os.environ.get("CLOUDFLARE_IMAGE_TIMEOUT", "45"))

# Hard ceiling on generated images per process. The QA loop re-renders up to 5
# times and each render asks for 6 backgrounds, so an unlucky post can demand
# 30 generations — and the backup top-up wants more on top. That is slow enough
# to threaten the job timeout and wasteful enough to matter against a daily
# free allowance. Past the ceiling generate_clip() returns None, which is the
# module's normal "fall back to stock" path, so the post still ships.
MAX_IMAGES_PER_RUN = int(os.environ.get("REEL_IMAGE_MAX_PER_RUN", "12"))
_generated = 0


def cloudflare_ready() -> bool:
    return bool(CF_ACCOUNT and CF_TOKEN)


def enabled() -> bool:
    """True only when explicitly turned on AND some provider is configured."""
    on = os.environ.get("REEL_IMAGE_BG", "0") not in ("0", "false", "False")
    return on and (cloudflare_ready()
                   or bool(os.environ.get("OPENAI_API_KEY", "").strip()))


def _decode_cf_image(payload: dict) -> bytes | None:
    """Pull image bytes out of a Workers AI response.

    Kept tolerant on purpose: this repo's sandbox cannot reach Cloudflare to
    confirm the exact response shape, and Workers AI has returned the image
    under more than one key across models. Anything that base64-decodes to a
    plausible image is accepted; anything else returns None and the caller
    falls back, so a schema surprise costs a nicer background, never a post.
    """
    result = payload.get("result")
    if isinstance(result, str):
        candidate = result
    elif isinstance(result, dict):
        candidate = (result.get("image") or result.get("images", [None])[0]
                     if result.get("images") else result.get("image"))
    else:
        candidate = None
    if not candidate or not isinstance(candidate, str):
        return None
    try:
        raw = base64.b64decode(candidate, validate=False)
    except Exception:  # noqa: BLE001
        return None
    return raw if len(raw) > 1000 else None


def _generate_image_cloudflare(prompt: str, out_png: Path,
                               seed: int | None = None) -> bool:
    full = f"{prompt}. {STYLE}"
    url = (f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}"
           f"/ai/run/{CF_MODEL}")
    body: dict = {"prompt": full, "steps": CF_STEPS}
    if seed is not None:
        body["seed"] = int(seed)

    resp = requests.post(url, headers={"Authorization": f"Bearer {CF_TOKEN}"},
                         json=body, timeout=CF_TIMEOUT)
    if resp.status_code == 400:
        # Some Workers AI models reject extra params. Retry with the minimum
        # the API is documented to always accept rather than losing the image.
        resp = requests.post(url, headers={"Authorization": f"Bearer {CF_TOKEN}"},
                             json={"prompt": full}, timeout=CF_TIMEOUT)
    resp.raise_for_status()

    payload = resp.json()
    if not payload.get("success", True):
        errs = payload.get("errors") or []
        raise RuntimeError(f"Workers AI refused the request: {str(errs)[:200]}")

    raw = _decode_cf_image(payload)
    if raw is None:
        raise RuntimeError(
            f"unrecognised Workers AI response shape: "
            f"{str(payload)[:200]}")
    out_png.write_bytes(raw)
    return out_png.exists() and out_png.stat().st_size > 1000


def _generate_image(prompt: str, out_png: Path, seed: int | None = None) -> bool:
    """Try Cloudflare (free) first, then OpenAI (paid) if a key exists."""
    if cloudflare_ready():
        try:
            if _generate_image_cloudflare(prompt, out_png, seed=seed):
                print(f"[imagegen] SOURCE=CLOUDFLARE_FLUX seed={seed}", flush=True)
                return True
        except Exception as e:  # noqa: BLE001
            print(f"[imagegen] Cloudflare failed ({e}); trying next provider",
                  file=sys.stderr, flush=True)
    if os.environ.get("OPENAI_API_KEY", "").strip():
        if _generate_image_openai(prompt, out_png):
            print("[imagegen] SOURCE=OPENAI", flush=True)
            return True
    return False


def _generate_image_openai(prompt: str, out_png: Path) -> bool:
    key = os.environ["OPENAI_API_KEY"].strip()
    full = f"{prompt}. {STYLE}"
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": MODEL, "prompt": full, "size": _SIZE, "n": 1},
        timeout=180,
    )
    resp.raise_for_status()
    d = resp.json()["data"][0]
    if d.get("b64_json"):
        out_png.write_bytes(base64.b64decode(d["b64_json"]))
    elif d.get("url"):
        img = requests.get(d["url"], timeout=180)
        img.raise_for_status()
        out_png.write_bytes(img.content)
    else:
        return False
    return out_png.exists() and out_png.stat().st_size > 1000


def generate_clip(prompt: str, out_path: Path, dur: float = 6.5,
                  width: int = 1080, height: int = 1920,
                  seed: int | None = None) -> Path | None:
    """Generate a still for `prompt` and render it into a short MP4 with a slow
    Ken Burns push. Returns the clip path, or None on ANY failure (caller then
    falls back to stock).

    `seed` is what makes a RECURRING CHARACTER possible for free: pass the same
    seed and the same prompt and FLUX returns the same statue, every day. That
    is the thing the paid video tools were going to be bought for.

    Note on framing: FLUX schnell returns a square image, and the ffmpeg step
    below covers-and-crops it to 9:16, so the left and right thirds are lost.
    Prompts should therefore put the subject centred and compose vertically.
    """
    global _generated
    if not enabled():
        return None
    if _generated >= MAX_IMAGES_PER_RUN:
        print(f"[imagegen] budget reached ({MAX_IMAGES_PER_RUN} images this "
              f"run); using stock for the rest", flush=True)
        return None
    try:
        png = out_path.with_suffix(".gen.png")
        _generated += 1
        if not _generate_image(prompt, png, seed=seed):
            return None
        # Still -> looping clip with a gentle push-in so a single frame doesn't
        # read as frozen. (render.py layers its own grade/motion on top.)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", f"{dur:.1f}",
             "-vf",
             f"scale={width}:{height}:force_original_aspect_ratio=increase,"
             f"crop={width}:{height},"
             f"zoompan=z='min(1.0+0.0006*on,1.12)':d=1:"
             f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
             str(out_path)],
            check=True, capture_output=True,
        )
        png.unlink(missing_ok=True)
        if out_path.exists() and out_path.stat().st_size > 10_000:
            print(f"[imagegen] generated clip for: {prompt[:50]}")
            return out_path
    except Exception as e:  # noqa: BLE001
        print(f"[imagegen] failed ({e}); falling back to stock", file=sys.stderr)
    return None
