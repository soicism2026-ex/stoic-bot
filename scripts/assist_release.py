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


def sync() -> None:
    """The Releases page lists exactly the videos still waiting to be posted.
    Any edit-* release whose video is no longer queued (posted, or withdrawn
    by deleting its data/assist/pending/<id>.json) is deleted."""
    queued = {p.stem for p in PENDING.glob("*.json")} if PENDING.exists() else set()
    r = _gh("release", "list", "--limit", "200", "--json", "tagName", check=False)
    if r.returncode != 0:
        print(f"[release] could not list releases: {r.stderr.strip()[:200]}", file=sys.stderr)
        return
    for rel in json.loads(r.stdout or "[]"):
        tag = rel.get("tagName", "")
        if tag.startswith("edit-") and tag[len("edit-"):] not in queued:
            _gh("release", "delete", tag, "--yes", "--cleanup-tag", check=False)
            print(f"[release] removed {tag} (no longer waiting to be posted)")


def main() -> int:
    if REL.exists():
        r = json.loads(REL.read_text(encoding="utf-8"))
        video, notes = ROOT / r["video"], ROOT / r["notes"]
        with tempfile.TemporaryDirectory() as td:
            asset = Path(td) / "edit.mp4"
            shutil.copyfile(video, asset)
            _gh("release", "create", r["tag"], str(asset), "--title", r["name"],
                "--notes-file", str(notes), "--latest")
        REL.unlink()
        print(f"[release] {r['tag']} published: {r['name']}")
    else:
        print("[release] no new video queued this run")
    sync()
    prune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
