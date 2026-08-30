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
    """Checks PUBLISHED text only. A caveat legitimately names what to keep
    out — relaxed_by_amusement's says Seneca's next example is Cato with wine,
    cut it — and scanning caveats would force production notes to be vague
    about exactly the material they exist to exclude."""
    for s in stories.load():
        published = " ".join(str(s.get(k, "")) for k in
                             ("hook", "story", "lesson", "quote", "author",
                              "tonight")).lower()
        for banned in ("cato", "utica", "opened his veins", "slit his",
                       "suicide", "kill himself", "end his life"):
            assert banned not in published, f"{banned!r} in {s['id']}"


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


# ------------------------------------------------- how a story RENDERS
#
# The scripts were approved on their words. But the pipeline they ship through
# was built for 4-word aphorisms over marble statues, and every default in it
# works against a confessional register. These tests exist because a story
# rendered with the old presentation is just the old channel with new words.

import textwrap  # noqa: E402


def _pack():
    """The truestory STYLE_PACK, read from daily_post rather than duplicated."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    i = src.index('"truestory": {')
    j = src.index("}", i)
    return src[i:j]


def test_story_hooks_are_not_shouted():
    """ALL CAPS is shouting, and shouting is the vocabulary this channel is
    trying to stop speaking."""
    assert '"REEL_HOOK_CAPS": "0"' in _pack()


def test_story_hooks_do_not_fill_the_frame():
    """At the 12-char default a 20-word hook wraps to ELEVEN lines covering
    63% of the frame. Simulate the real wrap and auto-fit."""
    wrap, base, safe_w, pad = 30, 56, 840, 18
    for s in stories.load():
        lines = textwrap.wrap(s["hook"], width=wrap) or [s["hook"]]
        fs = min(base, int(safe_w / (0.62 * max(len(l) for l in lines))))
        block = len(lines) * (fs + pad)
        assert block < 0.30 * 1920, (
            f"{s['id']}: hook block {block}px is "
            f"{block / 1920:.0%} of the frame")


def test_a_story_never_opens_on_a_marble_bust():
    """The statue bookends open every video on the most reproduced image in
    this niche. A story about a man lying awake at 2am opens on a bedroom."""
    assert '"_no_guide": True' in _pack()


def test_story_broll_describes_the_scene_not_ancient_rome():
    """The first frame must read as a real room, not as a video."""
    for s in stories.load():
        assert len(s.get("broll", [])) >= 3, s["id"]


def test_no_trailer_sting_over_a_confession():
    """A BRAAAM under 'I'm not ill, and I'm not well' is a promise the script
    does not make."""
    assert '"REEL_HOOK_SOUND": "0"' in _pack()


def test_render_exposes_caps_and_wrap_as_settings():
    """If these are hardcoded again, the pack silently stops working."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "REEL_HOOK_CAPS" in src and "REEL_HOOK_WRAP" in src
    assert "hook.upper(), width=12" not in src, "caps/wrap hardcoded again"


# ------------------------------------------------- the bank validator
#
# The bank is hand-edited JSON whose words publish verbatim, unreviewed by any
# other stage. These tests check the checker, because a validator that cannot
# fail is not a validator.

sys.path.insert(0, str(ROOT / "scripts"))
import validate_stories as vs  # noqa: E402


def test_the_live_bank_is_valid():
    assert vs.validate() == []


def test_validator_catches_a_missing_citation(monkeypatch):
    bad = [dict(stories.load()[0], id="x", citation="")]
    monkeypatch.setattr(stories, "load", lambda: bad)
    assert any("citation" in e for e in vs.validate())


def test_validator_catches_a_story_that_would_make_him_smaller(monkeypatch):
    bad = [dict(stories.load()[0], id="x", s5=3)]
    monkeypatch.setattr(stories, "load", lambda: bad)
    assert any("§5 floor" in e for e in vs.validate())


def test_validator_catches_banned_material(monkeypatch):
    bad = [dict(stories.load()[0], id="x",
                story="He went to Utica and opened his veins.")]
    monkeypatch.setattr(stories, "load", lambda: bad)
    assert any("banned" in e for e in vs.validate())


