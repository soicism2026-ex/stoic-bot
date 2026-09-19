"""No run may reach the 60-minute GitHub job cap.

2026-09-05, 09-08, 09-09, 09-10, 09-13: the channel published NOTHING on five
of fifteen days. On each, all six scheduled runs sat at exactly 60:00 and were
cancelled. The signature is bimodal — a healthy post takes 11-17 minutes, a
failing day's runs all hit the cap exactly — which is a HANG, not a slowdown.

Cause: 38 subprocess calls in the pipeline with no timeout. ffmpeg on a stalled
network stream waits forever and nothing under the job cap interrupts it.

Two independent guards, because they fail differently:
  * per-process timeouts stop any SINGLE call hanging
  * a wall-clock budget stops retries ACCUMULATING past the cap
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import proc  # noqa: E402

PIPELINE = ["src/render.py", "src/backgrounds.py", "src/music.py",
            "src/imagegen.py", "src/tts.py", "scripts/preflight.py",
            "scripts/qa_check.py", "src/visual_qa.py"]


def test_no_pipeline_module_calls_subprocess_run_directly():
    """Every external process must carry a deadline. A bare subprocess.run can
    wait forever, and one that does costs the whole day's post."""
    offenders = []
    for f in PIPELINE:
        src = (ROOT / f).read_text()
        if "subprocess.run(" in src:
            offenders.append(f)
    assert offenders == [], f"unbounded subprocess.run in {offenders}"


def test_proc_run_injects_a_timeout_when_none_given():
    seen = {}
    real = subprocess.run

    def spy(cmd, **kw):
        seen.update(kw)
        return real([sys.executable, "-c", "pass"], capture_output=True)
    proc.subprocess.run = spy
    try:
        proc.run(["ffmpeg", "-i", "x"])
    finally:
        proc.subprocess.run = real
    assert seen.get("timeout") == proc.DEFAULT_TIMEOUT


def test_an_explicit_timeout_is_respected():
    seen = {}
    real = subprocess.run

    def spy(cmd, **kw):
        seen.update(kw)
        return real([sys.executable, "-c", "pass"], capture_output=True)
    proc.subprocess.run = spy
    try:
        proc.run(["ffmpeg"], timeout=12)
    finally:
        proc.subprocess.run = real
    assert seen["timeout"] == 12


def test_probes_get_a_shorter_leash():
    """A slow ffprobe is a symptom, not something to wait 7 minutes for."""
    seen = {}
    real = subprocess.run

    def spy(cmd, **kw):
        seen.update(kw)
        return real([sys.executable, "-c", "pass"], capture_output=True)
    proc.subprocess.run = spy
    try:
        proc.run(["ffprobe", "-i", "x"])
    finally:
        proc.subprocess.run = real
    assert seen["timeout"] == proc.PROBE_TIMEOUT
    assert proc.PROBE_TIMEOUT < proc.DEFAULT_TIMEOUT


def test_a_hanging_process_actually_raises():
    with pytest.raises(proc.TimeoutExpired):
        proc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)


def test_the_worst_case_run_still_fits_inside_the_job_cap():
    """The arithmetic that caused BOTH outages.

    The first version of this test multiplied MAX_ATTEMPTS by
    proc.DEFAULT_TIMEOUT — but renders do not use that timeout, so it was
    checking a number nothing obeyed. The real bound is the budget: an attempt
    may START with as little as 600s left, and then run a full render on top
    of it. Everything after that (QA, preflight, upload, logging) has to fit
    in what remains of the 60-minute cap."""
    import daily_post as dp
    worst = (dp.POST_BUDGET_SECONDS - 600) + proc.RENDER_TIMEOUT
    tail = 600  # QA + preflight + upload + thumbnail + comments + push
    assert worst + tail < 60 * 60, (
        f"{(worst + tail) / 60:.0f} min worst case against a 60 min cap")


