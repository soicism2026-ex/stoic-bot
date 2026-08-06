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
# Hard DAILY cap. The workflow has 6 cron slots, so a per-run cap alone allowed
# 30 replies/day = 1,500 YouTube quota units (each comments.insert is 50) against
# a 10,000/day budget that must also fund uploads at 1600 each.
MAX_REPLIES_PER_DAY = int(os.environ.get("MAX_REPLIES_PER_DAY", "5"))


def _replies_today() -> int:
    """How many replies were already posted today (across all runs)."""
    if not REPLIED_CSV.exists():
        return 0
    today = datetime.date.today().isoformat()
    try:
        with open(REPLIED_CSV, newline="", encoding="utf-8") as f:
            return sum(1 for r in csv.DictReader(f) if r.get("date") == today)
    except Exception:
        return 0
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


def _get_own_channel_id(yt) -> str:
    """Fetch the authenticated channel's own ID via channels.list(mine=True)."""
    try:
        resp = yt.channels().list(part="id", mine=True).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else ""
    except Exception as e:
        print(f"  [comments] could not fetch own channel ID: {e}")
        return ""


def _fetch_top_comments(yt, video_id: str, replied_ids: set,
                        own_channel_id: str = "") -> list[dict]:
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

        # Belt-and-suspenders own-comment filter:
        # videoOwnerChannelId may be absent from the API response, so we also
        # compare against the channel ID we fetched explicitly at startup.
        video_owner_id = item["snippet"].get("videoOwnerChannelId", "")
        commenter_id   = snip.get("authorChannelId", {}).get("value", "")

        is_own = (
            (video_owner_id and commenter_id and video_owner_id == commenter_id)
            or (own_channel_id and commenter_id and own_channel_id == commenter_id)
        )
        if is_own:
            continue
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

_DISMISSIVE_SIGNALS = [
    "ai slop", "ai generated", "ai voice", "chatgpt", "bot channel", "grifter",
    "grift", "scam", "cringe", "stupid", "trash", "garbage", "boring", "mid",
    "fake deep", "pseudo", "nonsense", "who cares", "cope", "brainrot",
    "stolen", "ripoff", "rip off", "L take", "ratio", "yap", "midwit",
]


def _is_dismissive(text: str) -> bool:
    """Cheap prefilter: obvious mockery/hostility, skipped without a model call."""
    low = text.lower()
    return any(sig in low for sig in _DISMISSIVE_SIGNALS)


def _is_receptive(comment_text: str) -> bool:
    """Reply only to viewers who actually connect with the message — builds a
    real community and avoids amplifying detractors (engaging a hostile comment
    boosts it and tells the algorithm to find more people like them).

    True for: sincere agreement, sharing their own struggle/experience, genuine
    questions, gratitude, thoughtful reflection. False for: mockery, trolling,
    bad-faith argument, dismissal, or anything hollow. Fails CLOSED (skip) so a
    classifier hiccup never engages a troll.
    """
    if _is_dismissive(comment_text):
        return False
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            system=(
                "You screen YouTube comments for a Stoic philosophy channel. Reply "
                "ONLY to viewers who genuinely connect with the message. Answer with "
                "one word:\n"
                "ENGAGE — sincere agreement, someone sharing their own struggle or "
                "experience, a genuine question, gratitude, or thoughtful reflection "
                "that shows they take the ideas seriously.\n"
                "SKIP — mockery, trolling, sarcasm, bad-faith argument, dismissal, "
                "hostility, insults, or hollow one-word noise.\n"
                "When unsure, answer SKIP."
            ),
            messages=[{"role": "user", "content": f'Comment: "{comment_text}"'}],
        )
        verdict = msg.content[0].text.strip().upper()
        return verdict.startswith("ENGAGE")
    except Exception as e:
        print(f"  [comments] receptivity check failed ({e}) — skipping to be safe")
        return False


# Stock validation openers that instantly read as "bot". Stripped deterministically
# if the model produces one anyway — belt and braces with the prompt rules.
_BOT_OPENERS = [
    "that's the core of it", "thats the core of it", "that's exactly it",
    "that's honest", "thats honest", "you're touching on something",
    "youre touching on something", "well said", "absolutely,", "exactly,",
    "great point", "beautifully put", "so true", "this is powerful",
    "what a great", "i love this", "spot on",
]


def _strip_bot_tells(reply: str) -> str:
    """Remove stock openers and soften robotic punctuation so replies read human."""
    out = reply.strip().strip('"')
    low = out.lower()
    for opener in _BOT_OPENERS:
        if low.startswith(opener):
            # drop the opener and any trailing punctuation/space, recapitalise
            out = out[len(opener):].lstrip(" ,.—-:;!")
            if out:
                out = out[0].upper() + out[1:]
            break
    # People type dashes/commas, not em-dashes.
    out = out.replace(" — ", ", ").replace("—", ", ")
    return out.strip()


# Backwards-compatible alias used by _generate_reply.
_dehumanize_guard = _strip_bot_tells


