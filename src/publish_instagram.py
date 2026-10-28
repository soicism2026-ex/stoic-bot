"""
Echo's hands on Instagram: posts a rendered Short as a Reel through Meta's
Graph API. Echo is the Instagram crew member (owner, 2026-10-28: "lets work
on the instagram account now ... and get people to run that aswell");
scripts/echo.py runs his shift, this module does the talking to Instagram.

Instagram's publishing API takes no file upload with an Instagram Login key:
you give it a PUBLIC video URL and Meta's servers fetch the file. So:

  1. check the key, find the account   -> account()
  2. host the MP4 at a public URL       -> _host_via_github_release()
  3. create a Reels container           -> POST /{ig-id}/media (media_type=REELS)
  4. wait until Instagram processed it  -> GET /{container}?fields=status_code
  5. publish it                         -> POST /{ig-id}/media_publish
  6. delete the hosted copy             -> always, win or lose

Two kinds of key work, told apart by their first letters:
  * "IG..."  Instagram Login (Business Login for Instagram): the key the owner
             makes in Meta's App Dashboard (Instagram > API setup with
             Instagram login > Generate token). Host graph.instagram.com, and
             the account id comes from /me, so IG_USER_ID is not needed.
  * other    Facebook Login, the path tried from June to October 2026 (never
             worked): host graph.facebook.com, account id IG_USER_ID.
A long-lived key lasts 60 days; src/ig_key.py keeps it alive.

Keys never reach the output. Errors carry the HTTP status and Meta's message,
never the request URL, which holds the key (requests puts the URL in its
exception text).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v26.0")
IG_GRAPH = "https://graph.instagram.com"
FB_GRAPH = "https://graph.facebook.com"
UPLOADS = "https://uploads.github.com"
API = "https://api.github.com"

# Release used as a public media bucket. Created on demand, reused thereafter.
MEDIA_TAG = os.environ.get("IG_MEDIA_RELEASE_TAG", "media-bucket")

# Instagram transcodes a Reel before it can publish. Meta asks for at most
# one status check a minute for five minutes; a 15 s Short is usually ready
# well inside that, so check every 15 s.
POLL_INTERVAL = 15
POLL_MAX = 20

CAPTION_MAX = 2200
# Instagram capped hashtags at 5 per post in December 2025; more can fail.
MAX_HASHTAGS = 5
YOUTUBE_ONLY_TAGS = {"#shorts", "#short", "#youtubeshorts", "#ytshorts"}
FOLLOW_LINE = "Follow for a daily dose of Stoic wisdom."


class IGError(RuntimeError):
    """A refused Graph API call: status, Meta's message, Meta's error code."""

    def __init__(self, status: int, message: str, code: int | None = None):
        super().__init__(f"{status} {message}".strip())
        self.status, self.message, self.code = status, message, code

    @property
    def key_rejected(self) -> bool:
        """Meta's code 190 = the key is invalid, expired or revoked."""
        return self.code == 190 or "access token" in self.message.lower()


def kind(token: str) -> str:
    return "instagram" if token.startswith("IG") else "facebook"


def base(token: str) -> str:
    return f"{IG_GRAPH if kind(token) == 'instagram' else FB_GRAPH}/{GRAPH_VERSION}"


def _call(method: str, url: str, token: str, **params) -> dict:
    try:
        r = requests.request(method, url, params={**params, "access_token": token}, timeout=60)
    except requests.RequestException as e:
        raise IGError(0, f"could not reach Instagram ({type(e).__name__})") from None
    if not r.ok:
        err: dict = {}
        try:
            err = (r.json() or {}).get("error") or {}
        except Exception:  # noqa: BLE001
            pass
        msg = str(err.get("message") or getattr(r, "reason", "") or "refused")[:300]
        raise IGError(r.status_code, msg, err.get("code"))
    try:
        return r.json() or {}
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# The account
# ---------------------------------------------------------------------------

