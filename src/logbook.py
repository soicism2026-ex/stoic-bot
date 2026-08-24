"""
Append each post to data/posts.csv. This file is committed back to the repo by
the GitHub Action, so your full posting history lives in git for free.
"""
import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posts.csv"

# 'hook' is appended last so the Hook-lab agent (scripts/channel_report.py) can
# analyse which hook styles drive views. Trailing position keeps older
# positional readers and content.py's header-keyed reader working unchanged.
FIELDS = ["date", "theme", "author", "quote", "caption", "video_url", "video_id",
          "voice_name", "music_track", "hook", "experiment", "format",
          # Which provider actually served the backgrounds. Added 2026-08-25
          # after the switch from stock VIDEO to AI STILLS coincided with a
          # 3.8x drop in day-3 views and could only be established by
          # inferring from commit dates, because the single most important
          # production variable was never recorded. Never again.
          "bg_source"]


def _repair_header() -> bool:
    """Rewrite line 1 if it has drifted from FIELDS. Returns True if repaired.

    THE BUG THIS EXISTS TO PREVENT: the header is only written when the file is
    created, but FIELDS has grown over time (7 -> 9 -> 10 -> 11 -> 12 columns).
    posts.csv therefore sat with a 7-column header over 12-column rows, and
    csv.DictReader — which keys off the HEADER, not the data — dropped every
    column past video_id into a single None key. Everything that rotates off
    those columns went silently blind at once:

        content.py  recent-hook dedup      -> never saw a hook, so hooks repeated
        content.py  rule-number assignment -> used_ns always empty, so EVERY
                                              rule post shipped as "Rule 7"
        tts.py      voice LRU + weighting  -> never saw voice_name
        music.py    track LRU + weighting  -> never saw music_track

    No error, no warning, three months of quietly degrading variety. Adding a
    column must never be able to do that again, so the header is verified on
    every single append. Only line 1 is touched — post rows are never altered.
    """
    if not LOG.exists():
        return False
    with open(LOG, newline="", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return False
    current = next(csv.reader([lines[0]]), [])
    if current == FIELDS:
        return False
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(FIELDS)
    lines[0] = buf.getvalue()
    with open(LOG, "w", newline="", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[logbook] posts.csv header was stale {current} -> repaired to "
          f"{len(FIELDS)} columns; rotation history is readable again",
          flush=True)
    return True


def log_post(date, theme, quote, author, caption, publish_result,
             voice_name: str = "", music_track: str = "", hook: str = "",
             experiment: str = "", content_format: str = "",
             bg_source: str = ""):
    new = not LOG.exists()
    if not new:
        _repair_header()
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
            "voice_name": voice_name,
            "music_track": music_track,
            "hook": (hook or "").replace("\n", " ").strip(),
            "experiment": experiment,
            "format": content_format,
            "bg_source": bg_source,
        })
