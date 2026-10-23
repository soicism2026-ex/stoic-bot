"""
The calendar day a render is FOR.

A live run renders for today (UTC on the runner). A DRY_RUN rehearsal of the
next post (edit-preview on its schedule, owner 2026-10-23: "get them working")
sets REEL_TODAY to the day that post airs, so the choices keyed to the day,
which stock shot each search lands on, the day's pair of sound effects and
the music shuffle, come out the way the live run will make them.

Live runs ignore REEL_TODAY: a stray value can never move a real post's date,
its daily cap or its slot.

    python src/airday.py --next      # the day the next post airs (for REEL_TODAY)
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "0") not in ("0", "", "false", "False")


def today() -> _dt.date:
    v = os.environ.get("REEL_TODAY", "").strip()
    if v and _dry_run():
        try:
            return _dt.date.fromisoformat(v)
        except ValueError:
            pass
    return _dt.date.today()


def next_air_day(post_rows: list[dict], cap: int, now: _dt.datetime | None = None) -> _dt.date:
    """Today while today's posts are not all out, else tomorrow. A late
    second post (GitHub runs crons hours late) still counts as today's."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    d = now.date()
    done = sum(1 for r in post_rows if r.get("date") == d.isoformat())
    return d if done < max(1, cap) else d + _dt.timedelta(days=1)


def live_cap() -> int:
    """Posts a day on the live channel: daily-short.yml's MAX_POSTS_PER_DAY
    default. Not the environment: a preview runs with 99 to bypass the cap."""
    wf = ROOT / ".github" / "workflows" / "daily-short.yml"
    m = re.search(r"MAX_POSTS_PER_DAY:\s*\$\{\{[^}]*\|\|\s*'(\d+)'", wf.read_text()) if wf.exists() else None
    return max(1, int(m.group(1))) if m else 2


if __name__ == "__main__":
    if "--next" in sys.argv:
        p = ROOT / "data" / "posts.csv"
        rows = list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []
        print(next_air_day(rows, live_cap()).isoformat())
