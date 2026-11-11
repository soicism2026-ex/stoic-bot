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
# checked against a bank that does not contain it. It aired before quotes
# carried a description and question (2026-11-06), so it borrows a real pair.
BANK = edits.load()
SAMPLE = next(q for q in BANK if q.get("description"))
GOOD = {k: copy.deepcopy(BANK[0].get(k, SAMPLE.get(k))) for k in shelf.KEYS}
OTHERS = [q for q in BANK if q["id"] != GOOD["id"]]


def _why(**change):
    q = copy.deepcopy(GOOD)
    q.update(change)
    return " | ".join(shelf.problems(q, OTHERS, []))


def test_every_shelved_quote_passes_the_rules_it_would_be_held_to_today():
    for q in BANK:
        if "description" not in q:          # aired before 2026-11-06 (tests/test_descriptions.py)
            q = {k: q.get(k, SAMPLE.get(k)) for k in shelf.KEYS}
        assert shelf.problems(q, [b for b in BANK if b["id"] != q["id"]], []) == [], q["id"]


def test_a_new_quote_needs_the_owners_description_and_question():
    """2026-11-06: the owner sent a viral Short's description to model ours on."""
    assert _why() == ""
    two = "One short line that speaks to the viewer about his own life today and what to do.\n\n" * 2
    assert "description: 2-3 short paragraphs" in _why(description="")
    assert "2-3 paragraphs" in _why(description="One paragraph only. " * 8)
    assert "2-3 paragraphs" in _why(description=(two * 2).strip())               # four paragraphs
    assert "2-3 paragraphs" in _why(description="Line one.\nLine two " * 8 + "\n\nThree.")
    assert "description is 160 words" in _why(description=("word " * 80).strip() + "\n\n" + ("word " * 80).strip())
    assert "no links" in _why(description=two.strip() + " #stoic")
    assert "no links" in _why(description=two.strip() + " https://x.y")
    assert "question: one question" in _why(question="")
    assert "ending in '?'" in _why(question="What do you think.")
    assert "ending in '?'" in _why(question="Why " + "really " * 30 + "?")
    assert "ending in '?'" in _why(question="Why?")
    assert "shames" in _why(question="Are you a coward or a man?")
    assert "shames" in _why(description=two.strip() + " Stop being a pathetic loser.")


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


# --- scene fields (docs/scene_writing.md): scenes, emphasis, hook_emphasis ------

SCENED = [q for q in BANK if "scenes" in q]


def _scene(**change):
    q = {"quote": "Nothing need provoke one’s anger if one does not add to one’s pile of troubles by getting angry.",
         "hook": "Angry about it? Now it's two problems.",
         "scenes": _six("{man} staring at a shattered clay jar on a courtyard floor, fists clenched, hard noon sun"),
         "emphasis": ["pile of troubles"], "hook_emphasis": "two problems"}
    q.update(change)
    return " | ".join(shelf.scene_problems(q))


def _six(first):
    return [first] + ["{man} walking on a hill road at dawn, shot %d" % i for i in range(5)]


def test_scene_fields_are_optional_and_old_quotes_pass():
    assert shelf.scene_problems({"quote": "x", "hook": "y"}) == []
    assert _why() == ""                       # GOOD has no scene fields


def test_the_twelve_scened_quotes_exist_and_every_scened_quote_passes():
    assert len(SCENED) >= 12
    for q in SCENED:
        assert shelf.scene_problems(q) == [], q["id"]
        assert list(q.keys())[-3:] == shelf.SCENE_KEYS, q["id"]
        assert 6 <= len(q["scenes"]) <= 8


def test_a_good_scene_set_passes_and_all_three_fields_travel_together():
    assert _scene() == ""
    only = {"quote": "x y z", "hook": "a b", "scenes": ["a"] * 6}
    assert "emphasis: a quote with scene fields needs all three" in " | ".join(shelf.scene_problems(only))


def test_scene_count_length_and_duplicates():
    assert "scenes: 6-8 shots, got 5" in _scene(scenes=_six("{man} walking at dawn on a hill road alone")[:5])
    assert "two shots are identical" in _scene(scenes=["{man} walking at dawn on a hill road alone, wide"] * 6)
    assert "words; one paintable shot" in _scene(scenes=_six("{man} at dawn"))


def test_cast_tokens_are_known_and_at_most_two_per_shot():
    assert "unknown cast token ['caesar']" in _scene(scenes=_six("{caesar} walking in a torchlit hall alone"))
    assert "more than two people" in _scene(scenes=_six("{man} {marcus} {seneca} talking by an oil lamp at night"))
    assert _scene(scenes=_six("{marcus} and {man} talking by an oil lamp at night")) == ""


def test_style_negation_text_anachronism_and_light_rules():
    assert "style word 'cinematic'" in _scene(scenes=_six("{man} walking in a cinematic dawn on a hill road"))
    assert "style word '4k'" in _scene(scenes=_six("{man} walking in dawn light, 4k, on a hill road"))
    assert "negation 'without'" in _scene(scenes=_six("{man} walking on a hill road at dawn without a cloak"))
    assert "negation 'not'" in _scene(scenes=_six("{man} walking on a hill road at dawn, not smiling"))
    assert "asks for writing" in _scene(scenes=_six("{man} reading a sign on a hill road at dawn"))
    assert "asks for writing" in _scene(scenes=_six("{man} holding a tablet with words on it in dawn light"))
    assert "'lantern' did not exist" in _scene(scenes=_six("{man} carrying a lantern along a hill road at night"))
    assert "'book' did not exist" in _scene(scenes=_six("{man} holding a book in oil lamp glow at his desk"))
    assert "name a physical light source" in _scene(scenes=_six("{man} walking along a hill road, a calm look on his face"))
    assert "never a statue" in _scene(scenes=_six("a marble statue of a philosopher in dawn light, close up"))


def test_emphasis_must_be_verbatim_in_the_quote_and_hook():
    assert "emphasis 'pile of woes' is not word for word" in _scene(emphasis=["pile of woes"])
    assert "emphasis: 1-3 phrases, got 0" in _scene(emphasis=[])
    assert "emphasis: 1-3 phrases, got 4" in _scene(emphasis=["anger", "pile", "troubles", "getting"])
    assert _scene(emphasis=["PILE OF TROUBLES"]) == ""                  # case-insensitive
    assert "hook_emphasis 'three problems' is not word for word" in _scene(hook_emphasis="three problems")
    assert "phrase is listed twice" in _scene(emphasis=["anger", "Anger"])


def test_problems_accepts_scene_keys_after_the_base_keys_only():
    q = copy.deepcopy(GOOD)
    q.update({"scenes": _six("{man} walking on a hill road at dawn, first"),
              "emphasis": [GOOD["quote"].split()[0]], "hook_emphasis": GOOD["hook"].split()[0]})
    assert shelf.problems(q, OTHERS, []) == []
    bad = {"scenes": q["scenes"], **{k: v for k, v in q.items() if k != "scenes"}}
    assert "keys must be exactly" in " | ".join(shelf.problems(bad, OTHERS, []))
