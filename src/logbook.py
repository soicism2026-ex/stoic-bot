"""
Append each post to data/posts.csv. This file is committed back to the repo by
the GitHub Action, so your full posting history lives in git for free.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posts.csv"

FIELDS = ["date", "theme", "author", "quote", "caption", "scheduled_for", "raw_result"]


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
            "scheduled_for": publish_result.get("publish_at", ""),
            "raw_result": json.dumps(publish_result.get("response", {}))[:500],
        })
