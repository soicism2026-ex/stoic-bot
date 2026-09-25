"""Contact sheet for AI-video review: every shot at four moments.

    python scripts/review_shots.py data/2026-09-25_sb out/review.png

AI video glitches (extra fingers, fused objects, a face that melts, a ghost
blob) usually appear MID-MOTION, so one frame per clip misses them. This
samples each clip at 20/40/60/80% and lays them out one row per shot. It is
what caught the fused candle-and-stick and the ghost on the bedroom wall.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import proc  # noqa: E402


def duration(p: Path) -> float:
    r = proc.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    clips = sorted(p for p in src.glob("*.mp4") if ".raw." not in p.name)
    if not clips:
        print("no clips"); return 1
    tmp = out.parent / "_review_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, c in enumerate(clips, 1):
        d = duration(c)
        tiles = []
        for k in (1, 2, 3, 4):
            t = round(d * k / 5, 2)
            f = tmp / f"{n}_{k}.png"
            proc.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(c),
                      "-vframes", "1", "-vf",
                      f"scale=200:-2,drawtext=text='{n}@{t}':fontcolor=yellow:"
                      "fontsize=18:x=4:y=4:box=1:boxcolor=black@0.6", str(f)],
                     check=True, capture_output=True)
            tiles.append(f)
        row = tmp / f"row_{n}.png"
        proc.run(["ffmpeg", "-y", "-v", "error", *sum([["-i", str(t)] for t in tiles], []),
                  "-filter_complex", "hstack=4", str(row)], check=True, capture_output=True)
        rows.append(row)
    if len(rows) == 1:
        rows[0].rename(out)
    else:
        proc.run(["ffmpeg", "-y", "-v", "error", *sum([["-i", str(r)] for r in rows], []),
                  "-filter_complex", f"vstack={len(rows)}", str(out)],
                 check=True, capture_output=True)
    print(f"review sheet: {out} ({len(clips)} shots x 4 moments)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
