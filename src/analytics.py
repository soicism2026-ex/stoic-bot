"""
Pull recent Instagram analytics from Metricool and append to data/analytics.csv.

Runs as its own scheduled job (a day after posting, so numbers have accrued).
Like publish.py, all Metricool-specific calls are isolated here.

Metrics pulled per post where available: reach, impressions/views, likes,
comments, saves, shares. Field names follow Metricool's analytics API; adjust
if their docs differ when you wire it up.
"""
import os
import csv
import datetime
import requests
from pathlib import Path

BASE = "https://app.metricool.com/api"
TOKEN = os.environ["METRICOOL_USER_TOKEN"]
USER_ID = os.environ["METRICOOL_USER_ID"]
BLOG_ID = os.environ["METRICOOL_BLOG_ID"]

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "analytics.csv"
FIELDS = ["pulled_on", "post_date", "reach", "views", "likes",
          "comments", "saves", "shares", "permalink"]


def _headers():
    return {"X-Mc-Auth": TOKEN}


def fetch_recent(days_back: int = 7):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days_back)
    url = f"{BASE}/v2/analytics/posts"
    params = {
        "userId": USER_ID,
        "blogId": BLOG_ID,
        "network": "instagram",
        "from": start.isoformat(),
        "to": end.isoformat(),
    }
    resp = requests.get(url, headers=_headers(), params=params, timeout=120)
    resp.raise_for_status()
    return resp.json().get("data", [])


def append_rows(posts):
    new = not OUT.exists()
    pulled = datetime.date.today().isoformat()
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for p in posts:
            m = p.get("metrics", p)
            w.writerow({
                "pulled_on": pulled,
                "post_date": p.get("date") or p.get("publishedAt", ""),
                "reach": m.get("reach", ""),
                "views": m.get("views") or m.get("impressions", ""),
                "likes": m.get("likes", ""),
                "comments": m.get("comments", ""),
                "saves": m.get("saved") or m.get("saves", ""),
                "shares": m.get("shares", ""),
                "permalink": p.get("permalink", ""),
            })


def main():
    posts = fetch_recent()
    append_rows(posts)
    print(f"Wrote {len(posts)} analytics rows to {OUT.name}")


if __name__ == "__main__":
    main()
