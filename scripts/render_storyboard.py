"""Render a storyboard's shots and a silent rough cut.

    python scripts/render_storyboard.py before_breakfast out/

Every shot is a real billable generation. Shots that fail are replaced by a
labelled black slate, so the rough cut always shows exactly what was missing
instead of silently closing the gap.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import hfgen  # noqa: E402
import proc   # noqa: E402


def slate(out: Path, seconds: float, label: str) -> Path:
    proc.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
              "-i", f"color=c=black:s=1080x1920:d={seconds}:r=30",
              "-vf", f"drawtext=text='{label}':fontcolor=red:fontsize=60:"
                     "x=(w-text_w)/2:y=(h-text_h)/2",
              "-pix_fmt", "yuv420p", str(out)], check=True, capture_output=True)
    return out


def main() -> int:
    sid, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    board = json.loads((ROOT / "data" / "storyboards.json").read_text())[sid]
    clips, report = [], []
    for i, spec in enumerate(board["shots"], 1):
        path = out_dir / f"shot{i:02d}_{spec['model']}.mp4"
        got = hfgen.shot(spec, board.get("cast", {}), path)
        ok = got is not None
        report.append(f"shot {i:2d} {spec['model']:5s} {spec['seconds']:>4}s  "
                      f"{'OK' if ok else 'FAILED'}  {spec['picture'][:60]}")
        print(report[-1], flush=True)
        clips.append(got if ok else slate(path, spec["seconds"], f"SHOT {i} FAILED"))
    lst = out_dir / "list.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips))
    proc.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", str(lst), "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "20", "-pix_fmt", "yuv420p", str(out_dir / f"{sid}_roughcut.mp4")],
             check=True, capture_output=True)
    (out_dir / "report.txt").write_text("\n".join(report) + "\n")
    failed = sum("FAILED" in r for r in report)
    print(f"rough cut: {out_dir / (sid + '_roughcut.mp4')}  ({failed} failed)")
    return 1 if failed == len(report) else 0


if __name__ == "__main__":
    sys.exit(main())
