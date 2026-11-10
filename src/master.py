"""
Loudness mastering for the finished Short: YouTube's -14 LUFS, measured, not hoped for.

render.py ends its mix with single-pass loudnorm (I=-14), but on a ~10 s
Short single-pass loudnorm never gets there: it starts low and ramps. Measured
2026-11-10 on the rehearsal of `receive_without_arrogance`: -17.3 LUFS
integrated, peaks at -1.3 dBFS. YouTube turns louder videos down to about -14
and never turns quieter ones up, so our Shorts played ~3 dB under the ones
around them in the feed: the same music, just smaller.

master(video): measure (ebur128, the same EBU R128 meter YouTube's reference
follows), apply ONE constant gain to the target, with a peak limiter placed
before the gain so the headroom it needs exists, then measure again and trim
once if it came out short. A constant gain keeps the music's drop and the
voice's dynamics; loudnorm's dynamic mode flattens them (make_edit_music.py
learned that on the drops). The video stream is copied, never re-encoded.

Behind a switch (REEL_MASTER_LUFS, set by the new look's style pack) until the
owner picks the new look; any failure leaves the file exactly as rendered.
Tests: tests/test_master.py.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

TARGET = -14.0          # LUFS integrated: YouTube's playback reference
CEILING = -1.5          # dBFS sample peak after mastering (true peak lands ~0.3-0.8 dB above)
TOLERANCE = 0.5         # LU: close enough to the target
MAX_GAIN = 12.0         # dB: never lift a broken (near-silent) mix into noise


def measure(path: Path) -> tuple[float, float]:
    """(integrated LUFS, true peak dBFS) of the file's audio."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "a:0",
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=120)
    summary = r.stderr.split("Summary:")[-1]
    i = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
    tp = re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary, re.S)
    if not i or not tp:
        raise RuntimeError("no loudness reading (is there an audio stream?)")
    lufs, peak = (float("-inf") if x.group(1) == "-inf" else float(x.group(1)) for x in (i, tp))
    return lufs, peak


def _apply(src: Path, dst: Path, gain: float, ceiling: float) -> None:
    # Limit to (ceiling - gain) first, then add the gain: the peaks land on the
    # ceiling and everything under them rises by exactly `gain`.
    limit = 10 ** ((ceiling - max(gain, 0.0)) / 20)
    limit = min(1.0, max(0.0625, limit))          # alimiter's range
    chain = (f"alimiter=limit={limit:.6f}:attack=2:release=60:level=disabled,"
             f"volume={gain:.2f}dB,aresample=44100")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v?", "-map", "0:a:0",
                    "-c:v", "copy", "-af", chain, "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(dst)], check=True, timeout=180)


def master(path: Path, target: float = TARGET, ceiling: float = CEILING) -> dict:
    """Master `path` in place. Returns what happened; never raises."""
    path = Path(path)
    report: dict = {"target": target}
    try:
        before, peak = measure(path)
        report.update(before=round(before, 1), peakBefore=round(peak, 1))
        if before == float("-inf"):
            report["skipped"] = "silent"
            return report
        if abs(before - target) <= TOLERANCE and peak <= ceiling + 0.5:
            report["skipped"] = "already on target"
            return report
        gain = min(MAX_GAIN, target - before)
        tmp = path.with_suffix(".master.mp4")
        _apply(path, tmp, gain, ceiling)
        after, peak_after = measure(tmp)
        if after < target - TOLERANCE and gain < MAX_GAIN:
            # The limiter shaved a little loudness off the peaks; one trim.
            extra = min(MAX_GAIN - gain, target - after)
            gain += extra
            _apply(path, tmp, gain, ceiling)
            after, peak_after = measure(tmp)
        shutil.move(str(tmp), str(path))
        report.update(gain=round(gain, 2), after=round(after, 1), peakAfter=round(peak_after, 1))
        print(f"  [master] {report['before']} -> {report['after']} LUFS "
              f"(+{report['gain']} dB), peak {report['peakAfter']} dBFS", flush=True)
    except Exception as e:  # noqa: BLE001  a render must never fail on mastering
        report["error"] = f"{type(e).__name__}: {e}"[:200]
        path.with_suffix(".master.mp4").unlink(missing_ok=True)
        print(f"  [master] skipped ({report['error']}); the render is unchanged", flush=True)
    return report


def target_from_env() -> float | None:
    """REEL_MASTER_LUFS (e.g. "-14"), or None when mastering is off."""
    raw = os.environ.get("REEL_MASTER_LUFS", "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None
