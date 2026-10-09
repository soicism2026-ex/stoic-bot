"""Owned original music for edits: approval gate, shuffle, provenance."""
import json
import sys
from pathlib import Path

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
        assert p["reference_audio"] == "none", t["id"]
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
