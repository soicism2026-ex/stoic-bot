"""
Text-to-speech via ElevenLabs.

Isolated on purpose: to switch to OpenAI TTS (much cheaper) or a free engine,
you only rewrite synthesize_voice() and nothing else in the project changes.

synthesize_voice() returns (audio_path, word_timings) where word_timings is a
list of (word, start_seconds, end_seconds). The timings drive the karaoke
captions in render.py. We prefer ElevenLabs' /with-timestamps endpoint for real
per-character timing (folded up to words); if that is unavailable or fails we
fall back to the plain endpoint and estimate timing by distributing words across
the measured audio duration weighted by word length — so a run never breaks.

Voice pool: three voices chosen for the Stoic niche (deep, measured, authoritative).
Rotates analytics-weighted once each voice has ≥5 posts of view data; uses LRU
equal rotation before that.  George (British, deep) is the default opener.
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
# Voice pool
# ---------------------------------------------------------------------------

# Three ElevenLabs voices suited to deep, authoritative Stoic content.
# George: British, gravelly, commanding — top pick for this niche.
# Daniel: British, calm and professorial.
# Brian: American, deep and measured.
VOICE_POOL = [
    {"name": "George", "id": "JBFqnCBsd6RMkjVDRZzb"},
    {"name": "Daniel", "id": "onwK4e9ZLuTAKqWW03F9"},
    {"name": "Brian",  "id": "nPczCjzI2devNBz1zQrb"},
]

# Single-voice override: ELEVENLABS_VOICE_ID still works as a hard override.
_VOICE_ID_OVERRIDE = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()

MIN_POSTS_FOR_WEIGHT = 5  # posts per voice before analytics-weighting kicks in

# Voice / model settings stay configurable via env (defaults match prior values).
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
VOICE_SETTINGS = {
    "stability": float(os.environ.get("ELEVENLABS_STABILITY", "0.55")),
    "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
    "style": float(os.environ.get("ELEVENLABS_STYLE", "0.25")),
    "use_speaker_boost": os.environ.get("ELEVENLABS_SPEAKER_BOOST", "1") not in ("0", "false", "False"),
}

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
      - Hard override: if ELEVENLABS_VOICE_ID is set, use it directly.
      - Exploration (< MIN_POSTS_FOR_WEIGHT data per voice): LRU rotation.
      - Exploitation (enough data): block most-recent, pick highest avg-views.
    """
    if _VOICE_ID_OVERRIDE:
        # Honour legacy single-voice override; synthesize name from pool.
        for v in VOICE_POOL:
            if v["id"] == _VOICE_ID_OVERRIDE:
                return v
        return {"name": "Custom", "id": _VOICE_ID_OVERRIDE}

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

    # Exploration: at least one voice lacks enough data → LRU.
    if any(val is None for val in avgs.values()):
        candidates = [v for v in VOICE_POOL if v["name"] != block] or VOICE_POOL
        return candidates[date.today().toordinal() % len(candidates)]

    # Exploitation: pick highest avg-views, blocking most recent.
    candidates = [v for v in VOICE_POOL if v["name"] != block] or VOICE_POOL
    return max(candidates, key=lambda v: avgs.get(v["name"], 0))


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesize_voice(text: str, out_path: Path, voice_id: str = None) -> tuple:
    """Synthesize `text` to `out_path`. Returns (out_path, word_timings)."""
    vid = voice_id or (_VOICE_ID_OVERRIDE if _VOICE_ID_OVERRIDE else VOICE_POOL[0]["id"])

    headers = {
        "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }

    # Preferred path: with-timestamps -> real per-character alignment.
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps"
        resp = requests.post(url, headers={**headers, "Accept": "application/json"},
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
    except Exception as e:  # noqa: BLE001
        print(f"  tts: with-timestamps unavailable ({e}); falling back to plain endpoint")

    # Fallback: plain endpoint, estimate timing from measured duration.
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    resp = requests.post(url, headers={**headers, "Accept": "audio/mpeg"},
                         json=payload, timeout=120)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    return out_path, _estimate_timings(text, _audio_duration(out_path))


def _tokenize(text: str) -> list:
    """Split into display words (keeps trailing punctuation with the word)."""
    return re.findall(r"\S+", text)


def _words_from_alignment(text: str, alignment) -> list:
    """Fold ElevenLabs per-character alignment into per-word (word, start, end).

    alignment shape:
      {"characters": [...], "character_start_times_seconds": [...],
       "character_end_times_seconds": [...]}
    """
    if not alignment:
        return []
    chars = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends = alignment.get("character_end_times_seconds")
    if not chars or not starts or not ends:
        return []
    if not (len(chars) == len(starts) == len(ends)):
        return []

    timings = []
    cur_chars = []
    cur_start = None
    cur_end = None
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
    """Spread words across `duration`, weighted by word length (never breaks)."""
    words = _tokenize(text)
    if not words:
        return []
    weights = [max(1, len(w)) for w in words]
    total = sum(weights)
    timings = []
    t = 0.0
    for w, wt in zip(words, weights):
        span = duration * (wt / total)
        timings.append((w, t, t + span))
        t += span
    return timings


def _audio_duration(audio_path: Path) -> float:
    """Best-effort audio length via ffprobe; falls back to a sane default."""
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(audio_path),
        ])
        return float(json.loads(out)["format"]["duration"])
    except Exception:  # noqa: BLE001
        return 20.0
