"""
Text-to-speech — ElevenLabs primary (when ELEVENLABS_API_KEY is set),
edge-tts (Microsoft Neural, free) as automatic fallback.

synthesize_voice() returns (audio_path, word_timings) where word_timings is a
list of (word, start_seconds, end_seconds). The timings drive the karaoke
captions in render.py.

Voice pool — three deep ElevenLabs voices tuned for the Stoic niche:
  George — British, gravelly, commanding
  Adam   — American, very deep narrator
  Brian  — American, deep and measured
Rotates analytics-weighted once each voice has enough data; LRU before that.
Falls back to edge-tts if no EL key is set.
"""
import base64
import csv
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Voice pool — ElevenLabs (primary)
# ---------------------------------------------------------------------------

VOICE_POOL = [
    {"name": "Brian",  "id": "nPczCjzI2devNBz1zQrb"},  # deep American — user preferred
    {"name": "George", "id": "JBFqnCBsd6RMkjVDRZzb"},
    {"name": "Adam",   "id": "pNInz6obpgDQGcFmaJgB"},
]

_EL_KEY      = os.environ.get("ELEVENLABS_API_KEY", "").strip()
_EL_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()

MIN_POSTS_FOR_WEIGHT = 5

MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
VOICE_SETTINGS = {
    "stability":        float(os.environ.get("ELEVENLABS_STABILITY",        "0.72")),
    "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.90")),
    "style":            float(os.environ.get("ELEVENLABS_STYLE",            "0.20")),
    "use_speaker_boost": os.environ.get("ELEVENLABS_SPEAKER_BOOST", "1") not in ("0", "false", "False"),
}
OUTPUT_FORMAT = os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")

WordTiming = tuple  # (word: str, start: float, end: float)


def _load_analytics() -> dict[str, int]:
    ROOT = Path(__file__).resolve().parent.parent
    path = ROOT / "data" / "analytics.csv"
    if not path.exists():
        return {}
    peak: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            v = int(row.get("views") or 0)
            if vid and v > peak.get(vid, 0):
                peak[vid] = v
    return peak


def pick_voice(rows: list[dict]) -> dict:
    """Return a voice from VOICE_POOL using analytics-weighted selection."""
    if _EL_VOICE_ID:
        for v in VOICE_POOL:
            if v["id"] == _EL_VOICE_ID:
                return v
        return {"name": "Custom", "id": _EL_VOICE_ID}

    analytics = _load_analytics()

    def avg_views(voice_name: str) -> float | None:
        matching = [r for r in rows
                    if r.get("voice_name") == voice_name and r.get("video_id")]
        if len(matching) < MIN_POSTS_FOR_WEIGHT:
            return None
        return sum(analytics.get(r["video_id"], 0) for r in matching) / len(matching)

    avgs = {v["name"]: avg_views(v["name"]) for v in VOICE_POOL}
    recent_voices = [r.get("voice_name") for r in reversed(rows) if r.get("voice_name")]
    block = recent_voices[0] if recent_voices else None

    if any(val is None for val in avgs.values()):
        candidates = [v for v in VOICE_POOL if v["name"] != block] or VOICE_POOL
        return candidates[date.today().toordinal() % len(candidates)]

    candidates = [v for v in VOICE_POOL if v["name"] != block] or VOICE_POOL
    return max(candidates, key=lambda v: avgs.get(v["name"], 0))


# ---------------------------------------------------------------------------
# ElevenLabs synthesis (primary)
# ---------------------------------------------------------------------------

def synthesize_voice(text: str, out_path: Path, voice_id: str = None) -> tuple:
    """Synthesize text. Uses ElevenLabs if key is set, else falls back to edge-tts."""
    if _EL_KEY:
        vid = voice_id or (_EL_VOICE_ID if _EL_VOICE_ID else VOICE_POOL[0]["id"])
        return _synthesize_elevenlabs(text, out_path, vid, fallback_to_default=True)
    print("  tts: no ELEVENLABS_API_KEY — using edge-tts fallback")
    return _synthesize_edge(text, out_path, "en-US-GuyNeural")


