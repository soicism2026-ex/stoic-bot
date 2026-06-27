"""
ONE-TIME helper to generate your YouTube refresh token.

Phone-friendly. No browser on this machine required, no extra pip packages
beyond `requests`. It prints a Google sign-in URL; you open it on ANY device
(phone is fine), approve, and paste back the URL you land on. It then prints
the three values to copy into GitHub Secrets.

Why not the old run_console()/OOB flow: Google permanently shut down the
out-of-band (OOB) "copy this code" flow in 2023, so that path now errors. This
script uses the modern http://localhost redirect and reads the code straight
out of the redirected URL — which works even though nothing is listening on
localhost (the browser just shows "can't connect"; the code is in the URL bar).

Prerequisites (do these once in console.cloud.google.com):
  - APIs & Services -> Library -> enable "YouTube Data API v3".
  - APIs & Services -> OAuth consent screen -> External -> fill the basics ->
    add your brand Google account as a Test user. Under "Publishing status"
    click "Publish app" so the refresh token does NOT expire after 7 days.
  - Credentials -> Create credentials -> OAuth client ID -> type "Desktop app".
  - Either download the JSON as client_secret.json in the repo root, OR just
    have the Client ID + Client secret ready to paste.

Run:
  python src/auth_setup.py

Then copy CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN into:
  GitHub repo -> Settings -> Secrets and variables -> Actions
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

import requests

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    # force-ssl enables commentThreads.insert + set_thumbnail (needed by bot)
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

AUTH_ENDPOINT  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
# Desktop OAuth clients allow a localhost redirect. Nothing needs to listen
# there — we read the ?code=... straight out of the URL the browser lands on.
REDIRECT_URI = "http://localhost"


def _load_credentials() -> tuple[str, str]:
    """Get (client_id, client_secret) from client_secret.json, env, or prompt."""
    root = Path(__file__).resolve().parent.parent
    for candidate in (root / "client_secret.json", Path("client_secret.json")):
        if candidate.exists():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            block = data.get("installed") or data.get("web") or {}
            cid, secret = block.get("client_id"), block.get("client_secret")
            if cid and secret:
                print(f"Loaded credentials from {candidate}")
                return cid, secret

    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    if cid and secret:
        print("Loaded credentials from environment variables.")
        return cid, secret

    print("Enter your OAuth Desktop-app credentials "
          "(Google Cloud Console -> Credentials):")
    cid = input("  Client ID: ").strip()
    secret = input("  Client secret: ").strip()
    if not cid or not secret:
        sys.exit("Client ID and secret are both required.")
    return cid, secret


def _build_auth_url(client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",   # ask for a refresh token
        "prompt": "consent",        # force a refresh token even if re-authorizing
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _extract_code(pasted: str) -> str:
    """Accept either the full redirected URL or just the bare code value."""
    pasted = pasted.strip()
    if "code=" in pasted:
        query = urllib.parse.urlparse(pasted).query or pasted.split("?", 1)[-1]
        code = urllib.parse.parse_qs(query).get("code", [""])[0]
        if code:
            return code
    return pasted  # assume the user pasted just the code


def _exchange_code(client_id: str, client_secret: str, code: str) -> dict:
    resp = requests.post(
        TOKEN_ENDPOINT,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def main():
    client_id, client_secret = _load_credentials()

    print("\n1. Open this URL (phone browser is fine), sign in as the channel's")
    print("   Google account, and approve every permission:\n")
    print(_build_auth_url(client_id))
    print("\n2. Your browser will try to open http://localhost and show a")
    print('   "can\'t connect" / "site can\'t be reached" page. THAT IS EXPECTED.')
    print("   Copy the full address from the browser's address bar (it contains")
    print("   ?code=...) and paste it below.\n")

    pasted = input("Paste the redirected URL (or just the code): ").strip()
    code = _extract_code(pasted)
    if not code:
        sys.exit("No authorization code found in what you pasted.")

    tokens = _exchange_code(client_id, client_secret, code)
    refresh_token = tokens.get("refresh_token")

    print("\n=== COPY THESE INTO GITHUB SECRETS ===")
    print("YOUTUBE_CLIENT_ID     =", client_id)
    print("YOUTUBE_CLIENT_SECRET =", client_secret)
    print("YOUTUBE_REFRESH_TOKEN =", refresh_token)
    print("======================================")
    print("\nGo to: GitHub repo -> Settings -> Secrets and variables -> Actions")
    print("Update (or create) each of the three secrets above.")

    if not refresh_token:
        print(
            "\nNo refresh token returned — Google only sends one the first time "
            "an account approves the app.\nTo force a fresh one:\n"
            "  1. Go to myaccount.google.com/permissions\n"
            "  2. Remove access for this OAuth app.\n"
            "  3. Run this script again."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
