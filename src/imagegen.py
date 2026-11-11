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
import proc
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
# (prompt, seed) -> the still already generated this run. The QA loop re-renders
# up to five times and asks for every background again; without this each
# retry re-spent the budget and later attempts silently fell back to stock.
_CACHE: dict = {}


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
    if _generated >= MAX_IMAGES_PER_RUN and (prompt, seed) not in _CACHE:
        print(f"[imagegen] budget reached ({MAX_IMAGES_PER_RUN} images this "
              f"run); using stock for the rest", flush=True)
        return None
    try:
        png = out_path.with_suffix(".gen.png")
        cached = _CACHE.get((prompt, seed))
        if cached is not None and Path(cached).exists():
            import shutil
            shutil.copyfile(cached, png)
            print(f"[imagegen] reused still for: {prompt[:50]}", flush=True)
        else:
            _generated += 1
            if not _generate_image(prompt, png, seed=seed):
                return None
            keep = png.with_name(png.stem + ".keep.png")
            import shutil
            shutil.copyfile(png, keep)
            _CACHE[(prompt, seed)] = keep
        # Still -> looping clip with a gentle push-in so a single frame doesn't
        # read as frozen. (render.py layers its own grade/motion on top.)
        proc.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", f"{dur:.1f}",
             "-vf",
             f"scale={width}:{height}:force_original_aspect_ratio=increase,"
             # NO ZOOM. Owner, 2026-10-01: "I dont like the shaking images
             # remove that." zoompan moves in whole-pixel steps, so a slow push
             # on a still visibly judders, and render.py stacked a second one.
             f"crop={width}:{height},fps=30",
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


# ===========================================================================
# PAINTED STILLS (REEL_PICTURE=painted; src/painter.py builds the prompts).
#
# Model: FLUX.2 [klein] 4B on Cloudflare Workers AI, free tier. Chosen on the
# published neuron prices (developers.cloudflare.com/workers-ai/platform/
# pricing, 2026-11) against the free 10,000 neurons/day, which everything on
# the account shares:
#
#   model            price                                  one 1024x1920 still
#   flux-2-klein-4b  26.05 / output 512x512 tile (4 steps)  8 tiles = ~208
#   flux-2-klein-9b  1363.64 first MP + 181.82 each next MP ~1,545
#   flux-2-dev       37.5 / output tile / step              8 x 20 x 37.5 = 6,000
#   flux-1-schnell   4.8 / tile + 9.6 / step (1024x1024)    4 x 4.8 + 8 x 9.6 = 96
#
# A Short is 8 stills: ~1,670 neurons on klein-4b, ~3,300 a day for two
# Shorts when the rehearsal's stills are reused by the live post (the
# REEL_STILL_CACHE below), ~6,700 if nothing were reused. klein-9b would be
# ~12,400 for ONE Short: past the whole free day. dev is out of reach.
#
# API (Workers AI REST): FLUX.2 takes multipart/form-data even for a prompt
# alone: prompt, width, height (256-1920; multiples of 16 here), seed,
# optional guidance; steps are fixed at 4 on klein. The image comes back as
# base64 in result.image. Portrait is asked for directly (1024x1920, the
# largest ~9:16 within 8 tiles), then cover-scaled 5% to 1080x1920.
# flux-1-schnell (JSON body, square only) is the fallback; then stock.
# ===========================================================================
import hashlib as _hashlib
import json as _json
import threading as _threading
import time as _time

PAINT_MODELS_DEFAULT = ("@cf/black-forest-labs/flux-2-klein-4b",
                        "@cf/black-forest-labs/flux-1-schnell")
# Multipart (FLUX.2) vs JSON (FLUX.1) request bodies.
_MULTIPART = ("flux-2-",)
# Retries for one model before the next model in the chain is tried.
_PAINT_TRIES = 2


class CloudflareBudgetExhausted(RuntimeError):
    """Workers AI refused for the day's free allocation (error 4006)."""


class _Transient(RuntimeError):
    """Worth one more try on the same model (rate limit, 5xx, timeout)."""


_PAINT_LOCK = _threading.Lock()
_PAINT_MEMO: dict = {}           # (prompt, seed) -> result dict, this process
_PAINT_STATE = {"generated": 0, "neurons": 0.0, "exhausted": False}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def paint_models() -> list[str]:
    """The model chain, best first: REEL_PAINT_MODELS (comma separated, short
    names allowed), else klein-4b then schnell."""
    raw = os.environ.get("REEL_PAINT_MODELS", "").strip()
    names = [m.strip() for m in raw.split(",") if m.strip()] or list(PAINT_MODELS_DEFAULT)
    return [m if m.startswith("@cf/") else f"@cf/black-forest-labs/{m}" for m in names]


