"""The HQ app's studio snapshot: schedules, posting slots, bot status, numbers."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hq_snapshot as hq  # noqa: E402

UTC = dt.timezone.utc


def t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_next_cron_daily_weekly_and_weekday_ranges():
    assert hq.next_cron("0 3 * * *", t("2026-10-21T00:12:00")) == t("2026-10-21T03:00:00")
    assert hq.next_cron("0 3 * * *", t("2026-10-21T03:00:00")) == t("2026-10-22T03:00:00")
    # 2026-10-21 is a Wednesday; "1" is Monday
    assert hq.next_cron("0 6 * * 1", t("2026-10-21T12:00:00")) == t("2026-10-26T06:00:00")
    # Friday afternoon -> Monday noon for a weekdays-only schedule
    assert hq.next_cron("0 12 * * 1-5", t("2026-10-23T13:00:00")) == t("2026-10-26T12:00:00")
    assert hq.next_cron("*/15 * * * *", t("2026-10-21T00:16:00")) == t("2026-10-21T00:30:00")
    assert hq.next_cron("0 4 * * 0", t("2026-10-21T00:00:00")) == hq.next_cron("0 4 * * 7", t("2026-10-21T00:00:00"))
    assert hq.next_cron("not a cron", t("2026-10-21T00:00:00")) is None


def test_producer_schedule_is_read_from_the_live_workflow():
    assert sorted(hq.crons("daily-short.yml")) == sorted(
        ["0 3 * * *", "0 7 * * *", "0 11 * * *", "0 15 * * *", "0 19 * * *", "0 23 * * *"])
    assert hq._env_value("daily-short.yml", "MAX_POSTS_PER_DAY", "x") == "2"
    assert hq._env_value("daily-short.yml", "POST_SLOT_HOURS", "x") == "0,15"
    assert hq._env_value("daily-short.yml", "MIN_GAP_HOURS", "x") == "6"


def test_next_post_follows_the_cap_slots_and_gap():
    now = t("2026-10-21T00:12:00")
    # nothing posted today: the first cron of the day
    assert hq.next_post([], now, t("2026-10-20T15:05:00"))["at"] == "2026-10-21T03:00:00Z"
    # one posted at 03:05: the second waits for the 15:00 slot (also > 6 h later)
    one = [{"date": "2026-10-21"}]
    got = hq.next_post(one, t("2026-10-21T03:30:00"), t("2026-10-21T03:05:00"))
    assert got["at"] == "2026-10-21T15:00:00Z" and got["postsToday"] == 1
    # posted at 11:05 (a late first post): 15:00 is under 6 h, so 19:00
    got = hq.next_post(one, t("2026-10-21T11:30:00"), t("2026-10-21T11:05:00"))
    assert got["at"] == "2026-10-21T19:00:00Z"
    # both posted: tomorrow's first cron
    two = [{"date": "2026-10-21"}, {"date": "2026-10-21"}]
    assert hq.next_post(two, t("2026-10-21T16:00:00"), t("2026-10-21T15:05:00"))["at"] == "2026-10-22T03:00:00Z"


def test_bot_status_reads_runs():
    assert hq.bot_status(None) == "idle"
    assert hq.bot_status({"status": "in_progress"}) == "working"
    assert hq.bot_status({"status": "queued"}) == "queued"
    assert hq.bot_status({"status": "completed", "conclusion": "failure"}) == "failed"
    assert hq.bot_status({"status": "completed", "conclusion": "success"}) == "idle"


def test_latest_run_per_workflow_wins():
    runs = [
        {"path": ".github/workflows/daily-short.yml", "created_at": "2026-10-20T03:00:00Z", "conclusion": "failure"},
        {"path": ".github/workflows/daily-short.yml", "created_at": "2026-10-20T15:00:00Z", "conclusion": "success"},
        {"path": ".github/workflows/pull-analytics.yml", "created_at": "2026-10-20T19:00:00Z"},
    ]
    newest = hq.latest_runs(runs)
    assert newest["daily-short.yml"]["conclusion"] == "success"
    assert set(newest) == {"daily-short.yml", "pull-analytics.yml"}


def test_runs_fall_back_to_the_hq_status_branch(monkeypatch):
    run = {"id": 1, "path": ".github/workflows/daily-short.yml", "created_at": "2026-10-21T03:00:00Z"}
    monkeypatch.setattr(hq, "_get_json", lambda url: None)          # no API in this session
    monkeypatch.setattr(hq, "runs_from_branch", lambda: [run])
    assert hq.fetch_runs() == ([run], "hq-status branch")
    monkeypatch.setattr(hq, "runs_from_branch", lambda: [])
    assert hq.fetch_runs() == ([], None)                           # the page then says "Unknown"
    monkeypatch.setattr(hq, "_get_json", lambda url: {"workflow_runs": [run]})
    assert hq.fetch_runs() == ([run], "api")


def test_hq_status_workflow_follows_every_bot_by_its_real_name():
    """workflow_run matches workflows by their `name:`, so a renamed bot would
    silently stop updating the HQ."""
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "hq-status.yml").read_text())
    on = wf.get("on") or wf.get(True)
    listened = set(on["workflow_run"]["workflows"])
    names = {yaml.safe_load((ROOT / ".github" / "workflows" / b["workflow"]).read_text())["name"]
             for b in hq.BOTS}
    assert names <= listened, names - listened
    src = (ROOT / ".github" / "workflows" / "hq-status.yml").read_text()
    for b in hq.BOTS:
        assert b["workflow"] in src, b["workflow"]   # quiet bots' newest run is fetched too


def test_channel_numbers(tmp_path, monkeypatch):
    rows = ["pulled_on,subscribers,total_views,videos"]
    start = dt.date(2026, 7, 1)
    for i in range(112):
        d = start + dt.timedelta(days=i)
        rows.append(f"{d.isoformat()},{100 + i},{1000 + 50 * i},{10 + i}")
    rows.append(rows[-1].replace(f",{10 + 111}", f",{10 + 112}"))   # a same-day re-pull: last wins
    (tmp_path / "channel_stats.csv").write_text("\n".join(rows) + "\n")
    monkeypatch.setattr(hq, "DATA", tmp_path)
    c = hq.channel(t("2026-10-21T00:00:00"))
    assert c["asOf"] == "2026-10-20"
    assert c["subs"] == 211 and c["subsWeekAgo"] == 204
    assert c["videos"] == 122
    assert c["views7d"] == 350 and c["views90d"] == 4500
    assert len(c["viewsDaily"]) == 30 and all(p["v"] == 50 for p in c["viewsDaily"])
    assert c["goalSubs"] == 500 and c["goalViews90d"] == 3_000_000


def test_build_offline_is_one_small_json_document():
    doc = hq.build(now=t("2026-10-21T00:12:00"), runs=[])
    raw = json.dumps(doc)
    assert len(raw) < 200_000        # one db document holds at most 256 KiB
    assert [b["id"] for b in doc["bots"]][0] == "producer"
    assert "posted today" in doc["bots"][0]["note"]
    assert doc["nextPost"]["cap"] == 2
    assert all(b["url"].startswith("https://github.com/") for b in doc["bots"])


def test_the_snapshot_carries_the_shelf_and_the_next_edit_id():
    """The HQ warns on a low quote shelf and plays Apelles' rehearsal only when
    it is of the quote that airs next (2026-10-23)."""
    doc = hq.build(now=t("2026-10-23T22:00:00"), runs=[])
    sh = doc["shelf"]
    assert {"left", "days", "runsOut", "low", "target", "warn", "toTarget"} <= set(sh)
    assert sh["perDay"] == doc["nextPost"]["cap"]
    assert doc["nextOnAir"]["id"] and doc["nextOnAir"]["left"] == sh["left"]
    preview = next(b for b in doc["bots"] if b["id"] == "preview")
    assert preview["next"]          # rehearses on a schedule now, not only when asked
