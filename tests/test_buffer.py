"""Echo through Buffer (owner 2026-11-07: "how can i connect this to
insagram withoiut goign though meta developers?"; then "BUFFER_API_KEY is
added"). src/buffer_ig.py talks to Buffer's GraphQL API; scripts/echo.py
posts each new Short as a Reel through it, and deletes the hosted video only
once Buffer has sent the Reel."""
import datetime as dt
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import buffer_ig as bf  # noqa: E402
import echo  # noqa: E402

KEY = "bufkey_SECRET_123"
NOW = dt.datetime(2026, 11, 7, 23, 0, tzinfo=dt.timezone.utc)


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _server(answers):
    """A fake Buffer: answers[name of the operation] -> (status, body); records each call."""
    calls = []

    def post(url, json=None, headers=None, timeout=None):  # noqa: A002
        op = json["query"].split("(")[0].split("{")[0].split()[-1]
        calls.append({"url": url, "op": op, "variables": json.get("variables"), "headers": headers})
        status, body = answers[op](json.get("variables")) if callable(answers[op]) else answers[op]
        return _Resp(status, body)
    return post, calls


ORGS = (200, {"data": {"account": {"organizations": [{"id": "org1", "name": "Mine"}]}}})


def _channels(*chs):
    return (200, {"data": {"channels": list(chs)}})


IG = {"id": "ch_ig", "name": "forged.in.stoicism", "displayName": "Forged in Stoicism", "service": "instagram",
      "isDisconnected": False, "isLocked": False, "externalLink": "https://instagram.com/forged.in.stoicism",
      "organizationId": "org1"}


# ------------------------------------------------------------- the API

def test_the_key_goes_as_a_bearer_token_and_never_into_an_error(monkeypatch):
    post, calls = _server({"Orgs": (401, {"errors": [{"message": "Unauthorized",
                                                        "extensions": {"code": "UNAUTHORIZED"}}]})})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.instagram_channel(KEY)
    assert calls[0]["url"] == "https://api.buffer.com"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {KEY}"
    assert e.value.key_rejected and e.value.owners_to_fix and KEY not in str(e.value)


def test_echo_finds_the_connected_instagram_channel(monkeypatch):
    twitter = {**IG, "id": "ch_x", "service": "twitter"}
    locked = {**IG, "id": "ch_old", "isLocked": True}
    post, calls = _server({"Orgs": ORGS, "Channels": _channels(twitter, locked, IG)})
    monkeypatch.setattr(bf.requests, "post", post)
    assert bf.instagram_channel(KEY)["id"] == "ch_ig"
    assert calls[1]["variables"] == {"organizationId": "org1"}
    post, _ = _server({"Orgs": ORGS, "Channels": _channels(twitter)})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.instagram_channel(KEY)
    assert e.value.code == "NO_CHANNEL" and e.value.owners_to_fix
    post, _ = _server({"Orgs": ORGS, "Channels": _channels(locked)})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.instagram_channel(KEY)
    assert e.value.code == "DISCONNECTED"


def test_a_reel_is_shared_now_to_the_feed_from_the_hosted_url(monkeypatch):
    post, calls = _server({"Reel": (200, {"data": {"createPost": {"post": {"id": "p1", "status": "sending"}}}})})
    monkeypatch.setattr(bf.requests, "post", post)
    assert bf.create_reel(KEY, "ch_ig", "caption", "https://x/v.mp4")["id"] == "p1"
    inp = calls[0]["variables"]["input"]
    assert inp == {"channelId": "ch_ig", "text": "caption", "mode": "shareNow", "schedulingType": "automatic",
                   "assets": [{"video": {"url": "https://x/v.mp4"}}],
                   "metadata": {"instagram": {"type": "reel", "shouldShareToFeed": True}}}
    post, _ = _server({"Reel": (200, {"data": {"createPost": {"message": "Failed to fetch video: Not Found"}}})})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.create_reel(KEY, "ch_ig", "caption", "https://x/v.mp4")
    assert "Failed to fetch video" in e.value.message and not e.value.owners_to_fix


