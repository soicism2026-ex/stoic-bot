"""
Backfill flashy thumbnails + hook-first titles onto already-published Shorts.

For every unique video in data/posts.csv:
  1. generate a 3-5 word Stoic hook from the stored quote/author/theme
  2. set the title to   "<hook>" — <author> | Stoicism
  3. fetch a theme-matched background, render the gold-hook thumbnail, upload it

Design notes:
  - Self-contained: hook generation (Anthropic) and the in-place title update
    (videos.update) live here rather than in the library modules, so this runs
    against the current `main` without needing other source changes.
  - Each video is independent: a failure in hook / title / thumbnail logs and
    moves on — it never aborts the batch.
  - Backgrounds are varied per video via REEL_BG_OFFSET so two videos sharing a
    theme don't get an identical frame.
  - Safe to re-run: a title that already matches is skipped.

Run via the backfill workflow (workflow_dispatch) so it has the YouTube +
Anthropic + stock-footage secrets. It changes title/thumbnail only — it never
uploads a new video.
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from backgrounds import fetch_background      # noqa: E402 (after sys.path)
from render import generate_thumbnail         # noqa: E402
from publish import set_thumbnail, _service   # noqa: E402

POSTS = ROOT / "data" / "posts.csv"
WORK = ROOT / "data" / "_backfill"
MODEL = "claude-opus-4-8"
FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"

HOOK_SYSTEM = """You write the on-screen HOOK for a faceless Stoicism YouTube \
Short. Given a real Stoic quote, return ONE hook and nothing else.

The hook is 3-5 words: a blunt, second-person accusation or uncomfortable truth \
— not a question, not an inspirational phrase, not a summary. It must make the \
viewer feel personally called out the instant it appears. It sets up the quote's \
idea WITHOUT quoting or restating the passage. No author name, no quotation marks, \
no hashtags, no ellipsis, no trailing period.

RIGHT register (models — do NOT copy verbatim): "You're wasting your life." / \
"Your ego is the problem." / "You chose this." / "Nothing lasts." / \
"You already know." / "Stop performing discipline." / "You're running from yourself." / \
"The clock is running." / "You call that discipline."
WRONG register (avoid): "Time is precious." (cliche) / "What's holding you back?" \
(too soft) / "Wisdom from Marcus Aurelius." (never name the author) / anything \
that sounds like an introduction.

Respond with ONLY the hook text — no JSON, no quotes, no preamble."""


def generate_hook(quote: str, author: str, theme: str) -> str:
    """3-5 word scroll-stopping hook for an existing quote, via Anthropic."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=MODEL,
        max_tokens=40,
        temperature=1.0,
        system=HOOK_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Theme: {theme}\nAuthor: {author}\nQuote: \"{quote}\"\n\n"
                f"Write the hook."
            ),
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    # Strip any stray wrapping quotes / trailing punctuation the model may add.
    return text.strip().strip('"').strip("'").rstrip(".!?").strip()


def update_video_title(video_id: str, title: str) -> bool:
    """Swap a published video's title in place, preserving its other snippet
    fields. videos.update replaces the whole `snippet` part (categoryId is
    required), so fetch the current snippet first and change only the title.
    Requires force-ssl scope. Idempotent: skips a title that already matches."""
    try:
        yt = _service(extra_scopes=[FORCE_SSL])
        resp = yt.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            print(f"  [title] {video_id} not found / not owned", file=sys.stderr)
            return False
        snippet = items[0]["snippet"]
        if snippet.get("title") == title:
            print(f"  [title] {video_id} already set — skipping")
            return True
        snippet["title"] = title[:100]
        yt.videos().update(
            part="snippet", body={"id": video_id, "snippet": snippet}
        ).execute()
        print(f"  [title] updated {video_id}: {title}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [title] update failed for {video_id}: {e}", file=sys.stderr)
        return False


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

        try:
            hook = generate_hook(quote, author, theme)
        except Exception as e:  # noqa: BLE001
            print(f"  [hook] generation failed: {e}", file=sys.stderr)
            continue
        if not hook:
            print("  [hook] empty result — skipping video", file=sys.stderr)
            continue
        print(f"  hook: {hook}", flush=True)

        # Title — mirror daily_post.py's format exactly.
        hook_clean = hook.rstrip(".!? ")
        title = f'"{hook_clean}" — {author} | Stoicism'[:90].rstrip()
        if update_video_title(vid, title):
            ok_title += 1

        # Thumbnail — fresh theme background (varied per video), gold hook card.
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
