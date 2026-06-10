"""
Text-to-speech via ElevenLabs.

Isolated on purpose: to switch to OpenAI TTS (much cheaper) or a free engine,
you only rewrite synthesize_voice() and nothing else in the project changes.

synthesize_voice() returns (audio_path, word_timings) where word_timings is a
list of (word, start_seconds, end_seconds). These drive the karaoke captions in
render.py. We get real per-word timing from ElevenLabs' "with-timestamps"
endpoint; if that's unavailable we fall back to estimating timings by spreading
the words across the audio duration weighted by word length, so a run never
breaks.
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

# Voice settings stay env-configurable; defaults match the previous values.
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
_VOICE_SETTINGS = {
    "stability": float(os.environ.get("ELEVENLABS_STABILITY", "0.55")),
    "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
    "style": float(os.environ.get("ELEVENLABS_STYLE", "0.25")),
    "use_speaker_boost": os.environ.get("ELEVENLABS_SPEAKER_BOOST", "1") not in ("0", "false", "False"),
}


def synthesize_voice(text: str, out_path: Path):
    """Synthesize `text`, write the MP3 to `out_path`, return (out_path, word_timings)."""
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": _VOICE_SETTINGS,
    }

    word_timings = []
    try:
        # Preferred path: per-character timestamps we fold into per-word timings.
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"
        resp = requests.post(
            url,
            headers={"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        out_path.write_bytes(base64.b64decode(data["audio_base64"]))
        alignment = data.get("alignment") or data.get("normalized_alignment")
        if alignment:
            word_timings = _words_from_alignment(alignment)
    except Exception as e:
        # Fallback: plain endpoint so a run never breaks on the timestamps API.
        print(f"  [tts] with-timestamps failed ({e}); falling back to plain endpoint")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
        resp = requests.post(
            url,
            headers={
                "xi-api-key": ELEVEN_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)

    if not word_timings:
        # No alignment (either fallback path, or audio-only response). Estimate
        # by distributing words across the real audio duration, weighted by length.
        word_timings = _estimate_word_timings(text, _probe_duration(out_path))

    return out_path, word_timings


def _words_from_alignment(alignment: dict):
    """Fold ElevenLabs per-character alignment into a list of (word, start, end)."""
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    if not (chars and starts and ends):
        return []

    timings = []
    cur, cur_start, cur_end = "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                timings.append((cur, cur_start, cur_end))
                cur, cur_start, cur_end = "", None, None
            continue
        if not cur:
            cur_start = s
        cur += ch
        cur_end = e
    if cur:
        timings.append((cur, cur_start, cur_end))
    return timings


def _estimate_word_timings(text: str, duration: float):
    """Spread words across `duration`, weighted by word length (+1 so punctuation/short words still get time)."""
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words or duration <= 0:
        return [(w, 0.0, 0.0) for w in words]

    weights = [len(w) + 1 for w in words]
    total = sum(weights)
    timings, t = [], 0.0
    for w, weight in zip(words, weights):
        span = duration * weight / total
        timings.append((w, t, t + span))
        t += span
    return timings


def _probe_duration(audio_path: Path) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(audio_path),
        ])
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 0.0
