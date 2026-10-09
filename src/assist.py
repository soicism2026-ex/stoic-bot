"""
ASSISTED POSTING: the owner adds the song, the bot does everything else.

Owner, 2026-10-09: "I want the trending audios i mentioned anything else is
not good enough." Those songs (data/trending_songs.json: Hans Zimmer, Me and
the Devil, L'Amour Toujours, ...) can only be used legally by picking them in
the Shorts sound library INSIDE the YouTube app. The rights holder then shares
that Short's revenue and nothing is claimed. The Data API cannot attach them,
and uploading them already mixed in gets every video claimed. So the one tap
that needs the app is the owner's; everything else stays automatic.

POST_MODE=assist (daily-short.yml):
  1. daily_post renders the edit with the VOICE ONLY and, instead of
     uploading, queues it: data/assist/pending/<id>.json plus a GitHub
     release whose notes name the song to add and the title to paste.
     releases/latest/download/edit.mp4 is always the newest video.
  2. The owner posts it from the YouTube app with the song.
  3. scripts/adopt_uploads.py (every 30 min) finds that upload, matches it
     to the queued edit, and does the rest: description with the journal
     link, tags, thumbnail, comments, and the posts.csv row that analytics,
     pruning and content rotation all run on.

One JSON file per queued video, never a shared list: the daily pipeline adds
files while the adopter deletes them, and separate files cannot conflict when
both push to main.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
from pathlib import Path

import shuffle

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "assist"
PENDING = DIR / "pending"
RELEASE = DIR / "release.json"          # tells the workflow to publish one
SONGS = ROOT / "data" / "trending_songs.json"
SONG_PREFIX = "trending:"
QUEUE = int(os.environ.get("ASSIST_QUEUE", "2"))
REPO = os.environ.get("GITHUB_REPOSITORY", "soicism2026-ex/stoic-bot")
# Owner: "the music is a bit too loud compared to the voice talking".
MUSIC_PERCENT = int(os.environ.get("ASSIST_MUSIC_PERCENT", "25"))


def enabled() -> bool:
    return os.environ.get("POST_MODE", "auto").strip().lower() == "assist"


# ------------------------------------------------------------- the queue ---

def load() -> list[dict]:
    """Queued videos, oldest first."""
    if not PENDING.exists():
        return []
    items = []
    for f in sorted(PENDING.glob("*.json")):
        try:
            items.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return sorted(items, key=lambda p: p.get("prepared_at", ""))


def full() -> bool:
    return len(load()) >= QUEUE


def as_rows(pending: list[dict]) -> list[dict]:
    """Queued videos as posts.csv-shaped rows, so content and song rotation
    never pick something that is already waiting to be posted."""
    return [{"date": p.get("date", ""), "theme": p.get("theme", ""),
             "experiment": p.get("experiment", ""),
             "music_track": p.get("music_track", ""),
             "format": p.get("format", "")} for p in pending]


def remove(pid: str) -> None:
    """Drop a posted video from the queue (and its thumbnail, notes, file)."""
    for f in (PENDING / f"{pid}.json", DIR / f"{pid}.jpg", DIR / f"{pid}.md",
              DIR / f"{pid}.mp4"):
        if f.exists():
            f.unlink()


# ------------------------------------------------------------- the songs ---

def songs() -> list[dict]:
    return json.loads(SONGS.read_text(encoding="utf-8"))


def pick_song(post_rows: list[dict], seed: str = "") -> dict | None:
    """The owner's songs, shuffled across posts (src/shuffle.py)."""
    by_id = {s["id"]: s for s in songs()}
    played = [(r.get("music_track") or "").removeprefix(SONG_PREFIX) for r in post_rows
              if (r.get("music_track") or "").startswith(SONG_PREFIX)]
    sid = shuffle.pick(by_id, played, seed)
    return by_id[sid] if sid else None


# ------------------------------------------------------ queue one video ---

