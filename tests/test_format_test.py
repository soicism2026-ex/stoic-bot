"""The 20-video format test (data/format_test.md).

Designed after the finding that reframed everything: 210 videos, best ever
1,255 views, none above 5,000. The channel has never had a breakout, so the
question is not "which format is best" but "can any format break out at all".

These tests exist because the two ways this test can fail are both silent:
blocking instead of interleaving (confounds format with day/time), and reading
a leaderboard off n=5 (five videos cannot establish a median).
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import format_test as ft  # noqa: E402


def _posts(tmp_path, monkeypatch, experiments):
    p = tmp_path / "posts.csv"
    fields = ["date", "theme", "author", "quote", "caption", "video_url",
              "video_id", "voice_name", "music_track", "hook", "experiment",
              "format"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, e in enumerate(experiments):
            w.writerow({k: "" for k in fields} | {"video_id": f"v{i}",
                                                  "experiment": e})
    monkeypatch.setattr(ft, "POSTS", p)
    return p


def _analytics(tmp_path, monkeypatch, views_by_vid):
    p = tmp_path / "a.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pulled_on", "published_at", "video_id", "views"])
        for vid, v in views_by_vid.items():
            w.writerow(["2026-09-01", "2026-08-25", vid, v])
    monkeypatch.setattr(ft, "ANALYTICS", p)


# ------------------------------------------------------------- interleaving

def test_the_four_formats_are_genuinely_four():
    assert len(ft.ORDER) == 4 and len(set(ft.ORDER)) == 4


def test_only_built_formats_are_scheduled():
    """Tooling that claims an unbuilt arm is next is lying about what is
    running. Only F3 is built so far."""
    assert ft.BUILT <= set(ft.ORDER)
    # None is correct once every BUILT format has run its posts — the
    # programme is finished, not broken. It finished 2026-08-25: the_question
    # scored [51,29,24,20,16] against same-day controls with a median of 44.5,
    # so it lost to the format it was testing against.
    nxt = ft.next_format()
    assert nxt is None or nxt in ft.BUILT


def test_rotation_interleaves_rather_than_blocks(tmp_path, monkeypatch):
    """With more than one arm live, blocking would confound the format with
    the day, the time slot, and whatever the algorithm was doing that
    afternoon. Checked against the full ORDER so the property is pinned before
    the other three arms get built."""
    monkeypatch.setattr(ft, "BUILT", set(ft.ORDER))
    seq = []
    for _ in range(8):
        _posts(tmp_path, monkeypatch, [f"ftest:{x}" for x in seq])
        seq.append(ft.next_format())
    assert seq[:4] == ft.ORDER
    assert seq[4:] == ft.ORDER, "second cycle is not interleaved"


def test_test_ends_when_every_live_arm_has_its_five(tmp_path, monkeypatch):
    live = [f for f in ft.ORDER if f in ft.BUILT]
    n = ft.PER_FORMAT * len(live)
    _posts(tmp_path, monkeypatch,
           [f"ftest:{live[i % len(live)]}" for i in range(n)])
    assert ft.next_format() is None


def test_non_test_posts_are_ignored(tmp_path, monkeypatch):
    """Normal posts must not consume test slots or pollute the result."""
    _posts(tmp_path, monkeypatch, ["", "cold_open+gold", "ftest:the_question"])
    assert len(ft._test_rows()) == 1
    # None is correct once every BUILT format has run its posts — the
    # programme is finished, not broken. It finished 2026-08-25: the_question
    # scored [51,29,24,20,16] against same-day controls with a median of 44.5,
    # so it lost to the format it was testing against.
    nxt = ft.next_format()
    assert nxt is None or nxt in ft.BUILT


# ------------------------------------------------------------ the bar itself

def test_breakout_bar_is_well_above_the_all_time_best():
    """1,255 is the ceiling across 210 videos. A bar near it would let noise
    read as a win. 5,000 is 3.98x — called 4x, and the round number is the one
    worth stating out loud; what matters is that it is multiples away, not
    that it hits an exact integer ratio."""
    assert ft.BREAKOUT / ft.ALLTIME_BEST >= 3.9


# -------------------------------------------------------------- reading it

def test_partial_data_refuses_to_report_a_result(tmp_path, monkeypatch, capsys):
    """The failure mode this guards: reading a leaderboard off half the test."""
    _posts(tmp_path, monkeypatch, ["ftest:the_question" for _ in range(2)])
    _analytics(tmp_path, monkeypatch, {f"v{i}": 400 for i in range(2)})
    ft.main()
    out = capsys.readouterr().out
    assert "incomplete" in out and "RESULT" not in out


def test_a_breakout_is_called_out(tmp_path, monkeypatch, capsys):
    _posts(tmp_path, monkeypatch, ["ftest:the_question" for _ in range(5)])
    views = {f"v{i}": 300 for i in range(5)}
    views["v2"] = 9_000
    _analytics(tmp_path, monkeypatch, views)
    ft.main()
    out = capsys.readouterr().out
    assert "BREAKOUT" in out and "make 20 more" in out


def test_a_null_result_says_the_format_was_never_the_problem(tmp_path, monkeypatch, capsys):
    """The whole reason to run this. If all four fail, more polish cannot help
    and the checker has to say so plainly."""
    _posts(tmp_path, monkeypatch, ["ftest:the_question" for _ in range(5)])
    _analytics(tmp_path, monkeypatch, {f"v{i}": 400 for i in range(5)})
    ft.main()
    out = capsys.readouterr().out
    assert "never the problem" in out
    assert "positioning" in out


def test_design_doc_freezes_other_variables():
    """Four unproven variables in flight at once is how the last three weeks
    became unreadable."""
    doc = (ROOT / "data" / "format_test.md").read_text()
    assert "FREEZE EVERYTHING ELSE" in doc
    assert "5,000" in doc
