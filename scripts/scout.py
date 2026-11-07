"""
The scout: what is winning in our niche right now, on other channels.

Owner, 2026-11-07, in the HQ, sending Jake Trinder's advice on growing a
channel ("use this advice to grow our youtube channel"): "Knowing your
audience matters, but it does not prove that they will choose the subject on
YouTube. So, you need evidence that they will actually watch these videos
before you even press record."

Our own Shorts are too few to prove much (the best ever: 1,255 views). The
niche's are not. Once a day, free (YouTube Data API, about 620 of the 10,000
units a day), Glaux:

  1. searches recent Shorts (the last 30 days, US, English, most viewed first)
     for a few of the niche's searches ("stoicism", "stoic", "marcus aurelius"...)
  2. reads each one's views and length, and its channel's subscribers
  3. keeps the OUTLIERS: Shorts that reached far past their own channel
     (views at least twice the channel's subscribers, counting at least
     1,000; at least 20,000 views; three minutes or less). A big channel's
     usual hit proves the channel; an outlier proves the topic and the
     packaging.
  4. sorts them by our 12 themes and our three philosophers, and keeps the
     titles that won (the packaging lesson)

Writes data/scout.json and data/scout.md, overwritten each run (only the
latest read is kept). Varro reads it before every restock: write quotes on
the topics the niche proves, packaged like its winners.

    python scripts/scout.py            # search, read, write
    python scripts/scout.py --dry-run  # say what it would search; no API calls

Any failure prints the cause and exits 0: a missing signal must never cost a
post. Tests: tests/test_scout.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT_JSON = ROOT / "data" / "scout.json"
OUT_MD = ROOT / "data" / "scout.md"
OUR_CHANNEL = "UCoc54iJp29coIxWuuKwxVuw"      # forged.in.stoicism (reply_to_comments.py's own-channel id)
SEEDS = ["stoicism", "stoic", "marcus aurelius", "stoic quotes", "seneca", "epictetus"]
WINDOW_DAYS = 30
MIN_VIEWS = 20_000
MIN_SUBS = 1_000          # a 40-subscriber channel's 20k views is luck, not a 500x signal
MIN_SCORE = 2.0           # views at least twice the channel's subscribers
MAX_SECONDS = 180         # a Short is three minutes at most
TOP = 15

# Words in a title that put a Short under one of our themes (data/edit_quotes.json).
THEME_WORDS = {
    "discipline": ["discipline", "habit", "lazy", "routine", "consisten", "grind", "focus", "self control"],
    "control": ["control", "overthink", "worry", "worrying", "out of your hands"],
    "anger": ["anger", "angry", "calm", "react", "emotion", "temper", "patience", "provok"],
    "mortality": ["death", "die ", "dying", "memento mori", "mortal", "life is short"],
    "ego": ["ego", "pride", "opinion", "what others think", "what people think", "validation", "approval",
            "respect", "humble", "arrogan"],
    "resilience": ["strong", "strength", "pain", "tough", "endure", "resilien", "unbreakable", "mentally"],
    "fear": ["fear", "afraid", "anxiety", "anxious", "scared", "courage"],
    "desire": ["money", "wealth", "rich", "desire", "happy with less", "content with", "minimal", "greed"],
    "time": ["time", "waste", "today", "tomorrow", "procrastinat"],
    "friendship": ["friend", "toxic", "alone", "lonely", "loneliness", "company", "relationship"],
    "duty": ["work", "purpose", "duty", "responsib"],
    "adversity": ["obstacle", "setback", "adversity", "fail", "hard times", "struggle", "suffer"],
}
AUTHORS = {"Marcus Aurelius": ["marcus", "aurelius", "meditations"], "Seneca": ["seneca"],
           "Epictetus": ["epictetus"]}


def seconds(iso: str) -> int:
    """ISO 8601 duration ("PT1M5S") to seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def themes_of(title: str) -> list[str]:
    t = f" {title.lower()} "
    return [k for k, words in THEME_WORDS.items() if any(w in t for w in words)]


def author_of(title: str) -> str | None:
    t = title.lower()
    return next((a for a, words in AUTHORS.items() if any(w in t for w in words)), None)


def search(yt, q: str, after: dt.datetime) -> list[str]:
    resp = yt.search().list(part="id", q=q, type="video", videoDuration="short", order="viewCount",
                            publishedAfter=after.strftime("%Y-%m-%dT%H:%M:%SZ"), regionCode="US",
                            relevanceLanguage="en", maxResults=50).execute()
    return [i["id"]["videoId"] for i in resp.get("items", []) if i.get("id", {}).get("videoId")]


