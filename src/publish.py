"""
Publish the rendered Short to YouTube via the Data API v3 (videos.insert).

Auth: uses OAuth with a long-lived refresh token. You generate the refresh
token ONCE, locally, with auth_setup.py, then store these as GitHub secrets:
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
    YOUTUBE_REFRESH_TOKEN

videos.insert costs ~100 quota units; the free daily quota is 10,000, so one
daily upload plus analytics reads is comfortably free.

To be classified as a Short, the video must be vertical and <= 3 minutes and
include #Shorts in the title or description (we add it to the description).
"""
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# 22 = People & Blogs. 27 = Education. Either fits Stoic content.
CATEGORY_ID = os.environ.get("YOUTUBE_CATEGORY_ID", "22")


def _service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def publish_short(video_path: Path, title: str, description: str,
                  tags: list[str]) -> dict:
    yt = _service()

    # YouTube titles cap at 100 chars; ensure #Shorts is present.
    title = title[:90].rstrip()
    if "#shorts" not in (title + description).lower():
        description = description + "\n\n#Shorts"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [t.lstrip("#") for t in tags][:15],
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4",
                            resumable=True, chunksize=-1)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = req.next_chunk()

    vid = response["id"]
    return {
        "status": "published",
        "video_id": vid,
        "url": f"https://youtube.com/shorts/{vid}",
    }
