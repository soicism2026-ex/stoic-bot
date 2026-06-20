"""
One-time helper: turn a short-lived Facebook token into the two secrets the
Instagram cross-post needs — IG_ACCESS_TOKEN (long-lived, ~60 days) and
IG_USER_ID (the Instagram Business account id).

You only run this LOCALLY, once (and again every ~60 days to refresh the token).

------------------------------------------------------------------------------
STEP 1 — get a SHORT-LIVED user token (browser, ~2 min):
  1. Go to  https://developers.facebook.com/tools/explorer/
  2. Top-right: pick your App.
  3. "User or Page" -> User Token. Click "Add a Permission" and tick ALL of:
        instagram_basic
        instagram_content_publish
        pages_show_list
        pages_read_engagement
        business_management
  4. Click "Generate Access Token", approve the popup.
  5. Copy the token string it shows.

STEP 2 — run this script with your app id/secret + that token:
  export FB_APP_ID=...           # Meta app id (App Dashboard -> Settings -> Basic)
  export FB_APP_SECRET=...       # Meta app secret (same page)
  export FB_SHORT_TOKEN=...      # the token from step 1
  python scripts/get_ig_token.py

It prints IG_USER_ID and IG_ACCESS_TOKEN. Paste both into the repo's
GitHub Secrets (Settings -> Secrets and variables -> Actions).
------------------------------------------------------------------------------
"""
import os
import sys

import requests

GRAPH = "https://graph.facebook.com/v21.0"


def _need(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: {name} not set. See the instructions at the top of this file.",
              file=sys.stderr)
        sys.exit(1)
    return val


def main() -> int:
    app_id = _need("FB_APP_ID")
    app_secret = _need("FB_APP_SECRET")
    short_token = _need("FB_SHORT_TOKEN")

    # 1. Exchange the short-lived token for a long-lived one (~60 days).
    print("Exchanging for a long-lived token...")
    r = requests.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"ERROR exchanging token: {r.status_code} {r.text}", file=sys.stderr)
        return 1
    long_token = r.json()["access_token"]

    # 2. Find the Facebook Page linked to the IG Business account.
    r = requests.get(f"{GRAPH}/me/accounts",
                     params={"access_token": long_token}, timeout=30)
    r.raise_for_status()
    pages = r.json().get("data", [])
    if not pages:
        print("ERROR: no Facebook Pages found on this account. The IG Business "
              "account must be linked to a Page.", file=sys.stderr)
        return 1

    # 3. For each Page, resolve its instagram_business_account id.
    ig_user_id = None
    ig_username = None
    for pg in pages:
        pid = pg["id"]
        rr = requests.get(
            f"{GRAPH}/{pid}",
            params={"fields": "instagram_business_account{id,username}",
                    "access_token": long_token},
            timeout=30,
        )
        iba = rr.json().get("instagram_business_account") if rr.ok else None
        if iba:
            ig_user_id = iba["id"]
            ig_username = iba.get("username", "?")
            print(f"  found IG account @{ig_username} via Page '{pg.get('name','?')}'")
            break

    if not ig_user_id:
        print("ERROR: none of your Pages have a linked Instagram Business "
              "account. Link the IG account to a Page in the Meta Business "
              "Suite, then re-run.", file=sys.stderr)
        return 1

    # Token longevity for reference.
    dbg = requests.get(
        f"{GRAPH}/debug_token",
        params={"input_token": long_token,
                "access_token": f"{app_id}|{app_secret}"},
        timeout=30,
    )
    expires = "unknown"
    if dbg.ok:
        data = dbg.json().get("data", {})
        exp = data.get("expires_at")
        if exp:
            import datetime
            expires = datetime.datetime.utcfromtimestamp(exp).isoformat() + "Z"

    print("\n" + "=" * 64)
    print("Paste these into GitHub -> Settings -> Secrets and variables -> Actions:")
    print("=" * 64)
    print(f"IG_USER_ID      = {ig_user_id}")
    print(f"IG_ACCESS_TOKEN = {long_token}")
    print("=" * 64)
    print(f"(@{ig_username}; token expires ~{expires}. Re-run this script to refresh.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
