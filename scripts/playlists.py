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

Only PUBLIC Shorts are filed, and a Short that turns unlisted is taken out:
scripts/prune_videos.py unlists weak Shorts after a week to keep them off the
channel page, and a public playlist must not bring them back. What is in each
playlist is read from YouTube every run, so a Short is never filed twice,
even if the state file was lost.

State: data/playlists.json {"playlists": {author: playlist id},
"filed": {video id: author}} (what the playlists held after the last run).
Quota: making a playlist, filing or removing a Short costs 50 of the 10,000
units a day the uploads also need (an upload is 1,600), so one run makes at
most MAX_CALLS of them; a backfill takes a few runs. Reads cost 1 per 50.
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


def ensure_playlist(yt, author: str, st: dict) -> tuple[str, bool]:
    """(the author's playlist id, whether it was just made): found by title
    among the channel's own playlists, or made."""
    if st["playlists"].get(author):
        return st["playlists"][author], False
    title = TITLE.format(author=author)
    req = yt.playlists().list(part="snippet", mine=True, maxResults=50)
    while req is not None:
        resp = req.execute()
        for p in resp.get("items", []):
            if p["snippet"]["title"] == title:
                st["playlists"][author] = p["id"]
                return p["id"], False
        req = yt.playlists().list_next(req, resp)
    made = yt.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": DESCRIPTION.format(author=author), "defaultLanguage": "en"},
        "status": {"privacyStatus": "public"}}).execute()
    st["playlists"][author] = made["id"]
    print(f"  [playlists] made '{title}'")
    return made["id"], True


def public_ids(yt, ids: list[str]) -> set[str]:
    """The ones still public, 50 per read (1 unit each)."""
    out: set[str] = set()
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="status", id=",".join(ids[i:i + 50]), maxResults=50).execute()
        out |= {v["id"] for v in resp.get("items", [])
                if (v.get("status") or {}).get("privacyStatus") == "public"}
    return out


def items_in(yt, pid: str) -> dict[str, str]:
    """{video id: playlist item id} for what the playlist holds now."""
    out: dict[str, str] = {}
    req = yt.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50)
    while req is not None:
        resp = req.execute()
        for it in resp.get("items", []):
            out[it["contentDetails"]["videoId"]] = it["id"]
        req = yt.playlistItems().list_next(req, resp)
    return out


def _insert(yt, pid: str, vid: str) -> None:
    """At the top; a playlist that is not sorted by hand takes it at the end."""
    body = {"snippet": {"playlistId": pid, "position": 0,
                        "resourceId": {"kind": "youtube#video", "videoId": vid}}}
    try:
        yt.playlistItems().insert(part="snippet", body=body).execute()
    except Exception as e:  # noqa: BLE001
        if "manualSortRequired" not in str(e):
            raise
        del body["snippet"]["position"]
        yt.playlistItems().insert(part="snippet", body=body).execute()


def run(dry_run: bool = False, yt=None) -> int:
    if not gate():
        print("  [playlists] waiting for the owner's yes (Cicero's test 3): nothing to do")
        return 0
    with open(ROOT / "data" / "posts.csv", newline="", encoding="utf-8") as f:
        posts = list(csv.DictReader(f))
    st = load_state()
    edits = to_file(posts, {})                      # every edit, oldest first
    if not edits:
        print("  [playlists] no edits to file")
        return 0
    if dry_run:
        for vid, author in to_file(posts, st["filed"])[:MAX_CALLS]:
            print(f"  [playlists] would file {vid} under {author} (if it is still public)")
        return 0
    if yt is None:
        from publish import _service  # noqa: PLC0415
        yt = _service(extra_scopes=[FORCE_SSL])
    calls, added, removed = 0, 0, 0
    try:
        public = public_ids(yt, [v for v, _ in edits])
        for author in AUTHORS:
            mine = [v for v, a in edits if a == author]
            if not mine or calls >= MAX_CALLS:
                continue
            pid, made = ensure_playlist(yt, author, st)
            calls += int(made)
            held = items_in(yt, pid)                 # what YouTube holds is the truth
            st["filed"] = {**{v: a for v, a in st["filed"].items() if a != author},
                           **{v: author for v in held}}
            for vid, item in list(held.items()):     # unlisted since: out of the public playlist
                if vid not in public and calls < MAX_CALLS:
                    yt.playlistItems().delete(id=item).execute()
                    del held[vid]
                    st["filed"].pop(vid, None)
                    calls += 1
                    removed += 1
            for vid in mine:
                if vid in public and vid not in held and calls < MAX_CALLS:
                    _insert(yt, pid, vid)
                    held[vid] = ""
                    st["filed"][vid] = author
                    calls += 1
                    added += 1
    except Exception as e:  # noqa: BLE001  quota or a deleted video: keep what was done
        print(f"  [playlists] stopped: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
    finally:
        save_state(st)
    print(f"  [playlists] +{added} filed, -{removed} taken out (unlisted); {len(st['filed'])} Shorts in "
          f"{len(st['playlists'])} playlists" + ("; more next run" if calls >= MAX_CALLS else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    return run(ap.parse_args().dry_run)


if __name__ == "__main__":
    sys.exit(main())
