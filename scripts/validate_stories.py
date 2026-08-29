#!/usr/bin/env python3
"""
Validate data/stories.json before it can reach the channel.

The story bank is hand-edited JSON and it is the only part of this pipeline
whose words are published verbatim, unreviewed by any other stage. A typo in a
citation is a misattributed quote — the one failure this channel has said it
cannot survive. So the bank is checked on every run and in CI.

    python scripts/validate_stories.py          # exits 1 on any problem
    python scripts/validate_stories.py --list   # also print the running order
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import stories  # noqa: E402

REQUIRED = ("id", "hook", "story", "lesson", "quote", "author", "theme",
            "citation", "source", "tonight", "broll", "power", "s5")

# Doctrine §5 floor. Cato's suicide scores 10 on power and 2 here; a story that
# leaves a man on a bad night feeling smaller does not ship whatever its power.
MIN_S5 = 7

# Stories may use themes the GENERATED pipeline has retired. `friendship`,
# `desire` and `adversity as training` were cut from content.THEMES for weak
# view medians as aphorisms — but "a hand-written story about a friend" is a
# different proposition from "a generated quote about friendship", and the
# reason for the cut does not transfer.
EXTRA_THEMES = {"friendship", "desire", "adversity as training", "time"}

# HARD BAN. Owner, 2026-08-25: "dont use any stories about suicide they are
# restricted on youtube." Suicide and self-harm are advertiser-restricted
# regardless of framing, so this is a monetisation risk on top of the §5
# objection — a channel chasing YPP cannot spend videos on it. Not a judgement
# call, not re-proposable, and enforced here rather than in a doc.
# Stems, not exact phrases: "end his life" would miss "ending his life",
# which is precisely the wording that slipped past the first version.
BANNED = (
    "cato", "utica", "opened his veins", "slit his wrist",
    "suicid", "kill himself", "kill myself", "killing himself",
    "took his own life", "taking his own life", "take his own life",
    "end his life", "ending his life", "end my life",
    "ending my life", "self-harm", "self harm", "took his life",
)

MIN_WORDS, MAX_WORDS = 60, 140


def validate() -> list[str]:
    bank = stories.load()
    errs: list[str] = []
    if not bank:
        return ["data/stories.json is empty or unreadable"]

    try:
        import content
        valid_themes = set(content.THEMES) | EXTRA_THEMES
    except Exception:  # noqa: BLE001
        valid_themes = set()

    seen_ids: set[str] = set()
    seen_quotes: set[str] = set()
    for s in bank:
        sid = s.get("id", "<no id>")
        for k in REQUIRED:
            if k not in s or (isinstance(s[k], str) and not s[k].strip()):
                errs.append(f"{sid}: missing {k}")
        if sid in seen_ids:
            errs.append(f"{sid}: duplicate id")
        seen_ids.add(sid)

        q = (s.get("quote") or "").strip().lower()
        if q and q in seen_quotes:
            errs.append(f"{sid}: quote already used by another story")
        seen_quotes.add(q)

        if s.get("s5", 0) < MIN_S5:
            errs.append(f"{sid}: s5={s.get('s5')} below the §5 floor of {MIN_S5}")
        if not str(s.get("source", "")).startswith("http"):
            errs.append(f"{sid}: source is not a link")
        if valid_themes and s.get("theme") not in valid_themes:
            errs.append(f"{sid}: unknown theme {s.get('theme')!r}")

        n = len((s.get("story", "") + " " + s.get("lesson", "")).split())
        if not MIN_WORDS <= n <= MAX_WORDS:
            errs.append(f"{sid}: narration {n} words (want {MIN_WORDS}-{MAX_WORDS})")

        if len(s.get("broll") or []) < 3:
            errs.append(f"{sid}: needs at least 3 b-roll scenes")

        # Scan only what actually PUBLISHES. A caveat legitimately names the
        # thing to avoid — relaxed_by_amusement's says "Seneca's next example
        # is Cato relaxing with wine: CUT IT" — and flagging that would force
        # production notes to be vague about exactly the material they exist
        # to keep out.
        published = " ".join(str(s.get(k, "")) for k in
                             ("hook", "story", "lesson", "quote", "author",
                              "tonight", "caption")).lower()
        for b in BANNED:
            if b in published:
                errs.append(f"{sid}: banned material {b!r} in published text")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the running order")
    args = ap.parse_args()

    bank = stories.load()
    errs = validate()
    print(f"=== story bank: {len(bank)} scripts ===")
    if args.list:
        for i, s in enumerate(sorted(bank, key=lambda x: -x.get("score", 0)), 1):
            print(f"  {i:2d}. [{s.get('score', 0):3d}] {s['id']:<24} {s['hook'][:52]}")
    if errs:
        for e in errs:
            print(f"  FAIL {e}", file=sys.stderr)
        print(f"\n{len(errs)} problem(s) — not safe to publish", file=sys.stderr)
        return 1
    print(f"  all {len(bank)} valid — "
          f"{len(bank)} days of posts at 1/day")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
