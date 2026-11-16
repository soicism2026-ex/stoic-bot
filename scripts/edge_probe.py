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


VARIANTS = {
    "graded (no enhance)": "[g]null[e]",
    "glow blend only": "[g]split[pb][pg];[pg]gblur=sigma=18,eq=brightness=0.02[pgb];[pb][pgb]blend=c1_expr=A:c2_expr=A:c0_mode=screen:c0_opacity=0.160[e]",
    "glow+noise": "[g]split[pb][pg];[pg]gblur=sigma=18,eq=brightness=0.02[pgb];[pb][pgb]blend=c1_expr=A:c2_expr=A:c0_mode=screen:c0_opacity=0.160,noise=alls=3:allf=t[e]",
    "full enhance": None,
    "gblur only": "[g]gblur=sigma=18[e]",
    "eq only": "[g]eq=brightness=0.02[e]",
    "blend with plain copy": "[g]split[a][b];[a][b]blend=c1_expr=A:c2_expr=A:c0_mode=screen:c0_opacity=0.16[e]",
    "noise only": "[g]noise=alls=3:allf=t[e]",
    "vignette only": "[g]vignette=angle=0.300[e]",
    "full + fillborders smear": "FULL,fillborders=right=16:mode=smear",
    "full, yuv420p into blend": "[g]split[pb][pg];[pg]gblur=sigma=18,eq=brightness=0.02,format=yuv420p[pgb];[pb]format=yuv420p[pb2];[pb2][pgb]blend=c1_expr=A:c2_expr=A:c0_mode=screen:c0_opacity=0.160,noise=alls=3:allf=t,vignette=angle=0.300[e]",
    "full, gbrp into blend": "[g]split[pb][pg];[pg]gblur=sigma=18,eq=brightness=0.02,format=gbrp[pgb];[pb]format=gbrp[pb2];[pb2][pgb]blend=all_mode=screen:all_opacity=0.160,noise=alls=3:allf=t,vignette=angle=0.300[e]",
}


def widthmap(raw: bytes, y: int) -> str:
    """The last 24 columns: X where a pixel is far from the picture just inside."""
    row = y * 1080 * 3
    px = lambda x: raw[row + x * 3: row + x * 3 + 3]  # noqa: E731
    ref = [sum(px(x)[c] for x in range(1036, 1052)) / 16 for c in range(3)]
    return "".join("X" if sum(abs(px(x)[c] - ref[c]) for c in range(3)) > 70 else "." for x in range(1056, 1080))


def bisect(clip: Path) -> None:
    geo = f"[0:v]{GEO},trim=0:end=3,setpts=PTS-STARTPTS,{painter.motion_filter(1, 90)},{','.join(painter.grade_parts(0.0, 0.0))}[g]"
    full = painter.enhance_graph("g", "e")
    for name, v in VARIANTS.items():
        if v is None:
            v = full
        elif v.startswith("FULL,"):
            v = full.replace("[e]", "[e0]") + f";[e0]{v[5:]}[e]"
        raw = frame(["ffmpeg", "-v", "error", "-i", str(clip), "-filter_complex", geo + ";" + v, "-map", "[e]",
                     "-ss", "1.5", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        if len(raw) < 1080 * 1920 * 3:
            print(f"  {name:26s} no frame"); continue
        row = 960 * 1080 * 3
        e = tuple(raw[row + 1079 * 3: row + 1079 * 3 + 3])
        print(f"  {name:26s} y300 {widthmap(raw, 300)}  y960 {widthmap(raw, 960)}  x1079={e}")


def main() -> int:
    print(subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0])
    tmp = Path(tempfile.mkdtemp())
    still = tmp / "synthetic.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "nullsrc=s=1024x1920,format=rgb24,geq=r='150+80*sin(X/37)*cos(Y/53)':g='110+60*sin(X/61+1)':b='70+50*cos(Y/41+X/71)'",
                    "-frames:v", "1", str(still)], check=True)
    stills = [still]
    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "still_cache"
    if cache.exists():
        stills += sorted([p for p in cache.rglob("*.jpg")], key=lambda p: -p.stat().st_mtime)[:1]
    for s in stills:
        clip = tmp / (s.stem + ".mp4")
        if painter.prepare_still(s, clip, seconds=3.0):
            print(f"\n== {s.name}: the last 24 columns (X = not the picture)")
            bisect(clip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
