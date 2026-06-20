"""
Auto-reply to the best recent YouTube comments using Claude.

Strategy:
  1. Read recent video IDs from data/posts.csv (last 7 days)
  2. For each video, fetch top comments via YouTube Data API
  3. Filter: not already replied, not spam, long enough to be meaningful
  4. Rank by likes + length (proxy for quality / engagement)
  5. Generate a short Stoic reply with Claude
  6. Post the reply
  7. Log replied comment IDs to data/replied_comments.csv

Limits: max 5 replies per run to stay well clear of YouTube spam detection.

Requires: ANTHROPIC_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET,
          YOUTUBE_REFRESH_TOKEN (same secrets used by the main pipeline).
          The YouTube token MUST have the youtube.force-ssl scope — if it
          doesn't, comment posting returns 403 and we skip gracefully.
"""
import csv
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_CSV    = ROOT / "data" / "posts.csv"
REPLIED_CSV  = ROOT / "data" / "replied_comments.csv"
TOKEN_URI    = "https://oauth2.googleapis.com/token"

MAX_REPLIES_PER_RUN = 5
LOOKBACK_DAYS       = 7    # only reply on videos posted in the last N days
MIN_COMMENT_LEN     = 20   # ignore very short comments
REPLY_SCOPES        = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yt_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=REPLY_SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _load_recent_video_ids() -> list[str]:
    """Return video IDs posted within the last LOOKBACK_DAYS days."""
    if not POSTS_CSV.exists():
        return []
    cutoff = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    ids = []
    with open(POSTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("date", "") >= cutoff and row.get("video_id"):
                ids.append(row["video_id"].strip())
    return list(dict.fromkeys(ids))  # preserve order, dedupe


def _load_replied_ids() -> set[str]:
    if not REPLIED_CSV.exists():
        return set()
    with open(REPLIED_CSV, newline="", encoding="utf-8") as f:
        return {row["comment_id"] for row in csv.DictReader(f) if row.get("comment_id")}


def _save_replied(comment_id: str, video_id: str, reply_text: str):
    exists = REPLIED_CSV.exists()
    with open(REPLIED_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "comment_id", "video_id", "reply"])
        if not exists:
            w.writeheader()
        w.writerow({
            "date": datetime.date.today().isoformat(),
            "comment_id": comment_id,
            "video_id": video_id,
            "reply": reply_text.replace("\n", " "),
        })


def _is_spam(text: str) -> bool:
    lower = text.lower()
    spam_signals = ["sub4sub", "sub back", "check out my", "follow me", "visit my",
                    "http://", "https://", "subscribe to me", "www.", ".com/"]
    return any(s in lower for s in spam_signals)


def _score_comment(item: dict) -> float:
    """Higher = better comment worth replying to."""
    snip = item["snippet"]["topLevelComment"]["snippet"]
    likes = int(snip.get("likeCount", 0))
    length = len(snip.get("textDisplay", ""))
    return likes * 3 + min(length, 300)


