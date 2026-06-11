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
    #    first; the CTA is appended at the end for the reason-based follow hook.
    hook = content["hook"].strip()
    cta = content.get("cta", "").strip()
    spoken_text = f"{hook.rstrip('.!? ')}. {content['voiceover_text']}"
    if cta:
        spoken_text = f"{spoken_text} {cta}"
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

    # 4. Publish to YouTube as a Short — with series framing in title/description.
    day = content.get("day_number", "")
    day_prefix = f"Day {day} | " if day else ""
    title = f'{day_prefix}{content["quote"][:55]} — {content["author"]}'[:90].rstrip()
    description = (
        (f"Day {day} of daily Stoic wisdom.\n\n" if day else "")
        + content["caption"]
        + "\n\n"
        + " ".join(content["hashtags"])
    )
    result = publish_short(
        video_path=video_path,
        title=title,
        description=description,
        tags=content["hashtags"],
    )
    print(f"  published: {result.get('url', 'unknown')}")

    # 4b. Post engagement comment (pinnable from YouTube Studio)
    pinned_q = content.get("pinned_comment", "").strip()
    if pinned_q and result.get("video_id"):
        try:
            from publish import post_comment
            post_comment(result["video_id"], pinned_q)
        except Exception as e:
            print(f"  [comment] skipped: {e}", file=sys.stderr)

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
