"""
The pipeline must run to completion with NO paid language-model key.

OWNER DECISION 2026-09-18: "i dont want to pay for the separate claude api
anymore and i just want to use higgfield."

That is a real operating mode, not a degraded one, so it gets real tests. The
failure this guards against is not a crash — it is the quieter thing that
already happened once: for 51 runs after the credits ran dry, the reviewer
recorded `pacing=5.0` across the board and the pipeline read the failure as a
verdict. A switched-off feature must SAY it is off and record NOTHING.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import llm  # noqa: E402


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_DISABLED", raising=False)


# ------------------------------------------------------------ the switch

def test_no_key_means_unavailable():
    assert llm.available() is False
    assert llm.reason() == "no ANTHROPIC_API_KEY"


def test_a_key_makes_it_available(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm.available() is True
    assert llm.reason() == ""


def test_the_kill_switch_beats_a_present_key(monkeypatch):
    """The owner must be able to stop spending without deleting the secret
    from GitHub, and the no-API path must be exercisable on demand."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_DISABLED", "1")
    assert llm.available() is False
    assert llm.reason() == "LLM_DISABLED=1"


def test_a_blank_key_is_not_a_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert llm.available() is False


def test_every_skip_notice_names_the_feature_and_the_reason():
    for feature in llm.FEATURES:
        note = llm.skip_note(feature)
        assert feature in note and "no ANTHROPIC_API_KEY" in note
        assert note.startswith("  [llm] "), "one greppable prefix for all"


# -------------------------------------------- nothing is invented in its place

def test_the_reviewer_records_unreviewed_not_a_middling_score():
    """The exact regression: an all-5.0 row in QA_LOG.md reads like a verdict.
    With calls off there must be NO scores at all."""
    import visual_qa
    r = visual_qa.score_video(Path("/nonexistent.mp4"), {})
    assert r.verdict == visual_qa.UNREVIEWED
    assert r.scores == {}
    assert "llm_disabled" in r.flags
    # ...and it must not block the day's post. preflight is the gate that does.
    assert r.verdict != "fail"


def test_qa_says_reduced_rather_than_passed():
    """ffmpeg checks still ran. Reporting a clean pass would claim the video
    was looked at when nothing looked at it."""
    import qa_check
    assert not llm.available()
    note = llm.skip_note("qa_vision")
    assert "ffmpeg checks still run" in note


def test_the_reviewer_does_not_even_try_to_call(monkeypatch):
    """Calling and catching is what filled the log with API-error text. Ask
    first: with no key, frame extraction must not even happen."""
    import visual_qa
    monkeypatch.setattr(visual_qa, "extract_hook_frames",
                        lambda *a, **k: pytest.fail("frames extracted with no key"))
    assert visual_qa.score_video(Path("/nonexistent.mp4"), {}).scores == {}


# --------------------------------------------------- content: refuse, clearly

def test_generating_a_post_raises_a_named_error_not_a_keyerror():
    import content
    with pytest.raises(content.ContentUnavailable) as e:
        content.generate_content()
    msg = str(e.value)
    assert "data/stories.json" in msg, "the message must say what to do"
    assert "ANTHROPIC_API_KEY" in msg


def test_daily_post_treats_no_script_as_a_stop_not_a_render_failure():
    """Retrying five times and raiding the backup bank would spend compute
    fixing something that is not broken: there is simply no script today."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "except ContentUnavailable" in src
    # The handler's body runs until dedent back to the function's own level.
    after = src[src.index("except ContentUnavailable"):]
    lines = after.splitlines()[1:]
    handler = []
    for ln in lines:
        if ln.strip() and not ln.startswith(" " * 12):
            break
        handler.append(ln)
    assert any(ln.strip() == "return" for ln in handler), (
        "it must return, not fall through into the render loop")


def test_the_backup_top_up_is_skipped_rather_than_attempted():
    """The bank can only be filled by the generator, so with it off there is
    nothing to add — and raising inside the render path would look like a QA
    failure."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    top_up = src[src.index("def _add_to_backup_bank"):]
    assert "llm.available()" in top_up[:800]
    assert top_up.index("llm.available()") < top_up.index("generate_content()")


# ---------------------------------------------------- replies and strategy

def test_comment_replies_exit_without_posting_anything():
    """Both halves of that script are model calls. A canned reply would be
    worse than none — the screen exists so a real answer meets a real comment."""
    src = (ROOT / "scripts" / "reply_to_comments.py").read_text()
    body = src[src.index("def main():"):]
    assert "llm.available()" in body[:900]
    assert body.index("llm.available()") < body.index("_yt_service()")


def test_the_strategy_file_is_left_alone_rather_than_emptied():
    src = (ROOT / "scripts" / "strategy_loop.py").read_text()
    assert "llm.skip_note(\"strategy\")" in src
    i = src.index('llm.skip_note("strategy")')
    assert "return None" in src[i:i + 400]


# ------------------------------------------------------------- preflight

def test_the_secrets_gate_no_longer_fails_on_a_missing_anthropic_key():
    """This is what would have broken every run: check_secrets exits 1 on a
    missing required key, and Anthropic used to be required."""
    import check_secrets
    assert check_secrets.check_anthropic() is True


def test_the_free_gate_that_still_blocks_needs_no_api():
    """Losing the paid reviewer is survivable only because preflight is pure
    ffmpeg. If it ever grows an API call, the channel has no gate at all."""
    src = (ROOT / "scripts" / "preflight.py").read_text()
    assert "anthropic" not in src.lower()
    assert "ANTHROPIC_API_KEY" not in src


# --------------------------------------------------------------- the runway

def test_the_story_bank_reports_its_runway_every_run():
    """With the generator off this bank IS the content supply. The morning it
    empties must never be the first anyone hears of it."""
    import validate_stories as vs
    assert vs.LOW_WATER >= 1
    assert vs._remaining() >= 0


def test_a_low_bank_warns_but_does_not_block_the_post(capsys, monkeypatch):
    import validate_stories as vs
    monkeypatch.setattr(sys, "argv", ["validate_stories.py"])
    monkeypatch.setattr(vs, "LOW_WATER", 10_000)
    assert vs.main() == 0, "a warning must never stop today's post"
    assert "RUNWAY WARNING" in capsys.readouterr().err


def test_the_cost_registry_no_longer_bills_for_the_api():
    import json
    costs = json.loads((ROOT / "data" / "costs.json").read_text())
    names = [s["name"] for s in costs["subscriptions"]]
    assert not any("Anthropic API" in n for n in names), names
    assert any("Anthropic API" in c["name"] for c in costs.get("cancelled", [])), (
        "cancelled, not deleted — the history is the point")