def test_a_post_is_read_back_across_pages(monkeypatch):
    pages = {None: {"edges": [{"node": {"id": "p0", "status": "sent"}}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
             "c1": {"edges": [{"node": {"id": "p1", "status": "sent", "externalLink": "https://instagram.com/reel/A"}}],
                    "pageInfo": {"hasNextPage": False}}}
    post, calls = _server({"Posts": lambda v: (200, {"data": {"posts": pages[v["after"]]}})})
    monkeypatch.setattr(bf.requests, "post", post)
    assert bf.post_state(KEY, "org1", "ch_ig", "p1")["externalLink"] == "https://instagram.com/reel/A"
    assert calls[0]["variables"]["input"] == {"organizationId": "org1", "filter": {"channelIds": ["ch_ig"]}}
    assert bf.post_state(KEY, "org1", "ch_ig", "nope") is None


# ------------------------------------------------------------- Echo's shift

@pytest.fixture()
def data(tmp_path, monkeypatch):
    for name in ("STATUS", "POSTS", "STATS", "REELS"):
        monkeypatch.setattr(echo, name, tmp_path / Path(getattr(echo, name)).name)
    monkeypatch.setattr(echo, "TIKTOK_POSTS", tmp_path / "tiktok_posts.csv")
    monkeypatch.setenv("BUFFER_API_KEY", KEY)
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    monkeypatch.setattr(echo.time, "sleep", lambda s: None)
    # TikTok isn't connected unless a test says so (no network in tests)
    monkeypatch.setattr(bf, "tiktok_channel", lambda key: (_ for _ in ()).throw(
        bf.BufferError(200, "Buffer has no TikTok channel connected", "NO_CHANNEL")))
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"mp4")
    return {"tmp": tmp_path, "video": str(video)}


def _handed(data, vid="yt1"):
    return [{"video_id": vid, "date": "2026-11-07", "igCaption": "the caption", "video": data["video"],
             "hook": "Stay calm"}]


def test_a_shift_posts_through_buffer_and_keeps_the_reels_link(data):
    deleted, hosted = [], []
    with patch.object(bf, "instagram_channel", return_value=IG), \
         patch.object(echo, "handed_over", return_value=_handed(data)), \
         patch.object(echo.ig, "_host_via_github_release",
                      side_effect=lambda p: hosted.append(p.name) or ("https://gh/v.mp4", "me/repo", 77)), \
         patch.object(echo.ig, "_delete_asset", side_effect=lambda repo, a: deleted.append(a)), \
         patch.object(bf, "create_reel", return_value={"id": "p1", "status": "sending"}) as made, \
         patch.object(bf, "post_state", side_effect=[{"id": "p1", "status": "sending"},
                                                     {"id": "p1", "status": "sent",
                                                      "externalLink": "https://instagram.com/reel/A"}]):
        assert echo.shift(now=NOW) == 0
    assert made.call_args[0] == (KEY, "ch_ig", "the caption", "https://gh/v.mp4")
    assert hosted == ["yt1.mp4"] and deleted == [77]          # its own name; deleted once sent
    row = echo._read(echo.POSTS)[0]
    assert (row["status"], row["permalink"], row["via"], row["buffer_id"], row["asset_id"]) == \
        ("published", "https://instagram.com/reel/A", "buffer", "p1", "")
    st = json.loads(echo.STATUS.read_text())
    assert st["ok"] and st["via"] == "buffer" and st["account"]["username"] == "forged.in.stoicism"
    assert st["lastPost"]["permalink"] == "https://instagram.com/reel/A" and "key" not in st
    assert KEY not in echo.STATUS.read_text()


def test_a_reel_still_going_out_is_settled_by_the_next_shift(data):
    with patch.object(bf, "instagram_channel", return_value=IG), \
         patch.object(echo, "handed_over", return_value=_handed(data)), \
         patch.object(echo.ig, "_host_via_github_release", return_value=("https://gh/v.mp4", "me/repo", 77)), \
         patch.object(echo.ig, "_delete_asset") as dele, \
         patch.object(bf, "create_reel", return_value={"id": "p1", "status": "sending"}), \
         patch.object(bf, "post_state", return_value={"id": "p1", "status": "sending"}):
        assert echo.shift(now=NOW) == 0
        assert echo._read(echo.POSTS)[0]["status"] == "queued" and not dele.called   # the video stays up
    with patch.object(bf, "instagram_channel") as again, \
         patch.object(echo, "handed_over", return_value=_handed(data)), \
         patch.object(echo.ig, "_delete_asset") as dele, \
         patch.object(bf, "create_reel") as made, \
         patch.object(bf, "post_state", return_value={"id": "p1", "status": "sent",
                                                      "externalLink": "https://instagram.com/reel/A"}):
        assert echo.shift(now=NOW + dt.timedelta(minutes=40)) == 0      # same day
    assert not again.called and not made.called                # channel kept for the day; never posted twice
    assert dele.call_args[0] == ("me/repo", 77)
    assert echo._read(echo.POSTS)[0]["status"] == "published"
    assert json.loads(echo.STATUS.read_text())["lastPost"]["status"] == "published"


def test_a_reel_buffer_could_not_send_fails_the_shift_and_cleans_up(data):
    with patch.object(bf, "instagram_channel", return_value=IG), \
         patch.object(echo, "handed_over", return_value=_handed(data)), \
         patch.object(echo.ig, "_host_via_github_release", return_value=("https://gh/v.mp4", "me/repo", 77)), \
         patch.object(echo.ig, "_delete_asset") as dele, \
         patch.object(bf, "create_reel", return_value={"id": "p1", "status": "sending"}), \
         patch.object(bf, "post_state", return_value={"id": "p1", "status": "error",
                                                      "error": {"message": "Video too long for a Reel"}}):
        assert echo.shift(now=NOW) == 1                            # the HQ shows Echo failed
    row = echo._read(echo.POSTS)[0]
    assert row["status"] == "failed" and row["reason"] == "Video too long for a Reel" and dele.called


def test_a_refused_post_never_leaves_the_video_hosted(data):
    with patch.object(bf, "instagram_channel", return_value=IG), \
         patch.object(echo, "handed_over", return_value=_handed(data)), \
         patch.object(echo.ig, "_host_via_github_release", return_value=("https://gh/v.mp4", "me/repo", 77)), \
         patch.object(echo.ig, "_delete_asset") as dele, \
         patch.object(bf, "create_reel", side_effect=bf.BufferError(200, "Failed to fetch video", "MUTATION")):
        assert echo.shift(now=NOW) == 1
    assert dele.call_args[0] == ("me/repo", 77)
    assert echo._read(echo.POSTS)[0]["reason"] == "Buffer: Failed to fetch video"


def test_no_instagram_in_buffer_is_the_owners_to_fix(data):
    with patch.object(bf, "instagram_channel", side_effect=bf.BufferError(200, "none", "NO_CHANNEL")), \
         patch.object(echo, "handed_over") as handed:
        assert echo.shift(now=NOW) == 0
    st = json.loads(echo.STATUS.read_text())
    assert st["ok"] is False and st["ownerAction"] is True and "connect the channel's Instagram" in st["problem"]
    assert not handed.called


def test_a_post_buffer_lost_is_given_up_after_two_days(data):
    echo._rewrite(echo.POSTS, echo.POST_FIELDS, [{"tried_at": "2026-11-05T01:00:00Z", "youtube_id": "yt0",
                                                  "status": "queued", "via": "buffer", "buffer_id": "p0",
                                                  "asset_id": "70"}])
    with patch.object(bf, "instagram_channel", return_value=IG), \
         patch.object(echo, "handed_over", return_value=[]), \
         patch.object(echo.ig, "_delete_asset") as dele, \
         patch.object(bf, "post_state", return_value=None):
        assert echo.shift(now=NOW) == 0
    row = echo._read(echo.POSTS)[0]
    assert row["status"] == "failed" and row["reason"] == "Buffer no longer lists the post"
    assert dele.call_args[0] == ("me/repo", 70)


def test_buffer_comes_first_and_the_job_passes_its_key():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "instagram.yml").read_text())
    env = next(s for s in wf["jobs"]["echo"]["steps"] if s.get("name") == "Echo's shift")["env"]
    assert env["BUFFER_API_KEY"] == "${{ secrets.BUFFER_API_KEY }}"
    assert "IG_USER_ID" not in env              # the broken one hid every "e" and "d" in the logs
    assert echo.to_post([{"youtube_id": "a", "status": "queued"}], [{"video_id": "a"}]) is None   # never twice


