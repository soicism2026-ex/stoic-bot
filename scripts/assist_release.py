"""
Publish the video daily_post just queued as a GitHub release (assisted posting).

Runs in daily-short.yml right after daily_post, only when data/assist/
release.json exists. The asset is always named edit.mp4, so
    https://github.com/<repo>/releases/latest/download/edit.mp4
is always the newest video to post, and the release notes say which song to
add and which title to paste. adopt_uploads.py deletes a release once the
owner has posted it, so the Releases page is exactly the "to post" list.
Releases older than KEEP_DAYS are pruned as a backstop.
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


def main() -> int:
    if not REL.exists():
        print("[release] no new video queued this run")
        return 0
    r = json.loads(REL.read_text(encoding="utf-8"))
    video, notes = ROOT / r["video"], ROOT / r["notes"]
    with tempfile.TemporaryDirectory() as td:
        asset = Path(td) / "edit.mp4"
        shutil.copyfile(video, asset)
        _gh("release", "create", r["tag"], str(asset), "--title", r["name"],
            "--notes-file", str(notes), "--latest")
    REL.unlink()
    print(f"[release] {r['tag']} published: {r['name']}")
    prune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
