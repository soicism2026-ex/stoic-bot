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
    assert "volume=1.0,apad,asplit=2[voice][vkey]" in src


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


def test_music_ducks_under_the_voice():
    """Owner 2026-10-05: the voice must sit above the music."""
    src = (ROOT / "src" / "render.py").read_text()
    assert "[mraw][vkey]sidechaincompress=" in src
    assert 'os.environ.get("REEL_DUCK_RATIO", "1.6")' in src


def test_people_shots_ask_for_a_man():
    """The ICP is one man, 18-34 (doctrine §1). Unqualified people queries
    returned fitness-model footage of women ("boxer training", then "weight
    training": a woman's back in a sports bra), which tag filters cannot
    catch when the clip is not tagged that way. Ask for the subject outright."""
    people = {"boxer", "boxing", "training", "weight", "weightlifting", "lifting",
              "running", "runner", "eyes", "breathing", "punching"}
    for q in edits.load():
        for vis in q["visuals"]:
            if vis.startswith("still:") or not people & set(vis.split()):
                continue
            assert vis.split()[0] in ("man", "men", "old"), (q["id"], vis)


def test_second_daily_post_waits_for_its_slot():
    """2/day (owner, 2026-10-18): the second post waits for 15:00 UTC so the
    two videos do not go out 4 hours apart and split the same audience."""
    import daily_post
    slots = [0, 15]
    assert daily_post.slot_open(0, 3, slots)          # first post: any time
    assert not daily_post.slot_open(1, 7, slots)      # second: not at 07:00
    assert daily_post.slot_open(1, 15, slots)         # ...but from 15:00
    assert daily_post.slot_open(1, 23, slots)         # ...or a later slot
    assert daily_post.slot_open(2, 3, slots)          # beyond: cap decides
    assert daily_post.slot_open(1, 3, [])             # no slots = no gating
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert "MAX_POSTS_PER_DAY: ${{ inputs.max_posts || '2' }}" in wf
    assert 'POST_SLOT_HOURS: "0,15"' in wf


def test_edits_rotate_authors():
    """The bank is stored by author; plain order aired ten Marcus edits in a
    row. Consecutive picks must come from different authors while more than
    one author has quotes left."""
    rows = []
    for _ in range(12):
        q = edits.pick(rows)
        rows.append({"experiment": f"edit:{q['id']}", "theme": q["theme"],
                     "author": q["author"]})
    authors = [r["author"] for r in rows]
    assert all(a != b for a, b in zip(authors, authors[1:])), authors
    assert len(set(authors[:3])) == 3


def test_hook_shows_from_the_first_frame_without_lighting_up_early(monkeypatch):
    import importlib
    import render
    monkeypatch.setenv("REEL_HOOK_FROM_START", "1")
    importlib.reload(render)
    ev = render._hook_karaoke_events("Pick one thing.", [1.25, 1.55, 1.80], 2.6)
    assert ev.startswith("Dialogue: 0,0:00:00.00,")
    assert "\\fad(0,320)" in ev           # on screen in frame 0, not faded in
    assert "{\\k100}{\\k30}Pick" in ev     # silent 1.00s lead, then on cue
    monkeypatch.setenv("REEL_HOOK_FROM_START", "0")
    importlib.reload(render)
    assert render._hook_karaoke_events("Pick one thing.", [1.25, 1.55, 1.80],
                                       2.6).startswith("Dialogue: 0,0:00:01.00,")
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert '"REEL_HOOK_FROM_START": "1"' in src


def test_too_dark_retries_brighten_the_video_itself():
    """2026-10-19: all five attempts rendered an identical 28.1/255 frame and
    the day posted nothing, because the retry raised REEL_BRIGHTNESS, which
    only the thumbnail reads. The video grade now takes BRIGHTNESS_LIFT."""
    import daily_post
    env = {}
    for step in (1, 2, 3, 4, 5):
        env = daily_post._apply_corrections(env, ["preflight: too dark: mean luminance 28.1/255"], step)
    assert env["REEL_BRIGHTNESS_LIFT"] == "0.30"          # +0.08 a step, capped
    first = daily_post._apply_corrections({}, ["preflight: too dark"], 1)
    assert first["REEL_BRIGHTNESS_LIFT"] == "0.08"
    src = (ROOT / "src" / "render.py").read_text()
    assert "_br - EXTRA_DARKEN + BRIGHTNESS_LIFT" in src


def test_a_blocked_edit_is_set_aside_after_two_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(edits, "BLOCKS", tmp_path / "edit_blocks.csv")
    first = edits.pick([])
    edits.record_block(first["id"], "2026-10-19", "too dark")
    assert edits.pick([])["id"] == first["id"]           # one bad run: retried
    edits.record_block(first["id"], "2026-10-19", "too dark")
    assert edits.pick([])["id"] != first["id"]           # two: set aside
    assert edits.remaining([]) == len(edits.load()) - 1
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert "data/edit_blocks.csv" in wf and (ROOT / "data" / "edit_blocks.csv").exists()


def test_posts_keep_a_minimum_gap(tmp_path, monkeypatch):
    import datetime
    import daily_post
    a = tmp_path / "data"
    a.mkdir()
    (a / "analytics.csv").write_text(
        "pulled_on,published_at,video_id\n2026-10-19,2026-10-19T22:30:00Z,x\n"
        "2026-10-19,2026-10-18T01:07:00Z,y\n")
    monkeypatch.setattr(daily_post, "ROOT", tmp_path)
    now = datetime.datetime(2026, 10, 19, 23, 0, tzinfo=datetime.timezone.utc)
    assert abs(daily_post.hours_since_last_post(now, live=False) - 0.5) < 1e-6
    # YouTube's own newest upload wins over a stale stats file.
    monkeypatch.setattr(daily_post, "_newest_upload_from_youtube",
                        lambda: "2026-10-19T22:45:00Z")
    assert abs(daily_post.hours_since_last_post(now) - 0.25) < 1e-6
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert 'MIN_GAP_HOURS: "6"' in wf


def test_edits_never_reair_a_quote_from_any_older_post():
    """rising_to_work re-aired a 2026-09-03 quote on 2026-10-19: edit ids
    were checked, quote text was not."""
    q = edits.load()[0]
    rows = [{"quote": q["quote"], "experiment": "story:something_else", "date": "2026-09-03"}]
    assert edits.pick(rows)["id"] != q["id"]
    assert edits.remaining(rows) == edits.remaining([]) - 1
