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
  - a scroll-stopping hook card flashed over the first couple seconds, then faded
  - the ElevenLabs voiceover as the audio track, with a synthesized attention
    "whoosh" mixed under the opening so the start grabs the ear as well as the eye
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

# Primary font: sans-serif for hook and captions (punchy, modern energy).
FONT = os.environ.get("REEL_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# Quote font: serif for a classical / stone-inscription feel matching Stoic aesthetics.
QUOTE_FONT = os.environ.get(
    "REEL_QUOTE_FONT",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
)

# Color palette — all env-overridable.
QUOTE_COLOR  = os.environ.get("REEL_QUOTE_COLOR",  "0xF0E6C8")  # warm parchment
AUTHOR_COLOR = os.environ.get("REEL_AUTHOR_COLOR", "0xC9A055")  # antique bronze/gold
DIVIDER_COLOR = os.environ.get("REEL_DIVIDER_COLOR", "0xA08040") # darker bronze for divider

# Karaoke caption controls (all optional, sensible defaults).
CAPTIONS_ON = os.environ.get("REEL_CAPTIONS", "1") not in ("0", "false", "False")
CAPTIONS_ONLY = os.environ.get("REEL_CAPTIONS_ONLY", "0") not in ("0", "false", "False")
CAPTION_FONT = os.environ.get("REEL_CAPTION_FONT", "DejaVu Sans")
CAPTION_FONTSIZE = int(os.environ.get("REEL_CAPTION_FONTSIZE", "64"))
CAPTION_MARGINV = int(os.environ.get("REEL_CAPTION_MARGINV", "180"))
CAPTION_MARGINL = int(os.environ.get("REEL_CAPTION_MARGINL", "150"))
CAPTION_MARGINR = int(os.environ.get("REEL_CAPTION_MARGINR", "150"))

# Hook controls — the scroll-stopping opener. A big text card flashes for the
# first few seconds and an attention "whoosh" sound is mixed under the start.
HOOK_TEXT_ON = os.environ.get("REEL_HOOK_TEXT", "1") not in ("0", "false", "False")
HOOK_SOUND_ON = os.environ.get("REEL_HOOK_SOUND", "1") not in ("0", "false", "False")
HOOK_HOLD = float(os.environ.get("REEL_HOOK_HOLD", "2.2"))      # seconds fully shown
HOOK_FONTSIZE = int(os.environ.get("REEL_HOOK_FONTSIZE", "94"))
HOOK_COLOR = os.environ.get("REEL_HOOK_COLOR", "0xFFB830")      # warm amber/gold

# Extra darkening on top of the date-rotated grade. Set by the QA retry loop
# (scripts/daily_post.py) when a render fails on text contrast.
EXTRA_DARKEN = float(os.environ.get("REEL_EXTRA_DARKEN", "0"))

# Hook sound preset — read from env, then data/hook_preset file, then default.
# Updated weekly by scripts/update_hook_sound.py.
# Presets: bass_impact | cinematic | whoosh | minimal
_HOOK_PRESET_FILE = ROOT / "data" / "hook_preset"
def _read_hook_preset() -> str:
    p = os.environ.get("REEL_HOOK_SOUND_PRESET", "").strip()
    if not p and _HOOK_PRESET_FILE.exists():
        p = _HOOK_PRESET_FILE.read_text(encoding="utf-8").strip()
    return p if p in ("bass_impact", "cinematic", "whoosh", "minimal") else "bass_impact"

W, H = 1080, 1920


def _audio_duration(audio_path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(audio_path),
    ])
    return float(json.loads(out)["format"]["duration"])


