"""The spare-painting rule (src/spare_paint.py): non-Short painting only on what is left of the day."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import spare_paint as sp  # noqa: E402   (src/ or the scripts/ shim: the same functions)

UTC = dt.timezone.utc


def at(h, m=0, d=24):
    return dt.datetime(2026, 11, d, h, m, tzinfo=UTC)


def rehearsal(air="2026-11-25", painted=(True,) * 7):
    return {"airDay": air, "shots": [{"slot": i, "painted": p} for i, p in enumerate(painted)]}


@pytest.fixture(autouse=True)
def painted_look(monkeypatch):
    monkeypatch.setenv("REEL_EDIT_LOOK", "painted")


@pytest.mark.parametrize("h", [0, 2, 3, 7, 12, 19])
def test_hours_outside_20_to_23_are_refused(h):
    ok, why = sp.spare_ok(at(h), rehearsal())
    assert not ok and "UTC" in why


@pytest.mark.parametrize("h", [20, 21, 23])
def test_evening_with_tomorrows_painted_rehearsal_is_allowed(h):
    ok, why = sp.spare_ok(at(h, 59 if h == 23 else 0), rehearsal())
    assert ok and "spare" in why


def test_rehearsal_for_today_is_refused():
    ok, why = sp.spare_ok(at(21), rehearsal(air="2026-11-24"))
    assert not ok and "not rehearsed yet" in why


def test_an_old_air_day_is_refused():
    assert not sp.spare_ok(at(21), rehearsal(air="2026-11-23"))[0]


def test_one_unpainted_shot_is_refused():
    ok, why = sp.spare_ok(at(22), rehearsal(painted=(True, True, False, True)))
    assert not ok and "1 of 4" in why


def test_unreadable_rehearsal_refuses():
    assert not sp.spare_ok(at(21), None)[0]
    assert not sp.spare_ok(at(21), {"shots": []})[0]
    assert not sp.spare_ok(at(21), {"airDay": "soon"})[0]


def test_look_not_painted_or_no_shots_needs_no_painting(monkeypatch):
    monkeypatch.setenv("REEL_EDIT_LOOK", "")
    assert sp.spare_ok(at(21), rehearsal(painted=(False, False)))[0]
    monkeypatch.setenv("REEL_EDIT_LOOK", "painted")
    assert sp.spare_ok(at(21), {"airDay": "2026-11-25", "shots": []})[0]


def test_today_argument_overrides_the_clock_date():
    assert sp.spare_ok(at(21), rehearsal(air="2026-11-25"), today=dt.date(2026, 11, 25))[0] is False


def test_fetch_failure_refuses_and_is_not_attempted_outside_the_window():
    calls = []
    ok, why = sp.check(at(21), fetch=lambda: calls.append(1))
    assert not ok and calls == [1]
    calls.clear()
    assert not sp.check(at(3), fetch=lambda: calls.append(1))[0] and not calls


def test_force_always_allows():
    ok, why = sp.check(at(3), force=True, fetch=lambda: None)
    assert ok and "forced" in why


def test_fetch_up_next_reads_json_and_survives_errors(monkeypatch):
    import io
    import urllib.request

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R(json.dumps(rehearsal()).encode()))
    assert sp.fetch_up_next()["airDay"] == "2026-11-25"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R(b"<html>"))
    assert sp.fetch_up_next() is None

    def boom(*a, **k): raise OSError("down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert sp.fetch_up_next() is None


def test_cli_exit_codes_and_github_output(monkeypatch, tmp_path, capsys):
    # scripts/spare_paint.py shares its name with src/spare_paint.py: load it by path
    import importlib.util
    spec = importlib.util.spec_from_file_location("spare_paint_cli", ROOT / "scripts" / "spare_paint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.spare_ok.__code__.co_filename == sp.spare_ok.__code__.co_filename        # one rule, two doors
    assert mod.main(["check", "--force"]) == 0
    out = tmp_path / "gh"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(mod.sp, "check", lambda force=False: (False, "no"))
    assert mod.main(["check", "--gh-output"]) == 0 and "go=false" in out.read_text()
    assert mod.main(["check"]) == 3
    assert "REFUSED" in capsys.readouterr().out


def test_workflows_guard_first_and_declare_the_painted_look():
    import yaml
    for name, job in (("wallpapers", "guard"), ("long-form", "guard"), ("design-lab", "plan")):
        wf = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text()
        d = yaml.safe_load(wf)
        assert "spare_paint.py check" in wf and 'REEL_EDIT_LOOK: "painted"' in wf
        steps = d["jobs"][job]["steps"]
        assert steps[0]["uses"].startswith("actions/checkout") and "spare_paint" in json.dumps(steps[1])
    for name in ("wallpapers", "long-form"):
        d = yaml.safe_load((ROOT / ".github" / "workflows" / f"{name}.yml").read_text())
        trig = d.get(True) or d.get("on")
        assert trig["workflow_run"]["workflows"] == ["edit-preview"]
    assert "force" in yaml.safe_load((ROOT / ".github/workflows/design-lab.yml").read_text())[True]["workflow_dispatch"]["inputs"]
