#!/usr/bin/env python3
"""
Actual vs target, against data/roadmap.md. Run it any time.

A roadmap nobody measures is a wish. This prints where the channel really is
against the monthly targets, names the next milestone, and fires the tripwires
from the roadmap when they trip — including the uncomfortable ones, because a
plan that only reports good news is worse than no plan.

    python scripts/goal_check.py
"""
from __future__ import annotations

import csv
import datetime
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "data" / "channel_stats.csv"
POSTS = ROOT / "data" / "posts.csv"
ANALYTICS = ROOT / "data" / "analytics.csv"

# (date, subs_base, views_per_day_base) — from data/roadmap.md.
MILESTONES = [
    ("2026-09-19", 280, 500),
    ("2026-10-19", 330, 800),
    ("2026-11-19", 385, 1200),
    ("2026-12-19", 435, 1800),
    ("2027-01-19", 500, 2500),
]

OK = "\033[32mon track\033[0m"
BEHIND = "\033[33m behind \033[0m"
WARN = "\033[31m  WARN  \033[0m"


def _stats() -> dict:
    out = {}
    if not STATS.exists():
        return out
    with open(STATS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out[r["pulled_on"]] = (int(r["subscribers"] or 0),
                                       int(r["total_views"] or 0))
            except (ValueError, TypeError):
                continue
    return out


def _rate(stats: dict, days: int) -> tuple:
    """(subs/day, views/day) over the last `days`, or (0,0) if too little data."""
    ds = sorted(stats)
    if len(ds) <= days:
        return 0.0, 0.0
    a, b = stats[ds[-1 - days]], stats[ds[-1]]
    return (b[0] - a[0]) / days, (b[1] - a[1]) / days


def _median_1day_views() -> float:
    """Median views at ~1 day old for the last 10 posts — the tripwire metric."""
    if not (POSTS.exists() and ANALYTICS.exists()):
        return -1.0
    snaps, pub = defaultdict(dict), {}
    with open(ANALYTICS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = (r.get("video_id") or "").strip()
            if not v:
                continue
            if r.get("published_at"):
                pub[v] = r["published_at"][:10]
            if r.get("pulled_on"):
                snaps[v][r["pulled_on"]] = max(snaps[v].get(r["pulled_on"], 0),
                                               int(r.get("views") or 0))
    vals = []
    with open(POSTS, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    for r in rows[-12:]:
        v = r[6] if len(r) > 6 else ""
        if v not in pub:
            continue
        p = datetime.date.fromisoformat(pub[v])
        for d, n in sorted(snaps[v].items()):
            if (datetime.date.fromisoformat(d) - p).days >= 1:
                vals.append(n)
                break
    return st.median(vals) if vals else -1.0


def main() -> int:
    stats = _stats()
    if not stats:
        print("no channel_stats.csv", file=sys.stderr)
        return 1
    today = sorted(stats)[-1]
    subs, views = stats[today]
    ds, dv = _rate(stats, 7)

    print(f"=== Goal check ({today}) ===")
    print(f"  {subs} subs   {views:,} all-time views")
    print(f"  7-day rate: {ds:+.2f} subs/day   {dv:+.0f} views/day")
    print(f"  90-day view pace: {dv * 90:,.0f}\n")

    nxt = next((m for m in MILESTONES if m[0] > today), None)
    if nxt:
        date, t_subs, t_views = nxt
        left = (datetime.date.fromisoformat(date)
                - datetime.date.fromisoformat(today)).days
        proj = subs + ds * left
        tag = OK if proj >= t_subs else BEHIND
        print(f"  NEXT MILESTONE {date} ({left} days)")
        print(f"    [{tag}] subs      {subs} -> projected {proj:.0f}  target {t_subs}")
        tag = OK if dv >= t_views else BEHIND
        print(f"    [{tag}] views/day {dv:.0f}  target {t_views}")

    # YPP reality check — the number most likely to be misremembered as close.
    need = 3_000_000 / 90
    print(f"\n  YPP views: need {need:,.0f}/day, at {dv:.0f} "
          f"-> {need / max(dv, 1):.0f}x short")
    print(f"  YPP subs : {max(0, 500 - subs)} to go"
          + (f", ~{max(0, 500 - subs) / ds:.0f} days at this rate" if ds > 0 else ""))

    print("\n  TRIPWIRES")
    fired = []
    m1 = _median_1day_views()
    if m1 >= 0:
        if today >= "2026-08-24" and m1 < 100:
            fired.append(f"1-day median is {m1:.0f} (<100) past 2026-08-24 — the "
                         f"repetition theory is WRONG. Change theory, do not "
                         f"defend it.")
        else:
            print(f"    [{OK}] 1-day median views: {m1:.0f}")
    if ds < 0:
        fired.append("subscriber growth is NEGATIVE — something is actively "
                     "repelling viewers. Audit tone against doctrine section 5 "
                     "before touching anything else.")
    for f in fired:
        print(f"    [{WARN}] {f}")
    if not fired:
        print("    no tripwires fired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
