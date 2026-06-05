"""
Publish / schedule the Reel via the Metricool API.

ISOLATION NOTE: this is the single most likely file to need updates, because
scheduler APIs change endpoints. Everything Metricool-specific lives here. If
their API shifts, or you move to a different scheduler / the Meta Graph API,
you only rewrite schedule_reel().

Metricool requires the Advanced+ plan for API access. You need:
  METRICOOL_USER_TOKEN  - from your Metricool account API settings
  METRICOOL_USER_ID     - your account id
  METRICOOL_BLOG_ID     - the "brand"/profile id for the connected IG account

Flow per Metricool's scheduler API:
  1. upload the media file -> get a media reference / URL
  2. create a scheduled post (network=instagram, type=reel) with that media + caption

Endpoints below follow Metricool's documented v2 scheduler API shape. Verify
against their current docs when you set up; adjust paths/fields if they differ.
"""
import os
import datetime
import requests
from pathlib import Path

BASE = "https://app.metricool.com/api"
TOKEN = os.environ["METRICOOL_USER_TOKEN"]
USER_ID = os.environ["METRICOOL_USER_ID"]
BLOG_ID = os.environ["METRICOOL_BLOG_ID"]

# how many hours from now to schedule (gives the upload time to process)
SCHEDULE_OFFSET_HOURS = int(os.environ.get("SCHEDULE_OFFSET_HOURS", "3"))


def _headers():
    return {"X-Mc-Auth": TOKEN}


def _upload_media(video_path: Path) -> str:
    """Upload the MP4, return the media URL/reference Metricool gives back."""
    url = f"{BASE}/v2/media/upload"
    params = {"userId": USER_ID, "blogId": BLOG_ID}
    with open(video_path, "rb") as f:
        files = {"file": (video_path.name, f, "video/mp4")}
        resp = requests.post(url, headers=_headers(), params=params,
                             files=files, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    # Metricool returns the hosted media url; field name may be 'url' or 'data'
    return data.get("url") or data.get("data") or data["mediaUrl"]


def schedule_reel(video_path: Path, caption: str) -> dict:
    media_url = _upload_media(video_path)

    publish_at = (
        datetime.datetime.utcnow()
        + datetime.timedelta(hours=SCHEDULE_OFFSET_HOURS)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    url = f"{BASE}/v2/scheduler/posts"
    params = {"userId": USER_ID, "blogId": BLOG_ID}
    payload = {
        "providers": [{"network": "instagram"}],
        "publicationDate": {"dateTime": publish_at, "timezone": "America/Toronto"},
        "text": caption,
        "instagramData": {"type": "REEL"},
        "media": [media_url],
        "autoPublish": True,
    }
    resp = requests.post(url, headers=_headers(), params=params,
                         json=payload, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    return {"status": "scheduled", "publish_at": publish_at, "response": body}
