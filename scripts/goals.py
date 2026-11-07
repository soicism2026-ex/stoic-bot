"""
The channel's goal (owner 2026-11-07, in the HQ: "Brainstorm some goal for
this channel for the new year i want to makr something we can work towards
instead if aimlessly trying things").

data/goals.json holds the options asked in the HQ (asks/goal-2027) and the
one the owner chose. This measures every option, every day, from numbers the
bots already keep, so the HQ can show the chosen one the moment he picks it:

  views        views since the goal's start (data/channel_stats.csv, the
               channel's own counter, the same one the HQ's tiles show)
  subscribers  subscribers now
  views_90d    views in the last 90 days (YouTube's payout window)
  best_short   most views on one Short published since the start
               (data/analytics.csv, each Short's latest count)

For each target: what we have, the pace now (the last 28 days), the pace
needed to hit it by its date, and on track or behind; the same for the next
checkpoint (one every three months), so "are we on track?" has a yes or no.

    python scripts/goals.py            # print every option's progress
    python scripts/goals.py --json     # the same as JSON (hq_snapshot.py)

Free: no API, no secrets. Tests: tests/test_goals.py.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GOALS = DATA / "goals.json"
PACE_DAYS = 28            # "the pace now" = the average over the last 4 weeks


def load() -> dict:
    try:
        return json.loads(GOALS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"options": [], "chosen": None}


def _rows(name: str) -> list[dict]:
    p = DATA / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _day(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


class Stats:
    """The channel's counters by day (channel_stats.csv; the last row of a day wins)."""

    def __init__(self, rows: list[dict]):
        self.by_day: dict[str, dict] = {}
        for r in rows:
            if r.get("pulled_on"):
                self.by_day[r["pulled_on"]] = r
        self.days = sorted(self.by_day)

    def num(self, day: str | None, key: str) -> int | None:
        try:
            return int(self.by_day[day][key])
        except (KeyError, TypeError, ValueError):
            return None

    def until(self, day: dt.date) -> "Stats":
        """The counters as they stood at the end of `day`."""
        return Stats([r for d, r in self.by_day.items() if d <= day.isoformat()])

    @property
    def last(self) -> str | None:
        return self.days[-1] if self.days else None

    def before(self, day: dt.date) -> str | None:
        """The last day on record before `day` (its count = the count at `day`'s start)."""
        prior = [d for d in self.days if d < day.isoformat()]
        return prior[-1] if prior else None

    def on_or_after(self, day: dt.date) -> str | None:
        return next((d for d in self.days if d >= day.isoformat()), None)

    def pace(self, key: str, days: int = PACE_DAYS) -> float | None:
        """Gain a day over the last `days` days of records."""
        if not self.last:
            return None
        end = _day(self.last)
        first = self.on_or_after(end - dt.timedelta(days=days))
        a, b = self.num(first, key), self.num(self.last, key)
        n = (end - _day(first)).days if first else 0
        return (b - a) / n if a is not None and b is not None and n > 0 else None


def best_short(analytics: list[dict], since: dt.date) -> tuple[int | None, str | None]:
    """(views, video id) of the most-viewed Short published on or after `since`."""
    latest: dict[str, tuple[str, int, str]] = {}
    for r in analytics:
        vid, pub = r.get("video_id"), (r.get("published_at") or "")[:10]
        try:
            views = int(r.get("views") or 0)
        except ValueError:
            continue
        if vid and pub and pub >= since.isoformat() and (r.get("pulled_on") or "") >= latest.get(vid, ("",))[0]:
            latest[vid] = (r.get("pulled_on") or "", views, vid)
    if not latest:
        return None, None
    _, views, vid = max(latest.values(), key=lambda x: x[1])
    return views, vid


def measure(metric: str, start: dt.date, stats: Stats, analytics: list[dict]) -> int | None:
    last = stats.last
    if metric == "subscribers":
        return stats.num(last, "subscribers")
    if metric == "views":
        if not last or _day(last) < start:
            return 0                                     # not started yet
        base = stats.before(start) or stats.on_or_after(start)
        a, b = stats.num(base, "total_views"), stats.num(last, "total_views")
        return max(0, b - a) if a is not None and b is not None else None
    if metric == "views_90d":
        if not last:
            return None
        base = stats.on_or_after(_day(last) - dt.timedelta(days=90))
        a, b = stats.num(base, "total_views"), stats.num(last, "total_views")
        return max(0, b - a) if a is not None and b is not None else None
    if metric == "best_short":
        return best_short(analytics, start)[0] or 0
    raise ValueError(f"unknown metric {metric}")


