"""Cicero's test "journal-cta" (owner 2026-11-24, in chat: "we need to entice
people to buy something off gum road on the shorts"): the day's third Short
ends with a short, TRUE pitch for the Stoic Reset, for 14 days from 2026-11-25.
Flag off = nothing changes."""
import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edit_type  # noqa: E402
import journal_cta as jc  # noqa: E402
import marketer as mk  # noqa: E402

D = dt.date
ENTRY = {"id": "journal-cta", "status": "running", "started": "2026-11-25", "end": "2026-12-08",
         "exclude": ["2026-11-24"]}
HYPE = ("forever", "guarantee", "change your life", "changes your life", "limited", "hurry", "last chance",
        "only today", "now or never", "countdown", "reviews", "thousands", "#1", "best-selling", "free")


def _ledger(tmp_path, monkeypatch, **over):
    p = tmp_path / "marketing_tests.json"
    p.write_text(json.dumps({"tests": [{**ENTRY, **over}]}))
    monkeypatch.setattr(jc, "MARKETING_TESTS", p)


def test_the_ledger_entry_is_a_dated_14_day_test():
    t = next(t for t in json.loads((ROOT / "data/marketing_tests.json").read_text())["tests"]
             if t["id"] == "journal-cta")
    assert t["status"] == "running" and t["started"] == "2026-11-25" and t["end"] == "2026-12-08"
    assert (D.fromisoformat(t["end"]) - D.fromisoformat(t["started"])).days + 1 == 14
    assert t["kind"] == "third_vs_others" and t["ask"] == "idea-journal-cta"
    assert "2026-11-24" in t["exclude"]                       # today's 19:00 Short airs unpainted
    assert "gum road" in t["approved"] and "owner, in chat" in t["approved"]
    assert "gum road" in t["why"] and "short-cta" in t["change"] and "Gumroad" in t["measure"]


def test_off_means_nothing_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(jc, "MARKETING_TESTS", tmp_path / "missing.json")
    assert not jc.active(2, D(2026, 11, 25))
    _ledger(tmp_path, monkeypatch, status="queued")
    assert not jc.active(2, D(2026, 11, 25))
    _ledger(tmp_path, monkeypatch, status="done")
    assert not jc.active(2, D(2026, 11, 26))


