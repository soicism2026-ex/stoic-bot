"""
Frontinus, the free strategist: what is working on the channel, from numbers
the bots already collect, with no paid API.

Owner, 2026-10-27 (HQ): "I want to fire our strategist find some who will do
this for free before we fire though". The old strategist (strategy_loop.py,
"Agrippa") sent the data to Claude Opus through the paid API. The credit ran
out before its first real run, so data/strategy.md was still the empty
template, and he failed every day. Frontinus does the same job with plain
statistics, so he costs nothing and cannot run out of credit.

    python scripts/strategist.py            # print the read
    python scripts/strategist.py --write    # also write data/strategy.md + data/strategy.json

What he reads (all already in the repo, refreshed by the daily bots):
  data/posts.csv       every post: theme, author, hook, music, voice, date
  data/analytics.csv   repeated view snapshots per video
  data/retention.csv   average % of each Short watched

The fair comparison, in two steps:
  1. views at DAY 3 (the first snapshot at least 3 days after upload), so a
     2-week-old video does not beat a 4-day-old one just by age;
  2. each edit against the edits that aired within NEIGHBOUR_DAYS of it
     ("lift"), because the channel's reach changed under them: mid-October
     edits got 5-10x the views of early-October ones, and early October was
     ten Marcus Aurelius edits in a row, so raw views would blame Marcus for
     the season.
Retention (the share of the Short people watch, which drives Shorts reach) is
reported next to it. Only edits from the last WINDOW_DAYS count.

What his read changes (data/strategy.json):
  - the edit picker airs quotes of WINNING themes first, within the author
    rotation (src/edits.py), and LOSING themes last;
  - the Librarian writes more like the winners (scripts/shelf.py winners);
  - data/strategy.md feeds content.py's generated-content prompt, as before.
A group needs MIN_N settled edits before it can be called a winner or a
loser; small samples are reported, never acted on.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STRATEGY_MD = DATA / "strategy.md"
STRATEGY_JSON = DATA / "strategy.json"

WINDOW_DAYS = 28        # recent edits only: the channel changed a lot before
SETTLE_DAYS = 3         # views compared at day 3
NEIGHBOUR_DAYS = 7      # an edit is compared with the edits aired this close to it
MIN_N = 3               # settled edits a group needs before it is acted on
WIN, LOSE = 1.25, 0.75  # group median / overall median


def _rows(name: str) -> list[dict]:
    p = DATA / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _d(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def day3_views(stats: list[dict]) -> dict[str, int]:
    """video_id -> views in the first snapshot taken >= SETTLE_DAYS after upload."""
    by_vid: dict[str, list[tuple[dt.date, int]]] = defaultdict(list)
    published: dict[str, dt.date] = {}
    for a in stats:
        vid, pulled, pub = a.get("video_id"), _d(a.get("pulled_on", "")), _d(a.get("published_at", ""))
        if not vid or not pulled or not pub:
            continue
        published[vid] = pub
        try:
            by_vid[vid].append((pulled, int(float(a.get("views") or 0))))
        except ValueError:
            continue
    out = {}
    for vid, snaps in by_vid.items():
        due = published[vid] + dt.timedelta(days=SETTLE_DAYS)
        settled = sorted(s for s in snaps if s[0] >= due)
        if settled:
            out[vid] = settled[0][1]
    return out


def retention(rows: list[dict]) -> dict[str, float]:
    """video_id -> average % watched (latest pull)."""
    out, when = {}, {}
    for r in rows:
        vid = r.get("video_id")
        try:
            pct = float(r.get("avg_view_pct") or "")
        except ValueError:
            continue
        if vid and (vid not in when or (r.get("pulled_on") or "") >= when[vid]):
            out[vid], when[vid] = pct, r.get("pulled_on") or ""
    return out


def hook_form(hook: str) -> str:
    h = (hook or "").strip()
    if h.endswith("?"):
        return "question"
    first = (re.findall(r"[A-Za-z']+", h) or [""])[0].lower()
    if first in {"stop", "pick", "ask", "start", "look", "live", "treat", "read", "say", "do",
                 "don't", "never", "quit", "win", "lean", "fight", "practise", "practice", "tell"}:
        return "command"
    return "statement"


def _bucket(n: int, edges: tuple[int, ...], names: tuple[str, ...]) -> str:
    for e, name in zip(edges, names):
        if n <= e:
            return name
    return names[-1]


def settled_edits(posts: list[dict], views: dict[str, int], ret: dict[str, float],
                  today: dt.date) -> list[dict]:
    per_day: dict[str, int] = defaultdict(int)
    out = []
    for r in posts:
        if not (r.get("experiment") or "").startswith("edit:"):
            continue
        d = _d(r.get("date", ""))
        per_day[r.get("date", "")] += 1
        if not d or (today - d).days > WINDOW_DAYS or r.get("video_id") not in views:
            continue
        out.append({
            "id": r["experiment"].removeprefix("edit:"), "date": r["date"],
            "views": views[r["video_id"]], "retention": ret.get(r["video_id"]),
            "theme": r.get("theme") or "?", "author": r.get("author") or "?",
            "hook": r.get("hook") or "", "hook_form": hook_form(r.get("hook") or ""),
            "hook_len": _bucket(len((r.get("hook") or "").split()), (4, 6), ("short (<=4 words)", "medium (5-6)", "long (7+)")),
            "quote_len": _bucket(len((r.get("quote") or "").split()), (12, 24), ("short (<=12 words)", "medium (13-24)", "long (25+)")),
            "music": (r.get("music_track") or "?").split(":")[-1],
            "voice": r.get("voice_name") or "?",
            "slot": "first of the day" if per_day[r.get("date", "")] == 1 else "second of the day",
            "weekday": d.strftime("%A"),
        })
    return out


DIMENSIONS = ("theme", "author", "hook_form", "hook_len", "quote_len", "music", "voice", "slot", "weekday")


def read(posts: list[dict] | None = None, stats: list[dict] | None = None,
         ret_rows: list[dict] | None = None, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    posts = _rows("posts.csv") if posts is None else posts
    stats = _rows("analytics.csv") if stats is None else stats
    ret_rows = _rows("retention.csv") if ret_rows is None else ret_rows
    edits = settled_edits(posts, day3_views(stats), retention(ret_rows), today)
    overall = statistics.median([e["views"] for e in edits]) if edits else 0
    for e in edits:
        d = _d(e["date"])
        near = [x["views"] for x in edits if abs((_d(x["date"]) - d).days) <= NEIGHBOUR_DAYS]
        base = statistics.median(near) if len(near) >= 3 else overall
        e["rel"] = (e["views"] / base) if base else 1.0
    ret_all = [e["retention"] for e in edits if e["retention"] is not None]
    groups: dict[str, list[dict]] = {}
    for dim in DIMENSIONS:
        by: dict[str, list[dict]] = defaultdict(list)
        for e in edits:
            by[e[dim]].append(e)
        rows = []
        for key, items in by.items():
            med = statistics.median(i["views"] for i in items)
            rets = [i["retention"] for i in items if i["retention"] is not None]
            lift = round(statistics.median(i["rel"] for i in items), 2)
            verdict = ("winner" if lift >= WIN else "loser" if lift <= LOSE else "even") if len(items) >= MIN_N else "too few"
            rows.append({"key": key, "n": len(items), "median_views_day3": med, "lift": lift,
                         "median_retention": round(statistics.median(rets), 1) if rets else None,
                         "verdict": verdict})
        groups[dim] = sorted(rows, key=lambda r: (-r["lift"], -r["n"]))
    themes = groups["theme"]
    return {
        "updated": today.isoformat(), "by": "Frontinus (scripts/strategist.py, no paid API)",
        "window_days": WINDOW_DAYS, "settled_edits": len(edits),
        "median_views_day3": overall,
        "median_retention": round(statistics.median(ret_all), 1) if ret_all else None,
        "theme_rank": {r["key"]: (2 if r["verdict"] == "winner" else 0 if r["verdict"] == "loser" else 1)
                       for r in themes},
        "groups": groups,
        "top": sorted(edits, key=lambda e: -e["rel"])[:5],
        "bottom": sorted(edits, key=lambda e: e["rel"])[:3],
    }


def markdown(r: dict) -> str:
    g = r["groups"]
    win = [(d, x) for d in DIMENSIONS for x in g[d] if x["verdict"] == "winner"]
    lose = [(d, x) for d in DIMENSIONS for x in g[d] if x["verdict"] == "loser"]
    nice = {"theme": "theme", "author": "author", "hook_form": "hook as a", "hook_len": "hook length",
            "quote_len": "quote length", "music": "music", "voice": "voice", "slot": "posted", "weekday": "day"}

    def line(d, x):
        ret = f", {x['median_retention']}% watched" if x["median_retention"] is not None else ""
        return (f"- {nice[d]} **{x['key']}**: {x['lift']}x the edits aired around it "
                f"({x['median_views_day3']:.0f} views at day 3, {x['n']} edits{ret})")

    out = [
        "# Stoic Shorts Content Strategy", "",
        f"_Updated {r['updated']} by {r['by']}. Read from {r['settled_edits']} edits of the last "
        f"{r['window_days']} days, compared at day 3 (median {r['median_views_day3']:.0f} views"
        + (f", {r['median_retention']}% watched" if r["median_retention"] is not None else "") + ")._",
        "", "---", "", "## What Works", "",
        *([line(d, x) for d, x in win] or ["_No group is clearly ahead yet (each needs 3+ settled edits)._"]),
        "", "## What Doesn't Work", "",
        *([line(d, x) for d, x in lose] or ["_No group is clearly behind yet._"]),
        "", "## Top Recommendations for Next Posts", "",
    ]
    recs = []
    best_themes = [x["key"] for x in g["theme"] if x["verdict"] == "winner"]
    if best_themes:
        recs.append(f"- Air and write more **{', '.join(best_themes)}**: the shelf now plays these themes first.")
    worst = [x["key"] for x in g["theme"] if x["verdict"] == "loser"]
    if worst:
        recs.append(f"- Fewer **{', '.join(worst)}** edits: they move to the back of the shelf.")
    forms = [x for x in g["hook_form"] if x["verdict"] in ("winner", "even") and x["n"] >= MIN_N]
    if forms:
        recs.append(f"- Hooks that work best right now: **{forms[0]['key']}** form ("
                    f"{forms[0]['lift']}x).")
    for e in r["top"][:3]:
        recs.append(f"- Copy the shape of \"{e['hook']}\" ({e['author']}, {e['theme']}): "
                    f"{e['rel']:.1f}x the edits around it, {e['views']} views at day 3.")
    out += recs or ["_Not enough settled edits yet._"]
    out += ["", "---", "", "## Performance Data Window", "",
            "| Edit | Date | Author | Theme | Hook | Views day 3 | Lift | Watched |", "|---|---|---|---|---|---|---|---|"]
    for e in r["top"] + r["bottom"]:
        ret = f"{e['retention']}%" if e["retention"] is not None else "?"
        out.append(f"| {e['id']} | {e['date']} | {e['author']} | {e['theme']} | {e['hook']} | {e['views']} "
                   f"| {e['rel']:.1f}x | {ret} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    r = read()
    md = markdown(r)
    print(md)
    if a.write:
        STRATEGY_MD.write_text(md, encoding="utf-8")
        STRATEGY_JSON.write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {STRATEGY_MD.relative_to(ROOT)} and {STRATEGY_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
