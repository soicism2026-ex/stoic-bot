"""The roadmap has to be measurable or it is a wish.

These pin the two things that make goal_check.py worth having: that it reports
honestly when behind, and that the tripwires actually fire. A progress checker
that only prints good news is worse than none — it launders drift as progress.
"""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import goal_check as gc  # noqa: E402


def _stats(tmp_path, monkeypatch, rows):
    p = tmp_path / "s.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pulled_on", "subscribers", "total_views"])
        w.writerows(rows)
    monkeypatch.setattr(gc, "STATS", p)
    return p


def test_milestones_are_ordered_and_increasing():
    dates = [d for d, _, _ in gc.MILESTONES]
    assert dates == sorted(dates)
    subs = [s for _, s, _ in gc.MILESTONES]
    views = [v for _, _, v in gc.MILESTONES]
    assert subs == sorted(subs) and views == sorted(views)


def test_final_milestone_is_the_500_sub_threshold():
    """500 is the reachable half of YPP; the view half is 99x away and the
    roadmap says so rather than pretending."""
    assert gc.MILESTONES[-1][1] == 500


def test_rate_is_computed_over_the_window(tmp_path, monkeypatch):
    _stats(tmp_path, monkeypatch,
           [(f"2026-08-{d:02d}", 200 + d, 50000 + d * 100) for d in range(1, 16)])
    ds, dv = gc._rate(gc._stats(), 7)
    assert ds == pytest.approx(1.0) and dv == pytest.approx(100.0)


def test_rate_returns_zero_without_enough_history(tmp_path, monkeypatch):
    _stats(tmp_path, monkeypatch, [("2026-08-01", 200, 50000)])
    assert gc._rate(gc._stats(), 7) == (0.0, 0.0)


def test_missing_stats_is_reported_not_crashed(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "STATS", tmp_path / "nope.csv")
    assert gc.main() == 1


def test_negative_sub_growth_fires_a_tripwire(tmp_path, monkeypatch, capsys):
    """Losing subscribers means content is actively repelling people — that
    outranks every other metric on the page."""
    _stats(tmp_path, monkeypatch,
           [(f"2026-08-{d:02d}", 300 - d, 50000 + d * 10) for d in range(1, 16)])
    monkeypatch.setattr(gc, "_median_1day_views", lambda: 500.0)
    gc.main()
    assert "NEGATIVE" in capsys.readouterr().out


def test_low_median_fires_after_the_decision_date(tmp_path, monkeypatch, capsys):
    """The roadmap commits to a date for admitting the theory was wrong. If the
    checker will not say it, nobody will."""
    _stats(tmp_path, monkeypatch,
           [(f"2026-09-{d:02d}", 200 + d, 50000 + d * 100) for d in range(1, 16)])
    monkeypatch.setattr(gc, "_median_1day_views", lambda: 40.0)
    gc.main()
    assert "WRONG" in capsys.readouterr().out


def test_healthy_channel_fires_nothing(tmp_path, monkeypatch, capsys):
    _stats(tmp_path, monkeypatch,
           [(f"2026-08-{d:02d}", 200 + d * 3, 50000 + d * 2000) for d in range(1, 16)])
    monkeypatch.setattr(gc, "_median_1day_views", lambda: 400.0)
    gc.main()
    assert "no tripwires fired" in capsys.readouterr().out


def test_ypp_gap_is_always_printed(tmp_path, monkeypatch, capsys):
    """The 3M/90d number is the one most likely to be misremembered as close."""
    _stats(tmp_path, monkeypatch,
           [(f"2026-08-{d:02d}", 200 + d, 50000 + d * 100) for d in range(1, 16)])
    monkeypatch.setattr(gc, "_median_1day_views", lambda: 400.0)
    gc.main()
    assert "x short" in capsys.readouterr().out


def test_roadmap_exists_and_names_its_tripwires():
    rm = (ROOT / "data" / "roadmap.md").read_text()
    assert "Tripwires" in rm
    assert "99" in rm, "the YPP view gap must be stated, not softened"
    assert "2026-08-24" in rm, "the decision date must be committed to in writing"