def _judge(metric: str, have: int | None, target: int, by: dt.date, start: dt.date,
           today: dt.date, stats: Stats) -> dict:
    """have / pace / needed / status for one target by one date."""
    out: dict = {"metric": metric, "target": target, "have": have}
    out["pct"] = round(min(100.0, 100.0 * (have or 0) / target), 2) if target else None
    pace = needed = None
    if metric in ("views", "views_90d"):
        pace = stats.pace("total_views")
    elif metric == "subscribers":
        pace = stats.pace("subscribers")
    if metric == "views":
        if today < start:
            needed = target / max(1, (by - start).days + 1)          # the average the whole stretch needs
        else:
            needed = (target - (have or 0)) / max(1, (by - today).days)
    elif metric == "subscribers":
        needed = (target - (have or 0)) / max(1, (by - today).days)
    elif metric == "views_90d":
        needed = target / 90                                         # a full window at this daily rate
    out["pace"] = round(pace, 1) if pace is not None else None
    out["needed"] = round(needed, 1) if needed is not None else None
    if have is not None and have >= target:
        out["status"] = "reached"
    elif today > by:
        out["status"] = "missed"
    elif pace is None or needed is None:
        out["status"] = "open"                                       # a single Short: no daily pace
    elif metric == "views" and today < start:
        out["status"] = "starts"                                     # judged on pace from day one
        out["onPace"] = pace >= needed
    else:
        out["status"] = "on track" if pace >= needed else "behind"
    return out


def progress(goal: dict, today: dt.date, stats: Stats, analytics: list[dict]) -> dict:
    start, deadline = _day(goal["start"]), _day(goal["deadline"])
    have = {t["metric"]: measure(t["metric"], start, stats, analytics) for t in goal["targets"]}
    for cp in goal.get("checkpoints", []):
        for t in cp["targets"]:
            have.setdefault(t["metric"], measure(t["metric"], start, stats, analytics))
    labels = {t["metric"]: t.get("label") or t["metric"] for t in goal["targets"]}
    targets = [{**_judge(t["metric"], have[t["metric"]], t["target"], deadline, start, today, stats),
                "label": labels[t["metric"]]} for t in goal["targets"]]
    checkpoints = []
    for cp in goal.get("checkpoints", []):
        by = _day(cp["by"])
        if today > by:      # a passed checkpoint is judged by the numbers on its date
            then = stats.until(by)
            seen = [r for r in analytics if (r.get("pulled_on") or "") <= by.isoformat()]
            have_at = {t["metric"]: measure(t["metric"], start, then, seen) for t in cp["targets"]}
        else:
            have_at = have
        judged = [{**_judge(t["metric"], have_at[t["metric"]], t["target"], by, start, today, stats),
                   "label": labels.get(t["metric"], t["metric"])} for t in cp["targets"]]
        checkpoints.append({"by": cp["by"], "targets": judged, "passed": today > by,
                            "met": all(t["status"] == "reached" for t in judged)})
    nxt = next((c for c in checkpoints if not c["passed"]), None)
    out = {
        "id": goal["id"], "title": goal["title"], "start": goal["start"], "deadline": goal["deadline"],
        "started": today >= start, "daysLeft": max(0, (deadline - today).days),
        "targets": targets, "checkpoints": checkpoints, "next": nxt,
    }
    if "best_short" in have:
        out["bestShortId"] = best_short(analytics, start)[1]
    oks = [_ok(t) for t in (nxt["targets"] if nxt else targets)]
    out["onTrack"] = False if False in oks else (None if None in oks else True)
    return out


def _ok(t: dict) -> bool | None:
    """On track for this target? None when a pace can't tell (one Short's views)."""
    if t["status"] in ("reached", "on track"):
        return True
    if t["status"] in ("behind", "missed"):
        return False
    if t["status"] == "starts":
        return bool(t.get("onPace"))
    return None


def summary(today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    g = load()
    stats, analytics = Stats(_rows("channel_stats.csv")), _rows("analytics.csv")
    return {"ask": g.get("ask"), "chosen": g.get("chosen"), "asOf": stats.last,
            "options": [progress(o, today, stats, analytics) for o in g.get("options", [])]}


def _num(x: float) -> str:
    return f"{x:,.1f}" if abs(x) < 100 else f"{x:,.0f}"


def _line(t: dict) -> str:
    pace = (f", {_num(t['pace'])}/day now vs {_num(t['needed'])} needed"
            if t.get("needed") is not None and t.get("pace") is not None else "")
    have = f"{t['have']:,}" if t["have"] is not None else "–"
    return f"    {t['label']}: {have} of {t['target']:,} ({t['status']}{pace})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    s = summary()
    if ap.parse_args().json:
        print(json.dumps(s, indent=1))
        return 0
    for o in s["options"]:
        mark = "  <- chosen" if o["id"] == s["chosen"] else ""
        print(f"{o['title']} (by {o['deadline']}){mark}")
        for t in o["targets"]:
            print(_line(t))
        if o["next"]:
            print(f"   next checkpoint {o['next']['by']}:")
            for t in o["next"]["targets"]:
                print(_line(t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