def account(token: str, ig_user_id: str = "") -> dict:
    """The account this key opens. Raises IGError when Instagram refuses it."""
    if kind(token) == "instagram":
        me = _call("GET", f"{base(token)}/me", token,
                   fields="user_id,username,account_type,followers_count,media_count")
        ig_id = str(me.get("user_id") or me.get("id") or "")
    else:
        if not ig_user_id:
            raise IGError(0, "IG_USER_ID is not set (a Facebook Login key needs it)")
        me = _call("GET", f"{base(token)}/{ig_user_id}", token,
                   fields="id,username,followers_count,media_count")
        ig_id = str(me.get("id") or ig_user_id)
    if not ig_id:
        raise IGError(0, "Instagram did not say which account this key is for")
    return {"kind": kind(token), "id": ig_id, "username": me.get("username"),
            "accountType": me.get("account_type"), "followers": me.get("followers_count"),
            "mediaCount": me.get("media_count")}


# ---------------------------------------------------------------------------
# The caption
# ---------------------------------------------------------------------------

def hashtags(tags: list[str] | None) -> list[str]:
    """At most five, YouTube's own (#shorts) dropped, each once."""
    out: list[str] = []
    for t in tags or []:
        t = "#" + str(t).strip().lstrip("#").replace(" ", "")
        if len(t) > 1 and t.lower() not in YOUTUBE_ONLY_TAGS and t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out[:MAX_HASHTAGS]


def caption(hook: str, quote: str, author: str, citation: str = "",
            tags: list[str] | None = None, credit: str = "") -> str:
    """Instagram's caption: the hook, the quote with its source, a follow
    line, the music credit when a CC BY track played (the licence needs it),
    and the hashtags. No links: Instagram doesn't make caption links tappable."""
    hook = hook.strip().rstrip(".!? ")
    source = "— " + ", ".join(x for x in (author.strip(), citation.strip()) if x)
    parts = [f"{hook}." if hook else "", f"“{quote.strip()}”\n{source}" if quote.strip() else "",
             FOLLOW_LINE, credit.strip(), " ".join(hashtags(tags))]
    return "\n\n".join(p for p in parts if p)[:CAPTION_MAX]


# ---------------------------------------------------------------------------
# Step 2: host the MP4 at a public URL (a GitHub Release asset)
# ---------------------------------------------------------------------------

