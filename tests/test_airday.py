"""src/airday.py: a rehearsal renders for the day its post airs; a live run can't be moved."""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import airday  # noqa: E402


def test_rehearsal_day_applies_only_to_dry_runs(monkeypatch):
    monkeypatch.setenv("REEL_TODAY", "2030-01-02")
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert airday.today() == dt.date.today()          # a live post ignores it
    monkeypatch.setenv("DRY_RUN", "1")
    assert airday.today() == dt.date(2030, 1, 2)
    monkeypatch.setenv("REEL_TODAY", "not a date")
    assert airday.today() == dt.date.today()


def test_next_post_airs_today_until_the_cap_then_tomorrow():
    now = dt.datetime(2026, 10, 23, 19, 40, tzinfo=dt.timezone.utc)
    one = [{"date": "2026-10-23"}]
    assert airday.next_air_day(one, 2, now) == dt.date(2026, 10, 23)        # 2nd post still to come
    assert airday.next_air_day(one * 2, 2, now) == dt.date(2026, 10, 24)    # both out
    assert airday.next_air_day([], 2, now.replace(hour=8)) == dt.date(2026, 10, 23)


def test_the_cap_comes_from_the_live_workflow_not_the_preview_env(monkeypatch):
    monkeypatch.setenv("MAX_POSTS_PER_DAY", "99")
    assert airday.live_cap() == 2


def test_every_day_keyed_choice_goes_through_airday():
    """Stock-shot index, sound-effect pair and music shuffle: if any still read
    the wall clock, a rehearsal would show different shots than what airs."""
    for f in ("src/backgrounds.py", "src/render.py"):
        src = (ROOT / f).read_text()
        assert "date.today()" not in src, f
        assert "_air_day()" in src, f
    main = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "today = airday.today().isoformat()" in main
    assert "edit_music.pick(post_rows, seed=str(today))" in main
