"""
Pull stats for the channel's recent uploads via the YouTube Data API and append
to data/analytics.csv. Free: videos.list and playlistItems.list cost ~1 unit each.

Strategy (quota-cheap, no expensive search.list):
  1. channels.list -> get the "uploads" playlist id (1 unit)
  2. playlistItems.list -> recent video ids from that playlist (1 unit)
  3. videos.list (statistics) -> views/likes/comments for those ids (1 unit)
"""
import os
import csv
import datetime
from pathlib import Path

TOKEN_URI = "https://oauth2.googleapis.com/token"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "analytics.csv"
FIELDS = ["pulled_on", "published_at", "video_id", "title",
          "views", "likes", "comments", "url"]
MAX_VIDEOS = 15


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def fetch_recent():
    yt = _service()
    ch = yt.channels().list(part="contentDetails", mine=True).execute()
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = yt.playlistItems().list(
        part="contentDetails,snippet", playlistId=uploads,
        maxResults=MAX_VIDEOS,
    ).execute()
    vids = [(i["contentDetails"]["videoId"],
             i["snippet"]["title"],
             i["contentDetails"].get("videoPublishedAt", ""))
            for i in items.get("items", [])]
    if not vids:
        return []

    stats = yt.videos().list(
        part="statistics", id=",".join(v[0] for v in vids),
    ).execute()
    smap = {s["id"]: s.get("statistics", {}) for s in stats.get("items", [])}

    rows = []
    for vid, title, pub in vids:
        s = smap.get(vid, {})
        rows.append({
            "video_id": vid, "title": title, "published_at": pub,
            "views": s.get("viewCount", ""),
            "likes": s.get("likeCount", ""),
            "comments": s.get("commentCount", ""),
            "url": f"https://youtube.com/shorts/{vid}",
        })
    return rows


def append_rows(rows):
    new = not OUT.exists()
    pulled = datetime.date.today().isoformat()
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            r["pulled_on"] = pulled
            w.writerow(r)


CHANNEL_STATS = ROOT / "data" / "channel_stats.csv"


def snapshot_channel_stats():
    """Daily channel-level snapshot: subscribers + lifetime views + video count.

    Powers the monetization-goal tracker (500 subs + 3M Shorts views/90d):
    the report reads this series to show progress and required run-rate.
    Costs 1 API unit. Best-effort — never fails the analytics pull.
    """
    try:
        yt = _service()
        ch = yt.channels().list(part="statistics", mine=True).execute()
        s = ch["items"][0]["statistics"]
        new = not CHANNEL_STATS.exists()
        with open(CHANNEL_STATS, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pulled_on", "subscribers",
                                              "total_views", "videos"])
            if new:
                w.writeheader()
            w.writerow({
                "pulled_on": datetime.date.today().isoformat(),
                "subscribers": s.get("subscriberCount", ""),
                "total_views": s.get("viewCount", ""),
                "videos": s.get("videoCount", ""),
            })
        print(f"Channel stats: {s.get('subscriberCount','?')} subs, "
              f"{s.get('viewCount','?')} lifetime views")
    except Exception as e:
        print(f"[channel-stats] snapshot failed ({e}); continuing", flush=True)


def main():
    rows = fetch_recent()
    append_rows(rows)
    print(f"Wrote {len(rows)} analytics rows to {OUT.name}")
    snapshot_channel_stats()


if __name__ == "__main__":
    main()
