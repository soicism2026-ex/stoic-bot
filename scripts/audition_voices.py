#!/usr/bin/env python3
"""
Render the SAME script in every candidate voice so the owner can choose by ear.

Three rounds of guessing at the voice have now failed — a stock Chatterbox
voice, then two attempts to filter it into shape. Filters cannot recast a
performance. This produces the actual candidates as MP3s and lets the ear
decide, which is the only thing that has ever settled a taste question here.

Runs in CI (.github/workflows/audition-voices.yml) because edge-tts is
unreachable from the dev sandbox, and commits the files to samples/voices/ so
they play on a phone.

    python scripts/audition_voices.py
    python scripts/audition_voices.py --text "custom line to read"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "voices"

# A real script, not a test phrase: the voice has to carry a hook, a quote and
# a turn. Judging on "hello world" tells you nothing about how it reads Seneca.
SCRIPT = (
    "Nero handed him a death sentence. Seneca did not argue. "
    "He had spent a lifetime rehearsing this exact moment. "
    "It is not that we have a short time to live, but that we waste much of it. "
    "You already know what you are wasting."
)

# Deep male English voices. Andrew, BrianEdge and Chatterbox are excluded on
# purpose — all three are vetoed in data/decisions.md.
CANDIDATES = [
    ("Ryan_GB",      "en-GB-RyanNeural",        "-4%", "-6Hz"),
    ("Thomas_GB",    "en-GB-ThomasNeural",      "-4%", "-4Hz"),
    ("Steffan_US",   "en-US-SteffanNeural",     "-4%", "-6Hz"),
    ("Tony_US",      "en-US-TonyNeural",        "-4%", "-6Hz"),
    ("Davis_US",     "en-US-DavisNeural",       "-4%", "-6Hz"),
    ("Roger_US",     "en-US-RogerNeural",       "-4%", "-6Hz"),
    ("William_AU",   "en-AU-WilliamNeural",     "-4%", "-4Hz"),
    ("Christopher",  "en-US-ChristopherNeural", "+0%", "-8Hz"),
]


async def _render(voice_id: str, rate: str, pitch: str, dst: Path, text: str) -> None:
    import edge_tts
    comm = edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch)
    await comm.save(str(dst))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=SCRIPT)
    ap.add_argument("--no-master", action="store_true",
                    help="skip the mastering chain and hear the raw voice")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "src"))
    import tts

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.mp3"):
        old.unlink()

    print(f"Auditioning {len(CANDIDATES)} voices on {len(args.text.split())} words\n")
    made = []
    for name, vid, rate, pitch in CANDIDATES:
        dst = OUT / f"{name}.mp3"
        try:
            asyncio.run(_render(vid, rate, pitch, dst, args.text))
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {name}: {str(e)[:110]}")
            continue
        if not args.no_master:
            tts._master_voice(dst)
        dur = tts._audio_duration(dst)
        wpm = len(args.text.split()) / (dur / 60) if dur else 0
        made.append(name)
        print(f"  [ok] {name:14} {vid:26} {dur:5.1f}s  {wpm:3.0f} wpm  "
              f"{dst.stat().st_size / 1000:.0f} kB")

    print(f"\n{len(made)}/{len(CANDIDATES)} rendered to {OUT}")
    if made:
        print("Listen, then put the winner at the top of VOICE_POOL in src/tts.py.")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