def paint_size(model: str) -> tuple[int, int]:
    """Requested size for a model. FLUX.1 schnell takes no size (square)."""
    if not any(k in model for k in _MULTIPART):
        return 1024, 1024
    raw = os.environ.get("REEL_PAINT_SIZE", "1024x1920").lower().replace(" ", "")
    try:
        w, h = (int(x) for x in raw.split("x"))
    except ValueError:
        w, h = 1024, 1920
    w = max(256, min(1920, w - w % 16))
    h = max(256, min(1920, h - h % 16))
    return w, h


def neuron_cost(model: str, w: int, h: int, steps: int | None = None) -> float:
    """Published Workers AI price of one image (neurons), counted the
    conservative way: a started 512x512 tile is a whole tile."""
    import math as _m
    tiles = _m.ceil(w / 512) * _m.ceil(h / 512)
    name = model.split("/")[-1]
    if name == "flux-2-klein-4b":
        return round(26.05 * tiles, 2)
    if name == "flux-2-klein-9b":
        mp = _m.ceil(w * h / (1024 * 1024))
        return round(1363.64 + 181.82 * max(0, mp - 1), 2)
    if name == "flux-2-dev":
        return round(37.5 * tiles * (steps or _env_int("REEL_PAINT_DEV_STEPS", 20)), 2)
    if name == "flux-1-schnell":
        return round(4.8 * tiles + 9.6 * (steps or CF_STEPS), 2)
    return 500.0      # unknown model: assume dear, so the budget guard bites


