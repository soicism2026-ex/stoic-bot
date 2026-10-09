"""Assisted posting: the owner adds the trending song in the app, the bot
prepares every video and adopts his uploads."""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import assist   # noqa: E402
import shuffle  # noqa: E402


def _p(pid, prepared, title, duration, hook=""):
    return {"id": pid, "prepared_at": prepared, "title": title, "hook": hook,
            "duration": duration, "date": prepared[:10]}


def _u(vid, published, title, duration):
    return {"video_id": vid, "published_at": published, "title": title, "duration": duration}


P1 = _p("a", "2026-10-10T03:05:00+00:00",
        '"Stop talking about who you\'ll be." — Marcus Aurelius | Stoicism', 12.63,
        "Stop talking about who you'll be.")
P2 = _p("b", "2026-10-10T07:05:00+00:00",
        '"You\'re acting like you have forever." — Marcus Aurelius | Stoicism', 14.2,
        "You're acting like you have forever.")


def test_matches_the_pasted_title():
    up = _u("v1", "2026-10-10T12:00:00Z",
            '"Stop talking about who you\'ll be." — Marcus Aurelius | Stoicism', 13)
    assert [(p["id"], u["video_id"]) for p, u in assist.match([P1, P2], [up], set())] == [("a", "v1")]


def test_matches_a_retyped_title_by_its_hook():
    up = _u("v1", "2026-10-10T12:00:00Z", "stop talking about who you'll be #stoic", 30)
    assert assist.match([P1, P2], [up], set())[0][0]["id"] == "a"


def test_matches_by_length_when_the_title_is_his_own():
    up = _u("v2", "2026-10-10T12:00:00Z", "my own words", 14)
    assert assist.match([P1, P2], [up], set())[0][0]["id"] == "b"


def test_ignores_logged_and_earlier_uploads_and_wrong_lengths():
    logged = _u("v0", "2026-10-10T12:00:00Z", P1["title"], 13)
    early = _u("v3", "2026-10-09T12:00:00Z", "older video", 13)
    other = _u("v4", "2026-10-10T12:00:00Z", "an unrelated long video", 58)
    assert assist.match([P1, P2], [logged, early, other], {"v0"}) == []


def test_each_queued_video_is_adopted_once():
    a = _u("v1", "2026-10-10T12:00:00Z", "x", 13)
    b = _u("v2", "2026-10-10T12:30:00Z", "y", 13)
    pairs = assist.match([P1], [a, b], set())
    assert len(pairs) == 1 and pairs[0][1]["video_id"] == "v1"


def test_empty_hook_never_matches_every_title():
    p = _p("c", "2026-10-10T03:05:00+00:00", "Some title here", 99.0, hook="")
    assert assist.match([p], [_u("v1", "2026-10-10T12:00:00Z", "anything", 13)], set()) == []


def test_iso_durations():
    assert assist.parse_duration("PT13S") == 13
    assert assist.parse_duration("PT1M2S") == 62
    assert assist.parse_duration("") == 0


def test_every_song_in_the_list_is_one_the_owner_named():
    songs = assist.songs()
    assert len(songs) == 9 and len({s["id"] for s in songs}) == 9
    for s in songs:
        assert s["title"] and s["artist"] and s["search"]


def test_songs_shuffle_across_posts_and_skip_queued_ones():
    rows, seq = [], []
    for day in range(18):
        s = assist.pick_song(rows, seed=f"2026-11-{day:02d}")
        seq.append(s["id"])
        rows.append({"music_track": assist.SONG_PREFIX + s["id"]})
    assert len(set(seq[:9])) == 9 and len(set(seq[9:])) == 9
    assert all(a != b for a, b in zip(seq, seq[1:]))


def test_queued_edits_are_not_picked_again():
    import edits
    first = edits.pick([])
    rows = assist.as_rows([{"experiment": f"edit:{first['id']}", "theme": first["theme"]}])
    assert edits.pick(rows)["id"] != first["id"]


def test_queue_writes_record_notes_and_release(tmp_path, monkeypatch):
    monkeypatch.setattr(assist, "DIR", tmp_path)
    monkeypatch.setattr(assist, "PENDING", tmp_path / "pending")
    monkeypatch.setattr(assist, "RELEASE", tmp_path / "release.json")
    monkeypatch.setattr(assist, "ROOT", tmp_path)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 1000)
    song = assist.songs()[4]
    rec = assist.queue({"id": "2026-10-10-be_such", "date": "2026-10-10", "title": "T",
                        "quote": "Q", "author": "A", "song": song, "duration": 12.6},
                       video)
    assert (tmp_path / "pending" / "2026-10-10-be_such.json").exists()
    rel = json.loads((tmp_path / "release.json").read_text())
    assert rel["tag"] == "edit-2026-10-10-be_such"
    notes = (tmp_path / "2026-10-10-be_such.md").read_text()
    assert song["search"] in notes and "T" in notes and f"{assist.MUSIC_PERCENT}%" in notes
    assert assist.load()[0]["id"] == rec["id"]
    assist.remove(rec["id"])
    assert assist.load() == []


def test_daily_post_never_uploads_in_assist_mode():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    i = src.index("if upload_this and ASSIST:")
    j = src.index("upload_result = publish_short(")
    k = src.index("rec = assist.queue(")
    assert i < k < j and "return" in src[k:j]
    assert "backup = None if ASSIST else _load_backup()" in src
    assert "music_path = None" in src[src.index("if ASSIST:\n        # No music"):]


def test_workflows_are_wired():
    daily = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text()
    assert 'POST_MODE: "assist"' in daily and "scripts/assist_release.py" in daily
    adopt = (ROOT / ".github" / "workflows" / "adopt.yml").read_text()
    assert "scripts/adopt_uploads.py" in adopt and "cron:" in adopt
    assert "gh workflow run daily-short.yml" in adopt


def test_shuffle_is_shared():
    assert shuffle.pick([], []) is None
    assert shuffle.pick(["x"], ["x", "x"]) == "x"


def test_release_page_is_exactly_the_queue(tmp_path, monkeypatch):
    """Posted or withdrawn videos lose their release; queued ones and
    non-video releases (the Instagram media bucket) are left alone."""
    import assist_release as ar
    (tmp_path / "keep.json").write_text("{}")
    monkeypatch.setattr(ar, "PENDING", tmp_path)
    calls = []

    class R:
        returncode = 0
        stderr = ""

        def __init__(self, out=""):
            self.stdout = out

    def fake_gh(*args, check=True):
        calls.append(args)
        if args[:2] == ("release", "list"):
            return R(json.dumps([{"tagName": "edit-keep"}, {"tagName": "edit-gone"},
                                 {"tagName": "media-bucket"}]))
        return R()

    monkeypatch.setattr(ar, "_gh", fake_gh)
    ar.sync()
    deleted = [a[2] for a in calls if a[:2] == ("release", "delete")]
    assert deleted == ["edit-gone"]
