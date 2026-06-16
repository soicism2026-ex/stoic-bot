"""
Background music selection and download for the daily Short.

Tracks are fetched from the Pixabay music API (royalty-free, no attribution).
Downloaded once per track and cached in assets/music/.  A run never breaks:
every failure falls back gracefully so music is simply omitted on that day.

Analytics-weighted rotation: once a track has ≥5 posts worth of view data,
the track with the highest average views is preferred.  Below that threshold
all tracks rotate equally (LRU) to gather data.
"""
import csv
import os
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"

PIXABAY_MUSIC_URL = "https://pixabay.com/api/music/"

# Three distinct moods to vary the feel across the week.  Queries tuned for
# Stoic/philosophical Shorts — brooding, minimalist, contemplative.
MUSIC_POOL = [
    {"name": "dark_ambient",     "query": "dark ambient cinematic"},
    {"name": "ancient_minimal",  "query": "ancient meditation minimal"},
    {"name": "focus_underscore", "query": "deep focus cinematic underscore"},
]

# Volume for the background music relative to the voice (0.0–1.0).
MUSIC_VOLUME = float(os.environ.get("MUSIC_VOLUME", "0.07"))  # ~-23 dB under voice

MIN_POSTS_FOR_WEIGHT = 5  # require this many posts per track before analytics-weighting


# ---------------------------------------------------------------------------
# Analytics-weighted selection
# ---------------------------------------------------------------------------

def _load_analytics() -> dict[str, int]:
    """Return {video_id: views} from data/analytics.csv using peak views per video."""
    path = ROOT / "data" / "analytics.csv"
    if not path.exists():
        return {}
    peak: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            v = int(row.get("views") or 0)
            if vid and v > peak.get(vid, 0):
                peak[vid] = v
    return peak


def _avg_views(track_name: str, rows: list[dict], analytics: dict[str, int]) -> float | None:
    """Average views for posts that used this track.  Returns None if not enough data."""
    matching = [r for r in rows
                if r.get("music_track") == track_name and r.get("video_id")]
    if len(matching) < MIN_POSTS_FOR_WEIGHT:
        return None
    views = [analytics.get(r["video_id"], 0) for r in matching]
    return sum(views) / len(views)


def pick_music(rows: list[dict]) -> dict:
    """Return a track from MUSIC_POOL using analytics-weighted selection.

    Strategy:
      - If any track lacks ≥5 data posts: rotate LRU (equal exploration).
      - Once all tracks have data: prefer highest avg-views; block most recent
        to avoid repeating the same track two days running.
    """
    if not MUSIC_POOL:
        return MUSIC_POOL[0]

    analytics = _load_analytics()
    avgs = {t["name"]: _avg_views(t["name"], rows, analytics) for t in MUSIC_POOL}

    # Exploration phase: not enough data on at least one track → LRU rotation.
    if any(v is None for v in avgs.values()):
        recent = [r.get("music_track") for r in reversed(rows) if r.get("music_track")]
        block = recent[0] if recent else None
        candidates = [t for t in MUSIC_POOL if t["name"] != block] or MUSIC_POOL
        day = date.today().toordinal()
        return candidates[day % len(candidates)]

    # Exploitation phase: block most recent, pick highest avg views from rest.
    recent = [r.get("music_track") for r in reversed(rows) if r.get("music_track")]
    block = recent[0] if recent else None
    candidates = [t for t in MUSIC_POOL if t["name"] != block] or MUSIC_POOL
    return max(candidates, key=lambda t: avgs.get(t["name"], 0))


# ---------------------------------------------------------------------------
# Download / cache
# ---------------------------------------------------------------------------

def fetch_music(track: dict, out_path: Path) -> Path | None:
    """Download the track audio to out_path.  Returns out_path on success, None on failure."""
    # Use a persistent per-track cache so we only download once.
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    cached = MUSIC_DIR / f"{track['name']}.mp3"
    if cached.exists() and cached.stat().st_size > 5_000:
        return cached

    api_key = os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        print("[music] PIXABAY_API_KEY not set — skipping music", file=sys.stderr)
        return None

    try:
        resp = requests.get(
            PIXABAY_MUSIC_URL,
            params={"key": api_key, "q": track["query"], "per_page": 10, "order": "popular"},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            print(f"[music] no Pixabay music results for '{track['query']}'", file=sys.stderr)
            return None

        audio_url = hits[0].get("audio", {}).get("url") or hits[0].get("url", "")
        if not audio_url:
            # Try alternate key names
            for h in hits:
                for key in ("mp3", "preview_url", "url"):
                    u = h.get(key, "") or h.get("audio", {}).get(key, "")
                    if u and u.endswith(".mp3"):
                        audio_url = u
                        break
                if audio_url:
                    break

        if not audio_url:
            print(f"[music] could not extract audio URL from Pixabay response", file=sys.stderr)
            return None

        with requests.get(audio_url, stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with open(cached, "wb") as fh:
                for chunk in dl.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)

        if cached.stat().st_size < 5_000:
            cached.unlink(missing_ok=True)
            print(f"[music] downloaded file too small for '{track['name']}'", file=sys.stderr)
            return None

        print(f"[music] cached {track['name']} → {cached.name}")
        return cached

    except Exception as e:
        print(f"[music] fetch failed for '{track['name']}': {e}", file=sys.stderr)
        cached.unlink(missing_ok=True)
        return None
