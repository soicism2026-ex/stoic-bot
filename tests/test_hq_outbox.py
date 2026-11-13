"""The crew's outbox (scripts/hq_outbox.py): HQ reporting through git for the
small crew sessions, folded into hq/studio by hq_snapshot."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hq_outbox as ob  # noqa: E402
import hq_snapshot as hq  # noqa: E402


def test_lines_fold_into_log_ask_and_note_updates(tmp_path):
    p = tmp_path / "outbox.jsonl"
    ob.append({"t": "2026-11-13T08:42:00Z", "who": "Longinus", "kind": "done", "text": "Checked X: clean"}, p)
    ob.append({"t": "2026-11-13T10:55:00Z", "ask": "idea-follow-line", "outcome": "Started", "status": "answered", "answer": "go"}, p)
    ob.append({"t": "2026-11-13T11:00:00Z", "ask": "idea-follow-line", "closed": True}, p)
    ob.append({"t": "2026-11-13T11:05:00Z", "note": "n1", "status": "done", "reply": "Done."}, p)
    p.open("a", encoding="utf-8").write("not json\n")
    f = ob.fold(ob.recent(path=p, now=dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc)))
    assert f["crewLog"] == [{"t": "2026-11-13T08:42:00Z", "who": "Longinus", "kind": "done", "text": "Checked X: clean"}]
    assert f["askUpdates"]["idea-follow-line"] == {"outcome": "Started", "status": "answered", "answer": "go",
                                                   "closed": True, "t": "2026-11-13T11:00:00Z"}
    assert f["noteUpdates"]["n1"] == {"status": "done", "reply": "Done.", "t": "2026-11-13T11:05:00Z"}


def test_old_lines_drop_out_and_prune_keeps_two_weeks(tmp_path):
    p = tmp_path / "outbox.jsonl"
    ob.append({"t": "2026-10-01T00:00:00Z", "who": "Varro", "kind": "done", "text": "old"}, p)
    ob.append({"t": "2026-11-13T00:00:00Z", "who": "Varro", "kind": "done", "text": "new"}, p)
    now = dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc)
    assert [d["text"] for d in ob.recent(path=p, now=now)] == ["new"]
    assert ob.prune(path=p) == 1 and ob.read(p)[0]["text"] == "new"


def test_the_cli_writes_one_line_per_call(tmp_path, monkeypatch):
    p = tmp_path / "outbox.jsonl"
    monkeypatch.setattr(ob, "OUTBOX", p)
    assert ob.main(["log", "--who", "Cicero", "--kind", "done", "--text", "Judged test 2"]) == 0
    assert ob.main(["ask", "idea-x", "--outcome", "Started", "--closed"]) == 0
    assert ob.main(["note", "n9", "--status", "done", "--reply", "ok"]) == 0
    rows = ob.read(p)
    assert [r.get("who") or r.get("ask") or r.get("note") for r in rows] == ["Cicero", "idea-x", "n9"]
    assert rows[1]["closed"] is True and all(r["t"] for r in rows)


def test_the_snapshot_carries_the_outbox(monkeypatch, tmp_path):
    p = tmp_path / "outbox.jsonl"
    monkeypatch.setattr(ob, "OUTBOX", p)
    ob.append({"t": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "who": "Zeuxis", "kind": "done", "text": "fixed"}, p)
    got = hq.crew_outbox(dt.datetime.now(dt.timezone.utc))
    assert got["crewLog"][0]["who"] == "Zeuxis" and got["askUpdates"] == {} and got["noteUpdates"] == {}
    assert "crew_outbox(now)" in (ROOT / "scripts" / "hq_snapshot.py").read_text(encoding="utf-8")