def _make_hook_sound(out_path: Path, dur: float = 1.3) -> Path:
    """Synthesize a hook attention sound entirely from ffmpeg lavfi sources.

    Preset selected by _read_hook_preset() (env → data/hook_preset file → default).

    bass_impact  — sub-bass punch + transient snap; dominates in modern motivation/
                   philosophy Shorts and is updated weekly from YouTube trend data.
    cinematic    — orchestral harmonic swell → dramatic hit; serious/philosophical.
    whoosh       — original pink-noise swell + low sine; broadly neutral.
    minimal      — clean struck tone + overtone; calm/educational aesthetic.
    """
    preset = _read_hook_preset()

    if preset == "cinematic":
        h1 = f"sine=frequency=65:duration={dur},volume='min(1,t/0.8)*0.45':eval=frame"
        h2 = f"sine=frequency=130:duration={dur},volume='min(0.9,t/0.6)*0.3':eval=frame"
        h3 = f"sine=frequency=195:duration={dur},volume='min(0.7,t/0.45)*0.18':eval=frame"
        texture = (
            f"anoisesrc=d={dur}:c=pink:a=0.35,"
            "bandpass=f=800:width_type=h:w=1600,"
            f"volume='min(0.4,t/0.9)':eval=frame"
        )
        hit = (
            f"sine=frequency=52:duration={dur},"
            f"volume='if(lt(t,0.02),t/0.02,max(0,1-(t-0.02)/0.65))':eval=frame"
        )
        fc = (
            f"{h1}[h1];{h2}[h2];{h3}[h3];{texture}[tx];{hit}[ht];"
            "[h1][h2][h3][tx][ht]amix=inputs=5:duration=longest,"
            f"afade=t=out:st={dur-0.3:.3f}:d=0.3,volume=2.4,alimiter=limit=0.95"
        )

    elif preset == "minimal":
        tone = (
            f"sine=frequency=880:duration={dur},"
            f"volume='if(lt(t,0.008),t/0.008,exp(-t*3.5))':eval=frame"
        )
        overtone = (
            f"sine=frequency=1760:duration={dur},"
            f"volume='if(lt(t,0.008),t/0.008,exp(-t*5.0))*0.28':eval=frame"
        )
        fc = (
            f"{tone}[t1];{overtone}[t2];"
            "[t1][t2]amix=inputs=2:duration=longest,"
            f"afade=t=out:st={dur-0.3:.3f}:d=0.3,volume=2.0,alimiter=limit=0.95"
        )

    elif preset == "whoosh":
        swell = (
            f"anoisesrc=d={dur}:c=pink:a=0.6,"
            "highpass=f=350,lowpass=f=6500,"
            f"volume='min(1,t/0.55)*max(0,1-(t-0.55)/{dur - 0.55:.3f})':eval=frame"
        )
        impact = (
            f"sine=frequency=85:duration={dur},"
            "volume='max(0,1-t/0.9)':eval=frame"
        )
        fc = (
            f"{swell}[wh];{impact}[im];"
            "[wh][im]amix=inputs=2:duration=longest,"
            f"afade=t=out:st={dur - 0.3:.3f}:d=0.3,volume=1.6"
        )

    else:  # "bass_impact" — default; most prevalent in viral motivation Shorts
        sweep = (
            f"anoisesrc=d={dur}:c=pink:a=0.65,"
            "bandpass=f=1200:width_type=h:w=2000,"
            f"volume='min(1,t/0.5)*max(0,1-(t-0.5)/0.2)':eval=frame"
        )
        bass = (
            f"sine=frequency=58:duration={dur},"
            f"volume='if(lt(t,0.04),t/0.04,max(0,1-(t-0.04)/0.72))':eval=frame"
        )
        snap = (
            f"anoisesrc=d={dur}:c=white:a=1.0,"
            "highpass=f=6000,lowpass=f=18000,"
            "volume='max(0,1.0-t/0.05)':eval=frame"
        )
        mid = (
            f"sine=frequency=116:duration={dur},"
            f"volume='if(lt(t,0.03),t/0.03,max(0,1-(t-0.03)/0.5))*0.35':eval=frame"
        )
        fc = (
            f"{sweep}[sw];{bass}[bs];{snap}[sn];{mid}[md];"
            "[sw][bs][sn][md]amix=inputs=4:duration=longest,"
            f"afade=t=out:st={dur-0.25:.3f}:d=0.25,volume=2.2,alimiter=limit=0.95"
        )

    subprocess.run(
        ["ffmpeg", "-y", "-filter_complex", fc, "-ar", "44100", "-ac", "2",
         str(out_path)],
        check=True, capture_output=True,
    )
    return out_path


def _mix_intro_sound(voice_path: Path, hook_path: Path, out_path: Path) -> Path:
    """Overlay the hook sound under the very start of the voiceover.

    Keeps the output as long as the voiceover (`duration=first`); the hook simply
    stops contributing once it ends. The voice stays dominant so the opening
    words remain clear. Returns the mixed audio path.
    """
    fc = (
        "[0:a]volume=1.0[v];[1:a]volume=0.8[h];"
        "[v][h]amix=inputs=2:duration=first:dropout_transition=0,"
        # restore the loudness amix's averaging removed, then hard-cap so the
        # overlap of a loud word and the whoosh can never clip.
        "volume=1.9,alimiter=limit=0.95[a]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(voice_path), "-i", str(hook_path),
         "-filter_complex", fc, "-map", "[a]",
         "-c:a", "aac", "-b:a", "192k", str(out_path)],
        check=True, capture_output=True,
    )
    return out_path


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


