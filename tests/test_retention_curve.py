"""Where viewers leave — the feedback nobody has to type.

171 of 229 videos sit at exactly 2 comments, both the bot's own. Roughly 73
genuine viewer comments exist across the entire channel, so written feedback
is effectively zero and will stay that way at this size.

But avg_view_pct — the only retention number collected until now — is an
average, and an average hides the thing worth knowing. 55% could be everyone
watching just over half, or half the audience leaving in the first second. The
fixes for those are opposite. The curve distinguishes them.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import retention_curve as rc  # noqa: E402


def test_a_hook_failure_is_named_as_a_hook_failure():
    """Half gone in the first 5% is a hook problem, not a length problem."""
    curve = [(0.0, 1.0), (0.05, 0.48), (0.5, 0.40), (1.0, 0.30)]
    out = rc.describe(curve)
    assert "52% gone by the hook" in out


def test_a_strong_hook_with_a_late_cliff_is_not_blamed_on_the_hook():
    curve = [(0.0, 1.0), (0.05, 0.95), (0.4, 0.90), (0.45, 0.35), (1.0, 0.30)]
    out = rc.describe(curve)
    assert "5% gone by the hook" in out
    assert "45%" in out


def test_the_drop_is_located_in_the_script_not_just_numerically():
    """A percentage is not actionable; "the turn into the lesson" is."""
    curve = [(0.0, 1.0), (0.05, 0.9), (0.45, 0.4), (1.0, 0.3)]
    assert "the turn into the lesson" in rc.describe(curve)


def test_two_videos_with_the_SAME_average_read_differently():
    """The whole reason this exists: the average cannot tell these apart."""
    early = [(0.0, 1.0), (0.05, 0.30), (1.0, 0.28)]
    late = [(0.0, 1.0), (0.05, 0.98), (0.9, 0.90), (1.0, 0.20)]
    assert rc.describe(early) != rc.describe(late)
    assert "gone by the hook" in rc.describe(early)


def test_no_data_is_not_an_error():
    """Retention is only reported once a video has watch time. A fresh or
    tiny video legitimately returns nothing."""
    assert rc.describe([]) == "no retention data yet"


def test_a_missing_signal_never_breaks_a_post(monkeypatch):
    monkeypatch.setattr(rc, "_analytics_service",
                        lambda: (_ for _ in ()).throw(RuntimeError("no scope")))
    monkeypatch.setattr(sys, "argv", ["retention_curve.py"])
    assert rc.main() == 0


def test_promo_comment_is_off():
    """Under a 20-view video with no viewer comments, a bot-posted CTA is the
    tell that says nobody is here. The comment section is the only place this
    channel gets to be a person."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    line = [l for l in wf.splitlines()
            if "PROMO_COMMENT:" in l and not l.strip().startswith("#")]
    assert line and '"0"' in line[0], line


def test_the_curve_is_committed_so_it_accumulates():
    """A signal the next run cannot see is not a signal."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert "data/retention_curves.csv" in wf
