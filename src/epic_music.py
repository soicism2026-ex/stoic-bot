"""
Epic music for stoic edits — real orchestral tracks, legally free.

Owner, 2026-10-01: "I want grand music that is trending". The music bed had
been a SYNTHETIC DRONE for weeks: Pixabay's music API returns 404, so every
post fell back to an ffmpeg-generated tone. That alone made the posts flat.

Trending songs can't be used: YouTube's upload API cannot attach the in-app
licensed sounds, and uploading a commercial track gets the video claimed or
the channel struck — the opposite of the monetisation goal. These are Kevin
MacLeod's tracks (incompetech.com), licensed CC BY 4.0: free on monetised
YouTube with the credit line in the description, which credit() supplies.

Each track starts 2s before its LOUDEST 22-second section, measured per
second with ffmpeg (astats RMS) — an edit lives on the big part, not the
quiet intro. Two ambient tracks from the candidate list (Sovereign, Lord of
the Land, peak RMS -27/-24 dB) were dropped as not epic.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

import proc

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "assets" / "music" / "epic"
BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"

# name -> second where the measured peak 22s window begins
TRACKS = {
    "Heroic Age": 65,
    "Five Armies": 126,
    "Crusade": 141,
    "Clash Defiant": 148,
    "Prelude and Action": 58,
    "Volatile Reaction": 133,
    "Achilles": 29,
    "Unholy Knight": 95,
    "Strength of the Titans": 3,
    "Exhilarate": 14,
    "Rising Game": 73,
    "Impact Prelude": 135,
    "Ancient Rite": 77,
}
LEAD_IN = 2.0


def pick(post_rows: list[dict]) -> str:
    """Least-recently-used track, so the channel never repeats one back to back."""
    last = {}
    for i, r in enumerate(post_rows):
        name = (r.get("music_track") or "").removeprefix("epic:")
        if name in TRACKS:
            last[name] = i
    return min(TRACKS, key=lambda n: last.get(n, -1))


def credit(name: str) -> str:
    return (f'Music: "{name}" by Kevin MacLeod (incompetech.com)\n'
            "Licensed under Creative Commons: By Attribution 4.0 License\n"
            "http://creativecommons.org/licenses/by/4.0/")


def fetch(name: str, out_path: Path, seconds: float) -> Path | None:
    """The track's big section, `seconds` long, faded in and out. None on any
    failure — the caller keeps whatever music it had."""
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        src = CACHE / (name.replace(" ", "_") + ".mp3")
        if not src.exists() or src.stat().st_size < 100_000:
            r = requests.get(BASE + requests.utils.quote(name) + ".mp3", timeout=60)
            r.raise_for_status()
            src.write_bytes(r.content)
        start = max(0.0, TRACKS[name] - LEAD_IN)
        fade_out = max(0.0, seconds - 1.2)
        proc.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", str(src),
                  "-t", f"{seconds:.2f}",
                  "-af", f"afade=t=in:d=0.25,afade=t=out:st={fade_out:.2f}:d=1.2",
                  "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
                 check=True, capture_output=True)
        return out_path if out_path.exists() and out_path.stat().st_size > 10_000 else None
    except Exception as e:  # noqa: BLE001
        print(f"[epic_music] {name} unavailable ({e})", file=sys.stderr)
        return None
