"""
Generated MOTION backgrounds via the Higgsfield REST API (Kling 3.0 Standard).

WHY THIS EXISTS: the owner, on the stock-footage version of the story format —
"It's just a video of waves of water. I don't want it to be like that. I want
it to be an actual story from their description" — and then, plainly: "I mean
like actual animated videos that relate exactly to what we're talking about
not just a still video of water and then switching to different backgrounds."

Stock search cannot do that. `imagegen.py` gets closer (a still that depicts
the exact beat) but animates it with a Ken Burns push, so the frame still has
no life in it. Kling generates the beat as MOVING FOOTAGE.

NOT THE MCP CONNECTOR. Higgsfield's MCP connector lives in a chat session and
cannot be reached from a GitHub Actions runner; its trial credits are explicit
that they "exist only in the MCP". This module talks to the REST API at
api.higgsfield.ai with a server-side key, which a runner CAN hold.

DESIGN — safe by default, in the same shape as imagegen.py:
  * OFF unless REEL_KLING_BG=1 AND HIGGSFIELD_API_KEY is set.
  * Every failure returns None and the caller falls through to the normal
    generated -> stock -> synthetic chain. It can NEVER break a render.
  * Every network call has a timeout and the whole beat has a deadline. The
    five-day outage (see src/proc.py) was unbounded external calls; a video
    model that queues for minutes is exactly that hazard.
  * A hard per-run generation cap, because pricing for this model is NOT
    published and a loop bug must not be able to bill the owner repeatedly.

ONE REQUEST PER NARRATION BEAT, NOT PER SLOT. daily_post now asks for the same
beat query in several consecutive slots (see background_flavors: three angles
on one beat, ~4.4s each). Generating each slot separately would be three
requests for what Kling can return in one: `multi_prompt` takes up to 6
sub-shots with their own durations, and `multi_shots` cuts between them. So the
first slot of a beat generates ONE multi-shot master and the following slots
are served free from it by cutting the next segment out.

Cost: Higgsfield does not publish pricing for
`kling-video/v3.0/std/text-to-video`; check the console before enabling. What
this module controls is the REQUEST COUNT, and that is one per beat — four per
video at the current shot list, not twelve.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

import proc

ENDPOINT = os.environ.get(
    "KLING_ENDPOINT",
    "https://api.higgsfield.ai/kling-video/v3.0/std/text-to-video",
)

# Shots per generated master, and seconds per shot. 3 x 5s = a 15s master,
# which is the model's maximum duration and covers three ~4.4s slots with room
# to spare. Both are env-tunable so the shot list and the master stay in step.
SHOTS_PER_BEAT = int(os.environ.get("KLING_SHOTS_PER_BEAT", "3"))
SECONDS_PER_SHOT = int(os.environ.get("KLING_SECONDS_PER_SHOT", "5"))

# Spend guard. Pricing is not published, so the number of REQUESTS is the thing
# under our control. Four beats per video is the current shot list; anything
# past this ceiling in one process is a bug, not a longer story.
MAX_BEATS_PER_RUN = int(os.environ.get("KLING_MAX_BEATS_PER_RUN", "4"))

# Deadlines. A queued video generation can take minutes; it must never take
# forever. SUBMIT/POLL are per-HTTP-call, BEAT bounds the whole wait.
SUBMIT_TIMEOUT = float(os.environ.get("KLING_SUBMIT_TIMEOUT", "60"))
POLL_TIMEOUT = float(os.environ.get("KLING_POLL_TIMEOUT", "30"))
DOWNLOAD_TIMEOUT = float(os.environ.get("KLING_DOWNLOAD_TIMEOUT", "180"))
BEAT_DEADLINE = float(os.environ.get("KLING_BEAT_DEADLINE", "420"))
POLL_EVERY = float(os.environ.get("KLING_POLL_EVERY", "6"))

CFG_SCALE = float(os.environ.get("KLING_CFG_SCALE", "0.5"))

W, H = 1080, 1920

# Appended to every sub-shot. Mirrors imagegen.STYLE deliberately so generated
# stills and generated motion share ONE look, and carries the same hard-won
# rules: name a physical light source rather than a lighting style (diffusion
# text encoders have no reliable "not"), and ask for controlled midtones
# because render.py darkens on top of whatever arrives.
STYLE = os.environ.get(
    "KLING_STYLE",
    "cinematic film still in motion, lit by a single warm candle flame just "
    "out of frame, honey and amber tones on the lit side, soft neutral "
    "grey-blue shade on the unlit side, detail retained in the shadows, "
    "controlled midtones, shallow depth of field, subtle volumetric haze, "
    "photorealistic, shot on 35mm film, muted restrained palette, slow "
    "deliberate camera movement, no text, no watermark, no people speaking "
    "to camera",
)

# query -> (master clip path, how many segments have been handed out)
_MASTERS: dict[str, list] = {}
_BEATS_GENERATED = 0


def enabled() -> bool:
    """True only when explicitly switched on AND a key is present."""
    on = os.environ.get("REEL_KLING_BG", "0") not in ("0", "false", "False")
    return bool(on and api_key())


def api_key() -> str:
    """The server-side credential, as KEY_ID:KEY_SECRET.

    Returns "" rather than raising, because every caller treats a missing key
    as "this source is off" and falls through.
    """
    key = (os.environ.get("HIGGSFIELD_API_KEY")
           or os.environ.get("HF_KEY") or "").strip()
    # The API wants KEY_ID:KEY_SECRET. A half-pasted key would otherwise fail
    # as an opaque 401 in the middle of a render.
    if key and ":" not in key:
        print("[kling] HIGGSFIELD_API_KEY is not in KEY_ID:KEY_SECRET form "
              "— ignoring it", file=sys.stderr, flush=True)
        return ""
    return key


def _headers() -> dict:
    return {"Authorization": f"Key {api_key()}",
            "Content-Type": "application/json"}


def _payload(query: str) -> dict:
    """One multi-shot request covering a whole narration beat.

    The sub-prompts are three ANGLES on the same beat, not three different
    beats — doctrine section 6 says the picture follows the script's own image,
    and section 7 says a beat gets several shots rather than one long hold.
    """
    angles = [
        f"{query}. Wide establishing shot, still air. {STYLE}",
        f"{query}. Slow push in on the single most specific detail. {STYLE}",
        f"{query}. Close, shallow focus, the smallest movement in frame. {STYLE}",
    ][:SHOTS_PER_BEAT]
    while len(angles) < SHOTS_PER_BEAT:            # if someone raises the count
        angles.append(f"{query}. Another angle, same moment. {STYLE}")
    return {
        "prompt": f"{query}. {STYLE}",
        # Sound OFF: this channel mixes its own voiceover and score, and a
        # generated audio bed underneath them is noise we would have to strip.
        "sound": "off",
        "aspect_ratio": "9:16",
        "duration": SHOTS_PER_BEAT * SECONDS_PER_SHOT,
        "cfg_scale": CFG_SCALE,
        "multi_shots": True,
        # maxLength 512 per the model schema — truncate rather than 422.
        "multi_prompt": [{"prompt": a[:512], "duration": SECONDS_PER_SHOT}
                         for a in angles],
    }


def _submit(payload: dict) -> dict:
    r = requests.post(ENDPOINT, json=payload, headers=_headers(),
                      timeout=SUBMIT_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _poll(status_url: str, deadline: float) -> dict:
    """Poll until terminal or deadline. Returns the completed status dict."""
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("kling generation exceeded KLING_BEAT_DEADLINE")
        r = requests.get(status_url, headers=_headers(), timeout=POLL_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        status = (data.get("status") or "").lower()
        if status == "completed":
            return data
        if status in ("failed", "nsfw", "canceled"):
            raise RuntimeError(
                f"kling generation {status}: {data.get('error', '')}")
        time.sleep(POLL_EVERY)


def _download(url: str, out_path: Path) -> Path:
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
        r.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("kling download produced no usable file")
    return out_path


def _cut(master: Path, index: int, out_path: Path) -> Path:
    """Cut segment `index` out of the multi-shot master and normalise it.

    Normalising here (1080x1920, no audio) keeps the file interchangeable with
    a stock clip, so nothing downstream has to know where it came from.
    """
    start = index * SECONDS_PER_SHOT
    proc.run([
        "ffmpeg", "-y", "-ss", str(start), "-t", str(SECONDS_PER_SHOT),
        "-i", str(master),
        "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1"),
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", str(out_path),
    ], check=True, capture_output=True)
    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("kling segment cut produced no usable file")
    return out_path


def _generate_master(query: str, work_dir: Path) -> Path:
    """One API round trip: submit, wait, download the multi-shot master."""
    global _BEATS_GENERATED
    if _BEATS_GENERATED >= MAX_BEATS_PER_RUN:
        raise RuntimeError(
            f"kling beat cap reached ({MAX_BEATS_PER_RUN}) — refusing to "
            "generate more in one run")
    deadline = time.monotonic() + BEAT_DEADLINE
    sub = _submit(_payload(query))
    status = (sub.get("status") or "").lower()
    if status == "completed":
        data = sub
    else:
        status_url = sub.get("status_url")
        if not status_url:
            rid = sub.get("request_id")
            if not rid:
                raise RuntimeError(f"kling submit returned no handle: {sub}")
            status_url = f"{ENDPOINT.rsplit('/', 3)[0]}/requests/{rid}"
        data = _poll(status_url, deadline)
    url = (data.get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"kling completed with no video url: {data}")
    _BEATS_GENERATED += 1
    master = work_dir / f"kling_master_{abs(hash(query)) % 10**8}.mp4"
    return _download(url, master)


def fetch_clip(query: str, out_path: Path) -> Path | None:
    """Return one ~SECONDS_PER_SHOT clip for this beat, or None.

    The FIRST call for a query generates the multi-shot master; later calls for
    the same query are served from it for free, which is what keeps this at one
    request per narration beat instead of one per slot.

    Returns None on absolutely any problem — the caller falls back to stock.
    """
    if not enabled():
        return None
    out_path = Path(out_path)
    try:
        entry = _MASTERS.get(query)
        if entry is None:
            master = _generate_master(query, out_path.parent)
            entry = [master, 0]
            _MASTERS[query] = entry
        master, used = entry
        if used >= SHOTS_PER_BEAT:
            # Every angle in this master has been handed out. Reuse them in
            # order rather than paying for another generation.
            used = 0
        clip = _cut(master, used, out_path)
        entry[1] = used + 1
        return clip
    except Exception as e:  # noqa: BLE001
        print(f"[kling] skipped: {e}", file=sys.stderr, flush=True)
        return None


def reset() -> None:
    """Clear the per-run master cache and spend counter (tests, and any
    long-lived process that renders more than one video)."""
    global _BEATS_GENERATED
    _MASTERS.clear()
    _BEATS_GENERATED = 0
