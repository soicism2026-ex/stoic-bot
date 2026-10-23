"""
The studio's status for the HQ app (the owner's live view of every agent).

The HQ page shows the owner's Claude sessions live by itself. What only this
repo and GitHub know (the bots, meaning the scheduled workflows, and the
channel's numbers) reaches the page through one document in its database,
`hq/studio`, which this script builds:

    python scripts/hq_snapshot.py --out /tmp/hq_studio.json

Then a Claude session writes the file to the HQ's `hq/studio` document
(ArtifactData `set` with `file_path`, pinned to the version it last read).
The HQ sync scheduled task does that every few hours, and any session that
updates the HQ can too. See "HQ app" in CLAUDE.md.

Reads only: posts.csv, analytics.csv, channel_stats.csv, the workflow files,
and GitHub's public Actions API (no token needed for a public repo).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPO = "soicism2026-ex/stoic-bot"

GOAL_SUBS = 500
GOAL_VIEWS_90D = 3_000_000

# The bots, in the order the owner reads them. `slots` marks the poster.
BOTS = [
    {"id": "producer", "name": "Producer", "workflow": "daily-short.yml",
     "role": "Makes and posts the Shorts, then pulls stats, prunes and replies"},
    {"id": "analyst", "name": "Analyst", "workflow": "pull-analytics.yml",
     "role": "Pulls YouTube views, likes and subscribers every day"},
    {"id": "strategist", "name": "Strategist", "workflow": "strategy-update.yml",
     "role": "Rewrites the content strategy from the latest numbers"},
    {"id": "reporter", "name": "Reporter", "workflow": "auto-improve.yaml",
     "role": "Weekly channel report with one recommendation"},
    {"id": "preview", "name": "Preview studio", "workflow": "edit-preview.yml",
     "role": "Rehearses the next Short twice a day so you can watch it before it airs. Never posts"},
    {"id": "composer", "name": "Composer", "workflow": "make-music.yml",
     "role": "Generates original music for the edits"},
]


def _rows(name: str) -> list[dict]:
    p = DATA / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

def crons(workflow: str) -> list[str]:
    """The cron expressions in a workflow file (UTC)."""
    p = ROOT / ".github" / "workflows" / workflow
    if not p.exists():
        return []
    return re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", p.read_text(encoding="utf-8"))


def _field(spec: str, value: int, lo: int, hi: int) -> bool:
    if spec == "*":
        return True
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
        if a <= value <= b and (value - a) % step == 0:
            return True
    return False


def next_cron(expr: str, after: dt.datetime) -> dt.datetime | None:
    """Next UTC minute matching a 5-field cron expression, within 8 days.
    Day-of-week 0 and 7 are both Sunday, as in cron."""
    try:
        minute, hour, dom, month, dow = expr.split()[:5]
    except ValueError:
        return None
    t = after.astimezone(dt.timezone.utc).replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    end = t + dt.timedelta(days=8)
    while t < end:
        cron_dow = (t.weekday() + 1) % 7          # Monday=1 ... Sunday=0
        if (_field(month, t.month, 1, 12) and _field(dom, t.day, 1, 31)
                and (_field(dow, cron_dow, 0, 6) or (cron_dow == 0 and _field(dow, 7, 0, 7)))
                and _field(hour, t.hour, 0, 23) and _field(minute, t.minute, 0, 59)):
            return t
        if not _field(hour, t.hour, 0, 23):
            t = (t + dt.timedelta(hours=1)).replace(minute=0)
        else:
            t += dt.timedelta(minutes=1)
    return None


def next_run(workflow: str, now: dt.datetime) -> dt.datetime | None:
    times = [n for n in (next_cron(c, now) for c in crons(workflow)) if n]
    return min(times) if times else None


def _env_value(workflow: str, key: str, default: str) -> str:
    p = ROOT / ".github" / "workflows" / workflow
    m = re.search(rf"{key}:\s*\$\{{\{{[^}}]*\|\|\s*'(\d+)'\s*\}}\}}", p.read_text()) if p.exists() else None
    if m:
        return m.group(1)
    m = re.search(rf'{key}:\s*"([^"]*)"', p.read_text()) if p.exists() else None
    return m.group(1) if m else default


def next_post(posts: list[dict], now: dt.datetime, last_post_at: dt.datetime | None) -> dict:
    """When the Producer will next try to post, from the same rules
    daily_post.py applies: a daily cap, the slot hours that open the 2nd
    (and later) post of the day, and a minimum gap after the last upload.
    GitHub runs scheduled workflows late or not at all, so this is the
    earliest attempt, not a promise."""
    wf = "daily-short.yml"
    cap = int(_env_value(wf, "MAX_POSTS_PER_DAY", "2"))
    slots = [int(h) for h in _env_value(wf, "POST_SLOT_HOURS", "0").split(",") if h.strip().isdigit()]
    gap = float(_env_value(wf, "MIN_GAP_HOURS", "0"))
    today = now.date().isoformat()
    done_today = sum(1 for r in posts if r.get("date") == today)
    t = now
    for _ in range(40):
        t = next_run(wf, t)
        if t is None:
            break
        n_today = done_today if t.date() == now.date() else 0
        if n_today >= cap:
            continue
        if slots and n_today < len(slots) and t.hour < slots[n_today]:
            continue
        if gap and last_post_at and (t - last_post_at).total_seconds() < gap * 3600:
            continue
        return {"at": _iso(t), "postsToday": done_today, "cap": cap}
    return {"at": None, "postsToday": done_today, "cap": cap}


# ---------------------------------------------------------------------------
# GitHub Actions
# ---------------------------------------------------------------------------

def _get_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "stoic-bot-hq"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        pass
    try:   # inside a Claude session, gh goes through its GitHub proxy
        out = subprocess.run(["gh", "api", url.replace("https://api.github.com/", "")],
                             capture_output=True, text=True, timeout=30)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def runs_from_branch() -> list[dict]:
    """The bots' runs as .github/workflows/hq-status.yml last published them
    on the `hq-status` branch, read over git. This works in sessions with no
    GitHub API access (the HQ sync scheduled task), since cloning does."""
    try:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "--depth", "1", "origin", "hq-status"],
                       check=True, capture_output=True, timeout=60)
        out = subprocess.run(["git", "-C", str(ROOT), "show", "FETCH_HEAD:hq_runs.json"],
                             check=True, capture_output=True, text=True, timeout=30)
        return json.loads(out.stdout).get("workflow_runs") or []
    except Exception:  # noqa: BLE001
        return []


def fetch_runs() -> tuple[list[dict], str | None]:
    """Recent Actions runs and where they came from: GitHub's API when this
    machine can reach it, else the hq-status branch. ([], None) when neither
    answers; the page then shows the bots' status as unknown."""
    got = _get_json(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=100")
    runs = (got or {}).get("workflow_runs") or []
    if runs:
        return runs, "api"
    runs = runs_from_branch()
    return (runs, "hq-status branch") if runs else ([], None)


def latest_runs(runs: list[dict]) -> dict[str, dict]:
    """Newest run per workflow file name, from the Actions runs list."""
    out: dict[str, dict] = {}
    for r in sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True):
        wf = Path(r.get("path") or "").name
        if wf and wf not in out:
            out[wf] = r
    return out


