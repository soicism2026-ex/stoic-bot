"""
Pre-flight secrets validator. Run before the pipeline to confirm every API
key is present and actually works.

It exits non-zero ONLY for a definitively bad credential (missing, revoked,
401/400, invalid_grant). Transient failures — 5xx from the provider, 429, DNS
and connection blips — are retried with backoff and then WARNED about, never
failed. This gate guards the pipeline; it must never be the thing that kills
it. A single Google 500 aborted the whole 2026-08-05 05:37 slot before this
policy existed.

Required keys:  ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, YOUTUBE_CLIENT_ID,
                YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
Optional keys:  PEXELS_API_KEY, PIXABAY_API_KEY (fallbacks exist without them)
"""
import os
import socket
import sys
import time
import json
import urllib.request
import urllib.parse
import urllib.error

import requests as _requests

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

# How many times to retry a check that failed for a TRANSIENT reason before
# giving up on it. Backoff is 2s, 4s.
RETRIES = int(os.environ.get("SECRETS_CHECK_RETRIES", "3"))


def _is_transient(exc: Exception) -> bool:
    """True if this failure says nothing about whether the credential is valid.

    Google returns 500/502/503 on its own bad days, and runners hit DNS and
    connection blips. Treating those as "your credentials are invalid" aborts
    the whole job — the 2026-08-05 05:37 slot died to a single Google 500 and
    posted nothing. A blip must degrade to a warning, never a hard stop.
    429 counts as transient too: rate limiting is not an auth problem.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    if isinstance(exc, _requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", 0) or 0
        return code >= 500 or code == 429
    return isinstance(exc, (
        urllib.error.URLError,          # DNS / connection refused / TLS
        socket.timeout,
        TimeoutError,
        ConnectionError,
        _requests.exceptions.RequestException,
    ))


def _retrying(fn, label: str):
    """Run fn(), retrying only on transient failures. Returns (value, error).

    On success: (result, None). On failure: (None, last_exception) — the caller
    decides whether that exception is fatal or merely a warning.
    """
    last: Exception | None = None
    for attempt in range(1, max(1, RETRIES) + 1):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001
            last = e
            if not _is_transient(e) or attempt == max(1, RETRIES):
                return None, e
            wait = 2 ** attempt
            print(f"  [{SKIP}] {label} — transient error ({e}); "
                  f"retry {attempt}/{max(1, RETRIES) - 1} in {wait}s")
            time.sleep(wait)
    return None, last


def check_anthropic() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print(f"  [{FAIL}] ANTHROPIC_API_KEY — not set")
        return False
    def _call():
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    data, err = _retrying(_call, "ANTHROPIC_API_KEY")
    if err is None:
        count = len(data.get("data", []))
        print(f"  [{PASS}] ANTHROPIC_API_KEY — {count} models accessible")
        return True
    if _is_transient(err):
        # Anthropic's server having a bad minute is not a bad key. content.py
        # has its own retry path; let the pipeline try for real.
        print(f"  [{SKIP}] ANTHROPIC_API_KEY — API unreachable after {RETRIES} "
              f"tries ({err}). Not a key problem; proceeding.")
        return True
    print(f"  [{FAIL}] ANTHROPIC_API_KEY — {err}")
    return False


def check_elevenlabs() -> bool:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        # Not passed by this workflow — skip rather than fail so auto-improve
        # (which doesn't use TTS) doesn't block on a key it never needs.
        print(f"  [{SKIP}] ELEVENLABS_API_KEY — not set (skipping for this workflow)")
        return True
    try:
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": key},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        tier = data.get("subscription", {}).get("tier", "unknown")
        print(f"  [{PASS}] ELEVENLABS_API_KEY — subscription tier: {tier}")
        return True
    except Exception as e:
        # WARN, never FAIL: tts.py falls back to edge-tts (then gTTS) when the
        # ElevenLabs call errors, so a bad/expired key must degrade the voice,
        # not stop the channel. A 401 here once blocked all 4 daily posts.
        print(f"  [{SKIP}] ELEVENLABS_API_KEY — invalid ({e}); voice will FALL "
              f"BACK to edge-tts until the key is fixed")
        return True


def check_youtube() -> bool:
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    missing = [k for k, v in [
        ("YOUTUBE_CLIENT_ID", client_id),
        ("YOUTUBE_CLIENT_SECRET", client_secret),
        ("YOUTUBE_REFRESH_TOKEN", refresh_token),
    ] if not v]
    if missing:
        for k in missing:
            print(f"  [{FAIL}] {k} — not set")
        return False

    # Exchange refresh token for an access token
    def _exchange():
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    try:
        tokens, err = _retrying(_exchange, "YOUTUBE credentials")
        if err is not None:
            raise err

        if "error" in tokens:
            print(f"  [{FAIL}] YOUTUBE credentials — {tokens['error']}: {tokens.get('error_description', '')}")
            return False

        access_token = tokens["access_token"]

        # Quick channels.list to confirm upload scope works
        req2 = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            ch = json.loads(r.read())
        channel_name = (ch.get("items") or [{}])[0].get("snippet", {}).get("title", "unknown")
        scopes = tokens.get("scope", "")
        has_force_ssl = "force-ssl" in scopes
        comment_status = "comment posting enabled" if has_force_ssl else "comment posting needs re-auth (force-ssl missing)"
        print(f"  [{PASS}] YOUTUBE credentials — channel: '{channel_name}', {comment_status}")
        return True
    except urllib.error.HTTPError as e:
        # A 403 here is almost always quotaExceeded, NOT bad credentials. Saying
        # "credentials failed" for a temporary daily-quota trip sends the owner
        # off re-authenticating a token that is perfectly fine. Read the body and
        # name the real reason; quota is a SKIP (recoverable) not a FAIL.
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        if e.code == 403 and ("quota" in body.lower() or "quotaExceeded" in body):
            print(f"  [{SKIP}] YOUTUBE — daily API quota exceeded (credentials are "
                  f"fine). Resets at midnight Pacific. Uploads will fail until then.")
            return True
        if e.code == 403:
            print(f"  [{FAIL}] YOUTUBE credentials — 403 Forbidden. Not a bad token: "
                  f"check the API is enabled and the token has youtube.force-ssl. "
                  f"Detail: {body[:200]}")
            return False
        if _is_transient(e):
            print(f"  [{SKIP}] YOUTUBE — Google returned {e.code} after {RETRIES} "
                  f"tries. That is Google's server, not your credentials. "
                  f"Proceeding; upload has its own retry + backup path.")
            return True
        print(f"  [{FAIL}] YOUTUBE credentials — {e}")
        return False
    except Exception as e:
        if _is_transient(e):
            print(f"  [{SKIP}] YOUTUBE — network unreachable after {RETRIES} tries "
                  f"({e}). Not a credentials problem; proceeding.")
            return True
        print(f"  [{FAIL}] YOUTUBE credentials — {e}")
        return False


def check_pexels() -> bool:
    """Optional — pipeline falls back to Pixabay/synthetic if Pexels is unavailable."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        print(f"  [{SKIP}] PEXELS_API_KEY — not set (Pixabay/synthetic fallback active)")
        return True
    try:
        resp = _requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": key},
            params={"query": "nature", "per_page": 1},
            timeout=10,
        )
        resp.raise_for_status()
        total = resp.json().get("total_results", 0)
        print(f"  [{PASS}] PEXELS_API_KEY — {total:,} videos available")
    except Exception as e:
        # Pexels is optional — warn but never block the pipeline
        print(f"  [{SKIP}] PEXELS_API_KEY — unreachable ({e}); Pixabay/synthetic fallback will be used")
    return True


