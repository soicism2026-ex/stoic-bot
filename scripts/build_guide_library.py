#!/usr/bin/env python3
"""
Build the recurring-GUIDE clip library for $0, with no human in the loop.

THE PROBLEM: the marble statue that opens and closes every short is fetched
from stock search at render time, so it is a DIFFERENT bust every day. A
character that changes daily is not a character.

THE CONSTRAINT: the owner will pay nothing for this, and will not hand-generate
clips. Every AI video tool that produces watermark-free output costs money.

THE WAY OUT: consistency does not require generation. Pick ONE good stock clip
of a bust — free, via the Pixabay/Pexels keys the bot already has — and derive
the whole library from it with ffmpeg. Same statue in every clip by
construction, while framing, camera motion, lighting temperature and fade
differ enough that no two shots read as a repeat. That is exactly what the
30-shot prompt set in docs/guide_clip_prompts.md was trying to buy, obtained
for nothing.

Run it manually or via .github/workflows/build-guide-library.yml, which commits
the result. src/backgrounds.py then serves assets/guide/ for the bookend slots
automatically — there is no flag to set.

    python scripts/build_guide_library.py                 # 24 clips
    python scripts/build_guide_library.py --count 30
    python scripts/build_guide_library.py --source my.mp4 # skip the download
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
GUIDE_DIR = ROOT / "assets" / "guide"

CLIP_SECONDS = 4.0
FPS = 30
SIZE_WARN_MB = 80.0

# Queries ordered by how likely they are to return a single, centred, well-lit
# marble bust against a dark background. Tried in order until one yields a
# usable clip.
SOURCE_QUERIES = [
    "marble bust statue",
    "ancient greek statue head",
    "roman statue bust museum",
    "marble sculpture face",
    "classical statue portrait",
]

# ---------------------------------------------------------------- grade looks
# All are dark and contrasty: the render adds gold/white text over these, and a
# bright or flat background makes that text unreadable.
GRADES = {
    # warm candle key — the channel's default register
    "warm":  "colorbalance=rs=0.06:gs=0.01:bs=-0.07,eq=contrast=1.18:brightness=-0.07:saturation=0.88",
    # cold moonlight — a register break for the harder themes
    "cold":  "colorbalance=rs=-0.08:gs=-0.01:bs=0.11,eq=contrast=1.22:brightness=-0.10:saturation=0.82",
    # near-silhouette: shape only, no detail
    "sil":   "eq=contrast=1.95:brightness=-0.26:saturation=0.45",
    # neutral stone
    "stone": "eq=contrast=1.12:brightness=-0.06:saturation=0.90",
}

# ------------------------------------------------------------------- framings
# Applied to a 1080x1920 frame. Each keeps the subject out of the top of frame,
# where the hook text sits.
FRAMINGS = {
    "full":  "crop=1080:1920:0:0",
    "left":  "scale=1512:2688,crop=1080:1920:120:520",     # subject sits left
    "right": "scale=1512:2688,crop=1080:1920:320:520",     # subject sits right
    "tight": "scale=1728:3072,crop=1080:1920:324:700",     # close on the face
    "low":   "scale=1350:2400,crop=1080:1920:135:400",     # looking up at it
    "wide":  "scale=864:1536,pad=1080:1920:108:300:black",  # small in a void
}

# --------------------------------------------------------------------- motion
# zoompan expressions. d is filled in at build time from CLIP_SECONDS * FPS.
MOTIONS = {
    "push":   "z='min(1.0+0.0009*on,1.35)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "pull":   "z='max(1.35-0.0009*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "drift":  "z=1.18:x='iw/2-(iw/zoom/2)+0.35*on':y='ih/2-(ih/zoom/2)'",
    "driftl": "z=1.18:x='iw/2-(iw/zoom/2)-0.35*on':y='ih/2-(ih/zoom/2)'",
    "riseup": "z=1.18:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-0.30*on'",
    "hold":   "z=1.06:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
}

# ---------------------------------------------------------------- the library
# 24 curated shots. Openers need presence (arriving, holding); closers need
# departure (receding, dimming). Order is deliberate: backgrounds.py offsets
# the closing bookend, so neighbours should not look alike.
#         name              framing  motion    grade    fade
VARIANTS: list[tuple] = [
    ("open_push",           "full",  "push",   "warm",  "in"),
    ("open_emerge",         "tight", "hold",   "warm",  "in"),
    ("open_profile_right",  "right", "hold",   "warm",  "in"),
    ("open_profile_left",   "left",  "hold",   "warm",  "in"),
    ("open_low_angle",      "low",   "riseup", "warm",  "in"),
    ("open_rack",           "tight", "push",   "stone", "in"),
    ("open_orbit_left",     "left",  "driftl", "warm",  "in"),
    ("open_orbit_right",    "right", "drift",  "warm",  "in"),
    ("open_candle",         "full",  "hold",   "warm",  "in"),
    ("open_topdown",        "tight", "hold",   "stone", "in"),
    ("open_small",          "wide",  "push",   "warm",  "in"),
    ("open_cold",           "full",  "hold",   "cold",  "in"),
    ("close_pull",          "full",  "pull",   "warm",  "out"),
    ("close_fade",          "tight", "hold",   "warm",  "out"),
    ("close_turn",          "right", "driftl", "warm",  "out"),
    ("close_eyes",          "tight", "hold",   "stone", "out"),
    ("close_descend",       "low",   "pull",   "warm",  "out"),
    ("close_silhouette",    "full",  "hold",   "sil",   "out"),
    ("close_texture",       "tight", "drift",  "stone", "out"),
    ("close_cold_key",      "full",  "hold",   "cold",  "out"),
    ("close_long_shadow",   "left",  "hold",   "sil",   "out"),
    ("close_settle",        "wide",  "pull",   "warm",  "out"),
    ("close_offcentre_r",   "right", "hold",   "cold",  "out"),
    ("close_offcentre_l",   "left",  "hold",   "warm",  "out"),
]


def _need(exe: str) -> str:
    path = shutil.which(exe)
    if not path:
        sys.exit(f"{exe} not found on PATH — install it first (apt install ffmpeg).")
    return path


def _duration(path: Path) -> float:
    try:
        out = subprocess.run(
            [_need("ffprobe"), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


# ------------------------------------------------------------------ sourcing

def _pixabay(query: str) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": key, "q": query, "per_page": 20,
                             "safesearch": "true"}, timeout=30)
    r.raise_for_status()
    out = []
    for hit in r.json().get("hits", []):
        vids = hit.get("videos", {})
        best = vids.get("large") or vids.get("medium") or vids.get("small") or {}
        if best.get("url"):
            out.append({"url": best["url"], "w": best.get("width", 0),
                        "h": best.get("height", 0), "dur": hit.get("duration", 0),
                        "src": "pixabay"})
    return out


def _pexels(query: str) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    r = requests.get("https://api.pexels.com/videos/search",
                     headers={"Authorization": key},
                     params={"query": query, "per_page": 20}, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("link")]
        if not files:
            continue
        best = max(files, key=lambda f: (f.get("height") or 0))
        out.append({"url": best["link"], "w": best.get("width", 0),
                    "h": best.get("height", 0), "dur": v.get("duration", 0),
                    "src": "pexels"})
    return out


def _score(c: dict) -> float:
    """Prefer tall, long, high-resolution clips.

    Tall matters most — a 9:16 source survives the crop to 1080x1920 with its
    composition intact, where a landscape source loses the sides of the head.
    Length matters next: a long clip lets each variant start at a different
    moment, so the library varies in performance as well as in treatment.
    """
    w, h, dur = c.get("w") or 1, c.get("h") or 1, c.get("dur") or 0
    tall = min(h / max(w, 1), 2.0) / 2.0           # 0..1, 1 = 9:16 or taller
    length = min(dur, 30) / 30.0                   # 0..1
    res = min(h, 2160) / 2160.0                    # 0..1
    return tall * 0.5 + length * 0.3 + res * 0.2


def find_source(dest: Path, queries: list[str]) -> dict | None:
    """Download the single best candidate clip. Returns its metadata."""
    candidates: list[dict] = []
    for q in queries:
        for fn in (_pixabay, _pexels):
            try:
                found = fn(q)
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] {fn.__name__}('{q}') failed: {str(e)[:100]}")
                continue
            for c in found:
                c["query"] = q
            candidates.extend(found)
        if candidates:
            break  # the first query that returns anything is the most on-target

    if not candidates:
        return None

    candidates.sort(key=_score, reverse=True)
    for c in candidates[:5]:
        try:
            print(f"  downloading {c['src']} {c['w']}x{c['h']} {c['dur']}s "
                  f"(score {_score(c):.2f}) …")
            with requests.get(c["url"], stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            if dest.stat().st_size > 100_000 and _duration(dest) >= 2.0:
                return c
            print("  [warn] download too small/short, trying next candidate")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] download failed: {str(e)[:100]}")
    return None


# ------------------------------------------------------------------ rendering

def build_clip(src: Path, dst: Path, framing: str, motion: str, grade: str,
               fade: str, start: float, crf: int) -> None:
    frames = int(CLIP_SECONDS * FPS)
    chain = [
        # Cover the canvas first so every framing expression works on a known size.
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        FRAMINGS[framing],
        "scale=1080:1920",
        f"zoompan={MOTIONS[motion]}:d={frames}:s=1080x1920:fps={FPS}",
        GRADES[grade],
        "vignette=PI/4",              # pull the eye to the centre, darken edges
        "noise=alls=5:allf=t",        # film grain, kills stock-footage plastic
        "format=yuv420p",
    ]
    if fade == "in":
        chain.append("fade=t=in:st=0:d=1.0:color=black")
    elif fade == "out":
        chain.append(f"fade=t=out:st={CLIP_SECONDS - 1.2:.2f}:d=1.2:color=black")

    cmd = [
        _need("ffmpeg"), "-y", "-loglevel", "error",
        "-ss", f"{start:.2f}", "-i", str(src),
        "-t", f"{CLIP_SECONDS:.2f}",
        "-an",
        "-vf", ",".join(chain),
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if not dst.exists() or dst.stat().st_size < 1_000:
        raise RuntimeError("encode produced nothing usable")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=len(VARIANTS),
                    help=f"how many clips to build (max {len(VARIANTS)})")
    ap.add_argument("--crf", type=int, default=26, help="H.264 quality (default 26)")
    ap.add_argument("--source", help="use this local video instead of downloading")
    ap.add_argument("--keep-existing", action="store_true",
                    help="do not clear assets/guide/ first")
    args = ap.parse_args()

    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="guide_src_"))
    try:
        if args.source:
            src = Path(args.source).expanduser()
            if not src.is_file():
                sys.exit(f"No such file: {src}")
            meta = {"src": "local", "query": src.name}
        else:
            src = tmpdir / "source.mp4"
            print("Finding a source clip (free stock, Pixabay then Pexels)…")
            meta = find_source(src, SOURCE_QUERIES)
            if meta is None:
                print("FAILED: no usable source clip found. The guide library is "
                      "optional — the pipeline falls back to stock search per "
                      "render, exactly as before.", file=sys.stderr)
                return 1

        dur = _duration(src)
        print(f"Source: {meta['src']} '{meta.get('query')}' {dur:.1f}s")
        if dur < CLIP_SECONDS:
            print(f"FAILED: source is only {dur:.1f}s, need {CLIP_SECONDS}s",
                  file=sys.stderr)
            return 1

        if not args.keep_existing:
            for old in GUIDE_DIR.glob("guide_*.mp4"):
                old.unlink()

        chosen = VARIANTS[:max(1, min(args.count, len(VARIANTS)))]
        # Spread start offsets across the source so variants differ in the
        # statue's actual moment, not only in treatment.
        span = max(0.0, dur - CLIP_SECONDS)
        step = span / max(1, len(chosen) - 1) if len(chosen) > 1 else 0.0

        print(f"Building {len(chosen)} clips from one source "
              f"(same statue in every shot by construction)…")
        ok, failed = 0, []
        for i, (name, framing, motion, grade, fade) in enumerate(chosen):
            dst = GUIDE_DIR / f"guide_{i + 1:02d}_{name}.mp4"
            try:
                build_clip(src, dst, framing, motion, grade, fade,
                           start=min(i * step, span), crf=args.crf)
            except Exception as e:  # noqa: BLE001
                failed.append(name)
                print(f"  [FAIL] {name}: {str(e)[:120]}")
                continue
            ok += 1
            print(f"  [ok] {dst.name}  {dst.stat().st_size / 1e6:.1f} MB")

        lib = sorted(GUIDE_DIR.glob("guide_*.mp4"))
        total_mb = sum(p.stat().st_size for p in lib) / 1e6
        print(f"\nLibrary: {len(lib)} clips, {total_mb:.1f} MB total")
        if failed:
            print(f"{len(failed)} variant(s) failed: {', '.join(failed)}")
        if total_mb > SIZE_WARN_MB:
            print(f"WARNING: over the {SIZE_WARN_MB:.0f} MB soft budget — these "
                  f"are COMMITTED files. Re-run with a higher --crf.")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
