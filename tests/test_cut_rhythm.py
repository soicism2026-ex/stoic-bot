"""
The cut rhythm of the story format.

WHY THIS FILE EXISTS: the visual reviewer watched 206 of this channel's videos
and scored `pacing` lower than every other dimension — mean 5.4 against 7.9
for legibility — and flagged it 62 times, more than any other dimension. Its
words, over and over: frames "visually identical", "no motion", "static feel
during the crucial first 1.5s".

The cause was arithmetic, and it was mine. Cutting the statue bookends off the
story format was right, but it took the slot count from 6 to 4, and a measured
production run put 52.4 seconds of narration across those four shots — 13.1
SECONDS on one frame, against a short-form benchmark of a cut every 1.5-2.5s.

These tests hold the shot list to a cut-rhythm bar, and — because the fix
depends on behaviour that lives in two other modules — they also pin the two
things elsewhere that would silently un-fix it.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import stories  # noqa: E402
import daily_post as dp  # noqa: E402

# Words per second, MEASURED — not assumed. The 2026-09-17 production log:
# "two-part narration — story 29.6s, read beat 2.4s, total 52.4s" for the
# `failure_column` script, whose spoken text is 139 words. Every duration
# estimate below is calibrated to that one real render.
MEASURED_WPS = 139 / 52.4

SCENE = ["an empty chair by a rain-streaked window",
         "a name written on paper, hand still resting on it",
         "a table set for two with one place untouched",
         "a candle burning down to nothing"]
GUIDE = "marble bust ancient philosopher lit by warm candlelight, dark room"


def _spoken_seconds(story: dict) -> float:
    spoken = f"{story['hook'].rstrip('.!? ')}. {story['story']} {story['lesson']}"
    return len(spoken.split()) / MEASURED_WPS


# --------------------------------------------------------------- the bar

def test_no_story_leaves_one_frame_on_screen_past_the_bar():
    """Every script in the bank, at its own measured length."""
    for s in stories.load():
        secs = _spoken_seconds(s)
        flavors = dp.background_flavors(s["broll"], GUIDE, True, secs)
        per_clip = secs / len(flavors)
        assert per_clip <= dp.MAX_SECONDS_PER_CLIP + 0.01, (
            f"{s['id']}: {per_clip:.1f}s per clip over "
            f"{len(flavors)} shots — bar is {dp.MAX_SECONDS_PER_CLIP}s")


def test_the_shot_list_that_actually_shipped_would_fail_that_bar():
    """The regression this file exists for. A bar nothing can fail is not a
    bar, so prove the four-shot list breaks it at the real 52.4s length."""
    four = dp.background_flavors(SCENE, GUIDE, True, 0.0)
    assert len(four) == 4
    assert 52.4 / len(four) > dp.MAX_SECONDS_PER_CLIP


def test_a_measured_production_story_gets_the_benchmark_rhythm():
    """52.4s of narration over four written beats."""
    flavors = dp.background_flavors(SCENE, GUIDE, True, 52.4)
    assert len(flavors) == 12
    assert 52.4 / len(flavors) < 4.5


def test_sizing_is_driven_by_length_not_by_a_fixed_multiplier():
    """A short script must not get twelve cuts just because a long one did."""
    short = dp.background_flavors(SCENE, GUIDE, True, 18.0)
    long = dp.background_flavors(SCENE, GUIDE, True, 52.4)
    assert len(short) < len(long)
    assert len(short) == 4, "18s over four beats is already 4.5s a shot"


def test_with_no_length_information_it_asks_for_one_shot_per_beat():
    """Unknown duration must not silently multiply the download count."""
    assert dp.background_flavors(SCENE, GUIDE, True, 0.0) == SCENE
    assert dp.background_flavors(SCENE, GUIDE, True, -3.0) == SCENE


def test_the_beats_still_run_in_narration_order():
    """The whole point of scene-matched b-roll is that the picture tracks the
    words. Reordering or dropping a beat breaks that."""
    flavors = dp.background_flavors(SCENE, GUIDE, True, 52.4)
    assert [q for i, q in enumerate(flavors) if i == 0 or q != flavors[i - 1]] == SCENE


# ------------------------------------------- what the repeat is allowed to do

def test_it_never_asks_for_more_shots_than_the_relevance_window_holds():
    """A 4th request of the same query returns a clip already used, because
    backgrounds.py only picks from the top-N most relevant results."""
    import backgrounds
    assert dp.MAX_SHOTS_PER_BEAT == backgrounds.BG_TOP_N
    absurd = dp.background_flavors(SCENE, GUIDE, True, 600.0)
    assert len(absurd) == len(SCENE) * dp.MAX_SHOTS_PER_BEAT


def test_slots_sharing_a_query_come_back_with_different_footage():
    """The fix is worthless if the repeated slots return the SAME clip.

    render.py sets REEL_BG_OFFSET = base + i*7 per slot and backgrounds.py
    picks result index (today + offset) % window. Check the real functions,
    for every possible day, that the slots sharing one query resolve to
    distinct results."""
    import os

    import backgrounds
    prev = os.environ.get("REEL_BG_OFFSET")
    try:
        for base in range(7):                       # QA retry attempts
            for beat in range(len(SCENE)):
                slots = [beat * dp.MAX_SHOTS_PER_BEAT + k
                         for k in range(dp.MAX_SHOTS_PER_BEAT)]
                picks = []
                for slot in slots:
                    os.environ["REEL_BG_OFFSET"] = str(base + slot * 7)
                    picks.append(backgrounds._relevant_index(pool_len=20))
                assert len(set(picks)) == len(picks), (
                    f"base={base} beat={beat} slots={slots} -> {picks}")
    finally:
        if prev is None:
            os.environ.pop("REEL_BG_OFFSET", None)
        else:
            os.environ["REEL_BG_OFFSET"] = prev


def test_render_still_spaces_the_pick_per_slot():
    """If this line goes, every repeated slot downloads the identical clip and
    the cut rhythm quietly reverts to a slideshow with more steps."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "_i * 7" in src, "REEL_BG_OFFSET per-slot spacing removed"
    assert 'os.environ.get("REEL_BG_CLIPS"' in src


