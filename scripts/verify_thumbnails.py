"""
Diagnostic: print the current thumbnail URL for every video in posts.csv.

Usage:
    python scripts/verify_thumbnails.py

Requires YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN
in the environment (same as the daily post).

Output tells us:
  - whether YouTube has a custom thumbnail set (URL contains the video ID in a
    signed/hashed path) vs a plain auto-generated frame (sqp= or default.jpg)
  - whether the thumbnail looks like the gold-hook card we generated (hi-res)
    or just a 120px default frame
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from publish import _service  # noqa: E402

POSTS = ROOT / "data" / "posts.csv"


def main() -> int:
    if not POSTS.exists():
        print(f"posts.csv not found at {POSTS}", file=sys.stderr)
        return 1

    with open(POSTS, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    seen: set[str] = set()
    video_ids = []
    for row in rows:
        vid = (row.get("video_id") or "").strip()
        if vid and vid not in seen:
            seen.add(vid)
            video_ids.append(vid)

    if not video_ids:
        print("No video IDs found in posts.csv")
        return 1

    yt = _service()

    # YouTube videos.list accepts up to 50 IDs per call.
    CHUNK = 50
    custom_count = default_count = missing_count = 0

    for i in range(0, len(video_ids), CHUNK):
        chunk = video_ids[i:i + CHUNK]
        resp = yt.videos().list(
            part="snippet,status",
            id=",".join(chunk),
        ).execute()

        found_ids = {item["id"] for item in resp.get("items", [])}
        for vid in chunk:
            if vid not in found_ids:
                print(f"  {vid}  NOT FOUND / not owned")
                missing_count += 1
                continue
            item = next(x for x in resp["items"] if x["id"] == vid)
            thumbs = item.get("snippet", {}).get("thumbnails", {})
            title  = item.get("snippet", {}).get("title", "")[:60]
            status = item.get("status", {}).get("privacyStatus", "?")

            # maxresdefault is only present when a custom thumbnail was uploaded.
            # standard / high are present on both but have different sizes.
            maxres = thumbs.get("maxres", {})
            high   = thumbs.get("high",   {})
            url    = (maxres or high).get("url", "")
            w      = (maxres or high).get("width",  0)
            h      = (maxres or high).get("height", 0)

            # Heuristic: custom thumbnails are always maxres (1280×720 or larger).
            # YouTube's auto-generated ones top out at 480×360 (high) unless a
            # custom thumbnail was set.
            if maxres:
                label = "CUSTOM (maxres)"
                custom_count += 1
            elif w >= 1280:
                label = "CUSTOM (large high)"
                custom_count += 1
            else:
                label = f"AUTO-GENERATED ({w}x{h})"
                default_count += 1

            print(f"  {vid}  [{status:8s}]  {label:25s}  {url[:80]}")
            print(f"           title: {title}")

    print(
        f"\nSummary: {len(video_ids)} videos | "
        f"custom={custom_count} | auto-generated={default_count} | "
        f"not found={missing_count}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
