"""
Pre-flight secrets validator. Run before the pipeline to confirm every API
key is present and actually works. Exits 0 only if all required keys pass.

Required keys:  ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, YOUTUBE_CLIENT_ID,
                YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
Optional keys:  PEXELS_API_KEY, PIXABAY_API_KEY (fallbacks exist without them)
"""
import os
import sys
import json
import urllib.request
import urllib.parse

import requests as _requests

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"


def check_anthropic() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print(f"  [{FAIL}] ANTHROPIC_API_KEY — not set")
        return False
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        count = len(data.get("data", []))
        print(f"  [{PASS}] ANTHROPIC_API_KEY — {count} models accessible")
        return True
    except Exception as e:
        print(f"  [{FAIL}] ANTHROPIC_API_KEY — {e}")
        return False


def check_elevenlabs() -> bool:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        print(f"  [{FAIL}] ELEVENLABS_API_KEY — not set")
        return False
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
        print(f"  [{FAIL}] ELEVENLABS_API_KEY — {e}")
        return False


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
    try:
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
            tokens = json.loads(r.read())

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
    except Exception as e:
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


def main():
    print("=== Secrets pre-flight check ===")
    # Required: Anthropic, ElevenLabs, YouTube. Pexels/Pixabay are optional.
    required = [
        check_anthropic(),
        check_elevenlabs(),
        check_youtube(),
    ]
    check_pexels()
    check_pixabay()
    print("================================")
    failures = sum(1 for r in required if not r)
    if failures:
        print(f"FAILED: {failures} required key(s) invalid. Fix secrets before proceeding.")
        sys.exit(1)
    print("All required keys valid.")


if __name__ == "__main__":
    main()
