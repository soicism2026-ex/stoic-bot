"""
Adopt the Shorts the owner posted from the YouTube app (assisted posting).

The owner posts each queued video himself so he can add the trending song in
the app (src/assist.py). Everything the app does not do, this does, every 30
minutes (adopt.yml):
  * finds his new upload and matches it to the queued video (the title he
    pasted, else the video's length and timing);
  * sets the description (quote, citation, journal link, hashtags) and tags,
    keeping his title unless it is blank;
  * sets the thumbnail and posts the engagement comment (+ promo comment);
  * writes the posts.csv row that analytics, pruning, replies and content
    rotation all depend on;
  * removes it from the queue and deletes its release, so the Releases page
    only ever lists videos still waiting to be posted.

    python scripts/adopt_uploads.py            # adopt
    python scripts/adopt_uploads.py --dry-run  # show matches, change nothing
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import assist                               # noqa: E402
import promo                                # noqa: E402
from logbook import LOG, log_post           # noqa: E402
from publish import CATEGORY_ID, _service, post_comment, set_thumbnail  # noqa: E402

FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"


def recent_uploads(yt, n: int = 25) -> list[dict]:
    ch = yt.channels().list(part="contentDetails", mine=True).execute()
    playlist = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="contentDetails", playlistId=playlist,
                                    maxResults=n).execute().get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    vids = yt.videos().list(part="snippet,contentDetails,status",
                            id=",".join(ids)).execute().get("items", [])
    return [{"video_id": v["id"], "title": v["snippet"].get("title", ""),
             "published_at": v["snippet"].get("publishedAt", ""),
             "duration": assist.parse_duration(v["contentDetails"].get("duration", "")),
             "privacy": v.get("status", {}).get("privacyStatus", ""),
             "snippet": v["snippet"]} for v in vids]


def logged_ids() -> set:
    if not LOG.exists():
        return set()
    with open(LOG, newline="", encoding="utf-8") as f:
        return {r.get("video_id", "") for r in csv.DictReader(f)} - {""}


def adopt(yt, p: dict, u: dict) -> None:
    vid = u["video_id"]
    sn = u["snippet"]
    # His title wins (he pasted ours, or chose his own) unless he left it
    # blank or near-blank.
    title = sn.get("title", "")
    if len(assist._norm(title).split()) < 3:
        title = p["title"]
    description = p["description"]
    if "#shorts" not in description.lower():
        description += "\n\n#Shorts"
    snippet = {"title": title[:100], "description": description[:4900],
               "tags": [t.lstrip("#") for t in p.get("tags", [])][:15],
               "categoryId": sn.get("categoryId") or CATEGORY_ID}
    for keep in ("defaultLanguage", "defaultAudioLanguage"):
        if sn.get(keep):
            snippet[keep] = sn[keep]
    try:
        yt.videos().update(part="snippet", body={"id": vid, "snippet": snippet}).execute()
        print(f"  [adopt] {vid}: description, tags set")
    except Exception as e:  # noqa: BLE001
        print(f"  [adopt] {vid}: metadata update failed ({e})", file=sys.stderr)
    thumb = assist.DIR / f"{p['id']}.jpg"
    if thumb.exists():
        set_thumbnail(vid, thumb)
    for text in (p.get("pinned_comment", "").strip(), promo.comment_text()):
        if text:
            try:
                post_comment(vid, text)
            except Exception as e:  # noqa: BLE001
                print(f"  [adopt] {vid}: comment skipped ({e})", file=sys.stderr)
    log_post(
        date=(u.get("published_at") or p["date"])[:10], theme=p["theme"],
        quote=p["quote"], author=p["author"], caption=description,
        publish_result={"url": f"https://youtube.com/shorts/{vid}", "video_id": vid},
        voice_name=p.get("voice_name", ""), music_track=p.get("music_track", ""),
        hook=p.get("hook", ""), experiment=p.get("experiment", ""),
        content_format=p.get("format", ""), bg_source=p.get("bg_source", ""),
        reviewed=p.get("reviewed", ""))
    assist.remove(p["id"])
    subprocess.run(["gh", "release", "delete", f"edit-{p['id']}", "--yes", "--cleanup-tag"],
                   capture_output=True, text=True)
    print(f"  [adopt] {p['id']} -> https://youtube.com/shorts/{vid} logged")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    pending = assist.load()
    adopted = 0
    if not pending:
        print("[adopt] nothing waiting to be posted")
    else:
        yt = _service(extra_scopes=[FORCE_SSL])
        uploads = recent_uploads(yt)
        pairs = assist.match(pending, uploads, logged_ids())
        print(f"[adopt] {len(pending)} waiting, {len(uploads)} recent uploads, "
              f"{len(pairs)} matched")
        for p, u in pairs:
            print(f"  {p['id']}  <-  {u['video_id']}  \"{u['title'][:60]}\"  {u['duration']:.0f}s")
            if not a.dry_run:
                adopt(yt, p, u)
                adopted += 1
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"adopted={adopted}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
