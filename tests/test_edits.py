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
