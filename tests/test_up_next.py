"""Apelles' rehearsal of the next Short: rendered before it airs, carried to the HQ."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import up_next  # noqa: E402

WF = ROOT / ".github" / "workflows" / "edit-preview.yml"


def _preview(tmp_path):
    (tmp_path / "edit_be_such.mp4").write_bytes(b"x" * 20_000)
    (tmp_path / "meta.json").write_text(json.dumps({
        "video": "edit_be_such.mp4", "edit": "be_such", "quote": "q", "hook": "h",
        "author": "Marcus Aurelius", "citation": "c", "airDay": "2026-10-24", "voice": "Brian"}))
    return tmp_path


def test_publish_replaces_both_files_in_the_release(tmp_path, monkeypatch):
    calls = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    def gh(*args, check=True):
        calls.append(args)
        return R(1 if args[:2] == ("release", "view") else 0)

    monkeypatch.setattr(up_next, "_gh", gh)
    monkeypatch.setattr(up_next, "phone_cut", lambda s, d: d.write_bytes(s.read_bytes()[:15_000]) or d)
    monkeypatch.setenv("RUN_URL", "https://github.com/x/actions/runs/1")
    meta = up_next.publish(_preview(tmp_path))
    assert meta["edit"] == "be_such" and meta["run"].endswith("/runs/1") and meta["bytes"] == 15_000
    assert calls[1][:2] == ("release", "create") and "--prerelease" in calls[1]
    up = calls[2]
    assert up[:3] == ("release", "upload", "up-next") and "--clobber" in up
    assert {Path(a).name for a in up if a.startswith("/")} == {"up-next.mp4", "up-next.json"}
    written = json.loads((tmp_path / "up-next" / "up-next.json").read_text())
    assert written["renderedAt"].endswith("Z") and written["airDay"] == "2026-10-24"


def test_fetch_reports_failure_without_raising(tmp_path, monkeypatch):
    def boom(url, dst):
        raise OSError("404")
    monkeypatch.setattr(up_next, "_download", boom)
    got = up_next.fetch(tmp_path)
    assert got["ok"] is False and "404" in got["error"]


def test_fetch_returns_the_metadata_and_the_local_file(tmp_path, monkeypatch):
    def fake(url, dst):
        if url.endswith(".json"):
            dst.write_text(json.dumps({"edit": "be_such", "renderedAt": "2026-10-23T19:52:00Z"}))
        else:
            dst.write_bytes(b"v" * 50_000)
    monkeypatch.setattr(up_next, "_download", fake)
    got = up_next.fetch(tmp_path)
    assert got["ok"] and got["edit"] == "be_such" and Path(got["file"]).stat().st_size == 50_000
    assert up_next.PUBLIC == "https://github.com/soicism2026-ex/stoic-bot/releases/download/up-next/"


def test_need_rehearses_each_edit_once_and_stops_on_repeated_failure():
    cur = {"edit": "be_such", "airDay": "2026-10-26", "renderedAt": "x"}
    assert up_next.need("be_such", "2026-10-26", cur, 0)[0] is False       # already done
    assert up_next.need("next_one", "2026-10-26", cur, 0)[0] is True        # a post went out
    assert up_next.need("be_such", "2026-10-27", cur, 0)[0] is True         # same edit, new air day
    assert up_next.need("next_one", "2026-10-26", None, 0)[0] is True       # no release yet
    assert up_next.need("next_one", "2026-10-26", cur, 2)[0] is False       # broken: don't burn reads
    assert up_next.need(None, "2026-10-26", None, 0)[0] is False            # empty shelf


def test_apelles_rehearses_after_every_post_with_the_crons_as_backstop():
    """GitHub fired the two crons 2-5 hours late (10-24's 19:40 ran at 21:50);
    a Producer run that posted is the moment the next Short becomes known."""
    wf = yaml.safe_load(WF.read_text())
    on = wf[True]
    assert on["workflow_run"] == {"workflows": ["daily-short"], "types": ["completed"]}
    jobs = wf["jobs"]
    assert "scripts/up_next.py need" in jobs["check"]["steps"][1]["run"]
    assert jobs["preview"]["needs"] == "check" and jobs["preview"]["if"] == "needs.check.outputs.go == '1'"
    assert "github.event_name == 'workflow_run'" in jobs["preview"]["env"]["UP_NEXT"]
    assert wf["permissions"]["actions"] == "read"
    assert {c["cron"] for c in on["schedule"]} == {"40 8 * * *", "40 19 * * *"}
    steps = {s.get("name"): s for s in wf["jobs"]["preview"]["steps"]}
    assert "src/airday.py --next" in steps["The day the next post airs"]["run"]
    assert "REEL_TODAY=" in steps["The day the next post airs"]["run"]
    hq = steps["Put it in the HQ as the next Short"]
    assert hq["if"] == "env.UP_NEXT == '1'" and "scripts/up_next.py publish" in hq["run"]
    # A scheduled run has no inputs: it must still use Brian and the sounds.
    env = wf["jobs"]["preview"]["env"]
    assert env["VOICE"] == "${{ inputs.voice || 'brian' }}"
    assert "github.event_name == 'schedule'" in env["UP_NEXT"] and "inputs.music == ''" in env["UP_NEXT"]
    render = steps["Render the next edit (DRY_RUN: no upload, no log)"]["env"]
    assert render["REEL_EDIT_SFX"] == "${{ (inputs.sfx || 'on') == 'on' && '1' || '0' }}"
    assert render["DRY_RUN"] == "1"
    assert steps["Confirm Brian actually spoke"]["if"] == "env.VOICE == 'brian'"
    assert wf["permissions"]["contents"] == "write"


def test_a_rehearsal_records_what_it_rendered():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    i = src.index("if upload_this and DRY_RUN:")
    j = src.index("upload_result = publish_short(")
    block = src[i:j]
    assert '(out / "meta.json")' in block and '"airDay": today' in block and '"edit":' in block
    assert "return" in block                       # still returns before any upload


def test_the_hq_shows_the_rehearsal_only_for_the_quote_that_airs_next():
    page = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")
    assert 'doc("hq/upnext", "upnext")' in page
    assert "u.edit === q.id" in page              # a stale rehearsal is never shown as next
    assert "if (sig === onAirSig) return;" in page   # redraws don't stop a playing video
