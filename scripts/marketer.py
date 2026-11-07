"""
Cicero, the marketer (owner 2026-11-03: "Hire a marketing professional").

Frontinus (scripts/strategist.py) reads what the CONTENT does. Cicero works
on how the channel REACHES people: when the Shorts go out, how they are
packaged, how viewers turn into subscribers. Free: he reads numbers the bots
already keep (channel_stats.csv, analytics.csv, posts.csv), no paid API.

Every day (.github/workflows/marketing.yml) he writes data/marketing.md for
people and data/marketing.json for the HQ:

  1. the funnel: views a day this week against last week, subscribers a day,
     subscribers per 1,000 views, likes per 100 views
  2. reach by upload hour: each Short against the Shorts of its own week
     (reach swung tenfold between seasons, so raw views would blame the
     season), by UTC hour band
  3. his tests (data/marketing_tests.json): one change at a time, each with
     the question, the change, why, how it is judged and the verdict. A test
     ships only after the owner says yes in the HQ (owner's rule: "dont ship
     anything until i approve it"); Cicero proposes, measures and reports.

    python scripts/marketer.py            # print the read
    python scripts/marketer.py --write    # write data/marketing.{md,json}
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TESTS = DATA / "marketing_tests.json"
REPORT_MD = DATA / "marketing.md"
REPORT_JSON = DATA / "marketing.json"

NEIGHBOUR_DAYS = 7        # a Short is compared with the Shorts aired within a week of it
MIN_NEIGHBOURS = 4
BANDS = [(0, 3), (4, 7), (8, 11), (12, 15), (16, 19), (20, 23)]
TEST_DAYS = 14            # how long a test runs before its verdict
MIN_TEST_DAYS = 7         # days with both Shorts needed for a verdict
WIN, LOSE = 1.2, 0.85     # the change in the median that counts as a win / a loss
# The line every description in the owner's style ends its paragraphs with
# (src/edits.py QUESTION_MARK, tests/test_marketer.py keeps them equal):
# posts.csv's caption column is the full description, so it tells a Short in
# the new style from one in the old.
NEW_STYLE = "\U0001F4AC Question:"


def _rows(name: str) -> list[dict]:
    p = DATA / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _day(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


# ---------------------------------------------------------------- the numbers

class Views:
    """Each Short's upload time and its views at a given age, from analytics.csv."""

    def __init__(self, analytics: list[dict]):
        self.published: dict[str, dt.datetime] = {}
        self.snaps: dict[str, dict[str, int]] = defaultdict(dict)
        self.latest: dict[str, tuple[str, int, int]] = {}
        for r in analytics:
            v = (r.get("video_id") or "").strip()
            if not v:
                continue
            if r.get("published_at"):
                try:
                    self.published[v] = dt.datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            try:
                n = int(r.get("views") or 0)
                likes = int(r.get("likes") or 0)
            except ValueError:
                continue
            day = r.get("pulled_on") or ""
            if day:
                self.snaps[v][day] = max(self.snaps[v].get(day, 0), n)
                if day >= self.latest.get(v, ("", 0, 0))[0]:
                    self.latest[v] = (day, n, likes)

    def at_age(self, video: str, days: int = 1) -> int | None:
        """Views at the first snapshot at least `days` after upload."""
        pub = self.published.get(video)
        if pub is None:
            return None
        for day, n in sorted(self.snaps.get(video, {}).items()):
            if (_day(day) - pub.date()).days >= days:
                return n
        return None


