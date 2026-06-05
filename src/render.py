"""
Render a 1080x1920 vertical Reel with ffmpeg.

Composition:
  - a looping public-domain background clip (assets/backgrounds/*.mp4),
    darkened so text reads
  - the quote text centered, wrapped
  - the author attribution beneath
  - the ElevenLabs voiceover as the audio track
  - output length = length of the voiceover

You drop a handful of slow, moody, royalty-free background clips into
assets/backgrounds/ once (Pexels Videos = free, no attribution). The bot
rotates through them by date so videos don't all look identical.
"""
import os
import json
import subprocess
import textwrap
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "backgrounds"
FONT = os.environ.get("REEL_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

W, H = 1080, 1920


def _audio_duration(audio_path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(audio_path),
    ])
    return float(json.loads(out)["format"]["duration"])


def _pick_background() -> Path:
    clips = sorted(BG_DIR.glob("*.mp4"))
    if not clips:
        raise FileNotFoundError(
            f"No background clips in {BG_DIR}. Drop a few royalty-free vertical "
            f"MP4s there (Pexels Videos)."
        )
    # rotate deterministically by day so it's varied but reproducible
    return clips[date.today().toordinal() % len(clips)]


def _escape(text: str) -> str:
    # escape for ffmpeg drawtext
    return (text.replace("\\", "\\\\").replace(":", "\\:")
                .replace("'", "\u2019").replace("%", "\\%"))


def render_reel(quote: str, author: str, audio_path: Path, out_path: Path) -> Path:
    dur = _audio_duration(audio_path) + 1.0  # small tail
    bg = _pick_background()

    wrapped = "\n".join(textwrap.wrap(quote, width=24))
    quote_txt = _escape(wrapped)
    author_txt = _escape(f"\u2014 {author}")

    # drawtext for quote (centered) and author (below center)
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"eq=brightness=-0.18:saturation=0.9,"
        f"drawtext=fontfile='{FONT}':text='{quote_txt}':"
        f"fontcolor=white:fontsize=68:line_spacing=14:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-80:"
        f"box=0:shadowcolor=black@0.6:shadowx=3:shadowy=3,"
        f"drawtext=fontfile='{FONT}':text='{author_txt}':"
        f"fontcolor=white@0.85:fontsize=44:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+220:"
        f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(bg),   # loop bg to cover audio length
        "-i", str(audio_path),
        "-t", f"{dur:.2f}",
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
