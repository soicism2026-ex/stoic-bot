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


# ---------------------------------------------------------------------------
# CITATIONS. A verbatim quote can still carry the wrong reference: the bank
# had "lay aside the burdens of the mind" as Letter 104; the source has it
# only in Letter 28. These locate a quote in the raw text and read the book /
# section (Marcus) or letter (Seneca) it actually sits in.
# ---------------------------------------------------------------------------
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
          "IX": 9, "X": 10, "XI": 11, "XII": 12}
_raw = {}


def _flat(f: str) -> str:
    if f not in _raw:
        _raw[f] = re.sub(r"\s+", " ", (SRC / f).read_text(encoding="utf-8")).replace("\u200b", "")
    return _raw[f]


def _locate(text: str, quote: str) -> int:
    """Where the quote's opening words sit in the raw text, tolerating
    punctuation, footnote markers ("[ 3 ]") and drop caps ("I N the morning")."""
    # 12 words, not 6: "On every occasion a man should..." opens passages in
    # both 3.11 and 4.24, and six words located the wrong one.
    words = re.findall(r"[A-Za-z']+", quote)[:12]
    if not words:
        return -1
    sep = r"[^A-Za-z']+(?:\[\s*\d+\s*\][^A-Za-z']*)?"
    pat = sep.join([r"\s?".join(map(re.escape, words[0]))] + [re.escape(w) for w in words[1:]])
    m = re.search(pat, text, re.I)
    return m.start() if m else -1


def source_location(quote: str, author: str) -> str | None:
    """'book.section' of the Meditations, or the Seneca letter number."""
    if "Marcus" in author:
        t = _flat("marcus_long.txt")
        i = _locate(t, quote)
        books = [(m.start(), _ROMAN[m.group(1)]) for m in
                 re.finditer(r"Marcus Aurelius Antoninus — Book ([IVX]+)", t) if m.start() < i]
        if i < 0 or not books:
            return None
        start, b = books[-1]
        # +4: a quote that OPENS its section is preceded directly by "N. ".
        secs = re.findall(r"(?<![\d.])(\d{1,2})\. (?=[A-Z\[])", t[start:i + 4])
        return f"{b}.{secs[-1] if secs else 1}"
    if "Seneca" in author:
        t = _flat("seneca_gummere.txt")
        i = _locate(t, quote)
        letters = [m.group(1) for m in
                   re.finditer(r"Moral letters to Lucilius — Letter (\d+)\.", t[:max(i, 0)])]
        return letters[-1] if i >= 0 and letters else None
    if "Epictetus" in author:
        t = _flat("epictetus_long.txt")
        i = _locate(t, quote)
        if i < 0:
            return None
        ench = t.find("THE ENCHEIRIDION, OR MANUAL")
        frag = t.find("FRAGMENTS", ench) if ench >= 0 else -1
        if ench >= 0 and i > ench and (frag < 0 or i < frag):
            # A heading may carry a footnote marker ("XXIX. [ 20 ] In every
            # act..."): without the "[" a quote in 29 read as 28, in 42 as 41.
            secs = re.findall(r"(?<![A-Za-z])([IVXLC]{1,7})\. (?=[A-Z\[])", t[ench:i + 4])
            return f"Enchiridion {_roman(secs[-1])}" if secs else None
        # Every chapter's page carries its own running title ("... Fragments
        # — Book 1, Chapter 5"). The "CHAPTER V." headings are not reliable:
        # Book I's chapter 5 has none in the source, so its quotes read as I.4.
        pages = [(int(m.group(1)), int(m.group(2))) for m in
                 re.finditer(r"Fragments — Book (\d), Chapter (\d+)", t[:i + 4])]
        if pages:
            book, chap = pages[-1]
            return f"Discourses {('I', 'II', 'III', 'IV')[book - 1]}.{chap}"
        books = re.findall(r"BOOK ([IVX]+)", t[:i])
        chaps = [(m.start(), m.group(1)) for m in re.finditer(r"CHAPTER ([IVXLC]+)", t[:i + 12])]
        if not books or not chaps:
            return None
        return f"Discourses {books[-1]}.{_roman(chaps[-1][1])}"
    return None


def _roman(r: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    n = 0
    for a, b in zip(r, r[1:] + " "):
        n += -vals[a] if b != " " and vals[b] > vals[a] else vals[a]
    return n


def check_citation(quote: str, author: str, citation: str) -> str:
    """'ok' | 'WRONG (source: X)' | 'unchecked' (an author or work not covered)."""
    m = (re.search(r"Meditations (\d+\.\d+)", citation) if "Marcus" in author else
         re.search(r"Letters? (\d+)", citation) if "Seneca" in author else
         re.search(r"((?:Enchiridion|Discourses) [IVX]*\.?\d+)", citation) if "Epictetus" in author
         else None)
    if not m:
        return "unchecked"
    got = source_location(quote, author)
    if got is None:
        return "unchecked"
    return "ok" if got == m.group(1) else f"WRONG (source: {got})"


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
    wrong = 0
    if eb.exists():
        for q in json.loads(eb.read_text()):
            r = check_citation(q["quote"], q["author"], q.get("citation", ""))
            if r.startswith("WRONG"):
                wrong += 1
                print(f"[citation] {q['id']:26s} cited {q['citation']!r}: {r}")
    print(f"{wrong} edit citation(s) disagree with the source")
    return 1 if bad or wrong else 0


if __name__ == "__main__":
    sys.exit(main())
