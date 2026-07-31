"""Tests for the committed GUIDE clip library (assets/guide/).

The library is optional: when it's empty the pipeline must behave EXACTLY as it
did before it existed. When it's populated it must serve the bookend slots and
never hand the same clip to both the opener and the closer.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import backgrounds  # noqa: E402


@pytest.fixture
def guide_dir(tmp_path, monkeypatch):
    d = tmp_path / "guide"
    d.mkdir()
    monkeypatch.setattr(backgrounds, "GUIDE_DIR", d)
    return d


def _make_clips(d: Path, n: int) -> list[Path]:
    paths = []
    for i in range(1, n + 1):
        p = d / f"guide_{i:02d}.mp4"
        p.write_bytes(b"\0" * 5_000)  # over the 1000-byte sanity floor
        paths.append(p)
    return sorted(paths)


# ---------------------------------------------------------------- slot parsing

@pytest.mark.parametrize("raw,expected", [
    ("0,5", {0, 5}),
    (" 0 , 5 ", {0, 5}),
    ("0", {0}),
    ("", set()),
    ("nonsense", set()),
    ("0,junk,5", {0, 5}),        # partial garbage must not lose the good values
])
def test_guide_slots_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("REEL_GUIDE_SLOTS", raw)
    assert backgrounds._guide_slots() == expected


def test_guide_slots_unset(monkeypatch):
    monkeypatch.delenv("REEL_GUIDE_SLOTS", raising=False)
    assert backgrounds._guide_slots() == set()


# ----------------------------------------------------------------- empty state

def test_no_library_returns_none(guide_dir, monkeypatch):
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    assert backgrounds._guide_clip(0) is None


def test_missing_dir_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(backgrounds, "GUIDE_DIR", tmp_path / "does_not_exist")
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    assert backgrounds._guide_clip(0) is None


def test_tiny_files_are_ignored(guide_dir, monkeypatch):
    """A truncated/failed download must not become the channel's face."""
    (guide_dir / "guide_01.mp4").write_bytes(b"\0" * 10)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    assert backgrounds._guide_clip(0) is None


# ------------------------------------------------------------------- selection

def test_picks_from_library(guide_dir, monkeypatch):
    clips = _make_clips(guide_dir, 12)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    got = backgrounds._guide_clip(0)
    assert got in clips


def test_opener_and_closer_differ(guide_dir, monkeypatch):
    """A short that opens and closes on the identical clip reads as a bug."""
    _make_clips(guide_dir, 12)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    assert backgrounds._guide_clip(0) != backgrounds._guide_clip(5)


def test_opener_and_closer_differ_across_offsets(guide_dir, monkeypatch):
    """Must hold for every QA retry offset, not just today's date."""
    _make_clips(guide_dir, 12)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    for attempt in range(0, 12):
        monkeypatch.setenv("REEL_BG_OFFSET", str(attempt))
        assert backgrounds._guide_clip(0) != backgrounds._guide_clip(5), attempt


def test_single_clip_library_still_works(guide_dir, monkeypatch):
    """Degenerate case: one clip means both bookends are it. Must not crash."""
    _make_clips(guide_dir, 1)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    assert backgrounds._guide_clip(0) is not None
    assert backgrounds._guide_clip(5) is not None


def test_rotation_varies_by_day(guide_dir, monkeypatch):
    """Over a run of offsets the opener must cover more than one clip."""
    _make_clips(guide_dir, 12)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    seen = set()
    for attempt in range(12):
        monkeypatch.setenv("REEL_BG_OFFSET", str(attempt))
        seen.add(backgrounds._guide_clip(0).name)
    assert len(seen) == 12, f"rotation only reached {len(seen)} of 12 clips"


# -------------------------------------------------------- fetch_background hook

def test_fetch_background_uses_library_for_guide_slot(guide_dir, monkeypatch, tmp_path):
    clips = _make_clips(guide_dir, 6)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")

    def _boom(*a, **k):
        raise AssertionError("network source called for a guide slot")

    monkeypatch.setattr(backgrounds, "_fetch_from_pixabay", _boom)
    monkeypatch.setattr(backgrounds, "_fetch_from_pexels", _boom)

    got = backgrounds.fetch_background("discipline", tmp_path / "out.mp4", clip_idx=0)
    assert got in clips


def test_fetch_background_ignores_library_for_broll_slots(guide_dir, monkeypatch, tmp_path):
    """Middle clips are scene-matched b-roll — they must NEVER be the statue."""
    _make_clips(guide_dir, 6)
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    sentinel = tmp_path / "stock.mp4"
    sentinel.write_bytes(b"\0" * 5_000)
    monkeypatch.setattr(backgrounds, "_fetch_from_pixabay",
                        lambda *a, **k: sentinel)
    got = backgrounds.fetch_background("discipline", tmp_path / "out.mp4", clip_idx=2)
    assert got == sentinel


def test_fetch_background_falls_through_when_library_empty(guide_dir, monkeypatch, tmp_path):
    """The whole feature is additive — empty folder means old behaviour."""
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")
    sentinel = tmp_path / "stock.mp4"
    sentinel.write_bytes(b"\0" * 5_000)
    monkeypatch.setattr(backgrounds, "_fetch_from_pixabay",
                        lambda *a, **k: sentinel)
    got = backgrounds.fetch_background("discipline", tmp_path / "out.mp4", clip_idx=0)
    assert got == sentinel


def test_library_failure_never_breaks_a_render(guide_dir, monkeypatch, tmp_path):
    """If the library lookup raises, the run must degrade to stock, not die."""
    monkeypatch.setenv("REEL_GUIDE_SLOTS", "0,5")

    def _raise(_idx):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(backgrounds, "_guide_clip", _raise)
    sentinel = tmp_path / "stock.mp4"
    sentinel.write_bytes(b"\0" * 5_000)
    monkeypatch.setattr(backgrounds, "_fetch_from_pixabay",
                        lambda *a, **k: sentinel)
    got = backgrounds.fetch_background("discipline", tmp_path / "out.mp4", clip_idx=0)
    assert got == sentinel
