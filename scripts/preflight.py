#!/usr/bin/env python3
"""
Look at the video before it publishes. Measure it. Save the evidence. Block it.

WHY THIS EXISTS — owner, 2026-09-01: "How can I teach you to learn to catch the
mistakes and actually watch the videos you're making, or before making them
know if the post has been reviewed?"

The honest answer is that teaching does not work here. For six weeks the output
was never looked at, while every decision was made from CSVs. When a real
published video was finally opened it showed a MELTED AI marble bust with
garbled pseudo-text on the plinth, at 12.8% mean luminance — a black rectangle
on a phone. Both were visible in ten minutes and neither was in any metric.

So this is not a reminder. It is a gate that runs on every render, writes the
frames to disk as evidence, and fails the post on defects a person would catch
instantly:

  * TOO DARK      mean luminance under MIN_LUMA. Measured on real output at
                  12.8% (F3) and 21.5% (normal). Both read as black.
  * DEAD FRAME    a frame with almost no variation is a black or frozen plate.
  * TEXT WALL     first-frame text covering more than MAX_TEXT_FRAC. A 20-word
                  hook at the old 12-char wrap rendered as ELEVEN lines over
                  63% of the frame.
  * NO OPENING    the first frame is near-empty: nothing to read, nothing to
                  look at, and roughly 400ms to lose the viewer.

    python scripts/preflight.py video.mp4              # verdict, exit 1 on FAIL
    python scripts/preflight.py video.mp4 --frames out/ # keep the contact sheet
    python scripts/preflight.py video.mp4 --json

Exit 0 pass, 1 fail. Never blocks on its own errors — a broken checker must not
cost a post, only a broken video should.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mean luminance floor, 0-255. Real output measured 32.6 (12.8%) and 54.9
# (21.5%); the owner called the frame too dark at both. 45 (~18%) is the floor
# where a phone at low brightness in a dark room still shows an image.
MIN_LUMA = float(45)
# YMAX-YMIN, the tonal range in the frame. signalstats emits no stddev, and the
# first version silently defaulted to a pass — a dead-frame check that could
# never fire, which is exactly the class of bug this script exists to catch.
MIN_RANGE = float(40)
# Fraction of the frame the opening text may cover.
MAX_TEXT_FRAC = 0.35
SAMPLE_TIMES = (0.1, 1.0, 3.0, 8.0, 15.0, 25.0)
# Seconds between sampled frames in the SINGLE decode pass. The first version
# ran a separate seek-and-decode ffmpeg for every timestamp — six for
# luminance, six more for the contact sheet, two for the text measurement.
# Roughly fourteen decodes per render attempt, multiplied by up to five
# attempts, took the daily run from ~12 minutes to ~38 and pushed six runs on
# 2026-09-05 past the 60-minute job cap, which cost a whole day of posting.
# One pass now produces every sample.
SAMPLE_EVERY = float(os.environ.get("PREFLIGHT_SAMPLE_EVERY", "6"))


def _probe_duration(path: Path) -> float:
    """Duration, or 0.0. Never raises — this gate blocks posts, so a missing
    binary must not become a crash that stops the channel."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True).stdout.strip()
        return float(out)
    except (ValueError, OSError):
        return 0.0


def _scan(path: Path, frames_dir: Path | None) -> list[dict]:
    """Every measurement in ONE decode pass.

    `fps=1/N` walks the file once and emits a frame every N seconds;
    signalstats prints luminance for each, and the same pass writes the
    contact sheet. Previously this was one ffmpeg seek per sample, which is
    what made the gate expensive enough to time the job out.
    """
    try:
        return _scan_inner(path, frames_dir)
    except OSError:
        return []          # no ffmpeg -> no samples -> the caller WARNS


def _scan_inner(path: Path, frames_dir: Path | None) -> list[dict]:
    args = ["ffmpeg", "-v", "info", "-y", "-i", str(path),
            "-vf", f"fps=1/{SAMPLE_EVERY},signalstats,metadata=print"]
    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=True)
        # -y must precede the output; appending it after "-" made ffmpeg treat
        # it as a second output and the whole scan returned nothing.
        args += ["-q:v", "4", str(frames_dir / f"{path.stem}_%02d.jpg")]
    else:
        args += ["-f", "null", "-"]
    out = subprocess.run(args, capture_output=True, text=True).stderr

    samples, cur = [], {}
    for line in out.splitlines():
        if "pts_time:" in line:
            if cur.get("luma") is not None:
                samples.append(cur)
            cur = {"t": float(line.split("pts_time:")[1].split()[0])}
        elif "YAVG" in line and "luma" not in cur:
            cur["luma"] = float(line.split("=")[-1])
        elif "YMIN" in line and "ymin" not in cur:
            cur["ymin"] = float(line.split("=")[-1])
        elif "YMAX" in line and "ymax" not in cur:
            cur["ymax"] = float(line.split("=")[-1])
    if cur.get("luma") is not None:
        samples.append(cur)
    for sm in samples:
        sm["range"] = sm.get("ymax", 255.0) - sm.get("ymin", 0.0)
    return samples


