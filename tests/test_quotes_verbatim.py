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
