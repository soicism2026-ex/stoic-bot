"""The crew's outbox: HQ reporting through git.

The crew's shifts run in small standing sessions (2026-11-13, the token diet)
that can push to the repository but have no HQ database tools. They report
here instead: one JSON object per line in data/hq_outbox.jsonl, committed with
their work. scripts/hq_snapshot.py folds the recent lines into hq/studio
(crewLog, askUpdates, noteUpdates) on every HQ sync, and the HQ page merges
them into its log, its idea cards and its messages. Nothing else writes the
HQ from those sessions.

    python3 scripts/hq_outbox.py log --who Longinus --kind done --text "Checked X: clean"
    python3 scripts/hq_outbox.py ask idea-follow-line --outcome "Started 11-21" [--closed] [--status answered --answer go]
    python3 scripts/hq_outbox.py ask idea-new --create-json '{"kind":"idea","title":...,"pitch":...,"why":...,"crew":"marketer","options":[{"id":"go","label":"Go"},{"id":"no","label":"Not now"},{"id":"stop","label":"Stop"}],"order":12,"cost":"Free","impact":"medium"}'
    python3 scripts/hq_outbox.py note <id> --status done --reply "..."
    python3 scripts/hq_outbox.py prune            # keep the last 14 days (Varro, weekly)
    python3 scripts/hq_outbox.py show             # what the next sync will carry
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTBOX = ROOT / "data" / "hq_outbox.jsonl"
KEEP_DAYS = 14
LOG_KINDS = ("work", "done", "post", "decision", "alert", "you")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(path: Path | None = None) -> list[dict]:
    path = path or OUTBOX
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("t"):
                out.append(d)
    except OSError:
        pass
    return out


def append(item: dict, path: Path | None = None) -> dict:
    path = path or OUTBOX
    item = {"t": item.get("t") or now_iso(), **{k: v for k, v in item.items() if k != "t"}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def recent(days: int = KEEP_DAYS, path: Path | None = None, now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    cut = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [d for d in read(path) if str(d.get("t", "")) >= cut]


def fold(items: list[dict]) -> dict:
    """What hq_snapshot puts in hq/studio: log lines newest first, and the last
    update per ask and per note (later lines win)."""
    log = [d for d in items if d.get("kind") in LOG_KINDS and d.get("text")]
    log = sorted(log, key=lambda d: d["t"], reverse=True)[:80]
    asks: dict[str, dict] = {}
    notes: dict[str, dict] = {}
    for d in sorted(items, key=lambda d: d["t"]):
        if d.get("ask"):
            asks.setdefault(d["ask"], {}).update({k: v for k, v in d.items() if k not in ("ask", "t")})
            asks[d["ask"]]["t"] = d["t"]
        elif d.get("note"):
            notes.setdefault(d["note"], {}).update({k: v for k, v in d.items() if k not in ("note", "t")})
            notes[d["note"]]["t"] = d["t"]
    return {"crewLog": [{"t": d["t"], "who": d.get("who", "crew"), "kind": d["kind"], "text": d["text"]} for d in log],
            "askUpdates": asks, "noteUpdates": notes}


def prune(days: int = KEEP_DAYS, path: Path | None = None) -> int:
    path = path or OUTBOX
    keep = recent(days, path)
    path.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in keep), encoding="utf-8")
    return len(keep)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("log"); a.add_argument("--who", required=True); a.add_argument("--kind", default="done", choices=LOG_KINDS)
    a.add_argument("--text", required=True)
    b = sub.add_parser("ask"); b.add_argument("id"); b.add_argument("--outcome"); b.add_argument("--closed", action="store_true")
    b.add_argument("--status"); b.add_argument("--answer")
    b.add_argument("--create-json", help="a NEW card's fields as JSON (title, pitch, why, kind idea, crew, options, order, cost, impact)")
    c = sub.add_parser("note"); c.add_argument("id"); c.add_argument("--status", choices=("working", "done")); c.add_argument("--reply")
    sub.add_parser("prune"); sub.add_parser("show")
    ns = ap.parse_args(argv)
    if ns.cmd == "log":
        print(json.dumps(append({"who": ns.who, "kind": ns.kind, "text": ns.text}), ensure_ascii=False))
    elif ns.cmd == "ask":
        item = {"ask": ns.id}
        for k in ("outcome", "status", "answer"):
            if getattr(ns, k):
                item[k] = getattr(ns, k)
        if ns.closed:
            item["closed"] = True
        if ns.create_json:
            item["create"] = json.loads(ns.create_json)
        print(json.dumps(append(item), ensure_ascii=False))
    elif ns.cmd == "note":
        item = {"note": ns.id}
        for k in ("status", "reply"):
            if getattr(ns, k):
                item[k] = getattr(ns, k)
        print(json.dumps(append(item), ensure_ascii=False))
    elif ns.cmd == "prune":
        print(f"kept {prune()} lines")
    else:
        print(json.dumps(fold(recent()), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
