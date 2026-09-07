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


# ------------------------------------------------- cost of the gate itself
#
# 2026-09-05: SIX consecutive runs were cancelled at the 60-minute job cap and
# the channel published nothing that day. The pipeline step had gone from ~12
# minutes to ~38. Cause was this gate: it ran a separate ffmpeg seek-and-decode
# for every sampled timestamp — six for luminance, six for the contact sheet,
# two for the text measurement — about fourteen decodes per render attempt,
# multiplied by up to five attempts.
#
# A quality gate that costs the channel a day of posting is not a quality gate.

FFMPEG_SAMPLE = """
[Parsed_metadata_2 @ 0x1] pts_time:0.1
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMIN=9
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YAVG=41.9
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMAX=192
[Parsed_metadata_2 @ 0x1] pts_time:6.1
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMIN=4
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YAVG=25.6
[Parsed_metadata_2 @ 0x1] lavfi.signalstats.YMAX=33
"""


def test_one_decode_pass_not_one_per_sample():
    """The whole fix. fps=1/N walks the file once and emits every sample."""
    src = (ROOT / "scripts" / "preflight.py").read_text()
    assert "fps=1/" in src, "no single-pass sampling"
    assert "-ss" not in src.split("def _scan")[1].split("def ")[0], \
        "still seeking per sample inside the scan"


def test_scan_parses_every_sample_from_one_stderr(monkeypatch):
    import subprocess as sp

    class R:
        stderr = FFMPEG_SAMPLE
    monkeypatch.setattr(sp, "run", lambda *a, **k: R())
    samples = preflight._scan(Path("x.mp4"), None)
    assert len(samples) == 2
    assert samples[0]["luma"] == 41.9
    assert samples[1]["range"] == 33 - 4


def test_a_broken_scanner_WARNS_rather_than_blocking(monkeypatch, tmp_path):
    """The gate blocks posts. If it cannot measure, it must not conclude the
    video is bad — that would silently stop the channel, which is exactly the
    failure being fixed here."""
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    monkeypatch.setattr(preflight, "_scan", lambda *a, **k: [])
    res = preflight.review(v)
    assert res["verdict"] == "warn"
    assert res["fails"] == []


def test_sample_interval_is_tunable():
    """So the cost can be lowered further without a code change if a run ever
    approaches the job cap again."""
    src = (ROOT / "scripts" / "preflight.py").read_text()
    assert "PREFLIGHT_SAMPLE_EVERY" in src