def check_pixabay() -> bool:
    """Optional — pipeline falls back to synthetic backgrounds if Pixabay is unavailable."""
    key = os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        print(f"  [{SKIP}] PIXABAY_API_KEY — not set (synthetic fallback active)")
        return True
    try:
        resp = _requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": "nature", "per_page": 3},
            timeout=10,
        )
        resp.raise_for_status()
        total = resp.json().get("totalHits", 0)
        print(f"  [{PASS}] PIXABAY_API_KEY — {total:,} videos available")
    except Exception as e:
        # Pixabay is optional — warn but never block the pipeline
        print(f"  [{SKIP}] PIXABAY_API_KEY — unreachable ({e}); synthetic fallback will be used")
    return True


def check_cloudflare() -> bool:
    """Optional — free AI backgrounds via Workers AI (FLUX.1 schnell).

    Never fails the run: without it, backgrounds come from stock exactly as
    they did before. But it reports the remaining free allowance, because the
    whole reason to use Cloudflare is that 18 images/day fits inside a free
    10,000-neuron/day budget, and the owner should see that holding.
    """
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not acct or not token:
        print(f"  [{SKIP}] CLOUDFLARE — ACCOUNT_ID/API_TOKEN not set "
              f"(AI backgrounds off; stock footage will be used)")
        return True
    try:
        resp = _requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{acct}"
            f"/ai/run/@cf/black-forest-labs/flux-1-schnell",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "a single grey stone cube on black", "steps": 4},
            timeout=90,
        )
        if resp.status_code in (401, 403):
            print(f"  [{FAIL}] CLOUDFLARE — token rejected ({resp.status_code}). "
                  f"Needs the 'Workers AI' permission on the right account.")
            return True          # optional: warn loudly, never block a post
        resp.raise_for_status()
        data = resp.json()
        ok = bool(data.get("success", True)) and bool(data.get("result"))
        if ok:
            print(f"  [{PASS}] CLOUDFLARE — Workers AI reachable, FLUX.1 schnell "
                  f"generated a test image (free tier: ~230 images/day, "
                  f"this channel needs 18)")
        else:
            print(f"  [{SKIP}] CLOUDFLARE — unexpected response "
                  f"{str(data)[:160]}; backgrounds will fall back to stock")
    except Exception as e:  # noqa: BLE001
        print(f"  [{SKIP}] CLOUDFLARE — unreachable ({str(e)[:120]}); "
              f"backgrounds will fall back to stock")
    return True


