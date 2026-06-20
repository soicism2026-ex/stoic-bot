"""
Cross-post the rendered Short to Instagram Reels via the Meta Graph API.

Instagram's Content Publishing API does NOT accept a file upload. You give it a
PUBLIC video URL and Meta's servers fetch the file. So the flow is:

  1. host the MP4 at a public URL  -> _host_via_github_release()
  2. create a media container        -> POST /{ig-user-id}/media (media_type=REELS)
  3. poll the container until ready  -> GET /{container-id}?fields=status_code
  4. publish it                      -> POST /{ig-user-id}/media_publish

Auth: a long-lived access token for an Instagram Professional (Business/Creator)
account linked to a Facebook Page, stored as GitHub secrets:
    IG_ACCESS_TOKEN   long-lived token (60 days; refreshable)
    IG_USER_ID        the Instagram Business account id (numeric)

Hosting: the rendered MP4 is uploaded as a GitHub Release asset on this repo.
Release-asset download URLs are public on a PUBLIC repo, so Meta can fetch them.
Requires GITHUB_TOKEN + GITHUB_REPOSITORY (both already set in the workflow).

Everything is best-effort: any failure logs and returns a falsy result so a
broken Instagram cross-post never blocks the YouTube pipeline.
"""
import os
import sys
import time
from pathlib import Path

import requests

GRAPH = "https://graph.facebook.com/v21.0"
UPLOADS = "https://uploads.github.com"
API = "https://api.github.com"

# Release used as a public media bucket. Created on demand, reused thereafter.
MEDIA_TAG = os.environ.get("IG_MEDIA_RELEASE_TAG", "media-bucket")

# Container processing: Instagram transcodes the Reel before it can publish.
POLL_INTERVAL = 5      # seconds between status checks
POLL_MAX = 60          # up to ~5 minutes


# ---------------------------------------------------------------------------
# Step 1 — host the MP4 at a public URL (GitHub Release asset)
# ---------------------------------------------------------------------------

def _gh_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set — cannot host video for Instagram")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _ensure_release(repo: str) -> int:
    """Return the release id for MEDIA_TAG, creating the release if missing."""
    r = requests.get(f"{API}/repos/{repo}/releases/tags/{MEDIA_TAG}",
                     headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()["id"]
    # Create it (also creates the tag on the default branch).
    r = requests.post(
        f"{API}/repos/{repo}/releases",
        headers=_gh_headers(),
        json={
            "tag_name": MEDIA_TAG,
            "name": "Media bucket (Instagram hosting)",
            "body": "Public hosting for rendered Shorts so Instagram can fetch "
                    "them. Auto-managed — do not delete.",
            "prerelease": True,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def _host_via_github_release(video_path: Path) -> str:
    """Upload video_path as a release asset and return its public download URL."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY not set — cannot host video")
    release_id = _ensure_release(repo)

    # Asset names must be unique within a release; collisions 422. Use the file
    # name and delete any pre-existing asset of the same name first.
    asset_name = video_path.name
    existing = requests.get(
        f"{API}/repos/{repo}/releases/{release_id}/assets",
        headers=_gh_headers(), timeout=30,
    ).json()
    for a in existing if isinstance(existing, list) else []:
        if a.get("name") == asset_name:
            requests.delete(f"{API}/repos/{repo}/releases/assets/{a['id']}",
                            headers=_gh_headers(), timeout=30)

    with open(video_path, "rb") as fh:
        data = fh.read()
    up = requests.post(
        f"{UPLOADS}/repos/{repo}/releases/{release_id}/assets?name={asset_name}",
        headers={**_gh_headers(), "Content-Type": "video/mp4"},
        data=data,
        timeout=300,
    )
    up.raise_for_status()
    url = up.json()["browser_download_url"]
    print(f"  [instagram] hosted video at {url}")
    return url


# ---------------------------------------------------------------------------
# Steps 2-4 — Graph API container → poll → publish
# ---------------------------------------------------------------------------

def _create_container(ig_user: str, token: str, video_url: str,
                      caption: str) -> str:
    r = requests.post(
        f"{GRAPH}/{ig_user}/media",
        params={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],   # IG caption hard cap
            "share_to_feed": "true",
            "access_token": token,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def _wait_until_ready(container_id: str, token: str) -> bool:
    """Poll the container until Instagram finishes transcoding."""
    for _ in range(POLL_MAX):
        r = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        r.raise_for_status()
        code = r.json().get("status_code", "")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            print(f"  [instagram] container error: {r.json().get('status')}",
                  file=sys.stderr)
            return False
        time.sleep(POLL_INTERVAL)
    print("  [instagram] container did not finish in time", file=sys.stderr)
    return False


def _publish(ig_user: str, token: str, container_id: str) -> str:
    r = requests.post(
        f"{GRAPH}/{ig_user}/media_publish",
        params={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def publish_reel(video_path: Path, caption: str, hashtags: list[str]) -> dict:
    """Cross-post a rendered Short to Instagram Reels.

    Returns {"status": "published", "media_id": ...} on success, or
    {"status": "skipped"/"failed", "reason": ...} otherwise. Never raises.
    """
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    ig_user = os.environ.get("IG_USER_ID", "").strip()
    if not token or not ig_user:
        print("  [instagram] IG_ACCESS_TOKEN/IG_USER_ID not set — skipping cross-post")
        return {"status": "skipped", "reason": "no credentials"}

    full_caption = caption.strip()
    if hashtags:
        full_caption = f"{full_caption}\n\n{' '.join(hashtags)}"

    try:
        video_url = _host_via_github_release(Path(video_path))
        container = _create_container(ig_user, token, video_url, full_caption)
        print(f"  [instagram] container {container} created — waiting for processing")
        if not _wait_until_ready(container, token):
            return {"status": "failed", "reason": "container not ready"}
        media_id = _publish(ig_user, token, container)
        print(f"  [instagram] published reel {media_id}")
        return {"status": "published", "media_id": media_id}
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        print(f"  [instagram] HTTP error: {e} {body}", file=sys.stderr)
        return {"status": "failed", "reason": str(e)}
    except Exception as e:  # noqa: BLE001
        print(f"  [instagram] cross-post failed: {e}", file=sys.stderr)
        return {"status": "failed", "reason": str(e)}
