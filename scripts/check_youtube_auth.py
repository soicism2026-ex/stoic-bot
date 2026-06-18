"""
YouTube credential doctor.

Tests YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN as a
set — does a token refresh and a cheap channels.list(mine=true) read — and
prints a clear PASS/FAIL with the granted scopes and an actionable diagnosis.

Publishes NOTHING. Use it to debug auth without burning a full render+upload.

Exit code 0 = credentials work; 1 = they do not.
"""
import os
import sys

TOKEN_URI = "https://oauth2.googleapis.com/token"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
FORCE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def main() -> int:
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "")
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    rtok = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

    # Surface obvious shape problems without leaking the values.
    print("=== credential shape ===")
    print(f"CLIENT_ID present: {bool(cid)} "
          f"(ends with .apps.googleusercontent.com: {cid.strip().endswith('.apps.googleusercontent.com')})")
    print(f"CLIENT_SECRET present: {bool(csec)} (len {len(csec.strip())})")
    print(f"REFRESH_TOKEN present: {bool(rtok)} (len {len(rtok.strip())}, "
          f"starts with '1//': {rtok.strip().startswith('1//')})")
    if rtok != rtok.strip():
        print("WARNING: REFRESH_TOKEN has leading/trailing whitespace — re-paste it cleanly.")
    if not (cid and csec and rtok):
        print("\nFAIL: one or more secrets are empty. Set all three.")
        return 1

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    # Request the full scope set the bot actually uses so a scope mismatch
    # shows up here rather than mid-pipeline.
    creds = Credentials(
        token=None,
        refresh_token=rtok.strip(),
        token_uri=TOKEN_URI,
        client_id=cid.strip(),
        client_secret=csec.strip(),
        scopes=[
            UPLOAD_SCOPE,
            "https://www.googleapis.com/auth/youtube.readonly",
            FORCE_SSL_SCOPE,
        ],
    )

    print("\n=== refresh test ===")
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = yt.channels().list(part="snippet", mine=True).execute()
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        print(f"FAIL: {msg}")
        print("\n=== diagnosis ===")
        if "invalid_grant" in msg:
            print(
                "invalid_grant = the refresh token is not valid for THIS client.\n"
                "Most likely causes, in order:\n"
                "  1. CLIENT_ID/CLIENT_SECRET in GitHub do not match the OAuth\n"
                "     client that minted this refresh token. FIX: re-run\n"
                "     src/auth_setup.py and update ALL THREE secrets\n"
                "     (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN) from that one run.\n"
                "  2. The refresh token was revoked or superseded (generating a\n"
                "     new one can invalidate the old). Use the newest one only.\n"
                "  3. Whitespace/truncation when pasting the token.\n"
                "  4. OAuth consent screen still in 'Testing' → tokens expire\n"
                "     after 7 days. Publish the app (can stay unverified)."
            )
        elif "invalid_scope" in msg:
            print(
                "invalid_scope = the token was granted fewer scopes than requested.\n"
                "FIX: re-run src/auth_setup.py (it requests upload + readonly +\n"
                "force-ssl) and update YOUTUBE_REFRESH_TOKEN."
            )
        elif "invalid_client" in msg:
            print(
                "invalid_client = CLIENT_ID or CLIENT_SECRET is wrong/mismatched.\n"
                "FIX: copy both from the same OAuth client in Google Cloud Console."
            )
        else:
            print("Unexpected error — see the message above.")
        return 1

    items = resp.get("items", [])
    title = items[0]["snippet"]["title"] if items else "(no channel on this account)"
    granted = creds.scopes or []
    print("PASS: token refreshed and authenticated.")
    print(f"Channel: {title}")
    print(f"Granted scopes: {granted}")

    print("\n=== capability check ===")
    have_upload = UPLOAD_SCOPE in granted
    have_force_ssl = FORCE_SSL_SCOPE in granted
    print(f"Can upload videos (youtube.upload): {have_upload}")
    print(f"Can set thumbnails / comments / unlist (youtube.force-ssl): {have_force_ssl}")
    if not (have_upload and have_force_ssl):
        print(
            "\nWARNING: missing a scope the bot needs. Re-run src/auth_setup.py "
            "and update YOUTUBE_REFRESH_TOKEN so all required scopes are granted."
        )
        return 1
    print("\nAll required scopes present. Credentials are good to go.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
