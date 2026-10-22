"""
Listen-check: hear the narration before it airs.

Owner, 2026-10-21 (in the HQ): ElevenLabs "voice, plus a listen-check on every
video". Text-to-speech sometimes drops a word, stutters, or garbles a phrase,
and nothing in the pipeline ever listened: QA looks at frames and loudness,
never at whether the words were said. ElevenLabs Scribe now transcribes the
narration (voice only, before music is mixed in) and the transcript is
compared with the script.

    r = check(audio_path, script)
    r.ok is True   -> the narration says the script
    r.ok is False  -> words were dropped or garbled (r.reason says which)
    r.ok is None   -> the check could not run (no key, API error): the caller
                      fails OPEN, because a listening outage must never stop
                      the channel

The comparison forgives what a listener's spelling changes but a viewer never
hears (case, punctuation, a name split in two, near-miss spellings) and
fails on what a viewer does hear: two or more script words in a row missing (a
skipped phrase), overall recall under MIN_RECALL, or MAX_EXTRAS or more extra
words (a stutter or a hallucinated phrase).
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests

STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MIN_RECALL = 0.90
MAX_GAP = 2        # this many consecutive missing script words fails
MAX_EXTRAS = 3     # this many words the script never had fails
WORD_SIM = 0.75    # one word heard as a near-miss spelling still counts
SEGMENT_SIM = 0.80  # a run heard split or merged ("epic titus") still counts


@dataclass
class Result:
    ok: bool | None
    recall: float = 0.0
    longest_gap: int = 0
    extras: int = 0
    heard: str = ""
    missing: list = field(default_factory=list)
    reason: str = ""

    def summary(self) -> str:
        if self.ok is None:
            return f"skipped ({self.reason})"
        verdict = "PASS" if self.ok else "FAIL"
        gist = f"recall {self.recall:.2f}, longest gap {self.longest_gap}, extra words {self.extras}"
        return f"{verdict}: {gist}" + (f" ({self.reason})" if self.reason else "")


def words(text: str) -> list[str]:
    t = (text or "").lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return [w.strip("'") for w in t.split() if w.strip("'")]


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def compare(script: str, heard: str) -> Result:
    """Align what was heard with what was meant, word by word."""
    exp, got = words(script), words(heard)
    if not exp:
        return Result(ok=None, reason="empty script")
    missing_flags = [False] * len(exp)
    extras = 0
    ops = difflib.SequenceMatcher(None, exp, got, autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        if tag == "delete":
            for i in range(i1, i2):
                missing_flags[i] = True
            continue
        if tag == "insert":
            extras += j2 - j1
            continue
        # replace: forgive a run heard split, merged or misspelled
        if _sim("".join(exp[i1:i2]), "".join(got[j1:j2])) >= SEGMENT_SIM:
            continue
        pool = list(got[j1:j2])
        lost = 0
        for i in range(i1, i2):
            best = max(pool, key=lambda w: _sim(exp[i], w), default=None)
            if best is not None and _sim(exp[i], best) >= WORD_SIM:
                pool.remove(best)
            else:
                missing_flags[i] = True
                lost += 1
        # heard words left over beyond the ones that replaced lost words
        extras += max(0, len(pool) - lost)
    longest = run = 0
    for m in missing_flags:
        run = run + 1 if m else 0
        longest = max(longest, run)
    recall = 1 - sum(missing_flags) / len(exp)
    missing = [w for w, m in zip(exp, missing_flags) if m]
    reasons = []
    if longest >= MAX_GAP:
        reasons.append(f"{longest} words in a row not heard")
    if recall < MIN_RECALL:
        reasons.append(f"only {recall:.0%} of the script heard")
    if extras >= MAX_EXTRAS:
        reasons.append(f"{extras} words the script never had")
    if missing:
        reasons.append("missing: " + " ".join(missing[:8]))
    ok = longest < MAX_GAP and recall >= MIN_RECALL and extras < MAX_EXTRAS
    return Result(ok=ok, recall=recall, longest_gap=longest, extras=extras,
                  heard=heard, missing=missing, reason="; ".join(reasons))


def transcribe(audio_path: Path, key: str | None = None, timeout: int = 90) -> str:
    """The narration as ElevenLabs Scribe heard it. Raises on any failure."""
    key = (key if key is not None else os.environ.get("ELEVENLABS_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("no ELEVENLABS_API_KEY")
    with open(audio_path, "rb") as f:
        resp = requests.post(
            STT_URL, headers={"xi-api-key": key},
            data={"model_id": os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2"),
                  "language_code": "en", "tag_audio_events": "false",
                  "timestamps_granularity": "none"},
            files={"file": (Path(audio_path).name, f, "audio/mpeg")},
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return (resp.json() or {}).get("text") or ""


def enabled() -> bool:
    return os.environ.get("LISTEN_CHECK", "1") not in ("0", "false", "False")


def check(audio_path: Path, script: str) -> Result:
    """Transcribe and compare. Never raises: a failure to listen is ok=None."""
    if not enabled():
        return Result(ok=None, reason="switched off (LISTEN_CHECK=0)")
    try:
        heard = transcribe(audio_path)
    except Exception as e:  # noqa: BLE001
        return Result(ok=None, reason=f"could not listen: {str(e)[:160]}")
    return compare(script, heard)
