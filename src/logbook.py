"""
Append each post to data/posts.csv. This file is committed back to the repo by
the GitHub Action, so your full posting history lives in git for free.

The file is rewritten in full each run so the header always matches the columns
(older rows are backfilled with empty values for newer columns like `background`).
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posts.csv"

FIELDS = ["date", "theme", "author", "quote", "caption", "video_url", "video_id", "background"]


def log_post(date, theme, quote, author, caption, publish_result, background=""):
    rows = []
    if LOG.exists():
        with open(LOG, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    rows.append({
        "date": date,
        "theme": theme,
        "author": author,
        "quote": quote,
        "caption": caption.replace("\n", " / "),
        "video_url": publish_result.get("url", ""),
        "video_id": publish_result.get("video_id", ""),
        "background": background,
    })

    with open(LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
