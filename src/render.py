"""
Render a 1080x1920 vertical Reel with ffmpeg.

Composition:
  - a fresh, theme-matched background clip fetched from Pexels each day
    (backgrounds.fetch_background), darkened so text reads; falls back to a
    local clip in assets/backgrounds/ if Pexels is unavailable
  - the quote text (position + color grading rotate by date so days don't
    look identical), wrapped
  - the author attribution beneath
  - word-synced karaoke captions burned in across the lower-middle: 1-4 words
    at a time, the active word swept from soft white to amber as it is spoken
    (driven by the per-word timings from tts.synthesize_voice)
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

# Karaoke caption controls (all optional, sensible defaults).
CAPTIONS_ON = os.environ.get("REEL_CAPTIONS", "1") not in ("0", "false", "False")
CAPTIONS_ONLY = os.environ.get("REEL_CAPTIONS_ONLY", "0") not in ("0", "false", "False")
CAPTION_FONT = os.environ.get("REEL_CAPTION_FONT", "DejaVu Sans")
CAPTION_FONTSIZE = int(os.environ.get("REEL_CAPTION_FONTSIZE", "74"))
CAPTION_MARGINV = int(os.environ.get("REEL_CAPTION_MARGINV", "470"))

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


def _escape_filter_path(p: Path) -> str:
    # escape a path for use inside an ffmpeg filter argument
    s = str(p)
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


# Color-grade presets rotated by date (brightness, saturation, contrast).
_GRADES = [
    (-0.18, 0.90, 1.00),
    (-0.22, 0.75, 1.08),
    (-0.15, 1.05, 1.04),
    (-0.25, 0.85, 1.12),
]


def _ass_time(t: float) -> str:
    """Seconds -> ASS H:MM:SS.cc (centiseconds)."""
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _group_lines(word_timings: list, max_words: int = 4, pause: float = 0.55) -> list:
    """Group (word, start, end) into caption lines of 1-max_words words.

    Breaks on: reaching max_words, a silence gap > `pause` before the next word,
    or sentence-ending punctuation. Each returned line is a list of timings.
    """
    lines = []
    cur = []
    for i, wt in enumerate(word_timings):
        cur.append(wt)
        word = wt[0]
        end = wt[2]
        nxt_start = word_timings[i + 1][1] if i + 1 < len(word_timings) else None
        gap = (nxt_start - end) if nxt_start is not None else 0.0
        ends_sentence = word.rstrip()[-1:] in ".!?…:;" if word.strip() else False
        if len(cur) >= max_words or gap > pause or ends_sentence:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def _build_ass(word_timings: list, out_path: Path) -> Path:
    """Write a karaoke .ass file for the given word timings. Returns the path."""
    lines = _group_lines(word_timings)

    # PrimaryColour = amber (active/spoken), SecondaryColour = soft white (upcoming).
    # ASS colors are &HAABBGGRR (alpha, blue, green, red).
    primary = "&H0020C0FF"     # amber
    secondary = "&H00F5F5F5"   # soft white
    outline = "&H00000000"     # black
    back = "&H80000000"        # shadow / box

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{CAPTION_FONT},{CAPTION_FONTSIZE},{primary},{secondary},{outline},{back},-1,0,0,0,100,100,0,0,1,4,3,2,90,90,{CAPTION_MARGINV},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for line in lines:
        start = line[0][1]
        end = line[-1][2]
        parts = []
        for j, (word, w_start, w_end) in enumerate(line):
            # Hold the highlight until the next word begins so the sweep tracks
            # the voice; last word uses its own end.
            nxt = line[j + 1][1] if j + 1 < len(line) else w_end
            dur_cs = max(1, int(round((nxt - w_start) * 100)))
            parts.append(f"{{\\kf{dur_cs}}}{_ass_escape(word)} ")
        text = "".join(parts).rstrip()
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Karaoke,,0,0,0,,{text}"
        )

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def render_reel(quote: str, author: str, audio_path: Path, out_path: Path,
                theme: str = "", word_timings: list = None) -> Path:
    dur = _audio_duration(audio_path) + 1.0  # small tail

    # fresh Pexels clip (theme-matched) with safe local fallback
    bg_path = Path(out_path).with_suffix(".bg.mp4")
    bg = fetch_background(theme, bg_path)

    quote_lines = textwrap.wrap(quote, width=24) or [quote]
    author_txt = _escape(f"— {author}")

    day = date.today().toordinal()

    # When captions occupy the lower-middle, lift the quote card up so they don't
    # collide; otherwise keep the original date-varied placement.
    show_quote = not (CAPTIONS_ONLY and word_timings)
    caption_band = bool(word_timings) and CAPTIONS_ON

    # vary text vertical position: 0 -> centered, 1 -> upper third
    upper_third = (day % 2) == 1
    # When captions occupy the lower-middle, park the quote/author in the upper
    # third to clear the caption band; otherwise keep the date-varied placement.
    if caption_band or upper_third:
        center_expr = "h/3"
    else:
        center_expr = "(h/2)-80"

    # Render the quote as one drawtext per wrapped line with explicit, deterministic
    # Y offsets. Passing the wrapped quote to a single drawtext with embedded "\n"
    # is unreliable across ffmpeg builds (the newlines collapse and the lines draw
    # on top of each other), so we lay each line out ourselves around center_expr.
    QUOTE_FONTSIZE = 68
    LINE_H = QUOTE_FONTSIZE + 22  # font height + line spacing
    n_lines = len(quote_lines)
    half_block = (n_lines * LINE_H) // 2
    author_y = f"{center_expr}+{half_block + 40}"

    # vary color grading by date
    br, sat, con = _GRADES[day % len(_GRADES)]

    # slow Ken Burns push-in over the clip's frames
    total_frames = max(1, int(dur * 30))
    zoompan = (
        f"zoompan=z='min(zoom+0.0008,1.15)':d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30"
    )

    vf_parts = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        zoompan,
        f"eq=brightness={br}:saturation={sat}:contrast={con}",
    ]

    if show_quote:
        for i, line in enumerate(quote_lines):
            offset = i * LINE_H - half_block
            line_y = f"{center_expr}{offset:+d}"
            vf_parts.append(
                f"drawtext=fontfile='{FONT}':text='{_escape(line)}':"
                f"fontcolor=white:fontsize={QUOTE_FONTSIZE}:"
                f"x=(w-text_w)/2:y={line_y}:"
                f"box=0:shadowcolor=black@0.6:shadowx=3:shadowy=3"
            )
        vf_parts.append(
            f"drawtext=fontfile='{FONT}':text='{author_txt}':"
            f"fontcolor=white@0.85:fontsize=44:"
            f"x=(w-text_w)/2:y={author_y}:"
            f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
        )

    # burn in karaoke captions last so they sit on top
    ass_path = None
    if caption_band:
        ass_path = Path(out_path).with_suffix(".captions.ass")
        _build_ass(word_timings, ass_path)
        vf_parts.append(f"ass='{_escape_filter_path(ass_path)}'")

    vf = ",".join(vf_parts)

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