def _generate_reply(comment_text: str, video_title: str) -> str:
    """Ask Claude to write a short, on-brand Stoic reply."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system = (
        "You are a real person who runs a small Stoicism channel, replying to "
        "someone who took the time to comment. Not a brand account. Not a "
        "teacher. A person who reads every comment and answers like a human.\n\n"
        "WRITE LIKE A HUMAN — these are the tells that make replies feel botlike, "
        "and you must avoid all of them:\n"
        "- NEVER open with a stock validation phrase. Banned openers: 'That's the "
        "core of it', 'That's honest', 'You're touching on something', 'Exactly', "
        "'Well said', 'This is', 'Absolutely'. Just start with what you actually "
        "want to say.\n"
        "- Do NOT name-drop a philosopher every time. Most replies should mention "
        "NO philosopher at all. Only bring one up if it genuinely adds something "
        "the person would want — never as decoration, never 'X would say...'.\n"
        "- Do NOT end every reply with a question. Only ask if you're actually "
        "curious about their answer. Most replies end on a plain statement.\n"
        "- Do NOT explain the philosophy back to them. They didn't ask for a "
        "lesson. If they said something true, you can just agree.\n"
        "- Avoid em-dashes. Use plain punctuation like people type.\n\n"
        "HOW TO SOUND REAL:\n"
        "- Vary the length a lot. Some replies are four words ('Yeah. That one's "
        "hard.'). Some are two sentences. Never a uniform template.\n"
        "- Speak as yourself: 'I', 'me', 'honestly', 'took me years'. Admit "
        "things. Share the struggle instead of standing above it.\n"
        "- Answer THIS comment specifically. Reference their actual words or "
        "situation, not the general topic.\n"
        "- If they're going through something hard, be warm first. Comfort beats "
        "wisdom.\n"
        "- If they just said something kind, a genuine thank you is a complete "
        "reply.\n\n"
        "No emojis. No hashtags. No motivational-poster energy. Under 220 "
        "characters. Write only the reply text."
    )
    user = (
        f'Your video: "{video_title}"\n'
        f'Their comment: "{comment_text}"\n\n'
        "Reply the way you'd actually type it on your phone."
    )

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        temperature=1.0,  # variety — identical phrasing across replies reads as a bot
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    reply = msg.content[0].text.strip().strip('"')
    return _dehumanize_guard(reply)


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

    own_channel_id = _get_own_channel_id(yt)
    if own_channel_id:
        print(f"  Own channel ID: {own_channel_id}")
    else:
        print("  Warning: could not resolve own channel ID — self-reply filter may be incomplete")

    # Gather candidate comments across all recent videos
    candidates: list[tuple[dict, str, str]] = []  # (item, video_id, video_title)
    for vid in video_ids:
        items = _fetch_top_comments(yt, vid, replied_ids, own_channel_id=own_channel_id)
        for item in items:
            candidates.append((item, vid, vid))  # real title filled in below

    # Fetch video titles for context
    if candidates:
        vid_ids_needed = list({c[1] for c in candidates})
        try:
            vresp = yt.videos().list(part="snippet", id=",".join(vid_ids_needed)).execute()
            title_map = {v["id"]: v["snippet"]["title"] for v in vresp.get("items", [])}
        except Exception:
            title_map = {}
        candidates = [(item, vid, title_map.get(vid, "Stoic wisdom")) for item, vid, _ in candidates]

    # Sort all candidates globally by score. Keep a wider pool than
    # MAX_REPLIES_PER_RUN because the receptivity screen (below) will skip
    # non-believers, and we still want to reach the reply quota with the
    # genuine ones.
    candidates.sort(key=lambda x: _score_comment(x[0]), reverse=True)
    candidates = candidates[:max(MAX_REPLIES_PER_RUN * 6, 30)]

    if not candidates:
        print("  No suitable comments found this run.")
        return

    already = _replies_today()
    budget = min(MAX_REPLIES_PER_RUN, MAX_REPLIES_PER_DAY - already)
    if budget <= 0:
        print(f"  Daily reply budget used ({already}/{MAX_REPLIES_PER_DAY}) — "
              f"skipping to protect YouTube API quota.")
        return
    print(f"  Reply budget this run: {budget} ({already}/{MAX_REPLIES_PER_DAY} used today)")

    replied = 0
    for item, video_id, video_title in candidates:
        if replied >= budget:
            break
        comment_id  = item["snippet"]["topLevelComment"]["id"]
        comment_txt = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"].strip()
        author      = item["snippet"]["topLevelComment"]["snippet"].get("authorDisplayName", "viewer")
        likes       = item["snippet"]["topLevelComment"]["snippet"].get("likeCount", 0)

        print(f"\n  Comment ({likes} likes) by {author}:")
        print(f"    \"{comment_txt[:120]}{'...' if len(comment_txt) > 120 else ''}\"")

        # Only engage viewers who genuinely connect with the message.
        if not _is_receptive(comment_txt):
            print("  [screen] not receptive to the message — skipping (no reply)")
            continue

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