def bot_status(run: dict | None) -> str:
    if not run:
        return "idle"
    if run.get("status") in ("queued", "waiting", "pending", "requested"):
        return "queued"
    if run.get("status") == "in_progress":
        return "working"
    if run.get("conclusion") in ("failure", "timed_out", "startup_failure"):
        return "failed"
    return "idle"


def bots(runs: list[dict], now: dt.datetime, producer_note: str,
         fetch_missing: bool = True) -> list[dict]:
    newest = latest_runs(runs)
    out = []
    for b in BOTS:
        run = newest.get(b["workflow"])
        if run is None and fetch_missing:   # quiet bots fall out of the recent-runs page
            got = _get_json(f"https://api.github.com/repos/{REPO}/actions/workflows/"
                            f"{b['workflow']}/runs?per_page=1")
            run = ((got or {}).get("workflow_runs") or [None])[0]
        nxt = next_run(b["workflow"], now)
        last = None
        if run:
            last = {"at": run.get("run_started_at") or run.get("created_at"),
                    "finished": run.get("updated_at") if run.get("status") == "completed" else None,
                    "status": run.get("status"), "conclusion": run.get("conclusion"),
                    "event": run.get("event"), "url": run.get("html_url")}
        doc = {**b, "status": bot_status(run), "last": last,
               "next": _iso(nxt) if nxt else None,
               "url": f"https://github.com/{REPO}/actions/workflows/{b['workflow']}"}
        if b["id"] == "producer":
            doc["note"] = producer_note
        out.append(doc)
    return out


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------

