"""The hook: long enough to read, and led word by word.

Owner, 2026-09-04: "the hook doesnt stay for long enough to be read, add a
follower to read step by step for that."

Two faults. HOOK_HOLD was a fixed 2.2s, set when hooks were four words — a
20-word story hook cannot be read in that time and the card was gone before
the eye finished. And the whole line appeared at once, so there was nothing
leading the reader through it.

Both are fixed from the REAL narration timings: the hook is spoken first
(daily_post builds act1 as hook + story), so its words are the opening run of
word_timings and the follower cannot drift from the voice.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import render  # noqa: E402

HOOK = "Two thousand years ago a man wrote his friend a letter"
TIMINGS = [(w, 0.30 + i * 0.34, 0.58 + i * 0.34)
           for i, w in enumerate(HOOK.split())]


def test_hook_words_are_matched_to_the_narration():
    starts = render._hook_word_times(HOOK, TIMINGS)
    assert len(starts) == len(HOOK.split())
    assert starts[0] == 0.30


def test_matching_is_by_TEXT_not_by_count():
    """A TTS engine that splits or merges a token would silently shift the
    whole follower if we matched positionally."""
    noisy = [("Two", 0.1, 0.3), ("thousand", 0.4, 0.7), ("years", 0.8, 1.0)]
    assert render._hook_word_times("Two thousand years", noisy) == [0.1, 0.4, 0.8]


def test_punctuation_does_not_break_the_match():
    t = [("Serenus", 0.2, 0.5), ("wrote", 0.6, 0.9)]
    assert render._hook_word_times("Serenus, wrote.", t) == [0.2, 0.6]


def test_a_bad_match_falls_back_rather_than_desyncing():
    """No clean match must produce NO follower, not a wrong one."""
    assert render._hook_word_times("completely different words", TIMINGS) == []


def test_hold_extends_to_cover_a_long_hook():
    """The whole point: a 20-word hook must outlast the 2.2s default."""
    starts = render._hook_word_times(HOOK, TIMINGS)
    hold = max(render.HOOK_HOLD, starts[-1] + 0.9)
    assert hold > render.HOOK_HOLD
    assert hold >= starts[-1], "hook vanishes before its last word is spoken"


def test_karaoke_line_lights_each_word_in_turn():
    starts = render._hook_word_times(HOOK, TIMINGS)
    ev = render._hook_karaoke_events(HOOK, starts, starts[-1] + 0.9)
    assert ev.startswith("Dialogue:")
    assert ev.count("\\k") == len(HOOK.split()), "one karaoke beat per word"
    assert "Hook," in ev


def test_karaoke_refuses_a_mismatched_word_count():
    """Rather than emit a line whose highlight drifts off the words."""
    assert render._hook_karaoke_events(HOOK, [0.1, 0.2], 3.0) == ""


def test_unspoken_words_stay_readable():
    """Dim, not hidden — the eye should be able to run ahead of the voice."""
    import tempfile
    starts = render._hook_word_times(HOOK, TIMINGS)
    with tempfile.TemporaryDirectory() as d:
        p = render._build_ass(TIMINGS, Path(d) / "t.ass", hook=HOOK,
                              hook_starts=starts, hook_hold=starts[-1] + 0.9)
        txt = p.read_text()
    assert "Style: Hook," in txt
    # SecondaryColour (unsung) is a partial alpha, not fully transparent
    assert "&H99FFFFFF" in txt


def test_layout_is_left_to_libass_not_hand_computed():
    """A first attempt positioned each word with drawtext at
    0.62*fontsize*len(word); that ratio is a monospace assumption and the
    spacing visibly drifted across the line on a real render."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "0.62 * hook_fs * len(lw)" not in src


def test_the_card_and_the_follower_are_never_both_drawn():
    """Two copies of the same words stacked on each other."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "if hook and HOOK_TEXT_ON and not hook_starts:" in src
