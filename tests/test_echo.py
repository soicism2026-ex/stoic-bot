"""Echo, the Instagram crew member (owner 2026-10-28: "lets work on the
instagram account now ... and get people to run that aswell").

The cross-post never once worked from June to October: the key was pasted
across several lines, nothing ever refreshed a key that lasts 60 days, and a
failure only showed up as blanked letters in the Producer's logs. These tests
pin the new design: Echo's own job, the hand-over from the Producer, the key
kept alive, and the HQ telling the owner exactly what blocks Echo."""
import datetime as dt
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import echo  # noqa: E402
import hq_snapshot as hq  # noqa: E402
import ig_key  # noqa: E402
import publish_instagram as ig  # noqa: E402

NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)
IG_KEY = "IGAA" + "x" * 150
WF = ROOT / ".github" / "workflows"


class _Resp:
    def __init__(self, ok=True, status=200, payload=None, content=b""):
        self.ok, self.status_code, self._payload, self.content = ok, status, payload or {}, content
        self.reason = "Bad Request" if not ok else "OK"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise ig.requests.HTTPError(f"{self.status_code} for url: https://x?access_token=SECRET")


@pytest.fixture()
def data(tmp_path, monkeypatch):
    for name in ("STATUS", "POSTS", "STATS", "REELS"):
        monkeypatch.setattr(echo, name, tmp_path / Path(getattr(echo, name)).name)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("IG_USER_ID", raising=False)
    monkeypatch.setattr(ig_key, "load", lambda seed: (seed.strip(), "github"))
    return tmp_path


# ------------------------------------------------------------- the key

def test_an_instagram_login_key_talks_to_graph_instagram_com():
    assert ig.kind(IG_KEY) == "instagram" and ig.base(IG_KEY) == "https://graph.instagram.com/v26.0"
    assert ig.kind("EAAB123") == "facebook" and ig.base("EAAB123").startswith("https://graph.facebook.com/")


def test_the_account_comes_from_me_with_an_instagram_key():
    seen = {}

    def req(method, url, params=None, timeout=None):
        seen.update(url=url, params=params)
        return _Resp(payload={"user_id": "1789", "id": "app-scoped", "username": "forged.in.stoicism",
                              "account_type": "BUSINESS", "followers_count": 12, "media_count": 3})
    with patch.object(ig.requests, "request", side_effect=req):
        acct = ig.account(IG_KEY)
    assert seen["url"].endswith("/me") and "user_id" in seen["params"]["fields"]
    assert acct["id"] == "1789" and acct["username"] == "forged.in.stoicism" and acct["followers"] == 12


def test_a_facebook_key_still_needs_ig_user_id():
    with pytest.raises(ig.IGError, match="IG_USER_ID"):
        ig.account("EAAB123", "")


def test_a_refusal_never_carries_the_key():
    """requests puts the URL, key included, in its exception text."""
    refused = _Resp(ok=False, status=400, payload={"error": {"message": "Cannot parse access token", "code": 190}})
    with patch.object(ig.requests, "request", return_value=refused):
        with pytest.raises(ig.IGError) as e:
            ig.account(IG_KEY)
    assert e.value.key_rejected and IG_KEY not in str(e.value)
    with patch.object(ig.requests, "request",
                      side_effect=ig.requests.ConnectionError(f"https://graph.instagram.com/me?access_token={IG_KEY}")):
        with pytest.raises(ig.IGError) as e:
            ig.account(IG_KEY)
    assert IG_KEY not in str(e.value) and e.value.status == 0


def test_a_pasted_key_with_line_breaks_is_caught_before_instagram_sees_it():
    """The 2026-10-21 key: pasted across lines, so GitHub masked every e and d."""
    assert ig_key.problem_with("") == "There's no Instagram key in GitHub yet."
    assert "one line" in ig_key.problem_with("IGAAabc\ne\nd")
    assert "one line" in ig_key.problem_with("IGAA abc")
    assert ig_key.problem_with(IG_KEY + "\n") is None             # a trailing newline is harmless


