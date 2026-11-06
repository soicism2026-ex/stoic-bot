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
# Frontinus's daily read of what is working (scripts/strategist.py).
STRATEGY = ROOT / "data" / "strategy.json"
# Runs on which an edit was blocked by the preflight gate on every attempt.
BLOCKS = ROOT / "data" / "edit_blocks.csv"
MAX_BLOCKS = int(__import__("os").environ.get("EDIT_MAX_BLOCKS", "2"))


def load() -> list[dict]:
    return json.loads(BANK.read_text(encoding="utf-8"))


def _norm(t: str) -> str:
    import re
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower()).split())


def _aired_quotes(post_rows: list[dict]) -> list[str]:
    """Every quote the channel has posted, in ANY format. Edit ids alone were
    not enough: "In the morning when thou risest unwillingly" had aired as a
    2026-09-03 post and aired again as an edit on 2026-10-19."""
    return [_norm(r.get("quote", "")) for r in post_rows if r.get("quote")]


def _already_aired(q: dict, aired: list[str]) -> bool:
    key = _norm(q["quote"])[:50]
    return bool(key) and any(key in a for a in aired)


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


def theme_rank() -> dict[str, int]:
    """Frontinus's verdict per theme: 2 winning, 1 even or not enough data,
    0 losing. Empty when there is no read, which leaves bank order alone."""
    try:
        return {k: int(v) for k, v in json.loads(STRATEGY.read_text(encoding="utf-8"))["theme_rank"].items()}
    except Exception:  # noqa: BLE001
        return {}


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
    aired = _aired_quotes(post_rows)
    fresh = [q for q in load() if q["id"] not in used and q["id"] not in jammed
             and not _already_aired(q, aired)]
    if not fresh:
        return None
    seen = {}
    for i, r in enumerate(edit_rows):
        seen[(r.get("author") or "").strip()] = i
    authors = sorted({q["author"] for q in fresh}, key=lambda a: (seen.get(a, -1), a))
    rank = theme_rank()
    for a in authors:
        mine = [q for q in fresh if q["author"] == a and q["theme"] != last_theme]
        if mine:
            # Within the author's turn, winning themes air first and losing
            # ones last (owner 2026-10-27: a strategist that does the job for
            # free). max() keeps the first of equals: bank order breaks ties.
            return max(mine, key=lambda q: rank.get(q["theme"], 1))
    return fresh[0]


def remaining(post_rows: list[dict]) -> int:
    used, jammed, aired = _used(post_rows), jammed_ids(), _aired_quotes(post_rows)
    return sum(1 for q in load() if q["id"] not in used and q["id"] not in jammed
               and not _already_aired(q, aired))


# The comment the channel posts under every edit. Through 2026-11-06 it was
# PINNED_GENERIC under every one, and no viewer ever answered it: every edit
# had exactly one comment, the channel's own. On 2026-11-06 the owner sent a
# viral Short's description (on Cicero's test 2, "a real question under each
# Short?") "as inspiration for our next shorts": three short paragraphs and a
# question for the comments. Since then each quote on the shelf carries its
# own `description` and `question` (data/edit_quotes.json, checked by
# scripts/shelf.py); the question ends the description and is the channel's
# comment. A quote without one falls back to its theme's question, written in
# doctrine 5's register: about the viewer's own life, a handle, never shame.
PINNED_GENERIC = "Which line hit hardest? Write it below."
PINNED_BY_THEME = {
    "discipline": "What's one small thing you'll do today even if you don't feel like it?",
    "resilience": "What's something hard you got through that you'd forgotten you got through?",
    "fear": "What's one fear that turned out smaller than you expected?",
    "time": "What's one thing you'll stop putting off this week?",
    "friendship": "What does a real friend do that a contact never will?",
    "adversity": "What setback ended up teaching you the most?",
    "anger": "What helps you cool down before you say something you'd regret?",
    "ego": "What's one thing you only learned after admitting you were wrong?",
    "desire": "What's something you wanted badly and turned out to be fine without?",
    "duty": "What's one duty you'll do well today, even if nobody sees it?",
    "control": "What's one worry on your mind right now that isn't in your control?",
    "mortality": "What's one thing you'd stop postponing if you remembered time is short?",
}
# The line that ends every new-style description, worded like the owner's
# example; Cicero (scripts/marketer.py) tells old Shorts from new by it.
QUESTION_MARK = "\U0001F4AC Question:"
QUESTION_LINE = QUESTION_MARK + " {question} Share your thoughts in the comments."


def pinned_comment(q: dict) -> str:
    """The quote's own question, else its theme's, else the generic line."""
    own = (q.get("question") or "").strip()
    return own or PINNED_BY_THEME.get(q.get("theme"), PINNED_GENERIC)


def description(content: dict) -> str:
    """The YouTube description of an edit, in the style of the viral Short the
    owner sent (2026-11-06): the quote's three short paragraphs, then its
    question for the comments, then the quote word for word with its source
    (the channel's promise), then the hashtags. The caller adds the promo
    block and any music credit. A quote without paragraphs keeps the layout
    every edit had before: the hook, then the quote and its source."""
    body = (content.get("_description") or "").strip()
    ask = (content.get("_question") or "").strip()
    source = "\u2014 " + ", ".join(x for x in (content["author"], content.get("_citation") or "") if x)
    if not body:
        hook = content["hook"].strip().rstrip(".!? ")
        parts = [f"{hook}." if hook else "", content["caption"]]
    else:
        parts = [body, QUESTION_LINE.format(question=ask) if ask else "",
                 f"\u201c{content['quote'].strip()}\u201d\n{source}"]
    parts.append(" ".join(content["hashtags"]))
    return "\n\n".join(p for p in parts if p)


def as_content(q: dict) -> dict:
    """Same contract as stories.as_content, so render/QA/upload are unchanged.
    `_description` and `_question` carry the owner's description style
    (description() above) to scripts/daily_post.py."""
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
        "pinned_comment": pinned_comment(q),
        "callout_words": [],
        "_edit_id": q["id"],
        "_citation": q["citation"],
        "_description": q.get("description", ""),
        "_question": q.get("question", ""),
    }
