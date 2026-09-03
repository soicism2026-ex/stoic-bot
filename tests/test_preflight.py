"""Look at the video before it publishes — a gate, not a reminder.

Owner, 2026-09-01: "How can I teach you to learn to catch the mistakes and
actually watch the videos you're making?"

Teaching does not work here. For six weeks the output was never looked at
while every decision came from CSVs. When a published video was finally opened
it showed a melted AI marble bust with garbled pseudo-text, at 12.8% mean
luminance — a black rectangle on a phone. Both defects were invisible to every
metric collected and obvious within ten seconds of looking.

So the fix is mechanical: measure the file, write the frames to disk as
evidence, block the upload, and record the verdict in posts.csv so "was this
reviewed?" is answerable from the log.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import preflight  # noqa: E402


def _make(tmp_path, name, color, secs=3, text=None):
    """Render a tiny clip with ffmpeg so the checks run on real video."""
    out = tmp_path / name
    vf = f"color=c={color}:s=216x384:d={secs}"
    cmd = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", vf]
    if text:
        cmd += ["-vf", f"drawtext=text='{text}':fontcolor=white:fontsize=40:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2"]
    cmd += ["-frames:v", str(secs * 25), "-y", str(out)]
    subprocess.run(cmd, capture_output=True)
    return out


@pytest.fixture(scope="module")
def have_ffmpeg():
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode:
        pytest.skip("ffmpeg not available")


def test_a_too_dark_video_is_blocked(tmp_path, have_ffmpeg):
    """The exact defect that shipped for weeks."""
    v = _make(tmp_path, "dark.mp4", "0x0a0a12")
    res = preflight.review(v)
    assert res["verdict"] == "fail"
    assert any("too dark" in f for f in res["fails"])


def test_a_visible_video_passes(tmp_path, have_ffmpeg):
    v = _make(tmp_path, "ok.mp4", "gray", text="HELLO")
    res = preflight.review(v)
    assert "too dark" not in " ".join(res["fails"])


def test_a_flat_frame_is_caught_as_dead(tmp_path, have_ffmpeg):
    """A solid plate has no tonal range — black screen or frozen render."""
    v = _make(tmp_path, "flat.mp4", "gray")
    res = preflight.review(v)
    assert any("dead frame" in f for f in res["fails"]), res["fails"]


def test_the_dead_frame_check_can_actually_fire():
    """The first version parsed a stddev key ffmpeg never emits and defaulted
    to a pass — a check that could never fail, which is the exact class of bug
    this script exists to catch."""
    src = (ROOT / "scripts" / "preflight.py").read_text()
    assert "YSTD" not in src
    assert "MIN_RANGE" in src


def test_gold_text_counts_as_text():
    """#FFB830 has a luma near 180. A near-white cutoff reported a frame
    covered in gold caps as having no text at all."""
    src = (ROOT / "scripts" / "preflight.py").read_text()
    assert "gt(val,165)" in src


def test_frames_are_written_as_evidence(tmp_path, have_ffmpeg):
    """There must always be a record of what actually shipped."""
    v = _make(tmp_path, "e.mp4", "gray", text="X")
    out = tmp_path / "frames"
    res = preflight.review(v, out)
    assert res["frames"] and Path(res["frames"][0]).exists()


def test_a_missing_file_is_an_error_not_a_pass(tmp_path):
    res = preflight.review(tmp_path / "nope.mp4")
    assert res["verdict"] != "pass"


def test_the_verdict_is_recorded_in_the_log():
    """'Was this post reviewed?' must be answerable from posts.csv."""
    import logbook
    assert "reviewed" in logbook.FIELDS


def test_preflight_blocks_the_upload_in_the_pipeline():
    """A gate that reports but does not block is a reminder, and reminders are
    what failed."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "preflight_review(" in src
    assert 'pf["verdict"] == "fail"' in src
    # widened from 800 chars: the block grew when the last-attempt exemption
    # was removed, and the old window no longer reached upload_this
    assert "upload_this = False" in src.split("preflight_review(")[1][:2000]


def test_preflight_blocks_on_the_FINAL_attempt_too():
    """2026-09-02: the gate correctly failed a render, forced five retries,
    then published the failing video anyway — posts.csv recorded
    reviewed=fail against a live URL.

    The other QA gates fail OPEN on the last attempt, which was right at 3
    posts/day. At one post a day with quality as the whole strategy, shipping
    a video we KNOW is defective is worse than shipping nothing.
    """
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    blk = src.split("preflight_review(")[1][:1400]
    assert 'if pf["verdict"] == "fail":' in blk, "still exempts the last attempt"
    assert 'and not last_attempt' not in blk.split('if pf["verdict"]')[1][:80]


def test_a_failed_gate_does_not_fall_back_to_a_backup():
    """Backups are older renders of the same pipeline and carry the same
    defect — swapping one bad video for another is not a fix."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert 'if last_attempt and preflight_verdict == "fail":' in src
    i = src.index('if last_attempt and preflight_verdict == "fail":')
    j = src.index("if last_attempt:", i)
    assert "_load_backup" not in src[i:j]


def test_a_skipped_post_does_not_burn_the_story():
    """stories.pick() reads what was LOGGED, so an unpublished script runs
    again tomorrow rather than being silently lost."""
    import stories
    rows = [{"experiment": "story:serenus_not_ill"}]
    first = stories.pick(rows)
    assert stories.pick(rows)["id"] == first["id"]