# ------------------------------------------------------- the other formats

def test_guide_formats_keep_their_bookends():
    flavors = dp.background_flavors(SCENE, GUIDE, False, 52.4)
    assert flavors[0] == GUIDE and flavors[-1] == GUIDE
    assert flavors[1:-1] == SCENE


def test_a_format_with_no_scene_list_still_renders():
    assert dp.background_flavors([], GUIDE, False, 52.4) == [GUIDE, GUIDE]
    assert dp.background_flavors([], GUIDE, True, 52.4) == [GUIDE, GUIDE]


def test_daily_post_sizes_the_list_from_the_real_voiceover():
    """The call site must pass the measured narration length. Passing nothing
    is the bug this file is about, and it is invisible in a render."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "spoken_seconds = float(word_timings[-1][2])" in src
    assert "background_flavors(scene, guide, no_guide, spoken_seconds)" in src


# ---------------------------------------------- why shorter segments also move

def test_the_camera_move_is_per_segment_so_shorter_shots_move_faster():
    """The reviewer's actual complaint was "no motion", not "no cuts".

    render.py traverses the FULL move amplitude over one segment's frames, so
    thirteen seconds of `push` is imperceptible and four seconds of it is
    visible. Halving segment length triples the apparent speed for free — but
    only while the move stays per-segment rather than stretched across the
    whole video."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "seg_dur = dur / n_bg" in src
    assert "seg_frames = max(1, int(seg_dur * 30))" in src
    assert "_motion(_i, seg_frames)" in src, "camera move no longer per-segment"


def test_shots_on_the_same_beat_get_different_camera_moves():
    """Three clips of one narration beat should not all push in."""
    import render
    for beat in range(len(SCENE)):
        slots = [beat * dp.MAX_SHOTS_PER_BEAT + k
                 for k in range(dp.MAX_SHOTS_PER_BEAT)]
        moves = [render._MOVES[s % len(render._MOVES)] for s in slots]
        assert len(set(moves)) == len(moves), f"beat {beat}: {moves}"


def test_the_download_count_stays_inside_the_run_budget():
    """The 09-05 outage was a render that got too expensive, so a change that
    multiplies downloads has to be bounded.

    MEASURED: the 2026-09-17 production log fetched 4 Pixabay clips in 9.5s
    (~2.4s each), and rendering was FLAT in clip count locally — 151.3s at 4
    clips, 145.0s at 8, 144.3s at 12 — because each clip is trimmed to
    `dur / n_bg`, so total decode work is fixed by the output length. The only
    real added cost is the extra fetches."""
    worst = max(len(dp.background_flavors(s["broll"], GUIDE, True, 600.0))
                for s in stories.load())
    assert worst <= 12
    assert worst * 2.4 < 0.03 * dp.POST_BUDGET_SECONDS, "fetches eat the budget"
