"""
Content generation via the Anthropic API.

Asks Claude for one day's Stoic Reel: a real public-domain Stoic quote, a short
voiceover script, an engagement caption, and hashtags. Returns structured JSON.

Variety is enforced on three axes so the feed never fixates on one voice or idea:
- Author rotation draws from a broad roster of genuine Stoics (not just the three
  most famous), and is history-aware so no author repeats on consecutive days or
  within a short window.
- Theme rotation spreads across topics, least-recently-used first.
- Previously used quotes are read from posts.csv and injected into the prompt with
  explicit no-reuse / no-paraphrase instructions.
"""
import csv
import datetime
import json
import os
import sys
from pathlib import Path

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-opus-4-8"

# Resolve posts.csv relative to the repo root so it is read reliably no matter
# what the working directory is under GitHub Actions. POSTS_CSV can override it.
ROOT = Path(__file__).resolve().parent.parent
LOG = Path(os.environ.get("POSTS_CSV", ROOT / "data" / "posts.csv"))

# A broad roster of genuine Stoics. Each maps to the real, public-domain
# source(s) where their surviving words are preserved, so the model can ground
# every quote in an actual text instead of inventing one. These are all
# historically attested; fragmentary authors are paired with the collections
# that record their genuine sayings.
SOURCE_HINTS = {
    "Marcus Aurelius": "Meditations",
    "Seneca": "Letters to Lucilius and the moral essays (On the Shortness of Life, On Anger, etc.)",
    "Epictetus": "Discourses and the Enchiridion (as recorded by Arrian)",
    "Musonius Rufus": "the Lectures and Sayings preserved by Stobaeus",
    "Zeno of Citium": "sayings and doctrines preserved in Diogenes Laertius, Lives VII",
    "Cleanthes": "the Hymn to Zeus and fragments in Stobaeus and Diogenes Laertius",
    "Chrysippus": "fragments and sayings in Diogenes Laertius and Stobaeus",
    "Hierocles": "the Elements of Ethics and the fragments on social duties (oikeiosis)",
    "Hecato of Rhodes": "ethical maxims quoted by Seneca in the Letters",
    "Cato the Younger": "the Stoic statesman's sayings recorded in Plutarch's Life of Cato the Younger",
    "Posidonius": "fragments on ethics and the passions preserved by Galen, Seneca and Stobaeus",
    "Panaetius": "On Duties (the basis of Cicero's De Officiis) and fragments in Stobaeus",
    "Aristo of Chios": "ethical fragments preserved in Diogenes Laertius and Stobaeus",
    "Diogenes of Babylon": "fragments preserved in Cicero and Stobaeus",
}
AUTHORS = list(SOURCE_HINTS)

THEMES = [
    "discipline",
    "mortality/memento mori",
    "control vs acceptance",
    "anger",
    "desire",
    "resilience",
    "time",
    "ego",
    "fear",
    "friendship",
    "duty/justice",
    "adversity as training",
]

SYSTEM = """You are the content engine for a faceless Stoicism Instagram Reels \
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
Favor lesser-known but genuine passages over over-quoted "greatest hits."
- Hook: a 3-7 word scroll-stopping opener — a blunt claim or provocative question \
(e.g. "You are already dying." / "Stop waiting to live."). It is spoken first and \
flashed large on screen in the opening seconds to grab attention before the swipe. \
Punchy and plain; no author name, no quotation marks, no hashtags. It must set up the \
quote's idea WITHOUT quoting or restating the passage.
- Voiceover script: 18-35 seconds spoken (~45-90 words). It is spoken right AFTER the \
hook, so flow naturally into the idea and do NOT repeat the hook line. Plain, grounded, \
masculine-neutral tone. No hashtags in the voiceover.
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
  "caption": "...",
  "hashtags": ["#...", "..."]
}"""


def _load_rows() -> list[dict]:
    """Return all logged post rows (oldest first). Warns loudly if missing."""
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
    """Pick the least-recently-used option, blocking the most recent ones.

    `history` is most-recent-first. Options never used rank as most stale, so
    fresh authors/themes get used before anything cycles back. Ties break by
    `options` order, making the choice deterministic for a given history.
    """
    blocked = set(history[:block_last])
    candidates = [o for o in options if o not in blocked] or list(options)

    def staleness(o: str) -> int:
        # Lower history index = more recent; never-used = most stale.
        return history.index(o) if o in history else len(history) + 1

    return max(candidates, key=lambda o: (staleness(o), -options.index(o)))


def _pick_rotation(rows: list[dict]) -> tuple[str, str]:
    recent_authors = [r["author"] for r in reversed(rows) if r.get("author")]
    recent_themes = [r["theme"] for r in reversed(rows) if r.get("theme")]
    # Block the last 2 authors -> no Stoic repeats within any 3-day window.
    author = _pick_least_recent(AUTHORS, recent_authors, block_last=2)
    # Block the last 3 themes so ideas don't cluster.
    theme = _pick_least_recent(THEMES, recent_themes, block_last=3)
    return author, theme


def generate_content() -> dict:
    rows = _load_rows()
    used_quotes = [r["quote"] for r in rows if r.get("quote")]
    required_author, required_theme = _pick_rotation(rows)

    avoid_block = ""
    if used_quotes:
        quoted = "\n".join(f'- "{q}"' for q in used_quotes[-80:])
        avoid_block = (
            "\n\nQuotes already used — do NOT repeat, paraphrase, or recycle the "
            "core metaphor of any of these:\n"
            f"{quoted}"
        )

    user_msg = (
        f"Generate today's Stoic Reel.\n"
        f"Required author: {required_author}\n"
        f"Draw the quote from: {SOURCE_HINTS[required_author]}.\n"
        f"Required theme: {required_theme}\n"
        f"Pick a genuine, lesser-known passage that cuts differently from anything "
        f"on the avoid list."
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

    required = {"theme", "quote", "author", "hook", "voiceover_text", "caption", "hashtags"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")
    return data