def channel(now: dt.datetime) -> dict:
    stats = {}
    for r in _rows("channel_stats.csv"):
        stats[r["pulled_on"]] = r            # last row of a day wins
    days = sorted(stats)
    if not days:
        return {}

    def num(day, key):
        try:
            return int(stats[day][key])
        except (KeyError, ValueError):
            return None

    def on_or_after(day):
        return next((d for d in days if d >= day), None)

    last = days[-1]
    last_d = dt.date.fromisoformat(last)
    wk = on_or_after((last_d - dt.timedelta(days=7)).isoformat())
    q = on_or_after((last_d - dt.timedelta(days=90)).isoformat())
    total = num(last, "total_views")
    series = days[-31:]
    views_daily = [{"d": b, "v": max(0, (num(b, "total_views") or 0) - (num(a, "total_views") or 0))}
                   for a, b in zip(series, series[1:])]
    return {
        "asOf": last,
        "subs": num(last, "subscribers"),
        "subsWeekAgo": num(wk, "subscribers") if wk else None,
        "totalViews": total,
        "videos": num(last, "videos"),
        "views7d": total - num(wk, "total_views") if wk and total is not None else None,
        "views90d": total - num(q, "total_views") if q and total is not None else None,
        "views90dSince": q,
        "goalSubs": GOAL_SUBS,
        "goalViews90d": GOAL_VIEWS_90D,
        "viewsDaily": views_daily,
        "subsDaily": [{"d": d, "v": num(d, "subscribers")} for d in series],
    }


def recent_posts(posts: list[dict], n: int = 8) -> list[dict]:
    views: dict[str, tuple[str, int, str, str]] = {}
    for r in _rows("analytics.csv"):
        vid = r.get("video_id")
        try:
            v = int(r.get("views") or 0)
        except ValueError:
            continue
        prev = views.get(vid)
        if prev is None or r.get("pulled_on", "") >= prev[0]:
            views[vid] = (r.get("pulled_on", ""), v, r.get("title", ""), r.get("published_at", ""))
    out = []
    for r in reversed(posts[-n:]):
        vid = r.get("video_id") or ""
        seen = views.get(vid)
        out.append({
            "date": r.get("date"),
            "publishedAt": (seen[3] or None) if seen else None,
            "title": (seen[2] if seen and seen[2] else (r.get("hook") or r.get("quote") or ""))[:120],
            "author": r.get("author"),
            "url": r.get("video_url") or (f"https://youtube.com/shorts/{vid}" if vid else None),
            "views": seen[1] if seen else None,
            "voice": r.get("voice_name"),
            "format": r.get("format"),
        })
    return out


def _last_upload_at(posts: list[dict]) -> dt.datetime | None:
    best = None
    for r in _rows("analytics.csv"):
        if r.get("published_at"):
            best = max(best or "", r["published_at"])
    if best:
        return dt.datetime.fromisoformat(best.replace("Z", "+00:00"))
    if posts and posts[-1].get("date"):
        return dt.datetime.fromisoformat(posts[-1]["date"] + "T00:00:00+00:00")
    return None


def next_on_air(posts: list[dict]) -> dict | None:
    """The quote the next edit will use (edits.pick is deterministic)."""
    try:
        sys.path.insert(0, str(ROOT / "src"))
        import edits  # noqa: PLC0415
        q = edits.pick(posts)
        if not q:
            return None
        return {"id": q.get("id"), "quote": q.get("quote"), "author": q.get("author"),
                "citation": q.get("citation"), "hook": q.get("hook"),
                "left": edits.remaining(posts)}
    except Exception:  # noqa: BLE001
        return None


def shelf_status(now: dt.datetime) -> dict | None:
    """Days of verified quotes left (scripts/shelf.py); the HQ warns when low."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import shelf  # noqa: PLC0415
        return shelf.status(today=now.date())
    except Exception:  # noqa: BLE001
        return None


def build(now: dt.datetime | None = None, runs: list[dict] | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    posts = _rows("posts.csv")
    source = "given"
    if runs is None:
        runs, source = fetch_runs()
    online = source == "api"
    nxt = next_post(posts, now, _last_upload_at(posts))
    # the page shows the next try in the viewer's own time zone from nextPost
    note = f"{nxt['postsToday']} of {nxt['cap']} posted today"
    return {
        "updated": _iso(now),
        "source": "scripts/hq_snapshot.py",
        "bots": bots(runs, now, note, fetch_missing=online),
        "nextPost": nxt,
        "nextOnAir": next_on_air(posts),
        "shelf": shelf_status(now),
        "channel": channel(now),
        "posts": recent_posts(posts),
        "runsSeen": len(runs),
        "runsSource": source,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    doc = build()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"hq/studio: {len(doc['bots'])} bots, {doc['runsSeen']} runs seen "
          f"(from {doc['runsSource'] or 'nowhere: GitHub did not answer'}), "
          f"{len(doc['posts'])} posts -> {a.out} ({a.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
