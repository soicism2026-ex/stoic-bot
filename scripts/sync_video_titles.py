"""
Re-sync YouTube video titles to the correct Day-N number.

Run this any time the day counter drifts — after pruning videos, after a
batch of duplicate posts, or whenever YouTube Studio shows the wrong number.

It reads posts.csv to compute each video's correct day (calendar days since
the first post), fetches the current title from YouTube, and calls
videos.update only where the title is wrong.

Usage:
  python scripts/sync_video_titles.py           # live mode: updates YouTube
  python scripts/sync_video_titles.py --dry-run # preview only, no API writes

Requires: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
(same credentials as the daily pipeline — youtube.force-ssl scope).
"""
import csv
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


def _correct_title(day: int, quote: str, author: str) -> str:
    return f"Day {day} | {quote[:55]} — {author}"[:90].rstrip()


def main():
    dry_run = "--dry-run" in sys.argv
    posts_csv = ROOT / "data" / "posts.csv"

    if not posts_csv.exists():
        print("[sync] data/posts.csv not found", file=sys.stderr)
        sys.exit(1)

    with open(posts_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("[sync] posts.csv is empty")
        return

    channel_start = datetime.date.fromisoformat(rows[0]["date"])
    print(f"[sync] channel start: {channel_start}  dry_run={dry_run}")

    # Build video_id → (correct_day, quote, author) using first occurrence only
    videos: dict[str, dict] = {}
    for row in rows:
        vid = row.get("video_id", "").strip()
        if not vid or vid in videos:
            continue
        row_date = datetime.date.fromisoformat(row["date"])
        day = (row_date - channel_start).days + 1
        videos[vid] = {
            "day":    day,
            "quote":  row.get("quote", ""),
            "author": row.get("author", ""),
        }

    if not videos:
        print("[sync] no videos found in posts.csv")
        return

    if dry_run:
        print(f"[sync] would check {len(videos)} video(s):")
        for vid, m in videos.items():
            print(f"  {vid}  Day {m['day']}  →  {_correct_title(m['day'], m['quote'], m['author'])}")
        return

    yt = _service()

    # Fetch current titles in batches of 50
    ids = list(videos)
    current: dict[str, dict] = {}  # video_id → full snippet
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        resp = yt.videos().list(part="snippet", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            current[item["id"]] = item["snippet"]

    updated = skipped = missing = 0
    for vid, m in videos.items():
        target = _correct_title(m["day"], m["quote"], m["author"])
        if vid not in current:
            print(f"  [missing] {vid} — not found on YouTube (deleted or private)")
            missing += 1
            continue
        snippet = current[vid]
        if snippet["title"] == target:
            print(f"  [ok]     {vid}  {target[:60]}")
            skipped += 1
            continue
        print(f"  [fix]    {vid}")
        print(f"           was: {snippet['title']}")
        print(f"           now: {target}")
        snippet["title"] = target
        yt.videos().update(part="snippet", body={"id": vid, "snippet": snippet}).execute()
        updated += 1

    print(f"\n[sync] done — {updated} updated, {skipped} already correct, {missing} not found")


if __name__ == "__main__":
    main()
