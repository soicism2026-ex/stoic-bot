"""
Render a 1080x1920 vertical Reel with ffmpeg.

Composition:
  - a looping public-domain background clip (assets/backgrounds/*.mp4),
    darkened so text reads
  - the quote text centered, wrapped (the brand card)
  - the author attribution beneath
  - word-synced karaoke captions across the lower-middle, advancing with the
    voiceover (the spoken script, highlighted word-by-word)
  - the ElevenLabs voiceover as the audio track
  - output length = length of the voiceover

You drop a handful of slow, moody, royalty-free background clips into
assets/backgrounds/ once (Pexels Videos = free, no attribution). The bot
rotates through them by date so videos don't all look identical.

Design choice: captions are shown *in addition* to the quote/author card (the
issue is "audio and text simultaneously"). The canonical quote+author stays as
the brand card; the spoken script drives the karaoke line below it. Set
REEL_CAPTIONS_ONLY=1 to hide the static quote card for a captions-only look.
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

# Caption controls (all optional).
CAPTIONS = os.environ.get("REEL_CAPTIONS", "1") not in ("0", "false", "False")
CAPTIONS_ONLY = os.environ.get("REEL_CAPTIONS_ONLY", "0") not in ("0", "false", "False")
CAPTION_FONT = os.environ.get("REEL_CAPTION_FONT", "DejaVu Sans")
CAPTION_FONTSIZE = int(os.environ.get("REEL_CAPTION_FONTSIZE", "72"))

W, H = 1080, 1920

# Max words shown on one caption line, and the gap (seconds) that forces a new line.
_MAX_WORDS_PER_LINE = 4
_PAUSE_BREAK = 0.45


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
                .replace("'", "’").replace("%", "\\%"))


# ---------------------------------------------------------------------------
# Karaoke captions (ASS / libass)
# ---------------------------------------------------------------------------

def _ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_text_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _group_words(word_timings, max_words=_MAX_WORDS_PER_LINE, pause=_PAUSE_BREAK):
    """Group words into caption lines of up to `max_words`, breaking on pauses."""
    groups, cur = [], []
    prev_end = None
    for word, start, end in word_timings:
        if cur and (len(cur) >= max_words or (prev_end is not None and start - prev_end >= pause)):
            groups.append(cur)
            cur = []
        cur.append((word, start, end))
        prev_end = end
    if cur:
        groups.append(cur)
    return groups


def _build_ass(word_timings, out_path: Path) -> Path:
    """Write an ASS subtitle file with per-word karaoke highlighting."""
    margin_v = int(os.environ.get("REEL_CAPTION_MARGINV", "360"))  # px from bottom -> lower-middle band
    # ASS colour = &HAABBGGRR (alpha inverted: 00 = opaque).
    # Karaoke sweeps text from SecondaryColour (not yet spoken) to PrimaryColour (spoken).
    primary = "&H0000BFFF"     # amber (spoken)
    secondary = "&H00EBEBEB"   # soft white (not yet spoken)
    outline = "&H00000000"     # black outline
    back = "&H64000000"        # translucent black shadow

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{CAPTION_FONT},{CAPTION_FONTSIZE},{primary},{secondary},{outline},{back},-1,0,0,0,100,100,0,0,1,4,3,2,90,90,{margin_v},1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = []
    for group in _group_words(word_timings):
        g_start = group[0][1]
        g_end = group[-1][2]
        # \kf<cs> sweeps each word over its own duration (centiseconds).
        chunks = []
        for word, start, end in group:
            dur_cs = max(1, int(round((end - start) * 100)))
            chunks.append(f"{{\\kf{dur_cs}}}{_ass_text_escape(word)}")
        text = " ".join(chunks)
        lines.append(
            f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},Caption,,0,0,0,,{text}"
        )

    ass_path = out_path.with_suffix(".ass")
    ass_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return ass_path


def _ass_filter_path(ass_path: Path) -> str:
    # Escape the path for use inside an ffmpeg filtergraph value.
    p = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return p


def render_reel(quote: str, author: str, audio_path: Path, out_path: Path,
                word_timings=None) -> Path:
    dur = _audio_duration(audio_path) + 1.0  # small tail
    bg = _pick_background()

    wrapped = "\n".join(textwrap.wrap(quote, width=24))
    quote_txt = _escape(wrapped)
    author_txt = _escape(f"— {author}")

    use_captions = CAPTIONS and word_timings
    # When captions are on, nudge the quote card up to clear the caption band.
    quote_y = "(h-text_h)/2-260" if use_captions else "(h-text_h)/2-80"
    author_y = "(h-text_h)/2-30" if use_captions else "(h-text_h)/2+220"

    filters = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        "eq=brightness=-0.18:saturation=0.9",
    ]

    if not (use_captions and CAPTIONS_ONLY):
        filters.append(
            f"drawtext=fontfile='{FONT}':text='{quote_txt}':"
            f"fontcolor=white:fontsize=68:line_spacing=14:"
            f"x=(w-text_w)/2:y={quote_y}:"
            f"box=0:shadowcolor=black@0.6:shadowx=3:shadowy=3"
        )
        filters.append(
            f"drawtext=fontfile='{FONT}':text='{author_txt}':"
            f"fontcolor=white@0.85:fontsize=44:"
            f"x=(w-text_w)/2:y={author_y}:"
            f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
        )

    if use_captions:
        ass_path = _build_ass(word_timings, out_path)
        filters.append(f"ass={_ass_filter_path(ass_path)}")

    vf = ",".join(filters)

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
