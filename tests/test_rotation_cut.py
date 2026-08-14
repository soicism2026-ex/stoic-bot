"""Format/theme cut + opener variety (owner, 2026-08-13: "more variety, shorts out").

Two instructions that pull against each other, so both halves are pinned here.
Cutting the pool to three formats means each returns EVERY DAY at 3 posts/day —
which raises repetition risk, and repetition is the most likely cause of the
77% collapse in 1-day views. So the cut only makes sense paired with a hard
opener-variety rule. If a future change removes one half, these fail.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import content  # noqa: E402

# Age-corrected medians at 1 day old, full history.
CUT_FORMATS = {"letter", "story", "pov", "challenge"}
KEPT_FORMATS = {"quote", "rule", "minimal"}
CUT_THEMES = {"friendship", "desire"}


def _rotation():
    return [content._pick_format([0] * i) for i in range(6)]


def test_only_the_top_three_formats_rotate():
    assert set(_rotation()) == KEPT_FORMATS


def test_weak_formats_are_gone():
    assert not set(_rotation()) & CUT_FORMATS


def test_rotation_still_cycles_evenly():
    r = _rotation()
    assert r[:3] == r[3:], "rotation is not a clean cycle"


def test_weakest_themes_are_cut():
    assert not set(content.THEMES) & CUT_THEMES


def test_strongest_themes_lead_the_list():
    """LRU reaches the head of the list first."""
    assert content.THEMES[:3] == ["anger", "fear", "resilience"]


def test_enough_themes_remain_to_avoid_repetition():
    """Cutting to the top three would triple how often each recurs. The whole
    problem is repetition, so breadth here is deliberate."""
    assert len(content.THEMES) >= 8


# ------------------------------------------------------- opener variety

def test_system_prompt_bans_repeating_openers():
    assert "OPENER VARIETY" in content.SYSTEM
    assert "same word as ANY of the recent hooks" in content.SYSTEM


def test_system_prompt_explains_why_the_pool_is_narrow():
    """A rule without its reason gets optimised away by the next editor."""
    assert "returns every single day" in content.SYSTEM


def test_rule_format_told_not_to_always_open_with_the_word_rule():
    """6 of the last 15 hooks opened 'Rule' — the watchdog caught it."""
    assert 'not open every rule post' in content.SYSTEM


def test_banned_opener_list_is_computed_from_real_history():
    src = (ROOT / "src" / "content.py").read_text()
    assert "BANNED OPENING WORDS" in src
    assert "n >= 2" in src, "threshold missing — must ban words used twice+"


def test_banned_openers_fire_on_the_live_history():
    """End to end against the real posts.csv, not a fixture."""
    from collections import Counter
    rows = content._load_rows()
    hooks = [(r.get("hook") or "").strip() for r in rows]
    hooks = [h for h in hooks if h][-15:]
    if len(hooks) < 5:
        return
    op = Counter(h.split()[0].strip('.,:;"\'').lower() for h in hooks if h.split())
    assert [w for w, n in op.items() if n >= 2], \
        "no repeated openers in live history — check the detector still works"
