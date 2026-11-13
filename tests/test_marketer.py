"""Cicero, the marketer (owner 2026-11-03: "Hire a marketing professional").

He reads how the channel reaches people, proposes one test at a time, and
ships nothing without the owner's yes."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hq_snapshot as hq  # noqa: E402
import marketer as mk  # noqa: E402

TODAY = dt.date(2026, 11, 3)


def _analytics(rows):
    """rows: (video, published 'YYYY-MM-DDTHH:MM', [(age_days, views, likes)])"""
    out = []
    for vid, pub, snaps in rows:
        day = dt.date.fromisoformat(pub[:10])
        for age, views, likes in snaps:
            out.append({"video_id": vid, "published_at": pub + ":00Z", "views": str(views), "likes": str(likes),
                        "pulled_on": (day + dt.timedelta(days=age)).isoformat()})
    return out


def test_views_are_read_at_the_age_asked_for():
    v = mk.Views(_analytics([("a", "2026-10-30T01:00", [(0, 10, 0), (1, 200, 9), (4, 250, 12)])]))
    assert v.at_age("a", 1) == 200 and v.at_age("a", 3) == 250 and v.at_age("a", 9) is None
    assert v.at_age("missing", 1) is None
    assert v.latest["a"] == ("2026-11-03", 250, 12)


def test_the_funnel_compares_this_week_with_last():
    stats = []
    for i in range(15):
        day = (TODAY - dt.timedelta(days=14 - i)).isoformat()
        stats.append({"pulled_on": day, "subscribers": str(200 + i), "total_views": str(10_000 + 300 * i)})
    stats.append({"pulled_on": TODAY.isoformat(), "subscribers": "214", "total_views": "14200"})  # last row of a day wins
    f = mk.funnel(stats, mk.Views([]), TODAY)
    assert f["subscribers"] == 214 and f["viewsPerDayBefore"] == 300
    assert f["viewsPerDay"] == round((14200 - (10_000 + 300 * 7)) / 7)
    assert f["subsPerDay"] == 1.0 and f["subsPer1kViews"] == round(1000 * 1.0 / ((14200 - 12100) / 7), 1)


def test_reach_by_upload_hour_is_judged_against_the_week():
    rows, posts = [], []
    for d in range(10):
        day = dt.date(2026, 10, 10) + dt.timedelta(days=d)
        rows.append((f"e{d}", f"{day}T01:00", [(1, 300, 10)]))     # evening Shorts do well
        rows.append((f"a{d}", f"{day}T16:00", [(1, 50, 2)]))       # afternoon Shorts don't
        posts += [{"date": day.isoformat(), "video_id": f"e{d}"}, {"date": day.isoformat(), "video_id": f"a{d}"}]
    bands = {b["band"]: b for b in mk.hour_bands(posts, mk.Views(_analytics(rows)))}
    assert bands["00-03"]["lift"] > 1.4 and bands["16-19"]["lift"] < 0.6
    assert bands["16-19"]["stalled"] == 10 and bands["00-03"]["stalled"] == 0


def test_a_posting_time_test_uses_the_days_first_short_as_its_control():
    rows, posts = [], []
    for d in range(20):
        day = dt.date(2026, 10, 19) + dt.timedelta(days=d)
        later = 300 if day >= dt.date(2026, 10, 29) else 120       # the change starts on 10-29
        rows.append((f"f{d}", f"{day}T01:00", [(1, 300, 0)]))
        rows.append((f"s{d}", f"{day}T{'08' if later == 300 else '16'}:00", [(1, later, 0)]))
        posts += [{"date": day.isoformat(), "video_id": f"f{d}"}, {"date": day.isoformat(), "video_id": f"s{d}"}]
    views = mk.Views(_analytics(rows))
    test = {"id": "t", "kind": "second_vs_first", "baselineSince": "2026-10-19", "status": "running",
            "started": "2026-10-29"}
    got = mk.judge(test, posts, views, dt.date(2026, 11, 12))
    assert got["before"] == {"days": 10, "median": 0.4}
    assert got["during"]["median"] == 1.0 and got["during"]["days"] == 10
    assert got["change"] == 2.5 and got["verdict"] == "win"
    early = mk.judge(test, posts, views, dt.date(2026, 11, 5))
    assert "verdict" not in early                                    # not 14 days yet
    proposed = mk.judge({**test, "status": "proposed", "started": None}, posts, views, TODAY)
    assert proposed["before"]["days"] == 15 and "during" not in proposed


def test_the_ledger_proposes_before_it_ships():
    ledger = json.loads((ROOT / "data" / "marketing_tests.json").read_text())
    first = ledger["tests"][0]
    assert first["id"] == "second-post-morning" and first["kind"] == "second_vs_first"
    assert first["ask"] == "post-times"                              # the HQ question it waits on
    for t in ledger["tests"]:
        assert t["status"] in ("proposed", "queued", "running", "done", "declined")
        assert t.get("started") or t["status"] in ("proposed", "queued", "declined"), t["id"]
        for k in ("question", "change", "why", "measure"):
            assert t[k], (t["id"], k)
    assert {t["id"] for t in ledger["tests"]} >= {"pinned-question", "playlists"}   # ideas became tests
    assert {n["id"] for n in ledger["next"]} >= {"third-short"}


def test_the_read_is_written_for_people_and_for_the_hq(tmp_path, monkeypatch):
    r = mk.read(today=TODAY)
    md = mk.markdown(r)
    for h in ("## The funnel", "## Reach by upload hour (UTC)", "## Tests"):
        assert h in md
    assert "free, no paid API" in md
    assert "views a day" in mk.note(r)
    monkeypatch.setattr(hq, "DATA", tmp_path)
    (tmp_path / "marketing.json").write_text(json.dumps({"note": "323 views a day"}))
    run = {"path": ".github/workflows/marketing.yml", "status": "completed", "conclusion": "success",
           "created_at": "2026-11-03T10:31:00Z"}
    bot = next(b for b in hq.bots([run], dt.datetime(2026, 11, 3, 12, tzinfo=dt.timezone.utc), "",
                                  fetch_missing=False) if b["id"] == "marketer")
    assert bot["note"] == "323 views a day" and bot["workflow"] == "marketing.yml"


def test_cicero_works_for_free_every_day_and_shows_in_the_hq():
    src = (ROOT / ".github" / "workflows" / "marketing.yml").read_text()
    wf = yaml.safe_load(src)
    assert wf["name"] == "marketing" and {c["cron"] for c in wf[True]["schedule"]} == {"30 10 * * *"}
    assert "scripts/marketer.py --write" in src and "secrets." not in src
    hs = (ROOT / ".github" / "workflows" / "hq-status.yml").read_text()
    assert "marketing]" in hs and '"marketing.yml"' in hs
    page = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")
    assert 'marketer: { name: "Cicero", title: "Marketing", sprite: "orator"' in page
    assert "\n    orator: [" in page


# ------------------------------------------- "Get everyone working harder" (2026-11-06)

def test_the_description_test_compares_the_new_style_with_the_weeks_before():
    """2026-11-06: the owner wants his description style on every Short, so
    the Shorts before it are the control, each sorted by its own description."""
    start = dt.date(2026, 11, 6)
    posts, analytics = [], []
    for d in range(-14, 14):
        day = start + dt.timedelta(days=d)
        new = d >= 1                           # the first Short of the start day went out the old way
        posts.append({"date": day.isoformat(), "video_id": f"v{d}", "experiment": f"edit:e{d}",
                      "caption": ("Para.\n\n" + mk.NEW_STYLE + " Why? Share your thoughts in the comments.")
                      if new else "Hook.\n\nQuote."})
        # the channel's own comment is 1 of the count on every Short
        analytics.append({"video_id": f"v{d}", "pulled_on": (day + dt.timedelta(days=3)).isoformat(),
                          "views": "200", "likes": "10", "comments": str(1 + (1 if new else 0))})
    posts.append({"date": "2026-11-07", "video_id": "s", "experiment": "story:x", "caption": mk.NEW_STYLE})
    test = {"id": "pinned-question", "kind": "pinned_question", "status": "running", "started": start.isoformat()}
    got = mk.judge(test, posts, mk.Views(analytics), dt.date(2026, 11, 20), analytics, [])
    arms = got["during"]["arms"]
    assert arms["new style"] == {"shorts": 13, "views": 2600, "comments": 13, "likes": 130, "per1k": 5.0,
                                 "likesPer100": 5.0}
    assert arms["old style"]["shorts"] == 15 and arms["old style"]["comments"] == 0
    assert got["before"] == arms["old style"] and got["verdict"] == "win"
    assert "verdict" not in mk.judge(test, posts, mk.Views(analytics), dt.date(2026, 11, 19), analytics, [])
    flat = [dict(a, comments="1") for a in analytics]                        # nobody answers
    assert mk.judge(test, posts, mk.Views(flat), dt.date(2026, 11, 20), flat, [])["verdict"] == "loss"
    proposed = mk.judge({**test, "status": "proposed", "started": None}, posts, mk.Views(analytics),
                        dt.date(2026, 11, 6), analytics, [])
    assert "during" not in proposed and proposed["before"]["shorts"] == 14


def test_cicero_and_the_producer_mark_the_new_style_the_same_way():
    sys.path.insert(0, str(ROOT / "src"))
    import edits  # noqa: PLC0415
    assert mk.NEW_STYLE == edits.QUESTION_MARK
    assert mk.style_of({"caption": edits.QUESTION_LINE.format(question="Why?")}) == "new style"
    assert mk.style_of({"caption": "Hook.\n\nQuote"}) == mk.style_of({}) == "old style"


def test_the_playlist_test_reads_the_traffic_source_share():
    start = dt.date(2026, 11, 10)
    rows = []
    for d in range(-14, 14):
        day = (start + dt.timedelta(days=d)).isoformat()
        rows.append({"date": day, "source": "SHORTS", "views": "400"})
        rows.append({"date": day, "source": "PLAYLIST", "views": "20" if d >= 0 else "0"})
    test = {"id": "playlists", "kind": "traffic_source", "source": "PLAYLIST", "status": "running",
            "started": start.isoformat()}
    got = mk.judge(test, [], mk.Views([]), dt.date(2026, 11, 25), [], rows)
    assert got["before"]["share"] == 0.0 and got["during"]["share"] == round(20 / 420, 4)
    assert got["verdict"] == "win"


def test_the_owner_said_yes_to_tests_2_and_3_on_2026_11_06():
    ledger = json.loads((ROOT / "data" / "marketing_tests.json").read_text())
    by_id = {t["id"]: t for t in ledger["tests"]}
    two = by_id["pinned-question"]
    assert two["kind"] == "pinned_question" and two["ask"] == "pinned-question"
    assert two["status"] == "running" and two["started"] == "2026-11-06" and "inspiration" in two["approved"]
    assert by_id["playlists"]["kind"] == "traffic_source" and by_id["playlists"]["source"] == "PLAYLIST"
    assert by_id["playlists"]["status"] == "running" and by_id["playlists"]["started"] == "2026-11-06"
    assert by_id["second-post-morning"]["status"] == "running" and by_id["second-post-morning"]["started"] == "2026-11-06"


def test_the_read_shows_who_watches(tmp_path, monkeypatch):
    monkeypatch.setattr(mk, "DATA", tmp_path)
    (tmp_path / "audience.json").write_text(json.dumps({
        "pulled_on": "2026-11-06", "countries": [{"key": "US", "views": 500, "share": 0.4}],
        "sources": [{"key": "SHORTS", "views": 1100, "share": 0.9}], "subscribed": [],
        "searchTermsAllTime": [{"key": "stoicism", "views": 30, "share": 0.75}]}))
    md = mk.markdown({**mk.read(today=TODAY), "audience": mk.audience()})
    assert "## Who watches" in md and "US 40%" in md and "SHORTS 90%" in md
    assert '"stoicism" (30)' in md


def test_cicero_measures_his_tests_against_the_owners_goal(tmp_path, monkeypatch):
    """2026-11-07: "something we can work towards instead of aimlessly trying things"."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import goals as gl  # noqa: PLC0415
    r = mk.read(today=TODAY)
    assert "## The goal" in mk.markdown(r)
    if r["goal"].get("chosen") is None:
        assert "No goal picked yet" in mk.markdown(r)
    picked = {**json.loads((ROOT / "data" / "goals.json").read_text()), "chosen": "million"}
    (tmp_path / "goals.json").write_text(json.dumps(picked))
    monkeypatch.setattr(gl, "GOALS", tmp_path / "goals.json")
    r = mk.read(today=TODAY)
    md = mk.markdown(r)
    assert "**A million views and 1,000 subscribers in 2027**" in md and "Views in 2027" in md
    assert "Next checkpoint 2027-03-31" in md and "goal: " in mk.note(r)



