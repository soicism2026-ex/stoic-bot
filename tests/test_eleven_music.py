"""ElevenLabs edit music (owner 2026-10-25: "find much better music"): plans,
spend guard, and private storage in a public repo (src/vault.py)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edit_music  # noqa: E402
import make_eleven_music as m  # noqa: E402
import vault  # noqa: E402
from test_edit_music import FORBIDDEN_IN_PROMPTS  # noqa: E402

needs_tools = pytest.mark.skipif(not (shutil.which("gpg") and shutil.which("ffmpeg")),
                                 reason="needs gpg and ffmpeg")


def _wf(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


# ------------------------------------------------------------------ plans --

def test_plans_describe_sound_only_and_put_the_drop_where_an_edit_starts():
    plans = m.load_plans()
    assert len(plans) == 10 and len({p["id"] for p in plans}) == 10
    bank_ids = {t["id"] for t in edit_music.load()}
    for p in plans:
        text = " ".join(c["text"] + " " + " ".join(c["positive_styles"] + c.get("negative_styles", []))
                        for c in p["chunks"]).lower()
        for name in FORBIDDEN_IN_PROMPTS:
            assert name not in text, f"{p['id']} names '{name}'"
        assert all(3000 <= c["duration_ms"] <= 120000 for c in p["chunks"]), p["id"]
        assert p["chunks"][0]["duration_ms"] == 5000, p["id"]         # the drop lands at 5 s
        assert 30 <= m.plan_seconds(p) <= 60, p["id"]
        assert any("vocals" in c.get("negative_styles", []) for c in p["chunks"]), p["id"]
        if p["id"] in bank_ids:      # already made: it must be the encrypted ElevenLabs track
            assert next(t for t in edit_music.load() if t["id"] == p["id"])["file"].endswith(".gpg")


def test_rebuilds_of_songs_1_and_9_reference_the_owners_picks():
    refs = {p["conditioning"]["track"] for p in m.load_plans() if p.get("conditioning")}
    assert refs == {"bass_motivation__xl", "promise_spedup__xl"}
    approved = {t["id"] for t in edit_music.load() if t.get("approved")}
    assert refs <= approved
    for p in m.load_plans():
        c = p.get("conditioning")
        if c:
            assert 3000 <= c["end_ms"] - c["start_ms"] <= 30000      # references are at most 30 s


def test_request_body_conditions_only_the_first_chunk():
    p = next(p for p in m.load_plans() if p.get("conditioning"))
    b = m.body(p, "song_x")
    assert b["model_id"] == "music_v2_5" and b["seed"] == p["seed"]
    first, *rest = b["composition_plan"]["chunks"]
    assert first["conditioning_ref"]["song_id"] == "song_x"
    assert first["conditioning_ref"]["range"]["start_ms"] == 0
    assert all("conditioning_ref" not in c for c in rest)
    assert "conditioning_ref" not in p["chunks"][0]                  # the plan file is untouched
    plain = next(p for p in m.load_plans() if not p.get("conditioning"))
    assert "conditioning_ref" not in m.body(plain, None)["composition_plan"]["chunks"][0]


# ------------------------------------------------------------ spend guard --

def test_round_cost_counts_composing_and_reference_uploads():
    plans = m.load_plans()
    secs = sum(m.plan_seconds(p) for p in plans) + 26 + 30            # two 26 s / 30 s references
    assert m.round_cost(plans) == round(secs / 60 * m.CREDITS_PER_MIN)


def test_generate_refuses_without_the_music_key_before_spending(monkeypatch):
    monkeypatch.delenv("MUSIC_KEY", raising=False)
    monkeypatch.setattr(m, "subscription", lambda: pytest.fail("must not call the API"))
    with pytest.raises(SystemExit, match="MUSIC_KEY"):
        m.generate(m.load_plans()[:1])


def test_generate_keeps_a_reserve_for_brian(monkeypatch):
    monkeypatch.setenv("MUSIC_KEY", "k" * 32)
    plans = m.load_plans()
    need = m.round_cost(plans)
    monkeypatch.setattr(m, "subscription", lambda: {"character_limit": need + m.RESERVE - 1,
                                                    "character_count": 0, "tier": "starter"})
    monkeypatch.setattr(m, "_post", lambda *a, **k: pytest.fail("must not compose"))
    with pytest.raises(SystemExit, match="not enough credits"):
        m.generate(plans)


# ---------------------------------------------------------------- privacy --

@needs_tools
def test_vault_round_trip_and_wrong_key(tmp_path, monkeypatch):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"ID3" + bytes(range(256)) * 50)
    enc = vault.encrypt(src, tmp_path / "a.mp3.gpg", key="correct horse battery staple")
    assert enc.read_bytes()[:3] != b"ID3"
    out = vault.decrypt(enc, tmp_path / "b.mp3", key="correct horse battery staple")
    assert out.read_bytes() == src.read_bytes()
    with pytest.raises(subprocess.CalledProcessError):
        vault.decrypt(enc, tmp_path / "c.mp3", key="wrong")
    with pytest.raises(RuntimeError):
        vault.encrypt(src, tmp_path / "x.gpg", key="")


@needs_tools
def test_an_encrypted_track_plays_with_the_key_and_is_skipped_without(tmp_path, monkeypatch):
    mp3 = tmp_path / "t.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=8",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)
    rel = Path("assets/music/edit/zz_test_enc.mp3.gpg")
    enc = ROOT / rel
    try:
        vault.encrypt(mp3, enc, key="test-key-123456")
        t = {"id": "zz_test_enc", "file": str(rel), "approved": True, "start": 1.0}
        monkeypatch.delenv("MUSIC_KEY", raising=False)
        assert edit_music._exists(t) is False
        assert edit_music.fetch(t, tmp_path / "cut.mp3", 3.0) is None
        monkeypatch.setenv("MUSIC_KEY", "test-key-123456")
        assert edit_music._exists(t) is True
        got = edit_music.fetch(t, tmp_path / "cut.mp3", 3.0)
        assert got and got.stat().st_size > 10_000
        assert not (ROOT / "assets" / "music" / "edit" / "zz_test_enc.mp3").exists()
    finally:
        enc.unlink(missing_ok=True)


def test_no_elevenlabs_track_is_ever_stored_in_the_clear():
    """The Music Terms forbid making tracks available to others; the repo is public."""
    for t in edit_music.load():
        if "ElevenLabs" in (t.get("provenance") or {}).get("model", ""):
            assert t["file"].endswith(".mp3.gpg"), t["id"]
            plain = ROOT / t["file"][: -len(".gpg")]
            assert not plain.exists(), t["id"]
    tracked = subprocess.run(["git", "ls-files", "assets/music/edit"], cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    el_ids = {p["id"] for p in m.load_plans()}
    assert not [f for f in tracked if Path(f).name.split(".")[0] in el_ids and not f.endswith(".gpg")]


# -------------------------------------------------------------- workflows --

def test_every_job_that_renders_an_edit_can_decrypt_the_tracks():
    for name, job in (("daily-short.yml", "post"), ("edit-preview.yml", "preview"), ("repost.yml", None)):
        src = (ROOT / ".github" / "workflows" / name).read_text()
        assert "MUSIC_KEY: ${{ secrets.MUSIC_KEY }}" in src, name


def test_the_music_workflow_checks_for_free_before_it_spends_and_never_ships_plaintext():
    wf = _wf("make-eleven-music.yml")
    steps = [s.get("name") for s in wf["jobs"]["music"]["steps"]]
    assert steps.index("Preflight (free)") < steps.index("Generate (encrypted, unapproved)")
    commit = next(s for s in wf["jobs"]["music"]["steps"] if s.get("name") == "Commit the encrypted tracks")
    assert "assets/music/edit/*.gpg" in commit["run"] and ".mp3 " not in commit["run"]
    sampler = next(s for s in wf["jobs"]["music"]["steps"] if s.get("name") == "Sampler, encrypted to the HQ session")
    assert "--encrypt" in sampler["run"] and 'rm -f "$RUNNER_TEMP/sampler.mp4"' in sampler["run"]
    assert "music-sampler.mp4.gpg" in sampler["run"]


def test_the_sampler_can_be_rebuilt_without_spending():
    wf = _wf("make-eleven-music.yml")
    assert "sampler" in wf[True]["workflow_dispatch"]["inputs"]["mode"]["options"]
    steps = {s.get("name"): s for s in wf["jobs"]["music"]["steps"]}
    assert steps["Preflight (free)"]["if"] == "inputs.mode != 'sampler'"
    assert steps["Generate (encrypted, unapproved)"]["if"] == "inputs.mode == 'generate'"
    assert "inputs.mode == 'sampler'" in steps["Sampler, encrypted to the HQ session"]["if"]
