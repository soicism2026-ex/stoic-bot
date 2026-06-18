"""
ONE-TIME local helper to generate your YouTube refresh token.

You run this ONCE on your own computer (not in GitHub Actions). It opens a
browser, you log in with the brand's Google account and approve, and it prints
a refresh token. You copy that token into a GitHub secret and never run this
again.

Prerequisites:
  1. In Google Cloud Console (console.cloud.google.com):
     - Create a project.
     - APIs & Services -> Library -> enable "YouTube Data API v3".
     - APIs & Services -> OAuth consent screen -> External -> fill the basics ->
       add YOUR brand Google account as a Test user (so it works without app
       verification).
     - Credentials -> Create credentials -> OAuth client ID -> type "Desktop app".
     - Download the JSON, save it next to this file as client_secret.json.
  2. pip install google-auth-oauthlib google-api-python-client
  3. python src/auth_setup.py

It prints CLIENT_ID, CLIENT_SECRET, and REFRESH_TOKEN. Put all three into
GitHub repo secrets.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    # force-ssl enables commentThreads.insert (automated pinned comments)
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n=== COPY THESE INTO GITHUB SECRETS ===")
    print("YOUTUBE_CLIENT_ID     =", creds.client_id)
    print("YOUTUBE_CLIENT_SECRET =", creds.client_secret)
    print("YOUTUBE_REFRESH_TOKEN =", creds.refresh_token)
    print("======================================")
    if not creds.refresh_token:
        print("\nNo refresh token returned. Revoke prior access at "
              "myaccount.google.com/permissions and run again.")


if __name__ == "__main__":
    main()
