"""
The design lab: one Short rendered in each look, for the owner to compare and pick.

Owner, in the HQ, 2026-11-10: "Deploy agents to design higher quality
videos". The crew builds every change behind a switch that is OFF on the live
channel (Callimachus: the type, REEL_TYPE; Zeuxis: the picture, REEL_PICTURE;
REEL_EDIT_LOOK turns a whole look on), Plutarch writes what each shot shows
(data/edit_quotes.json `scenes`). The lab (.github/workflows/design-lab.yml)
renders a chosen quote in every look with the real pipeline and the real keys,
DRY_RUN (nothing uploaded, nothing logged), and puts the videos in the
`design-lab` release, outside git. Nothing here can change a live post.

    python scripts/design_lab.py matrix                       # design-lab.yml: the jobs ($LOOKS x $EDITS)
    python scripts/design_lab.py env <look>                   # KEY=VALUE lines for $GITHUB_ENV
    python scripts/design_lab.py publish data/preview <edit> <look>   # after a render (GH_TOKEN)
    python scripts/design_lab.py fetch <dir> <edit> <look>... # download from the release (public URLs)
    python scripts/design_lab.py sampler OUT.mp4 A.mp4 "Label A" B.mp4 "Label B" ...
    python scripts/design_lab.py sheet VIDEO OUT.png          # frames through the iPhone crop

Every look and every edit id is checked before anything renders, so a typo
fails in seconds instead of after a 10-minute render. Tests: tests/test_design_lab.py.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "soicism2026-ex/stoic-bot"
TAG = "design-lab"
PUBLIC = f"https://github.com/{REPO}/releases/download/{TAG}/"
BANK = ROOT / "data" / "edit_quotes.json"

# Each look is the environment the render runs with, on top of the edit
# format's own style pack. "current" is exactly the live channel.
LOOKS: dict[str, dict[str, str]] = {
    # The live channel airs the painted look since 2026-11-11 (owner's pick).
    "current": {"REEL_EDIT_LOOK": "painted"},
    "old": {"REEL_EDIT_LOOK": ""},                     # black-and-white stock, before 2026-11-11
    "painted": {"REEL_EDIT_LOOK": "painted"},          # the crew's whole new look
    "type": {"REEL_EDIT_TYPE": "v2"},                   # the new type (and its gold words) on today's picture
    "picture": {"REEL_PICTURE": "painted"},             # the new picture, today's type
}
LABELS = {"current": "Today's look", "old": "The old look", "painted": "The new look",
          "type": "New type only", "picture": "New picture only"}
MAX_JOBS = 8
NAME = re.compile(r"^[a-z0-9_]+$")
# Moments the sheet samples: the first frame (the swipe decision), the hook
# being read, the quote mid-read, and the very end.
SHEET_AT = (0.0, 0.8, 4.0, -0.15)


def _ids() -> list[str]:
    return [q["id"] for q in json.loads(BANK.read_text(encoding="utf-8"))]


def _split(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def next_edit() -> str:
    """The quote the live channel airs next (the shelf's own pick)."""
    import csv
    sys.path.insert(0, str(ROOT / "src"))
    import edits  # noqa: PLC0415
    rows = list(csv.DictReader(open(ROOT / "data" / "posts.csv", encoding="utf-8")))
    q = edits.pick(rows)
    if not q:
        raise SystemExit("the shelf is empty: name a quote id in `edits`")
    return q["id"]


def matrix(looks_raw: str, edits_raw: str, ids: list[str] | None = None) -> dict:
    """{"include": [{"look", "edit"}...]} for a GitHub Actions matrix."""
    looks = _split(looks_raw) or ["current", "painted"]
    unknown = [x for x in looks if x not in LOOKS]
    if unknown:
        raise SystemExit(f"unknown look(s): {', '.join(unknown)} (known: {', '.join(LOOKS)})")
    chosen = _split(edits_raw)
    if not chosen:
        chosen = [next_edit()]
    ids = ids if ids is not None else _ids()
    missing = [x for x in chosen if x not in ids]
    if missing:
        raise SystemExit(f"no quote with id {', '.join(missing)} in data/edit_quotes.json")
    jobs = [{"look": lk, "edit": e} for e in dict.fromkeys(chosen) for lk in dict.fromkeys(looks)]
    if len(jobs) > MAX_JOBS:
        raise SystemExit(f"{len(jobs)} renders asked; the lab runs at most {MAX_JOBS} at a time")
    return {"include": jobs}


def env_lines(look: str) -> list[str]:
    if look not in LOOKS:
        raise SystemExit(f"unknown look {look!r} (known: {', '.join(LOOKS)})")
    return [f"{k}={v}" for k, v in LOOKS[look].items()] + [f"REEL_LAB_LOOK={look}"]


def asset_name(edit: str, look: str, ext: str) -> str:
    if not (NAME.match(edit) and NAME.match(look)):
        raise ValueError(f"bad name: {edit!r} / {look!r}")
    return f"{edit}__{look}.{ext}"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def duration(video: Path) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def master_cut(src: Path, dst: Path) -> Path:
    """Full 1080x1920 for judging the look on a phone, index up front so it
    starts at once (the rehearsal's 720 px cut is too soft to judge type).
    Capped at ~5 Mb/s: the first lab run's CRF 20 made 18 MB for 11 s, too
    slow to start on a phone; YouTube itself serves Shorts well under that."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "5M", "-bufsize", "10M",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst)], check=True)
    return dst


def sheet(video: Path, out: Path) -> Path:
    """Four moments side by side, each through the iPhone crop (840 of 1080
    px wide), labelled with its time."""
    d = duration(video)
    tmp = out.parent / f"_{out.stem}_tiles"
    tmp.mkdir(parents=True, exist_ok=True)
    tiles = []
    for i, at in enumerate(SHEET_AT):
        t = max(0.0, d + at) if at < 0 else min(at, max(0.0, d - 0.05))
        f = tmp / f"{i}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-vframes", "1",
                        "-vf", "crop=840:1920:120:0,scale=420:-2", str(f)], check=True)
        tiles.append(f)
    inputs = [x for f in tiles for x in ("-i", str(f))]
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
                    "".join(f"[{i}]" for i in range(len(tiles))) + f"hstack=inputs={len(tiles)}",
                    str(out)], check=True)
    for f in tiles:
        f.unlink(missing_ok=True)
    tmp.rmdir()
    return out


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", os.environ.get("GITHUB_REPOSITORY", REPO)],
                          capture_output=True, text=True, check=check)


def describe(preview: Path, edit: str, look: str) -> dict:
    meta = json.loads((preview / "meta.json").read_text(encoding="utf-8"))
    if meta.get("edit") != edit:
        # REEL_EDIT_ID is honoured only in DRY_RUN; anything else is a lab bug.
        raise SystemExit(f"rendered {meta.get('edit')!r}, asked for {edit!r}")
    meta.update({"look": look, "env": dict(LOOKS[look]),
                 "renderedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "run": os.environ.get("RUN_URL", "")})
    return meta


def publish(preview: Path, edit: str, look: str) -> dict:
    meta = describe(preview, edit, look)
    src = preview / meta["video"]
    if not src.exists():
        raise SystemExit(f"no render at {src}")
    out = preview / "lab"
    out.mkdir(exist_ok=True)
    vid, js, png = (out / asset_name(edit, look, x) for x in ("mp4", "json", "png"))
    master_cut(src, vid)
    sheet(vid, png)
    meta["seconds"] = round(duration(vid), 2)
    meta["bytes"] = vid.stat().st_size
    js.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if _gh("release", "view", TAG, check=False).returncode != 0:
        _gh("release", "create", TAG, "--prerelease", "--title", "Design lab",
            "--notes", "The same Short rendered in each look the crew is building, for the owner "
                       "to compare in the HQ. Never posted. Files are replaced by name on each run. "
                       "Auto-managed by design-lab.yml: do not delete.")
    _gh("release", "upload", TAG, str(vid), str(js), str(png), "--clobber")
    print(f"design lab: {edit} in the {look} look ({meta['seconds']} s, {meta['bytes'] // 1024} KB) "
          f"-> {PUBLIC}{vid.name}")
    return meta


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "stoic-bot-lab"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dst.write_bytes(r.read())


def fetch(dest: Path, edit: str, looks: list[str]) -> list[dict]:
    dest.mkdir(parents=True, exist_ok=True)
    got = []
    for look in looks:
        item = {"edit": edit, "look": look}
        try:
            for ext in ("json", "mp4", "png"):
                _download(PUBLIC + asset_name(edit, look, ext), dest / asset_name(edit, look, ext))
            item.update(json.loads((dest / asset_name(edit, look, "json")).read_text(encoding="utf-8")))
            item["file"] = str(dest / asset_name(edit, look, "mp4"))
            item["ok"] = (dest / asset_name(edit, look, "mp4")).stat().st_size > 10_000
        except Exception as e:  # noqa: BLE001
            item.update({"ok": False, "error": f"{type(e).__name__}: {e}"[:200]})
        got.append(item)
    return got


def _card(text: str, out: Path, seconds: float = 1.4) -> Path:
    """A numbered title card, black, big white type (the music sampler's style)."""
    safe = text.replace("\\", "").replace("'", "’").replace(":", "\\:")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:d={seconds}:r=30",
                    "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={seconds}",
                    "-vf", "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                           f"text='{safe}':fontcolor=white:fontsize=84:x=(w-text_w)/2:y=(h-text_h)/2",
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)], check=True)
    return out


