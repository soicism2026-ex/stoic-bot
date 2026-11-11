"""
Longinus in the pipeline: every painted shot is looked at before it airs.

Owner, in the HQ, 2026-11-11, minutes after switching to the new look: "New
look is better but the generated images sometimes look off continuously
improve the shorts utilizing the agents specific tasks".

The free image model (FLUX.2 [klein], src/imagegen.py) sometimes paints a
defect a viewer notices in a second. The design lab's first real renders
(2026-11-11) had a boulder that read as a giant stone head, hands and a robe
growing out of a rock, and a wine cup with a candle burning inside it. The
painter's prompt rules now prevent those three; this catches the next kind.

judge(still, scene) shows the still to a free vision model on Cloudflare
Workers AI (Llama 4 Scout, natively multimodal: about 60 neurons a look,
inside the 10,000/day free allowance the paintings share) and asks for clear
defects only: broken anatomy, a face or body hidden in an object, two objects
fused into one, writing, modern objects, the same person twice. The painter
(painter.painted_still) repaints a failed shot with a new seed, up to
REEL_INSPECT_RETRIES times, and airs the first version that passes (else the
one with the fewest problems).

Each verdict is saved next to the still (<still>.inspect.json, keyed by the
inspector's VERSION), so a still is judged once and the live post repeats the
rehearsal's choices exactly. Anything that stops it looking (no key, a
timeout, a reply it can't read, REEL_INSPECT=0) passes the still: the
inspector can only make a Short better, never cost a post.
Tests: tests/test_inspector.py.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import requests

MODEL = os.environ.get("REEL_INSPECT_MODEL", "@cf/meta/llama-4-scout-17b-16e-instruct")
VERSION = "1"            # bump when the question changes: every still is judged again
TIMEOUT = 60
# Llama 4 Scout on Workers AI: 24,545 neurons per million input tokens, 77,273
# per million output tokens (developers.cloudflare.com, 2026-11-11). A look is
# ~2,000 input tokens (a 512 px still + the question) and ~100 output.
NEURONS_IN, NEURONS_OUT = 24_545 / 1e6, 77_273 / 1e6
EST_NEURONS = 2_000 * NEURONS_IN + 120 * NEURONS_OUT

QUESTION = """You are the last check before this painted still airs in a short video set in ancient Rome or Greece. It was painted from this description: "{scene}"

Report only CLEAR defects that an ordinary viewer would notice within a second:
1. broken anatomy: extra, missing or fused fingers, extra hands or limbs, a twisted or melted face, a body part growing out of an object;
2. a hidden figure: a face, head, hand or body formed inside a rock, cloud, wall, tree, water or object where no person belongs;
3. fused objects: two things merged into one impossible object (for example a cup with a candle burning inside it, a lamp melted into a hand);
4. writing: any letters, words, numbers, signs or watermark;
5. modern objects: glass lanterns, electric or string lights, eyeglasses, clocks, plastic, modern clothing, vehicles;
6. the same person shown twice in one picture.
Ignore style, mood, small imperfections and anything you are unsure about.