def _synthesize_elevenlabs(text: str, out_path: Path, vid: str,
                            fallback_to_default: bool = False) -> tuple:
    headers = {"xi-api-key": _EL_KEY, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": MODEL_ID, "voice_settings": VOICE_SETTINGS}

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps"
        resp = requests.post(url, headers={**headers, "Accept": "application/json"},
                             params={"output_format": OUTPUT_FORMAT},
                             json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        audio_b64 = data.get("audio_base64")
        if not audio_b64:
            raise ValueError("with-timestamps response missing audio_base64")
        out_path.write_bytes(base64.b64decode(audio_b64))
        alignment = data.get("alignment") or data.get("normalized_alignment")
        timings = _words_from_alignment(text, alignment)
        if timings:
            return out_path, timings
        return out_path, _estimate_timings(text, _audio_duration(out_path))
    except Exception as e:
        print(f"  tts: with-timestamps unavailable ({e}); falling back to plain endpoint")

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
        resp = requests.post(url, headers={**headers, "Accept": "audio/mpeg"},
                             params={"output_format": OUTPUT_FORMAT},
                             json=payload, timeout=120)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return out_path, _estimate_timings(text, _audio_duration(out_path))
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 403 and fallback_to_default:
            default_vid = VOICE_POOL[0]["id"]
            if vid != default_vid:
                print(f"  tts: voice {vid} returned 403; retrying with {VOICE_POOL[0]['name']}")
                return _synthesize_elevenlabs(text, out_path, default_vid, fallback_to_default=False)
        raise


# ---------------------------------------------------------------------------
# edge-tts fallback (no API key required)
# ---------------------------------------------------------------------------

async def _edge_stream(text: str, out_path: Path, voice_id: str) -> list:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice_id, rate="-5%", pitch="-8Hz")
    audio_chunks: list[bytes] = []
    word_timings: list[tuple] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            start = chunk["offset"] / 1e7
            dur   = chunk["duration"] / 1e7
            word_timings.append((chunk["text"], start, start + dur))
    out_path.write_bytes(b"".join(audio_chunks))
    return word_timings


def _synthesize_edge(text: str, out_path: Path, voice_id: str) -> tuple:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        timings = loop.run_until_complete(_edge_stream(text, out_path, voice_id))
    except RuntimeError:
        timings = asyncio.run(_edge_stream(text, out_path, voice_id))
    if not timings:
        timings = _estimate_timings(text, _audio_duration(out_path))
    return out_path, timings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list:
    return re.findall(r"\S+", text)


def _words_from_alignment(text: str, alignment) -> list:
    if not alignment:
        return []
    chars  = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends   = alignment.get("character_end_times_seconds")
    if not chars or not starts or not ends:
        return []
    if not (len(chars) == len(starts) == len(ends)):
        return []
    timings = []
    cur_chars, cur_start, cur_end = [], None, None
    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if cur_chars:
                timings.append(("".join(cur_chars), cur_start, cur_end))
                cur_chars, cur_start, cur_end = [], None, None
            continue
        if cur_start is None:
            cur_start = st
        cur_end = en
        cur_chars.append(ch)
    if cur_chars:
        timings.append(("".join(cur_chars), cur_start, cur_end))
    return timings


def _estimate_timings(text: str, duration: float) -> list:
    words = _tokenize(text)
    if not words:
        return []
    weights = [max(1, len(w)) for w in words]
    total = sum(weights)
    timings, t = [], 0.0
    for w, wt in zip(words, weights):
        span = duration * (wt / total)
        timings.append((w, t, t + span))
        t += span
    return timings


def _audio_duration(audio_path: Path) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(audio_path),
        ])
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 20.0