def funnel(stats: list[dict], views: Views, today: dt.date) -> dict:
    """This week against last week, from the daily channel totals."""
    by_day: dict[str, tuple[int, int]] = {}
    for r in stats:
        try:
            by_day[r["pulled_on"]] = (int(r.get("subscribers") or 0), int(r.get("total_views") or 0))
        except (KeyError, ValueError):
            continue
    days = sorted(d for d in by_day if _day(d) <= today)

    def window(end: int, length: int = 7):
        if end - length < 0:
            return None
        a, b = by_day[days[end - length]], by_day[days[end]]
        span = max(1, (_day(days[end]) - _day(days[end - length])).days)
        return {"views": (b[1] - a[1]) / span, "subs": (b[0] - a[0]) / span}

    now = window(len(days) - 1)
    before = window(len(days) - 8)
    recent = [v for v, pub in views.published.items() if 0 <= (today - pub.date()).days <= 14]
    seen = [views.latest[v] for v in recent if v in views.latest]
    total_views = sum(x[1] for x in seen)
    out = {
        "asOf": days[-1] if days else None,
        "subscribers": by_day[days[-1]][0] if days else None,
        "viewsPerDay": round(now["views"]) if now else None,
        "viewsPerDayBefore": round(before["views"]) if before else None,
        "subsPerDay": round(now["subs"], 1) if now else None,
        "subsPerDayBefore": round(before["subs"], 1) if before else None,
        "subsPer1kViews": round(1000 * now["subs"] / now["views"], 1) if now and now["views"] > 0 else None,
        "likesPer100Views": round(100 * sum(x[2] for x in seen) / total_views, 1) if total_views else None,
    }
    if out["viewsPerDay"] is not None and out["viewsPerDayBefore"]:
        out["viewsChange"] = round(out["viewsPerDay"] / out["viewsPerDayBefore"] - 1, 2)
    return out


def hour_bands(posts: list[dict], views: Views) -> list[dict]:
    """Each Short's day-1 views against the median of the Shorts aired within
    a week of it, grouped by UTC upload hour."""
    items = []
    for r in posts:
        v = r.get("video_id")
        pub = views.published.get(v or "")
        n = views.at_age(v or "", 1)
        if pub is not None and n is not None:
            items.append((pub, n))
    lifts: dict[int, list[float]] = defaultdict(list)
    for pub, n in items:
        nb = [m for t, m in items if t != pub and abs((t - pub).total_seconds()) <= NEIGHBOUR_DAYS * 86400]
        if len(nb) < MIN_NEIGHBOURS:
            continue
        band = next(i for i, (lo, hi) in enumerate(BANDS) if lo <= pub.hour <= hi)
        lifts[band].append(n / max(st.median(nb), 1))
    return [{"band": f"{lo:02d}-{hi:02d}", "posts": len(lifts[i]), "lift": round(st.median(lifts[i]), 2),
             "stalled": sum(1 for x in lifts[i] if x < 0.4)}
            for i, (lo, hi) in enumerate(BANDS) if lifts[i]]


def second_vs_first(posts: list[dict], views: Views, since: dt.date, until: dt.date) -> list[dict]:
    """For each day in [since, until) with two Shorts: the later one's day-1
    views over the earlier one's. The earlier Short is the day's control."""
    by_day: dict[str, list[str]] = defaultdict(list)
    for r in posts:
        v = r.get("video_id")
        if v and v in views.published and since <= _day(r["date"]) < until:
            by_day[r["date"]].append(v)
    out = []
    for day in sorted(by_day):
        if len(by_day[day]) != 2:
            continue
        first, second = sorted(by_day[day], key=lambda v: views.published[v])
        a, b = views.at_age(first, 1), views.at_age(second, 1)
        if a and b is not None:
            out.append({"date": day, "ratio": round(b / a, 2), "first": a, "second": b,
                        "secondAt": views.published[second].strftime("%H:%M")})
    return out


# ---------------------------------------------------------------- the tests

def load_tests() -> dict:
    try:
        return json.loads(TESTS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"tests": [], "next": []}


def style_of(post: dict) -> str:
    """"new style" for a Short whose description is in the owner's style
    (2026-11-06: paragraphs and a question), "old style" otherwise."""
    return "new style" if NEW_STYLE in (post.get("caption") or "") else "old style"


