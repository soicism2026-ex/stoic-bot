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
    "cinematic film still, dark moody dramatic chiaroscuro lighting, "
    "teal-and-orange color grade, shallow depth of field, volumetric light, "
    "atmospheric, photorealistic, shot on 35mm. Absolutely NO text, NO words, "
    "NO letters, NO watermark, NO captions.",
)
MODEL = os.environ.get("REEL_IMAGE_MODEL", "gpt-image-1")
_SIZE = os.environ.get("REEL_IMAGE_SIZE", "1024x1536")  # portrait ~2:3


def enabled() -> bool:
    """True only when explicitly turned on AND a key exists."""
    on = os.environ.get("REEL_IMAGE_BG", "0") not in ("0", "false", "False")
    return on and bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _generate_image(prompt: str, out_png: Path) -> bool:
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
                  width: int = 1080, height: int = 1920) -> Path | None:
    """Generate a still for `prompt` and render it into a short MP4 with a slow
    Ken Burns push. Returns the clip path, or None on ANY failure (caller then
    falls back to stock)."""
    if not enabled():
        return None
    try:
        png = out_path.with_suffix(".gen.png")
        if not _generate_image(prompt, png):
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
