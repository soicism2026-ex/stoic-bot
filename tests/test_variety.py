"""Repetition is the channel's recurring failure mode, and it never shows up
as an error. Rule 7 shipped 13x, one music bed shipped 30x, and the same hook
shipped verbatim 3x — all with a green test suite, because the CODE was right
and the DATA was wrong.

These tests cover the two fixes (cinematic bed rotation, full-history hook
ban) and the watchdog that judges the output instead of the code.
"""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import music  # noqa: E402
import variety_check as vc  # noqa: E402


def _rows(*tracks):
    return [{"music_track": t, "video_id": f"v{i}"} for i, t in enumerate(tracks)]


# ------------------------------------------------- cinematic bed rotation

def test_more_than_one_cinematic_bed_exists():
    """The whole bug was a single hardcoded bed."""
    assert len(music.CINEMATIC_SCORES) >= 4


def test_every_cinematic_bed_has_a_filter_graph():
    for name in music.CINEMATIC_SCORES:
        assert any(isinstance(v, dict) and name in v
                   for v in vars(music).values()), f"{name} has no synth graph"


def test_picker_blocks_the_last_two_used():
    """Blocking only one still lets a bed return the same afternoon."""
    rows = _rows("cinematic_score_f", "cinematic_score_d")
    # reversed(rows) -> _d is most recent, _f second
    got = music.pick_cinematic_score(rows)["name"]
    assert got not in {"cinematic_score_d", "cinematic_score_f"}


def test_picker_returns_a_known_bed():
    assert music.pick_cinematic_score([])["name"] in music.CINEMATIC_SCORES


def test_picker_survives_an_exhausted_pool():
    """If every bed is recent, still return one rather than crashing."""
    rows = _rows(*music.CINEMATIC_SCORES)
    assert music.pick_cinematic_score(rows)["name"] in music.CINEMATIC_SCORES


def test_picker_ignores_rows_without_a_track():
    rows = [{"music_track": ""}, {"music_track": None}]
    assert music.pick_cinematic_score(rows)["name"] in music.CINEMATIC_SCORES


@pytest.mark.parametrize("name", music.CINEMATIC_SCORES)
def test_every_bed_actually_renders(name, tmp_path):
    """ffmpeg's tremolo rejects f < 0.1 — two beds were silently unrenderable
    when first written. A bed that fails to synthesize means a silent video."""
    if not __import__("shutil").which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    graph = next(v[name] for v in vars(music).values()
                 if isinstance(v, dict) and name in v)
    out = tmp_path / f"{name}.mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-filter_complex",
         graph.format(d=2), "-t", "2", "-c:a", "libmp3lame", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:300]
    assert out.stat().st_size > 2_000


# ------------------------------------------------------- the watchdog itself

def _write(tmp_path, monkeypatch, rows):
    p = tmp_path / "posts.csv"
    fields = ["date", "theme", "author", "quote", "caption", "video_url",
              "video_id", "voice_name", "music_track", "hook", "experiment",
              "format"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    monkeypatch.setattr(vc, "POSTS", p)
    return p


def test_catches_verbatim_hook_repeat(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Nero handed him a death sentence."},
        {"hook": "Something else."},
        {"hook": "Nero handed him a death sentence."},
    ])
    issues = []
    vc.check_verbatim_hooks(vc._load(), issues)
    assert any("verbatim" in i for i in issues)


def test_catches_repeated_rule_number(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Rule 7: One."}, {"hook": "Rule 7: Two."},
    ])
    issues = []
    vc.check_rule_numbers(vc._load(), issues)
    assert any("rule number 7" in i for i in issues)


def test_passes_when_rule_numbers_are_distinct(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Rule 7: One."}, {"hook": "Rule 12: Two."},
    ])
    issues = []
    vc.check_rule_numbers(vc._load(), issues)
    assert issues == []


def test_catches_a_single_music_bed_dominating(tmp_path, monkeypatch):
    """The exact 30/30 cinematic_score case."""
    rows = [{"music_track": "cinematic_score"} for _ in range(10)]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_dominance(vc._load(), "music_track", "music", issues)
    assert any("rotation is not varying" in i for i in issues)


def test_healthy_rotation_raises_nothing(tmp_path, monkeypatch):
    rows = [{"music_track": t} for t in
            ["a", "b", "c", "d", "e"] * 2]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_dominance(vc._load(), "music_track", "music", issues)
    assert issues == []


def test_catches_formulaic_hook_openers(tmp_path, monkeypatch):
    """Six hooks opening 'Rule' is a formula, not a format."""
    rows = [{"hook": f"Rule {i}: thing"} for i in range(6)]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_hook_openers(vc._load(), issues)
    assert any("same word" in i for i in issues)


def test_catches_duplicate_quotes(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [{"quote": "Same"}, {"quote": "Same"}])
    issues = []
    vc.check_duplicate_quotes(vc._load(), issues)
    assert any("quote used 2x" in i for i in issues)


def test_missing_posts_csv_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vc, "POSTS", tmp_path / "nope.csv")
    monkeypatch.setattr(sys, "argv", ["variety_check.py"])
    assert vc.main() == 0


def test_exit_code_signals_problems(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Same hook.", "music_track": "x", "quote": "q"},
        {"hook": "Same hook.", "music_track": "x", "quote": "q"},
    ])
    monkeypatch.setattr(sys, "argv", ["variety_check.py"])
    assert vc.main() == 1
