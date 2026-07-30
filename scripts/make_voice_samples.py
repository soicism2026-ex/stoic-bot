"""
Generate Chatterbox voice samples for the owner to judge by ear.

The benchmark produced 11.7s of audio for a 39-word script (~200 wpm), which is
fast for this channel's calm, meditative delivery — and possibly truncated. So
rather than ask "is this OK?", produce three variants of the SAME script and let
the owner pick:

  A_default   — the settings currently in tts.py (exaggeration 0.45, cfg 0.35)
  B_chunked   — same settings but synthesized sentence-by-sentence and joined.
                Guarantees the whole script is spoken and adds natural pauses.
  C_slow      — chunked + calmer settings, for the most deliberate read.

Writes MP3s (small, plays on any phone) to samples/.
"""
import os
import re
import sys
import time
from pathlib import Path

OUT_DIR = Path("samples")

TEXT = (
    "You reopened the app again tonight. Nothing changed except the hour. "
    "Epictetus knew that ceiling too. It is not events that disturb you, but "
    "your judgments about them. Put it down. Tomorrow is lighter than tonight "
    "makes it look."
)

VARIANTS = [
    # (name, exaggeration, cfg_weight, chunked, gap_seconds)
    ("A_default", 0.45, 0.35, False, 0.0),
    ("B_chunked", 0.45, 0.35, True,  0.25),
    ("C_slow",    0.35, 0.25, True,  0.40),
]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def main() -> int:
    import torch
    import torchaudio
    from chatterbox.tts import ChatterboxTTS

    OUT_DIR.mkdir(exist_ok=True)
    print(f"loading model on CPU (threads={torch.get_num_threads()})...", flush=True)
    model = ChatterboxTTS.from_pretrained(device="cpu")
    sr = model.sr
    words = len(TEXT.split())
    print(f"script: {words} words\n", flush=True)

    for name, exag, cfg, chunked, gap in VARIANTS:
        t0 = time.time()
        if chunked:
            pieces = []
            for s in _sentences(TEXT):
                wav = model.generate(s, exaggeration=exag, cfg_weight=cfg)
                pieces.append(wav)
                if gap > 0:
                    pieces.append(torch.zeros(1, int(sr * gap)))
            audio = torch.cat(pieces, dim=-1)
        else:
            audio = model.generate(TEXT, exaggeration=exag, cfg_weight=cfg)

        secs = audio.shape[-1] / sr
        wpm = words / (secs / 60) if secs else 0
        gen = time.time() - t0

        wav_path = OUT_DIR / f"{name}.wav"
        mp3_path = OUT_DIR / f"chatterbox_{name}.mp3"
        torchaudio.save(str(wav_path), audio, sr)
        os.system(f'ffmpeg -y -loglevel error -i "{wav_path}" -b:a 128k "{mp3_path}"')
        wav_path.unlink(missing_ok=True)

        print(f"{name:11} exag={exag} cfg={cfg} chunked={str(chunked):5} "
              f"-> {secs:5.1f}s audio  {wpm:5.0f} wpm  (gen {gen:.0f}s)", flush=True)

    print("\nwrote:", ", ".join(sorted(p.name for p in OUT_DIR.glob('*.mp3'))))
    print("Target for calm narration is roughly 120-150 wpm.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
