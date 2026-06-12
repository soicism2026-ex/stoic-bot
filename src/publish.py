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

TOKEN_URI = "https://oauth2.googleapis.com/token"

# 22 = People & Blogs. 27 = Education. Either fits Stoic content.
CATEGORY_ID = os.environ.get("YOUTUBE_CATEGORY_ID", "22")


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            # force-ssl is needed for commentThreads.insert.
            # Re-run auth_setup.py to generate a refresh token that includes it.
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
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

    from googleapiclient.http import MediaFileUpload
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


def post_comment(video_id: str, text: str) -> str:
    """Post a top-level comment on the video and return the comment thread ID.

    Requires the refresh token to include the youtube.force-ssl scope.
    Re-run auth_setup.py (which now requests that scope) if you get a 403.
    Pinning the comment must be done manually in YouTube Studio — the public
    Data API v3 does not expose a pin endpoint.
    """
    yt = _service()
    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": text}},
        }
    }
    resp = yt.commentThreads().insert(part="snippet", body=body).execute()
    thread_id = resp.get("id", "")
    print(f"  [comment] posted thread {thread_id}")
    print("  [comment] → pin it in YouTube Studio: Comments → ⋮ → Pin comment")
    return thread_id
