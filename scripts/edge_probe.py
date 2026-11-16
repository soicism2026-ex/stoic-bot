"""Edge probe (2026-11-16): where does the red strip at the right edge of the
painted Shorts come from? Runs each stage of the painted picture chain on
synthetic and real cached stills and prints the right-edge pixels against
the picture just inside them. Diagnostic only: prints, writes nothing kept.

    python3 scripts/edge_probe.py [still_cache_dir]
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import painter  # noqa: E402

GEO = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p"


def frame(cmd: list[str]) -> bytes:
    return subprocess.run(cmd, capture_output=True).stdout


def edge(raw: bytes, y: int = 960) -> str:
    if len(raw) < 1080 * 1920 * 3:
        return "no frame"
    row = y * 1080 * 3
    px = lambda x: tuple(raw[row + x * 3: row + x * 3 + 3])  # noqa: E731
    e, i = px(1077), px(1050)
    strip = abs(e[0] - i[0]) + abs(e[1] - i[1]) + abs(e[2] - i[2]) > 90 and e[0] > 2 * max(e[1], 1)
    return f"{'STRIP' if strip else 'ok   '} edge{e} in{i}"


def run(clip: Path, stages: str, slot: int = 1) -> str:
    g = f"[0:v]{GEO},trim=0:end=3,setpts=PTS-STARTPTS"
    if "move" in stages:
        g += f",{painter.motion_filter(slot, 90)}"
    g += "[a]"
    last = "a"
    if "grade" in stages:
        g += f";[a]{','.join(painter.grade_parts(0.0, 0.0))}[b]"; last = "b"
    if "enh" in stages:
        g += ";" + painter.enhance_graph(last, "c"); last = "c"
    return edge(frame(["ffmpeg", "-v", "error", "-i", str(clip), "-filter_complex", g, "-map", f"[{last}]",
                       "-ss", "1.5", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]))


def main() -> int:
    print(subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0])
    flags = open("/proc/cpuinfo").read() if os.path.exists("/proc/cpuinfo") else ""
    print("cpu:", platform.processor() or "?", "| avx2" if " avx2" in flags else "", "| avx512" if "avx512f" in flags else "")
    tmp = Path(tempfile.mkdtemp())
    stills = []
    for ext in ("jpg", "png"):
        p = tmp / f"synthetic.{ext}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "nullsrc=s=1024x1920,format=rgb24,geq=r='150+80*sin(X/37)*cos(Y/53)':g='110+60*sin(X/61+1)':b='70+50*cos(Y/41+X/71)'",
                        "-frames:v", "1", str(p)], check=True)
        stills.append(p)
    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "still_cache"
    real = sorted([p for p in cache.rglob("*") if p.suffix in (".png", ".jpg", ".webp") and ".keep" not in p.name],
                  key=lambda p: -p.stat().st_mtime)[:3] if cache.exists() else []
    stills += real
    print(f"real cached stills: {len(real)}")
    for s in stills:
        size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,pix_fmt", "-of", "csv=p=0", str(s)],
                              capture_output=True, text=True).stdout.strip()
        clip = tmp / (s.stem + ".mp4")
        info = painter.prepare_still(s, clip, seconds=3.0)
        print(f"\n== {s.name} ({size}) k={info and round(info['k'], 3)} crop={info and info['crop']!r}")
        if not info:
            continue
        print("  still itself     ", edge(frame(["ffmpeg", "-v", "error", "-i", str(s), "-vf", "scale=1080:1920,format=rgb24",
                                                  "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])))
        print("  prepared clip    ", run(clip, ""))
        for slot in (0, 1, 2):
            print(f"  move {painter.MOVES[slot]:6s}      ", run(clip, "move", slot))
        print("  move+grade       ", run(clip, "move grade"))
        print("  move+grade+enh   ", run(clip, "move grade enh"))
        print("  grade+enh, still ", run(clip, "grade enh"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