def test_the_budget_makes_the_attempt_final_rather_than_abandoning_it():
    """Breaking out of the loop would publish NOTHING, which is the failure
    being fixed. The budget must mark the attempt final so the normal
    end-of-loop handling still runs."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "budget_spent = left < 600" in src
    assert "(attempt == MAX_ATTEMPTS) or budget_spent" in src
    block = src.split("budget_spent = left < 600")[1][:600]
    assert "break" not in block, "budget check abandons the run"


def test_the_budget_leaves_room_under_the_cap():
    import daily_post as dp
    assert dp.POST_BUDGET_SECONDS < 60 * 60
    assert 60 * 60 - dp.POST_BUDGET_SECONDS >= 600, \
        "needs a render's worth of headroom below the cap"


# ---------------------------------------------------------------------------
# The timeout that caused the outage it was written to prevent.
#
# PROC_TIMEOUT=420 was sized from a local benchmark run at
# REEL_X264_PRESET=ultrafast / REEL_CRF=30 — a PREVIEW encode. Production runs
# `-preset slower -crf 16`, which is an order of magnitude slower. Every
# scheduled run from 2026-09-18 01:07 onward died at exactly 420.0s inside the
# final ffmpeg call, and because that call was bare the exception escaped the
# retry loop and killed the run outright: no retry, no backup, nothing posted.
# ---------------------------------------------------------------------------

def test_the_main_encode_does_not_use_the_short_default():
    """The long call must ask for the long deadline explicitly."""
    src = (ROOT / "src" / "render.py").read_text()
    i = src.rindex("proc.run(cmd")
    call = src[i:i + 200]
    assert "timeout=proc.RENDER_TIMEOUT" in call, (
        "the main render must pass its own timeout, not inherit PROC_TIMEOUT")


def test_the_render_deadline_is_longer_than_the_default():
    import proc
    assert proc.RENDER_TIMEOUT > proc.DEFAULT_TIMEOUT


def test_the_render_deadline_still_fits_inside_the_post_budget():
    """Bounded, not unbounded. If one render could outlast the budget, the
    budget guard stops being what decides when to give up — the 60-minute job
    cap does, and that is the original five-day outage."""
    import proc
    sys.path.insert(0, str(ROOT / "scripts"))
    import daily_post
    assert proc.RENDER_TIMEOUT < daily_post.POST_BUDGET_SECONDS
    assert proc.RENDER_TIMEOUT < 3600, "must stay under the GitHub job cap"


def test_a_render_crash_is_an_attempt_failure_not_a_run_failure():
    """The loop calls itself self-healing; it only ever healed QA failures."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    loop = src[src.index("for attempt in range(1, MAX_ATTEMPTS + 1):"):]
    call = loop.index("_render_with_env(")
    assert "try:" in loop[:call], "the render call must be guarded"
    handler = loop[call:call + 1200]
    assert "except Exception" in handler
    assert "render_error" in handler


def test_a_failed_render_retries_before_giving_up():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    blk = src[src.index("if render_error:"):]
    blk = blk[:blk.index("else:")]
    assert "continue" in blk, "a non-final failure must retry"
    assert "_apply_corrections" in blk, "and retry with corrections"


def test_a_final_failed_render_reaches_the_backup_bank():
    """Falling through with upload_this=False is what hands the day over."""
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    blk = src[src.index("if render_error:"):]
    blk = blk[:blk.index("else:")]
    assert "upload_this = False" in blk
    statements = [ln.strip() for ln in blk.splitlines()
                  if ln.strip() and not ln.strip().startswith("#")]
    assert not any(st == "return" or st.startswith("return ")
                   for st in statements), \
        "must not abandon the run with nothing posted"


def test_the_encode_leaves_room_for_the_retries_it_promises():
    """MEASURED at production settings 2026-09-19: `slower`/crf16 renders this
    graph in 747.5s. Against a 2100s budget that is TWO attempts, not five —
    the self-healing loop was quietly a third of its advertised size, and the
    encode ran right up against its deadline. `medium`/crf18 is 237.4s.

    This test fails if the preset is ever raised back without also raising the
    budget: it asserts the default encode is cheap enough that the loop can
    actually use the attempts it is configured for."""
    import daily_post as dp
    import render
    # Cost of one render at each preset, seconds, measured on the real graph.
    MEASURED = {"slower": 747.5, "medium": 237.4, "fast": 181.6,
                "ultrafast": 145.0}
    cost = MEASURED.get(render.X264_PRESET)
    assert cost is not None, (
        f"preset {render.X264_PRESET!r} has never been benchmarked — measure "
        "it at production settings before shipping it")
    attempts_that_fit = int(dp.POST_BUDGET_SECONDS // cost)
    assert attempts_that_fit >= 5, (
        f"{render.X264_PRESET}/crf{render.X264_CRF} at {cost}s fits only "
        f"{attempts_that_fit} of {dp.MAX_ATTEMPTS} attempts in the budget")
    assert cost < proc.RENDER_TIMEOUT / 2, (
        "less than 2x headroom on the render deadline is how 2026-09-18 "
        "happened")