def notes(p: dict) -> str:
    """The release text the owner reads on his phone."""
    s = p["song"]
    return f"""## Add **{s['title']}** ({s['artist']}) and post

1. Tap **edit.mp4** under *Assets* below and save the video.
2. YouTube app → **+** → **Create a Short** → pick the video from your gallery.
3. **Add sound** → search **{s['search']}** → choose **{s['title']}**. Keep the part the app suggests, or drag to the part you know from trending edits.
4. **Volume**: Original sound **100%**, Added sound **{MUSIC_PERCENT}%** (the voice stays louder).
5. **Next** → paste the title → **Upload** as **Public**.

Title to paste:
```
{p['title']}
```

Within about 30 minutes the bot adds the description with the journal link, the tags, the thumbnail and the comments.

> {p['quote']}
> — {p['author']}{(', ' + p['citation']) if p.get('citation') else ''}
"""


def queue(record: dict, video: Path, thumb: Path | None = None) -> dict:
    """Queue a rendered, QA-passed video for the owner to post."""
    PENDING.mkdir(parents=True, exist_ok=True)
    pid = record["id"]
    shutil.copyfile(video, DIR / f"{pid}.mp4")          # gitignored; released
    if thumb and Path(thumb).exists():
        shutil.copyfile(thumb, DIR / f"{pid}.jpg")
    record = {**record,
              "prepared_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                  timespec="seconds")}
    (PENDING / f"{pid}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False),
                                         encoding="utf-8")
    (DIR / f"{pid}.md").write_text(notes(record), encoding="utf-8")
    RELEASE.write_text(json.dumps({
        "tag": f"edit-{pid}",
        "name": f"{record['date']}  ·  add {record['song']['title']}",
        "video": str((DIR / f"{pid}.mp4").relative_to(ROOT)),
        "notes": str((DIR / f"{pid}.md").relative_to(ROOT)),
    }, indent=1), encoding="utf-8")
    return record


def latest_link() -> str:
    return f"https://github.com/{REPO}/releases/latest/download/edit.mp4"


# ---------------------------------------------- matching the owner's upload ---

def parse_duration(iso: str) -> float:
    """ISO 8601 duration as YouTube returns it (PT13S, PT1M2S) -> seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", iso or "")
    if not m:
        return 0.0
    d, h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower()).split())


def _ts(iso: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))


def match(pending: list[dict], uploads: list[dict], logged: set,
          tolerance: float = 2.0) -> list[tuple[dict, dict]]:
    """Pair each new upload with the queued video it is.

    An upload counts only if it is not already in posts.csv and appeared after
    the video was queued. The title the owner pasted identifies it; if he
    retyped the title, the length does (the song is cut to the video's
    length, so the Short keeps the rendered duration), oldest queued first.
    """
    pairs, used = [], set()
    for u in sorted(uploads, key=lambda u: u.get("published_at", "")):
        if u["video_id"] in logged:
            continue
        try:
            when = _ts(u["published_at"])
        except ValueError:
            continue
        open_ = [p for p in pending if p["id"] not in used
                 and _ts(p["prepared_at"]) <= when + datetime.timedelta(minutes=10)]
        title = _norm(u.get("title", ""))

        def same_title(p: dict) -> bool:
            hook = _norm(p.get("hook", ""))
            return bool(title) and (_norm(p["title"]) == title or (bool(hook) and hook in title))

        hit = next((p for p in open_ if same_title(p)), None)
        if hit is None:
            # Closest length wins (YouTube reports whole seconds); a tie goes
            # to the video queued first.
            def gap(p: dict) -> float:
                return abs(float(u.get("duration", 0)) - float(p["duration"]))
            near = [p for p in open_ if p.get("duration") and gap(p) <= tolerance]
            hit = min(near, key=gap) if near else None
        if hit is not None:
            used.add(hit["id"])
            pairs.append((hit, u))
    return pairs