def test_settle_reads_back_what_is_going_out_and_posts_nothing_new(data):
    echo._rewrite(echo.POSTS, echo.POST_FIELDS, [{"tried_at": "2026-11-07T23:06:24Z", "youtube_id": "yt0",
                                                  "status": "queued", "via": "buffer", "buffer_id": "p0",
                                                  "asset_id": "70"}])
    with patch.object(bf, "instagram_channel", return_value=IG), \
         patch.object(echo, "handed_over", return_value=_handed(data)) as handed, \
         patch.object(echo.ig, "_delete_asset") as dele, \
         patch.object(bf, "create_reel") as made, \
         patch.object(bf, "post_state", return_value={"id": "p0", "status": "sent",
                                                      "externalLink": "https://instagram.com/reel/B"}):
        assert echo.shift("settle", now=NOW + dt.timedelta(minutes=10)) == 0
    assert not made.called and not handed.called
    row = echo._read(echo.POSTS)[0]
    assert row["status"] == "published" and row["permalink"] == "https://instagram.com/reel/B"
    assert dele.call_args[0] == ("me/repo", 70)
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "instagram.yml").read_text())
    assert wf[True]["workflow_dispatch"]["inputs"]["mode"]["options"] == ["run", "check", "settle"]



# ------------------------------------------------------------- TikTok (owner 2026-11-13)

