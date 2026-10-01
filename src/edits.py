"""
Stoic edits — the channel's main format from 2026-10-01.

Owner: "The posts are still a little bit boring ... lets pivot this channel to
a more stoic-edits style with a larger focus on cool stoic visuals rather than
explaining a boring story ... grand music ... motivational videos of people
who preach stoicism in the background."

An edit is ~15 seconds: one short line that names the viewer's problem, then
the quote delivered over epic music while the picture cuts on a fast rhythm.
No story to explain. What it keeps from everything before it:
  * every quote is VERBATIM public-domain text, checked against the source
    (scripts/validate_quotes.py; CI fails otherwise)
  * the voice reads the quote and the text follows it word by word
  * visuals are real stock video (short keyword searches, which Pixabay
    actually matches) plus free AI stills for what stock can't show (statues,
    the ancient world), tagged "still:" in the bank

What it does NOT do: use other creators' motivational clips or commercial
songs. That gets videos claimed and channels refused monetisation under
YouTube's reused-content policy — the opposite of the goal.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "edit_quotes.json"


def load() -> list[dict]:
    return json.loads(BANK.read_text(encoding="utf-8"))


def _used(post_rows: list[dict]) -> set:
    return {(r.get("experiment") or "").removeprefix("edit:")
            for r in post_rows if (r.get("experiment") or "").startswith("edit:")}


def pick(post_rows: list[dict]) -> dict | None:
    """First quote not yet used, avoiding the theme of the last edit."""
    used = _used(post_rows)
    last_theme = next((r.get("theme") for r in reversed(post_rows)
                       if (r.get("experiment") or "").startswith("edit:")), None)
    fresh = [q for q in load() if q["id"] not in used]
    if not fresh:
        return None
    for q in fresh:
        if q["theme"] != last_theme:
            return q
    return fresh[0]


def remaining(post_rows: list[dict]) -> int:
    used = _used(post_rows)
    return sum(1 for q in load() if q["id"] not in used)


def as_content(q: dict) -> dict:
    """Same contract as stories.as_content, so render/QA/upload are unchanged."""
    caption = f"{q['quote']}\n— {q['author']}, {q['citation']}"
    return {
        "theme": q["theme"],
        "quote": q["quote"],
        "author": q["author"],
        "caption": caption,
        "hook": q["hook"],
        "format": "edit",
        "hashtags": ["#stoicism", "#motivation", "#discipline", "#stoic", "#shorts"],
        # act 1 is the hook alone; act 3 is the quote (spoken-quote mode puts
        # it first) with nothing after it — the edit ends on the quote.
        "voiceover_story": "",
        "voiceover_lesson": "",
        "broll_queries": q["visuals"],
        "cta": "",
        "pinned_comment": "Which line hit hardest? Write it below.",
        "callout_words": [],
        "_edit_id": q["id"],
        "_citation": q["citation"],
    }
