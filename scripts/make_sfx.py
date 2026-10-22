"""
Sound effects for the edits, generated with ElevenLabs (owner, 2026-10-21).

    python scripts/make_sfx.py generate                 # every sound not yet in the bank
    python scripts/make_sfx.py generate --only whoosh_air,impact_boom

Each sound is made from a written description only (POST /v1/sound-generation),
trimmed to start on its first transient, faded out, peak-normalised to -1 dBFS,
saved to assets/sfx/<id>.mp3 and recorded UNAPPROVED in data/sfx.json with its
provenance. ElevenLabs sound effects are royalty-free for commercial use on a
paid plan (the channel is on Starter). Nothing airs until the owner approves
it (src/sfx.py).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "sfx"
BANK = ROOT / "data" / "sfx.json"
API = "https://api.elevenlabs.io/v1/sound-generation"
MODEL = "eleven_text_to_sound_v2"

SPECS = [
    {"id": "impact_boom", "role": "impact", "duration": 2.2, "influence": 0.55,
     "label": "Cinematic boom",
     "text": "One deep cinematic impact hit: a huge low boom with a short metallic ring tail, "
             "movie trailer style. A single hit, no music, no voice."},
    {"id": "impact_stone", "role": "impact", "duration": 2.0, "influence": 0.55,
     "label": "Stone slam",
     "text": "A heavy stone slab slamming shut in a temple: one deep thud, falling dust, short "
             "hall reverb. A single hit, no music, no voice."},
    {"id": "whoosh_air", "role": "whoosh", "duration": 1.0, "influence": 0.6,
     "label": "Air whoosh",
     "text": "One fast, clean air whoosh passing from left to right, a cinematic transition. "
             "No music, no voice."},
    {"id": "whoosh_blade", "role": "whoosh", "duration": 1.2, "influence": 0.6,
     "label": "Blade swing",
     "text": "A sword swung fast through the air: a whoosh ending in a soft metallic shing. "
             "No music, no voice."},
]


def load_bank() -> list[dict]:
    try:
        return json.loads(BANK.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def save_bank(bank: list[dict]) -> None:
    BANK.write_text(json.dumps(bank, indent=2) + "\n", encoding="utf-8")


def generate_raw(spec: dict, key: str) -> bytes:
    resp = requests.post(
        API, headers={"xi-api-key": key, "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={"text": spec["text"], "duration_seconds": spec["duration"],
              "prompt_influence": spec["influence"], "model_id": MODEL},
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{spec['id']}: HTTP {resp.status_code}: {resp.text[:200]}")
    if len(resp.content) < 2000:
        raise RuntimeError(f"{spec['id']}: empty audio")
    return resp.content


def finish(raw: Path, out: Path, duration: float) -> None:
    """Start on the first transient, fade the tail, peak-normalise to -1 dBFS."""
    with tempfile.TemporaryDirectory() as td:
        trimmed = Path(td) / "t.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
             "silenceremove=start_periods=1:start_threshold=-45dB,"
             f"atrim=0:{duration:.2f},afade=t=out:st={max(0.0, duration - 0.25):.2f}:d=0.25",
             "-ar", "44100", "-ac", "2", str(trimmed)],
            check=True)
        probe = subprocess.run(["ffmpeg", "-v", "info", "-i", str(trimmed), "-af", "volumedetect",
                                "-f", "null", "-"], capture_output=True, text=True)
        m = re.search(r"max_volume:\s*(-?[\d.]+) dB", probe.stderr)
        gain = -1.0 - float(m.group(1)) if m else 0.0
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(trimmed),
                        "-af", f"volume={gain:.2f}dB", "-c:a", "libmp3lame", "-b:a", "192k", str(out)],
                       check=True)


def generate(only: list[str] | None = None) -> int:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("no ELEVENLABS_API_KEY", file=sys.stderr)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bank = load_bank()
    have = {t["id"] for t in bank}
    made = 0
    for spec in SPECS:
        if only and spec["id"] not in only:
            continue
        if not only and spec["id"] in have:
            continue
        raw = OUT_DIR / f"{spec['id']}.raw.mp3"
        out = OUT_DIR / f"{spec['id']}.mp3"
        raw.write_bytes(generate_raw(spec, key))
        try:
            finish(raw, out, spec["duration"])
        finally:
            raw.unlink(missing_ok=True)
        entry = {
            "id": spec["id"], "role": spec["role"], "label": spec["label"],
            "file": str(out.relative_to(ROOT)), "approved": False,
            "provenance": {"model": MODEL, "prompt": spec["text"], "duration": spec["duration"],
                           "prompt_influence": spec["influence"],
                           "generated": dt.date.today().isoformat(),
                           "license": "ElevenLabs sound effects: royalty-free, commercial use on paid plans"},
        }
        bank = [t for t in bank if t["id"] != spec["id"]] + [entry]
        made += 1
        print(f"made {spec['id']} -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    save_bank(bank)
    return made


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--only", default="")
    a = ap.parse_args()
    only = [x.strip() for x in a.only.split(",") if x.strip() and x.strip() != "all"] or None
    made = generate(only)
    print(f"{made} sound(s) made")
    return 0 if made or not only else 1


if __name__ == "__main__":
    sys.exit(main())
