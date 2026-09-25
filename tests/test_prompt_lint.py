"""The free pre-flight prompt check. Each case is a failure seen in our own
generated footage (reviewed frame by frame on 2026-09-25)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import prompt_lint as pl  # noqa: E402


def errs(spec, cast=None):
    return [m for lvl, m in pl.check_shot(spec, cast) if lvl == "ERROR"]


def test_every_storyboard_passes_before_a_cent_is_spent():
    """CI gate: no board may contain a shot the checker would refuse."""
    boards = json.loads((ROOT / "data" / "storyboards.json").read_text())
    bad = [(sid, n, m) for sid, b in boards.items() if not sid.startswith("_")
           for n, lvl, m in pl.check_board(b) if lvl == "ERROR"]
    assert bad == [], bad


def test_frozen_motion_is_refused():
    """'stays completely still' produced a near-frozen clip (before_breakfast 1-2)."""
    s = {"model": "kling", "seconds": 3.5, "picture": "a man", "motion": "he stays completely still"}
    assert errs(s)
    s["motion"] += ", slow gentle camera creep in"
    assert not errs(s)


def test_readable_writing_is_refused_unless_blank_or_unreadable():
    assert errs({"model": "wan", "seconds": 4, "picture": "a hand writing figures in a ledger"})
    assert not errs({"model": "wan", "seconds": 4,
                     "picture": "a scroll, the writing too small to read and out of focus"})
    assert not errs({"model": "wan", "seconds": 4, "picture": "a blank yellow sticky note"})


def test_mirror_is_refused():
    assert errs({"model": "kling", "seconds": 3.5, "picture": "seen in the bathroom mirror",
                 "motion": "slow push in"})


def test_long_kling_shots_are_refused_for_cost():
    """Kling bills >5.5s as a 10s clip — double."""
    assert errs({"model": "kling", "seconds": 8, "picture": "a man", "motion": "slow push in"})
    assert not errs({"model": "kling", "seconds": 5.5, "picture": "a man", "motion": "slow push in"})


def test_anachronisms_are_refused_in_ancient_shots_only():
    assert errs({"model": "wan", "seconds": 4, "picture": "a Roman thief holding a glass lantern"})
    assert not errs({"model": "wan", "seconds": 4, "picture": "a modern hallway with a lantern"})


def test_two_held_objects_are_flagged():
    """The candle fused into the top of the walking stick (earthenware 3)."""
    w = pl.check_shot({"model": "kling", "seconds": 3.5,
                       "picture": "holding a candle and leaning on a walking stick",
                       "motion": "slow push in"})
    assert any(lvl == "WARN" and "two held" in m for lvl, m in w)


def test_motion_is_always_hardened_with_a_camera_move():
    assert "push" in pl.harden_motion("he breathes")
    assert pl.harden_motion("slow dolly left") == "slow dolly left"


def test_the_generator_refuses_a_bad_shot_without_calling_the_api(monkeypatch, tmp_path):
    import hfgen
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "a:b")
    monkeypatch.setattr(hfgen.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("paid call made")))
    out = hfgen.shot({"model": "wan", "seconds": 4, "picture": "a hand writing in a ledger"},
                     {}, tmp_path / "x.mp4")
    assert out is None


def test_kling_gets_the_negative_prompt_and_a_5s_bill(monkeypatch, tmp_path):
    import hfgen
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "a:b")
    sent = []

    class R:
        status_code = 200
        def __init__(self, d): self.d = d
        def json(self): return self.d
    def post(url, json=None, headers=None, timeout=None):
        sent.append(json)
        if "soul" in url:
            return R({"status": "completed", "request_id": "s", "images": [{"url": "u"}]})
        return R({"status": "completed", "request_id": "v", "video": {"url": "v"}})
    monkeypatch.setattr(hfgen.requests, "post", post)
    monkeypatch.setattr(hfgen, "_download", lambda u, o: o)
    monkeypatch.setattr(hfgen, "_normalise", lambda s, o, sec: o)
    hfgen.shot({"model": "kling", "seconds": 5.5, "picture": "a Roman senator in a toga",
                "motion": "he nods"}, {}, tmp_path / "k.mp4")
    still, vid = sent
    assert "five fingers" in still["prompt"] and "period-accurate" in still["prompt"]
    assert "extra fingers" in vid["negative_prompt"]
    assert vid["duration"] == 5
    assert "push" in vid["prompt"]


def test_writing_tool_anachronisms_seen_in_aired_posts_are_refused():
    """Aired: a 'bronze stylus on wax' became a fountain pen; Seneca wrote in a
    leather-bound journal in front of a chalkboard."""
    for thing in ("fountain pen", "notebook", "leather-bound journal", "chalkboard"):
        assert errs({"model": "wan", "seconds": 4,
                     "picture": f"Seneca the Roman philosopher at a desk with a {thing}"}), thing


def test_ancient_prompts_state_the_period_writing_tools():
    import hfgen
    g = hfgen._guarded("an old Roman man writing at a desk")
    assert "bronze stylus" in g and "papyrus" in g


def test_a_resolution_shot_must_name_the_face():
    """'shoulders relaxed, lies back' aired as 'distressed, head in hands'."""
    s = {"model": "kling", "seconds": 5, "resolve": True,
         "picture": "sitting on his bed, shoulders relaxed", "motion": "he lies back, slow push in"}
    assert errs(s)
    s["picture"] += ", a small relieved smile"
    assert not errs(s)
