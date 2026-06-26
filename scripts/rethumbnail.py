"""
Re-generate and upload custom thumbnails for past videos in posts.csv.

Run once to fix the grayed-out thumbnails on older videos that were posted
before the thumbnail pipeline was working.

Usage:
    python scripts/rethumbnail.py            # re-upload all videos
    python scripts/rethumbnail.py --only-missing  # skip if YouTube already
                                                   # reports a non-default thumb

Requires: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
          (+ PIXABAY_API_KEY or PEXELS_API_KEY for background clips)
"""
import csv
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from backgrounds import fetch_background  # noqa: E402
import render as render_mod               # noqa: E402
from publish import set_thumbnail         # noqa: E402

POSTS_CSV = ROOT / "data" / "posts.csv"


def _extract_hook(row: dict) -> str:
    """Pull the hook from the caption field (first segment before the divider)."""
    caption = row.get("caption", "")
    for sep in [" /  / ", "\n\n", "\r\n\r\n"]:
        if sep in caption:
            first = caption.split(sep)[0].strip().rstrip(".")
            if first:
                return first
    # Fall back to first 60 chars of the quote
    quote = row.get("quote", "")
    return quote[:60].rstrip() if quote else "Stoic wisdom"


def _has_custom_thumbnail(video_id: str) -> bool:
    """Return True if the video already has a non-default custom thumbnail."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        TOKEN_URI = "https://oauth2.googleapis.com/token"
        creds = Credentials(
            token=None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            token_uri=TOKEN_URI,
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
        )
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = yt.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return False
        thumbs = items[0]["snippet"].get("thumbnails", {})
        # YouTube always provides 'default', but 'maxres' only appears after a
        # custom thumbnail is uploaded and processed.
        return "maxres" in thumbs
    except Exception as e:
        print(f"  [check] failed for {video_id}: {e}")
        return False


def main():
    only_missing = "--only-missing" in sys.argv

    if not POSTS_CSV.exists():
        print("posts.csv not found")
        sys.exit(1)

    with open(POSTS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    videos = [r for r in rows if r.get("video_id", "").strip()]
    print(f"Found {len(videos)} videos with IDs in posts.csv")
    if only_missing:
        print("--only-missing: will skip videos that already have a maxres thumbnail")

    success = 0
    skipped = 0
    failed  = 0

    for i, row in enumerate(videos):
        video_id = row["video_id"].strip()
        theme    = row.get("theme", "discipline")
        author   = row.get("author", "Marcus Aurelius")
        hook     = _extract_hook(row)
        date_str = row.get("date", "?")

        print(f"\n[{i+1}/{len(videos)}] {date_str} | {video_id}")
        print(f"  theme={theme}  author={author}")
        print(f"  hook: {hook[:60]}")

        if only_missing and _has_custom_thumbnail(video_id):
            print("  already has custom thumbnail — skipping")
            skipped += 1
            continue

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp       = Path(tmpdir)
            bg_path   = tmp / "bg.mp4"
            thumb_out = tmp / "thumb.jpg"

            try:
                bg = fetch_background(theme, bg_path)
                print(f"  background: {bg.stat().st_size // 1024} KB")
            except Exception as e:
                print(f"  background failed: {e} — skipping")
                failed += 1
                continue

            try:
                t = render_mod.generate_thumbnail(
                    hook=hook, author=author,
                    bg_path=bg, out_path=thumb_out,
                )
                if not t or not t.exists():
                    print("  thumbnail generation returned None — skipping")
                    failed += 1
                    continue
                print(f"  thumbnail: {t.stat().st_size // 1024} KB")
            except Exception as e:
                print(f"  thumbnail generation failed: {e} — skipping")
                failed += 1
                continue

            ok = set_thumbnail(video_id, thumb_out)
            if ok:
                print("  uploaded OK")
                success += 1
            else:
                print("  upload failed (check youtube.force-ssl scope)")
                failed += 1

    print(f"\n=== Done: {success} uploaded, {skipped} skipped, {failed} failed ===")


if __name__ == "__main__":
    main()