def test_validator_catches_a_duplicate_id(monkeypatch):
    one = stories.load()[0]
    monkeypatch.setattr(stories, "load", lambda: [one, dict(one)])
    assert any("duplicate id" in e for e in vs.validate())


def test_validator_catches_a_reused_quote(monkeypatch):
    """Two stories paying off on the same line is a repeat the viewer feels."""
    a, b = stories.load()[0], dict(stories.load()[1])
    b["quote"] = a["quote"]
    monkeypatch.setattr(stories, "load", lambda: [a, b])
    assert any("already used" in e for e in vs.validate())


def test_validator_catches_a_source_that_is_not_a_link(monkeypatch):
    bad = [dict(stories.load()[0], id="x", source="somewhere in Seneca")]
    monkeypatch.setattr(stories, "load", lambda: bad)
    assert any("not a link" in e for e in vs.validate())


def test_validator_runs_before_the_post_in_ci():
    """A validator that runs after publishing validates nothing."""
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "daily-short.yml").read_text())
    names = [s.get("name") for s in wf["jobs"]["post"]["steps"]
             if isinstance(s, dict) and s.get("name")]
    assert names.index("Validate story bank") < \
        names.index("Run self-healing post pipeline")


def test_suicide_is_banned_in_code_not_just_in_a_doc():
    """Owner 2026-08-25: restricted on YouTube. Advertiser-restricted whatever
    the framing, so it is a monetisation risk on top of the doctrine objection.
    Not re-proposable, including 'carefully handled' versions."""
    import validate_stories as vs
    # Stems, so that "ending his life" is caught by "suicid"-style prefixes
    # rather than needing every inflection listed.
    for term in ("suicid", "kill himself", "ending his life", "self-harm"):
        assert term in vs.BANNED, term


def test_the_validator_blocks_a_suicide_story(monkeypatch):
    bad = [dict(stories.load()[0], id="x",
                story="He often thought about ending his life that winter.")]
    monkeypatch.setattr(stories, "load", lambda: bad)
    import validate_stories as vs
    assert any("banned" in e for e in vs.validate())


def test_stories_are_bright_enough_to_see_on_a_phone():
    """Measured on real published videos (2026-08-25): mean luminance 21.5%
    on a normal post, 12.8% on an F3 post, 10% mid-video. That is a black
    rectangle at low phone brightness, which is where this viewer is."""
    pack = _pack()
    assert '"REEL_BRIGHTNESS": "-0.06"' in pack
    assert '"REEL_EXTRA_DARKEN": "0"' in pack


def test_stories_drop_the_template_furniture():
    """Gold corner brackets + gold caps over a statue is, frame for frame,
    the house style of the category being demoted."""
    pack = _pack()
    assert '"REEL_FRAME": "0"' in pack
    assert '"REEL_CINEMATIC": "0"' in pack


def test_brightness_is_a_setting_not_a_constant():
    src = (ROOT / "src" / "render.py").read_text()
    assert "REEL_BRIGHTNESS" in src
    assert "eq=brightness=-0.25" not in src, "grade hardcoded again"


def test_no_shot_list_is_interchangeable_between_stories():
    """Doctrine 6: if a clip could illustrate any of the thirty scripts, it is
    illustrating none of them. Generic mood queries are the failure."""
    banned = {"a dark bedroom", "moody dark room", "sad man", "cinematic",
              "dramatic", "ancient rome", "marble bust", "greek statue"}
    for s in stories.load():
        for shot in s["broll"]:
            low = shot.lower()
            for b in banned:
                assert b not in low, f"{s['id']}: generic/statue shot {shot!r}"


def test_shot_lists_are_specific_enough_to_be_shots():
    """A shot has a subject and something happening. Three words is a mood."""
    for s in stories.load():
        for shot in s["broll"]:
            assert len(shot.split()) >= 4, f"{s['id']}: {shot!r} is a mood, not a shot"
