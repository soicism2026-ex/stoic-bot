"""
Echo's hands on Instagram through Buffer.

Owner, 2026-11-07: "how can i connect this to insagram withoiut goign though
meta developers?" Meta's developer sign-up never sent its text code (a known
Meta problem in 2026), so Echo posts through Buffer instead, which Meta has
approved: the owner connected the channel's Instagram inside Buffer and put a
personal API key in GitHub as BUFFER_API_KEY. No Meta developer account.

Buffer's API (developers.buffer.com): GraphQL at https://api.buffer.com, the
key as a Bearer token.

  1. instagram_channel(): the account's organizations, their channels, the
     one whose service is "instagram" (connected and not locked)
  2. create_reel(): createPost with the hosted video's URL, as a Reel shared
     to the feed, now (mode shareNow, schedulingType automatic)
  3. post_state(): read the post back (status scheduled / sending / sent /
     error; externalLink is the Reel on Instagram once it is sent)

Buffer has no upload endpoint and fetches the video when the post goes out, so
the hosted copy must stay reachable until the post is sent (scripts/echo.py
deletes it then). Free plan (developers.buffer.com/guides/api-limits): 600
requests a day, 1,000 per channel per 30 days; Echo keeps the channel id so a
quiet shift asks Buffer nothing.

Errors carry Buffer's message, never the key.
"""
from __future__ import annotations

import requests

API = "https://api.buffer.com"
TIMEOUT = 60

ORGS = "query Orgs { account { organizations { id name } } }"
CHANNELS = """query Channels($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id name displayName service isDisconnected isLocked externalLink organizationId
  }
}"""
CREATE = """mutation Reel($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id status externalLink } }
    ... on MutationError { message }
  }
}"""
POSTS = """query Posts($input: PostsInput!, $after: String) {
  posts(first: 50, after: $after, input: $input) {
    edges { node { id status externalLink sentAt error { message } } }
    pageInfo { hasNextPage endCursor }
  }
}"""
SETTLED = ("sent", "error")


class BufferError(Exception):
    def __init__(self, status: int, message: str, code: str = ""):
        super().__init__(f"{status} {message}".strip())
        self.status, self.message, self.code = status, message, code

    @property
    def key_rejected(self) -> bool:
        return self.status in (401, 403) or self.code in ("UNAUTHORIZED", "FORBIDDEN")

    @property
    def owners_to_fix(self) -> bool:
        """Only the owner can fix it: a refused key, or no usable Instagram/TikTok in Buffer."""
        return self.key_rejected or self.code in ("NO_CHANNEL", "DISCONNECTED")


def _gql(key: str, query: str, variables: dict | None = None) -> dict:
    try:
        r = requests.post(API, json={"query": query, "variables": variables or {}}, timeout=TIMEOUT,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    except requests.RequestException as e:
        raise BufferError(0, f"couldn't reach Buffer ({type(e).__name__})") from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    errors = body.get("errors") or []
    if r.status_code >= 400 or errors:
        first = errors[0] if errors else {}
        code = str((first.get("extensions") or {}).get("code") or "")
        message = str(first.get("message") or f"HTTP {r.status_code}")[:300]
        raise BufferError(r.status_code, message, code)
    return body.get("data") or {}


def _channel(key: str, service: str, label: str) -> dict:
    """The first connected, unlocked channel of `service` in any of the key's
    organizations; NO_CHANNEL when there is none, DISCONNECTED when all are off."""
    orgs = ((_gql(key, ORGS).get("account") or {}).get("organizations")) or []
    found = []
    for o in orgs:
        for c in _gql(key, CHANNELS, {"organizationId": o["id"]}).get("channels") or []:
            if c.get("service") == service:
                found.append({**c, "organizationId": c.get("organizationId") or o["id"]})
    if not found:
        raise BufferError(200, f"Buffer has no {label} channel connected", "NO_CHANNEL")
    usable = [c for c in found if not c.get("isDisconnected") and not c.get("isLocked")]
    if not usable:
        raise BufferError(200, f"Buffer's {label} channel is disconnected or locked", "DISCONNECTED")
    return usable[0]


def instagram_channel(key: str) -> dict:
    """{id, name, displayName, organizationId, externalLink, ...} of the
    Instagram channel Buffer can post to."""
    return _channel(key, "instagram", "Instagram")


def tiktok_channel(key: str) -> dict:
    """The same, for the TikTok channel (owner 2026-11-13: "Post every Short to
    TikTok too"). BufferError NO_CHANNEL when TikTok isn't connected yet."""
    return _channel(key, "tiktok", "TikTok")


def _create(key: str, channel_id: str, text: str, video_url: str, metadata: dict | None) -> dict:
    inp = {
        "channelId": channel_id,
        "text": text,
        "mode": "shareNow",
        "schedulingType": "automatic",
        "assets": [{"video": {"url": video_url}}],
    }
    if metadata:
        inp["metadata"] = metadata
    got = _gql(key, CREATE, {"input": inp}).get("createPost") or {}
    if got.get("post"):
        return got["post"]
    raise BufferError(200, got.get("message") or "Buffer didn't make the post", "MUTATION")


def create_reel(key: str, channel_id: str, text: str, video_url: str) -> dict:
    """The new post {id, status, externalLink}: a Reel, shared to the feed, now."""
    return _create(key, channel_id, text, video_url,
                   {"instagram": {"type": "reel", "shouldShareToFeed": True}})


def tiktok_title(caption: str) -> str:
    return (caption.strip().splitlines() or [""])[0].strip()[:90]


def create_tiktok(key: str, channel_id: str, video_url: str, caption: str) -> dict:
    """The new post {id, status, externalLink}: the video on TikTok, now.
    Buffer's TikTok metadata is undocumented, so the post goes out with none
    first; if Buffer's error talks about "tiktok" or "metadata", it is sent
    once more with a title (the caption's first line, 90 characters at most).
    A second refusal is raised as Buffer worded it (it never holds the key)."""
    try:
        return _create(key, channel_id, caption, video_url, None)
    except BufferError as e:
        if not any(w in e.message.lower() for w in ("tiktok", "metadata")):
            raise
    return _create(key, channel_id, caption, video_url, {"tiktok": {"title": tiktok_title(caption)}})


def post_state(key: str, organization_id: str, channel_id: str, post_id: str, pages: int = 6) -> dict | None:
    """{id, status, externalLink, sentAt, error} for one post, or None if
    Buffer doesn't list it (there is no single-post query)."""
    after = None
    for _ in range(pages):
        got = _gql(key, POSTS, {"after": after, "input": {
            "organizationId": organization_id, "filter": {"channelIds": [channel_id]}}}).get("posts") or {}
        for edge in got.get("edges") or []:
            node = edge.get("node") or {}
            if node.get("id") == post_id:
                return node
        info = got.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return None
        after = info.get("endCursor")
    return None
