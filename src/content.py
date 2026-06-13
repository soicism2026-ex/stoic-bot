"""
Content generation via the Anthropic API.

Asks Claude for one day's Stoic Reel: a real public-domain Stoic quote, a short
voiceover script, an engagement caption, and hashtags. Returns structured JSON.

Variety is enforced on three axes so the feed never fixates on one voice or idea:
- Author rotation favours the Big 3 (Marcus Aurelius, Seneca, Epictetus) on 3 of
  every 5 days — analytics show they outperform obscure Stoics by 2-4x — while
  still cycling the wider roster so content stays diverse.
- Theme rotation spreads across topics, least-recently-used first.
- Previously used quotes are read from posts.csv and injected as a hard block list.
"""
import csv
import json
import os
import sys
from pathlib import Path

MODEL = "claude-opus-4-8"

ROOT = Path(__file__).resolve().parent.parent
LOG = Path(os.environ.get("POSTS_CSV", ROOT / "data" / "posts.csv"))

SOURCE_HINTS = {
    "Marcus Aurelius": "Meditations",
    "Seneca": "Letters to Lucilius and the moral essays (On the Shortness of Life, On Anger, etc.)",
    "Epictetus": "Discourses and the Enchiridion (as recorded by Arrian)",
    "Musonius Rufus": "the Lectures and Sayings preserved by Stobaeus",
    "Zeno of Citium": "sayings and doctrines preserved in Diogenes Laertius, Lives VII",
    "Cleanthes": "the Hymn to Zeus and fragments in Stobaeus and Diogenes Laertius",
    "Chrysippus": "fragments and sayings in Diogenes Laertius and Stobaeus",
    "Hierocles": "the Elements of Ethics and the fragments on social duties (oikeiosis)",
    "Cato the Younger": "the Stoic statesman's sayings recorded in Plutarch's Life of Cato the Younger",
}

# Analytics signal: Big 3 consistently get 900–1050 views vs 200–600 for the
# full roster. Post from them on 3 of every 5 days; cycle the wider roster the
# other 2 days for variety.
BIG3 = ["Marcus Aurelius", "Seneca", "Epictetus"]
AUTHORS = list(SOURCE_HINTS)   # full rotation for the other 2 days

THEMES = [
    "discipline",
    "mortality/memento mori",
    "control vs acceptance",
    "ego",
    "resilience",
    "anger",
    "desire",
    "time",
    "fear",
    "friendship",
    "duty/justice",
    "adversity as training",
]

SYSTEM = """You are the content engine for a faceless Stoicism YouTube Shorts \
account. Your job is to produce ONE short-form video script per call.

Rules:
- Use only genuine, public-domain Stoic material. Quote a passage that is actually \
attested in the assigned author's surviving texts or fragments. NEVER fabricate, \
invent, or misattribute a quote. If you are not certain a line is genuinely the \
assigned author's, choose a different real passage from the same author rather than \
guessing.
- The quote must be punchy and fit on screen in under ~25 words. Lightly modernized \
phrasing of a real passage is fine, but it must preserve the author's actual meaning \
and wording; do not turn it into a new aphorism. Attribute to the correct author.
- Draw from the full breadth of the author's work, not only their most famous lines. \
Favor lesser-known but genuine passages over over-quoted "greatest hits." This is \
especially important: the channel's audience has already seen the most famous lines.
- Hook: a 3-7 word scroll-stopping opener — a blunt claim or provocative question \
(e.g. "You are already dying." / "Stop waiting to live."). It is spoken first and \
flashed large on screen in the opening seconds to grab attention before the swipe. \
Punchy and plain; no author name, no quotation marks, no hashtags. It must set up the \
quote's idea WITHOUT quoting or restating the passage.
- Voiceover script: 18-35 seconds spoken (~45-90 words). It is spoken right AFTER the \
hook, so flow naturally into the idea and do NOT repeat the hook line. Plain, grounded, \
masculine-neutral tone. No hashtags in the voiceover. End a sentence before the CTA.
- CTA: 1-2 spoken sentences for the very last moment of the voiceover. Reference the \
next day's theme naturally — give a REASON to follow, not just "subscribe". \
Under 25 words. Vary the phrasing across days. \
Example: "Tomorrow: Marcus Aurelius on anger. Follow for your daily Stoic dose."
- Pinned comment: a short, personal, slightly uncomfortable question that makes \
viewers stop and actually answer — tied directly to today's quote and theme. \
It should feel like something a friend would ask, not a YouTube engagement prompt. \
Under 20 words. Make it specific to the quote's idea. \
Example for discipline: "What's the one habit you keep starting and abandoning — and what's your real excuse?"
- Caption: 1-2 sentences that reframe the idea for daily life + one soft question \
to drive comments.
- Hashtags: 8-12, mixing broad (#stoicism #discipline) and mid-size niche tags.

Respond with ONLY valid JSON, no markdown, no preamble, in this exact shape:
{
  "theme": "...",
  "quote": "...",
  "author": "<the exact author name you were assigned>",
  "hook": "...",
  "voiceover_text": "...",
  "cta": "...",
  "pinned_comment": "...",
  "caption": "...",
  "hashtags": ["#...", "..."]
}"""


