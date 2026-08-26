#!/usr/bin/env python3
"""
Re-list videos that prune_videos.py unlisted. Dry-run by default.

WHY: 222 posts are logged but the channel reports 133 public videos. 89 are
unlisted, and the sum of per-video peak views (72,703) exceeds the channel
total (58,641) by 14,062 — views that were earned and are no longer counted.

The pruner that hid them was working from broken inputs. analytics.py had
MAX_VIDEOS=15, so at 3 posts/day every video aged out of the analytics window
in ~5 days, while PRUNE_MIN_AGE_DAYS was 7. It judged every video on a view
count frozen BEFORE it was old enough to be judged, then unlisted it for
underperforming. Pruning was disabled on 2026-08-14 but nothing was restored.

Unlisted views do not count toward the YouTube Partner Program threshold, so
this is the cheapest view recovery available: no rendering, no uploading, no
new content — just un-hiding work that already exists.

    python scripts/relist_videos.py                # dry run, lists what it would do
    python scripts/relist_videos.py --apply        # actually re-list
    python scripts/relist_videos.py --apply --limit 50

Quota: videos.update costs 50 units each against 10,000/day, so 89 videos is
4,450 units — most of a day's budget. --limit exists to spread it over two
days without starving the uploads, which cost 1,600 each.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

POSTS = ROOT / "data" / "posts.csv"
UPLOAD_COST = 1600
UPDATE_COST = 50
DAILY_QUOTA = 10_000


def _service():
    from publish import _service as svc
    return svc()


def logged_video_ids() -> list[str]:
    if not POSTS.exists():
        return []
    out, seen = [], set()
    with open(POSTS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            vid = (r.get("video_id") or "").strip()
            if vid and vid not in seen:
                seen.add(vid)
                out.append(vid)
    return out


def privacy_of(yt, ids: list[str]) -> dict[str, str]:
    """Map video_id -> privacyStatus. videos.list costs 1 unit per call."""
    out: dict[str, str] = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        resp = yt.videos().list(part="status,snippet",
                                id=",".join(chunk)).execute()
        for item in resp.get("items", []):
            out[item["id"]] = item.get("status", {}).get("privacyStatus", "?")
    return out


def relist(yt, video_id: str) -> bool:
    try:
        yt.videos().update(
            part="status",
            body={"id": video_id, "status": {"privacyStatus": "public"}},
        ).execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED {video_id}: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually re-list; without it this only reports")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap how many to re-list this run (quota safety)")
    args = ap.parse_args()

    ids = logged_video_ids()
    if not ids:
        print("no video ids in posts.csv")
        return 0
    print(f"{len(ids)} videos logged in posts.csv")

    yt = _service()
    status = privacy_of(yt, ids)
    missing = [v for v in ids if v not in status]
    hidden = [v for v in ids if status.get(v) in ("unlisted", "private")]
    public = [v for v in ids if status.get(v) == "public"]

    print(f"  public   : {len(public)}")
    print(f"  unlisted/private: {len(hidden)}")
    if missing:
        print(f"  not found (deleted?): {len(missing)}")

    if not hidden:
        print("nothing to re-list")
        return 0

    todo = hidden[:args.limit] if args.limit else hidden
    cost = len(todo) * UPDATE_COST
    print(f"\n{len(todo)} to re-list  ({cost:,} quota units; "
          f"{DAILY_QUOTA - 3 * UPLOAD_COST:,} available after 3 uploads)")
    if cost > DAILY_QUOTA - 3 * UPLOAD_COST:
        print("  WARNING: this exceeds the budget left after today's uploads. "
              "Use --limit to spread it across days; a lost upload costs more "
              "than a day's delay in re-listing.")

    for v in todo[:10]:
        print(f"  {'RELIST' if args.apply else ' would'} {v}  "
              f"({status.get(v)})")
    if len(todo) > 10:
        print(f"  ... and {len(todo) - 10} more")

    if not args.apply:
        print("\nDRY RUN — nothing changed. Re-run with --apply.")
        return 0

    ok = sum(relist(yt, v) for v in todo)
    print(f"\nre-listed {ok}/{len(todo)}")
    return 0 if ok == len(todo) else 1


if __name__ == "__main__":
    raise SystemExit(main())
