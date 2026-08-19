"""Retention-driven improvements (2026-08-16).

Retention is what the algorithm ranks on — views only measure how hard it
pushed a video once. Three findings from the channel's own 175 retention rows
drive this file:

  1. minimal retains 70.9% vs quote 53.5% / rule 50.3%  -> weight the rotation
  2. hook length is monotonic against retention          -> cap hooks at 4 words
       1-3w 68.8% | 4-5w 57.3% | 6-7w 54.5% | 8+w 50.0%  (r=-0.29, n=100)
  3. the prompt had SEVEN avoid-blocks and zero examples -> feed winners back
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import content  # noqa: E402


def _rotation(n=12):
    return [content._pick_format([0] * i) for i in range(n)]


# ------------------------------------------------- rotation weighted by retention

def test_minimal_is_the_most_frequent_format():
    """Highest retention of the three kept formats, by ~17 points."""
    c = Counter(_rotation())
    assert c["minimal"] > c["quote"] and c["minimal"] > c["rule"]


def test_no_format_ever_repeats_back_to_back():
    """["minimal","quote","rule","minimal"] has the right MIX but repeats
    minimal across the cycle boundary — the exact repetition risk being fixed
    everywhere else. Order matters as much as proportion."""
    r = _rotation(16)
    assert not [a for a, b in zip(r, r[1:]) if a == b]


def test_all_three_formats_still_appear():
    assert set(_rotation()) == {"minimal", "quote", "rule"}


# --------------------------------------------------------- hook length rule

def test_hook_length_cap_is_in_the_prompt():
    assert "FOUR WORDS OR FEWER" in content.SYSTEM


def test_hook_rule_carries_the_evidence_not_just_the_instruction():
    """A rule with its measurement attached survives the next editor; a bare
    style opinion gets 'improved' away."""
    assert "68.8%" in content.SYSTEM and "-0.29" in content.SYSTEM


# ------------------------------------------------- winning-hook feedback loop

def test_winners_are_returned_from_real_data():
    w = content._winning_hooks(content._load_rows())
    if not w:
        return                      # no retention data in this checkout
    assert len(w) <= 6
    pcts = [p for p, _, _ in w]
    assert pcts == sorted(pcts, reverse=True), "not ranked by retention"


def test_winners_are_capped_so_one_freak_loop_cannot_dominate():
    w = content._winning_hooks(content._load_rows())
    assert all(p <= 300.0 for p, _, _ in w)


def test_tiny_samples_are_excluded():
    """A 3-view video at 200% retention is noise, not a lesson."""
    w = content._winning_hooks(content._load_rows(), min_views=10_000)
    assert w == []


def test_winners_are_deduped():
    w = content._winning_hooks(content._load_rows())
    keys = [h.lower()[:20] for _, h, _ in w]
    assert len(keys) == len(set(keys))


def test_missing_retention_file_is_not_fatal(monkeypatch, tmp_path):
    """Generation must never fail because an optional analytics file is absent."""
    monkeypatch.setattr(content, "RETENTION_CSV", tmp_path / "nope.csv")
    assert content._winning_hooks(content._load_rows()) == []


def test_corrupt_retention_rows_are_skipped(monkeypatch, tmp_path):
    bad = tmp_path / "r.csv"
    bad.write_text("pulled_on,video_id,views,avg_view_seconds,avg_view_pct\n"
                   "2026-01-01,vid,notanumber,x,y\n", encoding="utf-8")
    monkeypatch.setattr(content, "RETENTION_CSV", bad)
    assert content._winning_hooks(content._load_rows()) == []


def test_prompt_asks_for_energy_not_copying():
    """The winners are all on the banned-quote list — reusing them would trip
    the dedup and waste a post."""
    src = (ROOT / "src" / "content.py").read_text()
    assert "Do NOT reuse their words" in src


# ------------------------------------------- retention must stay FRESH

def test_retention_is_pulled_by_the_daily_workflow():
    """scripts/retention.py existed from 2026-08-07 but was wired into NO
    workflow — it had run once, by hand. The content engine now LEARNS from
    retention, so a stale file means _winning_hooks recommends the same six
    hooks forever and never sees a new post."""
    yaml = __import__("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    runs = [s.get("run", "") for s in wf["jobs"]["post"]["steps"]]
    assert any("scripts/retention.py" in r for r in runs), \
        "retention is never pulled — the feedback loop will go stale"


def test_retention_pull_cannot_break_a_post():
    """Older refresh tokens lack yt-analytics.readonly. A missing signal must
    never cost a video."""
    yaml = __import__("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    step = next(s for s in wf["jobs"]["post"]["steps"]
                if "scripts/retention.py" in s.get("run", ""))
    assert step.get("continue-on-error") is True


def test_retention_file_is_committed():
    """Pulled but not committed = still stale on the next run's checkout."""
    wf = (ROOT / ".github/workflows/daily-short.yml").read_text()
    assert "data/retention.csv" in wf.split("git add")[1][:300]
