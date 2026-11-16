"""Fama (scripts/fama.py): today's trends tied to the next quote. No network."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import edits  # noqa: E402
import fama  # noqa: E402
import up_next  # noqa: E402

NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)

TRENDS_XML = b"""<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>Black Friday deals</title><ht:approx_traffic>200K+</ht:approx_traffic>
<ht:news_item><ht:news_item_title>Best Black Friday deals of 2026</ht:news_item_title><ht:news_item_source>CNET</ht:news_item_source></ht:news_item></item>
<item><title>Lakers</title><ht:approx_traffic>2M+</ht:approx_traffic></item></channel></rss>"""
NEWS_XML = b"""<?xml version="1.0"?><rss><channel>
<item><title>NASA shows new Mars images - Reuters</title></item></channel></rss>"""
WIKI = {"mostread": {"articles": [
    {"normalizedtitle": "Main Page", "views": 9},
    {"normalizedtitle": "Artemis program", "views": 90000, "description": "NASA lunar programme"}]},
    "news": [{"story": "<b>Apple</b> unveils a phone", "links": [{"normalizedtitle": "Apple Inc."}]}]}


def test_feeds_parse():
    t = fama.parse_trends_rss(TRENDS_XML)
    assert t[0] == {"topic": "Black Friday deals", "score": 200000.0,
                    "headlines": ["Best Black Friday deals of 2026"], "source": "google-trends"}
    assert t[1]["score"] == 2e6
    w = fama.parse_wikipedia(WIKI)
    assert [x["topic"] for x in w] == ["Artemis program", "Apple Inc."]   # Main Page dropped
    assert w[0]["headlines"] == ["NASA lunar programme"] and w[1]["headlines"] == ["Apple unveils a phone"]
    n = fama.parse_news_rss(NEWS_XML)
    assert n[0]["topic"] == "NASA shows new Mars images"


def test_fetch_dedupes_and_survives_failures(monkeypatch):
    def get(url):
        if "trends" in url:
            return TRENDS_XML
        if "wikimedia" in url:
            assert "/2026/11/16" in url
            return json.dumps(WIKI).encode()
        raise OSError("down")
    monkeypatch.setattr(fama, "_get", get)
    topics = [t["topic"] for t in fama.fetch(dt.date(2026, 11, 16))]
    assert "Black Friday deals" in topics and "Artemis program" in topics
    monkeypatch.setattr(fama, "_get", lambda u: (_ for _ in ()).throw(OSError("x")))
    assert fama.fetch(dt.date(2026, 11, 16)) == []


def _t(topic, *heads):
    return {"topic": topic, "score": 1.0, "headlines": list(heads), "source": "x"}


def test_screen_drops_tragedy_politics_and_minors_keeps_the_rest():
    drop = [_t("Storm", "Hurricane kills 12"), _t("Senator resigns"), _t("Big game", "Fans shot at stadium"),
            _t("Zoo news", "A 14-year-old finds a fossil"), _t("Court ruling", "Supreme Court hears case"),
            _t("Singer", "Protest outside concert"), _t("Trial begins")]
    keep = [_t("Lakers", "Lakers beat Celtics"), _t("Black Friday deals"), _t("Artemis program", "NASA lunar programme"),
            _t("iPhone 18", "Apple unveils a phone"), _t("Powerball", "Jackpot grows to 900 million"),
            _t("Snow forecast", "First snow of the season")]
    assert fama.screen(drop) == []
    assert fama.screen(keep) == keep
    assert fama.BLOCKED and "shooting" in fama.TRAGEDY_WORDS and "trump" in fama.POLITICS_WORDS


TREND = _t("Black Friday deals", "Best Black Friday deals of 2026", "Stores open at 6 am")
CANDS = [{"id": "e1", "author": "Seneca", "theme": "desire", "quote": "q", "hook": "old hook"},
         {"id": "e2", "author": "Epictetus", "theme": "control", "quote": "q2", "hook": "h2"}]
GOOD = {"trend_index": 0, "quote_id": "e1", "fit": 8, "hook": "Buying it to feel enough?",
        "punch": "enough", "lead": "Black Friday sells wanting; Seneca asked what is enough.",
        "question": "Will you buy it or keep your money?", "tags": ["black friday", "deals", "stoicism"]}


def v(**kw):
    return fama.validate({**GOOD, **kw}, [TREND], CANDS, {"some other hook"})


def test_validation_accepts_a_good_plan():
    ok, why = v()
    assert ok and ok["edit"] == "e1" and ok["theme"] == "desire" and why == ""


@pytest.mark.parametrize("kw,word", [
    ({"lead": "Elon Musk bought Black Friday."}, "invented name"),
    ({"lead": "Over 40 million shoppers."}, "invented number"),
    ({"hook": "Wait"}, "2-9"),
    ({"hook": "one two three four five six seven eight nine ten"}, "2-9"),
    ({"punch": "money"}, "punch"),
    ({"lead": " ".join(["word"] * 23)}, "22"),
    ({"question": " ".join(["word"] * 21)}, "20"),
    ({"question": "Comment your pick?"}, "asks"),
    ({"hook": "Subscribe for enough now"}, "asks"),
    ({"tags": ["deals", "#sale", "x"]}, "#"),
    ({"hook": "Buying it after the war?", "punch": "war"}, "screened"),
    ({"fit": 6}, "fit"),
    ({"trend_index": 5}, "trend_index"),
    ({"quote_id": "nope"}, "not offered"),
    ({"hook": "old hook now", "punch": "now"}, None),
])
def test_validation_rejects(kw, word):
    ok, why = v(**kw)
    if word is None:
        assert ok                       # control: a different hook is fine
    else:
        assert ok is None and word in why


def test_validation_rejects_a_repeated_hook():
    ok, why = fama.validate(GOOD, [TREND], CANDS, {"buying it to feel enough"})
    assert ok is None and "aired" in why
    assert fama.validate({"none": True}, [TREND], CANDS, set())[0] is None


# --- plan() ---------------------------------------------------------------
@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(fama, "PLAN", tmp_path / "topical.json")
    monkeypatch.setattr(edits, "TOPICAL", tmp_path / "topical.json")
    monkeypatch.setattr(fama, "_rows", lambda: [])
    monkeypatch.setattr(fama, "fetch", lambda today=None: [TREND])
    bank = [{"id": "e1", "author": "Epictetus", "theme": "desire", "quote": "Q one text", "hook": "old hook",
             "citation": "c", "visuals": []},
            {"id": "e2", "author": "Seneca", "theme": "control", "quote": "Q two text", "hook": "h2",
             "citation": "c", "visuals": []}]
    monkeypatch.setattr(edits, "load", lambda: bank)
    monkeypatch.setattr(edits, "jammed_ids", lambda: set())
    monkeypatch.setattr(edits, "theme_rank", lambda: {})
    monkeypatch.setattr(edits, "search_use", lambda: None)
    import llm
    monkeypatch.setattr(llm, "available", lambda f=None: True)
    monkeypatch.setattr(llm, "provider", lambda f=None: "anthropic")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps(GOOD))
    return tmp_path


def test_candidates_simulate_the_rotation(world):
    c = fama.candidates([])
    assert [x["id"] for x in c] == ["e1", "e2"] and c[0]["author"] == "Epictetus"


def test_plan_writes_the_file_and_keeps_it(world, monkeypatch, capsys):
    p = fama.plan(NOW)
    assert p["edit"] == "e1" and p["forPost"] == 0 and p["trend"]["topic"] == "Black Friday deals"
    assert p["airDay"] and p["decidedAt"] == "2026-11-16T12:00:00Z" and p["tags"][0] == "black friday"
    assert "e1" in capsys.readouterr().out
    import llm
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("replanned")))
    assert fama.plan(NOW + dt.timedelta(hours=3)) == p                # same post, < 20 h: unchanged


def test_plan_replans_for_a_new_post_or_after_20_hours(world, monkeypatch):
    p = fama.plan(NOW)
    monkeypatch.setattr(fama, "_now", lambda: NOW + dt.timedelta(hours=21))
    import llm
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps({"none": True}))
    assert "none" in fama.plan(NOW + dt.timedelta(hours=21)) and p["edit"] == "e1"


def test_plan_writes_none_when_the_model_fails(world, monkeypatch):
    import llm
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no credit")))
    p = fama.plan(NOW)
    assert p["none"].startswith("error") and p["forPost"] == 0
    assert json.loads((world / "topical.json").read_text())["none"]
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "I think maybe")
    (world / "topical.json").unlink()
    assert "not JSON" in fama.plan(NOW)["none"]


def test_plan_writes_none_without_safe_trends(world, monkeypatch):
    monkeypatch.setattr(fama, "fetch", lambda today=None: [_t("Hurricane hits coast")])
    assert fama.plan(NOW)["none"] == "no safe trend today"


# --- edits integration ----------------------------------------------------
def _plan_file(world, **kw):
    plan = {"forPost": 0, "airDay": "2026-11-16", "decidedAt": "2026-11-16T10:00:00Z",
            "trend": {"topic": "Black Friday deals", "source": "google-trends", "score": 1, "headlines": []},
            "edit": "e2", "theme": "control", "hook": "Buying it to feel enough?", "punch": "enough",
            "lead": "Black Friday sells wanting.", "question": "Buy it or keep your money?",
            "tags": ["black friday", "deals", "stoicism"], "model": "m", **kw}
    (world / "topical.json").write_text(json.dumps(plan))
    return plan


def test_pick_returns_the_topical_quote_only_when_fresh_and_for_this_post(world):
    _plan_file(world)
    now = dt.datetime(2026, 11, 16, 12, tzinfo=dt.timezone.utc)
    assert edits.topical_for([], now)["edit"] == "e2"
    q = edits.pick([])                                  # real clock: the plan is days old
    assert q["id"] == "e1" and "_topical" not in q       # stale: the rotation decides
    assert edits.topical_for([], now + dt.timedelta(hours=19)) is None           # 21 h old
    assert edits.topical_for([{"experiment": "edit:e1", "quote": "x"}], now) is None   # another post
    assert edits.topical_for([{"experiment": "edit:e2", "quote": "x"}], now) is None   # already aired
    _plan_file(world, forPost=0, none="no fit")
    assert edits.topical_for([], now) is None


def test_pick_with_a_fresh_plan(world):
    _plan_file(world, decidedAt=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    q = edits.pick([])
    assert q["id"] == "e2" and q["_topical"]["hook"] == "Buying it to feel enough?"
    assert edits.load()[1].get("_topical") is None       # a copy: the shelf is untouched
    c = edits.as_content(q)
    assert c["hook"] == "Buying it to feel enough?" and c["quote"] == "Q two text"   # the quote never changes
    assert c["_topical"]["punch"] == "enough"


def test_description_and_pinned_comment_use_the_lead_and_question(world):
    plan = _plan_file(world)
    q = {**edits.load()[1], "_topical": plan, "description": "Para one.\n\nPara two.", "question": "Old?"}
    c = edits.as_content(q)
    d = edits.description(c)
    assert d.startswith("Black Friday sells wanting.\n\nPara one.")
    assert f"{edits.QUESTION_MARK} Buy it or keep your money?" in d and "Old?" not in d
    assert "comment" not in d.lower()
    assert edits.pinned_comment(q) == "Buy it or keep your money?"
    plain = edits.description(edits.as_content({**edits.load()[1], "description": "Para one.", "question": "Old?"}))
    assert plain.startswith("Para one.") and "Old?" in plain


def test_up_next_plan_includes_the_topical_hook(world, monkeypatch):
    _plan_file(world, decidedAt=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert up_next.plan([], "2026-11-16")["topical"] == "Buying it to feel enough?"
    ok, why = up_next.need("e2", "2026-11-16",
                           {"edit": "e2", "airDay": "2026-11-16", "plan": {"topical": None}},
                           0, {"topical": "Buying it to feel enough?"})
    assert ok and "topical" in why
    (world / "topical.json").write_text(json.dumps({"forPost": 0, "none": "x", "decidedAt": "x"}))
    assert up_next.plan([], "2026-11-16")["topical"] is None


def test_daily_post_wiring():
    s = (ROOT / "scripts" / "daily_post.py").read_text()
    assert 'pack["REEL_HOOK_EMPHASIS"] = top["punch"]' in s and "_log_topical(" in s
    assert "topical_log.csv" in (ROOT / ".github/workflows/daily-short.yml").read_text()
    ep = (ROOT / ".github/workflows/edit-preview.yml").read_text()
    assert "scripts/fama.py plan" in ep and "ref: main" in ep
