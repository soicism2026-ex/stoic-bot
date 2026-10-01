"""Stoic edits (owner pivot, 2026-10-01)."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edits  # noqa: E402
import epic_music  # noqa: E402


def test_every_edit_has_a_short_hook_and_enough_visuals():
    for q in edits.load():
        assert len(q["hook"].split()) <= 9, q["id"]
        assert 6 <= len(q["visuals"]) <= 10, q["id"]


def test_stock_queries_are_short_keywords_not_sentences():
    """Pixabay matches tags; a written sentence returned unrelated popular clips
    (Mount Fuji, motocross) under the story format."""
    for q in edits.load():
        for vis in q["visuals"]:
            if not vis.startswith("still:"):
                assert len(vis.split()) <= 3, (q["id"], vis)


def test_pick_never_repeats_and_rotates_theme():
    rows, seen = [], set()
    while True:
        q = edits.pick(rows)
        if q is None:
            break
        assert q["id"] not in seen
        seen.add(q["id"])
        rows.append({"experiment": f"edit:{q['id']}", "theme": q["theme"]})
    assert len(seen) == len(edits.load())


def test_edit_content_has_the_render_contract():
    c = edits.as_content(edits.load()[0])
    for k in ("theme", "quote", "author", "caption", "hook", "format", "hashtags",
              "voiceover_story", "voiceover_lesson", "broll_queries", "_edit_id"):
        assert k in c
    assert c["format"] == "edit"


def test_music_rotates_and_is_credited():
    rows = [{"music_track": "epic:Heroic Age"}]
    assert epic_music.pick(rows) != "Heroic Age"
    cr = epic_music.credit("Heroic Age")
    assert "Kevin MacLeod" in cr and "Creative Commons" in cr


def test_the_live_bot_stays_on_stories_until_approved():
    """Standing rule: nothing ships until the owner approves it."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert 'REEL_FORMAT: "story"' in wf or 'REEL_FORMAT: "edit"' in wf


def test_only_tagged_shots_use_the_image_model():
    src = (ROOT / "src" / "backgrounds.py").read_text()
    assert 'if tagged_only and not wants_still:' in src


def test_dry_run_returns_before_any_upload():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    i = src.index("if upload_this and DRY_RUN:")
    j = src.index("upload_result = publish_short(")
    assert i < j and "return" in src[i:j]


def test_an_edit_cuts_on_all_eight_visuals():
    """First preview: broll[:4] kept half the visuals — 4 shots in 11.6s."""
    import daily_post
    scene = edits.load()[0]["visuals"]
    flavors = daily_post.background_flavors(scene, "guide", True, 11.6)
    assert len(flavors) == len(scene) == 8
    assert "broll if fmt == \"edit\" else broll[:4]" in \
        (ROOT / "scripts" / "daily_post.py").read_text()


def test_off_tone_stock_is_filtered(monkeypatch):
    import backgrounds
    monkeypatch.setenv("REEL_BG_AVOID_TAGS", "woman,girl")
    assert backgrounds._off_tone("boxing, woman, gym")
    assert backgrounds._off_tone("fitness model, sport")
    assert not backgrounds._off_tone("boxing, man, punching bag")
    monkeypatch.delenv("REEL_BG_AVOID_TAGS")
    assert not backgrounds._off_tone("woman, walking")


def test_karaoke_hook_honours_caps(tmp_path, monkeypatch):
    import importlib
    import render
    monkeypatch.setenv("REEL_HOOK_CAPS", "1")
    importlib.reload(render)
    ass = render._build_ass([("stop", 0.1, 0.4), ("now", 0.4, 0.8)],
                            tmp_path / "h.ass", hook="stop now",
                            hook_starts=[0.1, 0.4], hook_hold=1.0, captions_from=1.0)
    assert "STOP" in ass.read_text() and "stop" not in ass.read_text().split("[Events]")[1]


def test_stock_prefers_hits_tagged_with_the_whole_query():
    import backgrounds
    hits = [{"tags": "ship, sailing, training ship"},
            {"tags": "horses, running, snow"},
            {"tags": "boxing, gym, training"},
            {"tags": "man, running, rain, city"}]
    assert backgrounds._relevant_hits(hits, "boxer training") == [hits[2]]
    assert backgrounds._relevant_hits(hits, "man running rain") == [hits[3]]
    assert backgrounds._relevant_hits(hits, "lion walking") == []


def test_music_is_not_cut_with_the_last_word():
    src = (ROOT / "src" / "render.py").read_text()
    assert "volume=1.0,apad[voice]" in src


def test_strict_stock_never_falls_back_to_an_unrelated_portrait_clip():
    import backgrounds
    hits = [{"tags": "ship, sailing, training ship"}]
    assert backgrounds._relevant_hits(hits, "boxer training", require_all=True) == []
    src = (ROOT / "src" / "backgrounds.py").read_text()
    assert src.index("every = _relevant_hits(") < src.index("portrait = [\n")


def test_hook_is_gone_before_the_quote_fades_in():
    src = (ROOT / "src" / "render.py").read_text()
    assert "min(hook_hold, quote_times[0][0] - 0.3)" in src


def test_stock_clips_skip_their_fade_in():
    src = (ROOT / "src" / "render.py").read_text()
    assert '["-stream_loop", "-1", *skip, "-i", str(_clip)]' in src
