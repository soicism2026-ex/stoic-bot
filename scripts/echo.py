"""
Echo, the Instagram crew member (owner 2026-10-28: "lets work on the
instagram account now ... and get people to run that aswell").

Echo's shift (.github/workflows/instagram.yml: after every Producer run, plus
a daily backstop):

  1. the key: IG_ACCESS_TOKEN from GitHub, or the refreshed key Echo keeps
     (src/ig_key.py), checked against Instagram before anything else
  2. post: every Short the Producer put on YouTube in the last 36 hours that
     isn't on Instagram yet, oldest first, one per shift. daily-short hands
     each upload over as the `posted-short` artifact: the video and its
     Instagram caption (data/posted/<video id>/)
  3. keep the key alive: refresh it about weekly (a key lasts 60 days)
  4. numbers, once a day: followers, and each recent Reel's views and reach

It writes data/ig_status.json (what the HQ shows), data/ig_posts.csv (every
attempt), data/ig_stats.csv (followers by day) and data/ig_reels.csv (each
Reel's numbers by day). It exits 0 when the problem is on the owner's side
(no key, a refused key: the HQ asks him for a new one) and 1 when a post
failed with a working key (the HQ shows Echo failed, and Claude looks).

    python scripts/echo.py           # a full shift
    python scripts/echo.py check     # the key and the account only
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import ig_key  # noqa: E402
import publish_instagram as ig  # noqa: E402

DATA = ROOT / "data"
STATUS = DATA / "ig_status.json"
POSTS = DATA / "ig_posts.csv"
STATS = DATA / "ig_stats.csv"
REELS = DATA / "ig_reels.csv"
API = "https://api.github.com"
ARTIFACT = "posted-short"
WINDOW_HOURS = 36       # how far back a Short still goes to Instagram
MAX_TRIES = 3           # failed attempts before Echo gives up on one Short
NUMBERS_DAYS = 30       # Reels whose numbers are pulled daily
METRICS = "views,reach,likes,comments,shares,saved"
POST_FIELDS = ["tried_at", "date", "youtube_id", "ig_media_id", "permalink", "status", "reason"]
STATS_FIELDS = ["pulled_on", "username", "followers", "media_count"]
REEL_FIELDS = ["pulled_on", "ig_media_id", "youtube_id", "views", "reach", "likes", "comments",
               "shares", "saved"]


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append(path: Path, fields: list[str], row: dict) -> None:
    new = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def load_status() -> dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_status(st: dict) -> None:
    STATUS.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def id_advice(uid: str) -> str | None:
    """IG_USER_ID is only for an old Facebook Login key. When it isn't a plain
    number it is junk, and a secret pasted across lines makes GitHub blank
    every single letter on its lines out of the logs of any job that reads it
    (2026-10-28: Echo's key had no line breaks, yet his log lost every e and d)."""
    uid = uid.strip()
    if uid and not uid.isdigit():
        return ("IG_USER_ID in GitHub isn't a plain number (it looks pasted across lines). "
                "The new key doesn't need it: delete it.")
    return None


def plain(e: ig.IGError) -> str:
    """Meta's refusal in words the owner reads in the HQ."""
    if e.key_rejected:
        return f"Instagram refused the key ({e.message}). It needs a new one."
    if "IG_USER_ID" in e.message:
        return ("The Instagram key in GitHub is the old kind, and the IG_USER_ID it needs is broken. "
                "A new key fixes both: the steps are under Needs your call.")
    if e.status == 0:
        return f"Couldn't check Instagram: {e.message}."
    return f"Instagram refused the key check: {e.message}"


# ------------------------------------------------------------- the hand-over

def _gh() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def handed_over(now: dt.datetime, work: Path) -> list[dict]:
    """The Shorts uploaded in the last WINDOW_HOURS, from daily-short's
    posted-short artifacts: each post.json plus "video", the local file.
    Oldest first. [] when GitHub can't be asked (no token outside Actions)."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not (repo and os.environ.get("GITHUB_TOKEN")):
        return []
    try:
        r = requests.get(f"{API}/repos/{repo}/actions/artifacts", headers=_gh(), timeout=30,
                         params={"name": ARTIFACT, "per_page": 30})
        r.raise_for_status()
        arts = r.json().get("artifacts") or []
    except Exception as e:  # noqa: BLE001
        print(f"  [echo] couldn't list the Producer's hand-overs: {type(e).__name__}", file=sys.stderr)
        return []
    out = []
    for a in arts:
        try:
            made = dt.datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if a.get("expired") or now - made > dt.timedelta(hours=WINDOW_HOURS):
            continue
        d = work / f"a{a['id']}"
        try:
            if not d.exists():
                z = requests.get(a["archive_download_url"], headers=_gh(), timeout=180)
                z.raise_for_status()
                zipfile.ZipFile(io.BytesIO(z.content)).extractall(d)
        except Exception as e:  # noqa: BLE001
            print(f"  [echo] couldn't open hand-over {a['id']}: {type(e).__name__}", file=sys.stderr)
            continue
        for pj in sorted(d.rglob("post.json")):
            try:
                post = json.loads(pj.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            video = pj.parent / str(post.get("video") or "reel.mp4")
            if post.get("video_id") and video.exists():
                out.append({**post, "video": str(video)})
    seen, uniq = set(), []
    for p in sorted(out, key=lambda p: p.get("uploadedAt") or ""):
        if p["video_id"] not in seen:
            seen.add(p["video_id"])
            uniq.append(p)
    return uniq


def to_post(log: list[dict], handed: list[dict]) -> dict | None:
    """The oldest handed-over Short not yet on Instagram, unless it already
    failed MAX_TRIES times."""
    done = {r.get("youtube_id") for r in log if r.get("status") == "published"}
    tries = Counter(r.get("youtube_id") for r in log if r.get("status") == "failed")
    for p in handed:
        if p["video_id"] not in done and tries[p["video_id"]] < MAX_TRIES:
            return p
    return None


# ------------------------------------------------------------- the numbers

def _value(metric: dict):
    vals = metric.get("values") or []
    if vals and isinstance(vals[0], dict) and "value" in vals[0]:
        return vals[0]["value"]
    return (metric.get("total_value") or {}).get("value")


def pull_numbers(token: str, acct: dict, log: list[dict], today: dt.date, st: dict) -> None:
    """Once a day: followers, and the numbers of every Reel from the last
    NUMBERS_DAYS days (Instagram's numbers lag up to 48 hours)."""
    day = today.isoformat()
    if any(r.get("pulled_on") == day for r in _read(STATS)):
        return
    _append(STATS, STATS_FIELDS, {"pulled_on": day, "username": acct.get("username"),
                                  "followers": acct.get("followers"), "media_count": acct.get("mediaCount")})
    cutoff = (today - dt.timedelta(days=NUMBERS_DAYS)).isoformat()
    st.pop("numbersProblem", None)
    for r in log:
        if r.get("status") != "published" or not r.get("ig_media_id") or (r.get("date") or "") < cutoff:
            continue
        try:
            got = ig._call("GET", f"{ig.base(token)}/{r['ig_media_id']}/insights", token, metric=METRICS)
        except ig.IGError as e:
            st["numbersProblem"] = f"Instagram won't share the Reels' numbers: {e.message}"
            return
        vals = {m.get("name"): _value(m) for m in got.get("data") or []}
        _append(REELS, REEL_FIELDS, {"pulled_on": day, "ig_media_id": r["ig_media_id"],
                                     "youtube_id": r.get("youtube_id"), **vals})


# ------------------------------------------------------------- the shift

def shift(mode: str = "run", now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date()
    st = load_status()
    st["checked"] = _iso(now)
    st["advice"] = id_advice(os.environ.get("IG_USER_ID", ""))
    if st["advice"]:
        print(f"Echo: {st['advice']}")
    key = dict(st.get("key") or {})
    seed = os.environ.get("IG_ACCESS_TOKEN", "")
    bad = ig_key.problem_with(seed)
    if bad:
        st.update(ok=False, problem=bad, key=key)
        save_status(st)
        print(f"Echo: {bad}")
        return 0
    seed = seed.strip()
    fp = ig_key.fingerprint(seed)
    if key.get("fingerprint") != fp:            # a new key from the owner: start over
        key = {"fingerprint": fp, "firstSeen": today.isoformat()}
    token, source = ig_key.load(seed)
    ig_user = os.environ.get("IG_USER_ID", "").strip()
    try:
        acct = ig.account(token, ig_user)
    except ig.IGError as e:
        acct, err = None, e
        if source == "kept":                    # the kept key failed: try the owner's own
            try:
                token, source = seed, "github"
                acct = ig.account(token, ig_user)
            except ig.IGError as e2:
                err = e2
        if acct is None:
            key.update(kind=ig.kind(token), source=source)
            st.update(ok=False, problem=plain(err), key=key)
            save_status(st)
            print(f"Echo: {plain(err)}")
            return 0
    key.update(kind=acct["kind"], source=source)
    st.update(ok=True, problem=None, account={k: acct.get(k) for k in
                                               ("username", "accountType", "followers", "mediaCount")})

    # Keep the key alive.
    if ig_key.due(key, today):
        key["lastTry"] = today.isoformat()
        try:
            new, secs = ig_key.refresh(token)
            key["sameString"] = new == token
            if new == token or ig_key.keep(new, seed):
                token, key["source"] = new, (key["source"] if new == token else "kept")
                key["refreshed"] = today.isoformat()
                key["expires"] = (today + dt.timedelta(seconds=secs)).isoformat()
                key.pop("lastError", None)
            else:
                key["lastError"] = "Instagram gave a new key, but Echo couldn't keep it"
        except ig.IGError as e:
            key["lastError"] = e.message
    key["expiresAround"] = ig_key.expires(key)

    failed = False
    if mode != "check":
        log = _read(POSTS)
        with tempfile.TemporaryDirectory() as td:
            post = to_post(log, handed_over(now, Path(td)))
            if post:
                text = post.get("igCaption") or ig.caption(
                    post.get("hook", ""), post.get("quote", ""), post.get("author", ""),
                    post.get("citation", ""), post.get("hashtags") or [])
                res = ig.publish_reel(Path(post["video"]), text, token=token, acct=acct)
                row = {"tried_at": _iso(now), "date": post.get("date") or today.isoformat(),
                       "youtube_id": post["video_id"], "ig_media_id": res.get("media_id"),
                       "permalink": res.get("permalink"), "status": res["status"],
                       "reason": res.get("reason")}
                _append(POSTS, POST_FIELDS, row)
                st["lastPost"] = {"at": row["tried_at"], "youtube": post["video_id"],
                                  "title": post.get("title") or post.get("hook"), "status": res["status"],
                                  "permalink": res.get("permalink"), "reason": res.get("reason")}
                failed = res["status"] != "published"
            else:
                print("Echo: nothing new to post.")
        pull_numbers(token, acct, _read(POSTS), today, st)

    st["key"] = key
    save_status(st)
    a = st["account"]
    print(f"Echo: @{a.get('username')} ({a.get('accountType') or acct['kind']}), "
          f"{a.get('followers')} followers; key from {key['source']}, "
          f"good until about {key.get('expiresAround')}"
          + (f"; refresh problem: {key['lastError']}" if key.get("lastError") else ""))
    return 1 if failed else 0


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ECHO_MODE", "run")) or "run"
    if mode not in ("run", "check"):
        print(__doc__)
        return 2
    return shift(mode)


if __name__ == "__main__":
    sys.exit(main())