def _fetch_top_comments(yt, video_id: str, replied_ids: set) -> list[dict]:
    """Return filtered, ranked comment thread items for a single video."""
    try:
        resp = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=50,
            order="relevance",
            textFormat="plainText",
        ).execute()
    except Exception as e:
        print(f"  [comments] fetch failed for {video_id}: {e}")
        return []

    results = []
    for item in resp.get("items", []):
        snip = item["snippet"]["topLevelComment"]["snippet"]
        cid  = item["snippet"]["topLevelComment"]["id"]
        text = snip.get("textDisplay", "").strip()
        reply_count = item["snippet"].get("totalReplyCount", 0)

        # Skip: already replied, too short, spam, or already has replies
        if cid in replied_ids:
            continue
        if len(text) < MIN_COMMENT_LEN:
            continue
        if _is_spam(text):
            continue
        if reply_count > 0:
            continue  # already has a reply (possibly from us on a previous run)

        results.append(item)

    results.sort(key=_score_comment, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Claude reply generation
# ---------------------------------------------------------------------------

def _generate_reply(comment_text: str, video_title: str) -> str:
    """Ask Claude to write a short, on-brand Stoic reply."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system = (
        "You run a Stoic philosophy YouTube channel. "
        "Your voice is calm, direct, and grounded — like a mentor who has actually "
        "lived the philosophy, not just read about it. "
        "When replying to comments you write 1-3 short sentences: "
        "acknowledge what they said, tie it to a Stoic idea, and optionally ask one "
        "genuine question to continue the conversation. "
        "No emojis. No cringe motivational energy. No hashtags. "
        "Sound human. Keep it under 200 characters if possible."
    )
    user = (
        f'The video is titled: "{video_title}"\n'
        f'A viewer commented: "{comment_text}"\n\n'
        "Write a reply."
    )

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return msg.content[0].text.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Comment auto-reply ===")

    video_ids = _load_recent_video_ids()
    if not video_ids:
        print("  No recent videos found in posts.csv — nothing to reply to.")
        return

    print(f"  Checking {len(video_ids)} recent video(s): {video_ids}")
    replied_ids = _load_replied_ids()
    print(f"  Already replied to {len(replied_ids)} comment(s) in history.")

    try:
        yt = _yt_service()
    except Exception as e:
        print(f"  YouTube auth failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Gather candidate comments across all recent videos
    candidates: list[tuple[dict, str, str]] = []  # (item, video_id, video_title)
    for vid in video_ids:
        items = _fetch_top_comments(yt, vid, replied_ids)
        for item in items:
            title = item["snippet"]["topLevelComment"]["snippet"].get("videoId", vid)
            candidates.append((item, vid, vid))  # title fetched below

    # Fetch video titles for context
    if candidates:
        vid_ids_needed = list({c[1] for c in candidates})
        try:
            vresp = yt.videos().list(part="snippet", id=",".join(vid_ids_needed)).execute()
            title_map = {v["id"]: v["snippet"]["title"] for v in vresp.get("items", [])}
        except Exception:
            title_map = {}
        candidates = [(item, vid, title_map.get(vid, "Stoic wisdom")) for item, vid, _ in candidates]

    # Sort all candidates globally by score, take top N
    candidates.sort(key=lambda x: _score_comment(x[0]), reverse=True)
    candidates = candidates[:MAX_REPLIES_PER_RUN]

    if not candidates:
        print("  No suitable comments found this run.")
        return

    replied = 0
    for item, video_id, video_title in candidates:
        comment_id  = item["snippet"]["topLevelComment"]["id"]
        comment_txt = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"].strip()
        author      = item["snippet"]["topLevelComment"]["snippet"].get("authorDisplayName", "viewer")
        likes       = item["snippet"]["topLevelComment"]["snippet"].get("likeCount", 0)

        print(f"\n  Comment ({likes} likes) by {author}:")
        print(f"    \"{comment_txt[:120]}{'...' if len(comment_txt) > 120 else ''}\"")

        try:
            reply = _generate_reply(comment_txt, video_title)
        except Exception as e:
            print(f"  Claude generation failed: {e} — skipping")
            continue

        print(f"  Reply: \"{reply}\"")

        try:
            yt.comments().insert(
                part="snippet",
                body={
                    "snippet": {
                        "parentId": comment_id,
                        "textOriginal": reply,
                    }
                },
            ).execute()
            _save_replied(comment_id, video_id, reply)
            print(f"  Posted reply to {comment_id}")
            replied += 1
        except Exception as e:
            err = str(e)
            if "forbidden" in err.lower() or "403" in err:
                print(
                    "  [SKIP] YouTube returned 403 — token needs youtube.force-ssl scope.\n"
                    "  Re-run scripts/get_yt_token.py to refresh with comment permissions.",
                    file=sys.stderr,
                )
                break
            print(f"  Post failed: {e}", file=sys.stderr)

    print(f"\n  Done — replied to {replied} comment(s).")
    print("==========================")


if __name__ == "__main__":
    main()
