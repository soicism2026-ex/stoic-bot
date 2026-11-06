"""
Cicero's test 3 (owner's yes needed): a playlist per philosopher, with every
edit filed in it, so a viewer who liked one Short can watch the rest in a
row, and the playlists can turn up when people search for that philosopher.

    python scripts/playlists.py            # file what's missing (quota-capped)
    python scripts/playlists.py --dry-run  # say what it would do, call nothing

GATED. The code ships, the change doesn't: it does nothing unless the
"playlists" test in data/marketing_tests.json is running (the owner said yes
in the HQ) or has been adopted. Owner's rule: "dont ship anything until i
approve it".

Only edits are filed (the format since 2026-10-02, posts.csv experiment
"edit:<id>"): the older formats are a different, weaker look the channel has
moved on from. Newest first, so the playlist opens on the latest Short.

State: data/playlists.json {"playlists": {author: playlist id},
"filed": {video id: author}}. Quota: a new playlist or a filed video costs 50
of the 10,000 units a day the uploads also need (an upload is 1,600), so one
run makes at most MAX_CALLS write calls; a backfill takes a few runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

STATE = ROOT / "data" / "playlists.json"
TESTS = ROOT / "data" / "marketing_tests.json"
MAX_CALLS = 40                      # 2,000 units at most per run
AUTHORS = ("Marcus Aurelius", "Seneca", "Epictetus")
TITLE = "{author} quotes: Stoic Shorts"
DESCRIPTION = ("Short readings from {author}, word for word from the original text, "
               "with the source in every description. A new one most days.")
FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"


def gate() -> bool:
    """True only once the owner said yes (test running) or adopted it."""
    try:
        tests = json.loads(TESTS.read_text(encoding="utf-8")).get("tests", [])
    except Exception:  # noqa: BLE001
        return False
    t = next((t for t in tests if t.get("id") == "playlists"), None)
    return bool(t) and (t.get("status") == "running" or t.get("adopted") == "yes")


def load_state() -> dict:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    return {"playlists": dict(st.get("playlists") or {}), "filed": dict(st.get("filed") or {})}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def to_file(posts: list[dict], filed: dict) -> list[tuple[str, str]]:
    """(video id, author) for every edit not filed yet, oldest first: each is
    inserted at the top, so the playlist ends up newest first."""
    out = []
    for r in posts:
        vid, author = (r.get("video_id") or "").strip(), (r.get("author") or "").strip()
        if (vid and author in AUTHORS and (r.get("experiment") or "").startswith("edit:")
                and vid not in filed and (vid, author) not in out):
            out.append((vid, author))
    return out


def ensure_playlist(yt, author: str, st: dict) -> str:
    """The author's playlist id, found by title among the channel's own or made."""
    if st["playlists"].get(author):
        return st["playlists"][author]
    title = TITLE.format(author=author)
    req = yt.playlists().list(part="snippet", mine=True, maxResults=50)
    while req is not None:
        resp = req.execute()
        for p in resp.get("items", []):
            if p["snippet"]["title"] == title:
                st["playlists"][author] = p["id"]
                return p["id"]
        req = yt.playlists().list_next(req, resp)
    made = yt.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": DESCRIPTION.format(author=author), "defaultLanguage": "en"},
        "status": {"privacyStatus": "public"}}).execute()
    st["playlists"][author] = made["id"]
    print(f"  [playlists] made '{title}'")
    return made["id"]


def run(dry_run: bool = False, yt=None) -> int:
    if not gate():
        print("  [playlists] waiting for the owner's yes (Cicero's test 3): nothing to do")
        return 0
    with open(ROOT / "data" / "posts.csv", newline="", encoding="utf-8") as f:
        posts = list(csv.DictReader(f))
    st = load_state()
    todo = to_file(posts, st["filed"])
    if not todo:
        print("  [playlists] every edit is filed")
        return 0
    if dry_run:
        for vid, author in todo[:MAX_CALLS]:
            print(f"  [playlists] would file {vid} under {author}")
        return 0
    if yt is None:
        from publish import _service  # noqa: PLC0415
        yt = _service(extra_scopes=[FORCE_SSL])
    calls = 0
    try:
        for vid, author in todo:
            if calls >= MAX_CALLS:
                break
            had = bool(st["playlists"].get(author))
            pid = ensure_playlist(yt, author, st)
            calls += 0 if had else 1
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": pid, "position": 0,
                "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
            st["filed"][vid] = author
            calls += 1
    except Exception as e:  # noqa: BLE001  quota or a deleted video: keep what was filed
        print(f"  [playlists] stopped: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
    finally:
        save_state(st)
    left = len(todo) - sum(1 for v, _ in todo if v in st["filed"])
    print(f"  [playlists] filed {len(st['filed'])} edits in {len(st['playlists'])} playlists"
          + (f"; {left} left for the next run" if left else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    return run(ap.parse_args().dry_run)


if __name__ == "__main__":
    sys.exit(main())
