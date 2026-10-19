"""No quote airs unless it is found word for word in its public-domain source.

2026-10-01 audit against Long's Marcus Aurelius and Epictetus and Gummere's
Seneca (data/sources/, fetched by scripts/fetch_sources.py) found aired quotes
that were trimmed without marking, reworded, or — once — half invented
("Be content then in the rest of thy life" is not in Meditations 8.1). They all
came from memory. This test replaces memory.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import validate_quotes as v  # noqa: E402
import stories  # noqa: E402


def test_every_unaired_story_quote_is_verbatim_or_flagged():
    rows = list(csv.DictReader(open(ROOT / "data" / "posts.csv")))
    aired = stories._used_ids(rows)
    bad = []
    for s in stories.load():
        if s["id"] in aired or s.get("hold"):
            continue
        r = v.check(s["quote"], s["author"])
        if r == "MISSING" or (r.startswith("unverifiable") and not s.get("quote_unverified")):
            bad.append((s["id"], r, s["quote"]))
    assert bad == [], bad


def test_every_edit_quote_is_verbatim():
    p = ROOT / "data" / "edit_quotes.json"
    if not p.exists():
        return
    bad = [(q["id"], q["quote"]) for q in json.loads(p.read_text())
           if v.check(q["quote"], q["author"]) != "ok"]
    assert bad == [], bad


def test_the_checker_catches_a_real_misquote():
    assert v.check("Be content then in the rest of thy life, and let nothing else "
                   "distract thee.", "Marcus Aurelius") == "MISSING"
    assert v.check("Begin the morning by saying to thyself, I shall meet with the "
                   "busybody, the ungrateful, arrogant, deceitful, envious, unsocial.",
                   "Marcus Aurelius") == "ok", "drop-cap spacing must not cause a false alarm"


def test_sources_are_present():
    for f in ("marcus_long.txt", "seneca_gummere.txt", "epictetus_long.txt"):
        assert (ROOT / "data" / "sources" / f).stat().st_size > 200_000, f


def test_every_edit_citation_matches_where_the_source_has_it():
    """A verbatim quote can still carry the wrong reference: "lay aside the
    burdens of the mind" was cited as Letter 104; the source has it only in
    Letter 28. Every edit's book/section, letter or chapter is read from the
    source text itself."""
    bank = json.loads((ROOT / "data" / "edit_quotes.json").read_text())
    results = {q["id"]: v.check_citation(q["quote"], q["author"], q["citation"]) for q in bank}
    assert all(r == "ok" for r in results.values()), {k: r for k, r in results.items() if r != "ok"}


def test_citation_checker_catches_the_mistakes_it_was_built_for():
    burdens = ("You must lay aside the burdens of the mind; until you do this, "
               "no place will satisfy you.")
    assert v.check_citation(burdens, "Seneca", "Moral Letters 104") == "WRONG (source: 28)"
    assert v.check_citation(burdens, "Seneca", "Moral Letters 28") == "ok"
    # Six opening words matched a different passage (3.11) than the quote's own.
    q = "On every occasion a man should ask himself, Is this one of the unnecessary things?"
    assert v.source_location(q, "Marcus Aurelius") == "4.24"
    # A quote that opens its section, and a drop-capped section opening.
    assert v.source_location("Let not future things disturb thee", "Marcus Aurelius") == "7.8"
    assert v.source_location("In the morning when thou risest unwillingly", "Marcus Aurelius") == "5.1"
    assert v.source_location("How long will you then still defer thinking yourself worthy "
                             "of the best things", "Epictetus") == "Enchiridion 50"
