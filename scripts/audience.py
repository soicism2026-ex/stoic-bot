"""
Glaux's audience pull (owner 2026-11-06: "Get everyone working harder"):
WHERE the channel's viewers are and HOW they find the Shorts, from the
YouTube Analytics API, free and on its own quota (no upload units used).

Cicero's posting-time calls rested on upload hours alone; this tells him
which countries actually watch, so a time slot can be read as "evening in the
US" or "morning in India", and how much of the reach is the Shorts feed, search,
the channel page, playlists or subscribers.

    python scripts/audience.py        # pull and write

Writes:
  data/audience.json        the last 28 days: views by country (top 12), by
                            traffic source, and from subscribers vs not; and
                            the YouTube searches that led to our Shorts (top
                            25), over 28 days and since the channel began
                            (owner 2026-11-07: "do some research on things that
                            our audience actually care about ... a list of 10
                            things people might potentially search for")
  data/traffic_sources.csv  views by day and traffic source, upserted daily
                            (Cicero judges the playlist test on it)

Same token as scripts/retention.py (yt-analytics.readonly). Any failure prints
the cause and exits 0: a missing signal must never cost a post.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIENCE = ROOT / "data" / "audience.json"
SOURCES = ROOT / "data" / "traffic_sources.csv"
SOURCE_FIELDS = ["date", "source", "views"]
WINDOW_DAYS = 28
CHANNEL_START = "2026-06-01"     # the first Shorts went up in June 2026
SEARCH = "insightTrafficSourceType==YT_SEARCH"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], token_uri=TOKEN_URI,
                        client_id=os.environ["YOUTUBE_CLIENT_ID"],
                        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], scopes=SCOPES)
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _query(ya, start: dt.date, end: dt.date, dimensions: str, sort: str = "-views", top: int | None = None,
           filters: str | None = None) -> list:
    args = dict(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                metrics="views", dimensions=dimensions, sort=sort)
    if top:
        args["maxResults"] = top
    if filters:
        args["filters"] = filters
    return ya.reports().query(**args).execute().get("rows", [])


def search_terms(ya, start: dt.date, end: dt.date) -> list[dict] | None:
    """The words people typed into YouTube search before watching one of our
    Shorts, most views first (YouTube shows at most 25). None if the report
    failed: it must never cost the rest of the pull."""
    try:
        return shares(_query(ya, start, end, "insightTrafficSourceDetail", top=25, filters=SEARCH))
    except Exception as e:  # noqa: BLE001
        print(f"[audience] search terms skipped ({str(e)[:200]})", file=sys.stderr)
        return None


def shares(rows: list) -> list[dict]:
    """[[key, views], ...] -> [{"key", "views", "share"}], biggest first."""
    total = sum(int(r[-1] or 0) for r in rows) or 1
    out = [{"key": str(r[0]), "views": int(r[-1] or 0), "share": round(int(r[-1] or 0) / total, 3)} for r in rows]
    return sorted(out, key=lambda x: -x["views"])


def upsert_sources(rows: list, path: Path = SOURCES) -> int:
    """Merge [[date, source, views], ...] into the CSV, one row per (date, source)."""
    have: dict[tuple[str, str], int] = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                have[(r["date"], r["source"])] = int(r["views"] or 0)
    for day, source, views in rows:
        have[(str(day), str(source))] = int(views or 0)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_FIELDS)
        w.writeheader()
        for (day, source), views in sorted(have.items()):
            w.writerow({"date": day, "source": source, "views": views})
    return len(rows)


def main() -> int:
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=WINDOW_DAYS)
    try:
        ya = _service()
        countries = _query(ya, start, today, "country", top=12)
        sources = _query(ya, start, today, "insightTrafficSourceType")
        subscribed = _query(ya, start, today, "subscribedStatus")
        by_day = _query(ya, start, today, "day,insightTrafficSourceType", sort="day")
    except Exception as e:  # noqa: BLE001
        print(f"[audience] pull failed ({str(e)[:300]}); skipping. Same token and API as "
              "scripts/retention.py: if that one fails too, see its message.", file=sys.stderr)
        return 0
    doc = {"pulled_on": today.isoformat(), "window": [start.isoformat(), today.isoformat()],
           "countries": shares(countries), "sources": shares(sources), "subscribed": shares(subscribed),
           "searchTerms": search_terms(ya, start, today),
           "searchTermsAllTime": search_terms(ya, dt.date.fromisoformat(CHANNEL_START), today)}
    AUDIENCE.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    n = upsert_sources(by_day)
    top = ", ".join(f"{c['key']} {c['share']:.0%}" for c in doc["countries"][:5])
    terms = ", ".join(f"{t['key']} ({t['views']})" for t in (doc["searchTermsAllTime"] or [])[:8])
    print(f"[audience] {sum(c['views'] for c in doc['countries'])} views in 28 days; top countries: {top}; "
          f"{n} day-by-source rows; searches that found us: {terms or 'none reported'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