Answer with one line of JSON and nothing else: {{"ok": true, "defects": []}} or {{"ok": false, "defects": ["short description of each clear defect"]}}"""


@dataclass
class Verdict:
    ok: bool | None                  # None = could not look (the still passes)
    problems: list[str] = field(default_factory=list)
    neurons: float = 0.0
    cached: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {"ok": self.ok, "problems": list(self.problems), "neurons": round(self.neurons, 1),
                "cached": self.cached, "note": self.note}


def enabled() -> bool:
    return os.environ.get("REEL_INSPECT", "1").strip().lower() not in ("0", "false", "off", "no")


def _keys() -> tuple[str, str]:
    return (os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(),
            os.environ.get("CLOUDFLARE_API_TOKEN", "").strip())


def _verdict_path(still: Path) -> Path:
    return still.with_name(still.name + ".inspect.json")


def _read_cached(still: Path) -> Verdict | None:
    p = _verdict_path(still)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if d.get("version") != VERSION or d.get("model") != MODEL:
        return None
    ok = d.get("ok")
    return Verdict(ok if isinstance(ok, bool) else None, [str(x) for x in d.get("problems") or []],
                   0.0, True, "")


def _write_cached(still: Path, v: Verdict) -> None:
    if v.ok is None:                     # a failure to look is never remembered
        return
    try:
        _verdict_path(still).write_text(json.dumps(
            {"version": VERSION, "model": MODEL, "ok": v.ok, "problems": v.problems}), encoding="utf-8")
    except OSError:
        pass


def _jpeg_b64(still: Path) -> str:
    """The still at 512 px wide as base64 JPEG (fewer tokens, same defects)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "look.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(still), "-vf", "scale=512:-2",
                        "-q:v", "4", "-frames:v", "1", str(out)], check=True, timeout=60)
        return base64.b64encode(out.read_bytes()).decode("ascii")


def parse(text: str) -> tuple[bool | None, list[str]]:
    """(ok, defects) from the model's reply; (None, []) when it can't be read."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None, []
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None, []
    ok = d.get("ok")
    defects = [str(x).strip() for x in (d.get("defects") or []) if str(x).strip()]
    if not isinstance(ok, bool):
        return None, []
    if ok and defects:                   # contradictory: trust the listed defects
        ok = False
    if not ok and not defects:           # "not ok" with nothing named is not actionable
        return True, []
    return ok, defects[:6]


def _reply_text(payload) -> tuple[str, dict]:
    result = (payload or {}).get("result") or {}
    if isinstance(result, dict):
        text = result.get("response")
        if not isinstance(text, str):
            choices = result.get("choices") or [{}]
            text = ((choices[0] or {}).get("message") or {}).get("content") or ""
        return str(text), result.get("usage") or {}
    return "", {}


def judge(still: Path, scene: str = "") -> Verdict:
    """The verdict on one painted still. Never raises."""
    still = Path(still)
    if not enabled():
        return Verdict(None, note="off (REEL_INSPECT=0)")
    hit = _read_cached(still)
    if hit is not None:
        return hit
    acct, tok = _keys()
    if not (acct and tok):
        return Verdict(None, note="no Cloudflare key")
    try:
        b64 = _jpeg_b64(still)
        body = {"messages": [{"role": "user", "content": [
                    {"type": "text", "text": QUESTION.format(scene=(scene or "a scene from antiquity")[:400])},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
                "max_tokens": 160, "temperature": 0}
        r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{MODEL}",
                          headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=TIMEOUT)
        try:
            payload = r.json()
        except ValueError:
            payload = None
        if r.status_code >= 400 or not isinstance(payload, dict) or payload.get("success") is False:
            errs = (payload or {}).get("errors") if isinstance(payload, dict) else None
            return Verdict(None, note=f"HTTP {r.status_code} {str(errs or '')[:120]}".strip())
        text, usage = _reply_text(payload)
        ok, defects = parse(text)
        neurons = EST_NEURONS
        if usage.get("prompt_tokens") or usage.get("completion_tokens"):
            neurons = (float(usage.get("prompt_tokens") or 0) * NEURONS_IN
                       + float(usage.get("completion_tokens") or 0) * NEURONS_OUT)
        v = Verdict(ok, defects, neurons, False, "" if ok is not None else f"unreadable reply: {text[:80]!r}")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if tok:
            msg = msg.replace(tok, "<token>")
        if acct:
            msg = msg.replace(acct, "<account>")
        return Verdict(None, note=f"{type(e).__name__}: {msg[:120]}")
    _write_cached(still, v)
    return v


if __name__ == "__main__":       # python3 src/inspector.py STILL "scene"  (a manual look)
    print(json.dumps(judge(Path(sys.argv[1]), " ".join(sys.argv[2:])).as_dict()))