def test_the_new_look_is_judged_by_age_matched_views_before_and_after():
    """Test 5 (owner 2026-11-11: "Switch to the new look"): every Short carries
    it, so the 14 days before are the control, each Short at 3 days old."""
    rows, posts = [], []
    for i in range(14):
        day = dt.date(2026, 10, 29) + dt.timedelta(days=i)                    # before: 200 views at 3 days
        rows.append((f"b{i}", f"{day}T03:00", [(0, 5, 0), (3, 200, 5)]))
        posts.append({"date": day.isoformat(), "video_id": f"b{i}", "experiment": "edit:x"})
    for i in range(14):
        day = dt.date(2026, 11, 12) + dt.timedelta(days=i)                    # after: 300
        rows.append((f"a{i}", f"{day}T03:00", [(0, 5, 0), (3, 300, 9)]))
        posts.append({"date": day.isoformat(), "video_id": f"a{i}", "experiment": "edit:x"})
    posts.append({"date": "2026-11-13", "video_id": "s1", "experiment": "story:y"})   # not an edit: ignored
    views = mk.Views(_analytics(rows))
    test = {"id": "new-look", "kind": "views_before_after", "age": 3, "status": "running", "started": "2026-11-12"}
    got = mk.judge(test, posts, views, dt.date(2026, 11, 29))
    assert got["before"] == {"shorts": 14, "median": 200}
    assert got["during"]["shorts"] == 14 and got["change"] == 1.5 and got["verdict"] == "win"
    early = mk.judge(test, posts, views, dt.date(2026, 11, 20))
    assert "verdict" not in early and early["during"]["median"] == 300
    ledger = json.loads((ROOT / "data" / "marketing_tests.json").read_text(encoding="utf-8"))
    t = next(t for t in ledger["tests"] if t["id"] == "new-look")
    assert t["kind"] == "views_before_after" and t["status"] == "running" and t["started"] == "2026-11-12"
