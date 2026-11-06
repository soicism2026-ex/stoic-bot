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
        assert t["status"] in ("proposed", "running", "done", "declined")
        assert t.get("started") or t["status"] in ("proposed", "declined"), t["id"]
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

def test_the_pinned_question_test_compares_viewer_comments_by_arm():
    start = dt.date(2026, 11, 6)
    posts, analytics = [], []
    for d in range(14):
        day = start + dt.timedelta(days=d)
        themed = d % 2 == 0
        posts.append({"date": day.isoformat(), "video_id": f"v{d}", "experiment": f"edit:e{d}"})
        # the channel's own comment is 1 of the count on every Short
        analytics.append({"video_id": f"v{d}", "pulled_on": (day + dt.timedelta(days=3)).isoformat(),
                          "views": "200", "comments": str(1 + (2 if themed else 0))})
    test = {"id": "pinned-question", "kind": "pinned_question", "status": "running", "started": start.isoformat()}
    got = mk.judge(test, posts, mk.Views(analytics), dt.date(2026, 11, 21), analytics, [])
    arms = got["during"]["arms"]
    assert arms["themed"] == {"shorts": 7, "views": 1400, "comments": 14, "per1k": 10.0}
    assert arms["generic"]["comments"] == 0 and got["verdict"] == "win"
    proposed = mk.judge({**test, "status": "proposed", "started": None}, posts, mk.Views(analytics), TODAY,
                        analytics, [])
    assert "during" not in proposed and "verdict" not in proposed


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


def test_the_ledger_holds_tests_2_and_3_waiting_for_the_owner():
    ledger = json.loads((ROOT / "data" / "marketing_tests.json").read_text())
    by_id = {t["id"]: t for t in ledger["tests"]}
    assert by_id["pinned-question"]["kind"] == "pinned_question" and by_id["pinned-question"]["ask"] == "pinned-question"
    assert by_id["playlists"]["kind"] == "traffic_source" and by_id["playlists"]["source"] == "PLAYLIST"
    assert by_id["second-post-morning"]["status"] == "running" and by_id["second-post-morning"]["started"] == "2026-11-06"


def test_the_read_shows_who_watches(tmp_path, monkeypatch):
    monkeypatch.setattr(mk, "DATA", tmp_path)
    (tmp_path / "audience.json").write_text(json.dumps({
        "pulled_on": "2026-11-06", "countries": [{"key": "US", "views": 500, "share": 0.4}],
        "sources": [{"key": "SHORTS", "views": 1100, "share": 0.9}], "subscribed": []}))
    md = mk.markdown({**mk.read(today=TODAY), "audience": mk.audience()})
    assert "## Who watches" in md and "US 40%" in md and "SHORTS 90%" in md
