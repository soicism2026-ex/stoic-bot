"""Owned original music for edits: approval gate, shuffle, provenance."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edit_music  # noqa: E402

# Names of the songs and artists the owner asked for. A prompt naming one is
# an attempt to copy it; the prompts must describe the STYLE only.
FORBIDDEN_IN_PROMPTS = [
    "zimmer", "interstellar", "stay", "no time for caution", "where we're going",
    "devil", "luke muzzic", "soap", "pharrell", "freedom", "bass media",
    "god's promise", "daniel.mp3", "gigi", "toujours", "chubina", "east duo",
    "kevin macleod",
]


def _fake(monkeypatch, n=3, approved=True):
    tracks = [{"id": f"t{i}", "file": f"assets/music/edit/t{i}.mp3",
               "approved": approved, "start": 3.0} for i in range(n)]
    monkeypatch.setattr(edit_music, "load", lambda: tracks)
    monkeypatch.setattr(edit_music, "_exists", lambda t: True)
    return tracks


def test_nothing_airs_until_the_owner_approves(monkeypatch):
    _fake(monkeypatch, approved=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("REEL_EDIT_MUSIC", raising=False)
    assert edit_music.pick([]) is None


def test_preview_override_only_in_dry_run(monkeypatch):
    _fake(monkeypatch, approved=False)
    monkeypatch.setenv("REEL_EDIT_MUSIC", "t1")
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert edit_music.pick([]) is None          # a live post can never use it
    monkeypatch.setenv("DRY_RUN", "1")
    assert edit_music.pick([])["id"] == "t1"    # the preview can audition it


def test_shuffle_never_repeats_within_a_cycle(monkeypatch):
    _fake(monkeypatch, n=5)
    monkeypatch.delenv("REEL_EDIT_MUSIC", raising=False)
    rows, seq = [], []
    for day in range(40):
        t = edit_music.pick(rows, seed=f"2026-11-{day:02d}")
        seq.append(t["id"])
        rows.append({"music_track": edit_music.PREFIX + t["id"]})
    cycles = [tuple(seq[i:i + 5]) for i in range(0, 40, 5)]
    for c in cycles:   # every track once per cycle
        assert len(set(c)) == 5, f"repeat inside a cycle: {c}"
    for a, b in zip(seq, seq[1:]):   # never the same track twice in a row
        assert a != b, seq
    # ...and it is a shuffle, not a fixed rotation
    assert len(set(cycles)) > 1


def test_same_day_retry_picks_the_same_track(monkeypatch):
    _fake(monkeypatch, n=6)
    monkeypatch.delenv("REEL_EDIT_MUSIC", raising=False)
    a = edit_music.pick([], seed="2026-10-10")
    b = edit_music.pick([], seed="2026-10-10")
    assert a["id"] == b["id"]


def test_every_track_has_provenance_and_names_no_song():
    for t in edit_music.load():
        p = t.get("provenance", {})
        for k in ("model", "license", "prompt", "reference_audio", "generated"):
            assert p.get(k), f"{t['id']} missing provenance.{k}"
        # No one else's song, ever. An ElevenLabs rebuild may reference one of
        # OUR approved originals (owner 2026-10-25: "more like 1 and 9").
        ref = p["reference_audio"]
        if ref != "none":
            own = next((x for x in edit_music.load() if f"own:{x['id']}" == ref), None)
            assert own and ("ACE-Step" in own["provenance"]["model"]
                            or "ElevenLabs" in own["provenance"]["model"]), t["id"]
        prompt = p["prompt"].lower()
        for name in FORBIDDEN_IN_PROMPTS:
            assert name not in prompt, f"{t['id']} prompt names '{name}'"


def test_track_files_exist_and_stay_small():
    total = 0
    for t in edit_music.load():
        f = ROOT / t["file"]
        assert f.exists(), f"{t['id']}: {t['file']} missing"
        size = f.stat().st_size
        assert size < 3_000_000, f"{t['id']} is {size} bytes"
        total += size
    assert total < 40_000_000


def test_bank_json_is_valid_and_ids_unique():
    data = json.loads((ROOT / "data" / "edit_music.json").read_text())
    ids = [t["id"] for t in data]
    assert len(ids) == len(set(ids))
    for t in data:
        assert isinstance(t.get("approved"), bool), t["id"]
        assert float(t.get("start", 0)) >= 0


def test_daily_post_prefers_owned_music_and_keeps_a_fallback():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    i = src.index("em = edit_music.pick(post_rows")
    j = src.index("track = epic_music.pick(post_rows)")
    assert i < j and "if not got:" in src[i:j]


def test_drop_finder_starts_just_before_the_drop():
    import make_edit_music as m
    db = [-40.0] * 20 + [-18.0] * 60          # 10s quiet build, then the drop
    start, how, contrast = m.find_start(db)
    assert how == "drop" and contrast > 15
    assert start == 10.0 - m.LEAD


def test_drop_finder_without_a_drop_uses_the_loudest_section():
    import make_edit_music as m
    db = [-20.0 + 0.1 * i for i in range(100)]   # a slow swell: no step >= 3 dB
    start, how, _ = m.find_start(db)
    assert how == "loudest"
    assert 0 <= start <= len(db) * m.HOP - m.SECTION


def test_merge_keeps_approval_and_new_tracks_start_unapproved(tmp_path, monkeypatch):
    import make_edit_music as m
    bank = tmp_path / "edit_music.json"
    bank.write_text(json.dumps([{"id": "old", "file": "assets/music/edit/old.mp3",
                                 "approved": True, "provenance": {}}]))
    monkeypatch.setattr(m, "BANK", bank)
    monkeypatch.setattr(m, "OUT_DIR", tmp_path / "edit")
    src = tmp_path / "new"
    src.mkdir()
    for tid in ("old", "fresh"):
        (src / f"{tid}.mp3").write_bytes(b"x" * 100)
        (src / f"{tid}.json").write_text(json.dumps(
            {"id": tid, "file": f"assets/music/edit/{tid}.mp3", "approved": True,
             "provenance": {"prompt": "p"}}))
    assert m.merge(src) == 2
    got = {t["id"]: t["approved"] for t in json.loads(bank.read_text())}
    assert got == {"old": True, "fresh": False}   # approval only ever comes from the owner


def test_generator_is_pinned_and_text_only():
    src = (ROOT / "scripts" / "make_edit_music.py").read_text()
    assert 'ACE_COMMIT = "d881ad2c080bac65cc73cb3bbcc831f79462b98b"' in src
    assert '"lyrics": "[Instrumental]"' in src
    assert "--ref-audio" not in src and "--src-audio" not in src
    for s in json.loads((ROOT / "data" / "edit_music_styles.json").read_text()):
        cap = s["caption"].lower()
        for name in FORBIDDEN_IN_PROMPTS:
            assert name not in cap, f"style {s['id']} names '{name}'"


def test_the_owners_current_picks_are_what_airs():
    """Owner 2026-10-27, judging the ElevenLabs sampler: "1 and 2 are good ...
    for now 1 and 2 pass for something better than we had before"; then, on
    round 3, built from those two: "All are good rotate them"."""
    bank = edit_music.load()
    approved = {t["id"] for t in bank if t.get("approved")}
    round3 = {t["id"] for t in bank if t["id"].startswith("el3_")}
    assert len(round3) == 9
    assert approved == {"el_bass_piano", "el_bass_felt_dark"} | round3
    for t in bank:
        if t["id"] in approved:
            assert t["approved_on"] and t["approved_how"].startswith("Owner"), t["id"]


def test_a_late_drop_starts_early_instead_of_looping():
    """el3_upright_tape drops 24 s into a 40 s track and edits run to 17 s.
    render.py loops the bed, so a cut that ran out restarted at the drop in
    the last second. It starts early enough to end with the track instead."""
    assert edit_music.cut_start(9.5, 17.0, 40.0) == 9.5             # room: from the drop
    assert edit_music.cut_start(24.0, 12.0, 40.0) == 24.0
    late = edit_music.cut_start(24.0, 17.3, 40.0)                    # a long edit
    assert 22.0 < late < 24.0 and late + 17.3 <= 40.0
    assert edit_music.cut_start(5.0, 50.0, 40.0) == 0.0              # shorter than the Short
    assert edit_music.cut_start(24.0, 17.3, 0.0) == 24.0             # length unknown: as before
    assert edit_music.cut_start(-1.0, 5.0, 40.0) == 0.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_the_cut_covers_the_whole_short_even_from_a_late_drop(tmp_path):
    src = tmp_path / "late.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=20",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(src)], check=True)
    assert abs(edit_music._length(src) - 20.0) < 0.15
    t = {"id": "late", "file": str(src), "approved": True, "start": 14.0}
    got = edit_music.fetch(t, tmp_path / "cut.mp3", 12.0)
    assert got and abs(edit_music._length(got) - 12.0) < 0.15        # not 6 s, then a loop
    early = {"id": "early", "file": str(src), "approved": True, "start": 2.0}
    got = edit_music.fetch(early, tmp_path / "cut2.mp3", 12.0)
    assert got and abs(edit_music._length(got) - 12.0) < 0.15


def test_the_planned_track_is_the_one_a_live_run_picks(monkeypatch):
    """The rehearsal check has no MUSIC_KEY, so it plans from the approval
    flags; with the key present the live pick must be the same track."""
    _fake(monkeypatch, n=6)
    monkeypatch.delenv("REEL_EDIT_MUSIC", raising=False)
    rows = []
    for day in range(1, 25):
        seed = f"2026-11-{day:02d}"
        live = edit_music.pick(rows, seed=seed)["id"]
        assert edit_music.planned(rows, seed=seed) == live
        rows.append({"music_track": edit_music.PREFIX + live})
