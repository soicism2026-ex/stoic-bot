"""Repetition is the channel's recurring failure mode, and it never shows up
as an error. Rule 7 shipped 13x, one music bed shipped 30x, and the same hook
shipped verbatim 3x — all with a green test suite, because the CODE was right
and the DATA was wrong.

These tests cover the two fixes (cinematic bed rotation, full-history hook
ban) and the watchdog that judges the output instead of the code.
"""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import music  # noqa: E402
import variety_check as vc  # noqa: E402


def _rows(*tracks):
    return [{"music_track": t, "video_id": f"v{i}"} for i, t in enumerate(tracks)]


# ------------------------------------------------- cinematic bed rotation

def test_more_than_one_cinematic_bed_exists():
    """The whole bug was a single hardcoded bed."""
    assert len(music.CINEMATIC_SCORES) >= 4


def test_every_cinematic_bed_has_a_filter_graph():
    for name in music.CINEMATIC_SCORES:
        assert any(isinstance(v, dict) and name in v
                   for v in vars(music).values()), f"{name} has no synth graph"


def test_picker_blocks_the_last_two_used():
    """Blocking only one still lets a bed return the same afternoon."""
    rows = _rows("cinematic_score_f", "cinematic_score_d")
    # reversed(rows) -> _d is most recent, _f second
    got = music.pick_cinematic_score(rows)["name"]
    assert got not in {"cinematic_score_d", "cinematic_score_f"}


def test_picker_returns_a_known_bed():
    assert music.pick_cinematic_score([])["name"] in music.CINEMATIC_SCORES


def test_picker_survives_an_exhausted_pool():
    """If every bed is recent, still return one rather than crashing."""
    rows = _rows(*music.CINEMATIC_SCORES)
    assert music.pick_cinematic_score(rows)["name"] in music.CINEMATIC_SCORES


def test_picker_ignores_rows_without_a_track():
    rows = [{"music_track": ""}, {"music_track": None}]
    assert music.pick_cinematic_score(rows)["name"] in music.CINEMATIC_SCORES


@pytest.mark.parametrize("name", music.CINEMATIC_SCORES)
def test_every_bed_actually_renders(name, tmp_path):
    """ffmpeg's tremolo rejects f < 0.1 — two beds were silently unrenderable
    when first written. A bed that fails to synthesize means a silent video."""
    if not __import__("shutil").which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    graph = next(v[name] for v in vars(music).values()
                 if isinstance(v, dict) and name in v)
    out = tmp_path / f"{name}.mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-filter_complex",
         graph.format(d=2), "-t", "2", "-c:a", "libmp3lame", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:300]
    assert out.stat().st_size > 2_000


# ------------------------------------------------------- the watchdog itself

def _write(tmp_path, monkeypatch, rows):
    p = tmp_path / "posts.csv"
    fields = ["date", "theme", "author", "quote", "caption", "video_url",
              "video_id", "voice_name", "music_track", "hook", "experiment",
              "format"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    monkeypatch.setattr(vc, "POSTS", p)
    return p


def test_catches_verbatim_hook_repeat(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Nero handed him a death sentence."},
        {"hook": "Something else."},
        {"hook": "Nero handed him a death sentence."},
    ])
    issues, healed = [], []
    vc.check_verbatim_hooks(vc._load(), 0, issues, healed)
    assert any("verbatim" in i for i in issues)


def test_catches_repeated_rule_number(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Rule 7: One."}, {"hook": "Rule 7: Two."},
    ])
    issues, healed = [], []
    vc.check_rule_numbers(vc._load(), 0, issues, healed)
    assert any("rule number 7" in i for i in issues)


def test_passes_when_rule_numbers_are_distinct(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Rule 7: One."}, {"hook": "Rule 12: Two."},
    ])
    issues, healed = [], []
    vc.check_rule_numbers(vc._load(), 0, issues, healed)
    assert issues == []


def test_catches_a_single_music_bed_dominating(tmp_path, monkeypatch):
    """The exact 30/30 cinematic_score case."""
    rows = [{"music_track": "cinematic_score"} for _ in range(10)]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_dominance(vc._load(), "music_track", "music", issues)
    assert any("rotation is not varying" in i for i in issues)


