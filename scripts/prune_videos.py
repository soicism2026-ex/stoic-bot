"""
Unlist (or delete) YouTube videos that have under-performed.

After MIN_AGE_DAYS days, any video with fewer than VIEW_THRESHOLD views is
unlisted — hidden from the channel page but not permanently deleted. Delete
mode is available via PRUNE_ACTION=delete but is irreversible.

Config via environment variables (all optional):
  PRUNE_VIEW_THRESHOLD  — minimum views to keep; default 300
  PRUNE_MIN_AGE_DAYS    — how many days to wait before judging; default 7
  PRUNE_ACTION          — "unlist" (default) or "delete"

Reads data/analytics.csv for the latest view counts. Run after analytics.py
so data is fresh.

Requires YOUTUBE_* credentials with the youtube.force-ssl scope
(needed for videos.update / videos.delete). If the current token lacks
this scope the step skips gracefully with re-auth instructions:
  python src/auth_setup.py
"""
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VIEW_THRESHOLD = int(os.environ.get("PRUNE_VIEW_THRESHOLD", "300"))
MIN_AGE_DAYS   = int(os.environ.get("PRUNE_MIN_AGE_DAYS",   "7"))
ACTION         = os.environ.get("PRUNE_ACTION", "unlist").lower()

TOKEN_URI = "https://oauth2.googleapis.com/token"


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _load_latest_views() -> dict[str, dict]:
    """Return {video_id: {views, published_at, title}} using each video's peak."""
    path = ROOT / "data" / "analytics.csv"
    if not path.exists():
        print("[prune] data/analytics.csv not found — skipping", file=sys.stderr)
        return {}
    latest: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            if not vid:
                continue
            views = int(row.get("views") or 0)
            if vid not in latest or views > latest[vid]["views"]:
                latest[vid] = {
                    "views":        views,
                    "published_at": row.get("published_at", ""),
                    "title":        row.get("title", ""),
                    "url":          row.get("url", ""),
                }
    return latest


def _age_days(published_at: str) -> float:
    if not published_at:
        return 0.0
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - pub).total_seconds() / 86400
    except Exception:
        return 0.0


def _unlist(yt, video_id: str) -> bool:
    yt.videos().update(
        part="status",
        body={"id": video_id, "status": {"privacyStatus": "unlisted"}},
    ).execute()
    return True


def _delete(yt, video_id: str) -> bool:
    yt.videos().delete(id=video_id).execute()
    return True


def main():
    print(f"[prune] threshold={VIEW_THRESHOLD}v  min_age={MIN_AGE_DAYS}d  action={ACTION}")

    all_stats = _load_latest_views()
    if not all_stats:
        return

    candidates = [
        (vid, data) for vid, data in all_stats.items()
        if _age_days(data["published_at"]) >= MIN_AGE_DAYS
        and data["views"] < VIEW_THRESHOLD
    ]

    if not candidates:
        print(f"[prune] no videos qualify (age≥{MIN_AGE_DAYS}d AND views<{VIEW_THRESHOLD})")
        return

    print(f"[prune] {len(candidates)} video(s) qualify:")
    for vid, d in candidates:
        print(f"  {vid}  {d['views']:>5}v  {_age_days(d['published_at']):.1f}d  {d['title'][:55]}")

    try:
        yt = _service()
    except Exception as e:
        if "invalid_scope" in str(e) or "scope" in str(e).lower():
            print(
                "[prune] SKIP — token lacks youtube.force-ssl scope.\n"
                "  Re-run: python src/auth_setup.py  (then update YOUTUBE_REFRESH_TOKEN secret)",
                file=sys.stderr,
            )
        else:
            print(f"[prune] YouTube auth failed: {e}", file=sys.stderr)
        return

    fn = _delete if ACTION == "delete" else _unlist
    done = 0
    for vid, data in candidates:
        try:
            fn(yt, vid)
            print(f"  [{ACTION}d] {vid} — {data['title'][:55]}")
            done += 1
        except Exception as e:
            print(f"  [error] {vid}: {e}", file=sys.stderr)

    print(f"[prune] {ACTION}d {done}/{len(candidates)} videos")


if __name__ == "__main__":
    main()
