#!/usr/bin/env python3
"""
Pull the AUDIENCE RETENTION CURVE — where, to the second, viewers leave.

THE FEEDBACK PROBLEM: 171 of 229 videos sit at exactly 2 comments, both the
bot's own. About 73 genuine viewer comments exist across the whole channel, so
written feedback is effectively zero and always will be at this size.

But every viewer who scrolls away is giving feedback. `retention.py` records
only the AVERAGE (avg_view_pct), which says how much they watched and not
WHERE they stopped — and those are completely different facts. 55% average
retention could be everyone watching just over half, or half the audience
leaving in the first second. The fix for those two is opposite.

The YouTube Analytics API exposes the curve: `elapsedVideoTimeRatio` against
`audienceWatchRatio`, per video, in 1% steps. That is feedback from every
single viewer, without one of them having to type anything.

    python scripts/retention_curve.py                 # last 10 videos
    python scripts/retention_curve.py --video ID
    python scripts/retention_curve.py --limit 30 --csv

Writes data/retention_curves.csv: video_id, ratio, watch_ratio.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from retention import _analytics_service  # noqa: E402

OUT = ROOT / "data" / "retention_curves.csv"
POSTS = ROOT / "data" / "posts.csv"
FIELDS = ["pulled_on", "video_id", "ratio", "watch_ratio"]

# The moments worth naming when reporting a drop. A viewer lost before 0.10 of
# a 45s video never got past the hook.
LANDMARKS = [
    (0.00, 0.05, "the first 2 seconds — the hook itself"),
    (0.05, 0.15, "the opening line"),
    (0.15, 0.40, "the middle of the story"),
    (0.40, 0.70, "the turn into the lesson"),
    (0.70, 1.01, "the close"),
]


def recent_video_ids(limit: int) -> list[str]:
    if not POSTS.exists():
        return []
    ids = []
    with open(POSTS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = (r.get("video_id") or "").strip()
            if v:
                ids.append(v)
    return list(dict.fromkeys(ids))[-limit:]


def fetch_curve(ya, video_id: str) -> list[tuple[float, float]]:
    """[(elapsed_ratio, watch_ratio)] or [] if unavailable.

    Retention is only reported once a video has enough watch time, so a fresh
    or tiny video legitimately returns nothing. That is not an error.
    """
    today = datetime.date.today().isoformat()
    try:
        resp = ya.reports().query(
            ids="channel==MINE",
            startDate="2020-01-01",
            endDate=today,
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        ).execute()
    except Exception as e:  # noqa: BLE001
        print(f"  [{video_id}] {str(e)[:160]}", file=sys.stderr)
        return []
    return [(float(r[0]), float(r[1])) for r in resp.get("rows", [])]


def describe(curve: list[tuple[float, float]]) -> str:
    """Say in one line where this video loses people."""
    if not curve:
        return "no retention data yet"
    start = curve[0][1] or 1.0
    # Biggest single drop between adjacent samples.
    worst_at, worst_drop = 0.0, 0.0
    for (a, wa), (b, wb) in zip(curve, curve[1:]):
        d = wa - wb
        if d > worst_drop:
            worst_at, worst_drop = b, d
    held = next((w for r, w in curve if r >= 0.05), start)
    lost_in_hook = max(0.0, 1 - held / start) if start else 0.0
    where = next((name for lo, hi, name in LANDMARKS if lo <= worst_at < hi),
                 "the close")
    return (f"{lost_in_hook:.0%} gone by the hook · "
            f"biggest drop at {worst_at:.0%} ({where})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--csv", action="store_true", help="also write the CSV")
    args = ap.parse_args()

    ids = [args.video] if args.video else recent_video_ids(args.limit)
    if not ids:
        print("no videos to check")
        return 0
    try:
        ya = _analytics_service()
    except Exception as e:  # noqa: BLE001
        print(f"analytics auth failed: {e}", file=sys.stderr)
        return 0            # never break a post over a missing signal

    rows, pulled = [], datetime.date.today().isoformat()
    print(f"=== audience retention — where {len(ids)} video(s) lose people ===")
    for vid in ids:
        curve = fetch_curve(ya, vid)
        print(f"  {vid}  {describe(curve)}")
        for ratio, watch in curve:
            rows.append({"pulled_on": pulled, "video_id": vid,
                         "ratio": round(ratio, 3), "watch_ratio": round(watch, 4)})

    if args.csv and rows:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {len(rows)} points to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
