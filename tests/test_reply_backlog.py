"""The reply bot could only ever see the last 7 days of videos.

That was 21 of 229 — 9% of the catalogue. The blind spot grew as the channel
did, and the reply rate collapsed with it:

    June 24 replies | July 5 | August 1

while ~73 viewer comments sat unanswered on older videos. Shorts accrue views
for weeks after posting, so they accrue comments for weeks too; a viewer who
comments on a three-week-old Short was invisible forever.

Replies are the direct lever on the 500-subscriber goal, so this is not a
cosmetic gap. These tests pin the rotating back-catalogue sweep that closes
it, and the quota ceiling that keeps it affordable.
"""
import csv
import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import reply_to_comments as rc  # noqa: E402


FIELDS = ["date", "theme", "author", "quote", "caption", "video_url",
          "video_id", "voice_name", "music_track", "hook", "experiment",
          "format"]


def _posts(tmp_path, monkeypatch, n_old, n_recent):
    """n_old videos from long ago, n_recent from today."""
    old_day = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    today = datetime.date.today().isoformat()
    rows = [{"date": old_day, "video_id": f"old{i}"} for i in range(n_old)]
    rows += [{"date": today, "video_id": f"new{i}"} for i in range(n_recent)]
    p = tmp_path / "posts.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    monkeypatch.setattr(rc, "POSTS_CSV", p)
    return p


# ------------------------------------------------- the blind spot

def test_old_videos_are_no_longer_invisible(tmp_path, monkeypatch):
    """The whole bug in one assertion."""
    _posts(tmp_path, monkeypatch, n_old=200, n_recent=21)
    scanned = rc._load_recent_video_ids()
    assert any(v.startswith("old") for v in scanned), \
        "the back catalogue is still unreachable"


def test_recent_videos_are_always_scanned(tmp_path, monkeypatch):
    """Fresh comments matter most; the backlog must not displace them."""
    _posts(tmp_path, monkeypatch, n_old=200, n_recent=21)
    scanned = set(rc._load_recent_video_ids())
    assert {f"new{i}" for i in range(21)} <= scanned


def test_every_old_video_is_reached_within_a_full_sweep(tmp_path, monkeypatch):
    """Rotation must COVER, not just sample — no video starved forever."""
    _posts(tmp_path, monkeypatch, n_old=200, n_recent=3)
    _, older = rc._split_catalogue()
    runs = -(-len(older) // rc.BACKLOG_PER_RUN)
    seen = set()
    for i in range(runs):
        seen |= set(rc._backlog_slice(older, i))
    assert seen == set(older), f"missed {len(set(older) - seen)} videos"


def test_the_window_wraps_past_the_end(tmp_path, monkeypatch):
    """The tail of the catalogue is where the oldest comments are."""
    older = [f"v{i}" for i in range(10)]
    got = rc._backlog_slice(older, run_counter=1, per_run=7)
    assert len(got) == 7
    assert "v0" in got, "window did not wrap; the list tail would starve"


def test_slice_is_bounded_by_the_quota_setting(tmp_path, monkeypatch):
    older = [f"v{i}" for i in range(500)]
    assert len(rc._backlog_slice(older, 0, per_run=40)) == 40


def test_a_small_catalogue_is_scanned_whole():
    older = ["a", "b", "c"]
    assert set(rc._backlog_slice(older, 3, per_run=40)) == {"a", "b", "c"}


def test_empty_catalogue_is_not_an_error():
    assert rc._backlog_slice([], 5) == []


def test_disabling_the_backlog_leaves_recent_only(tmp_path, monkeypatch):
    older = [f"v{i}" for i in range(50)]
    assert rc._backlog_slice(older, 0, per_run=0) == []


# ------------------------------------------------- run counter

def test_run_counter_tracks_posts(tmp_path, monkeypatch):
    """posts.csv IS the run log, so it cannot drift out of sync the way a
    separate state file would."""
    _posts(tmp_path, monkeypatch, n_old=10, n_recent=2)
    assert rc._run_counter() == 12


def test_run_counter_survives_a_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "POSTS_CSV", tmp_path / "nope.csv")
    assert rc._run_counter() == 0


def test_successive_runs_scan_different_old_videos(tmp_path, monkeypatch):
    """A rotation that does not rotate is just a smaller blind spot."""
    older = [f"v{i}" for i in range(200)]
    a = set(rc._backlog_slice(older, 0, per_run=40))
    b = set(rc._backlog_slice(older, 1, per_run=40))
    assert a != b and not (a & b)


# ------------------------------------------------- quota safety

def test_per_run_scan_stays_well_inside_the_daily_quota(tmp_path, monkeypatch):
    """commentThreads.list is 1 unit/video; the 3 daily uploads cost 1,600
    each, so the scan must stay small next to a 10,000/day budget."""
    _posts(tmp_path, monkeypatch, n_old=200, n_recent=21)
    per_run = len(rc._load_recent_video_ids())
    daily = per_run * 3 + 3 * 1600
    assert daily < 10_000, f"{daily} units/day would risk the upload budget"


def test_no_duplicate_ids_are_scanned(tmp_path, monkeypatch):
    """A duplicate is a wasted quota unit and a double reply risk."""
    _posts(tmp_path, monkeypatch, n_old=200, n_recent=21)
    scanned = rc._load_recent_video_ids()
    assert len(scanned) == len(set(scanned))
