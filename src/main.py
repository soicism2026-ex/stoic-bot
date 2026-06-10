"""
Stoic Reels bot — daily orchestrator.

Flow:
  1. Claude API  -> pick a Stoic theme, write script + caption + hashtags
  2. ElevenLabs  -> voiceover MP3
  3. ffmpeg      -> render vertical 1080x1920 MP4 (quote text + bg video + voiceover)
  4. Metricool   -> upload & schedule the Reel
  5. analytics.py runs separately the next day to pull yesterday's numbers

Designed to be run once per day by GitHub Actions. Everything that can fail
is isolated into its own module so you swap one file, not the system.
"""
import os
import sys
import json
import datetime
from pathlib import Path

from content import generate_content
from tts import synthesize_voice
from render import render_reel
from publish import publish_short
from logbook import log_post

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)


def main():
    today = datetime.date.today().isoformat()
    print(f"[{today}] starting run")

    # 1. Content
    content = generate_content()
    print(f"  theme: {content['theme']}")
    print(f"  hook:  {content['hook']}")
    print(f"  quote: {content['quote'][:60]}...")

    # 2. Voiceover (+ per-word timings for karaoke captions). The hook is spoken
    #    first so the opening audio matches the on-screen hook card, then flows
    #    into the script. word_timings cover the combined line for the captions.
    hook = content["hook"].strip()
    spoken_text = f"{hook.rstrip('.!? ')}. {content['voiceover_text']}"
    audio_path = OUT / f"{today}_voice.mp3"
    audio_path, word_timings = synthesize_voice(spoken_text, audio_path)
    print(f"  voiceover -> {audio_path.name} ({len(word_timings)} word timings)")

    # 3. Render
    video_path = OUT / f"{today}_reel.mp4"
    render_reel(
        quote=content["quote"],
        author=content["author"],
        audio_path=audio_path,
        out_path=video_path,
        theme=content["theme"],
        word_timings=word_timings,
        hook=hook,
    )
    print(f"  rendered -> {video_path.name}")

    # 4. Publish to YouTube as a Short
    description = content["caption"] + "\n\n" + " ".join(content["hashtags"])
    title = f'{content["quote"][:70]} | {content["author"]}'
    result = publish_short(
        video_path=video_path,
        title=title,
        description=description,
        tags=content["hashtags"],
    )
    print(f"  published: {result.get('url', 'unknown')}")

    # 5. Log it
    log_post(
        date=today,
        theme=content["theme"],
        quote=content["quote"],
        author=content["author"],
        caption=description,
        publish_result=result,
    )
    print("  logged. done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"RUN FAILED: {e}", file=sys.stderr)
        sys.exit(1)
