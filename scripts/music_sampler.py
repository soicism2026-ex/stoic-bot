"""
One phone-friendly video to judge candidate edit music by ear.

Each track plays from where an edit would start (its drop) for 14 seconds,
behind a title card: its number, its label, and whose style it follows. The
owner replies with the numbers to keep; approving is setting "approved": true
on those tracks in data/edit_music.json.

    python scripts/music_sampler.py out.mp4                 # every unapproved track
    python scripts/music_sampler.py out.mp4 --ids a,b,c     # these, in this order
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "edit_music.json"
SECONDS = 14.0
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _txt(s: str) -> str:
    return s.replace("\\", "").replace(":", "\\:").replace("'", "’").replace("%", "")


def build(tracks: list[dict], out: Path) -> Path:
    with tempfile.TemporaryDirectory() as td:
        parts = []
        for n, t in enumerate(tracks, 1):
            p = Path(td) / f"part{n:02d}.mp4"
            vf = ",".join([
                f"drawtext=fontfile={FONT}:text='{n} / {len(tracks)}':fontcolor=white:"
                f"fontsize=110:x=(w-tw)/2:y=h*0.36",
                f"drawtext=fontfile={FONT}:text='{_txt(t.get('label', t['id']))}':"
                f"fontcolor=0xFFB830:fontsize=44:x=(w-tw)/2:y=h*0.50",
                f"drawtext=fontfile={FONT}:text='{_txt('in the style of ' + t.get('style_of', ''))}':"
                f"fontcolor=0xBBBBBB:fontsize=28:x=(w-tw)/2:y=h*0.57",
            ])
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error",
                 "-f", "lavfi", "-i", f"color=c=0x101010:s=720x1280:d={SECONDS}:r=24",
                 "-ss", str(t.get("start", 0)), "-t", str(SECONDS), "-i", str(ROOT / t["file"]),
                 "-vf", vf,
                 "-af", f"afade=t=in:d=0.2,afade=t=out:st={SECONDS - 0.8}:d=0.8,aresample=44100",
                 "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "30", "-c:a", "aac", "-b:a", "160k", "-shortest", str(p)],
                check=True)
            parts.append(p)
        lst = Path(td) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(out)], check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    bank = json.loads(BANK.read_text())
    if a.ids:
        by_id = {t["id"]: t for t in bank}
        tracks = [by_id[i] for i in a.ids.split(",") if i in by_id]
    else:
        tracks = [t for t in bank if not t.get("approved")]
    tracks = [t for t in tracks if (ROOT / t["file"]).exists()]
    if not tracks:
        print("no tracks to sample", file=sys.stderr)
        return 1
    build(tracks, a.out)
    for n, t in enumerate(tracks, 1):
        print(f"{n}: {t['id']}  ({t.get('label')}, like {t.get('style_of')})")
    print(f"sampler: {a.out} ({a.out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
