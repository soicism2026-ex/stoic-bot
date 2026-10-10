"""
Publish the video daily_post just queued as a GitHub release (assisted posting).

Runs in daily-short.yml right after daily_post. When daily_post queued a
video (data/assist/release.json), it is published; the asset is always named
edit.mp4, so
    https://github.com/<repo>/releases/latest/download/edit.mp4
is always the newest video to post, and the release notes say which song to
add and which title to paste. adopt_uploads.py deletes a release once the
owner has posted it, and sync() removes any release whose video is no longer
queued, so the Releases page is exactly the "to post" list. Releases older
than KEEP_DAYS are pruned as a backstop.
"""
from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "data" / "assist" / "release.json"
PENDING = ROOT / "data" / "assist" / "pending"
KEEP_DAYS = 14


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True)


def prune(keep_days: int = KEEP_DAYS) -> None:
    r = _gh("release", "list", "--limit", "200", "--json", "tagName,createdAt", check=False)
    if r.returncode != 0:
        print(f"[release] could not list releases: {r.stderr.strip()[:200]}", file=sys.stderr)
        return
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=keep_days)
    for rel in json.loads(r.stdout or "[]"):
        tag = rel.get("tagName", "")
        when = datetime.datetime.fromisoformat(rel["createdAt"].replace("Z", "+00:00"))
        if tag.startswith("edit-") and when < cutoff:
            _gh("release", "delete", tag, "--yes", "--cleanup-tag", check=False)
            print(f"[release] pruned {tag}")


def _withdraw(pid: str) -> None:
    """Take a video out of the queue (its file is gone, so it can never be
    posted); the content goes back into rotation and is rendered again."""
    for f in (PENDING / f"{pid}.json", PENDING.parent / f"{pid}.jpg",
              PENDING.parent / f"{pid}.md", PENDING.parent / f"{pid}.mp4"):
        if f.exists():
            f.unlink()
    print(f"[release] withdrew {pid}: it has no release, so it would never be posted")


def sync(just_published: str = "") -> None:
    """The Releases page lists exactly the videos still waiting to be posted,
    and every queued video has a release.
      * an edit-* release whose video is no longer queued (posted, or
        withdrawn) is deleted;
      * a queued video with no release is withdrawn: its .mp4 only ever
        existed on the runner that rendered it, so it can never be released
        later and would hold a queue slot forever.
    Nothing is changed when the release list cannot be read."""
    queued = {p.stem for p in PENDING.glob("*.json")} if PENDING.exists() else set()
    r = _gh("release", "list", "--limit", "200", "--json", "tagName", check=False)
    if r.returncode != 0:
        print(f"[release] could not list releases: {r.stderr.strip()[:200]}", file=sys.stderr)
        return
    released = set()
    for rel in json.loads(r.stdout or "[]"):
        tag = rel.get("tagName", "")
        if not tag.startswith("edit-"):
            continue
        pid = tag[len("edit-"):]
        if pid in queued:
            released.add(pid)
        else:
            _gh("release", "delete", tag, "--yes", "--cleanup-tag", check=False)
            print(f"[release] removed {tag} (no longer waiting to be posted)")
    for pid in sorted(queued - released - {just_published}):
        _withdraw(pid)


def publish(r: dict) -> bool:
    """Create the release for a newly queued video. A leftover release with
    the same tag is replaced, never collided with."""
    video, notes = ROOT / r["video"], ROOT / r["notes"]
    _gh("release", "delete", r["tag"], "--yes", "--cleanup-tag", check=False)
    with tempfile.TemporaryDirectory() as td:
        asset = Path(td) / "edit.mp4"
        shutil.copyfile(video, asset)
        res = _gh("release", "create", r["tag"], str(asset), "--title", r["name"],
                  "--notes-file", str(notes), "--latest", check=False)
    if res.returncode != 0:
        print(f"[release] could not publish {r['tag']}: {res.stderr.strip()[:300]}",
              file=sys.stderr)
        return False
    print(f"[release] {r['tag']} published: {r['name']}")
    return True


def main() -> int:
    ok, published = True, ""
    if REL.exists():
        r = json.loads(REL.read_text(encoding="utf-8"))
        REL.unlink()
        if publish(r):
            published = r["tag"][len("edit-"):]
        else:
            ok = False      # sync() below withdraws it, so it is re-rendered
    else:
        print("[release] no new video queued this run")
    sync(just_published=published)
    prune()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
