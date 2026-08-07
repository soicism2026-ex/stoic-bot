#!/usr/bin/env python3
"""
Fetch one background per clip slot exactly the way a real render does, report
which PROVIDER served each, and save a frame from each so the look can be
judged instead of described.

Cheaper and far more direct than rendering a whole short: it exercises the same
backgrounds.fetch_background() chain the pipeline uses, so the SOURCE= lines it
prints are the real answer to "did Cloudflare actually serve these, or did it
quietly fall back to stock?"

Runs in CI (the sandbox cannot reach cloudflare.com) via
.github/workflows/preview-backgrounds.yml, which commits the JPEGs so they
can be opened on a phone.

    python scripts/preview_backgrounds.py
    python scripts/preview_backgrounds.py --theme resilience
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "samples" / "frames"

# The same 6-slot assembly daily_post builds: guide bookends around four
# scene-matched b-roll beats. Slots 0 and 5 must come back as the SAME statue.
GUIDE_Q = "marble bust ancient philosopher dramatic chiaroscuro slow"
BEATS = [
    "a man sitting alone on the edge of a bed at night, head lowered",
    "a storm breaking over an empty ancient colonnade",
    "close on weathered hands gripping a stone ledge",
    "first light over a still mountain lake",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--theme", default="discipline")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")

    flavors = [GUIDE_Q] + BEATS + [GUIDE_Q]
    os.environ["REEL_BG_CLIPS"] = str(len(flavors))
    os.environ["REEL_GUIDE_SLOTS"] = f"0,{len(flavors) - 1}"
    for i, q in enumerate(flavors):
        os.environ[f"REEL_BG_FLAVOR{i if i else ''}"] = q

    import backgrounds
    import imagegen

    print("=== Background preview ===")
    print(f"REEL_IMAGE_BG={os.environ.get('REEL_IMAGE_BG', '0')}  "
          f"cloudflare_ready={imagegen.cloudflare_ready()}  "
          f"generation_enabled={imagegen.enabled()}")
    print(f"guide slots={sorted(backgrounds._guide_slots())} "
          f"seed={backgrounds.GUIDE_SEED}\n")

    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("bg_*.png")) + list(OUT.glob("bg_*.jpg")):
        old.unlink()

    work = ROOT / "data"
    work.mkdir(exist_ok=True)
    made = 0
    for i, q in enumerate(flavors):
        clip = work / f"_preview_bg{i}.mp4"
        try:
            got = backgrounds.fetch_background(args.theme, clip, clip_idx=i)
        except Exception as e:  # noqa: BLE001
            print(f"  slot {i}: FAILED {str(e)[:120]}")
            continue
        # JPEG, not PNG. These are COMMITTED on every preview run, and a set of
        # six 1080x1920 PNGs is ~11 MB — that lands in history permanently and
        # is paid for on every clone and CI checkout. JPEG q3 is visually
        # indistinguishable for judging a look and roughly a tenth the size.
        png = OUT / f"bg_{i}_{'guide' if i in (0, len(flavors) - 1) else 'beat'}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0",
                 "-i", str(got), "-frames:v", "1",
                 "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                        "crop=1080:1920", "-q:v", "3", str(png)],
                check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"  slot {i}: frame grab failed {e.stderr.decode()[:100]}")
            continue
        made += 1
        print(f"  slot {i}: {png.name}  ({png.stat().st_size/1000:.0f} kB)  q='{q[:44]}'")

    for tmp in work.glob("_preview_bg*"):
        tmp.unlink(missing_ok=True)

    print(f"\n{made}/{len(flavors)} frames written to {OUT}")
    print("Read the SOURCE= lines above: GENERATED means Cloudflare/OpenAI "
          "served it, PIXABAY/PEXELS means generation was skipped or failed.")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
