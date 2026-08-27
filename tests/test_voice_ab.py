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


def test_the_channel_has_exactly_one_narrator():
    """SUPERSEDED 2026-08-25: the A/B is called. Owner: "remove the less
    popular voice."

    Christopher beat Steffan on every measure across the same days and slots
    (median day-3 views 70 vs 44, mean 175 vs 89; z = -1.52, a consistent lead
    rather than a proven result). The deciding argument is one the A/B could
    not measure: the channel has used EIGHT narrators across 222 posts, and
    the one thing surviving faceless channels share is a single unmistakable
    voice. Rotating narrators was destroying the asset it was measuring.

    One voice, forever. This test exists to stop a second one drifting back
    in without a deliberate decision."""
    assert len(tts.VOICE_POOL) == 1, [v["name"] for v in tts.VOICE_POOL]
    assert tts.VOICE_POOL[0]["name"] == "Christopher"


def test_no_rejected_voice_is_in_the_pool():
    assert not {v["name"] for v in tts.VOICE_POOL} & REJECTED


def test_voice_ids_are_real_microsoft_names():
    for v in tts.VOICE_POOL:
        assert v["id"].endswith("Neural"), v["id"]
        assert v["id"].startswith("en-"), v["id"]


def test_the_narrator_never_changes():
    """SUPERSEDED 2026-08-25 — this asserted strict alternation between two
    voices. The requirement is now the opposite: the viewer must hear the same
    person every time. A picker that "rotates" a one-entry pool must return
    that entry, not fall back to something else."""
    hist = []
    picks = []
    for _ in range(8):
        v = tts.pick_voice(hist)
        picks.append(v["name"])
        hist.append({"voice_name": v["name"], "video_id": f"v{len(hist)}"})
    assert set(picks) == {"Christopher"}, picks


def test_the_real_history_does_not_resurrect_the_dropped_voice():
    """SUPERSEDED 2026-08-25. posts.csv contains 24 Steffan posts; the
    analytics-weighted picker must not be tempted back to a voice that is no
    longer in the pool."""
    live = ROOT / "data" / "posts.csv"
    if not live.exists():
        pytest.skip("no posts.csv")
    hist = list(csv.DictReader(live.open(newline="", encoding="utf-8")))
    picks = []
    for i in range(6):
        v = tts.pick_voice(hist)
        picks.append(v["name"])
        hist.append({"voice_name": v["name"], "video_id": f"sim{i}"})
    assert set(picks) == {"Christopher"}, picks


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
