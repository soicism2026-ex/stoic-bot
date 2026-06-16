"""
Unlist a specific video and remove its row from posts.csv.

Usage:
  python scripts/remove_post.py --video-id VIDEO_ID

Requires: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
"""
import argparse
import csv
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    vid = args.video_id.strip()

    posts_csv = ROOT / "data" / "posts.csv"
    if not posts_csv.exists():
        print("[remove] posts.csv not found", file=sys.stderr)
        sys.exit(1)

    with open(posts_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    matched = [r for r in rows if r.get("video_id") == vid]
    remaining = [r for r in rows if r.get("video_id") != vid]

    if not matched:
        print(f"[remove] video_id {vid} not found in posts.csv — unlisting anyway")
    else:
        for r in matched:
            print(f"[remove] removing from posts.csv: {r['date']} {r['quote'][:50]}")

    if args.dry_run:
        print("[remove] dry-run — no changes made")
        return

    if not args.dry_run:
        try:
            yt = _service()
            yt.videos().update(
                part="status",
                body={"id": vid, "status": {"privacyStatus": "unlisted"}},
            ).execute()
            print(f"[remove] unlisted {vid} on YouTube")
        except Exception as e:
            # videos.update requires the youtube.force-ssl scope. If the
            # refresh token was issued before that scope was added to
            # auth_setup.py, Google rejects it at refresh time with
            # invalid_scope rather than at the API call — non-fatal here so
            # a repost can still proceed; unlist manually in YouTube Studio
            # and re-run src/auth_setup.py to mint a token that covers it.
            print(
                f"[remove] could not unlist {vid} on YouTube ({e}) — "
                f"continuing without unlisting. Re-run src/auth_setup.py to "
                f"refresh YOUTUBE_REFRESH_TOKEN with the force-ssl scope, "
                f"then unlist {vid} manually in the meantime.",
                file=sys.stderr,
            )

    if matched:
        fieldnames = list(rows[0].keys())
        with open(posts_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(remaining)
        print(f"[remove] posts.csv updated ({len(remaining)} rows remaining)")


if __name__ == "__main__":
    main()
