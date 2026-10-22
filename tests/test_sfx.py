"""ElevenLabs sound effects for the edits: approval gate, timing, generator."""
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import sfx  # noqa: E402


def _bank(monkeypatch, approved=False):
    bank = [
        {"id": "impact_a", "role": "impact", "file": "assets/sfx/impact_a.mp3", "approved": approved},
        {"id": "impact_b", "role": "impact", "file": "assets/sfx/impact_b.mp3", "approved": approved},
        {"id": "whoosh_a", "role": "whoosh", "file": "assets/sfx/whoosh_a.mp3", "approved": approved},
    ]
    monkeypatch.setattr(sfx, "load", lambda: bank)
    monkeypatch.setattr(sfx, "_exists", lambda t: True)
    return bank


def test_nothing_airs_until_the_owner_approves(monkeypatch):
    _bank(monkeypatch, approved=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert sfx.cues(4.0, "2026-10-22") == []
    monkeypatch.setenv("DRY_RUN", "1")                 # a preview may audition them
    assert len(sfx.cues(4.0, "2026-10-22")) == 2


def test_impact_on_the_first_frame_whoosh_into_the_quote(monkeypatch):
    _bank(monkeypatch, approved=True)
    monkeypatch.delenv("DRY_RUN", raising=False)
    got = sfx.cues(3.2, "2026-10-22")
    assert [t for _, t in got] == [0.0, round(3.2 - sfx.WHOOSH_LEAD, 2)]
    assert got[0][0].name.startswith("impact") and got[1][0].name.startswith("whoosh")
    # a quote that arrives almost at once gets no whoosh
    assert [t for _, t in sfx.cues(0.5, "2026-10-22")] == [0.0]


def test_the_same_day_picks_the_same_sounds(monkeypatch):
    _bank(monkeypatch, approved=True)
    a = sfx.pick("impact", "2026-10-22")["id"]
    assert all(sfx.pick("impact", "2026-10-22")["id"] == a for _ in range(5))


def test_a_preview_can_audition_one_sound(monkeypatch):
    _bank(monkeypatch, approved=False)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("REEL_SFX_IMPACT", "impact_b")
    assert sfx.pick("impact", "any")["id"] == "impact_b"


def test_bank_file_is_valid():
    data = json.loads((ROOT / "data" / "sfx.json").read_text())
    assert isinstance(data, list)
    for t in data:
        assert t["role"] in sfx.ROLES and isinstance(t.get("approved"), bool)
        assert t["provenance"]["model"] and t["provenance"]["prompt"]
        assert (ROOT / t["file"]).exists(), t["file"]


def test_generator_specs_are_valid():
    import make_sfx as m
    ids = [s["id"] for s in m.SPECS]
    assert len(ids) == len(set(ids))
    for s in m.SPECS:
        assert s["role"] in sfx.ROLES
        assert 0.5 <= s["duration"] <= 30 and 0 <= s["influence"] <= 1
        assert "no music" in s["text"].lower()
    assert {s["role"] for s in m.SPECS} == set(sfx.ROLES)


def test_sound_effects_are_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("REEL_SFX", raising=False)
    import render
    importlib.reload(render)
    assert render.SFX_ON is False
    monkeypatch.setenv("REEL_SFX", "1")
    importlib.reload(render)
    assert render.SFX_ON is True
    monkeypatch.delenv("REEL_SFX", raising=False)
    importlib.reload(render)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_sfx_track_places_each_sound_and_lasts_the_video(tmp_path):
    import render
    tones = []
    for i, f in enumerate((220, 880)):
        p = tmp_path / f"t{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency={f}:duration=0.4", str(p)], check=True)
        tones.append(p)
    out = render._make_sfx_track([(tones[0], 0.0), (tones[1], 1.5)], 3.0, tmp_path / "sfx.wav")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
    assert abs(dur - 3.0) < 0.05

    def level(start):
        r = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(start), "-t", "0.3", "-i", str(out),
                            "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        return float(r.stderr.split("mean_volume:")[1].split("dB")[0])
    assert level(1.55) > -40          # the second sound sits at 1.5 s
    assert level(0.8) < -60           # silence between the two
    assert render._make_sfx_track([], 3.0, tmp_path / "none.wav") is None


def test_every_edit_gets_the_owners_sounds():
    """Owner, 2026-10-22 (HQ): "Use all four, rotating". Edits only: the
    classic format already opens on its own hook sound."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert 'REEL_EDIT_SFX: "1"' in wf
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    edit_pack = src[src.index('"edit": {'):src.index('"truestory": {')]
    assert '"REEL_SFX": os.environ.get("REEL_EDIT_SFX", "0")' in edit_pack
    bank = json.loads((ROOT / "data" / "sfx.json").read_text())
    assert len(bank) == 4 and all(t["approved"] is True for t in bank)
    assert {t["role"] for t in bank} == set(sfx.ROLES)


def test_the_poster_cannot_hang_on_its_install_step():
    """2026-10-22: apt hung for the whole 60-minute job and a post was lost."""
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "daily-short.yml").read_text())
    step = next(s for s in wf["jobs"]["post"]["steps"] if s.get("name") == "Install ffmpeg + fonts")
    assert step.get("timeout-minutes", 999) <= 20
    assert "timeout " in step["run"] and "command -v ffmpeg" in step["run"]