def details(yt, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            sn, stt = v.get("snippet") or {}, v.get("statistics") or {}
            out[v["id"]] = {"id": v["id"], "title": sn.get("title", ""), "channelId": sn.get("channelId"),
                            "channel": sn.get("channelTitle", ""), "published": (sn.get("publishedAt") or "")[:10],
                            "views": int(stt.get("viewCount") or 0),
                            "seconds": seconds((v.get("contentDetails") or {}).get("duration", ""))}
    return out


def subscribers(yt, channel_ids: list[str]) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for i in range(0, len(channel_ids), 50):
        resp = yt.channels().list(part="statistics", id=",".join(channel_ids[i:i + 50])).execute()
        for c in resp.get("items", []):
            stt = c.get("statistics") or {}
            out[c["id"]] = None if stt.get("hiddenSubscriberCount") else int(stt.get("subscriberCount") or 0)
    return out


def outliers(videos: dict[str, dict], subs: dict[str, int | None]) -> list[dict]:
    """Shorts that reached far past their own channel, best first."""
    out = []
    for v in videos.values():
        n = subs.get(v["channelId"])
        if (v["channelId"] == OUR_CHANNEL or n is None or v["views"] < MIN_VIEWS
                or not 0 < v["seconds"] <= MAX_SECONDS):
            continue
        score = v["views"] / max(n, MIN_SUBS)
        if score < MIN_SCORE:
            continue
        out.append({**v, "subscribers": n, "score": round(score, 1), "themes": themes_of(v["title"]),
                    "author": author_of(v["title"]), "url": f"https://youtube.com/shorts/{v['id']}"})
    return sorted(out, key=lambda x: -x["score"])


def summarize(outs: list[dict], searched: list[str], videos: int, today: dt.date) -> dict:
    def group(key_of) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for o in outs:
            for k in key_of(o):
                groups.setdefault(k, []).append(o)
        rows = [{"key": k, "outliers": len(g), "medianViews": int(st.median(x["views"] for x in g)),
                 "medianScore": round(st.median(x["score"] for x in g), 1)} for k, g in groups.items()]
        return sorted(rows, key=lambda r: (-r["outliers"], -r["medianViews"]))
    keep = ("title", "channel", "views", "subscribers", "score", "published", "seconds", "themes", "author", "url")
    return {
        "updated": today.isoformat(), "window": WINDOW_DAYS, "searched": searched, "videos": videos,
        "outliers": len(outs),
        "themes": group(lambda o: o["themes"] or ["(none of ours)"]),
        "authors": group(lambda o: [o["author"]] if o["author"] else []),
        "top": [{k: o[k] for k in keep} for o in outs[:TOP]],
    }


def markdown(s: dict) -> str:
    lines = [
        "# The scout: what's winning in our niche",
        "",
        f"_Updated {s['updated']} by Glaux (scripts/scout.py, free). Stoicism Shorts from the last "
        f"{s['window']} days on other channels: {s['videos']} read, {s['outliers']} outliers (at least "
        f"{MIN_VIEWS:,} views, and far past their own channel's subscribers)._",
        "",
        "Evidence before we make a Short (owner 2026-11-07, Jake Trinder's advice): write on the topics the",
        "niche proves, packaged like its winners. Searched: " + ", ".join(f'"{q}"' for q in s["searched"]) + ".",
        "",
        "## Topics that win (by our themes)",
        "",
        "| Theme | Outliers | Median views | Median views per subscriber |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r['key']} | {r['outliers']} | {r['medianViews']:,} | {r['medianScore']}x |" for r in s["themes"]]
    if s["authors"]:
        lines += ["", "## Philosophers in the winning titles", "",
                  "| Philosopher | Outliers | Median views |", "|---|---|---|"]
        lines += [f"| {r['key']} | {r['outliers']} | {r['medianViews']:,} |" for r in s["authors"]]
    lines += ["", "## The titles that won (the packaging)", "",
              "| Views | Per subscriber | Title | Channel |", "|---|---|---|---|"]
    for o in s["top"]:
        title = o["title"].replace("|", "/")
        lines.append(f"| {o['views']:,} | {o['score']}x | [{title}]({o['url']}) | {o['channel'].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def run(yt, today: dt.date, seeds: list[str] = SEEDS) -> dict:
    after = dt.datetime.combine(today - dt.timedelta(days=WINDOW_DAYS), dt.time(), tzinfo=dt.timezone.utc)
    ids: list[str] = []
    for q in seeds:
        ids += [i for i in search(yt, q, after) if i not in ids]
    videos = details(yt, ids)
    subs = subscribers(yt, sorted({v["channelId"] for v in videos.values() if v.get("channelId")}))
    return summarize(outliers(videos, subs), seeds, len(videos), today)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    today = dt.datetime.now(dt.timezone.utc).date()
    if a.dry_run:
        print(f"[scout] would search {SEEDS} for Shorts since {today - dt.timedelta(days=WINDOW_DAYS)}")
        return 0
    try:
        from publish import _service  # noqa: PLC0415
        s = run(_service(), today)
    except Exception as e:  # noqa: BLE001
        print(f"[scout] skipped: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
        return 0
    OUT_JSON.write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    OUT_MD.write_text(markdown(s), encoding="utf-8")
    top = ", ".join(f"{r['key']} {r['outliers']}" for r in s["themes"][:5])
    print(f"[scout] {s['videos']} Shorts read, {s['outliers']} outliers; winning themes: {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