def sampler(out: Path, pairs: list[tuple[Path, str]]) -> Path:
    """One video for the phone: "1 · Label" card, the first look, "2 · Label",
    the second look, and so on, each at 1080x1920 with stereo 44.1 kHz sound."""
    tmp = out.parent / f"_{out.stem}_parts"
    tmp.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, (video, label) in enumerate(pairs, 1):
        parts.append(_card(f"{i} · {label}", tmp / f"card{i}.mp4"))
        norm = tmp / f"part{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video),
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                        "-c:a", "aac", "-ar", "44100", "-ac", "2", str(norm)], check=True)
        parts.append(norm)
    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "matrix":
        m = matrix(os.environ.get("LOOKS", ""), os.environ.get("EDITS", ""))
        print("matrix=" + json.dumps(m, separators=(",", ":")))
        return 0
    if cmd == "env" and len(args) == 1:
        print("\n".join(env_lines(args[0])))
        return 0
    if cmd == "publish" and len(args) == 3:
        publish(Path(args[0]), args[1], args[2])
        return 0
    if cmd == "fetch" and len(args) >= 3:
        got = fetch(Path(args[0]), args[1], args[2:])
        print(json.dumps(got, ensure_ascii=False))
        return 0 if all(g.get("ok") for g in got) else 1
    if cmd == "sampler" and len(args) >= 3 and len(args) % 2 == 1:
        pairs = [(Path(args[i]), args[i + 1]) for i in range(1, len(args), 2)]
        sampler(Path(args[0]), pairs)
        return 0
    if cmd == "sheet" and len(args) == 2:
        sheet(Path(args[0]), Path(args[1]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
