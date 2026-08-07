#!/usr/bin/env python3
"""
Watchdog for sameness. Reads data/posts.csv and reports where the channel has
started repeating itself.

WHY THIS EXISTS: every repetition bug so far was invisible to the test suite,
because the code was fine and the DATA was wrong. Unit tests asserted that
rule numbers rotate; they did rotate, over a `used` set that was always empty
because posts.csv had a stale header. Nothing failed. "Rule 7" shipped
thirteen times, one identical music bed shipped thirty times, and the same
Seneca hook shipped verbatim three times — all with a green suite.

So this checks the output, not the code. It runs after every post and prints
loudly. Exit 1 on any WARN, but the workflow step is continue-on-error: the
point is to surface drift on the run page, never to block a post.

    python scripts/variety_check.py            # last 30 posts
    python scripts/variety_check.py --window 60
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.csv"

# A single value covering more than this fraction of the window means the
# rotation for that dimension has effectively stopped.
DOMINANCE = 0.60
# How many hooks may share an opening word before it reads as a formula.
MAX_SHARED_OPENER = 2

WARN = "\033[33mWARN\033[0m"
OK = "\033[32m ok \033[0m"


def _load() -> list[dict]:
    if not POSTS.exists():
        print(f"posts.csv not found at {POSTS}", file=sys.stderr)
        return []
    with open(POSTS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _hook(row: dict) -> str:
    return (row.get("hook") or "").strip()


def check_verbatim_hooks(rows: list[dict], issues: list[str]) -> None:
    """The same hook, word for word, more than once — ever."""
    counts = Counter(_hook(r) for r in rows if _hook(r))
    repeats = {h: n for h, n in counts.items() if n > 1}
    if repeats:
        for h, n in sorted(repeats.items(), key=lambda kv: -kv[1])[:5]:
            issues.append(f"hook published {n}x verbatim: \"{h[:60]}\"")
    else:
        print(f"  [{OK}] no hook has ever been published twice verbatim")


def check_rule_numbers(rows: list[dict], issues: list[str]) -> None:
    """Rule numbers are code-assigned precisely because models fixate on 7/9."""
    ns = [int(m.group(1)) for r in rows
          if (m := re.match(r"\s*Rule\s+(\d+)", _hook(r)))]
    if not ns:
        print(f"  [{OK}] no rule posts yet")
        return
    counts = Counter(ns)
    dupes = {n: c for n, c in counts.items() if c > 1}
    if dupes:
        worst = max(dupes.items(), key=lambda kv: kv[1])
        issues.append(
            f"rule number {worst[0]} used {worst[1]}x (all numbers so far: "
            f"{sorted(counts)}) — code assignment is not reaching the output")
    else:
        print(f"  [{OK}] {len(ns)} rule posts, all distinct numbers")


def check_dominance(rows: list[dict], column: str, label: str,
                    issues: list[str]) -> None:
    """One value swamping a column means that rotation has stopped."""
    vals = [(r.get(column) or "").strip() for r in rows]
    vals = [v for v in vals if v]
    if not vals:
        print(f"  [{OK}] {label}: no data")
        return
    top, n = Counter(vals).most_common(1)[0]
    share = n / len(vals)
    if share > DOMINANCE and len(set(vals)) > 0:
        issues.append(f"{label}: '{top}' on {n}/{len(vals)} recent posts "
                      f"({share:.0%}) — rotation is not varying")
    else:
        print(f"  [{OK}] {label}: {len(set(vals))} distinct, "
              f"top '{top}' at {share:.0%}")


def check_hook_openers(rows: list[dict], issues: list[str]) -> None:
    """Three hooks opening on the same proper noun is a formula, not a style."""
    openers = [h.split()[0].strip(".,:;\"'").lower()
               for r in rows if (h := _hook(r)) and h.split()]
    if not openers:
        return
    for word, n in Counter(openers).most_common(3):
        if n > MAX_SHARED_OPENER:
            issues.append(f"{n} recent hooks open with the same word "
                          f"'{word}' — the model has found a formula")


def check_duplicate_quotes(rows: list[dict], issues: list[str]) -> None:
    counts = Counter((r.get("quote") or "").strip() for r in rows
                     if (r.get("quote") or "").strip())
    dupes = {q: n for q, n in counts.items() if n > 1}
    if dupes:
        q, n = max(dupes.items(), key=lambda kv: kv[1])
        issues.append(f"quote used {n}x: \"{q[:60]}\" — the block list is not "
                      f"reaching the model")
    else:
        print(f"  [{OK}] no quote reused")


def check_header(issues: list[str]) -> None:
    """The bug behind all of the above: a stale header hides whole columns."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import logbook
    except Exception:  # noqa: BLE001
        return
    if not POSTS.exists():
        return
    with open(POSTS, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if header != logbook.FIELDS:
        issues.append(
            f"posts.csv header {header} != logbook.FIELDS — every rotation "
            f"reading the missing columns is BLIND. This is the root cause of "
            f"every repetition bug so far.")
    else:
        print(f"  [{OK}] posts.csv header matches logbook.FIELDS "
              f"({len(header)} columns)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", type=int, default=30,
                    help="how many recent posts to judge rotation on")
    args = ap.parse_args()

    rows = _load()
    if not rows:
        return 0
    recent = rows[-args.window:]
    issues: list[str] = []

    print(f"=== Variety check ({len(rows)} posts, judging last {len(recent)}) ===")
    check_header(issues)
    check_verbatim_hooks(rows, issues)          # all history
    check_rule_numbers(rows, issues)            # all history
    check_duplicate_quotes(rows, issues)        # all history
    for col, label in (("format", "format"), ("theme", "theme"),
                       ("author", "author"), ("music_track", "music"),
                       ("voice_name", "voice")):
        check_dominance(recent, col, label, issues)
    check_hook_openers(recent, issues)

    print("=" * 58)
    if issues:
        for i in issues:
            print(f"  [{WARN}] {i}")
        print(f"\n{len(issues)} variety problem(s). The channel is repeating "
              f"itself — viewers notice this before any metric does.")
        return 1
    print("No repetition detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
