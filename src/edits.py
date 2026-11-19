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


# Fama's plan for the next Short (scripts/fama.py): a safe trend of the day
# tied to one of the next quotes. The quote is never changed; only the hook,
# the description's lead, the question and the tags are today's.
TOPICAL = ROOT / "data" / "topical.json"
TOPICAL_MAX_AGE_H = 20


def edit_post_count(post_rows: list[dict]) -> int:
    return sum(1 for r in post_rows if (r.get("experiment") or "").startswith("edit:"))


def topical_for(post_rows: list[dict], now=None) -> dict | None:
    """Fama's plan for THIS post when it is fresh (same forPost, decided under
    20 hours ago), its edit is still unaired and not jammed, and it is whole;
    else None, and the rotation decides as it always did."""
    import datetime as dt
    try:
        plan = json.loads(TOPICAL.read_text(encoding="utf-8"))
        if plan.get("none") or plan.get("forPost") != edit_post_count(post_rows):
            return None
        at = dt.datetime.fromisoformat(str(plan["decidedAt"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=dt.timezone.utc)
        now = now or dt.datetime.now(dt.timezone.utc)
        if not dt.timedelta(0) <= now - at < dt.timedelta(hours=TOPICAL_MAX_AGE_H):
            return None
        if not all(isinstance(plan.get(k), str) and plan[k].strip() for k in ("edit", "hook", "lead")):
            return None
        eid = plan["edit"]
        if eid in _used(post_rows) or eid in jammed_ids():
            return None
        aired = _aired_quotes(post_rows)
        q = next((x for x in load() if x["id"] == eid), None)
        if q is None or _already_aired(q, aired):
            return None
        return plan
    except Exception:  # noqa: BLE001  a broken plan never stops a post
        return None


def pick(post_rows: list[dict]) -> dict | None:
    """The quote to air: Fama's topical one when she has a fresh plan for this
    post (returned as a copy carrying `_topical`), else the rotation's. The
    owner's own thoughts (`personal`, below) air before either."""
    plan = None if personal_fresh(post_rows) else topical_for(post_rows)
    if plan:
        q = next(x for x in load() if x["id"] == plan["edit"])
        return {**q, "_topical": plan}
    return rotation_pick(post_rows)


def personal_fresh(post_rows: list[dict]) -> list[dict]:
    """The owner's own thoughts still to air, in shelf order.

    Owner 2026-11-19, in the HQ: "I want to make the short more personal and
    based on my life". Varro pairs each of his thoughts with the Stoic who said
    the same and marks the entry `"personal": true`; those air first, one at a
    time, ahead of Fama's topical plan and the author rotation.
    """
    used, jammed, aired = _used(post_rows), jammed_ids(), _aired_quotes(post_rows)
    return [q for q in load() if q.get("personal") is True and q["id"] not in used
            and q["id"] not in jammed and not _already_aired(q, aired)]


def rotation_pick(post_rows: list[dict]) -> dict | None:
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
    own = personal_fresh(post_rows)
    if own:
        return own[0]
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


# The comment the channel posts under every edit. Through 2026-11-05 it was
# PINNED_GENERIC under every one, and viewers left 5 comments on 51 edits
# (0.48 per 1,000 views; analytics.csv). On 2026-11-06 the owner sent a
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
# Owner 2026-11-16: "more enticing to leave a comment but dont ask to leave a
# comment". The question invites the answer; the explicit ask is gone.
QUESTION_LINE = QUESTION_MARK + " {question}"


# The YouTube searches our audience makes (owner 2026-11-07: "a list of 10
# things people might potentially search for ... we will use it make our
# shorts easier to find"; data/search_research.md). Each quote answers one,
# by its id or its theme. Used only once the owner says yes: Cicero's ledger,
# test "search-phrases" ("descriptions": the description opens with it and a
# matching hashtag and tags join; "titles": the title carries it too).
SEARCH_PHRASES = ROOT / "data" / "search_phrases.json"
MARKETING_TESTS = ROOT / "data" / "marketing_tests.json"


def search_phrase(q: dict) -> dict | None:
    """{id, phrase, hashtag, ...}: the search this quote answers, or None."""
    try:
        data = json.loads(SEARCH_PHRASES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    pid = (data.get("overrides") or {}).get(q.get("id")) or (data.get("byTheme") or {}).get(q.get("theme"))
    return next((p for p in data.get("phrases", []) if p.get("id") == pid), None)


def _titles_test_on(today=None) -> bool:
    """Cicero's "titles-search" test (owner 2026-11-16, Go on the Ideas card
    idea-titles-search): the title carries the search too. On while the test
    runs or is adopted, and from its start date while it is still queued (it
    is meant to begin the day test "search-phrases" ends, 2026-11-22, and no
    shift has to flip a status for that to happen). A loss ("done" without
    "adopted") turns it off."""
    try:
        tests = json.loads(MARKETING_TESTS.read_text(encoding="utf-8")).get("tests", [])
        t = next(t for t in tests if t.get("id") == "titles-search")
    except Exception:  # noqa: BLE001
        return False
    if t.get("adopted"):
        return True
    if t.get("status") == "running":
        return True
    if t.get("status") == "queued" and t.get("start"):
        from datetime import date, datetime, timezone
        today = today or datetime.now(timezone.utc).date()
        try:
            return date.fromisoformat(t["start"]) <= today
        except ValueError:
            return False
    return False


def search_use() -> str | None:
    """None until the owner says yes; then "descriptions" or "titles"."""
    try:
        tests = json.loads(MARKETING_TESTS.read_text(encoding="utf-8")).get("tests", [])
        t = next(t for t in tests if t.get("id") == "search-phrases")
    except Exception:  # noqa: BLE001  no ledger, no test: nothing changes
        return None
    use = None
    if t.get("adopted") in ("descriptions", "titles"):
        use = t["adopted"]
    elif t.get("status") == "running":
        use = t.get("use") if t.get("use") in ("descriptions", "titles") else "descriptions"
    if use and _titles_test_on():
        return "titles"
    return use


# Cicero's test 6 (2026-11-12): a follow line as the description's last line
# before the hashtags, on while the ledger's "follow-line" test is running
# or adopted (data/marketing_tests.json; the owner's Ideas board card
# idea-follow-line). Measured in subscribers per 1,000 views.
FOLLOW_LINE = "One Stoic line a day. Follow for tomorrow's."


def _ledger_test(test_id: str) -> dict | None:
    try:
        tests = json.loads(MARKETING_TESTS.read_text(encoding="utf-8")).get("tests", [])
        return next((t for t in tests if t.get("id") == test_id), None)
    except Exception:  # noqa: BLE001  no ledger: nothing changes
        return None


def follow_line() -> str:
    """FOLLOW_LINE while the test runs or stays adopted, else ""."""
    t = _ledger_test("follow-line")
    if t and (t.get("status") == "running" or t.get("adopted")):
        return FOLLOW_LINE
    return ""


def search_lead(content: dict) -> str:
    """The description's first line when the search is on, in plain words,
    e.g. How to stop overthinking: Epictetus's answer."""
    found = content.get("_search")
    if not found:
        return ""
    return f"{found['phrase'][0].upper()}{found['phrase'][1:]}: {content['author']}'s answer."


def pinned_comment(q: dict) -> str:
    """The quote's own question, else its theme's, else the generic line."""
    top = q.get("_topical") or {}
    own = ((top.get("question") or "") or (q.get("question") or "")).strip()
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
    top = content.get("_topical") or {}
    ask = (top.get("question") or "").strip() or ask
    source = "\u2014 " + ", ".join(x for x in (content["author"], content.get("_citation") or "") if x)
    if not body:
        hook = content["hook"].strip().rstrip(".!? ")
        parts = [f"{hook}." if hook else "", content["caption"]]
    else:
        parts = [body, QUESTION_LINE.format(question=ask) if ask else "",
                 f"\u201c{content['quote'].strip()}\u201d\n{source}"]
    parts.insert(0, search_lead(content))            # only once the owner said yes
    if (top.get("lead") or "").strip():
        parts.insert(0, top["lead"].strip())          # Fama: today's event, then the quote's own words
    parts.append(follow_line())                       # Cicero's test 6, while it runs
    parts.append(" ".join(content["hashtags"]))
    return "\n\n".join(p for p in parts if p)


def as_content(q: dict) -> dict:
    """Same contract as stories.as_content, so render/QA/upload are unchanged.
    `_description` and `_question` carry the owner's description style
    (description() above) to scripts/daily_post.py."""
    caption = f"{q['quote']}\n— {q['author']}, {q['citation']}"
    use = search_use()
    found = search_phrase(q) if use else None
    tags = ["#stoicism", "#motivation", "#discipline", "#stoic", "#shorts"]
    if found and found.get("hashtag") and found["hashtag"] not in tags:
        tags.insert(1, found["hashtag"])
    top = q.get("_topical") or None
    return {
        "theme": q["theme"],
        "quote": q["quote"],
        "author": q["author"],
        "caption": caption,
        "hook": (top or {}).get("hook") or q["hook"],
        "format": "edit",
        "hashtags": tags,
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
        "_question": (top or {}).get("question") or q.get("question", ""),
        "_topical": top,
        "_search": found,
        "_searchUse": use if found else None,
        # The painted look (REEL_EDIT_LOOK=painted): the scene writer's shots
        # (6-8, in order; src/painter.py paints them) and the words the type
        # sets in gold (the quote's, then the hook's). Empty when the quote
        # has none: the painter's template and the plain type take over.
        "_scenes": [s for s in (q.get("scenes") or []) if isinstance(s, str) and s.strip()],
    }
