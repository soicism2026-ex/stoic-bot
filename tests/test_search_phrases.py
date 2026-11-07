"""What our audience searches for (owner 2026-11-07: "a list of 10 things
people might potentially search for. we will use it make our shorts easier
to find"). data/search_phrases.json holds the ten, each quote answers one by
its theme or id, and nothing changes a Short until the owner says yes
(Cicero's ledger, test "search-phrases")."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edits  # noqa: E402
import shelf  # noqa: E402

DATA = json.loads((ROOT / "data" / "search_phrases.json").read_text(encoding="utf-8"))
Q = {"id": "x", "theme": "fear", "quote": "Q.", "author": "Epictetus", "citation": "Enchiridion 5, trans. George Long",
     "hook": "Stop fearing.", "visuals": [], "description": "One.\n\nTwo.\n\nThree.", "question": "Why?"}


def _ledger(tmp_path, monkeypatch, **test):
    p = tmp_path / "marketing_tests.json"
    p.write_text(json.dumps({"tests": [{"id": "search-phrases", **test}]}))
    monkeypatch.setattr(edits, "MARKETING_TESTS", p)


def test_the_ten_searches_are_well_formed():
    ids = [p["id"] for p in DATA["phrases"]]
    assert len(ids) == len(set(ids)) == 10
    for p in DATA["phrases"]:
        assert p["phrase"] == p["phrase"].lower().strip() and p["evidence"], p["id"]
        assert re.fullmatch(r"#[a-z]+", p["hashtag"]), p["id"]
    assert set(DATA["byTheme"]) == shelf.THEMES                     # every theme answers a search
    assert set(DATA["byTheme"].values()) | set(DATA["overrides"].values()) <= set(ids)


def test_every_quote_still_to_air_answers_a_search():
    for q in edits.load():
        assert edits.search_phrase(q), q["id"]


def test_nothing_changes_until_the_owner_says_yes(tmp_path, monkeypatch):
    ledger = json.loads((ROOT / "data" / "marketing_tests.json").read_text())
    t = next(t for t in ledger["tests"] if t["id"] == "search-phrases")
    assert t["kind"] == "traffic_source" and t["source"] == "YT_SEARCH" and t["ask"] == "search-phrases"
    _ledger(tmp_path, monkeypatch, status="proposed")
    c = edits.as_content(Q)
    assert c["_search"] is None and c["hashtags"][1] == "#motivation"
    assert edits.description(c).startswith("One.")


def test_once_on_the_description_opens_with_the_search(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, status="running", started="2026-11-08")
    assert edits.search_use() == "descriptions"
    c = edits.as_content(Q)
    assert c["_search"]["id"] == "overthinking" and c["_searchUse"] == "descriptions"
    assert c["hashtags"][:2] == ["#stoicism", "#overthinking"]
    d = edits.description(c)
    assert d.split("\n\n")[0] == "How to stop overthinking: Epictetus's answer."
    assert d.split("\n\n")[1] == "One."                                   # then the owner's paragraphs
    _ledger(tmp_path, monkeypatch, status="running", started="2026-11-08", use="titles")
    assert edits.as_content(Q)["_searchUse"] == "titles"
    _ledger(tmp_path, monkeypatch, status="done", adopted="descriptions")
    assert edits.search_use() == "descriptions"


def test_a_quote_can_answer_a_search_its_theme_does_not(tmp_path, monkeypatch):
    p = tmp_path / "search_phrases.json"
    p.write_text(json.dumps({**DATA, "overrides": {"x": "calm"}}))
    monkeypatch.setattr(edits, "SEARCH_PHRASES", p)
    assert edits.search_phrase(Q)["phrase"] == "how to stay calm under pressure"
    assert edits.search_phrase({**Q, "id": "y"})["id"] == "overthinking"


def test_the_producer_puts_the_search_in_tags_and_titles_only_when_on():
    src = (ROOT / "scripts" / "daily_post.py").read_text(encoding="utf-8")
    assert 'if content.get("_searchUse") == "titles":' in src
    assert 'seo_tags = [content["_search"]["phrase"], f\'{content["author"].lower()} quotes\'] + seo_tags' in src


def test_the_research_is_kept_for_the_next_session():
    doc = (ROOT / "data" / "search_research.md").read_text(encoding="utf-8")
    for p in DATA["phrases"]:
        assert p["phrase"] in doc, p["id"]
    assert "Not one view came from a problem search" in doc
