"""The design lab (owner 2026-11-10: "Deploy agents to design higher quality
videos"): one quote rendered in each look, DRY_RUN, for the owner to compare.
Nothing in it may touch a live post."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import design_lab as lab  # noqa: E402

IDS = ["receive_without_arrogance", "pile_of_troubles", "fly_from_the_stronger"]
FFMPEG = shutil.which("ffmpeg") is not None


def test_the_matrix_is_every_look_for_every_quote():
    m = lab.matrix("current, painted", "pile_of_troubles,fly_from_the_stronger", ids=IDS)
    assert m["include"] == [
        {"look": "current", "edit": "pile_of_troubles"}, {"look": "painted", "edit": "pile_of_troubles"},
        {"look": "current", "edit": "fly_from_the_stronger"}, {"look": "painted", "edit": "fly_from_the_stronger"}]
    assert lab.matrix("painted,painted", "pile_of_troubles,pile_of_troubles", ids=IDS)["include"] == [
        {"look": "painted", "edit": "pile_of_troubles"}]           # duplicates once


def test_a_typo_fails_before_anything_renders():
    with pytest.raises(SystemExit, match="unknown look"):
        lab.matrix("current,paintd", "pile_of_troubles", ids=IDS)
    with pytest.raises(SystemExit, match="no quote with id"):
        lab.matrix("current", "pile_of_troubels", ids=IDS)
    with pytest.raises(SystemExit, match="at most"):
        lab.matrix(",".join(lab.LOOKS), ",".join(IDS), ids=IDS)   # 4 looks x 3 quotes = 12


def test_no_quote_named_means_the_next_to_air(monkeypatch):
    monkeypatch.setattr(lab, "next_edit", lambda: "fly_from_the_stronger")
    assert lab.matrix("", "", ids=IDS)["include"] == [
        {"look": "current", "edit": "fly_from_the_stronger"}, {"look": "painted", "edit": "fly_from_the_stronger"}]


def test_every_real_quote_id_is_a_safe_asset_name():
    for q in json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8")):
        assert lab.asset_name(q["id"], "painted", "mp4") == f"{q['id']}__painted.mp4"
    with pytest.raises(ValueError):
        lab.asset_name("../x", "painted", "mp4")


def test_the_current_look_is_the_live_channel():
    assert lab.LOOKS["current"] == {}
    assert lab.env_lines("current") == ["REEL_LAB_LOOK=current"]
    assert "REEL_EDIT_LOOK=painted" in lab.env_lines("painted")
    assert set(lab.LABELS) == set(lab.LOOKS)
    with pytest.raises(SystemExit):
        lab.env_lines("nope")


def test_a_render_of_the_wrong_quote_is_refused(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps({"video": "x.mp4", "edit": "pile_of_troubles"}))
    assert lab.describe(tmp_path, "pile_of_troubles", "painted")["look"] == "painted"
    with pytest.raises(SystemExit, match="asked for"):
        lab.describe(tmp_path, "fly_from_the_stronger", "painted")


def test_the_lab_can_only_render_dry_and_only_by_hand():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "design-lab.yml").read_text(encoding="utf-8"))
    on = wf.get("on") or wf.get(True)
    assert set(on) == {"workflow_dispatch"}                       # never on a schedule
    steps = wf["jobs"]["render"]["steps"]
    render = next(s for s in steps if s.get("name", "").startswith("Render"))
    assert render["env"]["DRY_RUN"] == "1" and render["env"]["REEL_EDIT_ID"] == "${{ matrix.edit }}"
    assert render["env"]["REEL_REHEARSAL"] == "1"                 # approved sounds only, as live
    assert "YOUTUBE" not in json.dumps([s.get("run", "") for s in steps])


def test_the_producer_honours_a_chosen_quote_only_in_a_dry_run():
    src = (ROOT / "scripts" / "daily_post.py").read_text(encoding="utf-8")
    assert 'forced = os.environ.get("REEL_EDIT_ID", "").strip()' in src
    assert 'if forced and DRY_RUN and os.environ.get("REEL_FORMAT", "edit") == "edit":' in src
    for wf in ("daily-short.yml", "repost.yml"):
        p = ROOT / ".github" / "workflows" / wf
        if p.exists():
            assert "REEL_EDIT_ID" not in p.read_text(encoding="utf-8"), wf


def _tiny(path: Path, colour: str, seconds: float = 1.2) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=1080x1920:d={seconds}:r=30",
                    "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_the_sheet_and_the_sampler_render(tmp_path):
    a, b = _tiny(tmp_path / "a.mp4", "red"), _tiny(tmp_path / "b.mp4", "blue")
    png = lab.sheet(a, tmp_path / "a.png")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(png)],
                           capture_output=True, text=True).stdout.strip()
    assert probe == f"{420 * len(lab.SHEET_AT)},960"               # four iPhone-cropped moments
    out = lab.sampler(tmp_path / "s.mp4", [(a, "Today's look"), (b, "The new look")])
    assert lab.duration(out) == pytest.approx(2 * 1.4 + 2 * 1.2, abs=0.3)
