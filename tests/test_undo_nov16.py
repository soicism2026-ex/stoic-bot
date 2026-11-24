"""Cicero's 3-day test "undo-nov16" (owner 2026-11-20, Go on idea-undo-nov16):
for Shorts aired Nov 20-22 the news tie-ins (Fama) are paused and the
description's question ends with "Share your thoughts in the comments." again.
Everything reverts by itself after the end date."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edits  # noqa: E402
import fama  # noqa: E402
import marketer as mk  # noqa: E402
import publish_instagram as ig  # noqa: E402

D = dt.date
ENTRY = {"id": "undo-nov16", "status": "running", "started": "2026-11-20", "end": "2026-11-22"}
Q = {"id": "x", "theme": "fear", "quote": "Q.", "author": "Epictetus", "citation": "Enchiridion 5",
     "hook": "Stop fearing.", "visuals": [], "description": "One.\n\nTwo.\n\nThree.", "question": "Why?"}


def _ledger(tmp_path, monkeypatch, **over):
    p = tmp_path / "marketing_tests.json"
    p.write_text(json.dumps({"tests": [{**ENTRY, **over}]}))
    monkeypatch.setattr(edits, "MARKETING_TESTS", p)


def test_the_ledger_entry_is_a_dated_self_ending_test():
    t = next(t for t in json.loads((ROOT / "data/marketing_tests.json").read_text())["tests"]
             if t["id"] == "undo-nov16")
    assert t["kind"] == "views_before_after" and t["age"] == 1
    # the first run (Nov 20-22) is kept in first_run; the owner extended it on Nov 24
    # ("Keep the old hooks and the comment line?: Test 7 more days"): Nov 24-30
    assert t["started"] == "2026-11-24" and t["end"] == "2026-11-30" and t["ask"] == "idea-undo-nov16"
    assert t["first_run"]["verdict"] == "win" and t["first_run"]["window"] == "2026-11-20 to 2026-11-22"
    assert t["before"] == ["2026-11-16", "2026-11-19"]
    assert "owner, in the HQ" in t["approved"] and "Test 7 more days" in t["extended"]


def test_active_until_the_end_day_then_reverts_by_itself(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    assert edits.undo_nov16_active(D(2026, 11, 20)) and edits.undo_nov16_active(D(2026, 11, 22))
    assert not edits.undo_nov16_active(D(2026, 11, 23))            # reverts on Nov 23
    assert not edits.undo_nov16_active(D(2026, 11, 19))
    _ledger(tmp_path, monkeypatch, status="done")
    assert not edits.undo_nov16_active(D(2026, 11, 21))
    monkeypatch.setattr(edits, "MARKETING_TESTS", tmp_path / "missing.json")
    assert not edits.undo_nov16_active(D(2026, 11, 21))


def test_the_air_day_comes_from_airday_so_a_rehearsal_matches(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("REEL_TODAY", "2026-11-21")
    assert edits.undo_nov16_active()
    monkeypatch.setenv("REEL_TODAY", "2026-11-23")
    assert not edits.undo_nov16_active()


def test_the_question_line_gets_its_ask_back_and_loses_it_on_nov_23(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: True)
    c = edits.as_content(Q)
    q = [p for p in edits.description(c).split("\n\n") if p.startswith(edits.QUESTION_MARK)][0]
    assert q == "\U0001F4AC Question: Why? Share your thoughts in the comments."
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: False)
    q = [p for p in edits.description(c).split("\n\n") if p.startswith(edits.QUESTION_MARK)][0]
    assert q == "\U0001F4AC Question: Why?"


def test_topical_for_is_none_while_it_runs_and_back_after(tmp_path, monkeypatch):
    plan = {"forPost": 0, "decidedAt": "2026-11-21T01:00:00Z", "edit": "e1", "hook": "h", "lead": "l"}
    (tmp_path / "topical.json").write_text(json.dumps(plan))
    monkeypatch.setattr(edits, "TOPICAL", tmp_path / "topical.json")
    monkeypatch.setattr(edits, "load", lambda: [{"id": "e1", "author": "A", "quote": "Q unique text", "citation": "c"}])
    monkeypatch.setattr(edits, "jammed_ids", lambda: set())
    now = dt.datetime(2026, 11, 21, 2, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: True)
    assert edits.topical_for([], now) is None
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: False)
    assert edits.topical_for([], now) == plan


def test_the_instagram_caption_gets_the_same_ask(monkeypatch):
    kw = dict(hook="H", quote="Q.", author="Epictetus", body="One.\n\nTwo.", question="Why?")
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: True)
    assert "Question: Why? Share your thoughts in the comments." in ig.caption(**kw)
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: False)
    assert "Question: Why?\n" in ig.caption(**kw) and "Share your thoughts" not in ig.caption(**kw)


def test_fama_pauses_without_fetching_or_calling_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(fama, "PLAN", tmp_path / "topical.json")
    monkeypatch.setattr(fama, "_rows", lambda: [])
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run"))  # noqa: E731
    monkeypatch.setattr(fama, "fetch", boom)
    monkeypatch.setattr(fama, "decide", boom)
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: True)
    now = dt.datetime(2026, 11, 20, 5, tzinfo=dt.timezone.utc)
    out = fama.plan(now)
    assert out == {"forPost": 0, "decidedAt": "2026-11-20T05:00:00Z", "none": "paused for the undo-nov16 test"}
    assert json.loads((tmp_path / "topical.json").read_text()) == out


def test_marketer_takes_explicit_windows_for_a_dated_test():
    rows, posts = [], []
    for day, n in ((D(2026, 11, 16), 100), (D(2026, 11, 17), 100), (D(2026, 11, 18), 120), (D(2026, 11, 19), 100),
                   (D(2026, 11, 20), 200), (D(2026, 11, 21), 220), (D(2026, 11, 22), 210)):
        vid = f"v{day.day}"
        rows.append((vid, f"{day}T03:00", [(0, 5, 0), (1, n, 3)]))
        posts.append({"date": day.isoformat(), "video_id": vid, "experiment": "edit:x"})
    # a Short from Nov 15 sits outside the control window and must not count
    rows.append(("old", "2026-11-15T03:00", [(0, 5, 0), (1, 900, 3)]))
    posts.append({"date": "2026-11-15", "video_id": "old", "experiment": "edit:x"})
    views = mk.Views(_analytics(rows))
    test = {"id": "undo-nov16", "kind": "views_before_after", "age": 1, "status": "running",
            "started": "2026-11-20", "end": "2026-11-22", "before": ["2026-11-16", "2026-11-19"]}
    got = mk.judge(test, posts, views, D(2026, 11, 25))
    assert got["before"] == {"shorts": 4, "median": 100}
    assert got["during"]["shorts"] == 3 and got["during"]["median"] == 210
    assert got["change"] == 2.1 and got["verdict"] == "win"
    # the window ends on its own: a Short aired Nov 23 is not counted
    rows.append(("late", "2026-11-23T03:00", [(0, 5, 0), (1, 5000, 3)]))
    posts.append({"date": "2026-11-23", "video_id": "late", "experiment": "edit:x"})
    again = mk.judge(test, posts, mk.Views(_analytics(rows)), D(2026, 11, 25))
    assert again["during"]["shorts"] == 3


def _analytics(rows):
    from test_marketer import _analytics as a
    return a(rows)
