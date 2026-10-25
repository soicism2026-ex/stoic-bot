"""
Apelles' rehearsal goes to the HQ: the next Short, rendered before it airs.

    python scripts/up_next.py need                     # edit-preview: is the next Short rehearsed?
    python scripts/up_next.py publish data/preview     # edit-preview, after the render
    python scripts/up_next.py fetch /tmp/upnext        # the HQ sync, in a Claude session

`need` (2026-10-25) lets edit-preview run right after every Producer run
instead of only on its two crons, which GitHub fired 2-5 hours late (the
19:40 rehearsal of 10-24 started at 21:50, three hours before its post). It
prints `go` or `skip: <why>`: skip when the release already holds the next
edit for its air day, or when two rehearsals failed today (a broken render
must not burn a Brian read on every retry; Apelles already shows as failed).

`publish` (GitHub Actions, GH_TOKEN) puts two files in the `up-next` release,
a prerelease that only ever holds these two:
  up-next.mp4    the rehearsal, re-encoded for a phone (720 px wide, ~2-3 MB)
  up-next.json   what it is: the edit id, quote, hook, author, citation, the
                 day it airs, the voice that spoke, when, and the run
Release assets live outside git, so no video enters the repo's history (the
"never commit video files" rule).

`fetch` downloads both from the release's public URLs (no token: the HQ sync
session has no GitHub API access) and prints one JSON line: the metadata with
"ok": true and "file": the local video, or {"ok": false, "error": ...}. The
sync then uploads the video to the HQ's asset store and writes `hq/upnext`
(CLAUDE.md "HQ app").
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "soicism2026-ex/stoic-bot"
TAG = "up-next"
VIDEO, META = "up-next.mp4", "up-next.json"
PUBLIC = f"https://github.com/{REPO}/releases/download/{TAG}/"


def phone_cut(src: Path, dst: Path) -> Path:
    """720 px wide H.264 + AAC with the index up front, so it starts at once on
    a phone. The 1080x1920 master is ~15 MB; this is ~2-3 MB."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "scale=720:-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst)],
                   check=True)
    return dst


def describe(preview: Path, now: dt.datetime | None = None) -> dict:
    meta = json.loads((preview / "meta.json").read_text(encoding="utf-8"))
    meta["renderedAt"] = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta["run"] = os.environ.get("RUN_URL", "")
    return meta


def need(next_edit: str | None, air_day: str, current: dict | None,
         failures_today: int) -> tuple[bool, str]:
    """Should a scheduled or post-triggered rehearsal render now?"""
    if not next_edit:
        return False, "skip: no edit left to rehearse (the shelf is empty)"
    if current and current.get("edit") == next_edit and current.get("airDay") == air_day:
        return False, f"skip: {next_edit} for {air_day} is already rehearsed ({current.get('renderedAt')})"
    if failures_today >= 2:
        return False, f"skip: {failures_today} rehearsals failed today; waiting for a fix"
    return True, f"go: rehearse {next_edit} for {air_day}"


def _failures_today(now: dt.datetime) -> int:
    """Failed edit-preview runs today (UTC), from the Actions API; 0 if unknown."""
    try:
        out = _gh("api", "-X", "GET", f"repos/{os.environ.get('GITHUB_REPOSITORY', REPO)}/actions/workflows/"
                  f"edit-preview.yml/runs", "-f", f"created=>={now.date().isoformat()}",
                  "-f", "status=failure", "--jq", ".total_count", check=False, repo=False)
        return int((out.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0


def _need_cli() -> int:
    import csv
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "src"))
    import airday  # noqa: PLC0415
    import edits  # noqa: PLC0415
    rows = list(csv.DictReader(open(root / "data" / "posts.csv", encoding="utf-8")))
    q = edits.pick(rows)
    day = airday.next_air_day(rows, airday.live_cap()).isoformat()
    current = None
    try:
        with urllib.request.urlopen(urllib.request.Request(
                PUBLIC + META, headers={"User-Agent": "stoic-bot-hq"}), timeout=30) as r:
            current = json.loads(r.read())
    except Exception:  # noqa: BLE001
        pass   # no release yet, or GitHub didn't answer: rehearse
    go, why = need(q and q["id"], day, current, _failures_today(dt.datetime.now(dt.timezone.utc)))
    print(why)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"go={'1' if go else '0'}\n")
    return 0


def _gh(*args: str, check: bool = True, repo: bool = True) -> subprocess.CompletedProcess:
    extra = ["--repo", os.environ.get("GITHUB_REPOSITORY", REPO)] if repo else []
    return subprocess.run(["gh", *args, *extra], capture_output=True, text=True, check=check)


def publish(preview: Path) -> dict:
    meta = describe(preview)
    src = preview / meta["video"]
    if not src.exists():
        raise SystemExit(f"no rehearsal video at {src}")
    out = preview / "up-next"
    out.mkdir(exist_ok=True)
    phone_cut(src, out / VIDEO)
    meta["bytes"] = (out / VIDEO).stat().st_size
    (out / META).write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if _gh("release", "view", TAG, check=False).returncode != 0:
        _gh("release", "create", TAG, "--prerelease", "--title", "Up next (HQ)",
            "--notes", "The next Short, rehearsed by edit-preview before it airs, for the "
                       "owner's HQ app. Never posted. Replaced twice a day; holds only "
                       f"{VIDEO} and {META}. Auto-managed: do not delete.")
    _gh("release", "upload", TAG, str(out / VIDEO), str(out / META), "--clobber")
    print(f"up next: {meta.get('edit')} for {meta.get('airDay')} "
          f"({meta['bytes'] // 1024} KB) -> {PUBLIC}{VIDEO}")
    return meta


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "stoic-bot-hq"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dst.write_bytes(r.read())


def fetch(dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        _download(PUBLIC + META, dest / META)
        meta = json.loads((dest / META).read_text(encoding="utf-8"))
        _download(PUBLIC + VIDEO, dest / VIDEO)
        if (dest / VIDEO).stat().st_size < 10_000:
            raise ValueError("the video is too small to be a render")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    return {**meta, "ok": True, "file": str(dest / VIDEO)}


def main() -> int:
    if sys.argv[1:] == ["need"]:
        return _need_cli()
    if len(sys.argv) != 3 or sys.argv[1] not in ("publish", "fetch"):
        print(__doc__)
        return 2
    if sys.argv[1] == "publish":
        publish(Path(sys.argv[2]))
        return 0
    got = fetch(Path(sys.argv[2]))
    print(json.dumps(got, ensure_ascii=False))
    return 0 if got["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
