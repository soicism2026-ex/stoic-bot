#!/usr/bin/env python3
"""
Runs and reads the 20-video format test (see data/format_test.md).

The test asks ONE question: does any video exceed 5,000 views — 4x the best
this channel has ever made in 210 attempts. Not medians; five videos cannot
establish a median, and a tidy leaderboard at the end would tempt someone into
believing one.

    python scripts/format_test.py --next     # which format the next post uses
    python scripts/format_test.py            # read the result so far
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.csv"
ANALYTICS = ROOT / "data" / "analytics.csv"

# Interleaved, never blocked: five F1s in a row would confound the format with
# the day, the time slot, and whatever the algorithm was doing that afternoon.
ORDER = ["first_person", "the_screen", "the_question", "the_countdown"]
# Only formats that are actually BUILT can be scheduled. The owner picked F3
# first, so it is the only arm live; next_format() must not claim otherwise or
# the tooling is lying about what is running.
BUILT = {"the_question"}
PER_FORMAT = 5
BREAKOUT = 5_000
# The bar is 4x the channel's all-time best (1,255 over 210 videos). Anything
# lower sits inside existing noise and would let a fluke read as a win.
ALLTIME_BEST = 1_255


def _test_rows() -> list:
    """Posts whose `experiment` column marks them as part of this test."""
    if not POSTS.exists():
        return []
    with open(POSTS, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if (r.get("experiment") or "").startswith("ftest:")]


def _peak_views() -> dict:
    peak: dict = defaultdict(int)
    if not ANALYTICS.exists():
        return peak
    with open(ANALYTICS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = (r.get("video_id") or "").strip()
            if v:
                peak[v] = max(peak[v], int(r.get("views") or 0))
    return peak


def next_format() -> str | None:
    """The format the next post should use, or None when the test is complete."""
    live = [f for f in ORDER if f in BUILT]
    if not live:
        return None
    done = _test_rows()
    if len(done) >= PER_FORMAT * len(live):
        return None
    return live[len(done) % len(live)]


def main(argv: list | None = None) -> int:
    # argv is a parameter so tests can call main() without argparse swallowing
    # pytest's own command line. A script that can only be exercised through a
    # subprocess tends not to get exercised.
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--next", action="store_true",
                    help="print the format for the next post and exit")
    args = ap.parse_args([] if argv is None and "pytest" in sys.modules else argv)

    if args.next:
        nxt = next_format()
        print(nxt or "COMPLETE")
        return 0

    rows = _test_rows()
    peak = _peak_views()
    live = [f for f in ORDER if f in BUILT]
    total = PER_FORMAT * max(1, len(live))
    print(f"=== Format test: {len(rows)}/{total} posts ===")
    print(f"    breakout bar: {BREAKOUT:,} views "
          f"({BREAKOUT / ALLTIME_BEST:.1f}x the all-time best of {ALLTIME_BEST:,})\n")
    if not rows:
        print("  not started — set experiment='ftest:<format>' on posts")
        return 0

    by = defaultdict(list)
    for r in rows:
        fmt = (r.get("experiment") or "").split(":", 1)[-1]
        by[fmt].append(peak.get((r.get("video_id") or "").strip(), 0))

    breakouts = 0
    for fmt in ORDER:
        v = by.get(fmt, [])
        if not v:
            state = "not run yet" if fmt in BUILT else "NOT BUILT"
            print(f"  {fmt:14} — {state}")
            continue
        best = max(v)
        hit = best >= BREAKOUT
        breakouts += sum(1 for x in v if x >= BREAKOUT)
        flag = "  <-- BREAKOUT" if hit else ""
        print(f"  {fmt:14} n={len(v)}  best={best:6,}  "
              f"all={sorted(v, reverse=True)}{flag}")

    print()
    if len(rows) < total:
        print(f"  incomplete — {total - len(rows)} posts to go. Do not read "
              f"medians off partial data.")
        return 0
    if breakouts:
        print(f"  RESULT: {breakouts} breakout(s). Drop the rest, make 20 more "
              f"of the winner.")
    else:
        print("  RESULT: no breakouts in 20 videos across 4 genuinely different\n"
              "  formats. The FORMAT was never the problem — positioning or\n"
              "  niche is. Stop tuning Stoicism quote Shorts and reconsider\n"
              "  what this channel is. That is the finding worth having.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