TT = {**IG, "id": "ch_tt", "name": "forged.in.stoicism", "service": "tiktok"}
CREATED = lambda: (200, {"data": {"createPost": {"post": {"id": "t1", "status": "sending"}}}})  # noqa: E731


def test_echo_finds_the_connected_tiktok_channel_and_not_instagram(monkeypatch):
    post, calls = _server({"Orgs": ORGS, "Channels": _channels(IG, TT)})
    monkeypatch.setattr(bf.requests, "post", post)
    assert bf.tiktok_channel(KEY)["id"] == "ch_tt" and bf.instagram_channel(KEY)["id"] == "ch_ig"
    post, _ = _server({"Orgs": ORGS, "Channels": _channels(IG)})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.tiktok_channel(KEY)
    assert e.value.code == "NO_CHANNEL" and "TikTok" in e.value.message
    post, _ = _server({"Orgs": ORGS, "Channels": _channels({**TT, "isDisconnected": True})})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.tiktok_channel(KEY)
    assert e.value.code == "DISCONNECTED"


def test_a_tiktok_is_shared_now_from_the_hosted_url_with_no_metadata_first(monkeypatch):
    post, calls = _server({"Reel": lambda v: CREATED()})
    monkeypatch.setattr(bf.requests, "post", post)
    made = bf.create_tiktok(KEY, "ch_tt", "https://gh/v.mp4", "Line one\n\nmore")
    assert made["id"] == "t1" and len(calls) == 1
    inp = calls[0]["variables"]["input"]
    assert inp["channelId"] == "ch_tt" and inp["mode"] == "shareNow" and inp["schedulingType"] == "automatic"
    assert inp["assets"] == [{"video": {"url": "https://gh/v.mp4"}}] and "metadata" not in inp


def test_a_tiktok_buffer_wants_metadata_for_is_retried_once_with_a_title(monkeypatch):
    seen = []

    def answer(v):
        seen.append(v["input"].get("metadata"))
        if len(seen) == 1:
            return 200, {"errors": [{"message": "Field metadata.tiktok is required"}]}
        return CREATED()
    post, calls = _server({"Reel": answer})
    monkeypatch.setattr(bf.requests, "post", post)
    made = bf.create_tiktok(KEY, "ch_tt", "https://gh/v.mp4", "x" * 120 + "\nsecond line")
    assert made["id"] == "t1" and seen == [None, {"tiktok": {"title": "x" * 90}}]


def test_a_tiktok_refused_twice_raises_buffers_words_never_the_key(monkeypatch):
    post, calls = _server({"Reel": lambda v: (200, {"errors": [{"message": "TikTok needs a privacy level"}]})})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.create_tiktok(KEY, "ch_tt", "https://gh/v.mp4", "caption")
    assert len(calls) == 2 and "privacy level" in str(e.value) and KEY not in str(e.value)
    assert all(KEY not in json.dumps(c["variables"]) for c in calls)
    # an error that has nothing to do with TikTok or metadata is not retried
    post, calls = _server({"Reel": lambda v: (200, {"errors": [{"message": "Failed to fetch video"}]})})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError):
        bf.create_tiktok(KEY, "ch_tt", "https://gh/v.mp4", "caption")
    assert len(calls) == 1
    # a refused key
    post, _ = _server({"Reel": lambda v: (401, {"errors": [{"message": "Unauthorized"}]})})
    monkeypatch.setattr(bf.requests, "post", post)
    with pytest.raises(bf.BufferError) as e:
        bf.create_tiktok(KEY, "ch_tt", "https://gh/v.mp4", "caption")
    assert e.value.key_rejected and KEY not in str(e.value)


def test_the_tiktok_caption():
    import tiktok_caption as tc
    cap = tc.tiktok_caption({"hook": "Stay calm.", "quote": "You have power over your mind.",
                             "author": "Marcus Aurelius", "citation": "Meditations 8.47",
                             "hashtags": ["shorts", "stoicism", "stoic", "#a", "b", "c", "d"],
                             "igCaption": "x #seneca #stoic"})
    assert cap.startswith("Stay calm.\n\n“You have power over your mind.”\n— Marcus Aurelius, Meditations 8.47")
    assert "Follow for one Stoic line a day." in cap and "#shorts" not in cap.lower() and "http" not in cap
    assert len([w for w in cap.split() if w.startswith("#")]) == 5
    assert len(tc.tiktok_caption({"hook": "h", "quote": "q" * 5000})) <= 2200
    assert "#stoicism" in tc.tiktok_caption({"quote": "q"})        # defaults when the post carries none
