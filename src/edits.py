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
# Runs on which an edit was blocked by the preflight gate on every attempt.
BLOCKS = ROOT / "data" / "edit_blocks.csv"
MAX_BLOCKS = int(__import__("os").environ.get("EDIT_MAX_BLOCKS", "2"))


def load() -> list[dict]:
    return json.loads(BANK.read_text(encoding="utf-8"))


def _used(post_rows: list[dict]) -> set:
    return {(r.get("experiment") or "").removeprefix("edit:")
            for r in post_rows if (r.get("experiment") or "").startswith("edit:")}


def record_block(edit_id: str, date: str, reason: str) -> None:
    """Append one fully-blocked run for this edit."""
    import csv
    new = not BLOCKS.exists()
    with open(BLOCKS, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "edit_id", "reason"])
        w.writerow([date, edit_id, reason])


def jammed_ids() -> set:
    """Edits blocked on at least MAX_BLOCKS separate runs: set aside so one
    un-renderable quote cannot stop the channel (it happened 2026-10-19)."""
    import csv
    from collections import Counter
    if not BLOCKS.exists():
        return set()
    try:
        c = Counter(r["edit_id"] for r in csv.DictReader(open(BLOCKS, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return set()
    return {eid for eid, n in c.items() if n >= MAX_BLOCKS}


def pick(post_rows: list[dict]) -> dict | None:
    """Next quote: never one already used, from the author used LEAST
    recently, avoiding the theme of the last edit.

    Author rotation since 2026-10-18 (2 posts a day): the bank is stored by
    author, so plain bank order aired ten Marcus Aurelius edits in a row and
    then a run of Seneca. Alternating keeps back-to-back posts distinct (the
    repetitive-content risk grows with volume) and gives each author a fair
    test. Deterministic: ties break by author name, then bank order.
    """
    used = _used(post_rows)
    edit_rows = [r for r in post_rows if (r.get("experiment") or "").startswith("edit:")]
    last_theme = edit_rows[-1].get("theme") if edit_rows else None
    jammed = jammed_ids()
    fresh = [q for q in load() if q["id"] not in used and q["id"] not in jammed]
    if not fresh:
        return None
    seen = {}
    for i, r in enumerate(edit_rows):
        seen[(r.get("author") or "").strip()] = i
    authors = sorted({q["author"] for q in fresh}, key=lambda a: (seen.get(a, -1), a))
    for a in authors:
        for q in fresh:
            if q["author"] == a and q["theme"] != last_theme:
                return q
    return fresh[0]


def remaining(post_rows: list[dict]) -> int:
    used, jammed = _used(post_rows), jammed_ids()
    return sum(1 for q in load() if q["id"] not in used and q["id"] not in jammed)


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
