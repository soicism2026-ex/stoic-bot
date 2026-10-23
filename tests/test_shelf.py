"""The quote shelf (scripts/shelf.py): runway, and the door new quotes come in through.

2026-10-23: the edit bank had 18 days of quotes left, the story bank 1, and
the generated fallback needs API credit the account did not have. Nothing
watched it. These tests pin the runway maths and every rule a new quote must
pass before it can air.
"""
import copy
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edits  # noqa: E402
import shelf  # noqa: E402

# A real, unaired-looking entry to mutate: the bank's own first quote,
# checked against a bank that does not contain it.
BANK = edits.load()
GOOD = copy.deepcopy(BANK[0])
OTHERS = [q for q in BANK if q["id"] != GOOD["id"]]


def _why(**change):
    q = copy.deepcopy(GOOD)
    q.update(change)
    return " | ".join(shelf.problems(q, OTHERS, []))


def test_every_shelved_quote_passes_the_rules_it_would_be_held_to_today():
    for q in BANK:
        assert shelf.problems(q, [b for b in BANK if b["id"] != q["id"]], []) == [], q["id"]


def test_a_misquote_is_refused():
    assert "word for word" in _why(quote=GOOD["quote"].replace("good man", "great man"))


def test_a_wrong_citation_is_refused():
    assert "citation: WRONG" in _why(citation="Meditations 2.1, trans. George Long")


def test_a_citation_in_the_wrong_form_is_refused():
    assert "citation format" in _why(citation="Meditations 10.16")


def test_an_aired_quote_is_refused():
    rows = [{"quote": GOOD["quote"], "experiment": "story:x", "date": "2026-09-01"}]
    assert "already aired" in " | ".join(shelf.problems(GOOD, OTHERS, rows))


def test_a_quote_already_on_the_shelf_is_refused():
    assert "overlaps the shelved quote" in " | ".join(shelf.problems(
        dict(GOOD, id="a_new_id"), BANK, []))
    assert "id already taken" in " | ".join(shelf.problems(GOOD, BANK, []))


def test_hooks_are_short_and_never_shame():
    assert "hook is 10 words" in _why(hook="one two three four five six seven eight nine ten")
    assert "shames" in _why(hook="Stop being a pathetic loser.")
    assert "shames" in _why(hook="Nobody is coming to save you.")


def test_visual_rules_match_the_render_tests():
    v = list(GOOD["visuals"])
    assert "over 3 words" in _why(visuals=v[:-1] + ["a man walking alone at night"])
    assert "start it with 'man'" in _why(visuals=v[:-1] + ["boxer training"])
    assert "1-3 'still:'" in _why(visuals=[x for x in v if not x.startswith("still:")] + ["clock"])
    assert "6-10 shots" in _why(visuals=v[:3])


def test_theme_keys_and_author_are_checked():
    assert "theme must be one of" in _why(theme="vibes")
    q = {k: GOOD[k] for k in reversed(shelf.KEYS)}
    assert "keys must be exactly" in " | ".join(shelf.problems(q, OTHERS, []))
    assert "author must be one of" in _why(author="Cicero")


def test_check_rejects_a_duplicate_inside_one_batch():
    a = dict(GOOD)
    good, bad = shelf.check([a, dict(a)], bank=OTHERS, rows=[])
    assert [q["id"] for q in good] == [GOOD["id"]] and len(bad) == 1


def test_runway_counts_only_fresh_quotes(monkeypatch):
    monkeypatch.setattr(shelf, "posts_per_day", lambda: 2)
    monkeypatch.setattr(edits, "jammed_ids", lambda: set())
    rows = [{"experiment": f"edit:{BANK[0]['id']}", "quote": BANK[0]["quote"]}]
    st = shelf.status(today=dt.date(2026, 10, 23), rows=rows, bank=BANK[:21])
    assert st["left"] == 20 and st["days"] == 10 and st["runsOut"] == "2026-11-02"
    assert st["low"] is True and st["toTarget"] == 40
    st = shelf.status(today=dt.date(2026, 10, 23), rows=[], bank=BANK[:61])
    assert st["days"] == 30 and st["low"] is False and st["toTarget"] == 0


def test_add_keeps_the_bank_file_format(tmp_path, monkeypatch):
    bank_file = tmp_path / "edit_quotes.json"
    bank_file.write_text(json.dumps(OTHERS, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(edits, "BANK", bank_file)
    shelf.save(edits.load() + [GOOD])
    raw = bank_file.read_text(encoding="utf-8")
    assert raw == json.dumps(OTHERS + [GOOD], indent=1, ensure_ascii=False) + "\n"


def test_the_real_bank_file_is_in_the_format_save_writes():
    raw = edits.BANK.read_text(encoding="utf-8")
    assert raw == json.dumps(json.loads(raw), indent=1, ensure_ascii=False) + "\n"


def test_winners_rank_settled_edits_from_the_window():
    now = dt.datetime(2026, 10, 23, 22, 0, tzinfo=dt.timezone.utc)
    ids = [q["id"] for q in BANK[:3]]
    rows = [{"experiment": f"edit:{ids[0]}", "video_id": "a", "date": "2026-10-20"},
            {"experiment": f"edit:{ids[1]}", "video_id": "b", "date": "2026-10-21"},
            {"experiment": f"edit:{ids[2]}", "video_id": "c", "date": "2026-10-23"},   # too new
            {"experiment": "story:x", "video_id": "d", "date": "2026-10-20"}]          # not an edit
    stats = [{"video_id": "a", "published_at": "2026-10-20T01:00:00Z", "views": "10", "pulled_on": "2026-10-21"},
             {"video_id": "a", "published_at": "2026-10-20T01:00:00Z", "views": "300", "pulled_on": "2026-10-23"},
             {"video_id": "b", "published_at": "2026-10-21T01:00:00Z", "views": "500", "pulled_on": "2026-10-23"},
             {"video_id": "c", "published_at": "2026-10-23T01:00:00Z", "views": "900", "pulled_on": "2026-10-23"},
             {"video_id": "d", "published_at": "2026-10-20T01:00:00Z", "views": "999", "pulled_on": "2026-10-23"}]
    got = shelf.winners(rows, stats, now=now)
    assert [(w["id"], w["views"]) for w in got] == [(ids[1], 500), (ids[0], 300)]


def test_the_hq_warns_and_the_librarian_aims_at_the_same_numbers():
    assert shelf.WARN_DAYS < shelf.TARGET_DAYS
    page = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")
    assert "sh && sh.low" in page and "librarian:" in page
