"""
Text-to-speech via edge-tts (Microsoft Neural — free, no API key required).

edge-tts uses the same engine as Azure Cognitive Services Neural TTS but at
zero cost through the Edge browser TTS endpoint.  No account, no key, no rate
limits at our posting frequency.

ElevenLabs is retained as an optional upgrade: set ELEVENLABS_API_KEY +
ELEVENLABS_VOICE_ID to override the free engine on any run.

synthesize_voice() returns (audio_path, word_timings) where word_timings is a
list of (word, start_seconds, end_seconds). The timings drive the karaoke
captions in render.py.

Voice pool — three deep Microsoft Neural voices tuned for the Stoic niche:
  Guy         — deep, dominant American; closest to high-view Stoic Shorts style
  Ryan        — deep British, measured and philosophical
  Christopher — authoritative American, confident narrator register
Rotates analytics-weighted once each voice has ≥5 posts of view data; uses LRU
equal rotation before that.
"""
import asyncio
import csv
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Voice pool — edge-tts Microsoft Neural (free)
# ---------------------------------------------------------------------------

VOICE_POOL = [
    {"name": "Guy",         "id": "en-US-GuyNeural"},
    {"name": "Ryan",        "id": "en-GB-RyanNeural"},
    {"name": "Christopher", "id": "en-US-ChristopherNeural"},
]

# Optional ElevenLabs override: set both ELEVENLABS_API_KEY and
# ELEVENLABS_VOICE_ID to bypass edge-tts for a specific run.
_EL_KEY      = os.environ.get("ELEVENLABS_API_KEY", "").strip()
_EL_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()

MIN_POSTS_FOR_WEIGHT = 5

WordTiming = tuple  # (word: str, start: float, end: float)


def _load_analytics() -> dict[str, int]:
    """Return {video_id: peak_views} from data/analytics.csv."""
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
    """Return a voice from VOICE_POOL using analytics-weighted selection.

    Strategy:
      - Exploration (< MIN_POSTS_FOR_WEIGHT data per voice): LRU rotation.
      - Exploitation (enough data): block most-recent, pick highest avg-views.
    """
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
# edge-tts synthesis (primary)
# ---------------------------------------------------------------------------

async def _edge_stream(text: str, out_path: Path, voice_id: str) -> list:
    """Async core: stream edge-tts, collect audio + word boundaries."""
    import edge_tts  # lazy import keeps startup fast when EL override is used

    communicate = edge_tts.Communicate(text, voice_id, rate="-5%", pitch="-8Hz")
    audio_chunks: list[bytes] = []
    word_timings: list[tuple] = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            # Microsoft reports offsets in 100-nanosecond ticks
            start = chunk["offset"] / 1e7
            dur   = chunk["duration"] / 1e7
            word_timings.append((chunk["text"], start, start + dur))

    out_path.write_bytes(b"".join(audio_chunks))
    return word_timings


def _synthesize_edge(text: str, out_path: Path, voice_id: str) -> tuple:
    """Run edge-tts synthesis and return (out_path, word_timings)."""
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
# ElevenLabs synthesis (optional upgrade)
# ---------------------------------------------------------------------------

_EL_MODEL = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
_EL_SETTINGS = {
    "stability":        float(os.environ.get("ELEVENLABS_STABILITY",        "0.72")),
    "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.90")),
    "style":            float(os.environ.get("ELEVENLABS_STYLE",            "0.20")),
    "use_speaker_boost": os.environ.get("ELEVENLABS_SPEAKER_BOOST", "1") not in ("0", "false"),
}
_EL_FORMAT = os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")


def _synthesize_elevenlabs(text: str, out_path: Path, voice_id: str) -> tuple:
    """ElevenLabs path (only called when ELEVENLABS_API_KEY + VOICE_ID are set)."""
    headers = {"xi-api-key": _EL_KEY, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": _EL_MODEL, "voice_settings": _EL_SETTINGS}

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
        resp = requests.post(url, headers={**headers, "Accept": "application/json"},
                             params={"output_format": _EL_FORMAT},
                             json=payload, timeout=120)
        resp.raise_for_status()
        import base64
        data = resp.json()
        out_path.write_bytes(base64.b64decode(data["audio_base64"]))
        alignment = data.get("alignment") or data.get("normalized_alignment")
        timings = _words_from_alignment(text, alignment)
        if timings:
            return out_path, timings
    except Exception as e:
        print(f"  tts: ElevenLabs with-timestamps failed ({e}); trying plain endpoint")

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        resp = requests.post(url, headers={**headers, "Accept": "audio/mpeg"},
                             params={"output_format": _EL_FORMAT},
                             json=payload, timeout=120)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return out_path, _estimate_timings(text, _audio_duration(out_path))
    except Exception as e:
        print(f"  tts: ElevenLabs plain endpoint also failed ({e}); falling back to edge-tts")
        return _synthesize_edge(text, out_path, VOICE_POOL[0]["id"])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def synthesize_voice(text: str, out_path: Path, voice_id: str = None) -> tuple:
    """Synthesize `text` to `out_path`. Returns (out_path, word_timings).

    Uses ElevenLabs only when both ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID
    are set (legacy override path). Otherwise uses edge-tts for free.
    """
    if _EL_KEY and _EL_VOICE_ID:
        print(f"  tts: ElevenLabs override active (voice {_EL_VOICE_ID})")
        return _synthesize_elevenlabs(text, out_path, _EL_VOICE_ID)

    vid = voice_id or VOICE_POOL[0]["id"]
    # Resolve name for logging
    name = next((v["name"] for v in VOICE_POOL if v["id"] == vid), vid)
    print(f"  tts: edge-tts voice {name} ({vid})")
    return _synthesize_edge(text, out_path, vid)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list:
    return re.findall(r"\S+", text)


def _words_from_alignment(text: str, alignment) -> list:
    """Fold ElevenLabs per-character alignment into per-word timings."""
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
    """Spread words across duration weighted by word length."""
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
