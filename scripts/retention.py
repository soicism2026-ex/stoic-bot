"""
Retention agent — pulls the REAL Shorts ranking signal: average view duration
and average view percentage per video, via the YouTube Analytics API.

Views (what analytics.py pulls from the Data API) is a lagging, weak signal.
The algorithm promotes Shorts on RETENTION — how much of each video people
actually watch. This agent surfaces that so content can be optimised for what
the algorithm rewards, not just raw views.

Writes data/retention.csv:  pulled_on, video_id, views, avg_view_seconds, avg_view_pct

IMPORTANT — one-time setup: the Analytics API needs the extra OAuth scope
    https://www.googleapis.com/auth/yt-analytics.readonly
which older refresh tokens do NOT have. If you see a 403 / insufficient scope
below, re-run  python src/auth_setup.py  (it now requests that scope) and update
YOUTUBE_REFRESH_TOKEN. Until then this exits cleanly and changes nothing.
"""
import csv
import datetime
import os
import sys
from pathlib import Path

TOKEN_URI = "https://oauth2.googleapis.com/token"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "retention.csv"
FIELDS = ["pulled_on", "video_id", "views", "avg_view_seconds", "avg_view_pct"]

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _analytics_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def fetch_retention() -> list[dict]:
    """Query per-video retention. Returns [] (and prints guidance) on any error,
    so this can run in the pipeline without ever breaking a build."""
    try:
        ya = _analytics_service()
        today = datetime.date.today().isoformat()
        resp = ya.reports().query(
            ids="channel==MINE",
            startDate="2020-01-01",
            endDate=today,
            metrics="views,averageViewDuration,averageViewPercentage",
            dimensions="video",
            sort="-views",
            maxResults=200,
        ).execute()
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        # Same 403, two different fixes — name the right one in the log.
        if "accessnotconfigured" in low or "has not been used" in low or "is disabled" in low:
            print(
                "[retention] CAUSE=API_DISABLED — the 'YouTube Analytics API' is "
                "not enabled in Google Cloud Console (note: the 'YouTube Reporting "
                "API' is a different product). Enable: APIs & Services > Library > "
                "'YouTube Analytics API' > Enable. Skipping for now.",
                file=sys.stderr,
            )
        elif "insufficient" in low or "scope" in low or "invalid_scope" in low:
            print(
                "[retention] CAUSE=TOKEN_SCOPE — the refresh token lacks "
                "yt-analytics.readonly. Run 'git pull' FIRST (an old auth_setup.py "
                "does not request the scope), then re-run 'python src/auth_setup.py' "
                "and update YOUTUBE_REFRESH_TOKEN. Skipping for now.",
                file=sys.stderr,
            )
        else:
            print(f"[retention] pull failed ({msg[:300]}); skipping.", file=sys.stderr)
        return []

    rows = []
    for r in resp.get("rows", []):
        # columns follow the metrics order: video, views, avgDuration, avgPct
        vid, views, avg_sec, avg_pct = r[0], r[1], r[2], r[3]
        rows.append({
            "video_id": vid,
            "views": int(views or 0),
            "avg_view_seconds": round(float(avg_sec or 0), 1),
            "avg_view_pct": round(float(avg_pct or 0), 1),
        })
    return rows


def write_rows(rows: list[dict]) -> None:
    pulled = datetime.date.today().isoformat()
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            r["pulled_on"] = pulled
            w.writerow(r)


# Below this many views, averageViewPercentage is a handful of sessions and
# swings wildly — one viewer leaving a Short looping produces figures like the
# 2128% this line used to headline. Matches content._winning_hooks(min_views).
REPORT_MIN_VIEWS = 60
# Shorts loop, so >100% is normal and real. Past this it is a freak session,
# not a signal. Same ceiling content.py caps the feedback list at.
PLAUSIBLE_MAX_PCT = 300.0


def report_line(rows: list[dict]) -> str:
    """A headline that means something.

    This used to print max(avg_view_pct) over every row, which reported
    "Best retention: qzLbKJVZfbw at 2128.7%" — a 108-view video someone left
    looping. It reads as a broken pipeline and sent me hunting a bug that was
    not there, while saying nothing about how the channel is doing. The
    content engine already ignores rows like that; the log should too.
    """
    usable = [r for r in rows
              if int(r.get("views") or 0) >= REPORT_MIN_VIEWS
              and r["avg_view_pct"] <= PLAUSIBLE_MAX_PCT]
    head = f"[retention] wrote {len(rows)} rows to {OUT.name}."
    if not usable:
        return f"{head} No video yet has {REPORT_MIN_VIEWS}+ views at a " \
               f"plausible retention — nothing to rank."
    best = max(usable, key=lambda r: r["avg_view_pct"])
    excluded = len(rows) - len(usable)
    return (f"{head} Best retention (>={REPORT_MIN_VIEWS} views): "
            f"{best['video_id']} at {best['avg_view_pct']}% "
            f"on {best['views']} views. {excluded} row(s) excluded as "
            f"low-sample or implausible.")


def main():
    rows = fetch_retention()
    if not rows:
        print("[retention] no data written.")
        return
    write_rows(rows)
    print(report_line(rows))


if __name__ == "__main__":
    main()
