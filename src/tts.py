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
"""
import base64
import json
import os
import re
import subprocess
from pathlib import Path

import requests

ELEVEN_API_KEY = os.environ["ELEVENLABS_API_KEY"]
# Default voice "Adam" (deep, calm). Override with ELEVENLABS_VOICE_ID secret.
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

# Voice / model settings stay configurable via env (defaults match prior values).
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
VOICE_SETTINGS = {
    "stability": float(os.environ.get("ELEVENLABS_STABILITY", "0.55")),
    "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
    "style": float(os.environ.get("ELEVENLABS_STYLE", "0.25")),
    "use_speaker_boost": os.environ.get("ELEVENLABS_SPEAKER_BOOST", "1") not in ("0", "false", "False"),
}

WordTiming = tuple  # (word: str, start: float, end: float)


def synthesize_voice(text: str, out_path: Path) -> tuple:
    """Synthesize `text` to `out_path`. Returns (out_path, word_timings)."""
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }

    # Preferred path: with-timestamps -> real per-character alignment.
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"
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
        # Audio is good but no usable alignment — keep it, estimate timing.
        return out_path, _estimate_timings(text, _audio_duration(out_path))
    except Exception as e:  # noqa: BLE001 — never let TTS take the whole run down
        print(f"  tts: with-timestamps unavailable ({e}); falling back to plain endpoint")

    # Fallback: plain endpoint, estimate timing from measured duration.
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
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
