"""
Backfill flashy thumbnails + hook-first titles onto already-published Shorts.

For every unique video in data/posts.csv:
  1. generate a 3-5 word Stoic hook from the stored quote/author/theme
  2. set the title to   "<hook>" — <author> | Stoicism
  3. fetch a theme-matched background, render the gold-hook thumbnail, upload it

Design:
  - Each video is independent: one failure (hook, title, or thumbnail) never
    aborts the batch — it logs and moves on.
  - Backgrounds are varied per video via REEL_BG_OFFSET so two videos sharing a
    theme don't get an identical frame.
  - Safe to re-run: update_video_title() skips a video whose title already matches.

Run via the backfill workflow (workflow_dispatch) so it has the YouTube +
Anthropic + stock-footage secrets. Publishes only title/thumbnail changes —
it never uploads a new video.
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from content import generate_hook            # noqa: E402 (after sys.path)
from backgrounds import fetch_background      # noqa: E402
from render import generate_thumbnail         # noqa: E402
from publish import set_thumbnail, update_video_title  # noqa: E402

POSTS = ROOT / "data" / "posts.csv"
WORK = ROOT / "data" / "_backfill"


def main() -> int:
    if not POSTS.exists():
        print(f"posts.csv not found at {POSTS}", file=sys.stderr)
        return 1

    with open(POSTS, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    WORK.mkdir(parents=True, exist_ok=True)

    total = ok_title = ok_thumb = 0
    seen: set[str] = set()

    for idx, row in enumerate(rows):
        vid = (row.get("video_id") or "").strip()
        if not vid or vid in seen:
            continue
        seen.add(vid)
        total += 1

        quote = (row.get("quote") or "").strip()
        author = (row.get("author") or "").strip()
        theme = (row.get("theme") or "").strip()
        print(f"\n=== {vid}  [{author} / {theme}] ===", flush=True)

        # 1) hook
        try:
            hook = generate_hook(quote, author, theme)
        except Exception as e:  # noqa: BLE001
            print(f"  [hook] generation failed: {e}", file=sys.stderr)
            continue
        if not hook:
            print("  [hook] empty result — skipping video", file=sys.stderr)
            continue
        print(f"  hook: {hook}", flush=True)

        # 2) title — mirror daily_post.py's format exactly
        hook_clean = hook.rstrip(".!? ")
        title = f'"{hook_clean}" — {author} | Stoicism'[:90].rstrip()
        if update_video_title(vid, title):
            ok_title += 1

        # 3) thumbnail — fresh theme background (varied per video), gold hook card
        try:
            os.environ["REEL_BG_OFFSET"] = str(idx)  # vary clip per video
            bg = fetch_background(theme, WORK / f"{vid}.bg.mp4")
            thumb = generate_thumbnail(
                hook=hook, author=author, bg_path=bg,
                out_path=WORK / f"{vid}.thumb.jpg",
            )
            if thumb and Path(thumb).exists() and set_thumbnail(vid, thumb):
                ok_thumb += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [thumbnail] failed: {e}", file=sys.stderr)

    print(
        f"\nDone. videos: {total} | titles updated: {ok_title} | "
        f"thumbnails set: {ok_thumb}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
