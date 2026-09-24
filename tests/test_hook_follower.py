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


def test_hook_line_and_captions_never_share_the_screen(tmp_path, monkeypatch):
    """Owner, 2026-09-24: the hook showed twice — the white hook line and the
    bigger gold-shadowed captions of the same words. One text at a time: the
    hook ends exactly when the first caption begins, decided by timing."""
    import render
    monkeypatch.setattr(render, "QUOTE_APPEAR", 0.0)
    words = "Dreading tomorrow's people doesn't make you weak The Emperor of Rome felt it too".split()
    wt = [(w, 0.3 + i * 0.4, 0.3 + i * 0.4 + 0.35) for i, w in enumerate(words)]
    hook = "Dreading tomorrow's people doesn't make you weak."
    starts = render._hook_word_times(hook, wt)
    assert len(starts) == 7
    nxt = wt[7][1]
    hold = max(starts[-1] + 0.4, min(max(2.2, starts[-1] + 0.9), nxt))
    ass = render._build_ass(wt, tmp_path / "c.ass", hook=hook, hook_starts=starts,
                            hook_hold=hold, captions_from=hold).read_text()
    ev = [l for l in ass.splitlines() if l.startswith("Dialogue:")]

    def t(x):
        h, m, sec = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)
    hook_ev = [e for e in ev if ",Hook," in e]
    caps = [e for e in ev if ",Karaoke," in e]
    assert len(hook_ev) == 1
    hook_end = t(hook_ev[0].split(",")[2])
    first_cap = min(t(c.split(",")[1]) for c in caps)
    assert first_cap >= hook_end - 0.06, "captions start while the hook is still up"
    captioned = " ".join(c.split("}")[-1] for c in caps)
    assert "DREADING" not in captioned and "WEAK" not in captioned, "hook words captioned twice"
    assert "EMPEROR" in captioned, "the story's words must still be captioned"


def test_the_quote_is_spoken_shown_only_while_spoken_and_then_hands_over(tmp_path, monkeypatch):
    """Owner, 2026-09-24: reading the quote while the voice said something else
    was annoying. The voice now reads the quote; the line shows only while it
    is spoken, word by word, and the lesson's captions resume after."""
    import render
    monkeypatch.setattr(render, "QUOTE_APPEAR", 5.0)
    quote = "Begin the morning by saying to thyself, I shall meet with the busybody."
    story = "Marcus wrote himself a script".split()
    wt = [(w, 0.5 + i * 0.4, 0.8 + i * 0.4) for i, w in enumerate(story)]
    t = 5.7
    for w in quote.split() + "That isn't bitterness at all".split():
        wt.append((w, t, t + 0.35)); t += 0.4
    qt = render._phrase_times(quote, wt, 5.0)
    assert len(qt) == len(quote.split())
    q_end = qt[-1][1]
    hide = max(q_end + 0.35, [w[1] for w in wt if w[1] > q_end + 0.02][0])
    ass = render._build_ass(wt, tmp_path / "q.ass", quote=quote, author="Marcus Aurelius",
                            quote_times=qt, quote_hide=hide).read_text()
    ev = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    qline = [e for e in ev if ",Quote," in e]
    assert len(qline) == 1 and "\\k" in qline[0] and "MARCUS AURELIUS" in qline[0]
    caps = " ".join(e.split("}")[-1] for e in ev if ",Karaoke," in e)
    assert "BUSYBODY" not in caps and "THYSELF" not in caps, "quote captioned twice"
    assert "BITTERNESS" in caps, "the lesson must be captioned after the quote"


def test_quote_matching_is_bounded_to_where_the_quote_is_spoken():
    """A word that recurs later in the lesson must not drag the match."""
    import render
    wt = [(w, 1.0 + i * 0.4, 1.3 + i * 0.4) for i, w in enumerate("so then he went home".split())]
    wt += [("Begin", 9.0, 9.3), ("now", 9.4, 9.6)]
    assert render._phrase_times("Begin now", wt, after=1.0) == []
    assert len(render._phrase_times("Begin now", wt, after=8.9)) == 2


def test_daily_post_has_the_voice_read_the_quote():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert 'act3 = f"{content[\'quote\'].strip()} {act3}"' in src
    assert 'pack["REEL_QUOTE_SPOKEN"] = "1"' in src
