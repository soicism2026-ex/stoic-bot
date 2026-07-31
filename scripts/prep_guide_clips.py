#!/usr/bin/env python3
"""
Normalise a folder of hand-generated GUIDE clips into a committable library.

The recurring marble-statue guide opens AND closes every short. Stock search
gives us a *different* bust every day, which is not a character — it's noise.
This script takes whatever you generated (Higgsfield, Runway, Kling, Sora, a
stock download, a phone video of a museum) and turns it into a uniform,
repo-safe library at assets/guide/.

What it does to every input clip:
  * scales + centre-crops to exactly 1080x1920 (vertical, the render's canvas)
  * trims to --seconds (default 4s — the guide is a bookend, not a scene)
  * strips audio (the render supplies its own bed; audio is dead weight in git)
  * re-encodes H.264 yuv420p at --crf so 30 clips fit in tens of MB, not GB
  * names them guide_01.mp4 ... guide_NN.mp4 so the rotation is deterministic

It then prints the total library size and warns if the repo is about to gain
more weight than it should.

Usage:
    python scripts/prep_guide_clips.py ~/Downloads/higgsfield_guide
    python scripts/prep_guide_clips.py ~/clips --seconds 5 --crf 26
    python scripts/prep_guide_clips.py ~/clips --append     # keep existing lib

Prompts for generating the source clips: docs/guide_clip_prompts.md
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE_DIR = ROOT / "assets" / "guide"

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

# Soft budget. Guide clips are committed (unlike stock backgrounds, which are
# gitignored and re-downloaded daily), so every MB is paid for on every CI
# checkout, 3x a day, forever.
SIZE_WARN_MB = 80.0


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("ffmpeg not found on PATH — install it first (apt install ffmpeg).")
    return exe


def _duration(path: Path) -> float:
    """Seconds, or 0.0 if ffprobe can't tell us."""
    probe = shutil.which("ffprobe")
    if not probe:
        return 0.0
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


def normalise(src: Path, dst: Path, seconds: float, crf: int) -> None:
    """Scale/crop to 1080x1920, trim, mute, re-encode."""
    vf = (
        # cover the 1080x1920 frame (never letterbox), then centre-crop the
        # overflow — the guide's face stays in the middle of the frame.
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "fps=30,"
        "format=yuv420p"
    )
    cmd = [
        _ffmpeg(), "-y", "-loglevel", "error",
        "-i", str(src),
        "-t", f"{seconds:.2f}",
        "-an",                      # no audio
        "-vf", vf,
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if not dst.exists() or dst.stat().st_size < 1_000:
        raise RuntimeError(f"encode produced nothing usable for {src.name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="folder containing the generated guide clips")
    ap.add_argument("--seconds", type=float, default=4.0,
                    help="trim length per clip (default 4.0)")
    ap.add_argument("--crf", type=int, default=25,
                    help="H.264 quality, lower=better/bigger (default 25)")
    ap.add_argument("--append", action="store_true",
                    help="add to the existing library instead of replacing it")
    args = ap.parse_args()

    src_dir = Path(args.source).expanduser()
    if not src_dir.is_dir():
        sys.exit(f"Not a folder: {src_dir}")

    sources = sorted(p for p in src_dir.iterdir()
                     if p.suffix.lower() in VIDEO_SUFFIXES and p.is_file())
    if not sources:
        sys.exit(f"No video files in {src_dir} "
                 f"(looked for {', '.join(sorted(VIDEO_SUFFIXES))})")

    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(GUIDE_DIR.glob("guide_*.mp4"))
    if args.append:
        start = len(existing) + 1
    else:
        for old in existing:
            old.unlink()
        start = 1

    print(f"Normalising {len(sources)} clip(s) -> {GUIDE_DIR.relative_to(ROOT)}/")
    ok, failed = 0, []
    for i, src in enumerate(sources, start=start):
        dst = GUIDE_DIR / f"guide_{i:02d}.mp4"
        dur = _duration(src)
        try:
            normalise(src, dst, args.seconds, args.crf)
        except Exception as e:  # noqa: BLE001
            failed.append((src.name, str(e)[:120]))
            print(f"  [FAIL] {src.name}: {str(e)[:120]}")
            continue
        ok += 1
        mb = dst.stat().st_size / 1e6
        short = " (SHORTER THAN TRIM — will freeze on the tail)" if 0 < dur < args.seconds - 0.05 else ""
        print(f"  [ok] {src.name} -> {dst.name}  {mb:.1f} MB{short}")

    lib = sorted(GUIDE_DIR.glob("guide_*.mp4"))
    total_mb = sum(p.stat().st_size for p in lib) / 1e6
    print(f"\nLibrary: {len(lib)} clips, {total_mb:.1f} MB total")
    if failed:
        print(f"{len(failed)} clip(s) failed — they were skipped, the rest are fine.")
    if total_mb > SIZE_WARN_MB:
        print(f"WARNING: over the {SIZE_WARN_MB:.0f} MB soft budget. These are "
              f"COMMITTED files — re-run with a higher --crf (e.g. 28) or a "
              f"shorter --seconds to shrink them.")
    if len(lib) < 8:
        print("NOTE: with fewer than ~8 clips the same guide shot returns every "
              "few days. 20-30 is the target.")
    if lib:
        print("\nNext:")
        print("  git add -f assets/guide/*.mp4")
        print("  git commit -m 'guide: curated statue library'")
        print("  # the pipeline picks them up automatically — no flag to set.")
    return 1 if failed and ok == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
