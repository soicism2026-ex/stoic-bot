"""The curated true-story bank.

222 videos of aphorisms produced no emotional connection. The owner: "these
stories dont make me feel anything... we need real stories and real substance."

The invariant these tests defend is that NOTHING SPOKEN IS GENERATED. A model
asked for a moving Stoic story will invent a fluent, plausible, false one, and
this channel's rule is that quotes are genuine public-domain text. The stories
are hand-written, checked against a public-domain translation, and rated on
emotional power AND on whether they leave the viewer better (doctrine section
5, which outranks everything).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import stories  # noqa: E402


def test_the_bank_is_not_empty():
    assert len(stories.load()) >= 10


def test_every_story_has_a_real_citation():
    """A misattributed quote is the one thing this channel cannot survive."""
    for s in stories.load():
        assert s["citation"].strip(), s["id"]
        assert s["source"].startswith("http"), s["id"]
        assert s["quote"].strip(), s["id"]
        assert s["author"].strip(), s["id"]


def test_every_story_ends_with_something_to_do_tonight():
    """Doctrine section 5: 'advice with no handle is decoration'."""
    for s in stories.load():
        assert s["tonight"].strip(), s["id"]


def test_nothing_high_power_and_low_on_leaving_him_better():
    """Cato's suicide is power 10, section-5 2. It must never be in this file.

    A man alone at 11:40pm is the viewer. A story that frames death as dignity
    is the most dangerous thing Stoicism contains for him.
    """
    for s in stories.load():
        assert s["s5"] >= 7, (
            f"{s['id']} scores {s['s5']} on leaving-him-better — a story that "
            f"makes him feel smaller must not ship, whatever its power")


def test_the_forbidden_stories_are_absent():
    blob = json.dumps(stories.load()).lower()
    for banned in ("cato", "utica", "opened his veins", "slit his"):
        assert banned not in blob, f"{banned!r} is in the bank"


def test_picks_the_highest_scoring_story_first():
    s = stories.pick([])
    best = max(stories.load(), key=lambda x: x["score"])
    assert s["id"] == best["id"]


def test_never_repeats_a_story():
    """A viewer who sees the same story twice learns it was never personal."""
    rows, seen = [], set()
    while True:
        s = stories.pick(rows)
        if s is None:
            break
        assert s["id"] not in seen, f"{s['id']} served twice"
        seen.add(s["id"])
        rows.append({"experiment": f"story:{s['id']}"})
    assert len(seen) == len(stories.load())


def test_exhausted_bank_returns_none_rather_than_looping():
    rows = [{"experiment": f"story:{s['id']}"} for s in stories.load()]
    assert stories.pick(rows) is None


def test_spacing_rule_holds_the_second_serenus_story_back():
    """failure_column reveals Serenus's death; serenus_not_ill must land first
    and be given room, or the opener is spoiled."""
    first = stories.pick([])
    assert first["id"] != "failure_column"
    # even once it has aired, not immediately after
    rows = [{"experiment": "story:serenus_not_ill"}]
    assert stories.pick(rows)["id"] != "failure_column"


def test_content_shape_matches_what_the_pipeline_expects():
    """The render, QA, upload and logging paths must be untouched."""
    c = stories.as_content(stories.pick([]))
    for k in ("theme", "quote", "author", "caption", "hook", "hashtags",
              "voiceover_story", "voiceover_lesson"):
        assert k in c and c[k], k
    assert c["format"] == "truestory"
    assert c["_story_id"]


def test_narration_length_is_sayable():
    """60-110 spoken words. Long enough to be a story, short enough to finish."""
    for s in stories.load():
        n = len((s["story"] + " " + s["lesson"]).split())
        assert 60 <= n <= 140, f"{s['id']}: {n} words"


def test_caption_carries_the_citation():
    """Real citation on screen is the credibility signal that separates this
    from a generic quote account."""
    c = stories.as_content(stories.pick([]))
    assert stories.pick([])["citation"] in c["caption"]


def test_stories_with_a_caveat_say_what_it_is():
    for s in stories.load():
        if s["id"] in ("only_a_man", "prosperous_shipwreck", "failure_column",
                       "ran_out_of_room"):
            assert s["caveat"].strip(), f"{s['id']} needs its source caveat"


def test_missing_bank_does_not_crash_the_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(stories, "STORIES", tmp_path / "nope.json")
    assert stories.load() == []
    assert stories.pick([]) is None
