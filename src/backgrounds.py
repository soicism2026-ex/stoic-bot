"""
Background video sourcing for the daily Short.

Primary path: fetch a fresh, theme-matched vertical clip from the Pexels
video API each day so Shorts don't all look identical. If anything goes wrong
(no API key, network error, no results, bad download) we fall back to the
original rotate-by-date logic over assets/backgrounds/ — a run never breaks.
"""
import os
import sys
from pathlib import Path
from datetime import date

import requests

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "backgrounds"

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

# Themes from content.py are full phrases ("mortality/memento mori",
# "control vs acceptance", ...), so we match by substring keyword.
THEME_QUERIES = [
    ("mortality", "dark storm clouds"),
    ("discipline", "cold mountain peak"),
    ("time", "flowing river"),
    ("control", "calm ocean"),
]
DEFAULT_QUERY = "cinematic nature"


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
    return clips[date.today().toordinal() % len(clips)]


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

    # deterministic-by-date choice so it's varied but reproducible per day
    video = videos[date.today().toordinal() % len(videos)]
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


def fetch_background(theme: str, out_path: Path) -> Path:
    """
    Return a path to a background clip for today's Short.

    Tries Pexels first (fresh, theme-matched). On ANY failure, falls back to
    the local rotate-by-date clip and returns that path instead.
    """
    out_path = Path(out_path)
    query = _search_term(theme)
    try:
        path = _fetch_from_pexels(theme, out_path)
        print(f"[background] SOURCE=PEXELS query='{query}' file={path.name}", flush=True)
        return path
    except Exception as e:  # noqa: BLE001 — any failure must fall back
        local = _rotate_local()
        print(
            f"[background] SOURCE=LOCAL_FALLBACK query='{query}' reason={e} "
            f"file={local.name} "
            f"(set the PEXELS_API_KEY repo secret to get fresh clips)",
            file=sys.stderr, flush=True,
        )
        print(f"[background] SOURCE=LOCAL_FALLBACK file={local.name}", flush=True)
        return local
