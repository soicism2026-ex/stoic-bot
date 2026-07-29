---
name: preview-short
description: Render a test Short locally and show the owner frames before anything is published — for checking look, text placement, captions, safe zones, grade, or any visual/audio change. Use after changing render.py, captions, grade, backgrounds, music, or when the owner asks what will this look like, show me, or gives visual feedback that needs verifying.
---

# Preview a short before it ships

The owner judges with their eyes and ears, and they have caught real bugs I
missed (cut-off hook text, captions colliding with the hook, a voice they hated).
Every visual change should be shown as a **frame**, not described in prose — and
verified through the phone crop, because that's where things actually break.

## Render a test short

ffmpeg may be missing after a container refresh:
```bash
which ffmpeg || (apt-get update -qq && apt-get install -y ffmpeg -qq)
```

```bash
D=/tmp/claude-0/*/scratchpad/rtest && mkdir -p $D && cd $D
ffmpeg -y -f lavfi -i "sine=frequency=300:duration=18" -filter:a volume=0.5 \
  -c:a libmp3lame voice.mp3 2>/dev/null   # stand-in voiceover

export REEL_X264_PRESET=ultrafast REEL_CRF=30      # fast preview, not final quality
export PIXABAY_API_KEY="" PEXELS_API_KEY=""        # offline → synthetic backgrounds
export REEL_CINEMATIC=1 REEL_BG_CLIPS=6

python3 - <<'PY'
import sys; sys.path.insert(0,"/home/user/stoic-bot/src")
from pathlib import Path
import render
wt=[]; t=1.0
for w in "The obstacle in the path becomes the path".split():
    wt.append((w,t,t+0.4)); t+=0.45
render.render_reel(quote="The impediment to action advances action.",
    author="Marcus Aurelius", audio_path=Path("voice.mp3"),
    out_path=Path("preview.mp4"), theme="discipline", word_timings=wt,
    hook="The obstacle is the way.", callout_words=[], music_path=None,
    mission="DAY 50 · UNTIL DISCIPLINE IS COOL AGAIN")
PY
```

## ALWAYS check through the iPhone crop

iPhones are ~19.5:9 — narrower than 9:16 — so the Shorts player **crops ~120px
off each side**. Text that looks fine full-frame gets cut on device (this is
exactly how "MEET WHAT COMES" once shipped as "EET WHAT COME"). Judge the
cropped frame, not the raw one:

```bash
ffmpeg -y -ss 5.5 -i preview.mp4 -vf "crop=840:1920:120:0" -vframes 1 frame.png
```

Sample multiple moments — the hook window (~t=1-2s), the steady state (~t=4-6s),
and a late caption (~t=10s) — since collisions only appear at specific times.

Then **Read the PNG** to inspect it yourself, and **SendUserFile** it so the owner
can judge. Say plainly that a black/flat background is the offline synthetic
placeholder; production pulls real footage.

## Check the audio too

```bash
ffprobe -v error -show_entries stream=codec_type -of csv=p=0 preview.mp4   # audio present?
ffmpeg -ss 6 -t 4 -i preview.mp4 -af volumedetect -f null - 2>&1 | grep mean_volume
```
Target ≈ -14 LUFS (mean roughly -12 to -16 dB). Around -91 dB means silence —
a shipped silent video is the worst possible failure.

## Caveat honestly

A local preview uses synthetic backgrounds and a tone instead of the real voice,
so it proves **layout, timing, safe zones and loudness** — not the final look of
graded stock footage. Say which of those the frame actually settles.
