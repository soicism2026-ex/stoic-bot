"""
YouTube Analytics API v2 client.

Pulls extended per-video metrics not available in the basic YouTube Data API v3
statistics endpoint:
  avg_view_duration_s    — seconds of the video actually watched on average
  avg_view_percentage    — percentage of the video watched (proxy for retention)
  swipe_away_rate        — 1 - avg_view_percentage/100 (higher = viewers leave sooner)
  estimated_minutes_watched
  likes, comments, shares, subscribers_gained

Quota notes
-----------
YouTube Analytics API v2 costs ~1 unit per report query (vs. ~100 for uploads).
We batch up to BATCH_SIZE=25 video IDs per query and cache results to
data/analytics_extended.json so we never re-pull data that is already fresh.
Budget is controlled by YOUTUBE_ANALYTICS_QUOTA_BUDGET (default: 200 units).

OAuth scope
-----------
Requires: https://www.googleapis.com/auth/yt-analytics.readonly
This is a SEPARATE scope from youtube.readonly and youtube.force-ssl.
If you see a 403, re-run scripts/auth_setup.py with the additional scope and
update the YOUTUBE_REFRESH_TOKEN secret.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "analytics_extended.json"

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
BATCH_SIZE = 25

DEFAULT_QUOTA_BUDGET = int(os.environ.get("YOUTUBE_ANALYTICS_QUOTA_BUDGET", "200"))

_BASE_METRICS = ",".join([
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _build_creds():
    from google.oauth2.credentials import Credentials
    return Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.readonly", ANALYTICS_SCOPE],
    )


def build_analytics_client():
    """Build the YouTube Analytics API v2 service client."""
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=_build_creds(), cache_discovery=False)


def get_channel_id() -> str:
    """Return the authenticated channel's ID via the Data API."""
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
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.channels().list(part="id", mine=True).execute()
    return resp["items"][0]["id"]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def load_cache() -> dict[str, dict]:
    """Load the extended analytics cache from JSON."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cache(data: dict[str, dict]):
    """Persist the extended analytics cache to JSON."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def fetch_video_metrics(
    video_ids: list[str],
    *,
    channel_id: str | None = None,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    quota_budget: int = DEFAULT_QUOTA_BUDGET,
) -> dict[str, dict]:
    """
    Fetch extended metrics for video_ids from the Analytics API.

    Returns {video_id: {metric: value, ...}}.
    Returns partial results (and prints a warning) when quota_budget is reached
    or a quota/auth error (403/400) is encountered.
    """
    if end_date is None:
        end_date = date.today().strftime("%Y-%m-%d")

    if channel_id is None:
        try:
            channel_id = get_channel_id()
        except Exception as e:
            print(f"  [youtube_analytics] could not get channel ID: {e}", file=sys.stderr)
            return {}

    try:
        client = build_analytics_client()
    except Exception as e:
        print(f"  [youtube_analytics] could not build client: {e}", file=sys.stderr)
        return {}

    results: dict[str, dict] = {}
    units_used = 0
    fetched_at = datetime.utcnow().isoformat()

    for i in range(0, len(video_ids), BATCH_SIZE):
        if units_used >= quota_budget:
            print(
                f"  [youtube_analytics] quota budget ({quota_budget} units) reached; "
                f"processed {i}/{len(video_ids)} videos",
                file=sys.stderr,
            )
            break

        batch = video_ids[i : i + BATCH_SIZE]
        filter_str = "video==" + ",".join(batch)

        try:
            resp = client.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics=_BASE_METRICS,
                dimensions="video",
                filters=filter_str,
                maxResults=BATCH_SIZE,
            ).execute()
            units_used += 1

        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "rateLimitExceeded" in err:
                print(f"  [youtube_analytics] quota error — stopping: {e}", file=sys.stderr)
                break
            elif "403" in err:
                print(f"  [youtube_analytics] 403 — ensure YOUTUBE_REFRESH_TOKEN includes "
                      "yt-analytics.readonly scope: {e}", file=sys.stderr)
                break
            elif "400" in err:
                print(f"  [youtube_analytics] 400 — check scope or filter syntax: {e}",
                      file=sys.stderr)
                break
            else:
                print(f"  [youtube_analytics] error on batch {i // BATCH_SIZE}: {e}",
                      file=sys.stderr)
                continue

        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        for row in resp.get("rows", []):
            rd = dict(zip(headers, row))
            vid = rd.get("video", "")
            if not vid:
                continue
            avg_pct = float(rd.get("averageViewPercentage", 0))
            results[vid] = {
                "views": int(float(rd.get("views", 0))),
                "avg_view_duration_s": round(float(rd.get("averageViewDuration", 0)), 1),
                "avg_view_percentage": round(avg_pct, 1),
                "swipe_away_rate": round(max(0.0, 1.0 - avg_pct / 100.0), 3),
                "estimated_minutes_watched": round(
                    float(rd.get("estimatedMinutesWatched", 0)), 1
                ),
                "likes": int(float(rd.get("likes", 0))),
                "comments": int(float(rd.get("comments", 0))),
                "shares": int(float(rd.get("shares", 0))),
                "subscribers_gained": int(float(rd.get("subscribersGained", 0))),
                "fetched_at": fetched_at,
            }

    return results


def fetch_and_cache(
    video_ids: list[str],
    *,
    min_age_hours: float = 48.0,
    force: bool = False,
    quota_budget: int = DEFAULT_QUOTA_BUDGET,
    channel_id: str | None = None,
) -> dict[str, dict]:
    """
    Fetch metrics for video_ids, using the JSON cache for fresh entries.

    Cached entries are considered stale when older than min_age_hours, so we
    re-pull to get settled metrics. force=True skips the cache entirely.
    Returns {video_id: metrics} for every video that has data.
    """
    cache = load_cache()
    now = datetime.utcnow()
    stale_cutoff = (now - timedelta(hours=min_age_hours)).isoformat()

    to_fetch = [
        vid for vid in video_ids
        if force
        or vid not in cache
        or cache[vid].get("fetched_at", "") < stale_cutoff
    ]

    if to_fetch:
        print(
            f"  [youtube_analytics] fetching {len(to_fetch)} video(s) "
            f"(cache holds {len(cache)})",
            file=sys.stderr,
        )
        fresh = fetch_video_metrics(
            to_fetch,
            channel_id=channel_id,
            quota_budget=quota_budget,
        )
        cache.update(fresh)
        if fresh:
            save_cache(cache)

    return {vid: cache[vid] for vid in video_ids if vid in cache}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import csv

    parser = argparse.ArgumentParser(description="Pull extended analytics for recent videos")
    parser.add_argument("--posts-csv", default=str(ROOT / "data" / "posts.csv"))
    parser.add_argument("--window-days", type=int, default=21)
    parser.add_argument("--min-age-hours", type=float, default=48)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quota-budget", type=int, default=DEFAULT_QUOTA_BUDGET)
    args = parser.parse_args()

    cutoff = (date.today() - timedelta(days=args.window_days)).isoformat()
    posts_path = Path(args.posts_csv)
    if not posts_path.exists():
        print("posts.csv not found", file=sys.stderr)
        sys.exit(1)

    with open(posts_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    video_ids = list(dict.fromkeys(
        r["video_id"]
        for r in rows
        if r.get("date", "") >= cutoff and r.get("video_id")
    ))
    print(f"Pulling metrics for {len(video_ids)} videos in last {args.window_days} days...")

    results = fetch_and_cache(
        video_ids,
        min_age_hours=args.min_age_hours,
        force=args.force,
        quota_budget=args.quota_budget,
    )
    print(json.dumps(results, indent=2))
