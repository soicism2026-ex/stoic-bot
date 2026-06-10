"""
Weekly performance report.

Reads the last 7 days of posts (data/posts.csv) joined with view stats
(data/analytics.csv) and asks Claude for a short markdown summary: top/bottom
posts, trends, and exactly ONE suggested change. Writes it to reports/YYYY-MM-DD.md.

Deliberately cheap: one API call, small max_tokens, on the small Haiku model.
Intended to run weekly from .github/workflows/weekly-report.yml (Sundays).
"""
import csv
import datetime
import os
from pathlib import Path

import anthropic

from logbook import classify_title_style

MODEL = "claude-haiku-4-5"  # cheap is the point; this is a digest, not generation

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.csv"
ANALYTICS = ROOT / "data" / "analytics.csv"
REPORTS = ROOT / "reports"

DAYS = 7


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _max_views_by_video() -> dict[str, int]:
    out: dict[str, int] = {}
    for row in _read_csv(ANALYTICS):
        vid = row.get("video_id")
        if not vid:
            continue
        try:
            views = int(row.get("views") or 0)
        except ValueError:
            continue
        out[vid] = max(out.get(vid, 0), views)
    return out


def gather(today: datetime.date, days: int = DAYS) -> list[dict]:
    """Recent posts within `days`, each annotated with peak views + title style."""
    cutoff = today - datetime.timedelta(days=days)
    views_by_video = _max_views_by_video()

    rows = []
    for post in _read_csv(POSTS):
        try:
            posted = datetime.date.fromisoformat((post.get("date") or "").strip())
        except ValueError:
            continue
        if posted < cutoff:
            continue
        vid = post.get("video_id", "")
        rows.append({
            "date": post.get("date", ""),
            "theme": post.get("theme", ""),
            "author": post.get("author", ""),
            "style": post.get("title_style") or classify_title_style(post.get("quote", "")),
            "views": views_by_video.get(vid, 0),
            "quote": (post.get("quote", "") or "")[:90],
        })
    rows.sort(key=lambda r: r["views"], reverse=True)
    return rows


def _table(rows: list[dict]) -> str:
    lines = ["views | theme | author | style | quote"]
    for r in rows:
        lines.append(f'{r["views"]} | {r["theme"]} | {r["author"]} | '
                     f'{r["style"]} | "{r["quote"]}"')
    return "\n".join(lines)


def build_report(today: datetime.date) -> str:
    rows = gather(today)
    if not rows:
        return (f"# Weekly report — {today.isoformat()}\n\n"
                "No posts in the last 7 days. Nothing to summarise.\n")

    prompt = (
        f"Here are this channel's last {DAYS} days of Stoic Shorts, with peak "
        "views (0 = not yet measured):\n\n"
        f"{_table(rows)}\n\n"
        "Write a brief markdown report (no preamble) with these sections:\n"
        "## Top & bottom posts — name the best and worst performers.\n"
        "## Trends — which themes / authors / title styles correlate with views.\n"
        "## One change to try — exactly ONE concrete, specific suggestion for next week.\n"
        "Be concise and concrete. Ignore 0-view posts when judging performance "
        "(they're just too new to measure)."
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=("You are an analytics assistant for a faceless Stoicism YouTube "
                "Shorts channel. You write short, concrete weekly reports in markdown."),
        messages=[{"role": "user", "content": prompt}],
    )
    body = "".join(b.text for b in msg.content if b.type == "text").strip()
    return f"# Weekly report — {today.isoformat()}\n\n{body}\n"


def main():
    today = datetime.date.today()
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{today.isoformat()}.md"
    out.write_text(build_report(today), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
