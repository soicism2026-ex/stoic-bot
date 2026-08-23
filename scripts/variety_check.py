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

LIVE vs HEALED: repeat detection scans ALL history, because a quote reused
after two months is still a block-list failure. But it only WARNS when the
most recent occurrence falls inside the window. Otherwise every bug ever
fixed warns forever — this check was exiting 1 with eight warnings, all of
them damage from June and July that had already been repaired, which is
exactly how a real ninth warning goes unnoticed. Healed repeats print as a
quiet line instead.

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
# Repeats that happened, were fixed, and have not recurred. Printed for the
# record; they never fail the check.
HEALED = "\033[90mpast\033[0m"


def _load() -> list[dict]:
    if not POSTS.exists():
        print(f"posts.csv not found at {POSTS}", file=sys.stderr)
        return []
    with open(POSTS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _hook(row: dict) -> str:
    return (row.get("hook") or "").strip()


# The "Rule N:" prefix is assigned by code (content._rule_directive), not
# chosen by the model, so it must not be read as the model finding a formula.
_RULE_PREFIX = re.compile(r"^\s*rule\s+\d+\s*[:.\-—]?\s*", re.I)


def _positions(rows: list[dict], key) -> dict:
    """Map each non-empty key value to the list of row indices holding it."""
    out: dict = {}
    for i, r in enumerate(rows):
        k = key(r)
        if k:
            out.setdefault(k, []).append(i)
    return out


def _split_live(groups: dict, first_recent: int) -> tuple[list, list]:
    """Split repeated values into (live, healed).

    A repeat is LIVE if its most recent occurrence is inside the window —
    the pipeline is still doing it. If every occurrence predates the window
    the defect was fixed and reporting it again teaches everyone to ignore
    this check.
    """
    live, healed = [], []
    for val, idxs in groups.items():
        if len(idxs) < 2:
            continue
        (live if max(idxs) >= first_recent else healed).append((val, idxs))
    live.sort(key=lambda kv: -len(kv[1]))
    healed.sort(key=lambda kv: -len(kv[1]))
    return live, healed


def check_verbatim_hooks(rows: list[dict], first_recent: int,
                         issues: list[str], healed: list[str]) -> None:
    """The same hook, word for word, more than once."""
    live, old = _split_live(_positions(rows, _hook), first_recent)
    for h, idxs in live[:5]:
        issues.append(f"hook published {len(idxs)}x verbatim, most recently "
                      f"{rows[idxs[-1]]['date']}: \"{h[:60]}\"")
    if old:
        healed.append(f"{len(old)} hook(s) were repeated verbatim before this "
                      f"window (latest {rows[max(i for _, ix in old for i in ix)]['date']})")
    if not live:
        print(f"  [{OK}] no hook repeated verbatim in this window")


def _rule_number(row: dict) -> str:
    m = re.match(r"\s*Rule\s+(\d+)", _hook(row))
    return m.group(1) if m else ""


def check_rule_numbers(rows: list[dict], first_recent: int,
                       issues: list[str], healed: list[str]) -> None:
    """Rule numbers are code-assigned precisely because models fixate on 7/9."""
    groups = _positions(rows, _rule_number)
    if not groups:
        print(f"  [{OK}] no numbered rule posts yet")
        return
    live, old = _split_live(groups, first_recent)
    for n, idxs in live[:3]:
        issues.append(f"rule number {n} used {len(idxs)}x, most recently "
                      f"{rows[idxs[-1]]['date']} — code assignment is not "
                      f"reaching the output")
    if old:
        worst = max(old, key=lambda kv: len(kv[1]))
        healed.append(f"rule number {worst[0]} was used {len(worst[1])}x up to "
                      f"{rows[worst[1][-1]]['date']}, none since")
    if not live:
        total = sum(len(v) for v in groups.values())
        print(f"  [{OK}] {total} numbered rule posts, no number reused "
              f"in this window")


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
    """Three hooks opening on the same word is a formula, not a style.

    The "Rule N:" prefix is stripped first. That word is written by
    content._rule_directive, not chosen by the model, so counting it flagged
    the rule format's own signature as model fixation — a warning no change
    to the prompt could ever clear. What matters is the word AFTER it.
    """
    openers = []
    for r in rows:
        h = _RULE_PREFIX.sub("", _hook(r))
        if h.split():
            openers.append(h.split()[0].strip(".,:;\"'").lower())
    if not openers:
        return
    for word, n in Counter(openers).most_common(3):
        if n > MAX_SHARED_OPENER:
            issues.append(f"{n} recent hooks open with the same word "
                          f"'{word}' — the model has found a formula")


def check_duplicate_quotes(rows: list[dict], first_recent: int,
                           issues: list[str], healed: list[str]) -> None:
    """A quote reused at ANY distance is a block-list failure, so this scans
    all history — but only warns if the reuse itself is recent."""
    live, old = _split_live(
        _positions(rows, lambda r: (r.get("quote") or "").strip()), first_recent)
    for q, idxs in live[:3]:
        issues.append(f"quote used {len(idxs)}x, most recently "
                      f"{rows[idxs[-1]]['date']}: \"{q[:60]}\" — the block "
                      f"list is not reaching the model")
    if old:
        worst = max(old, key=lambda kv: len(kv[1]))
        healed.append(f"{len(old)} quote(s) were reused before this window "
                      f"(worst {len(worst[1])}x, last {rows[worst[1][-1]]['date']})")
    if not live:
        print(f"  [{OK}] no quote reused in this window")


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
    first_recent = max(0, len(rows) - args.window)
    issues: list[str] = []
    healed: list[str] = []

    print(f"=== Variety check ({len(rows)} posts, judging last {len(recent)}) ===")
    check_header(issues)
    # Scan all history, warn only on repeats that recur inside the window.
    check_verbatim_hooks(rows, first_recent, issues, healed)
    check_rule_numbers(rows, first_recent, issues, healed)
    check_duplicate_quotes(rows, first_recent, issues, healed)
    for col, label in (("format", "format"), ("theme", "theme"),
                       ("author", "author"), ("music_track", "music"),
                       ("voice_name", "voice")):
        check_dominance(recent, col, label, issues)
    check_hook_openers(recent, issues)

    print("=" * 58)
    for h in healed:
        print(f"  [{HEALED}] {h}")
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