def test_the_date_window_and_the_third_post(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    assert not jc.active(2, D(2026, 11, 24))                  # today: no pitch
    assert jc.active(2, D(2026, 11, 25))                      # the first pitch Short
    assert jc.active(2, D(2026, 12, 8))                       # the last day
    assert not jc.active(2, D(2026, 12, 9))                   # switched itself off
    assert not jc.active(0, D(2026, 11, 26)) and not jc.active(1, D(2026, 11, 26))   # only the third
    assert not jc.active(3, D(2026, 11, 26)) and not jc.active(None, D(2026, 11, 26))
    _ledger(tmp_path, monkeypatch, exclude=["2026-11-24", "2026-11-27"])
    assert not jc.active(2, D(2026, 11, 27)) and jc.active(2, D(2026, 11, 28))


def test_the_air_day_comes_from_airday(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("REEL_TODAY", "2026-11-24")
    assert not jc.active(2)
    monkeypatch.setenv("REEL_TODAY", "2026-11-26")
    assert jc.active(2)


def test_the_closing_line_fits_the_budget_and_is_true():
    assert jc.word_count(jc.CLOSING_LINE) <= jc.MAX_CLOSING_WORDS == 14
    assert len(jc.CLOSING_LINE) <= 80                         # a few cents of ElevenLabs characters
    assert jc.CLOSING_LINE == "If this one hit home, the Stoic Reset is thirty days of exactly this."
    for text in (jc.CLOSING_LINE, jc.PINNED, " ".join(jc.CARD_LINES)):
        low = text.lower()
        assert not any(w in low for w in HYPE), text


def test_the_pinned_comment_points_to_the_channel_page():
    assert "channel page" in jc.PINNED and "http" not in jc.PINNED        # links in Shorts comments are dead
    assert "30-day" in jc.PINNED and "C$5.99" in jc.PINNED and len(jc.PINNED) < 300


def test_the_tracking_link_keeps_the_journal_line():
    d = "Q.\n\n---\nTry our 30-Day Guided Journal ONLY $5.99 - https://soicism.gumroad.com/l/cslosv"
    out = jc.with_tracking(d)
    assert out.endswith("https://soicism.gumroad.com/l/cslosv?ref=short-cta") and out.startswith("Q.")
    assert jc.with_tracking(out) == out                                   # idempotent
    assert jc.TRACKING_URL == "https://soicism.gumroad.com/l/cslosv?ref=short-cta"


def test_the_card_renders_with_the_key_word_red():
    ev = edit_type.end_card_events(list(jc.CARD_LINES), jc.CARD_ACCENT, 20.0, 22.5)
    text = "\n".join(ev)
    assert "THE" in text and "30 days. One page a day." in text and "Link on our channel page" in text
    red = edit_type._c(edit_type.emphasis_colour())
    assert f"\\1c{red}}}RESET" in text and "0:00:20.00,0:00:22.50" in text
    assert edit_type.end_card_events([], "", 1.0, 2.0) == [] and edit_type.end_card_events(["A"], "", 3.0, 3.0) == []
    # it fits the frame: the title is measured, not guessed
    f = edit_type.font(edit_type.HOOK_FONT)
    fs = edit_type.END_CARD_TITLE_FS
    while fs > 80 and f.width(jc.CARD_LINES[0], fs) > edit_type.END_CARD_MAX_W:
        fs -= 4
    assert f.width(jc.CARD_LINES[0], fs) <= edit_type.END_CARD_MAX_W < 1080 - 100


def test_the_render_shows_the_card_last_and_steps_the_quote_aside(monkeypatch):
    monkeypatch.setenv("REEL_END_CARD", jc.card_text())
    monkeypatch.setenv("REEL_END_CARD_ACCENT", jc.CARD_ACCENT)
    monkeypatch.setenv("REEL_END_CARD_SECONDS", "2.5")
    import render
    importlib.reload(render)
    try:
        ev = render._type_v2_events("Stop fearing.", [0.2, 0.5], 2.0, "Fear is a habit.", "Seneca",
                                    [(3.0, 3.4), (3.4, 3.8), (3.8, 4.2), (4.2, 4.6)], 0.0, None, 14.0)
        text = "\n".join(ev)
        assert "0:00:11.50,0:00:14.00" in text and "THE" in text and "Link on our channel page" in text
        quote = [e for e in ev if "TypeQuote" in e]
        assert quote and all("0:00:14.00" not in e.split(",")[2] for e in quote)   # the quote ends before the card
    finally:
        monkeypatch.delenv("REEL_END_CARD")
        importlib.reload(render)
    plain = render._type_v2_events("Stop fearing.", [0.2, 0.5], 2.0, "Fear is a habit.", "Seneca",
                                   [(3.0, 3.4), (3.4, 3.8), (3.8, 4.2), (4.2, 4.6)], 0.0, None, 14.0)
    assert "Link on our channel page" not in "\n".join(plain)                  # flag off: nothing changes


def test_the_pipeline_wires_the_card_only_for_the_pitch_short(monkeypatch):
    import daily_post
    import edits
    bank = json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))
    content = edits.as_content(next(q for q in bank if q.get("scenes")))
    monkeypatch.setenv("REEL_EDIT_LOOK", "painted")
    pack = {}
    daily_post._type_edit(pack, content, "edit")
    assert "REEL_END_CARD" not in pack
    content["_journalCta"] = True
    daily_post._type_edit(pack, content, "edit")
    assert pack["REEL_END_CARD"] == "THE STOIC RESET|30 days. One page a day.|Link on our channel page"
    assert pack["REEL_END_CARD_ACCENT"] == "RESET" and pack["REEL_END_CARD_SECONDS"] == "2.5"
    src = (ROOT / "scripts/daily_post.py").read_text()
    assert "journal_cta.active(POSTS_TODAY)" in src and "journal_cta.CLOSING_LINE" in src
    assert "journal_cta.with_tracking(description)" in src


def _analytics(rows):
    from test_marketer import _analytics as a
    return a(rows)


def test_marketer_compares_the_third_short_with_the_days_others():
    rows, posts = [], []

    def day(d, v1, v2, v3):
        for i, (n, hh) in enumerate(((v1, "01"), (v2, "07"), (v3, "19"))):
            vid = f"{d}-{i}"
            rows.append((vid, f"{d}T{hh}:00", [(0, 5, 0), (3, n, 3)]))
            posts.append({"date": d, "video_id": vid, "experiment": "edit:x"})
    for d in ("2026-11-13", "2026-11-14", "2026-11-15"):
        day(d, 300, 300, 300)                                  # before: ratio 1.0
    day("2026-11-24", 300, 300, 30)                            # excluded: aired unpainted
    for k in range(7):
        day(str(D(2026, 11, 25) + dt.timedelta(days=k)), 300, 300, 330)   # during: 1.1x
    views = mk.Views(_analytics(rows))
    test = {"id": "journal-cta", "kind": "third_vs_others", "age": 3, "status": "running",
            "started": "2026-11-25", "end": "2026-12-08", "baselineSince": "2026-11-13", "exclude": ["2026-11-24"]}
    got = mk.judge(test, posts, views, D(2026, 12, 20))
    assert got["before"] == {"days": 3, "median": 1.0}
    assert got["during"]["days"] == 7 and got["during"]["median"] == 1.1 and got["during"]["ends"] == "2026-12-08"
    assert got["change"] == 1.1 and got["verdict"] == "no clear change"
    early = mk.judge(test, posts, views, D(2026, 11, 30))
    assert "verdict" not in early
    # the pitch costing views shows as a loss
    posts2 = [dict(p) for p in posts]
    rows2 = [(v, p, [(a, (n // 2 if v.endswith("-2") and v >= "2026-11-25" else n), l) for a, n, l in sn])
             for v, p, sn in rows]
    loss = mk.judge(test, posts2, mk.Views(_analytics(rows2)), D(2026, 12, 20))
    assert loss["verdict"] == "loss"