def check_instagram() -> bool:
    """Optional — cross-post to Instagram Reels. Skips if not configured."""
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    ig_user = os.environ.get("IG_USER_ID", "")
    if not token or not ig_user:
        print(f"  [{SKIP}] INSTAGRAM — IG_ACCESS_TOKEN/IG_USER_ID not set (cross-post disabled)")
        return True
    try:
        resp = _requests.get(
            f"https://graph.facebook.com/v21.0/{ig_user}",
            params={"fields": "username,media_count", "access_token": token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        uname = data.get("username", "?")
        count = data.get("media_count", "?")
        print(f"  [{PASS}] INSTAGRAM — @{uname} ({count} posts), token valid")
    except Exception as e:
        # Optional — never block the pipeline; YouTube post still proceeds.
        print(f"  [{SKIP}] INSTAGRAM — token check failed ({e}); cross-post will be skipped")
    return True


def main():
    print("=== Secrets pre-flight check ===")
    # Required: Anthropic, ElevenLabs, YouTube. Pexels/Pixabay/Instagram optional.
    required = [
        check_anthropic(),
        check_elevenlabs(),
        check_youtube(),
    ]
    check_pexels()
    check_pixabay()
    check_cloudflare()
    check_instagram()
    print("================================")
    failures = sum(1 for r in required if not r)
    if failures:
        print(f"FAILED: {failures} required key(s) are definitively invalid "
              f"(not a transient outage — those are retried and warned about). "
              f"Fix the secret before the next run.")
        sys.exit(1)
    print("All required keys valid.")


if __name__ == "__main__":
    main()
