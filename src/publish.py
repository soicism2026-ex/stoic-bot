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


def _service(extra_scopes: list[str] | None = None):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    if extra_scopes:
        scopes.extend(extra_scopes)
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=scopes,
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


def set_thumbnail(video_id: str, thumb_path) -> bool:
    """Upload a custom thumbnail image for the video.

    Requires youtube.force-ssl scope (same token used for post_comment).
    Returns True on success, False on any failure (non-blocking).
    """
    import sys as _sys
    thumb_path = __import__("pathlib").Path(thumb_path)
    size_mb = thumb_path.stat().st_size / 1_048_576 if thumb_path.exists() else 0
    if size_mb > 2.0:
        print(
            f"  [thumbnail] SKIP {video_id} — file {size_mb:.1f}MB exceeds YouTube 2MB limit",
            file=_sys.stderr,
        )
        return False
    try:
        from googleapiclient.http import MediaFileUpload
        yt = _service(extra_scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
        resp = yt.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
        ).execute()
        items = resp.get("items", [{}])
        url = (items[0].get("maxres") or items[0].get("high") or {}).get("url", "?")
        print(f"  [thumbnail] set for {video_id}  ({size_mb:.2f}MB)  url={url[:70]}")
        return True
    except Exception as e:
        print(f"  [thumbnail] upload failed: {e}", file=_sys.stderr)
        return False


def post_comment(video_id: str, text: str) -> str:
    """Post a top-level comment on the video and return the comment thread ID.

    Requires the refresh token to include the youtube.force-ssl scope.
    Returns an empty string (skips silently) if the token lacks that scope.
    Re-run auth_setup.py to generate a refresh token that includes force-ssl.
    """
    try:
        yt = _service(extra_scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
        body = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": text}},
            }
        }
        resp = yt.commentThreads().insert(part="snippet", body=body).execute()
        thread_id = resp.get("id", "")
        print(f"  [comment] posted thread {thread_id}")
        return thread_id
    except Exception as e:
        print(f"  [comment] skipped — token may lack force-ssl scope: {e}")
        return ""
