"""
Content generation via the Anthropic API.

Asks Claude for one day's Stoic Reel: a real public-domain quote (Marcus
Aurelius / Seneca / Epictetus), a short voiceover script, an engagement
caption, and hashtags. Returns structured JSON.

Repeats are prevented by reading posts.csv and injecting previously used
quotes into the prompt. Author and theme are deterministically rotated by
calendar day so the feed never fixates on one voice or idea.
"""
import csv
import datetime
import json
import os
from pathlib import Path

import anthropic

from logbook import classify_title_style

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-opus-4-8"

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posts.csv"
ANALYTICS = ROOT / "data" / "analytics.csv"

# Only start steering on performance once we have enough measured posts that the
# top/bottom signal isn't just noise.
MIN_MEASURED_POSTS = 14

AUTHORS = ["Marcus Aurelius", "Seneca", "Epictetus"]
THEMES = [
    "discipline",
    "mortality/memento mori",
    "control vs acceptance",
    "anger",
    "desire",
    "resilience",
    "time",
    "ego",
]

SYSTEM = """You are the content engine for a faceless Stoicism Instagram Reels \
account. Your job is to produce ONE short-form video script per call.

Rules:
- Use only genuine, public-domain Stoic material: Marcus Aurelius (Meditations), \
Seneca (Letters/essays), Epictetus (Discourses, Enchiridion). Do not fabricate quotes.
- The quote must be punchy and fit on screen in under ~25 words. Lightly modernized \
phrasing of a real passage is fine; attribute to the correct author.
- Voiceover script: 18-35 seconds spoken (~45-90 words). Open with a hook in the \
first line. Plain, grounded, masculine-neutral tone. No hashtags in the voiceover.
- Caption: 1-2 sentences that reframe the idea for daily life + one soft question \
to drive comments.
- Hashtags: 8-12, mixing broad (#stoicism #discipline) and mid-size niche tags.

Respond with ONLY valid JSON, no markdown, no preamble, in this exact shape:
{
  "theme": "...",
  "quote": "...",
  "author": "Marcus Aurelius | Seneca | Epictetus",
  "voiceover_text": "...",
  "caption": "...",
  "hashtags": ["#...", "..."]
}"""


def _load_used_quotes() -> list[str]:
    if not LOG.exists():
        return []
    with open(LOG, newline="", encoding="utf-8") as f:
        return [row["quote"] for row in csv.DictReader(f) if row.get("quote")]


def _pick_rotation() -> tuple[str, str]:
    day = datetime.date.today().toordinal()
    return AUTHORS[day % len(AUTHORS)], THEMES[day % len(THEMES)]


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _max_views_by_video() -> dict[str, int]:
    """Latest/peak view count per video_id from analytics.csv.

    analytics.csv is append-only (one row per pull), so a video shows up many
    times; we keep its highest observed view count.
    """
    out: dict[str, int] = {}
    for row in _read_csv(ANALYTICS):
        vid = row.get("video_id")
        if not vid:
            continue
        try:
            views = int(row.get("views") or 0)
        except ValueError:
            continue
        out[vid] = max(out.get(vid, 0), views)
    return out


def _performance_insights() -> str:
    """Join posts.csv with analytics.csv and summarise what's working.

    Returns a prompt fragment nudging toward the themes/authors/title styles of
    top performers and away from bottom performers. Returns "" (skip silently)
    until we have at least MIN_MEASURED_POSTS posts with view data.
    """
    views_by_video = _max_views_by_video()
    if not views_by_video:
        return ""

    scored = []
    for post in _read_csv(LOG):
        vid = post.get("video_id")
        if not vid or vid not in views_by_video:
            continue
        # Backfill title_style for rows logged before the column existed.
        style = post.get("title_style") or classify_title_style(post.get("quote", ""))
        scored.append({
            "views": views_by_video[vid],
            "theme": post.get("theme", "") or "?",
            "author": post.get("author", "") or "?",
            "style": style or "unknown",
        })

    if len(scored) < MIN_MEASURED_POSTS:
        return ""

    scored.sort(key=lambda p: p["views"], reverse=True)
    top, bottom = scored[:3], scored[-3:]

    def fmt(p: dict) -> str:
        return (f'- theme "{p["theme"]}", {p["author"]}, '
                f'{p["style"]}-style title ({p["views"]} views)')

    return (
        "\n\nPERFORMANCE INSIGHTS (from your "
        f"{len(scored)} measured posts — use as a soft nudge, never at the cost "
        "of quote authenticity or the required author/theme above):\n"
        "Top performers — lean toward these themes / title styles:\n"
        + "\n".join(fmt(p) for p in top)
        + "\nBottom performers — steer away from these patterns:\n"
        + "\n".join(fmt(p) for p in bottom)
        + "\nFavor the angle and title style of the top group; do not copy any "
        "specific quote."
    )


def generate_content() -> dict:
    used_quotes = _load_used_quotes()
    required_author, required_theme = _pick_rotation()

    avoid_block = ""
    if used_quotes:
        quoted = "\n".join(f'- "{q}"' for q in used_quotes[-60:])
        avoid_block = (
            f"\n\nQuotes already used — do NOT repeat or closely paraphrase any of these:\n"
            f"{quoted}"
        )

    insights_block = _performance_insights()

    user_msg = (
        f"Generate today's Stoic Reel.\n"
        f"Required author: {required_author}\n"
        f"Required theme: {required_theme}\n"
        f"Find a fresh angle — pick a passage that cuts differently from anything on the avoid list."
        f"{insights_block}"
        f"{avoid_block}"
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        temperature=1.0,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    data = json.loads(raw)

    required = {"theme", "quote", "author", "voiceover_text", "caption", "hashtags"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")
    return data