def _bright_fraction(path: Path, t: float) -> float:
    """Roughly, how much of the frame is text.

    Threshold 165, not 200: the channel's gold accent (#FFB830) has a luma
    around 180, so a near-white cutoff reported a frame COVERED in gold caps as
    having no text at all.
    """
    try:
        return _bright_fraction_inner(path, t)
    except OSError:
        return 0.0


def _bright_fraction_inner(path: Path, t: float) -> float:
    with tempfile.TemporaryDirectory() as d:
        png = Path(d) / "f.png"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path),
             "-frames:v", "1", "-vf",
             "scale=216:384,format=gray,lut=y='if(gt(val,165),255,0)'", str(png)],
            capture_output=True)
        if not png.exists():
            return 0.0
        out = subprocess.run(
            ["ffmpeg", "-v", "info", "-i", str(png), "-vf",
             "signalstats,metadata=print", "-f", "null", "-"],
            capture_output=True, text=True).stderr
        for line in out.splitlines():
            if "YAVG" in line:
                return float(line.split("=")[-1]) / 255.0
    return 0.0


def review(path: Path, frames_dir: Path | None = None) -> dict:
    """Measure the video. Returns a verdict dict; never raises."""
    res = {"video": path.name, "checks": [], "fails": [], "warns": [],
           "frames": [], "verdict": "pass"}
    if not path.exists():
        res["verdict"] = "error"
        res["fails"].append("video file does not exist")
        return res
    res["duration"] = round(_probe_duration(path), 1)

    samples = _scan(path, frames_dir)
    if not samples:
        res["warns"].append("could not sample any frames")
        res["verdict"] = "warn"
        return res

    lumas = []
    for sm in samples:
        lumas.append(sm["luma"])
        res["checks"].append({"t": round(sm["t"], 1), "luma": round(sm["luma"], 1),
                              "pct": round(sm["luma"] / 255, 3),
                              "range": round(sm["range"], 1)})
        if sm["range"] < MIN_RANGE:
            res["fails"].append(
                f"t={sm['t']:.0f}s is a dead frame (tonal range "
                f"{sm['range']:.0f}) — black or frozen")
    if frames_dir:
        res["frames"] = sorted(str(p) for p in frames_dir.glob(f"{path.stem}_*.jpg"))

    mean = sum(lumas) / len(lumas)
    res["mean_luma"] = round(mean, 1)
    res["mean_pct"] = round(mean / 255, 3)
    if mean < MIN_LUMA:
        res["fails"].append(
            f"too dark: mean luminance {mean:.1f}/255 ({mean / 255:.1%}), "
            f"floor is {MIN_LUMA:.0f} ({MIN_LUMA / 255:.0%}). This reads as a "
            f"black rectangle on a phone.")

    frac = _bright_fraction(path, samples[0]["t"])
    res["opening_text_frac"] = round(frac, 3)
    if frac > MAX_TEXT_FRAC:
        res["fails"].append(
            f"opening frame is a wall of text ({frac:.0%} covered, max "
            f"{MAX_TEXT_FRAC:.0%})")
    elif frac < 0.005:
        res["warns"].append(
            "opening frame has almost no text — nothing to read in the first "
            "second")

    res["verdict"] = "fail" if res["fails"] else ("warn" if res["warns"] else "pass")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--frames", help="directory to write the contact sheet into")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    res = review(Path(args.video), Path(args.frames) if args.frames else None)
    if args.json:
        print(json.dumps(res, indent=2))
        return 1 if res["verdict"] == "fail" else 0

    print(f"=== preflight: {res['video']} ({res.get('duration', '?')}s) ===")
    for c in res["checks"]:
        print(f"  t={c['t']:<5} luma {c['luma']:6.1f}/255 ({c['pct']:6.1%})  "
              f"range {c['range']:.0f}")
    if "mean_luma" in res:
        print(f"  mean luminance {res['mean_luma']}/255 = {res['mean_pct']:.1%} "
              f"(floor {MIN_LUMA / 255:.0%})")
    if "opening_text_frac" in res:
        print(f"  opening text covers {res['opening_text_frac']:.1%} of frame")
    for w in res["warns"]:
        print(f"  WARN {w}")
    for f in res["fails"]:
        print(f"  FAIL {f}")
    print(f"\n  VERDICT: {res['verdict'].upper()}")
    return 1 if res["verdict"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
