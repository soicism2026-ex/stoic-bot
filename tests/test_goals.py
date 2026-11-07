"""The channel's goal (owner 2026-11-07: "Brainstorm some goal for this channel
for the new year i want to makr something we can work towards instead if
aimlessly trying things").

scripts/goals.py measures every option asked in the HQ from numbers the bots
already keep, so "are we on track?" always has a yes or no, and the HQ shows
the owner's pick the moment he taps it."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import goals as gl  # noqa: E402
import hq_snapshot as hq  # noqa: E402

METRICS = {"views", "subscribers", "views_90d", "best_short"}


def _stats(start: dt.date, days: int, subs0: int, subs_per_day: int, views0: int, views_per_day: int) -> gl.Stats:
    return gl.Stats([{"pulled_on": (start + dt.timedelta(days=i)).isoformat(),
                      "subscribers": str(subs0 + i * subs_per_day),
                      "total_views": str(views0 + i * views_per_day)} for i in range(days)])


def test_the_pace_is_the_last_four_weeks():
    st = _stats(dt.date(2026, 10, 1), 40, 200, 2, 10_000, 400)
    assert st.pace("total_views") == 400 and st.pace("subscribers") == 2
    assert gl.Stats([]).pace("total_views") is None


def test_views_count_from_the_goal_start():
    st = _stats(dt.date(2026, 12, 20), 30, 300, 2, 100_000, 1000)            # Dec 20 to Jan 18
    assert gl.measure("views", dt.date(2027, 1, 1), st, []) == 18_000         # Jan 1-18 only
    assert gl.measure("views", dt.date(2027, 6, 1), st, []) == 0              # not started yet
    assert gl.measure("subscribers", dt.date(2027, 1, 1), st, []) == 358      # a count, not a gain
    assert gl.measure("views_90d", dt.date(2027, 1, 1), st, []) == 29_000     # all the 30 days on record


def test_the_best_short_counts_only_shorts_from_the_start():
    analytics = [
        {"video_id": "old", "published_at": "2026-11-01T01:00:00Z", "views": "5000", "pulled_on": "2026-11-20"},
        {"video_id": "new", "published_at": "2026-11-08T01:00:00Z", "views": "300", "pulled_on": "2026-11-09"},
        {"video_id": "new", "published_at": "2026-11-08T01:00:00Z", "views": "900", "pulled_on": "2026-11-12"},
        {"video_id": "new2", "published_at": "2026-11-09T01:00:00Z", "views": "700", "pulled_on": "2026-11-12"},
    ]
    assert gl.best_short(analytics, dt.date(2026, 11, 7)) == (900, "new")
    assert gl.best_short([], dt.date(2026, 11, 7)) == (None, None)


def test_a_target_is_judged_by_its_pace_against_what_it_needs():
    st = _stats(dt.date(2027, 1, 1), 31, 400, 2, 0, 3000)                    # January: 3,000 views, 2 subs a day
    start, end, today = dt.date(2027, 1, 1), dt.date(2027, 12, 31), dt.date(2027, 1, 31)
    v = gl._judge("views", 90_000, 1_000_000, end, start, today, st)
    assert v["status"] == "on track" and v["pace"] == 3000 and v["needed"] == round(910_000 / 334, 1)
    assert gl._judge("subscribers", 460, 1000, end, start, today, st)["status"] == "on track"   # 2.0 vs 1.6
    slow = _stats(dt.date(2027, 1, 1), 31, 400, 1, 0, 1000)
    assert gl._judge("views", 30_000, 1_000_000, end, start, today, slow)["status"] == "behind"
    assert gl._judge("subscribers", 1000, 1000, end, start, today, st)["status"] == "reached"
    assert gl._judge("subscribers", 460, 1000, dt.date(2027, 1, 15), start, today, st)["status"] == "missed"
    early = gl._judge("views", 0, 1_000_000, end, start, dt.date(2026, 11, 7), st)
    assert early["status"] == "starts" and early["needed"] == round(1_000_000 / 365, 1) and early["onPace"] is True
    assert gl._judge("best_short", 900, 100_000, end, start, today, st)["status"] == "open"


def test_progress_points_at_the_next_checkpoint_and_keeps_score():
    goal = next(o for o in gl.load()["options"] if o["id"] == "million")
    st = _stats(dt.date(2026, 12, 31), 101, 340, 2, 50_000, 1500)            # Dec 31 to Apr 10
    p = gl.progress(goal, dt.date(2027, 4, 10), st, [])
    first, second = p["checkpoints"][0], p["checkpoints"][1]
    assert first["passed"] and first["met"] is True                           # 135,000 views and 520 subs by Mar 31
    assert not second["passed"] and p["next"]["by"] == "2027-06-30"
    assert p["targets"][0]["have"] == 150_000 and p["started"] and p["daysLeft"] == 265
    late = _stats(dt.date(2026, 12, 31), 101, 340, 0, 50_000, 100)            # a slow first quarter
    lp = gl.progress(goal, dt.date(2027, 4, 10), late, [])
    assert lp["checkpoints"][0]["met"] is False and lp["onTrack"] is False


def test_a_passed_checkpoint_is_judged_by_the_numbers_on_its_date():
    goal = next(o for o in gl.load()["options"] if o["id"] == "thousand")
    rows = _stats(dt.date(2026, 12, 31), 91, 300, 1, 0, 0).by_day             # 390 subscribers on Mar 31
    rows["2027-04-10"] = {"pulled_on": "2027-04-10", "subscribers": "600", "total_views": "0"}   # caught up later
    p = gl.progress(goal, dt.date(2027, 4, 10), gl.Stats(list(rows.values())), [])
    assert p["checkpoints"][0]["met"] is False and p["targets"][0]["have"] == 600


def test_the_options_asked_in_the_hq_are_well_formed():
    g = gl.load()
    ids = [o["id"] for o in g["options"]]
    assert g["ask"] == "goal-2027" and len(ids) == len(set(ids)) >= 3
    assert g["chosen"] in (None, *ids)
    for o in g["options"]:
        start, end = dt.date.fromisoformat(o["start"]), dt.date.fromisoformat(o["deadline"])
        assert o["title"] and start <= end, o["id"]
        metrics = {t["metric"] for t in o["targets"]}
        assert metrics <= METRICS and all(t["label"] and t["target"] > 0 for t in o["targets"]), o["id"]
        dates = [cp["by"] for cp in o["checkpoints"]]
        assert dates == sorted(dates) and dates[-1] <= o["deadline"], o["id"]
        for cp in o["checkpoints"]:
            assert {t["metric"] for t in cp["targets"]} <= metrics, (o["id"], cp["by"])
    million = next(o for o in g["options"] if o["id"] == "million")
    steps = [next(t["target"] for t in cp["targets"] if t["metric"] == "views") for cp in million["checkpoints"]]
    assert steps == sorted(steps) and steps[-1] == 1_000_000


def test_every_option_is_measured_today_from_the_real_numbers():
    s = gl.summary(today=dt.date(2026, 11, 7))
    assert [o["id"] for o in s["options"]] == [o["id"] for o in gl.load()["options"]]
    million = next(o for o in s["options"] if o["id"] == "million")
    views = million["targets"][0]
    assert views["have"] == 0 and views["status"] == "starts" and views["pace"] > 0      # counts from Jan 1
    subs = next(o for o in s["options"] if o["id"] == "thousand")["targets"][0]
    assert subs["have"] >= 250 and subs["status"] in ("on track", "behind")


def test_the_hq_carries_every_option_and_shows_the_pick_at_once():
    doc = hq.build(now=dt.datetime(2026, 11, 7, 1, tzinfo=dt.timezone.utc), runs=[])
    assert doc["goals"]["ask"] == "goal-2027"
    assert [o["id"] for o in doc["goals"]["options"]] == [o["id"] for o in gl.load()["options"]]
    assert len(json.dumps(doc)) < 200_000
    page = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")
    assert 'id="goal-block"' in page and "drawGoal();" in page
    assert 'ask.status === "answered" && g.options.some((o) => o.id === ask.answer)' in page   # the tap shows at once
