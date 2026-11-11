"""Longinus in the pipeline (src/inspector.py + painter.painted_still): every
painted shot is looked at by a free vision model before it airs, and a shot
with a clear defect is repainted (owner 2026-11-11: "the generated images
sometimes look off continuously improve the shorts")."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import inspector  # noqa: E402
import painter  # noqa: E402

FFMPEG = shutil.which("ffmpeg") is not None


def _still(path: Path, colour: str = "orange") -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=256x448",
                    "-frames:v", "1", str(path)], check=True)
    return path


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


def _keys(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok456")
    monkeypatch.delenv("REEL_INSPECT", raising=False)


def test_reading_the_reply():
    assert inspector.parse('{"ok": true, "defects": []}') == (True, [])
    assert inspector.parse('Sure! {"ok": false, "defects": ["six fingers on the left hand"]}') == (
        False, ["six fingers on the left hand"])
    assert inspector.parse('{"ok": true, "defects": ["a face in the rock"]}') == (False, ["a face in the rock"])
    assert inspector.parse('{"ok": false, "defects": []}') == (True, [])     # nothing named: nothing to fix
    assert inspector.parse("I cannot see the image.") == (None, [])
    assert inspector.parse('{"ok": "maybe"}') == (None, [])


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_a_look_sends_the_still_and_the_scene_and_is_remembered(tmp_path, monkeypatch):
    _keys(monkeypatch)
    still = _still(tmp_path / "a.png")
    sent = []

    def post(url, headers=None, json=None, timeout=None):
        sent.append((url, headers, json))
        return _Resp({"success": True, "result": {"response": '{"ok": false, "defects": ["a face in the boulder"]}',
                                                   "usage": {"prompt_tokens": 1800, "completion_tokens": 20}}})
    monkeypatch.setattr(inspector.requests, "post", post)
    v = inspector.judge(still, "Rain over a grey boulder in an olive grove")
    assert v.ok is False and v.problems == ["a face in the boulder"] and not v.cached
    assert v.neurons == pytest.approx(1800 * inspector.NEURONS_IN + 20 * inspector.NEURONS_OUT)
    url, headers, body = sent[0]
    assert url.endswith("/accounts/acct123/ai/run/" + inspector.MODEL)
    assert headers == {"Authorization": "Bearer tok456"}
    content = body["messages"][0]["content"]
    assert "grey boulder" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    again = inspector.judge(still, "anything")              # judged once, from the file next to the still
    assert again.ok is False and again.cached and len(sent) == 1
    assert json.loads((tmp_path / "a.png.inspect.json").read_text())["version"] == inspector.VERSION


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_anything_that_stops_it_looking_passes_the_still(tmp_path, monkeypatch):
    still = _still(tmp_path / "b.png")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    assert inspector.judge(still).ok is None                                 # no key
    _keys(monkeypatch)
    monkeypatch.setenv("REEL_INSPECT", "0")
    assert inspector.judge(still).ok is None                                 # switched off
    monkeypatch.delenv("REEL_INSPECT")
    for reply in (_Resp({"success": False, "errors": [{"code": 5006}]}, 400),
                  _Resp(ValueError("not json"), 502),
                  _Resp({"success": True, "result": {"response": "no idea"}})):
        monkeypatch.setattr(inspector.requests, "post", lambda *a, _r=reply, **k: _r)
        assert inspector.judge(still).ok is None
    def boom(*a, **k):
        raise inspector.requests.ConnectionError("down tok456 acct123")
    monkeypatch.setattr(inspector.requests, "post", boom)
    v = inspector.judge(still)
    assert v.ok is None and "tok456" not in v.note and "acct123" not in v.note
    assert not (tmp_path / "b.png.inspect.json").exists()                    # failures aren't remembered


def _fake_paint(monkeypatch, tmp_path, verdicts):
    """generate_still returns one file per seed; judge answers from `verdicts`
    (seed -> (ok, problems))."""
    import imagegen
    painted = []

    def gen(prompt, seed=None):
        painted.append(seed)
        p = tmp_path / f"s{seed}.png"
        p.write_bytes(b"x")
        return {"path": str(p), "model": "@cf/black-forest-labs/flux-2-klein-4b", "cached": False, "neurons": 208}

    def judge(path, scene=""):
        seed = int(Path(path).stem[1:])
        ok, problems = verdicts.get(seed, (True, []))
        return inspector.Verdict(ok, problems, 60.0)
    monkeypatch.setattr(imagegen, "generate_still", gen)
    monkeypatch.setattr(inspector, "judge", judge)
    monkeypatch.setattr(imagegen, "_ledger_add", lambda cache, n: None)
    painter._CHOSEN.clear()
    return painted


def test_a_shot_that_passes_airs_as_painted(tmp_path, monkeypatch):
    painted = _fake_paint(monkeypatch, tmp_path, {})
    got = painter.painted_still("a man at dawn", 410170, "a man at dawn")
    assert painted == [410170] and got["tries"] == 1 and got["inspect"]["ok"] is True


def test_a_flagged_shot_is_repainted_and_the_passing_one_airs(tmp_path, monkeypatch):
    s1 = painter._alt_seed(410170, 1)
    painted = _fake_paint(monkeypatch, tmp_path, {410170: (False, ["a face in the rock"])})
    got = painter.painted_still("rain over a boulder", 410170, "rain over a boulder")
    assert painted == [410170, s1] and got["seed_used"] == s1 and got["tries"] == 2
    assert got["inspect"]["ok"] is True
    # asked again in the same run (fetch_slot after prefetch): the same choice, no new paintings
    assert painter.painted_still("rain over a boulder", 410170) is got and len(painted) == 2


def test_when_every_repaint_fails_the_least_broken_airs(tmp_path, monkeypatch):
    s1, s2 = painter._alt_seed(7, 1), painter._alt_seed(7, 2)
    _fake_paint(monkeypatch, tmp_path, {7: (False, ["six fingers", "text on the wall"]),
                                        s1: (False, ["six fingers"]),
                                        s2: (False, ["six fingers", "a lantern", "two of him"])})
    got = painter.painted_still("a hand", 7, "a hand")
    assert got["seed_used"] == s1 and got["tries"] == 2 and got["inspect"]["problems"] == ["six fingers"]


def test_repaints_follow_the_budget_and_the_setting(tmp_path, monkeypatch):
    import imagegen
    painted = _fake_paint(monkeypatch, tmp_path, {5: (False, ["a face in the cloud"])})
    real = imagegen.generate_still
    monkeypatch.setattr(imagegen, "generate_still", lambda p, s=None: real(p, s) if s == 5 else None)
    got = painter.painted_still("clouds", 5, "clouds")        # no paint left for a repaint: the first stays
    assert got["seed_used"] == 5 and got["inspect"]["ok"] is False
    painter._CHOSEN.clear()
    monkeypatch.setattr(imagegen, "generate_still", real)
    monkeypatch.setenv("REEL_INSPECT_RETRIES", "0")
    painted.clear()
    painter.painted_still("clouds", 5, "clouds")
    assert painted == [5]


def test_alternate_seeds_are_stable_and_distinct():
    seeds = [painter._alt_seed(410170, n) for n in range(1, 4)]
    assert seeds == [painter._alt_seed(410170, n) for n in range(1, 4)]       # the live run repeats the rehearsal
    assert len(set(seeds + [410170])) == 4


def test_a_live_post_logs_what_the_inspector_saw(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import csv
    import daily_post
    log = tmp_path / "inspector.csv"
    monkeypatch.setattr(daily_post, "INSPECTOR_LOG", log)
    monkeypatch.setattr(painter, "SLOTS", {
        0: {"ok": True, "tries": 1, "seed": 410170, "scene": "{man} at a feast", "inspect": {"ok": True, "problems": []}},
        1: {"ok": True, "tries": 2, "seed": 9, "scene": "rain over a boulder",
            "inspect": {"ok": False, "problems": ["a face in the rock"]}},
        2: {"ok": False, "scene": "a street at night"}})
    daily_post._log_inspection("2026-11-12", {"format": "edit", "_edit_id": "fly"}, {"video_id": "abc"})
    rows = list(csv.DictReader(open(log, encoding="utf-8")))
    assert [r["verdict"] for r in rows] == ["pass", "flagged", "stock"]
    assert rows[1]["problems"] == "a face in the rock" and rows[1]["tries"] == "2" and rows[0]["video_id"] == "abc"
    daily_post._log_inspection("2026-11-12", {"format": "story"}, {})          # other formats: nothing
    assert len(list(csv.DictReader(open(log, encoding="utf-8")))) == 3
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text(encoding="utf-8")
    assert "git add data/inspector.csv" in wf
    assert "data/inspector.csv merge=union" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
