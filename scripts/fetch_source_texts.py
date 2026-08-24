#!/usr/bin/env python3
"""
Download the public-domain Stoic texts that long-form videos are read from.

WHY A REAL TEXT FILE: the channel's hard rule is that quotes must be genuine
public-domain Stoic text, never fabricated or misattributed. For 20-second
Shorts a block-list plus review is enough. For a 20-minute reading it is not —
a model asked to "recite Meditations Book 2" will produce fluent, plausible,
invented Marcus Aurelius. So the words are never generated. They are read from
a verified file, and this script is what puts that file there.

Sources are Project Gutenberg, which is public domain in the US. The runner
has open internet; the dev container may not, so this is designed to run in
CI and commit its output.

    python scripts/fetch_source_texts.py           # fetch anything missing
    python scripts/fetch_source_texts.py --force   # re-fetch everything
    python scripts/fetch_source_texts.py --check   # verify what is on disk

Every download is validated before it is written: expected length, expected
marker phrases, and a successful header/footer strip. A truncated or wrong
file is rejected rather than quietly becoming the script of a video.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "texts"

# Gutenberg ebook ids. `markers` are phrases that MUST appear in a correct
# download — they are how a wrong or truncated file is caught.
SOURCES = {
    "meditations": {
        "gutenberg_id": 2680,
        "title": "Meditations",
        "author": "Marcus Aurelius",
        "translator": "George Long",
        "min_chars": 200_000,
        "markers": ["MARCUS AURELIUS", "Begin the morning by saying"],
    },
    "seneca_letters": {
        "gutenberg_id": 56075,
        "title": "Moral Letters to Lucilius",
        "author": "Seneca",
        "translator": "Richard Mott Gummere",
        "min_chars": 300_000,
        "markers": ["LUCILIUS", "Seneca"],
    },
    "discourses": {
        "gutenberg_id": 45109,
        "title": "The Discourses",
        "author": "Epictetus",
        "translator": "George Long",
        "min_chars": 200_000,
        "markers": ["EPICTETUS"],
    },
}

# Gutenberg wraps every text in a licence header and footer. Reading those
# aloud would be absurd, so they are stripped — and a failure to find them is
# treated as a bad download, not something to shrug at.
_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
                    re.I | re.S)
_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
                  re.I | re.S)


def _urls(gid: int) -> list[str]:
    return [
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
        f"https://www.gutenberg.org/ebooks/{gid}.txt.utf-8",
    ]


def strip_boilerplate(raw: str) -> str:
    """Remove the Gutenberg licence header/footer. Raises if absent."""
    m = _START.search(raw)
    if not m:
        raise ValueError("no Gutenberg START marker — not a Gutenberg text file")
    body = raw[m.end():]
    m2 = _END.search(body)
    if m2:
        body = body[:m2.start()]
    return body.strip()


def validate(name: str, text: str, spec: dict) -> None:
    """Reject anything that is not clearly the expected book."""
    if len(text) < spec["min_chars"]:
        raise ValueError(
            f"{name}: {len(text):,} chars, expected at least "
            f"{spec['min_chars']:,} — truncated or wrong book")
    missing = [m for m in spec["markers"] if m.lower() not in text.lower()]
    if missing:
        raise ValueError(f"{name}: missing expected phrase(s) {missing} — "
                         f"this is not the book it claims to be")


def fetch(name: str, spec: dict) -> str:
    last = None
    for url in _urls(spec["gutenberg_id"]):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code != 200:
                last = f"HTTP {r.status_code}"
                continue
            r.encoding = r.encoding or "utf-8"
            body = strip_boilerplate(r.text)
            validate(name, body, spec)
            print(f"  [{name}] {len(body):,} chars from {url}")
            return body
        except Exception as e:  # noqa: BLE001
            last = str(e)
            print(f"  [{name}] {url} -> {e}", file=sys.stderr)
    raise RuntimeError(f"{name}: every source failed (last: {last})")


def path_for(name: str) -> Path:
    return OUT_DIR / f"{name}.txt"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-fetch even if present")
    ap.add_argument("--check", action="store_true", help="validate on-disk files only")
    ap.add_argument("--only", help="just this source key")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keys = [args.only] if args.only else list(SOURCES)
    failed = 0

    for name in keys:
        spec = SOURCES[name]
        p = path_for(name)
        if args.check:
            if not p.exists():
                print(f"  [{name}] MISSING")
                failed += 1
                continue
            try:
                validate(name, p.read_text(encoding="utf-8"), spec)
                print(f"  [{name}] ok — {p.stat().st_size:,} bytes")
            except ValueError as e:
                print(f"  [{name}] INVALID: {e}", file=sys.stderr)
                failed += 1
            continue

        if p.exists() and not args.force:
            print(f"  [{name}] already present, skipping")
            continue
        try:
            p.write_text(fetch(name, spec), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"  [{name}] FAILED: {e}", file=sys.stderr)
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
