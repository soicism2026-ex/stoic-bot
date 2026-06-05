"""
Text-to-speech via ElevenLabs.

Isolated on purpose: to switch to OpenAI TTS (much cheaper) or a free engine,
you only rewrite synthesize_voice() and nothing else in the project changes.
"""
import os
import requests
from pathlib import Path

ELEVEN_API_KEY = os.environ["ELEVENLABS_API_KEY"]
# Default voice "Adam" (deep, calm). Override with ELEVENLABS_VOICE_ID secret.
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
MODEL_ID = "eleven_multilingual_v2"


def synthesize_voice(text: str, out_path: Path) -> Path:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.75,
            "style": 0.25,
            "use_speaker_boost": True,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    return out_path