def test_healthy_rotation_raises_nothing(tmp_path, monkeypatch):
    rows = [{"music_track": t} for t in
            ["a", "b", "c", "d", "e"] * 2]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_dominance(vc._load(), "music_track", "music", issues)
    assert issues == []


def test_catches_formulaic_hook_openers(tmp_path, monkeypatch):
    """Six hooks opening on the same real word is a formula."""
    rows = [{"hook": f"Stop doing thing {i}"} for i in range(6)]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_hook_openers(vc._load(), issues)
    assert any("same word" in i for i in issues)


def test_rule_prefix_is_not_counted_as_a_formulaic_opener(tmp_path, monkeypatch):
    """"Rule N:" is written by content._rule_directive, not by the model.

    Counting it flagged the rule format's own signature as model fixation —
    a warning no prompt change could ever clear. The word AFTER it is what
    reveals a formula, and here those words are all different.
    """
    rows = [{"hook": f"Rule {i}: {w} it."} for i, w in
            enumerate(["Guard", "Choose", "Train", "Own", "Carry", "Spend"])]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_hook_openers(vc._load(), issues)
    assert issues == [], issues


def test_formula_hiding_behind_a_rule_prefix_is_still_caught(tmp_path, monkeypatch):
    """Stripping the prefix must not become a blanket exemption."""
    rows = [{"hook": f"Rule {i}: Stop wanting thing {i}."} for i in range(6)]
    _write(tmp_path, monkeypatch, rows)
    issues = []
    vc.check_hook_openers(vc._load(), issues)
    assert any("'stop'" in i for i in issues), issues


def test_catches_duplicate_quotes(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [{"quote": "Same"}, {"quote": "Same"}])
    issues, healed = [], []
    vc.check_duplicate_quotes(vc._load(), 0, issues, healed)
    assert any("quote used 2x" in i for i in issues)


def test_missing_posts_csv_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vc, "POSTS", tmp_path / "nope.csv")
    monkeypatch.setattr(sys, "argv", ["variety_check.py"])
    assert vc.main() == 0


def test_exit_code_signals_problems(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [
        {"hook": "Same hook.", "music_track": "x", "quote": "q"},
        {"hook": "Same hook.", "music_track": "x", "quote": "q"},
    ])
    monkeypatch.setattr(sys, "argv", ["variety_check.py"])
    assert vc.main() == 1


# ---------------------------------------------- live repeats vs healed ones
#
# The check was exiting 1 on every single run with eight warnings, all of them
# June/July damage that had already been fixed: rule 7 (last used 2026-08-06),
# a Seneca quote reused four times (last 2026-06-07), six verbatim hooks (last
# 2026-08-06). A watchdog that always barks is a watchdog nobody hears, and
# the ninth warning — a real one — would have landed in that noise unseen.
#
# The fix narrows the ALARM to repeats that recur inside the window while
# keeping detection across all history. These tests exist to prove the second
# half of that sentence is still true.


def _old_then_new(old_hook, n_filler, recent_hook=None):
    """A repeat far in the past, then n_filler clean posts, then maybe a recur."""
    rows = [{"hook": old_hook, "date": "2026-06-01"},
            {"hook": old_hook, "date": "2026-06-02"}]
    rows += [{"hook": f"unique hook {i}", "date": "2026-07-01"}
             for i in range(n_filler)]
    if recent_hook:
        rows.append({"hook": recent_hook, "date": "2026-08-23"})
    return rows


def test_repeat_that_stopped_before_the_window_does_not_warn(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, _old_then_new("Nero handed him a sentence.", 40))
    issues, healed = [], []
    rows = vc._load()
    vc.check_verbatim_hooks(rows, len(rows) - 30, issues, healed)
    assert issues == [], issues
    assert healed, "a fixed repeat must still be reported, just not as a failure"


