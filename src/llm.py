"""
One place that decides whether a paid language-model call may be made.

OWNER DECISION 2026-09-18: "i dont want to pay for the separate claude api
anymore and i just want to use higgfield." So the pipeline must run to
completion with no `ANTHROPIC_API_KEY` at all — not crash, not fabricate, and
not fail open in a way that looks like a real result.

Before this module, six call sites each invented their own behaviour when the
key was missing or out of credit, and one of them recorded a fabricated
`pacing=5.0` into QA_LOG.md for 51 runs. The rule is now single and explicit:

    ASK `available()` FIRST. If it says no, SKIP and SAY SO.
    Never call and catch. Never substitute a made-up value for a missing one.

`LLM_DISABLED=1` forces off even when a key is present, so the no-API path can
be exercised deliberately — in tests, and by the owner, without deleting the
secret from GitHub.

WHAT HIGGSFIELD DOES NOT REPLACE: it generates pictures, video and voice. It
does not write Stoic scripts and it cannot verify a quote against a
public-domain translation. The channel's words come from `data/stories.json`,
which is hand-written and human-approved by design (see src/stories.py), so
dropping the API costs the channel a *generator*, not its content.
"""
from __future__ import annotations

import os

# Features that call a language model, and what the channel loses without one.
# Used for the honest one-line skip notices, so a silent run is never mistaken
# for a working one.
FEATURES = {
    "content": "generated posts (the hand-written story bank is unaffected)",
    "visual_qa": "the reviewer that watches each render",
    "qa_vision": "the vision half of the QA check (ffmpeg checks still run)",
    "replies": "auto-replies to viewer comments",
    "strategy": "the daily strategy rewrite",
}


def disabled_by_config() -> bool:
    return os.environ.get("LLM_DISABLED", "0") not in ("0", "false", "False")


def key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def available() -> bool:
    """True only when a call may actually be attempted."""
    return bool(key()) and not disabled_by_config()


def reason() -> str:
    """Why calls are off, in words fit for a log line."""
    if disabled_by_config():
        return "LLM_DISABLED=1"
    if not key():
        return "no ANTHROPIC_API_KEY"
    return ""


def skip_note(feature: str) -> str:
    """The standard one-line notice. Every caller prints the same shape, so
    `grep '\\[llm\\]'` in a workflow log shows everything that was skipped."""
    lost = FEATURES.get(feature, feature)
    return f"  [llm] {feature} skipped ({reason()}) — {lost}"
