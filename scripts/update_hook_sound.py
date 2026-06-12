"""
Weekly hook-sound preset updater.

Queries YouTube for trending philosophy/motivation Shorts published in the last
7 days, then asks Claude Haiku which of the four synthesized presets best matches
the current viral audio aesthetic.  Writes the result to data/hook_preset so
render.py picks it up on the next daily run.

Presets: bass_impact | cinematic | whoosh | minimal
"""
import csv
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import anthropic

ROOT = Path(__file__).resolve().parent.parent
PRESET_FILE = ROOT / "data" / "hook_preset"
ANALYTICS_CSV = ROOT / "data" / "analytics.csv"

PRESETS = ["bass_impact", "cinematic", "whoosh", "minimal"]
DESCRIPTIONS = {
    "bass_impact": "Sub-bass punch + transient snap; heavy, modern, hype/motivation energy.",
    "cinematic":   "Orchestral harmonic swell → dramatic hit; serious, philosophical depth.",
    "whoosh":      "Pink-noise rising whoosh + soft low sine; broadly neutral.",
    "minimal":     "Single clean struck tone with overtone; calm, educational aesthetic.",
}


def _yt_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def fetch_trending(max_results: int = 20) -> list:
    """Return metadata for top-viewed philosophy/motivation Shorts this week.

    Uses search.list (100 quota units) — runs once per week so ~14 units/day avg.
    Falls back to an empty list on any error so the rest of the script still runs.
    """
    try:
        yt = _yt_service()
        week_ago = (
            datetime.datetime.utcnow() - datetime.timedelta(days=7)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        results = yt.search().list(
            part="snippet",
            q="stoic motivation wisdom philosophy mindset",
            type="video",
            videoDuration="short",
            order="viewCount",
            publishedAfter=week_ago,
            maxResults=max_results,
        ).execute()

        ids = [item["id"]["videoId"] for item in results.get("items", [])]
        if not ids:
            return []

        stats = yt.videos().list(part="statistics,snippet", id=",".join(ids)).execute()
        rows = []
        for item in stats.get("items", []):
            rows.append({
                "title":        item["snippet"]["title"],
                "channelTitle": item["snippet"]["channelTitle"],
                "views":        int(item.get("statistics", {}).get("viewCount", 0) or 0),
                "likes":        int(item.get("statistics", {}).get("likeCount", 0) or 0),
                "tags":         item["snippet"].get("tags", [])[:8],
            })
        rows.sort(key=lambda r: r["views"], reverse=True)
        return rows[:12]
    except Exception as e:
        print(f"  [hook] YouTube trending fetch failed: {e}", file=sys.stderr)
        return []


def read_own_analytics() -> list:
    """Return our channel's recent analytics rows for context."""
    if not ANALYTICS_CSV.exists():
        return []
    with open(ANALYTICS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))[-20:]  # last 20 rows


def recommend(trending: list, own_analytics: list) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    trend_block = ""
    if trending:
        trend_block = "Trending Shorts this week (by views):\n" + "\n".join(
            f'- "{r["title"]}" ({r["views"]:,} views) — {r["channelTitle"]}'
            for r in trending[:10]
        )
    else:
        trend_block = "(No external trending data available this run.)"

    own_block = ""
    if own_analytics:
        top = sorted(own_analytics, key=lambda r: int(r.get("views", 0) or 0), reverse=True)[:5]
        own_block = "\nOur channel's recent top videos:\n" + "\n".join(
            f'- "{r["title"]}" ({r.get("views", 0)} views)'
            for r in top
        )

    preset_block = "\n".join(f"- {k}: {v}" for k, v in DESCRIPTIONS.items())

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                f"{trend_block}{own_block}\n\n"
                f"Based on the tone and energy of high-performing content in this niche, "
                f"which single hook-sound preset will best grab attention?\n\n"
                f"Available presets:\n{preset_block}\n\n"
                f"Return ONLY JSON: "
                f'{{\"preset\": \"<name>\", \"reason\": \"<one sentence>\"}} '
                f"where preset is one of: {', '.join(PRESETS)}"
            ),
        }],
    )

    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(ln for ln in raw.split("\n") if not ln.startswith("```"))

    try:
        result = json.loads(raw.strip())
        preset = result.get("preset", "bass_impact")
        if preset not in PRESETS:
            preset = "bass_impact"
        print(f"  [hook] → '{preset}': {result.get('reason', '')}")
        return preset
    except Exception:
        print(f"  [hook] parse failed ({raw[:80]}); keeping current", file=sys.stderr)
        return PRESET_FILE.read_text(encoding="utf-8").strip() if PRESET_FILE.exists() else "bass_impact"


def main():
    print("[update_hook_sound] fetching trending Shorts...")
    trending = fetch_trending()
    print(f"  trending: {len(trending)} videos found")

    own = read_own_analytics()
    print(f"  own analytics: {len(own)} rows")

    preset = recommend(trending, own)
    PRESET_FILE.parent.mkdir(exist_ok=True)
    PRESET_FILE.write_text(preset, encoding="utf-8")
    print(f"[update_hook_sound] wrote preset '{preset}' → {PRESET_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
