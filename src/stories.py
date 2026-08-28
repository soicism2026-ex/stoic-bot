"""
The curated true-story bank — hand-written, human-approved, never generated.

WHY THIS EXISTS: 222 videos of aphorisms ("Stand unshaken", "Set it down")
produced no emotional connection and falling reach. The owner: "these stories
dont make me feel anything... we need real stories and real substance."

The craft rule these were written to, and the reason they are NOT generated:

    Do not write heroism. "Great man overcomes great suffering" makes a man on
    a bad night feel SMALLER, which doctrine section 5 forbids. He is not
    failing to survive a POW camp; he is failing to answer a text. The stories
    that land are the ones where the great man was PATHETIC FIRST. The
    mechanism is RECOGNITION, not ADMIRATION.

Every script was written by hand, checked against a public-domain translation,
and rated on two axes: emotional power, and whether it leaves the viewer
better (doctrine section 5, which outranks everything). Cato's suicide scores
10 on power and 2 on section 5 — it is the most dangerous story in Stoicism
for a man alone at 11:40pm, and it is not in this file. Neither is Seneca's
forced death, nor Stockdale's torture years, which every draft rendered as
"look what he survived, and you can't answer a text."

NOTHING HERE IS MODEL-GENERATED. A language model asked for a moving Stoic
story will invent a fluent, plausible, false one, and this channel's rule is
that quotes are genuine public-domain text. So the spoken words come out of
data/stories.json verbatim and Claude is not called at all for these posts.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORIES = ROOT / "data" / "stories.json"

# Two stories that must never run close together (same person, and the second
# reveals his death).
APART: dict[str, tuple[str, int]] = {
    # failure_column reveals Serenus's death; the opener must land clean.
    "failure_column": ("serenus_not_ill", 14),
    # Three sea stories close together reads as a gimmick, not a theme.
    "off_the_boat": ("first_hit", 10),
    # Both turn on Seneca going red in public.
    "no_wisdom_removes_it": ("unfinished", 10),
    # Same work as the opener (De Tranquillitate Animi).
    "relaxed_by_amusement": ("serenus_not_ill", 10),
    # Both are Meditations Book 5.
    "sponge_and_egg": ("the_note", 7),
}


def load() -> list[dict]:
    if not STORIES.exists():
        return []
    try:
        data = json.loads(STORIES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return data if isinstance(data, list) else []


def _used_ids(post_rows: list[dict]) -> list[str]:
    """Story ids already published, oldest first, read from posts.csv."""
    out = []
    for r in post_rows:
        exp = (r.get("experiment") or "")
        if exp.startswith("story:"):
            out.append(exp.split(":", 1)[1])
    return out


def _blocked(story: dict, used: list[str], bank_size: int = 0) -> bool:
    """True if a spacing rule forbids this story right now.

    The gap is CLAMPED to the size of the bank. A 14-post gap against a
    15-story bank is unsatisfiable — the story would be starved forever and
    the bank would report itself exhausted one short, which is exactly the
    kind of silent shortfall that is hard to notice in production.
    """
    rule = APART.get(story["id"])
    if not rule:
        return False
    other, gap = rule
    if other not in used:
        return True          # the setup has not aired yet
    if bank_size:
        gap = min(gap, max(1, bank_size - 2))
    since = len(used) - 1 - used.index(other)
    return since < gap


def pick(post_rows: list[dict]) -> dict | None:
    """Highest-scoring story that has not run yet.

    Returns None when the bank is exhausted, so the caller can fall back to the
    generated pipeline rather than repeating a story. Repeating one of these
    would be worse than an ordinary repeat: the whole point is that each is a
    specific human moment, and a viewer who sees one twice learns it was never
    personal.
    """
    used = _used_ids(post_rows)
    seen = set(used)
    bank = load()
    for s in sorted(bank, key=lambda x: -x.get("score", 0)):
        if s["id"] in seen or _blocked(s, used, len(bank)):
            continue
        return s
    return None


def remaining(post_rows: list[dict]) -> int:
    seen = set(_used_ids(post_rows))
    return sum(1 for s in load() if s["id"] not in seen)


def as_content(story: dict) -> dict:
    """Shape a story into the dict daily_post expects from generate_content().

    Deliberately mirrors the generated contract so the render, QA, upload and
    logging paths are completely unchanged — the only difference is that the
    words were written by a person.
    """
    caption = (
        f"{story['tonight']}\n\n"
        f"{story['quote']}\n— {story['author']}, {story['citation']}"
    )
    return {
        "theme": story["theme"],
        "quote": story["quote"],
        "author": story["author"],
        "caption": caption,
        "hook": story["hook"],
        "format": "truestory",
        "hashtags": ["#stoicism", "#marcusaurelius", "#seneca", "#epictetus"],
        "voiceover_story": story["story"],
        "voiceover_lesson": story["lesson"],
        "broll_queries": story.get("broll", []),
        "cta": "",
        "pinned_comment": story["tonight"],
        "callout_words": [],
        "_story_id": story["id"],
        "_citation": story["citation"],
        "_source": story.get("source", ""),
        "_caveat": story.get("caveat", ""),
    }
