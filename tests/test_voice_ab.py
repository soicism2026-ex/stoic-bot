"""The Steffan/Christopher A/B (owner verdict, 2026-08-07).

"I like Steffan and Christopher, the rest not so much — you can cycle between
those two and we can check back in to see which one the audience prefers."

That is a two-arm experiment, so the pool must contain exactly those two, they
must actually alternate, and nothing else may speak — a third voice on the
first post of each day would contaminate the comparison while still being
logged as part of the rotation.
"""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tts  # noqa: E402

CHOSEN = {"Steffan", "Christopher"}
REJECTED = {"Ryan", "Thomas", "Roger", "William", "Andrew", "BrianEdge", "Guy"}


def test_pool_is_exactly_the_two_chosen_voices():
    assert {v["name"] for v in tts.VOICE_POOL} == CHOSEN


def test_no_rejected_voice_is_in_the_pool():
    assert not {v["name"] for v in tts.VOICE_POOL} & REJECTED


def test_voice_ids_are_real_microsoft_names():
    for v in tts.VOICE_POOL:
        assert v["id"].endswith("Neural"), v["id"]
        assert v["id"].startswith("en-"), v["id"]


def test_rotation_alternates_strictly():
    """With two entries, blocking the most recent gives strict alternation —
    which is what makes the comparison fair rather than lopsided."""
    hist = []
    picks = []
    for _ in range(8):
        v = tts.pick_voice(hist)
        picks.append(v["name"])
        hist.append({"voice_name": v["name"], "video_id": f"v{len(hist)}"})
    assert all(a != b for a, b in zip(picks, picks[1:])), picks
    assert set(picks) == CHOSEN


def test_rotation_alternates_on_the_real_history():
    """Live posts.csv is heavily weighted toward Christopher; the new voice
    must still get equal airtime rather than being starved by that history."""
    live = ROOT / "data" / "posts.csv"
    if not live.exists():
        pytest.skip("no posts.csv")
    hist = list(csv.DictReader(live.open(newline="", encoding="utf-8")))
    picks = []
    for i in range(6):
        v = tts.pick_voice(hist)
        picks.append(v["name"])
        hist.append({"voice_name": v["name"], "video_id": f"sim{i}"})
    assert set(picks) == CHOSEN, picks
    assert abs(picks.count("Steffan") - picks.count("Christopher")) <= 1


def test_elevenlabs_is_silenced_so_the_ab_stays_clean():
    """A paid third voice on the first post each day would be logged inside the
    rotation while sounding like neither arm."""
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    env = next(s["env"] for s in wf["jobs"]["post"]["steps"]
               if "ELEVENLABS_POSTS_PER_DAY" in (s.get("env") or {}))
    assert str(env["ELEVENLABS_POSTS_PER_DAY"]) == "0"


def test_chatterbox_stays_off_so_it_cannot_rejoin():
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    env = next(s["env"] for s in wf["jobs"]["post"]["steps"]
               if "CHATTERBOX_LOCAL" in (s.get("env") or {}))
    assert "'0'" in env["CHATTERBOX_LOCAL"]


def test_logged_voice_is_whoever_actually_spoke():
    """The A/B is only readable if posts.csv records the real speaker, not the
    intended one — tts sets LAST_VOICE_NAME after synthesis for this reason."""
    assert hasattr(tts, "LAST_VOICE_NAME")
