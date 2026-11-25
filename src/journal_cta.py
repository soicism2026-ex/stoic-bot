"""A closing pitch for the Stoic Reset journal (owner 2026-11-24, in chat: "we
need to entice people to buy something off gum road on the shorts").

Cicero's test "journal-cta" (data/marketing_tests.json): for 14 days, from
2026-11-25, the day's THIRD Short (the 19:00 UTC one) ends with a short pitch:
Brian reads one closing line after the quote, an end card shows for the last
couple of seconds, the Short's pinned comment is the pitch, and its description
keeps the journal line with a tracking link (?ref=short-cta) so the owner can
read the sales in Gumroad's own dashboard.

The pitch is TRUE: it names what the product is (a 30-day guided journal, one
page a day) and its price, and promises nothing about anyone's life. No fake
scarcity, no invented reviews, no countdown. Everything is gated on the ledger
test and switches itself off after its end date; with the test absent or not
running, nothing changes.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETING_TESTS = ROOT / "data" / "marketing_tests.json"
TEST_ID = "journal-cta"
SLOT_INDEX = 2                      # the day's third post (POST_SLOT_HOURS 0,7,19)
MAX_CLOSING_WORDS = 14              # the ElevenLabs budget: about 70 characters

# What Brian reads after the quote (14 words).
CLOSING_LINE = "If this one hit home, the Stoic Reset is thirty days of exactly this."
# The end card, last CARD_SECONDS of the Short, in the v2 type; RESET is red.
CARD_LINES = ("THE STOIC RESET", "30 days. One page a day.", "Link on our channel page")
CARD_ACCENT = "RESET"
CARD_SECONDS = 2.5
# The pinned comment (links in Shorts comments are not clickable, so it points to the channel page).
PINNED = ("If this one hit home: The Stoic Reset is a 30-day guided journal, one page a day, "
          "C$5.99. The link is on our channel page.")
BASE_URL = "https://soicism.gumroad.com/l/cslosv"
TRACKING_URL = BASE_URL + "?ref=short-cta"


def _test() -> dict | None:
    try:
        tests = json.loads(MARKETING_TESTS.read_text(encoding="utf-8")).get("tests", [])
        return next((t for t in tests if t.get("id") == TEST_ID), None)
    except Exception:  # noqa: BLE001  no ledger, no test: nothing changes
        return None


def active(posts_today: int | None, day=None) -> bool:
    """True for the pitch Short only: the ledger test is running, `day` (the
    air day, src/airday.py) is inside [started, end] and not in `exclude`, and
    this is the day's third post (`posts_today` posts already out: 2)."""
    t = _test()
    if not t or t.get("status") != "running" or not t.get("started") or not t.get("end"):
        return False
    if posts_today != SLOT_INDEX:
        return False
    try:
        if day is None:
            import airday
            day = airday.today()
        if isinstance(day, dt.datetime):
            day = day.date()
        if str(day) in (t.get("exclude") or []):
            return False
        return dt.date.fromisoformat(t["started"]) <= day <= dt.date.fromisoformat(t["end"])
    except Exception:  # noqa: BLE001
        return False


def word_count(text: str) -> int:
    return len(text.split())


def with_tracking(description: str) -> str:
    """The description with the journal link carrying ?ref=short-cta."""
    return description.replace(BASE_URL, TRACKING_URL) if "?ref=" not in description else description


def card_text() -> str:
    """REEL_END_CARD: the three lines, joined for the render's environment."""
    return "|".join(CARD_LINES)


def apply(content: dict, description: str, spoken: str) -> tuple[str, str]:
    """(description, spoken) for the pitch Short, and content's pinned comment
    and end-card flag set. The caller passes the narration it already built."""
    content["pinned_comment"] = PINNED
    content["_journalCta"] = True
    return with_tracking(description), f"{spoken} {CLOSING_LINE}".strip()
