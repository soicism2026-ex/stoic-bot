"""
subprocess.run with a timeout that is always set.

WHY: on 2026-09-08, 09-09, 09-10 and 09-13 the channel published NOTHING. All
six scheduled runs on each of those days hit the 60-minute job cap and were
cancelled. The pattern is bimodal, not a slowdown — a healthy day's post takes
11-17 minutes, a failing day's runs all sit at exactly 60:00. That is a HANG.

The pipeline made 38 subprocess calls with no timeout. ffmpeg reading a stalled
network stream, or chewing a pathological input, waits forever; nothing below
the job cap ever interrupts it. One hung call costs the whole day.

Every external process now gets a deadline. A call that overruns raises
TimeoutExpired, which the caller can retry or fall back from — a loud, handled
failure instead of a silent hour.
"""
from __future__ import annotations

import os
import subprocess

# Generous enough for a full render (measured at 3-5 minutes), short enough
# that five attempts cannot approach the 60-minute job cap.
DEFAULT_TIMEOUT = float(os.environ.get("PROC_TIMEOUT", "420"))
# Probes and metadata reads should be near-instant; a slow one is a symptom.
PROBE_TIMEOUT = float(os.environ.get("PROC_PROBE_TIMEOUT", "90"))

_PROBES = ("ffprobe", "identify")


def run(cmd, **kwargs):
    """subprocess.run with a default timeout.

    Callers that genuinely need longer pass timeout= explicitly. Nothing gets
    to wait forever.
    """
    if "timeout" not in kwargs:
        exe = (cmd[0] if isinstance(cmd, (list, tuple)) and cmd else "")
        kwargs["timeout"] = (PROBE_TIMEOUT if any(p in str(exe) for p in _PROBES)
                             else DEFAULT_TIMEOUT)
    return subprocess.run(cmd, **kwargs)


# Re-export so `from proc import run, TimeoutExpired` reads naturally at the
# call sites that need to catch it.
TimeoutExpired = subprocess.TimeoutExpired
CalledProcessError = subprocess.CalledProcessError
PIPE = subprocess.PIPE
DEVNULL = subprocess.DEVNULL