def test_the_key_is_refreshed_about_weekly_never_on_its_first_day():
    today = dt.date(2026, 10, 28)
    fresh = {"kind": "instagram", "firstSeen": "2026-10-28"}
    assert not ig_key.due(fresh, today)                            # Meta refuses keys under a day old
    assert ig_key.due({**fresh, "firstSeen": "2026-10-27"}, today)
    assert not ig_key.due({**fresh, "refreshed": "2026-10-25"}, today)
    assert ig_key.due({**fresh, "refreshed": "2026-10-21"}, today)
    assert not ig_key.due({**fresh, "refreshed": "2026-10-21", "lastTry": "2026-10-28"}, today)
    assert not ig_key.due({"kind": "facebook", "firstSeen": "2026-10-01"}, today)
    assert ig_key.expires({"firstSeen": "2026-10-28"}) == "2026-12-27"
    assert ig_key.expires({"firstSeen": "2026-10-28", "expires": "2027-01-03"}) == "2027-01-03"


def test_refreshing_asks_instagram_and_masks_the_new_key(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with patch.object(ig, "_call", return_value={"access_token": "IGAAnew", "expires_in": 5184000}) as c:
        new, secs = ig_key.refresh(IG_KEY)
    assert (new, secs) == ("IGAAnew", 5184000)
    assert c.call_args[0][1] == "https://graph.instagram.com/refresh_access_token"
    assert c.call_args[1] == {"grant_type": "ig_refresh_token"}
    assert "::add-mask::IGAAnew" in capsys.readouterr().out


@pytest.mark.skipif(not shutil.which("gpg"), reason="needs gpg")
def test_a_refreshed_key_is_kept_encrypted_with_the_owners_key(tmp_path, monkeypatch):
    """Only the ciphertext leaves the runner, and only the GitHub secret opens it."""
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    stored = {}

    def get(url, headers=None, timeout=None):
        return _Resp(payload={"id": 5, "assets": []})

    def post(url, headers=None, data=None, json=None, timeout=None):
        stored["bytes"] = data
        return _Resp(payload={"id": 9})
    with patch.object(ig_key.requests, "get", side_effect=get), \
         patch.object(ig_key.requests, "post", side_effect=post):
        assert ig_key.keep("IGAArefreshed", IG_KEY)
    assert b"IGAArefreshed" not in stored["bytes"]

    class _U:
        def __init__(self, b):
            self.b = b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.b
    with patch.object(ig_key.urllib.request, "urlopen", return_value=_U(stored["bytes"])):
        assert ig_key.load(IG_KEY) == ("IGAArefreshed", "kept")
        other = "IGAA" + "y" * 150                              # the owner pasted a new key
        assert ig_key.load(other) == (other, "github")
    with patch.object(ig_key.urllib.request, "urlopen", side_effect=OSError("404")):
        assert ig_key.load(IG_KEY) == (IG_KEY, "github")      # nothing kept yet


# ------------------------------------------------------------- the caption

def test_the_instagram_caption():
    text = ig.caption("Stop worrying about problems you don't have yet.",
                      "Let not future things disturb thee.", "Marcus Aurelius", "Meditations VII.8",
                      ["#stoicism", "#shorts", "#motivation", "#discipline", "#stoic", "#marcusaurelius",
                       "#philosophy", "stoicism"],
                      credit='Music: "Crusade" by Kevin MacLeod (incompetech.com), CC BY 4.0')
    lines = text.split("\n\n")
    assert lines[0] == "Stop worrying about problems you don't have yet."
    assert lines[1] == "“Let not future things disturb thee.”\n— Marcus Aurelius, Meditations VII.8"
    assert lines[2] == ig.FOLLOW_LINE and lines[3].startswith("Music:")
    tags = lines[4].split()
    assert tags == ["#stoicism", "#motivation", "#discipline", "#stoic", "#marcusaurelius"]  # 5, no #shorts
    assert "http" not in text and len(text) <= 2200


# ------------------------------------------------------------- the hand-over

def test_the_producer_hands_each_upload_to_echo(tmp_path, monkeypatch):
    import daily_post
    monkeypatch.setattr(daily_post, "POSTED", tmp_path / "posted")
    video = tmp_path / "2026-10-28_reel.mp4"
    video.write_bytes(b"v" * 1000)
    daily_post._hand_to_echo(video, {"video_id": "abc123", "url": "https://youtube.com/shorts/abc123"},
                             {"date": "2026-10-28", "igCaption": "cap", "hook": "h"})
    d = tmp_path / "posted" / "abc123"
    post = json.loads((d / "post.json").read_text())
    assert (d / "reel.mp4").read_bytes() == video.read_bytes()
    assert post["video_id"] == "abc123" and post["igCaption"] == "cap" and post["video"] == "reel.mp4"
    daily_post._hand_to_echo(video, {}, {})                        # no upload: nothing handed over
    assert len(list((tmp_path / "posted").iterdir())) == 1
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    assert "publish_instagram.publish_reel" not in src             # Instagram is Echo's job now
    assert src.count("_hand_to_echo(") == 3                        # the helper, the post, the backup


def _zip(posts: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for vid, post in posts.items():
            z.writestr(f"{vid}/post.json", json.dumps({"video_id": vid, **post}))
            z.writestr(f"{vid}/reel.mp4", b"v" * 100)
    return buf.getvalue()


def test_echo_finds_the_recent_hand_overs_oldest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    arts = [{"id": 2, "created_at": "2026-10-28T09:00:00Z", "expired": False, "archive_download_url": "u2"},
            {"id": 1, "created_at": "2026-10-27T20:00:00Z", "expired": False, "archive_download_url": "u1"},
            {"id": 0, "created_at": "2026-10-25T01:00:00Z", "expired": False, "archive_download_url": "u0"},
            {"id": 3, "created_at": "2026-10-28T10:00:00Z", "expired": True, "archive_download_url": "u3"}]
    zips = {"u2": _zip({"new": {"uploadedAt": "2026-10-28T08:59:00Z"}}),
            "u1": _zip({"old": {"uploadedAt": "2026-10-27T19:59:00Z"}})}

    def get(url, headers=None, params=None, timeout=None):
        if url.endswith("/actions/artifacts"):
            assert params["name"] == "posted-short"
            return _Resp(payload={"artifacts": arts})
        return _Resp(content=zips[url])
    with patch.object(echo.requests, "get", side_effect=get):
        got = echo.handed_over(NOW, tmp_path)
    assert [p["video_id"] for p in got] == ["old", "new"]          # 3 days old and expired are skipped
    assert all(Path(p["video"]).exists() for p in got)


def test_echo_posts_each_short_once_and_gives_up_after_three_failures():
    handed = [{"video_id": "a"}, {"video_id": "b"}]
    assert echo.to_post([], handed)["video_id"] == "a"
    done = [{"youtube_id": "a", "status": "published"}]
    assert echo.to_post(done, handed)["video_id"] == "b"
    tried = done + [{"youtube_id": "b", "status": "failed"}] * 3
    assert echo.to_post(tried, handed) is None


# ------------------------------------------------------------- the shift

def _acct(**k):
    return {"kind": "instagram", "id": "1789", "username": "forged.in.stoicism", "accountType": "BUSINESS",
            "followers": 40, "mediaCount": 2, **k}


def test_no_key_is_the_owners_to_fix_not_a_failure(data, monkeypatch):
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    with patch.object(ig, "account", side_effect=AssertionError("must not call Instagram")):
        assert echo.shift(now=NOW) == 0
    st = json.loads(echo.STATUS.read_text())
    assert st["ok"] is False and st["problem"] == "There's no Instagram key in GitHub yet."


def test_a_refused_key_is_reported_in_plain_words(data, monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG_KEY)
    with patch.object(ig, "account", side_effect=ig.IGError(400, "Cannot parse access token", 190)):
        assert echo.shift(now=NOW) == 0
    st = json.loads(echo.STATUS.read_text())
    assert st["problem"] == "Instagram refused the key (Cannot parse access token). It needs a new one."
    assert IG_KEY not in echo.STATUS.read_text()


def test_a_shift_posts_whats_waiting_and_counts_once_a_day(data, monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG_KEY)
    handed = [{"video_id": "yt1", "date": "2026-10-28", "igCaption": "the caption", "video": "/tmp/x.mp4",
               "hook": "Stop worrying"}]
    insights = {"data": [{"name": "views", "values": [{"value": 321}]},
                         {"name": "reach", "total_value": {"value": 200}}]}
    with patch.object(ig, "account", return_value=_acct()), \
         patch.object(echo, "handed_over", return_value=handed), \
         patch.object(ig, "publish_reel", return_value={"status": "published", "media_id": "m1",
                                                         "permalink": "https://instagram.com/reel/x"}) as pub, \
         patch.object(ig, "_call", return_value=insights) as call:
        assert echo.shift(now=NOW) == 0
        assert pub.call_args[0][1] == "the caption" and pub.call_args[1]["token"] == IG_KEY
        assert echo.shift(now=NOW + dt.timedelta(hours=4)) == 0     # same day: no repost, no recount
    assert pub.call_count == 1 and call.call_count == 1
    rows = echo._read(echo.POSTS)
    assert [(r["youtube_id"], r["status"], r["ig_media_id"]) for r in rows] == [("yt1", "published", "m1")]
    reels = echo._read(echo.REELS)
    assert reels[0]["views"] == "321" and reels[0]["reach"] == "200"
    st = json.loads(echo.STATUS.read_text())
    assert st["ok"] and st["account"]["username"] == "forged.in.stoicism"
    assert st["lastPost"]["permalink"] == "https://instagram.com/reel/x"
    assert st["key"]["firstSeen"] == "2026-10-28" and st["key"]["expiresAround"] == "2026-12-27"
    assert IG_KEY not in echo.STATUS.read_text() and st["key"]["fingerprint"] == ig_key.fingerprint(IG_KEY)


def test_a_post_that_fails_with_a_working_key_fails_the_shift(data, monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG_KEY)
    with patch.object(ig, "account", return_value=_acct()), \
         patch.object(echo, "handed_over", return_value=[{"video_id": "yt1", "video": "/x.mp4"}]), \
         patch.object(ig, "publish_reel", return_value={"status": "failed", "reason": "boom"}), \
         patch.object(echo, "pull_numbers"):
        assert echo.shift(now=NOW) == 1                                 # the HQ shows Echo failed


def test_the_key_is_refreshed_and_a_new_string_is_kept(data, monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG_KEY)
    echo.save_status({"key": {"fingerprint": ig_key.fingerprint(IG_KEY), "firstSeen": "2026-10-20"}})
    with patch.object(ig, "account", return_value=_acct()), \
         patch.object(echo, "handed_over", return_value=[]), patch.object(echo, "pull_numbers"), \
         patch.object(ig_key, "refresh", return_value=("IGAAnew", 60 * 86400)), \
         patch.object(ig_key, "keep", return_value=True) as keep:
        assert echo.shift(now=NOW) == 0
    keep.assert_called_once_with("IGAAnew", IG_KEY)
    k = json.loads(echo.STATUS.read_text())["key"]
    assert k["refreshed"] == "2026-10-28" and k["expires"] == "2026-12-27" and k["source"] == "kept"
    assert k["sameString"] is False and "lastError" not in k


def test_a_refresh_that_cannot_be_kept_is_retried_tomorrow(data, monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG_KEY)
    echo.save_status({"key": {"fingerprint": ig_key.fingerprint(IG_KEY), "firstSeen": "2026-10-20"}})
    with patch.object(ig, "account", return_value=_acct()), \
         patch.object(echo, "handed_over", return_value=[]), patch.object(echo, "pull_numbers"), \
         patch.object(ig_key, "refresh", return_value=("IGAAnew", 60 * 86400)), \
         patch.object(ig_key, "keep", return_value=False):
        echo.shift(now=NOW)
    k = json.loads(echo.STATUS.read_text())["key"]
    assert "refreshed" not in k and k["lastTry"] == "2026-10-28" and "couldn't keep" in k["lastError"]


def test_a_new_key_from_the_owner_starts_the_clock_again(data, monkeypatch):
    echo.save_status({"key": {"fingerprint": "old", "firstSeen": "2026-09-01", "refreshed": "2026-10-01"}})
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG_KEY)
    with patch.object(ig, "account", return_value=_acct()):
        echo.shift("check", now=NOW)
    k = json.loads(echo.STATUS.read_text())["key"]
    assert k["firstSeen"] == "2026-10-28" and "refreshed" not in k


# ------------------------------------------------------------- the crew

def test_echo_has_his_own_job_and_the_producer_no_longer_reads_instagram_secrets():
    wf = yaml.safe_load((WF / "instagram.yml").read_text())
    on = wf[True]
    assert on["workflow_run"] == {"workflows": ["daily-short"], "types": ["completed"]}
    assert on["schedule"] and "workflow_dispatch" in on
    assert wf["permissions"] == {"contents": "write", "actions": "read"}
    steps = {s.get("name"): s for s in wf["jobs"]["echo"]["steps"]}
    shift = steps["Echo's shift"]
    assert shift["run"] == "python scripts/echo.py"
    assert shift["env"]["IG_ACCESS_TOKEN"] == "${{ secrets.IG_ACCESS_TOKEN }}"
    assert steps["Commit Echo's log"]["if"] == "always()"
    producer = (WF / "daily-short.yml").read_text()
    assert "secrets.IG_ACCESS_TOKEN" not in producer and "secrets.IG_USER_ID" not in producer
    hand = next(s for s in yaml.safe_load(producer)["jobs"]["post"]["steps"]
                if s.get("name") == "Hand the upload to Echo (Instagram)")
    assert hand["with"]["name"] == echo.ARTIFACT and hand["with"]["path"] == "data/posted/"
    assert "data/posted/" in (ROOT / ".gitignore").read_text()


def test_the_hq_shows_echo_and_what_blocks_him(tmp_path, monkeypatch):
    monkeypatch.setattr(hq, "DATA", tmp_path)
    assert any(b["id"] == "instagram" and b["workflow"] == "instagram.yml" for b in hq.BOTS)
    (tmp_path / "ig_status.json").write_text(json.dumps(
        {"ok": False, "problem": "Instagram refused the key (expired). It needs a new one."}))
    run = {"path": ".github/workflows/instagram.yml", "status": "completed", "conclusion": "success",
           "created_at": "2026-10-28T11:00:00Z"}
    bot = next(b for b in hq.bots([run], NOW, "", fetch_missing=False) if b["id"] == "instagram")
    assert bot["status"] == "failed" and "needs a new one" in bot["note"]
    assert hq.instagram(NOW)["problem"].startswith("Instagram refused")
    (tmp_path / "ig_status.json").write_text(json.dumps(
        {"ok": True, "account": {"username": "forged.in.stoicism", "followers": 1234},
         "key": {"expiresAround": "2026-12-27"}}))
    (tmp_path / "ig_stats.csv").write_text("pulled_on,username,followers,media_count\n"
                                           "2026-10-21,f,1000,1\n2026-10-28,f,1234,5\n")
    (tmp_path / "ig_posts.csv").write_text("tried_at,date,youtube_id,ig_media_id,permalink,status,reason\n"
                                           "x,2026-10-15,y0,m0,,published,\n"
                                           "x,2026-10-27,y1,m1,https://instagram.com/reel/a,published,\n")
    (tmp_path / "ig_reels.csv").write_text("pulled_on,ig_media_id,youtube_id,views,reach,likes,comments,shares,saved\n"
                                           "2026-10-27,m1,y1,50,,,,,\n2026-10-28,m1,y1,400,,,,,\n")
    bot = next(b for b in hq.bots([run], NOW, "", fetch_missing=False) if b["id"] == "instagram")
    assert bot["status"] == "idle" and bot["note"] == "@forged.in.stoicism · 1,234 followers"
    g = hq.instagram(NOW)
    assert (g["followers"], g["followersWeekAgo"], g["reels"], g["views7d"]) == (1234, 1000, 2, 400)
    assert g["lastReel"] == {"date": "2026-10-27", "permalink": "https://instagram.com/reel/a"}


def test_the_hq_page_has_echo_and_instagram_numbers():
    page = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")
    assert 'instagram: { name: "Echo", title: "Instagram", sprite: "echo"' in page
    assert "function drawInstagram()" in page and 'id="ig"' in page
    # a blocked bot that waits on the owner reads "Needs you", not "failed"
    assert '["offduty", "oncall", "done", "failed"].includes(status)) { status = "waiting"' in page