def viewer_comments(posts: list[dict], analytics: list[dict], since: dt.date, until: dt.date,
                    arm_of=style_of) -> dict:
    """Per arm: Shorts, views, likes and comments from viewers (the channel
    posts one comment of its own under each, which is taken off) for edits
    aired in [since, until), at their latest snapshot. `arm_of(post)` names
    the arm a posts.csv row belongs to."""
    latest: dict[str, tuple[str, int, int, int]] = {}
    for r in analytics:
        v = r.get("video_id")
        try:
            row = (r.get("pulled_on") or "", int(r.get("views") or 0), int(r.get("comments") or 0),
                   int(r.get("likes") or 0))
        except ValueError:
            continue
        if v and row[0] >= latest.get(v, ("", 0, 0, 0))[0]:
            latest[v] = row
    arms: dict[str, dict] = {}
    for r in posts:
        if not (r.get("experiment") or "").startswith("edit:") or r.get("video_id") not in latest:
            continue
        if not since <= _day(r["date"]) < until:
            continue
        _, n, c, likes = latest[r["video_id"]]
        a = arms.setdefault(arm_of(r), {"shorts": 0, "views": 0, "comments": 0, "likes": 0})
        a["shorts"] += 1
        a["views"] += n
        a["comments"] += max(0, c - 1)
        a["likes"] += likes
    for a in arms.values():
        a["per1k"] = round(1000 * a["comments"] / a["views"], 2) if a["views"] else None
        a["likesPer100"] = round(100 * a["likes"] / a["views"], 1) if a["views"] else None
    return arms


def source_share(rows: list[dict], source: str, since: dt.date, until: dt.date) -> dict:
    """Views from one traffic source as a share of all, over [since, until),
    from data/traffic_sources.csv."""
    total = part = 0
    for r in rows:
        try:
            day, n = _day(r["date"]), int(r.get("views") or 0)
        except (KeyError, ValueError):
            continue
        if since <= day < until:
            total += n
            part += n if r.get("source") == source else 0
    return {"views": part, "of": total, "share": round(part / total, 4) if total else None}


def judge(test: dict, posts: list[dict], views: Views, today: dt.date,
          analytics: list[dict] | None = None, sources: list[dict] | None = None) -> dict:
    """Where a test stands, in numbers. Kinds: `second_vs_first` (a posting
    time, against the day's other Short), `pinned_question` (the owner's
    description style with its question, viewer comments per 1,000 views on
    the edits of the 14 days before against those after, each Short sorted by
    its own description) and `traffic_source` (a source's share of views,
    the 14 days before against the 14 after)."""
    out = {"id": test["id"], "status": test.get("status")}
    start = _day(test["started"]) if test.get("started") else today
    end = start + dt.timedelta(days=TEST_DAYS)
    running = test.get("status") == "running" and bool(test.get("started"))
    if test.get("kind") == "pinned_question":
        # Not an A/B: the owner wants it on every Short (2026-11-06), so the
        # Shorts before the change are the control.
        arms = viewer_comments(posts, analytics or [], start - dt.timedelta(days=TEST_DAYS),
                               min(end, today) if running else start)
        out["before"] = arms.get("old style")
        if running:
            out["during"] = {"arms": arms, "ends": end.isoformat()}
            new, old = arms.get("new style"), arms.get("old style") or {}
            if today >= end and new:
                before = old.get("per1k") or 0
                if new["comments"] >= 3 and new["per1k"] is not None and new["per1k"] >= 2 * before:
                    out["verdict"] = "win"
                elif (new["per1k"] or 0) <= before:
                    out["verdict"] = "loss"
                else:
                    out["verdict"] = "no clear change"
        return out
    if test.get("kind") == "traffic_source":
        src = test.get("source", "PLAYLIST")
        out["before"] = source_share(sources or [], src, start - dt.timedelta(days=TEST_DAYS), start)
        if running:
            out["during"] = {**source_share(sources or [], src, start, min(end, today)), "ends": end.isoformat()}
            if today >= end and out["during"]["share"] is not None:
                b = out["before"]["share"] or 0
                out["verdict"] = ("win" if out["during"]["share"] >= max(0.01, 2 * b) else "no clear change")
        return out
    if test.get("kind") != "second_vs_first":
        return out
    base = second_vs_first(posts, views, _day(test.get("baselineSince", "2026-01-01")), start)
    out["before"] = {"days": len(base), "median": round(st.median([d["ratio"] for d in base]), 2) if base else None}
    if not running:
        return out
    during = second_vs_first(posts, views, start, min(end, today))
    med = round(st.median([d["ratio"] for d in during]), 2) if during else None
    out["during"] = {"days": len(during), "median": med, "ends": end.isoformat()}
    if med is not None and out["before"]["median"] and len(during) >= MIN_TEST_DAYS:
        change = med / out["before"]["median"]
        out["change"] = round(change, 2)
        if today >= end:
            out["verdict"] = "win" if change >= WIN else "loss" if change <= LOSE else "no clear change"
    return out


