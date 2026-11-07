"""The scout (owner 2026-11-07, Jake Trinder's advice: "you need evidence that
they will actually watch these videos before you even press record"): the
Stoicism Shorts winning on other channels, by our themes, with their titles."""
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import scout  # noqa: E402
import shelf  # noqa: E402


class _Req:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class _YT:
    """A fake YouTube: two searches' worth of Shorts and their channels."""

    def __init__(self):
        self.searched = []
        yt = self
        vids = {
            "a": ("Stop overthinking: Marcus Aurelius", "big", 2_000_000, "PT45S"),
            "b": ("Seneca on wasting time", "small", 300_000, "PT58S"),
            "c": ("The calm man always wins", "tiny", 50_000, "PT30S"),       # 40 subscribers: counted as 1,000
            "d": ("Stoic morning routine (full talk)", "small", 900_000, "PT12M"),   # not a Short
            "e": ("Discipline", "small", 5_000, "PT20S"),                     # too few views
            "f": ("Our own Short", scout.OUR_CHANNEL, 90_000, "PT20S"),       # ours: never counted
            "g": ("Hidden subscribers", "hidden", 400_000, "PT40S"),
            "h": ("무뚝뚝한 아들이 엄마 기분 풀어준 비법", "small", 600_000, "PT40S"),   # not English
        }
        chans = {"big": 5_000_000, "small": 10_000, "tiny": 40, scout.OUR_CHANNEL: 260, "hidden": None}

        class Search:
            def list(self, **k):
                yt.searched.append(k)
                assert k["videoDuration"] == "short" and k["order"] == "viewCount" and k["type"] == "video"
                ids = ["a", "b", "c", "d"] if k["q"] == "stoicism" else ["b", "e", "f", "g", "h"]
                return _Req({"items": [{"id": {"videoId": i}} for i in ids]})

        class Videos:
            def list(self, part, id):  # noqa: A002
                return _Req({"items": [{"id": i, "snippet": {"title": vids[i][0], "channelId": vids[i][1],
                                                             "channelTitle": vids[i][1], "publishedAt": "2026-11-01T00:00:00Z"},
                                        "statistics": {"viewCount": str(vids[i][2])},
                                        "contentDetails": {"duration": vids[i][3]}} for i in id.split(",")]})

        class Channels:
            def list(self, part, id):  # noqa: A002
                return _Req({"items": [{"id": c, "statistics": ({"hiddenSubscriberCount": True} if chans[c] is None
                                                                else {"subscriberCount": str(chans[c])})}
                                       for c in id.split(",")]})

        self._s, self._v, self._c = Search(), Videos(), Channels()

    def search(self):
        return self._s

    def videos(self):
        return self._v

    def channels(self):
        return self._c


def test_durations_and_topics_are_read_from_the_title():
    assert scout.seconds("PT1M5S") == 65 and scout.seconds("PT45S") == 45 and scout.seconds("") == 0
    assert scout.themes_of("Stop overthinking: Marcus Aurelius") == ["control"]
    assert "time" in scout.themes_of("Seneca on wasting time")
    assert scout.author_of("Stop overthinking: Marcus Aurelius") == "Marcus Aurelius"
    assert scout.author_of("The calm man always wins") is None
    assert set(scout.THEME_WORDS) == shelf.THEMES                       # the same 12 themes as the shelf


def test_outliers_are_shorts_that_reached_far_past_their_channel():
    s = scout.run(_YT(), dt.date(2026, 11, 7), seeds=["stoicism", "stoic"])
    # 50,000 views on a 40-subscriber channel counts as 1,000 subscribers: 50x;
    # Seneca's 300,000 on 10,000: 30x; the 5-million channel's 2 million: its usual (0.4x)
    assert [(o["title"], o["score"]) for o in s["top"]] == [("The calm man always wins", 50.0),
                                                           ("Seneca on wasting time", 30.0)]
    assert s["videos"] == 8 and s["outliers"] == 2      # no long talk, low views, hidden, ours, usual hit
    assert scout.english("Master Your Emotions 🧠💯") and not scout.english("무뚝뚝한 아들이")      # or other language


def test_the_read_groups_the_winners_by_our_themes_and_philosophers():
    s = scout.run(_YT(), dt.date(2026, 11, 7), seeds=["stoicism", "stoic"])
    themes = {r["key"]: r for r in s["themes"]}
    assert themes["time"]["outliers"] == 1 and themes["anger"]["outliers"] == 1 and "control" not in themes
    assert [r["key"] for r in s["authors"]] == ["Seneca"]
    md = scout.markdown(s)
    assert "## Topics that win (by our themes)" in md and "## The titles that won (the packaging)" in md
    assert "[Seneca on wasting time](https://youtube.com/shorts/b)" in md


def test_the_search_asks_for_recent_us_shorts():
    yt = _YT()
    scout.run(yt, dt.date(2026, 11, 7), seeds=["stoicism"])
    k = yt.searched[0]
    assert k["publishedAfter"] == "2026-10-08T00:00:00Z" and k["regionCode"] == "US" and k["maxResults"] == 50


def test_glaux_scouts_daily_and_a_failure_never_fails_the_job():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pull-analytics.yml").read_text())
    steps = {s.get("name"): s for s in wf["jobs"]["analytics"]["steps"]}
    step = steps["Scout the niche (what's winning on other channels)"]
    assert step["run"] == "python scripts/scout.py" and step["continue-on-error"] is True
    assert "data/scout.json data/scout.md" in steps["Commit analytics"]["run"]


def test_a_failed_scout_exits_cleanly(monkeypatch, tmp_path):
    import publish  # noqa: PLC0415
    monkeypatch.setattr(publish, "_service", lambda: (_ for _ in ()).throw(RuntimeError("quotaExceeded")))
    monkeypatch.setattr(scout, "OUT_JSON", tmp_path / "scout.json")
    monkeypatch.setattr(sys, "argv", ["scout.py"])
    assert scout.main() == 0 and not (tmp_path / "scout.json").exists()
