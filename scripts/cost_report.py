"""
Cost agent — tracks what the bot costs to run, every month, all-in.

Reads data/costs.json (the editable subscription registry: Claude subscription,
ElevenLabs, API estimates, one-time purchases) and joins it with posts.csv +
analytics.csv to answer the questions that matter:

  - What am I paying per month right now?
  - What has the whole operation cost since it started?
  - What does one Short cost me? A thousand views?

Run standalone:
    python scripts/cost_report.py

Or imported by channel_report.py, which embeds the same summary in the weekly
report so the money picture ships alongside the performance picture.

Assumption-flagging: any subscription whose note contains ASSUMED or ESTIMATE
is marked in the output — those numbers are guesses until the owner edits
data/costs.json with real prices.
"""
import csv
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COSTS = ROOT / "data" / "costs.json"
POSTS = ROOT / "data" / "posts.csv"
ANALYTICS = ROOT / "data" / "analytics.csv"


def _load_costs() -> dict:
    if not COSTS.exists():
        return {"subscriptions": [], "one_time": [], "free_services": []}
    try:
        return json.loads(COSTS.read_text(encoding="utf-8"))
    except Exception:
        return {"subscriptions": [], "one_time": [], "free_services": []}


def _months_active(start: str, today: datetime.date) -> float:
    """Fractional months from start date to today (30.44-day months)."""
    try:
        s = datetime.date.fromisoformat(start)
    except Exception:
        return 0.0
    days = max(0, (today - s).days)
    return days / 30.44


def _channel_stats() -> tuple[int, int]:
    """(total posts, total peak views) from the logs."""
    n_posts = 0
    if POSTS.exists():
        with open(POSTS, newline="", encoding="utf-8") as f:
            n_posts = max(0, sum(1 for _ in f) - 1)
    peak: dict[str, int] = {}
    if ANALYTICS.exists():
        with open(ANALYTICS, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                vid = (r.get("video_id") or "").strip()
                v = int(r.get("views") or 0)
                if vid and v > peak.get(vid, 0):
                    peak[vid] = v
    return n_posts, sum(peak.values())


def costs_summary(today: datetime.date | None = None) -> str:
    """Markdown summary of the money picture. Used by channel_report.py."""
    today = today or datetime.date.today()
    data = _load_costs()
    subs = data.get("subscriptions", [])
    ones = data.get("one_time", [])

    lines = []
    monthly_total = 0.0
    cumulative = 0.0

    lines.append("## 💰 Costs (edit data/costs.json to correct any number)")
    if not subs and not ones:
        lines.append("- No costs recorded yet — add subscriptions to data/costs.json.")
        return "\n".join(lines)

    for s in subs:
        price = float(s.get("monthly_usd", 0))
        monthly_total += price
        months = _months_active(s.get("start", ""), today)
        spent = price * months
        cumulative += spent
        note = s.get("note", "")
        flag = " ⚠️ _guess — edit me_" if ("ASSUM" in note.upper() or "ESTIMATE" in note.upper()) else ""
        lines.append(f"- {s.get('name','?')}: **${price:.2f}/mo** "
                     f"(since {s.get('start','?')}, ~${spent:.0f} total){flag}")

    for o in ones:
        price = float(o.get("usd", 0))
        cumulative += price
        lines.append(f"- {o.get('name','?')}: **${price:.2f}** one-time ({o.get('date','?')})")

    n_posts, total_views = _channel_stats()
    lines.append(f"- **Monthly burn: ${monthly_total:.2f}** · "
                 f"all-time spend: **~${cumulative:.0f}**")
    if n_posts:
        lines.append(f"- Unit economics: **${cumulative / n_posts:.2f} per Short**"
                     + (f" · **${1000 * cumulative / total_views:.2f} per 1k views**"
                        if total_views else ""))
    free = data.get("free_services", [])
    if free:
        lines.append(f"- Running free: {', '.join(free)}")
    lines.append("- _Revenue not tracked yet — add Gumroad numbers and this becomes "
                 "a profit report._")
    return "\n".join(lines)


def main():
    print(costs_summary())


if __name__ == "__main__":
    main()
