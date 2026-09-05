#!/usr/bin/env python3
"""
Measure how far the reported word timings sit from the actual audio.

WHY: the owner reports captions running slightly out of sync with the voice.
The captions are driven by edge-tts WordBoundary events, which report offsets
in 100-nanosecond ticks — but nothing has ever checked those offsets against
where sound actually begins in the rendered file. Two plausible sources of a
systematic shift:

  * MP3 encoder delay. edge-tts returns MP3; _master_voice re-encodes to MP3.
    Each LAME pass adds ~1152 samples (~26ms at 44.1kHz) of leading padding,
    and the word timings do not know about it.
  * WordBoundary offsets marking synthesis position rather than audible onset.

Either way the fix is the same and it is NOT a guessed constant: measure the
offset, then set REEL_CAPTION_OFFSET to the measured value.

This must run where edge-tts can reach Microsoft. The dev container's proxy
blocks it (SSL interception breaks aiohttp), so it runs in CI.

    python scripts/measure_tts_drift.py
    python scripts/measure_tts_drift.py --voice en-US-SteffanNeural --master
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SENTENCE = ("His name was Serenus. He wasn't in crisis. "
            "Nothing had collapsed at all.")


def _first_sound(path: Path, floor_db: int = -45) -> float | None:
    """Seconds until audio first rises above the noise floor."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-af",
         f"silencedetect=n={floor_db}dB:d=0.05", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    # A file that starts with silence reports silence_end at the first sound.
    for line in out.splitlines():
        if "silence_end" in line:
            return float(line.split("silence_end:")[1].split()[0])
    # No leading silence detected at all — sound starts immediately.
    return 0.0


async def _synth(text: str, voice: str, out: Path) -> list[tuple]:
    import edge_tts
    c = edge_tts.Communicate(text, voice)
    audio, words = [], []
    async for ch in c.stream():
        if ch["type"] == "audio":
            audio.append(ch["data"])
        elif ch["type"] == "WordBoundary":
            words.append((ch["text"], ch["offset"] / 1e7, ch["duration"] / 1e7))
    out.write_bytes(b"".join(audio))
    return words


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default="en-US-SteffanNeural")
    ap.add_argument("--master", action="store_true",
                    help="also measure AFTER _master_voice re-encodes")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "raw.mp3"
        try:
            words = asyncio.run(_synth(SENTENCE, args.voice, raw))
        except Exception as e:  # noqa: BLE001
            print(f"edge-tts unreachable ({str(e)[:120]}) — "
                  f"must run where Microsoft is reachable.", file=sys.stderr)
            return 0
        if not words:
            print("no word boundaries returned", file=sys.stderr)
            return 0

        reported = words[0][1]
        actual = _first_sound(raw)
        print(f"=== {args.voice} ===")
        print(f"  first word          : {words[0][0]!r}")
        print(f"  reported onset      : {reported:.3f}s")
        print(f"  actual audio onset  : {actual:.3f}s")
        print(f"  DRIFT (raw)         : {actual - reported:+.3f}s")

        if args.master:
            import tts
            mastered = Path(d) / "m.mp3"
            mastered.write_bytes(raw.read_bytes())
            tts._master_voice(mastered)
            after = _first_sound(mastered)
            print(f"  actual onset AFTER mastering: {after:.3f}s")
            print(f"  DRIFT (mastered)    : {after - reported:+.3f}s")
            print(f"  added by mastering  : {after - actual:+.3f}s")

        drift = actual - reported
        print()
        if abs(drift) < 0.03:
            print("  Under 30ms — imperceptible. No correction needed.")
        else:
            print(f"  Set REEL_CAPTION_OFFSET={drift:+.3f} in the workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
