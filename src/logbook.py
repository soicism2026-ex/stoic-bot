"""
Append each post to data/posts.csv. This file is committed back to the repo by
the GitHub Action, so your full posting history lives in git for free.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posts.csv"

FIELDS = ["date", "theme", "author", "quote", "caption", "video_url", "video_id"]


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
        })