def _load_rows() -> list[dict]:
    if not LOG.exists():
        print(
            f"WARNING: posts.csv not found at {LOG} — repeat-avoidance history is "
            f"empty this run.",
            file=sys.stderr,
        )
        return []
    with open(LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _pick_least_recent(options: list[str], history: list[str], block_last: int) -> str:
    """Pick the least-recently-used option, blocking the most recent N entries.

    history is most-recent-first. Never-used options rank as most stale.
    Ties break by position in `options` (lower index wins), making the
    choice deterministic for a given history.
    """
    blocked = set(history[:block_last])
    candidates = [o for o in options if o not in blocked] or list(options)

    def staleness(o: str) -> int:
        return history.index(o) if o in history else len(history) + 1

    return max(candidates, key=lambda o: (staleness(o), -options.index(o)))


def _pick_rotation(rows: list[dict]) -> tuple[str, str]:
    recent_authors = [r["author"] for r in reversed(rows) if r.get("author")]
    recent_themes = [r["theme"] for r in reversed(rows) if r.get("theme")]

    # 3 out of every 5 days: pick from Big 3 (MA, Seneca, Epictetus).
    # Analytics show they average 900-1050 views vs 200-600 for lesser-known Stoics.
    day_index = len(rows)
    if day_index % 5 < 3:
        author = _pick_least_recent(BIG3, recent_authors, block_last=1)
    else:
        # Full roster on the other 2 days, excluding anyone just posted.
        author = _pick_least_recent(AUTHORS, recent_authors, block_last=2)

    theme = _pick_least_recent(THEMES, recent_themes, block_last=3)
    return author, theme


def _pick_next_theme(rows: list, current_theme: str) -> str:
    recent = [r["theme"] for r in reversed(rows) if r.get("theme")]
    return _pick_least_recent(THEMES, [current_theme] + recent, block_last=3)


def generate_content() -> dict:
    import anthropic
    rows = _load_rows()
    used_quotes = [r["quote"] for r in rows if r.get("quote")]
    required_author, required_theme = _pick_rotation(rows)
    day_number = len(rows) + 1
    next_theme = _pick_next_theme(rows, required_theme)

    # Build a hard block list, highlighting any quotes by today's author so the
    # model knows it must pick a completely different passage from the same source.
    author_used = [q for i, q in enumerate(used_quotes)
                   if rows[i].get("author") == required_author]
    avoid_block = ""
    if used_quotes:
        quoted = "\n".join(f'- "{q}"' for q in used_quotes[-80:])
        avoid_block = (
            "\n\nCRITICAL — quotes already used on this channel. You MUST NOT repeat, "
            "paraphrase, or use the core idea of ANY quote on this list:\n"
            f"{quoted}"
        )
        if author_used:
            author_quoted = "\n".join(f'- "{q}"' for q in author_used)
            avoid_block += (
                f"\n\nQuotes already used from {required_author} specifically — "
                f"you MUST pick a DIFFERENT passage from the same source:\n"
                f"{author_quoted}"
            )

    user_msg = (
        f"Generate today's Stoic Reel.\n"
        f"Required author: {required_author}\n"
        f"Draw the quote from: {SOURCE_HINTS[required_author]}.\n"
        f"Required theme: {required_theme}\n"
        f"Tomorrow's theme (for the CTA): {next_theme}\n"
        f"Pick a genuine, lesser-known passage that cuts differently from anything "
        f"on the avoid list."
        f"{avoid_block}"
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        temperature=1.0,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    data = json.loads(raw)

    required = {"theme", "quote", "author", "hook", "voiceover_text",
                "cta", "pinned_comment", "caption", "hashtags"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")

    data["day_number"] = day_number
    return data
