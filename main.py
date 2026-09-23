"""
Higgsfield SDK example — Seedance 2.5 text-to-video.

    pip install -r requirements.txt
    # .env.local (git-ignored):  HF_KEY=YOUR_KEY_ID:YOUR_KEY_SECRET
    python main.py

Submits one generation with the official SDK's `subscribe`, waits for it to
finish, and prints the video URL. THIS IS A BILLABLE REQUEST.

Two things about the SDK (higgsfield-client 0.2.0, read from its source) shape
this file:

  * `subscribe()` does NOT raise when a generation fails, is canceled, or is
    moderated. It returns the final JSON with `status` set to "failed",
    "canceled" or "nsfw". Printing `result["video"]["url"]` blindly would
    report a moderated request as a success, so every terminal status is
    checked explicitly and only "completed" with a URL counts.
  * `subscribe()` polls in an unbounded loop. Each HTTP call has a timeout, but
    the wait as a whole does not. This project has lost days to unbounded
    waits, so the example stops after HF_MAX_WAIT seconds and tries to cancel.

The credential is loaded at runtime and never printed. Any error text is
scrubbed of it before it reaches the terminal.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import higgsfield_client
from dotenv import load_dotenv

MODEL = "bytedance/seedance-2.5/text-to-video"
ARGUMENTS = {
    "prompt": "A cinematic scene at sunset",
    "duration": 5,
    "resolution": "720p",
    "aspect_ratio": "16:9",
}
# Generous for a 5s 720p clip, but finite.
MAX_WAIT_SECONDS = float(os.environ.get("HF_MAX_WAIT", "900"))

ENV_FILE = Path(__file__).resolve().with_name(".env.local")


class _DeadlineExceeded(Exception):
    pass


def _secret_values() -> list[str]:
    """Every credential value currently in the environment, so error text can
    be scrubbed of it. Includes each half of KEY_ID:KEY_SECRET."""
    found = []
    for name in ("HF_KEY", "HF_API_KEY", "HF_API_SECRET"):
        value = os.environ.get(name) or ""
        if value:
            found.append(value)
            found.extend(part for part in value.split(":") if len(part) >= 6)
    return sorted(set(found), key=len, reverse=True)


def redact(text: object) -> str:
    out = str(text)
    for value in _secret_values():
        out = out.replace(value, "***")
    return out


def credentials_problem() -> str | None:
    """None when usable credentials are present, else what is wrong.
    Never includes the value."""
    key = (os.environ.get("HF_KEY") or "").strip()
    if key:
        if ":" not in key:
            return "HF_KEY is set but is not in KEY_ID:KEY_SECRET form."
        return None
    if os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET"):
        return None
    return (f"HF_KEY is not set. Add HF_KEY=KEY_ID:KEY_SECRET to "
            f"{ENV_FILE.name} (git-ignored) or to the environment.")


def video_url(result: dict) -> str | None:
    """The completed video's URL, per Higgsfield's shared request-status schema
    (`video.url`). None if the response carries no URL."""
    video = result.get("video")
    if isinstance(video, dict) and isinstance(video.get("url"), str):
        return video["url"] or None
    return None


def main() -> int:
    # override=False: a real environment variable (CI secret, cloud env config)
    # wins over the file.
    load_dotenv(ENV_FILE, override=False)

    problem = credentials_problem()
    if problem:
        print(f"NOT RUN: {problem}", file=sys.stderr)
        return 2

    started = time.monotonic()
    request_id: str | None = None
    last_status: str | None = None

    def on_enqueue(rid: str) -> None:
        nonlocal request_id
        request_id = rid
        print(f"submitted  request_id={rid}  model={MODEL}")

    def on_queue_update(status) -> None:
        nonlocal last_status
        name = type(status).__name__
        if name != last_status:
            print(f"status     {name:<11} {time.monotonic() - started:5.0f}s")
            last_status = name
        if time.monotonic() - started > MAX_WAIT_SECONDS:
            raise _DeadlineExceeded()

    try:
        result = higgsfield_client.subscribe(
            MODEL,
            arguments=ARGUMENTS,
            on_enqueue=on_enqueue,
            on_queue_update=on_queue_update,
        )
    except _DeadlineExceeded:
        print(f"FAILED: no result after {MAX_WAIT_SECONDS:.0f}s.", file=sys.stderr)
        if request_id:
            try:
                higgsfield_client.cancel(request_id)
                print(f"cancel requested for {request_id}. A job that has "
                      "already started cannot be canceled and may still "
                      "complete and bill.", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"cancel failed: {redact(e)}", file=sys.stderr)
        return 1
    except higgsfield_client.CredentialsMissedError as e:
        print(f"NOT RUN: {redact(e)}", file=sys.stderr)
        return 2
    except higgsfield_client.HiggsfieldClientError as e:
        print(f"FAILED: API error: {redact(e)}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001  network, DNS, proxy, bad JSON
        print(f"FAILED: {type(e).__name__}: {redact(e)}", file=sys.stderr)
        return 1

    status = str(result.get("status", "")).lower()
    rid = result.get("request_id") or request_id

    if status == "completed":
        url = video_url(result)
        if url:
            print(f"completed  {time.monotonic() - started:5.0f}s")
            print(f"video_url  {url}")
            return 0
        print(f"FAILED: request {rid} reported completed but returned no "
              "video URL.", file=sys.stderr)
        return 1
    if status == "nsfw":
        print(f"FAILED: request {rid} was blocked by moderation (nsfw). "
              "No video was produced.", file=sys.stderr)
        return 1
    if status == "canceled":
        print(f"FAILED: request {rid} was canceled. No video was produced.",
              file=sys.stderr)
        return 1
    if status == "failed":
        print(f"FAILED: request {rid} failed: "
              f"{redact(result.get('error') or 'no error message given')}",
              file=sys.stderr)
        return 1
    print(f"FAILED: request {rid} ended with unexpected status "
          f"{status or '(none)'}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
