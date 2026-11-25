#!/usr/bin/env python3
"""Decide whether non-Short painting (wallpapers, long video, design lab) may spend
Cloudflare's free allowance now. The rule and its reasons live in src/spare_paint.py.

    python3 scripts/spare_paint.py check [--force] [--gh-output]

Exit 0 = allowed (or forced); 3 = refused (the reason is printed). With
--gh-output the answer is written to $GITHUB_OUTPUT (`go=true|false`) and the
exit code is always 0, so a workflow's guard job ends quietly in seconds.

This file and src/spare_paint.py share a name and both directories are on sys.path
(scripts first), so `import spare_paint` can land here: this file loads the real
module by path and re-exports it, so either import gives the same functions.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src" / "spare_paint.py"
_spec = importlib.util.spec_from_file_location("spare_paint_rule", _SRC)
sp = importlib.util.module_from_spec(_spec)
sys.modules["spare_paint_rule"] = sp
_spec.loader.exec_module(sp)
for _n in dir(sp):
    if not _n.startswith("__"):
        globals().setdefault(_n, getattr(sp, _n))


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
