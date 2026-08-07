#!/usr/bin/env python3
"""
Pull representative frames out of a rendered short so a visual change can be
JUDGED rather than described.

The owner reviews on a phone, so this does two things a naive screenshot does
not: it samples frames across the whole clip (one per background cut, not just
frame 0), and it optionally shows the iPhone fullscreen crop, which trims the
sides and is where safe-zone mistakes actually bite.

    python scripts/preview_frames.py backups/2026-08-07_bk_reel.mp4
    python scripts/preview_frames.py video.mp4 --count 8 --crop
    python scripts/preview_frames.py video.mp4 --out samples/frames

Writes PNGs and prints their paths. Commit them if they need to travel.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "samples" / "frames"

# What an iPhone actually shows in the Shorts player: the sides are cropped
# away, so anything outside this band is invisible on the device most viewers
# use. 1080 wide source -> 840 wide visible, centred.
IPHONE_CROP = "crop=840:1920:120:0"


def _need(exe: str) -> str:
    path = shutil.which(exe)
    if not path:
        sys.exit(f"{exe} not found on PATH (apt install ffmpeg)")
    return path


def duration(video: Path) -> float:
    out = subprocess.run(
        [_need("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def grab(video: Path, at: float, dst: Path, crop: bool) -> None:
    vf = IPHONE_CROP if crop else "null"
    subprocess.run(
        [_need("ffmpeg"), "-y", "-loglevel", "error", "-ss", f"{at:.2f}",
         "-i", str(video), "-frames:v", "1", "-vf", vf, str(dst)],
        check=True, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--count", type=int, default=6,
                    help="frames to sample (default 6 — one per background cut)")
    ap.add_argument("--crop", action="store_true",
                    help="show the iPhone fullscreen crop instead of the full frame")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    video = Path(args.video).expanduser()
    if not video.is_file():
        sys.exit(f"No such video: {video}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{video.stem}_f*.png"):
        old.unlink()

    dur = duration(video)
    n = max(1, args.count)
    # Sample inside the clip, never at 0.0 or the very last frame: the first
    # frame is usually mid-fade and the last is often black, so both would
    # misrepresent the look.
    step = dur / (n + 1)
    made = []
    for i in range(1, n + 1):
        at = step * i
        dst = out_dir / f"{video.stem}_f{i:02d}{'_iphone' if args.crop else ''}.png"
        try:
            grab(video, at, dst, args.crop)
        except subprocess.CalledProcessError as e:
            print(f"  [FAIL] {at:.1f}s: {e.stderr.decode()[:120]}")
            continue
        made.append(dst)
        print(f"  [ok] {at:5.1f}s -> {dst}  ({dst.stat().st_size/1000:.0f} kB)")

    print(f"\n{len(made)} frame(s) from {dur:.1f}s of video in {out_dir}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