def _group_lines(word_timings: list, max_words: int = 2, pause: float = 0.55) -> list:
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

    # PrimaryColour = warm gold (active/spoken), SecondaryColour = parchment (upcoming).
    # ASS colors are &HAABBGGRR (alpha=00 is fully opaque, then blue, green, red).
    # #FFB830 (warm amber gold) → BGR: B=0x30, G=0xB8, R=0xFF → &H0030B8FF
    # #E8DCC8 (warm parchment)  → BGR: B=0xC8, G=0xDC, R=0xE8 → &H00C8DCE8
    primary = "&H0030B8FF"     # warm amber gold (active word)
    secondary = "&H00C8DCE8"   # warm parchment (upcoming words)
    outline = "&H00000000"     # black
    back = "&H80000000"        # shadow / box

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{CAPTION_FONT},{CAPTION_FONTSIZE},{primary},{secondary},{outline},{back},-1,0,0,0,100,100,0,0,1,4,3,2,{CAPTION_MARGINL},{CAPTION_MARGINR},{CAPTION_MARGINV},1

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
                theme: str = "", word_timings: list = None,
                hook: str = "") -> Path:
    # Mix an attention "whoosh" under the opening before anything else so the
    # rest of the pipeline just sees a normal audio track. Never let it break a
    # run: on any failure fall back to the raw voiceover.
    audio_for_render = audio_path
    if HOOK_SOUND_ON:
        try:
            hook_wav = Path(out_path).with_suffix(".hook.wav")
            mixed = Path(out_path).with_suffix(".mix.m4a")
            _make_hook_sound(hook_wav)
            _mix_intro_sound(audio_path, hook_wav, mixed)
            audio_for_render = mixed
        except Exception as e:  # noqa: BLE001
            print(f"  hook sound unavailable ({e}); using plain voiceover")

    dur = _audio_duration(audio_for_render) + 1.0  # small tail

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

    # slow Ken Burns push-in over the clip's frames.
    # NOTE: zoompan with d>1 on a *video* input holds each input frame for d
    # frames, which freezes the background on its first frame for the whole
    # Short. Use d=1 (one output frame per input frame, so the clip keeps
    # playing) and drive the zoom off `on` (the running output-frame index)
    # rather than self-referencing `zoom`, which does not accumulate when d=1.
    total_frames = max(1, int(dur * 30))
    zoom_inc = 0.15 / total_frames  # reach ~1.15x by the end of the clip
    zoompan = (
        f"zoompan=z='min(1.0+{zoom_inc:.6f}*on,1.15)':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30"
    )

    vf_parts = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        zoompan,
        f"eq=brightness={br - EXTRA_DARKEN}:saturation={sat}:contrast={con}",
    ]

    if show_quote:
        # Fade the quote in as the hook fades out so only one primary text is
        # on screen at a time. If no hook is shown, appear from the start.
        if hook and HOOK_TEXT_ON:
            hook_fade = 0.4
            quote_appear = HOOK_HOLD          # start fading in when hook starts fading
            quote_fade_dur = hook_fade + 0.2  # slightly longer for a softer entrance
            quote_alpha = f"min(1,max(0,(t-{quote_appear})/{quote_fade_dur:.2f}))"
        else:
            quote_alpha = "1"

        # Quote lines — serif font, warm parchment color.
        for i, line in enumerate(quote_lines):
            offset = i * LINE_H - half_block
            line_y = f"{center_expr}{offset:+d}"
            vf_parts.append(
                f"drawtext=fontfile='{_escape_filter_path(Path(QUOTE_FONT))}':"
                f"text='{_escape(line)}':"
                f"fontcolor={QUOTE_COLOR}:fontsize={QUOTE_FONTSIZE}:"
                f"x=(w-text_w)/2:y={line_y}:"
                f"box=0:shadowcolor=black@0.85:shadowx=4:shadowy=4:"
                f"alpha='{quote_alpha}'"
            )

        # Thin gold divider line between quote block and author.
        divider_y = f"{center_expr}+{half_block + 18}"
        vf_parts.append(
            f"drawbox=x=(w-240)/2:y={divider_y}:w=240:h=2:"
            f"color={DIVIDER_COLOR}@0.85:t=fill"
        )

        # Author — antique bronze, all-caps, slightly smaller than quote.
        author_upper = _escape(f"— {author.upper()}")
        vf_parts.append(
            f"drawtext=fontfile='{_escape_filter_path(Path(QUOTE_FONT))}':"
            f"text='{author_upper}':"
            f"fontcolor={AUTHOR_COLOR}:fontsize=38:"
            f"x=(w-text_w)/2:y={author_y}:"
            f"shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            f"alpha='{quote_alpha}'"
        )

    # Hook card: big, bold, scroll-stopping text flashed over the opening, then
    # faded out so the clean quote is what remains. Drawn after the quote so it
    # sits on top during those first seconds.
    if hook and HOOK_TEXT_ON:
        hook_lines = textwrap.wrap(hook.upper(), width=15) or [hook.upper()]
        HOOK_LINE_H = HOOK_FONTSIZE + 18
        h_half = (len(hook_lines) * HOOK_LINE_H) // 2
        fade = 0.4  # seconds to fade the card out after HOOK_HOLD
        for i, line in enumerate(hook_lines):
            offset = i * HOOK_LINE_H - h_half
            line_y = f"(h/2)-150{offset:+d}"
            vf_parts.append(
                f"drawtext=fontfile='{FONT}':text='{_escape(line)}':"
                f"fontcolor={HOOK_COLOR}:fontsize={HOOK_FONTSIZE}:"
                f"x=(w-text_w)/2:y={line_y}:"
                f"borderw=7:bordercolor=black@0.9:"
                f"shadowcolor=black@0.7:shadowx=3:shadowy=3:"
                f"alpha='if(lt(t,{HOOK_HOLD}),1,max(0,1-(t-{HOOK_HOLD})/{fade}))':"
                f"enable='lt(t,{HOOK_HOLD + fade})'"
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
        "-i", str(audio_for_render),
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
