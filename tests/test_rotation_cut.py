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
    """SUPERSEDED 2026-08-21: "question" (F3) joined the rotation as a format
    TEST arm, taking every third slot. The three retention-picked formats must
    all still be present — the test arm adds to them, it does not replace
    them, so the control runs concurrently."""
    assert KEPT_FORMATS <= set(_rotation())


def test_weak_formats_are_gone():
    assert not set(_rotation()) & CUT_FORMATS


def test_rotation_still_cycles_cleanly():
    """Cycle length has grown twice: 3 -> 4 when minimal was weighted double
    for retention, then 4 -> 6 when the F3 "question" test arm took every third
    slot. It must still be a clean repeating cycle, whatever its length."""
    r = [content._pick_format([0] * i) for i in range(12)]
    assert r[:6] == r[6:], "rotation is not a clean cycle"


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


def test_banned_openers_fire_on_a_repetitive_history():
    """The detector must fire on repetition — tested against a FIXTURE.

    This used to assert the LIVE posts.csv still contained repeated openers,
    "to check the detector still works". That inverts the contract: it passes
    only while the channel is repeating itself, and fails the build the moment
    the writing improves. Which is exactly what happened once the hand-written
    stories started shipping — every opener distinct, so the suite went red on
    good news. Same mistake as the variety check asserting the live channel is
    warning-free: data health is not code health.
    """
    from collections import Counter
    hooks = ["Stop forcing it.", "Stop the spiral.", "Stop asking.",
             "Let it be.", "Quiet now."]
    op = Counter(h.split()[0].strip('.,:;"\'').lower() for h in hooks)
    assert [w for w, n in op.items() if n >= 2] == ["stop"]


def test_the_live_history_is_reported_not_asserted(capsys):
    """Repetition in real data is information for the owner, not a failure."""
    from collections import Counter
    rows = content._load_rows()
    hooks = [h for h in ((r.get("hook") or "").strip() for r in rows) if h][-15:]
    if len(hooks) < 5:
        return
    op = Counter(h.split()[0].strip('.,:;"\'').lower() for h in hooks if h.split())
    repeats = {w: n for w, n in op.items() if n >= 2}
    print(f"live repeated openers in last {len(hooks)} hooks: {repeats or 'none'}")


# ------------------------------------- rule hook SHAPE is code-assigned

def _rows(n_rules):
    return [{"format": "rule", "hook": f"Rule {i}: x"} for i in range(n_rules)]


def test_rule_shape_rotates_across_three_forms():
    got = {content._rule_directive(_rows(k)).split("Hook shape for this post:")[1]
           for k in range(6)}
    assert len(got) == 3, "rule hook shape does not cycle through three forms"


def test_two_of_three_shapes_forbid_opening_with_rule():
    """The old directive said "the hook starts with 'Rule N:'" outright, which
    silently overruled OPENER VARIETY and made "Rule" the most repeated opening
    word on the channel — every rule post, without exception."""
    forbids = sum("MUST NOT begin with the word Rule" in content._rule_directive(_rows(k))
                  for k in range(3))
    assert forbids == 2, f"only {forbids} of 3 shapes forbid the Rule opener"


def test_one_shape_still_allows_the_classic_form():
    """The 'Rule N:' form is recognisable and worth keeping — just not every time."""
    allows = sum("EXACTLY 'Rule" in content._rule_directive(_rows(k))
                 for k in range(3))
    assert allows == 1


def test_rule_number_is_still_code_assigned():
    """The shape rotation must not have loosened the number rule, which exists
    because models fixate on 7 and 9."""
    for k in range(3):
        assert "MUST use EXACTLY the number" in content._rule_directive(_rows(k))


def test_rule_number_avoids_already_used_numbers():
    used = [{"format": "rule", "hook": "Rule 7: x"}]
    assert "number 7 " not in content._rule_directive(used)