def still_cache_dir() -> Path | None:
    """REEL_STILL_CACHE (a directory; relative = from the repo root). The
    workflows back it with actions/cache, so the rehearsal's stills are what
    the live post airs: half the neurons, and the owner sees what will air."""
    raw = os.environ.get("REEL_STILL_CACHE", "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    if str(p) not in _PRUNED:
        _PRUNED.add(str(p))
        prune_still_cache(p)
    return p


_PRUNED: set = set()


def prune_still_cache(cache: Path, days: float | None = None) -> int:
    """Delete stills older than REEL_STILL_CACHE_DAYS (21): the cache is
    restored and saved again by every run, so without this it only grows.
    A rehearsal's still is used within a day or two of being painted."""
    if days is None:
        try:
            days = float(os.environ.get("REEL_STILL_CACHE_DAYS", "21") or 21)
        except ValueError:
            days = 21.0
    cutoff = _time.time() - days * 86400
    n = 0
    for f in cache.iterdir():
        if f.name == "neurons.json" or f.suffix not in (".png", ".jpg", ".webp", ".json", ".tmp"):
            continue
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            continue
    return n


def still_key(model: str, prompt: str, seed, w: int, h: int) -> str:
    """Cache key: a hash of everything that decides the picture."""
    blob = _json.dumps({"model": model, "prompt": prompt, "seed": seed,
                        "w": int(w), "h": int(h)}, sort_keys=True)
    return _hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _image_ext(raw: bytes) -> str | None:
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if raw[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return None


def _valid_image(raw: bytes | None) -> bool:
    return bool(raw) and len(raw) > 1000 and _image_ext(raw) is not None


def _cache_lookup(cache: Path, key: str) -> Path | None:
    for ext in (".png", ".jpg", ".webp"):
        p = cache / f"{key}{ext}"
        try:
            if p.exists() and p.stat().st_size > 1000 and _image_ext(p.read_bytes()[:12]):
                return p
        except OSError:
            continue
    return None


def _cache_store(cache: Path, key: str, raw: bytes, meta: dict) -> Path:
    ext = _image_ext(raw) or ".png"
    final = cache / f"{key}{ext}"
    tmp = cache / f".{key}.{os.getpid()}.{_threading.get_ident()}.tmp"
    tmp.write_bytes(raw)
    os.replace(tmp, final)            # atomic: a reader never sees half a file
    try:
        (cache / f"{key}.json").write_text(_json.dumps(meta, indent=1), encoding="utf-8")
    except OSError:
        pass
    return final


def _ledger_path(cache: Path | None) -> Path | None:
    return (cache / "neurons.json") if cache else None


def _today_utc() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def neurons_spent_today(cache: Path | None = None) -> float:
    """Neurons this bot spent today (UTC, when Cloudflare's free day resets),
    from the ledger kept in the still cache. Approximate across jobs: each
    job restores its own copy of the cache."""
    lp = _ledger_path(cache if cache is not None else still_cache_dir())
    spent = 0.0
    if lp and lp.exists():
        try:
            d = _json.loads(lp.read_text(encoding="utf-8"))
            if d.get("day") == _today_utc():
                spent = float(d.get("neurons", 0.0))
        except Exception:  # noqa: BLE001
            spent = 0.0
    return max(spent, 0.0)


def _ledger_add(cache: Path | None, neurons: float) -> None:
    lp = _ledger_path(cache)
    if not lp:
        return
    try:
        spent = neurons_spent_today(cache) + neurons
        lp.write_text(_json.dumps({"day": _today_utc(), "neurons": round(spent, 2)}),
                      encoding="utf-8")
    except OSError:
        pass


def _scrub(text: str) -> str:
    """Error text without the account id (the token never reaches a URL)."""
    s = str(text)
    if CF_ACCOUNT:
        s = s.replace(CF_ACCOUNT, "<account>")
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if tok:
        s = s.replace(tok, "<token>")
    return s[:240]


def _cf_url(model: str) -> str:
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip() or CF_ACCOUNT
    return f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}"


def _cf_headers() -> dict:
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() or CF_TOKEN
    return {"Authorization": f"Bearer {tok}"}


def _cf_errors(payload) -> tuple[list, str]:
    errs = (payload or {}).get("errors") or [] if isinstance(payload, dict) else []
    text = "; ".join(f"{e.get('code', '')} {e.get('message', '')}".strip()
                     if isinstance(e, dict) else str(e) for e in errs)
    return errs, text


def _cf_image_from(resp) -> bytes:
    """Image bytes from a Workers AI response, or a classified exception."""
    status = getattr(resp, "status_code", 200)
    ctype = ""
    try:
        ctype = (resp.headers or {}).get("Content-Type", "") or ""
    except Exception:  # noqa: BLE001
        ctype = ""
    if status < 400 and ctype.startswith("image/"):
        raw = resp.content
        if _valid_image(raw):
            return raw
        raise RuntimeError("Workers AI returned an empty or unreadable image")
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        payload = None
    errs, text = _cf_errors(payload)
    codes = {str(e.get("code")) for e in errs if isinstance(e, dict)}
    low = text.lower()
    if "4006" in codes or "daily free allocation" in low or (
            "neurons" in low and ("allocation" in low or "exceeded" in low)):
        raise CloudflareBudgetExhausted(_scrub(text or f"HTTP {status}"))
    if status == 429 or status >= 500:
        raise _Transient(_scrub(f"HTTP {status} {text}"))
    if status >= 400 or (isinstance(payload, dict) and payload.get("success") is False):
        raise RuntimeError(_scrub(f"HTTP {status} {text or 'refused'}"))
    if not isinstance(payload, dict):
        raise RuntimeError("unrecognised Workers AI response (not JSON)")
    raw = _decode_cf_image(payload)
    if not _valid_image(raw):
        raise RuntimeError(_scrub(f"unrecognised Workers AI response shape: {str(payload)[:120]}"))
    return raw


def _cf_run(model: str, prompt: str, w: int, h: int, seed) -> bytes:
    """ONE Workers AI image request. Raises on any failure (classified)."""
    timeout = float(os.environ.get("REEL_PAINT_TIMEOUT", "75") or 75)
    try:
        if any(k in model for k in _MULTIPART):
            fields = {"prompt": (None, prompt), "width": (None, str(w)),
                      "height": (None, str(h))}
            if seed is not None:
                fields["seed"] = (None, str(int(seed)))
            g = os.environ.get("REEL_PAINT_GUIDANCE", "").strip()
            if g:
                fields["guidance"] = (None, g)
            if model.endswith("flux-2-dev"):
                fields["steps"] = (None, str(_env_int("REEL_PAINT_DEV_STEPS", 20)))
            resp = requests.post(_cf_url(model), headers=_cf_headers(), files=fields,
                                 timeout=timeout)
        else:
            body = {"prompt": prompt[:2048], "steps": CF_STEPS}
            if seed is not None:
                body["seed"] = int(seed)
            resp = requests.post(_cf_url(model), headers=_cf_headers(), json=body,
                                 timeout=timeout)
            if getattr(resp, "status_code", 200) == 400:
                # schnell's schema lists only prompt and steps
                resp = requests.post(_cf_url(model), headers=_cf_headers(),
                                     json={"prompt": prompt[:2048]}, timeout=timeout)
    except requests.exceptions.Timeout as e:
        raise _Transient(f"timed out after {timeout:.0f}s") from e
    except requests.exceptions.ConnectionError as e:
        raise _Transient(_scrub(f"connection failed: {e}")) from e
    return _cf_image_from(resp)


def paint_stats() -> dict:
    """This process's painting so far: images generated, neurons spent."""
    return dict(_PAINT_STATE)


def generate_still(prompt: str, seed=None) -> dict | None:
    """A painted still for `prompt`: {path, model, cached, neurons, key}, or
    None (the caller falls back to stock for that shot). Never raises.

    Order: this process's memo -> the still cache for EVERY model in the chain
    (so the live post airs exactly what the rehearsal painted, whichever
    model painted it) -> generate along the chain, within the per-run cap and
    the day's neuron budget. Cloudflare's own "daily allocation used up"
    stops all further calls this run.
    """
    try:
        return _generate_still(prompt, seed)
    except Exception as e:  # noqa: BLE001
        print(f"[imagegen] painted still failed ({_scrub(e)}); stock for this shot",
              file=sys.stderr, flush=True)
        return None


def _generate_still(prompt: str, seed) -> dict | None:
    memo_key = (prompt, seed)
    with _PAINT_LOCK:
        if memo_key in _PAINT_MEMO and Path(_PAINT_MEMO[memo_key]["path"]).exists():
            return dict(_PAINT_MEMO[memo_key], cached=True, neurons=0.0)
    cache = still_cache_dir()
    chain = paint_models()
    if cache:
        for model in chain:
            w, h = paint_size(model)
            k = still_key(model, prompt, seed, w, h)
            hit = _cache_lookup(cache, k)
            if hit:
                res = {"path": str(hit), "model": model, "cached": True,
                       "neurons": 0.0, "key": k}
                with _PAINT_LOCK:
                    _PAINT_MEMO[memo_key] = res
                return res
    if not cloudflare_ready() and not (os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
                                       and os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()):
        print("[imagegen] no Cloudflare key: stock for this shot", flush=True)
        return None
    cap = _env_int("REEL_PAINT_MAX_PER_RUN", 12)
    day_cap = float(os.environ.get("REEL_PAINT_DAILY_NEURONS", "8000") or 8000)
    out_dir = cache or Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "reel_stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    for model in chain:
        w, h = paint_size(model)
        cost = neuron_cost(model, w, h)
        with _PAINT_LOCK:
            if _PAINT_STATE["exhausted"]:
                return None
            if _PAINT_STATE["generated"] >= cap:
                print(f"[imagegen] {cap} stills painted this run (REEL_PAINT_MAX_PER_RUN): "
                      f"stock for this shot", flush=True)
                return None
            spent = neurons_spent_today(cache) if cache else _PAINT_STATE["neurons"]
            if spent + cost > day_cap:
                print(f"[imagegen] {model.split('/')[-1]}: {spent:.0f} + {cost:.0f} neurons "
                      f"would pass today's {day_cap:.0f} (REEL_PAINT_DAILY_NEURONS)", flush=True)
                continue
            _PAINT_STATE["generated"] += 1      # reserve the slot before the call
        raw, err = None, ""
        for attempt in range(_PAINT_TRIES):
            try:
                raw = _cf_run(model, prompt, w, h, seed)
                break
            except CloudflareBudgetExhausted as e:
                with _PAINT_LOCK:
                    _PAINT_STATE["exhausted"] = True
                    _PAINT_STATE["generated"] -= 1
                print(f"[imagegen] Cloudflare's free day is used up ({e}): stock from here",
                      flush=True)
                return None
            except _Transient as e:
                err = str(e)
                _time.sleep(2.0 * (attempt + 1))
            except Exception as e:  # noqa: BLE001
                err = _scrub(e)
                break
        if raw is None:
            with _PAINT_LOCK:
                _PAINT_STATE["generated"] -= 1
            print(f"[imagegen] {model.split('/')[-1]} failed ({err}); next in the chain",
                  file=sys.stderr, flush=True)
            continue
        k = still_key(model, prompt, seed, w, h)
        meta = {"model": model, "prompt": prompt, "seed": seed, "w": w, "h": h,
                "neurons": cost, "made": _today_utc()}
        path = _cache_store(out_dir, k, raw, meta)
        with _PAINT_LOCK:
            _PAINT_STATE["neurons"] += cost
            if cache:
                _ledger_add(cache, cost)
            res = {"path": str(path), "model": model, "cached": False,
                   "neurons": cost, "key": k}
            _PAINT_MEMO[memo_key] = res
        print(f"[imagegen] SOURCE=CLOUDFLARE_{model.split('/')[-1].upper()} "
              f"{w}x{h} seed={seed} ~{cost:.0f} neurons", flush=True)
        return dict(res)
    return None