def _gh_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set: cannot host the video for Instagram")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _ensure_release(repo: str) -> int:
    """Return the release id for MEDIA_TAG, creating the release if missing."""
    r = requests.get(f"{API}/repos/{repo}/releases/tags/{MEDIA_TAG}", headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()["id"]
    r = requests.post(f"{API}/repos/{repo}/releases", headers=_gh_headers(), json={
        "tag_name": MEDIA_TAG, "name": "Media bucket (Instagram hosting)",
        "body": "Public hosting for rendered Shorts so Instagram can fetch them. "
                "Each file is deleted once Instagram has it. Auto-managed: do not delete.",
        "prerelease": True}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _delete_asset(repo: str, asset_id: int) -> None:
    """Remove a hosted asset. Best effort: never raises into the post."""
    try:
        requests.delete(f"{API}/repos/{repo}/releases/assets/{asset_id}", headers=_gh_headers(), timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"  [instagram] could not clean up asset {asset_id}: {type(e).__name__}", file=sys.stderr)


def _host_via_github_release(video_path: Path) -> tuple[str, str, int]:
    """Upload video_path as a release asset: (public_url, repo, asset_id).
    The caller MUST delete it afterwards: by 2026-08-23 this bucket held 59
    files and 12.2 GB, one per day since June, because nothing removed them."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY not set: cannot host the video")
    release_id = _ensure_release(repo)
    name = video_path.name
    existing = requests.get(f"{API}/repos/{repo}/releases/{release_id}/assets",
                            headers=_gh_headers(), timeout=30).json()
    for a in existing if isinstance(existing, list) else []:
        if a.get("name") == name:          # names are unique within a release
            requests.delete(f"{API}/repos/{repo}/releases/assets/{a['id']}", headers=_gh_headers(), timeout=30)
    up = requests.post(f"{UPLOADS}/repos/{repo}/releases/{release_id}/assets?name={name}",
                       headers={**_gh_headers(), "Content-Type": "video/mp4"},
                       data=video_path.read_bytes(), timeout=300)
    up.raise_for_status()
    body = up.json()
    print(f"  [instagram] hosted the video for Instagram to fetch ({video_path.stat().st_size // 1024} KB)")
    return body["browser_download_url"], repo, body["id"]


# ---------------------------------------------------------------------------
# Steps 3-5: container, wait, publish
# ---------------------------------------------------------------------------

def _create_container(token: str, ig_id: str, video_url: str, text: str) -> str:
    got = _call("POST", f"{base(token)}/{ig_id}/media", token, media_type="REELS",
                video_url=video_url, caption=text[:CAPTION_MAX], share_to_feed="true")
    if not got.get("id"):
        raise IGError(0, "Instagram made no container for the video")
    return str(got["id"])


def _wait_until_ready(token: str, container_id: str) -> bool:
    for _ in range(POLL_MAX):
        got = _call("GET", f"{base(token)}/{container_id}", token, fields="status_code,status")
        code = got.get("status_code", "")
        if code in ("FINISHED", "PUBLISHED"):
            return True
        if code in ("ERROR", "EXPIRED"):
            print(f"  [instagram] Instagram could not process the video: {str(got.get('status'))[:200]}",
                  file=sys.stderr)
            return False
        time.sleep(POLL_INTERVAL)
    print("  [instagram] Instagram did not finish processing the video in time", file=sys.stderr)
    return False


def _publish(token: str, ig_id: str, container_id: str) -> str:
    got = _call("POST", f"{base(token)}/{ig_id}/media_publish", token, creation_id=container_id)
    if not got.get("id"):
        raise IGError(0, "Instagram did not return the new Reel's id")
    return str(got["id"])


def permalink(token: str, media_id: str) -> str | None:
    try:
        return _call("GET", f"{base(token)}/{media_id}", token, fields="permalink").get("permalink")
    except IGError:
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def publish_reel(video_path: Path, text: str, token: str | None = None,
                 ig_user_id: str | None = None, acct: dict | None = None) -> dict:
    """Post a rendered Short as a Reel. Returns {"status": "published",
    "media_id", "permalink"} or {"status": "skipped"/"failed", "reason"}.
    Never raises. The key is checked BEFORE anything is uploaded: the old
    order uploaded the whole MP4 and only then found the key dead."""
    token = (token if token is not None else os.environ.get("IG_ACCESS_TOKEN", "")).strip()
    ig_user_id = (ig_user_id if ig_user_id is not None else os.environ.get("IG_USER_ID", "")).strip()
    if not token:
        print("  [instagram] no key (IG_ACCESS_TOKEN) — skipping")
        return {"status": "skipped", "reason": "no key"}
    if acct is None:
        try:
            acct = account(token, ig_user_id)
        except IGError as e:
            print(f"  [instagram] key refused ({e}) — skipping before uploading anything")
            return {"status": "skipped", "reason": f"key refused: {e.message}"}

    repo = asset_id = None
    try:
        video_url, repo, asset_id = _host_via_github_release(Path(video_path))
        container = _create_container(token, acct["id"], video_url, text)
        print(f"  [instagram] container {container} made — waiting for Instagram to process it")
        if not _wait_until_ready(token, container):
            return {"status": "failed", "reason": "Instagram could not process the video"}
        media_id = _publish(token, acct["id"], container)
        link = permalink(token, media_id)
        print(f"  [instagram] published Reel {media_id} {link or ''}".rstrip())
        return {"status": "published", "media_id": media_id, "permalink": link}
    except IGError as e:
        print(f"  [instagram] Instagram refused: {e}", file=sys.stderr)
        return {"status": "failed", "reason": f"Instagram refused: {e.message}"}
    except Exception as e:  # noqa: BLE001
        print(f"  [instagram] post failed: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return {"status": "failed", "reason": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        # Safe on every path. After FINISHED Meta already has the file; on a
        # failure it is litter. Either way the video's home is YouTube.
        if repo and asset_id:
            _delete_asset(repo, asset_id)
