"""Download the public-domain Stoic translations this channel quotes from.

    python scripts/fetch_sources.py

Saves plain text to data/sources/. Every quote the bot publishes is checked
against these files word for word (scripts/validate_quotes.py), so "never
fabricate or misattribute" is enforced by a test rather than by memory.

Sources (all public domain, via Wikisource):
  marcus_long.txt     George Long, The Thoughts of the Emperor Marcus Aurelius
  seneca_gummere.txt  Richard M. Gummere, Moral Letters to Lucilius
  epictetus_long.txt  George Long, The Discourses of Epictetus; with the
                      Encheiridion and Fragments
"""
import html
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources"
API = "https://en.wikisource.org/w/index.php"

ROOTS = {
    "marcus_long.txt": "The_Thoughts_of_the_Emperor_Marcus_Aurelius_Antoninus",
    "seneca_gummere.txt": "Moral_letters_to_Lucilius",
    "epictetus_long.txt": "The_Discourses_of_Epictetus;_with_the_Encheiridion_and_Fragments",
}
SKIP = re.compile(r"(Index|Biographical|Philosophy_of|Preface|Prologue)", re.I)


def render(title: str) -> str:
    r = requests.get(API, params={"title": title, "action": "render"}, timeout=60,
                     headers={"User-Agent": "stoic-bot quote verifier"})
    r.raise_for_status()
    return r.text


def text_of(page_html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page_html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def subpages(root: str, page_html: str) -> list:
    links = re.findall(r'href="https://en\.wikisource\.org/wiki/([^"#]+)"', page_html)
    seen, out = set(), []
    for l in links:
        t = urllib.parse.unquote(l)
        if t.startswith(root + "/") and t not in seen and not SKIP.search(t):
            seen.add(t)
            out.append(t)
    return out


def fetch_tree(root: str) -> str:
    top = render(root)
    pages = subpages(root, top)
    # one level deeper (Epictetus: Book N -> Chapter M)
    parts = []
    for p in pages:
        h = render(p)
        deeper = subpages(p, h)
        if deeper:
            for d in deeper:
                parts.append(text_of(render(d)))
                time.sleep(0.2)
        else:
            parts.append(text_of(h))
        time.sleep(0.2)
    return "\n".join(parts)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, root in ROOTS.items():
        if "--only" in sys.argv and name not in sys.argv:
            continue
        txt = fetch_tree(root)
        (OUT / name).write_text(txt, encoding="utf-8")
        print(f"{name}: {len(txt):,} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
