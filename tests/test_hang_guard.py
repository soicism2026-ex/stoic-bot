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


def test_five_attempts_cannot_reach_the_job_cap():
    """The arithmetic that caused the outage: attempts x per-call timeout must
    stay under 60 minutes."""
    import daily_post as dp
    worst = dp.MAX_ATTEMPTS * proc.DEFAULT_TIMEOUT
    assert worst < 60 * 60, f"{worst / 60:.0f} min of renders fits inside a 60 min cap"


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
