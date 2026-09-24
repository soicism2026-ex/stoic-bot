"""Storyboards in the daily pipeline: only approved boards air, timing follows
the voice, and a failed shot never costs the post."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import storyboard  # noqa: E402

BOARD = {"status": "approved", "shots": [
    {"model": "wan", "seconds": 3.5, "picture": "a"},
    {"model": "wan", "seconds": 3.5, "picture": "b"},
    {"model": "wan", "seconds": 5.5, "picture": "q", "quote": True},
    {"model": "wan", "seconds": 4.0, "picture": "c"}]}


def test_quote_shot_starts_exactly_when_the_quote_appears():
    secs = storyboard.plan_seconds(BOARD, quote_at=12.0, total=34.0)
    assert abs(sum(secs[:2]) - 12.0) < 1e-6
    assert abs(sum(secs) - 34.0) < 1e-6
    assert secs[2] > secs[3], "the plan's proportions survive the scaling"


def test_without_a_usable_quote_time_it_scales_evenly():
    secs = storyboard.plan_seconds(BOARD, quote_at=0, total=33.0)
    assert abs(sum(secs) - 33.0) < 1e-6


def test_only_approved_boards_air(tmp_path, monkeypatch):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"x": dict(BOARD, status="draft"), "y": BOARD}))
    monkeypatch.setattr(storyboard, "BOARDS", f)
    assert storyboard.load("x") is None
    assert storyboard.load("y") is not None
    assert storyboard.load("missing") is None


def test_off_without_a_key_or_with_the_switch(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.delenv("HF_KEY", raising=False)
    assert storyboard.enabled() is False
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "a:b")
    assert storyboard.enabled() is True
    monkeypatch.setenv("REEL_STORYBOARDS", "0")
    assert storyboard.enabled() is False


def test_a_failed_shot_keeps_its_place_as_none(monkeypatch, tmp_path):
    import hfgen
    monkeypatch.setattr(hfgen, "shot",
                        lambda spec, cast, out: None if spec["picture"] == "b" else out)
    got = storyboard.generate(BOARD, tmp_path)
    assert [g is None for g in got] == [False, True, False, False]


def test_a_crashing_shot_is_also_just_none(monkeypatch, tmp_path):
    import hfgen

    def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(hfgen, "shot", boom)
    assert storyboard.generate(BOARD, tmp_path) == [None] * 4


def test_every_live_board_is_approved_and_matches_a_story():
    import stories
    boards = json.loads((ROOT / "data" / "storyboards.json").read_text())
    ids = {s["id"] for s in stories.load()}
    for sid, b in boards.items():
        if sid.startswith("_"):
            continue
        assert sid in ids, f"board {sid} has no story"
        assert sum(1 for s in b["shots"] if s.get("quote")) == 1, f"{sid}: one quote shot"


def test_render_honours_planned_shot_lengths(monkeypatch):
    import render
    monkeypatch.setenv("REEL_BG_SECONDS", "1,1,2")
    assert [round(x, 3) for x in render._segment_durations(8, 3)] == [2, 2, 4]
    monkeypatch.setenv("REEL_BG_SECONDS", "junk")
    assert render._segment_durations(9, 3) == [3, 3, 3]


def test_background_chain_serves_a_generated_shot_first(tmp_path):
    import backgrounds
    clip = tmp_path / "gen.mp4"
    clip.write_bytes(b"x" * 2000)
    backgrounds.PRESET.clear()
    backgrounds.PRESET[2] = clip
    try:
        out = backgrounds.fetch_background("time", tmp_path / "slot2.mp4", clip_idx=2)
        assert out.read_bytes() == clip.read_bytes()
        assert backgrounds.LAST_BG_SOURCE == "STORYBOARD"
    finally:
        backgrounds.PRESET.clear()