# ---------------------------------------------------------------- the audience

def audience() -> dict | None:
    """Glaux's pull (scripts/audience.py): countries, traffic sources and
    subscribers' share of views over the last 28 days."""
    try:
        return json.loads((DATA / "audience.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- the goal

def goal(today: dt.date) -> dict:
    """The goal the owner picked for 2027 (scripts/goals.py, asked in the HQ),
    measured today; {"chosen": None} until he picks. Every test is judged by
    whether it moves these numbers."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import goals as goals_mod  # noqa: PLC0415
        s = goals_mod.summary(today=today)
    except Exception:  # noqa: BLE001
        return {"chosen": None}
    picked = next((o for o in s["options"] if o["id"] == s.get("chosen")), None)
    return {"chosen": s.get("chosen"), "ask": s.get("ask"), **({"progress": picked} if picked else {})}


# ---------------------------------------------------------------- the read

def read(today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    posts = _rows("posts.csv")
    analytics = _rows("analytics.csv")
    views = Views(analytics)
    sources = _rows("traffic_sources.csv")
    ledger = load_tests()
    tests = [{**t, **judge(t, posts, views, today, analytics, sources)} for t in ledger.get("tests", [])]
    return {
        "audience": audience(),
        "updated": today.isoformat(),
        "source": "scripts/marketer.py (Cicero, free)",
        "funnel": funnel(_rows("channel_stats.csv"), views, today),
        "hours": hour_bands(posts, views),
        "tests": tests,
        "next": ledger.get("next", []),
        "goal": goal(today),
    }


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x:+.0%}"


def note(r: dict) -> str:
    """One line for Cicero's card in the HQ."""
    f = r["funnel"]
    bits = []
    if f.get("viewsPerDay") is not None:
        bits.append(f"{f['viewsPerDay']:,} views a day ({_pct(f.get('viewsChange'))} on last week)")
    if f.get("subsPerDay") is not None:
        bits.append(f"{f['subsPerDay']} new subscribers a day")
    running = [t for t in r["tests"] if t.get("status") == "running"]
    waiting = [t for t in r["tests"] if t.get("status") == "proposed"]
    g = (r.get("goal") or {}).get("progress")
    if g and g.get("onTrack") is not None:
        bits.append("goal: " + ("on track" if g["onTrack"] else "behind"))
    if running:
        bits.append(f"testing: {running[0]['question']}"
                    + (f" (+{len(running) - 1} more)" if len(running) > 1 else ""))
    elif waiting:
        bits.append(f"{len(waiting)} test waiting for your yes")
    return " · ".join(bits)


def _arms(t: dict) -> dict:
    return (t.get("during") or {}).get("arms") or {}


def markdown(r: dict) -> str:
    f = r["funnel"]
    lines = [
        "# Marketing: how the channel reaches people",
        "",
        f"_Updated {r['updated']} by Cicero (scripts/marketer.py, free, no paid API)._",
        "",
        "## The funnel",
        "",
        f"- Views a day, last 7 days: **{f.get('viewsPerDay')}** (the 7 before: {f.get('viewsPerDayBefore')}, "
        f"{_pct(f.get('viewsChange'))})",
        f"- New subscribers a day: **{f.get('subsPerDay')}** (the 7 before: {f.get('subsPerDayBefore')}); "
        f"{f.get('subscribers')} in all",
        f"- Subscribers per 1,000 views: {f.get('subsPer1kViews')}",
        f"- Likes per 100 views (Shorts of the last 14 days): {f.get('likesPer100Views')}",
        "",
        "## Reach by upload hour (UTC)",
        "",
        "Each Short's day-1 views against the Shorts aired within a week of it.",
        "",
        "| Hour (UTC) | Shorts | Reach vs its week | Stalled (<0.4x) |",
        "|---|---|---|---|",
    ]
    lines += [f"| {h['band']} | {h['posts']} | {h['lift']}x | {h['stalled']} |" for h in r["hours"]]
    a = r.get("audience")
    if a:
        top = lambda xs, k=5: ", ".join(f"{x['key']} {x['share']:.0%}" for x in xs[:k])  # noqa: E731
        lines += ["", f"## Who watches (last 28 days, pulled {a.get('pulled_on')})", "",
                  f"- Countries: {top(a.get('countries') or [], 6)}",
                  f"- How they find the Shorts: {top(a.get('sources') or [])}",
                  f"- Subscribed or not: {top(a.get('subscribed') or [])}"]
    lines += ["", "## The goal", ""]
    g = (r.get("goal") or {}).get("progress")
    if not g:
        lines.append(f"- No goal picked yet: the options wait in the HQ (asks/{(r.get('goal') or {}).get('ask') or 'goal-2027'}).")
    else:
        lines.append(f"- **{g['title']}** (by {g['deadline']})")
        for t in g["targets"]:
            pace = (f"; {t['pace']:,.1f} a day now, {t['needed']:,.1f} needed"
                    if t.get("pace") is not None and t.get("needed") is not None else "")
            lines.append(f"- {t['label']}: {t['have'] if t['have'] is not None else '–'} of {t['target']:,} "
                         f"({t['status']}{pace})")
        if g.get("next"):
            state = {True: "on track", False: "behind", None: "open"}[g.get("onTrack")]
            lines.append(f"- Next checkpoint {g['next']['by']}: {state}")
        lines.append("- Every test below is judged by whether it moves these numbers.")
    lines += ["", "## Tests (one change at a time, each only with the owner's yes)", ""]
    for t in r["tests"]:
        lines.append(f"### {t['question']}")
        lines.append("")
        lines.append(f"- Status: **{t.get('status')}**" + (f" since {t['started']}" if t.get("started") else ""))
        lines.append(f"- Change: {t.get('change')}")
        lines.append(f"- Why: {t.get('why')}")
        lines.append(f"- Judged by: {t.get('measure')}")
        b = t.get("before") or {}
        if b.get("comments") is not None and not _arms(t):
            lines.append(f"- Before: {b['comments']} viewer comments on {b['shorts']} Shorts "
                         f"({b['per1k']} per 1,000 views)")
        if b.get("median") is not None:
            lines.append(f"- Before: median {b['median']}x over {b['days']} days")
        d = t.get("during") or {}
        if d.get("median") is not None:
            lines.append(f"- During: median {d['median']}x over {d['days']} days (ends {d['ends']})")
        for name, arm in (d.get("arms") or {}).items():
            lines.append(f"- {name.capitalize()}: {arm['comments']} viewer comments on {arm['shorts']} Shorts "
                         f"({arm['per1k']} per 1,000 views; {arm.get('likesPer100')} likes per 100 views)")
        if b.get("share") is not None or d.get("share") is not None:
            lines.append(f"- Share of views: {b.get('share')} before"
                         + (f", {d['share']} during" if d.get("share") is not None else ""))
        if t.get("verdict"):
            lines.append(f"- Verdict: **{t['verdict']}**" + (f" ({t['change']}x)" if t.get("change") else ""))
        lines.append("")
    if r["next"]:
        lines += ["## Next ideas (each is proposed in the HQ first)", ""]
        lines += [f"- {n['idea']}" for n in r["next"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    r = read()
    r["note"] = note(r)
    if a.write:
        REPORT_JSON.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        REPORT_MD.write_text(markdown(r), encoding="utf-8")
    print(markdown(r))
    print("HQ:", r["note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
