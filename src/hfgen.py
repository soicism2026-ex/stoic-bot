"""
Storyboard shot generator on the Higgsfield REST API.

Three models, each doing the job it is best at — schemas read from Higgsfield's
own model docs on 2026-09-23:

  WAN 3.0  alibaba/wan-3.0/text-to-video
      Native 9:16, ANY length 2-30s, so a 3.5s shot bills 3.5s, not a padded
      5 or 10. Used for settings, objects and atmosphere.
  SOUL     higgsfield-ai/soul/standard
      9:16 stills with a fixed seed. Used as the start frame for every shot
      with a person in it.
  KLING    kling-video/v2.5-turbo/standard/image-to-video
      Best human motion. Its text-to-video variant has NO aspect_ratio
      parameter (it would arrive landscape and lose two thirds of the frame in
      a vertical crop), but image-to-video follows the start image's shape —
      so a 9:16 Soul still in means a 9:16 clip out. The shared still is also
      what keeps one character looking like the same man from shot to shot,
      which the Kling 3.0 smoke test visibly failed.

Every call is bounded (per-request timeouts plus an overall deadline) and every
function returns None on failure rather than raising, so a caller can always
fall back to stock. Credentials: HIGGSFIELD_API_KEY or HF_KEY, KEY_ID:KEY_SECRET,
never logged.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

import proc

BASE = os.environ.get("HF_BASE_URL", "https://api.higgsfield.ai")
WAN = "alibaba/wan-3.0/text-to-video"
SOUL = "higgsfield-ai/soul/standard"
KLING_I2V = os.environ.get("HF_KLING_I2V",
                           "kling-video/v2.5-turbo/standard/image-to-video")

SUBMIT_TIMEOUT = 60
POLL_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 180
# 360s per shot, 4 in parallel: 8 shots fit in ~12 min worst case, which
# keeps setup + storyboard + the 35 min post budget under the 60 min job cap.
DEADLINE = float(os.environ.get("HF_SHOT_DEADLINE", "360"))
POLL_EVERY = 5

W, H = 1080, 1920

# Shared look. Named physical light sources, not lighting styles (the model
# has no reliable "not"), and controlled midtones so render.py's grade has
# room to darken without crushing.
LOOK = ("cinematic 35mm film, natural warm practical light, detail kept in the "
        "shadows, controlled midtones, shallow depth of field, photorealistic, "
        "muted restrained palette, no text, no watermark, no subtitles")


def key() -> str:
    k = (os.environ.get("HIGGSFIELD_API_KEY") or os.environ.get("HF_KEY") or "").strip()
    return k if ":" in k else ""


def _headers() -> dict:
    return {"Authorization": f"Key {key()}", "Content-Type": "application/json"}


def _log(msg: str) -> None:
    print(f"[hfgen] {msg}", file=sys.stderr, flush=True)


def _run(model: str, payload: dict) -> dict | None:
    """Submit, poll to a terminal status, return the completed JSON or None.
    Failed, canceled and moderated generations are failures, never results."""
    if not key():
        _log("no HIGGSFIELD_API_KEY / HF_KEY in KEY_ID:KEY_SECRET form")
        return None
    deadline = time.monotonic() + DEADLINE
    try:
        r = requests.post(f"{BASE}/{model}", json=payload, headers=_headers(),
                          timeout=SUBMIT_TIMEOUT)
        if r.status_code >= 400:
            _log(f"{model}: HTTP {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        status_url = data.get("status_url") or f"{BASE}/requests/{data['request_id']}/status"
        while True:
            s = (data.get("status") or "").lower()
            if s == "completed":
                return data
            if s in ("failed", "nsfw", "canceled"):
                _log(f"{model}: {s} {data.get('error', '')}")
                return None
            if time.monotonic() > deadline:
                _log(f"{model}: no result after {DEADLINE:.0f}s")
                try:
                    requests.put(data.get("cancel_url") or
                                 f"{BASE}/requests/{data['request_id']}/cancel",
                                 headers=_headers(), timeout=POLL_TIMEOUT)
                except Exception:  # noqa: BLE001
                    pass
                return None
            time.sleep(POLL_EVERY)
            g = requests.get(status_url, headers=_headers(), timeout=POLL_TIMEOUT)
            if g.status_code >= 400:
                _log(f"{model}: status HTTP {g.status_code}")
                return None
            data = g.json()
    except Exception as e:  # noqa: BLE001
        _log(f"{model}: {type(e).__name__}: {str(e)[:200]}")
        return None


def _download(url: str, out: Path) -> Path | None:
    try:
        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            with open(out, "wb") as fh:
                for chunk in r.iter_content(1 << 16):
                    fh.write(chunk)
        return out if out.stat().st_size > 5_000 else None
    except Exception as e:  # noqa: BLE001
        _log(f"download failed: {e}")
        return None


def _normalise(src: Path, out: Path, seconds: float) -> Path | None:
    """1080x1920, no audio. NOT trimmed to the planned length: the renderer
    scales the plan to the real voiceover, so a shot can land a little longer
    than planned, and a clip trimmed to the plan would visibly loop."""
    try:
        proc.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                  "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                         f"crop={W}:{H},setsar=1,fps=30",
                  "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-pix_fmt", "yuv420p", str(out)], check=True, capture_output=True)
        return out
    except Exception as e:  # noqa: BLE001
        _log(f"normalise failed: {e}")
        return None


def still(prompt: str, seed: int | None = None) -> str | None:
    """A 9:16 Soul keyframe. Returns its URL (Kling takes a URL as start frame)."""
    p = {"prompt": f"{prompt}. {LOOK}", "aspect_ratio": "9:16",
         "resolution": "1080p", "batch_size": 1}
    if seed is not None:
        p["seed"] = int(seed)
    d = _run(SOUL, p)
    imgs = (d or {}).get("images") or []
    return imgs[0].get("url") if imgs and isinstance(imgs[0], dict) else None


def wan(prompt: str, seconds: float, out: Path, seed: int | None = None) -> Path | None:
    """A setting/object shot, billed for exactly its own length (min 2s)."""
    dur = max(2, min(30, round(seconds + 1.5)))   # 1.5s handle for re-timing
    p = {"prompt": f"{prompt}. {LOOK}", "duration": dur, "resolution": "720p",
         "aspect_ratio": "9:16", "generate_audio": False}
    if seed is not None:
        p["seed"] = int(seed)
    d = _run(WAN, p)
    url = ((d or {}).get("video") or {}).get("url")
    raw = _download(url, out.with_suffix(".raw.mp4")) if url else None
    return _normalise(raw, out, seconds) if raw else None


def kling(still_prompt: str, motion: str, seconds: float, out: Path,
          seed: int | None = None) -> Path | None:
    """A character shot: Soul still (9:16, seeded) -> Kling 2.5 image-to-video."""
    img = still(still_prompt, seed)
    if not img:
        return None
    d = _run(KLING_I2V, {"image_url": img, "prompt": f"{motion}. {LOOK}",
                         "duration": 5 if seconds <= 5 else 10})
    url = ((d or {}).get("video") or {}).get("url")
    raw = _download(url, out.with_suffix(".raw.mp4")) if url else None
    return _normalise(raw, out, seconds) if raw else None


def shot(spec: dict, cast: dict, out: Path) -> Path | None:
    """Render one storyboard shot. spec: {model, seconds, picture, motion?, who?}.
    `who` names a cast member; their fixed description and seed are prepended
    so the same man is the same man in every shot."""
    who = spec.get("who")
    person = cast.get(who, {}) if who else {}
    desc = f"{person['look']}, {spec['picture']}" if person else spec["picture"]
    seed = person.get("seed", spec.get("seed"))
    if spec["model"] == "kling":
        return kling(desc, spec.get("motion", "subtle natural movement"),
                     spec["seconds"], out, seed)
    return wan(desc, spec["seconds"], out, seed)
