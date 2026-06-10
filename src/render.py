"""
Render a 1080x1920 vertical Reel with ffmpeg.

Composition:
  - a fresh, theme-matched background clip fetched from Pexels each day
    (backgrounds.fetch_background), darkened so text reads; falls back to a
    local clip in assets/backgrounds/ if Pexels is unavailable
  - the quote text (position + color grading rotate by date so days don't
    look identical), wrapped
  - the author attribution beneath
  - a slow Ken Burns push-in (zoompan) for subtle motion
  - the ElevenLabs voiceover as the audio track
  - output length = length of the voiceover
"""
import os
import json
import subprocess
import textwrap
from pathlib import Path
from datetime import date

from backgrounds import fetch_background

ROOT = Path(__file__).resolve().parent.parent
FONT = os.environ.get("REEL_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

W, H = 1080, 1920


def _audio_duration(audio_path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(audio_path),
    ])
    return float(json.loads(out)["format"]["duration"])


def _escape(text: str) -> str:
    # escape for ffmpeg drawtext
    return (text.replace("\\", "\\\\").replace(":", "\\:")
                .replace("'", "’").replace("%", "\\%"))


# Color-grade presets rotated by date (brightness, saturation, contrast).
_GRADES = [
    (-0.18, 0.90, 1.00),
    (-0.22, 0.75, 1.08),
    (-0.15, 1.05, 1.04),
    (-0.25, 0.85, 1.12),
]


def render_reel(quote: str, author: str, audio_path: Path, out_path: Path,
                theme: str = "") -> Path:
    dur = _audio_duration(audio_path) + 1.0  # small tail

    # fresh Pexels clip (theme-matched) with safe local fallback
    bg_path = Path(out_path).with_suffix(".bg.mp4")
    bg = fetch_background(theme, bg_path)

    wrapped = "\n".join(textwrap.wrap(quote, width=24))
    quote_txt = _escape(wrapped)
    author_txt = _escape(f"— {author}")

    day = date.today().toordinal()

    # vary text vertical position: 0 -> centered, 1 -> upper third
    upper_third = (day % 2) == 1
    if upper_third:
        quote_y = "h/3-text_h/2"
        author_y = "h/3+text_h/2+90"
    else:
        quote_y = "(h-text_h)/2-80"
        author_y = "(h-text_h)/2+220"

    # vary color grading by date
    br, sat, con = _GRADES[day % len(_GRADES)]

    # slow Ken Burns push-in over the clip's frames
    total_frames = max(1, int(dur * 30))
    zoompan = (
        f"zoompan=z='min(zoom+0.0008,1.15)':d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30"
    )

    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"{zoompan},"
        f"eq=brightness={br}:saturation={sat}:contrast={con},"
        f"drawtext=fontfile='{FONT}':text='{quote_txt}':"
        f"fontcolor=white:fontsize=68:line_spacing=14:"
        f"x=(w-text_w)/2:y={quote_y}:"
        f"box=0:shadowcolor=black@0.6:shadowx=3:shadowy=3,"
        f"drawtext=fontfile='{FONT}':text='{author_txt}':"
        f"fontcolor=white@0.85:fontsize=44:"
        f"x=(w-text_w)/2:y={author_y}:"
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
