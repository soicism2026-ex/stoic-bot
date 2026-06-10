"""
Background video sourcing for the daily Short.

Primary path: fetch a fresh, theme-matched vertical clip from the Pexels
video API each day so Shorts don't all look identical. If anything goes wrong
(no API key, network error, no results, bad download) we fall back to a clip
from assets/backgrounds/ — a run never breaks.

Variety: selection is RANDOM each run (not keyed on the calendar date), and we
read the recently-used backgrounds out of data/posts.csv and exclude them, so
the same clip never lands two runs in a row — including same-day re-runs, which
a date-based pick could not distinguish.
"""
import csv
import os
import random
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "backgrounds"
POSTS_CSV = Path(os.environ.get("POSTS_CSV", ROOT / "data" / "posts.csv"))

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

# Themes from content.py are full phrases ("mortality/memento mori",
# "control vs acceptance", ...), so we match by substring keyword. All 12
# themes in content.py are covered so the search term varies meaningfully
# day to day; anything unmatched uses DEFAULT_QUERY.
THEME_QUERIES = [
    ("mortality", "dark storm clouds"),
    ("discipline", "cold mountain peak"),
    ("control", "calm ocean"),
    ("anger", "raging wildfire"),
    ("desire", "desert sand dunes"),
    ("resilience", "waves crashing on rocks"),
    ("time", "flowing river"),
    ("ego", "vast starry night sky"),
    ("fear", "dark misty forest"),
    ("friendship", "campfire at night"),
    ("duty", "ancient stone columns"),
    ("justice", "ancient stone columns"),
    ("adversity", "snowstorm blizzard"),
]
DEFAULT_QUERY = "cinematic nature"

# How many recent backgrounds to avoid reusing.
AVOID_RECENT = 3

# Set by fetch_background() so main.py can record which clip was used (into
# posts.csv) and the next run can avoid it. Format: "pexels:<id>" / "local:<file>".
_LAST_CHOSEN = None


def last_chosen() -> str:
    """Identifier of the background chosen by the most recent fetch_background()."""
    return _LAST_CHOSEN or ""


def _search_term(theme: str) -> str:
    t = (theme or "").lower()
    for keyword, query in THEME_QUERIES:
        if keyword in t:
            return query
    return DEFAULT_QUERY


def _recent_backgrounds(n: int = AVOID_RECENT) -> set:
    """Recently-used background identifiers, read from the committed posts.csv."""
    if not POSTS_CSV.exists():
        return set()
    try:
        with open(POSTS_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:  # noqa: BLE001 — history is best-effort
        return set()
    vals = [r.get("background") for r in rows if r.get("background")]
    return set(vals[-n:])


def _rotate_local() -> Path:
    """Fallback: pick a local clip at random, avoiding recently-used ones."""
    clips = sorted(BG_DIR.glob("*.mp4"))
    if not clips:
        raise FileNotFoundError(
            f"No background clips in {BG_DIR}. Drop a few royalty-free vertical "
            f"MP4s there (Pexels Videos)."
        )
    recent = _recent_backgrounds()
    pool = [c for c in clips if f"local:{c.name}" not in recent] or clips
    return random.choice(pool)


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


def _fetch_from_pexels(theme: str, out_path: Path) -> tuple[Path, str]:
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
            "per_page": 30,
        },
        timeout=30,
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"Pexels returned no videos for '{query}'")

    # Random pick, avoiding clips used on recent runs. Shuffle so we also skip
    # any result that has no usable vertical file without re-picking the same one.
    recent = _recent_backgrounds()
    candidates = [v for v in videos if f"pexels:{v.get('id')}" not in recent] or videos
    random.shuffle(candidates)

    video = link = None
    for cand in candidates:
        link = _pick_vertical_file(cand)
        if link:
            video = cand
            break
    if not video or not link:
        raise RuntimeError("No suitable vertical MP4 in any Pexels result")

    with requests.get(link, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in dl.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("Downloaded Pexels clip is empty/too small")

    return out_path, f"pexels:{video.get('id')}"


def fetch_background(theme: str, out_path: Path) -> Path:
    """
    Return a path to a background clip for today's Short.

    Tries Pexels first (fresh, theme-matched, random with recent-avoidance). On
    ANY failure, falls back to a local clip and returns that path instead. The
    chosen clip's identifier is recorded in `last_chosen()` for history logging.
    """
    global _LAST_CHOSEN
    out_path = Path(out_path)
    query = _search_term(theme)
    try:
        path, label = _fetch_from_pexels(theme, out_path)
        _LAST_CHOSEN = label
        print(f"[background] SOURCE=PEXELS query='{query}' {label} file={path.name}", flush=True)
        return path
    except Exception as e:  # noqa: BLE001 — any failure must fall back
        local = _rotate_local()
        _LAST_CHOSEN = f"local:{local.name}"
        print(
            f"[background] SOURCE=LOCAL_FALLBACK query='{query}' reason={e} "
            f"file={local.name} "
            f"(set the PEXELS_API_KEY repo secret to get fresh clips)",
            file=sys.stderr, flush=True,
        )
        print(f"[background] SOURCE=LOCAL_FALLBACK {_LAST_CHOSEN} file={local.name}", flush=True)
        return local
