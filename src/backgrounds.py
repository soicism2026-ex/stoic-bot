"""
Background video sourcing for the daily Short.

Source chain (first that succeeds wins):
  1. Pexels  — fresh, theme-matched vertical clip (PEXELS_API_KEY)
  2. Pixabay — second free API (PIXABAY_API_KEY, optional)
  3. Synthetic — ffmpeg lavfi dark-gradient; always available, no network needed
  4. Local rotation — assets/backgrounds/ deterministic fallback

A run never breaks: every stage catches its own errors and tries the next.
"""
import os
import subprocess
import sys
from pathlib import Path
from datetime import date

import requests

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "backgrounds"

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

# Themes from content.py are full phrases ("mortality/memento mori",
# "control vs acceptance", ...), so we match by substring keyword.
THEME_QUERIES = [
    ("mortality", "dark storm clouds"),
    ("discipline", "cold mountain peak"),
    ("time", "flowing river"),
    ("control", "calm ocean"),
    ("virtue", "ancient temple"),
    ("wisdom", "misty forest"),
    ("resilience", "rocky coastline"),
    ("purpose", "mountain sunrise"),
    ("impermanence", "autumn leaves"),
    ("justice", "thunderstorm"),
]
DEFAULT_QUERY = "cinematic dark nature"


def _bg_offset() -> int:
    """Offset for the deterministic-by-date pick. Set by the QA retry loop
    (REEL_BG_OFFSET=attempt) so a failed render gets a different clip on retry.
    Read at call time, not import time, because daily_post.py changes it
    between attempts without reimporting this module."""
    try:
        return int(os.environ.get("REEL_BG_OFFSET", "0"))
    except ValueError:
        return 0

# Dark colour palettes (hex) for synthetic backgrounds, keyed by theme keyword.
_SYNTHETIC_COLOURS = {
    "mortality":    "0x0b0c1e",
    "discipline":   "0x0a1015",
    "time":         "0x100e08",
    "control":      "0x091212",
    "virtue":       "0x0e0c18",
    "wisdom":       "0x120f0a",
    "resilience":   "0x0a0f0a",
    "purpose":      "0x12100a",
    "impermanence": "0x0e0c0a",
    "justice":      "0x140a0a",
}


def _search_term(theme: str) -> str:
    t = (theme or "").lower()
    for keyword, query in THEME_QUERIES:
        if keyword in t:
            return query
    return DEFAULT_QUERY


def _rotate_local() -> Path:
    """Original fallback: rotate deterministically by day over local clips."""
    clips = sorted(BG_DIR.glob("*.mp4"))
    if not clips:
        raise FileNotFoundError(
            f"No background clips in {BG_DIR}. Drop a few royalty-free vertical "
            f"MP4s there (Pexels Videos)."
        )
    return clips[(date.today().toordinal() + _bg_offset()) % len(clips)]


def _pick_vertical_file(video: dict) -> str | None:
    """Pick the best vertical MP4 link from a Pexels video result."""
    files = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4"
        and f.get("link")
        and (f.get("height") or 0) >= (f.get("width") or 0)  # portrait/square
    ]
    if not files:
        return None
    # prefer something close to 1920 tall but not absurdly huge
    files.sort(key=lambda f: abs((f.get("height") or 0) - 1920))
    return files[0]["link"]


def _fetch_from_pexels(theme: str, out_path: Path) -> Path:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY not set")

    query = _search_term(theme)
    resp = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={
            "query": query,
            "orientation": "portrait",
            "size": "medium",
            "per_page": 15,
        },
        timeout=30,
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"Pexels returned no videos for '{query}'")

    # deterministic-by-date choice so it's varied but reproducible per day;
    # the retry loop shifts the pick via REEL_BG_OFFSET
    video = videos[(date.today().toordinal() + _bg_offset()) % len(videos)]
    link = _pick_vertical_file(video)
    if not link:
        raise RuntimeError("No suitable vertical MP4 in chosen Pexels result")

    with requests.get(link, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in dl.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("Downloaded Pexels clip is empty/too small")

    return out_path


def _fetch_from_pixabay(theme: str, out_path: Path) -> Path:
    """Download a portrait video from Pixabay (requires PIXABAY_API_KEY)."""
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        raise RuntimeError("PIXABAY_API_KEY not set")

    query = _search_term(theme)
    resp = requests.get(
        PIXABAY_VIDEO_URL,
        params={"key": api_key, "q": query, "per_page": 20, "order": "popular"},
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    # Prefer portrait (height >= width); fall back to any if none found
    portrait = [
        h for h in hits
        if (h.get("videos", {}).get("large", {}).get("height", 0) >=
            h.get("videos", {}).get("large", {}).get("width", 1))
    ]
    pool = portrait or hits
    if not pool:
        raise RuntimeError(f"Pixabay returned no videos for '{query}'")

    pick = pool[(date.today().toordinal() + _bg_offset()) % len(pool)]
    url = None
    for size in ("large", "medium", "small"):
        v = pick.get("videos", {}).get(size, {})
        if v.get("url"):
            url = v["url"]
            break
    if not url:
        raise RuntimeError("No usable URL in Pixabay response")

    with requests.get(url, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in dl.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("Pixabay clip too small")
    return out_path


def _fetch_synthetic(theme: str, out_path: Path) -> Path:
    """Generate a dark atmospheric background via ffmpeg lavfi (no network needed).

    Produces a 2-second loopable clip. render.py's stream_loop -1 fills the full
    Short duration; Ken Burns zoom makes the still frame feel alive.
    """
    t = (theme or "").lower()
    colour = _SYNTHETIC_COLOURS.get(
        next((k for k in _SYNTHETIC_COLOURS if k in t), ""), "0x0c0c1a"
    )
    # solid dark colour → vignette darkens edges → subtle warmth via hue nudge
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={colour}:size=1080x1920:rate=1:duration=2",
        "-vf", "vignette=PI/3.5:eval=init",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError("Synthetic background generation failed")
    return out_path


def fetch_background(theme: str, out_path: Path) -> Path:
    """
    Return a background clip for today's Short.

    Chain: Pexels → Pixabay → Synthetic (lavfi) → Local rotation.
    Every stage catches its own failures so a run never breaks.
    """
    out_path = Path(out_path)
    query = _search_term(theme)

    for label, fn in [
        ("PEXELS",    lambda: _fetch_from_pexels(theme, out_path)),
        ("PIXABAY",   lambda: _fetch_from_pixabay(theme, out_path)),
        ("SYNTHETIC", lambda: _fetch_synthetic(theme, out_path)),
    ]:
        try:
            path = fn()
            print(f"[background] SOURCE={label} query='{query}' file={path.name}", flush=True)
            return path
        except Exception as e:  # noqa: BLE001
            print(f"[background] {label} failed: {e}", file=sys.stderr, flush=True)

    local = _rotate_local()
    print(f"[background] SOURCE=LOCAL_FALLBACK file={local.name}", flush=True)
    return local