def test_the_same_repeat_recurring_today_DOES_warn(tmp_path, monkeypatch):
    """The critical case: detection must survive the noise reduction."""
    hook = "Nero handed him a sentence."
    _write(tmp_path, monkeypatch, _old_then_new(hook, 40, recent_hook=hook))
    issues, healed = [], []
    rows = vc._load()
    vc.check_verbatim_hooks(rows, len(rows) - 30, issues, healed)
    assert any("verbatim" in i for i in issues), issues


def test_live_warning_names_the_date_it_last_happened(tmp_path, monkeypatch):
    hook = "Nero handed him a sentence."
    _write(tmp_path, monkeypatch, _old_then_new(hook, 40, recent_hook=hook))
    issues, healed = [], []
    rows = vc._load()
    vc.check_verbatim_hooks(rows, len(rows) - 30, issues, healed)
    assert "2026-08-23" in issues[0], issues


def test_quote_reused_across_a_long_gap_still_warns(tmp_path, monkeypatch):
    """A quote must never repeat at ANY distance — the block list is all-history.

    So detection deliberately spans everything; only the recurrence has to be
    recent. A quote first used in June and used again today is exactly the
    block-list failure this check exists to catch.
    """
    rows = [{"quote": "On living well", "date": "2026-06-01"}]
    rows += [{"quote": f"other {i}", "date": "2026-07-01"} for i in range(50)]
    rows += [{"quote": "On living well", "date": "2026-08-23"}]
    _write(tmp_path, monkeypatch, rows)
    issues, healed = [], []
    loaded = vc._load()
    vc.check_duplicate_quotes(loaded, len(loaded) - 30, issues, healed)
    assert any("block list" in i for i in issues), issues


def test_rule_number_reused_only_in_the_distant_past_is_healed(tmp_path, monkeypatch):
    rows = [{"hook": "Rule 7: a", "date": "2026-07-01"},
            {"hook": "Rule 7: b", "date": "2026-08-06"}]
    rows += [{"hook": f"Rule {i + 10}: c", "date": "2026-08-20"} for i in range(40)]
    _write(tmp_path, monkeypatch, rows)
    issues, healed = [], []
    loaded = vc._load()
    vc.check_rule_numbers(loaded, len(loaded) - 30, issues, healed)
    assert issues == [], issues
    assert any("rule number 7" in h for h in healed), healed


def test_real_posts_csv_is_currently_clean(tmp_path, monkeypatch):
    """Regression bar for the live data: the eight warnings must stay gone.

    If this fails, either a genuine repeat shipped or the window logic broke.
    Both are worth stopping for.
    """
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "variety_check.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------ the background regression
#
# 2026-08-25: comparing day-3 views at identical video age, the switch from
# stock VIDEO backgrounds to AI STILLS coincided with the largest sustained
# drop in the channel's history:
#
#   stock video, 10 Jul - 6 Aug : n=82  median 217
#   AI stills,   7 Aug onward   : n=44  median  58    Mann-Whitney z = 5.1
#
# Day-level data is noisier, so this is association rather than a proven
# single cause — but it is the biggest identifiable change at the biggest
# drop, and it was only findable by inferring from COMMIT DATES, because the
# background provider was never recorded. These tests keep both fixes true.

def test_generated_backgrounds_stay_off_until_a_measured_win():
    """A revert that silently flips back is not a revert."""
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    line = [l for l in wf.splitlines()
            if "REEL_IMAGE_BG:" in l and not l.strip().startswith("#")]
    assert line, "REEL_IMAGE_BG is not set in the daily workflow"
    assert '"0"' in line[0], (
        f"AI still backgrounds are back on ({line[0].strip()}). They are "
        f"associated with a 3.8x drop in day-3 views; re-enable only with a "
        f"measured win.")


def test_background_source_is_recorded_for_every_post():
    """The variable that caused the drop was invisible in the data."""
    import logbook
    assert "bg_source" in logbook.FIELDS


def test_background_module_reports_what_served_the_clip():
    import backgrounds
    backgrounds._note_source("PIXABAY")
    assert backgrounds.LAST_BG_SOURCE == "PIXABAY"
