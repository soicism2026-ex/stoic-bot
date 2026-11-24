#!/usr/bin/env python3
"""Decide whether non-Short painting (wallpapers, long video, design lab) may spend
Cloudflare's free allowance now. Rule and reasons: src/spare_paint.py.

    python3 scripts/spare_paint.py check [--force] [--gh-output]

Exit 0 = allowed (or forced); 3 = refused (the reason is printed). With
--gh-output the answer is written to $GITHUB_OUTPUT (`go=true|false`) and the
exit code is always 0, so a workflow's guard job ends quietly in seconds.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import spare_paint as sp  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--force", action="store_true")
    c.add_argument("--gh-output", action="store_true")
    a = ap.parse_args(argv)
    ok, why = sp.check(force=a.force)
    print(f"spare paint: {'ALLOWED' if ok else 'REFUSED'}: {why}")
    if a.gh_output:
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"go={'true' if ok else 'false'}\n")
        return 0
    return 0 if ok else sp.EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
