"""Every published quote must appear WORD FOR WORD in the public-domain source.

    python scripts/validate_quotes.py            # audit story bank + edit bank

Standing rule: quotes are genuine public-domain text, never fabricated or
misattributed. Until 2026-10-01 that rule was enforced by memory. This checks
each quote against the downloaded translations (scripts/fetch_sources.py),
ignoring only case, punctuation and whitespace.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sources"
FILES = {"Marcus Aurelius": "marcus_long.txt", "Seneca": "seneca_gummere.txt",
         "Epictetus": "epictetus_long.txt"}


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    # Wikisource carries footnote markers inline ("Rusticus 6 I received");
    # standalone numbers are never part of a quote we publish.
    s = re.sub(r"(?<![a-z0-9])\d+(?![a-z0-9])", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_cache = {}


def corpus(author: str) -> str | None:
    for key, f in FILES.items():
        if key.lower() in author.lower():
            if f not in _cache:
                p = SRC / f
                _cache[f] = norm(p.read_text(encoding="utf-8")) if p.exists() else None
            return _cache[f]
    return None


def check(quote: str, author: str) -> str:
    """'ok' | 'MISSING' | 'unverifiable (<why>)'"""
    c = corpus(author)
    if c is None:
        return "unverifiable (no source text for this author)"
    if norm(quote) in c:
        return "ok"
    # Scan artefacts: drop caps ("B egin the morning") and "every thing" vs
    # "everything" split words differently. Comparing with spaces removed
    # tolerates spacing ONLY — every letter must still match in order.
    if norm(quote).replace(" ", "") in _nospace(c):
        return "ok"
    return "MISSING"


_ns = {}


def _nospace(c: str) -> str:
    k = id(c)
    if k not in _ns:
        _ns[k] = c.replace(" ", "")
    return _ns[k]


def main() -> int:
    bad = 0
    sets = [("stories", json.loads((ROOT / "data" / "stories.json").read_text()))]
    eb = ROOT / "data" / "edit_quotes.json"
    if eb.exists():
        sets.append(("edits", json.loads(eb.read_text())))
    for name, items in sets:
        for s in items:
            r = check(s["quote"], s["author"])
            if r == "MISSING":
                bad += 1
            if r != "ok" or "--all" in sys.argv:
                print(f"[{name}] {s['id']:26s} {r:10s} {s['author'][:22]:22s} {s['quote'][:70]}")
    print(f"{bad} quote(s) not found word for word in their source")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
