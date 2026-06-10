"""
Append each post to data/posts.csv. This file is committed back to the repo by
the GitHub Action, so your full posting history lives in git for free.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posts.csv"

FIELDS = ["date", "theme", "author", "quote", "caption",
          "video_url", "video_id", "title_style"]


def classify_title_style(text: str) -> str:
    """Bucket a headline/quote into question | statement | fragment.

    Shared by logbook (writes it per post) and content.py / weekly_report.py
    (read it back for the feedback loop). Kept here so it has no heavy deps.
    """
    t = (text or "").strip()
    if not t:
        return "unknown"
    if "?" in t:
        return "question"
    if t.endswith((".", "!", '."', '!"', ".'", "!'")):
        return "statement"
    return "fragment"


def log_post(date, theme, quote, author, caption, publish_result):
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "date": date,
            "theme": theme,
            "author": author,
            "quote": quote,
            "caption": caption.replace("\n", " / "),
            "video_url": publish_result.get("url", ""),
            "video_id": publish_result.get("video_id", ""),
            "title_style": classify_title_style(quote),
        })
