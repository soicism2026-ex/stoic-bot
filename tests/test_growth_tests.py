"""The code behind Cicero's test 3 ships before the owner's yes, so it must
change nothing until the ledger says the test is running (owner's rule:
"dont ship anything until i approve it"); test 2 the owner answered himself
(2026-11-06, tests/test_descriptions.py); Glaux's audience pull feeds him."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import audience  # noqa: E402
import edits  # noqa: E402
import playlists  # noqa: E402

Q = {"id": "x", "theme": "fear", "quote": "q", "author": "Seneca", "citation": "c", "hook": "h", "visuals": []}


def _ledger(tmp_path, monkeypatch, module, attr, **test):
    p = tmp_path / "marketing_tests.json"
    p.write_text(json.dumps({"tests": [test] if test else []}))
    monkeypatch.setattr(module, attr, p)


# ---------------------------------------------------------------- test 2

def test_each_short_asks_its_own_question_since_the_owners_example():
    """2026-11-06: the owner answered test 2 with a viral Short's description
    to model ours on, so the question is on from the next Short, no A/B."""
    own = {**Q, "question": "What's one fear you faced this year?"}
    assert edits.as_content(own)["pinned_comment"] == own["question"]
    assert edits.pinned_comment(Q) == edits.PINNED_BY_THEME["fear"]           # no question: its theme's
    assert edits.pinned_comment({**Q, "theme": "unknown"}) == edits.PINNED_GENERIC
    assert edits.pinned_comment({**own, "question": "  "}) == edits.PINNED_BY_THEME["fear"]


def test_every_theme_on_the_shelf_has_a_kind_question():
    assert {q["theme"] for q in edits.load()} <= set(edits.PINNED_BY_THEME)
    for theme, text in edits.PINNED_BY_THEME.items():
        assert text.endswith("?") and len(text) <= 100, theme
        low = text.lower()
        for bad in ("weak", "pathetic", "loser", "nobody is coming", "die", "kill"):
            assert bad not in low, (theme, bad)                     # doctrine 5: no shame, no harm


# ---------------------------------------------------------------- test 3

class _Req:
    def __init__(self, result):
        self.result = result

    def execute(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _YT:
    """A fake YouTube: the channel's playlists, what each holds, each video's privacy."""

    def __init__(self, fail_after=None, unlisted=(), manual=True):
        self.inserted, self.made, self.deleted = [], [], []
        self.fail_after, self.unlisted, self.manual = fail_after, set(unlisted), manual
        self.lists: dict[str, str] = {}                 # title -> playlist id
        self.held: dict[str, dict[str, str]] = {}       # playlist id -> {video id: item id}
        yt = self

        class Playlists:
            def list(self, **k):
                return _Req({"items": [{"id": i, "snippet": {"title": t}} for t, i in yt.lists.items()]})

            def list_next(self, req, resp):
                return None

            def insert(self, part, body):
                yt.made.append(body["snippet"]["title"])
                assert body["status"]["privacyStatus"] == "public"
                pid = f"PL{len(yt.made)}"
                yt.lists[body["snippet"]["title"]] = pid
                return _Req({"id": pid})

        class Items:
            def list(self, part, playlistId, maxResults):
                return _Req({"items": [{"id": i, "contentDetails": {"videoId": v}}
                                       for v, i in yt.held.get(playlistId, {}).items()]})

            def list_next(self, req, resp):
                return None

            def insert(self, part, body):
                sn = body["snippet"]
                if yt.fail_after is not None and len(yt.inserted) >= yt.fail_after:
                    return _Req(RuntimeError("quotaExceeded"))
                if "position" in sn and not yt.manual:
                    return _Req(RuntimeError("<HttpError 400: manualSortRequired>"))
                yt.inserted.append((sn["playlistId"], sn["resourceId"]["videoId"], sn.get("position")))
                yt.held.setdefault(sn["playlistId"], {})[sn["resourceId"]["videoId"]] = f"it{len(yt.inserted)}"
                return _Req({})

            def delete(self, id):  # noqa: A002  the API's own name
                yt.deleted.append(id)
                for items in yt.held.values():
                    for v, i in list(items.items()):
                        if i == id:
                            del items[v]
                return _Req({})

        class Videos:
            def list(self, part, id, maxResults):  # noqa: A002
                return _Req({"items": [{"id": v, "status": {
                    "privacyStatus": "unlisted" if v in yt.unlisted else "public"}} for v in id.split(",")]})

        self._p, self._i, self._v = Playlists(), Items(), Videos()

    def playlists(self):
        return self._p

    def playlistItems(self):
        return self._i

    def videos(self):
        return self._v


def _setup(tmp_path, monkeypatch, status="running", posts=None):
    monkeypatch.setattr(playlists, "ROOT", tmp_path)
    monkeypatch.setattr(playlists, "STATE", tmp_path / "data" / "playlists.json")
    (tmp_path / "data").mkdir()
    _ledger(tmp_path, monkeypatch, playlists, "TESTS", id="playlists", status=status)
    rows = posts or [
        ("2026-10-02", "Marcus Aurelius", "edit:a", "v1"), ("2026-10-03", "Seneca", "edit:b", "v2"),
        ("2026-10-04", "Marcus Aurelius", "edit:c", "v3"), ("2026-09-01", "Seneca", "story:s", "v0"),
        ("2026-10-05", "Zeno of Citium", "edit:z", "v9")]
    lines = ["date,author,experiment,video_id"] + [",".join(r) for r in rows]
    (tmp_path / "data" / "posts.csv").write_text("\n".join(lines) + "\n")


def _filed():
    return json.loads(playlists.STATE.read_text())["filed"]


def test_playlists_do_nothing_until_the_owner_says_yes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, status="proposed")
    yt = _YT()
    assert playlists.run(yt=yt) == 0
    assert yt.made == [] and yt.inserted == [] and not playlists.STATE.exists()


def test_playlists_file_each_edit_once_newest_first(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    yt = _YT()
    playlists.run(yt=yt)
    assert yt.made == ["Marcus Aurelius quotes: Stoic Shorts", "Seneca quotes: Stoic Shorts"]
    assert [v for _, v, _ in yt.inserted] == ["v1", "v3", "v2"]            # each philosopher oldest first,
    assert all(pos == 0 for _, _, pos in yt.inserted)                       # each at the top: newest first
    assert _filed() == {"v1": "Marcus Aurelius", "v2": "Seneca", "v3": "Marcus Aurelius"}
    playlists.run(yt=yt)                                                    # nothing twice
    assert len(yt.made) == 2 and len(yt.inserted) == 3
    playlists.STATE.unlink()                                                # even with the state lost:
    playlists.run(yt=yt)                                                    # found by title, read back
    assert len(yt.made) == 2 and len(yt.inserted) == 3 and len(_filed()) == 3


def test_unlisted_shorts_stay_out_and_leave_once_pruned(tmp_path, monkeypatch):
    """prune_videos.py unlists weak Shorts after a week; a public playlist must not bring them back."""
    _setup(tmp_path, monkeypatch)
    yt = _YT(unlisted={"v3"})
    playlists.run(yt=yt)
    assert [v for _, v, _ in yt.inserted] == ["v1", "v2"] and "v3" not in _filed()
    yt.unlisted.add("v1")
    playlists.run(yt=yt)
    assert yt.deleted == ["it1"] and _filed() == {"v2": "Seneca"}


def test_a_quota_stop_keeps_what_was_filed(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    playlists.run(yt=_YT(fail_after=1))
    assert _filed() == {"v1": "Marcus Aurelius"}


def test_a_playlist_not_sorted_by_hand_still_gets_the_short(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    yt = _YT(manual=False)
    playlists.run(yt=yt)
    assert [(v, pos) for _, v, pos in yt.inserted] == [("v1", None), ("v3", None), ("v2", None)]


def test_a_backfill_is_spread_over_runs_and_stays_newest_first(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(playlists, "MAX_CALLS", 2)                          # 50 units each
    yt = _YT()
    for _ in range(3):
        playlists.run(yt=yt)
    assert [v for _, v, _ in yt.inserted] == ["v1", "v3", "v2"] and len(_filed()) == 3


def test_the_owner_said_yes_to_playlists_on_2026_11_06():
    ledger = json.loads((ROOT / "data" / "marketing_tests.json").read_text())
    t = next(t for t in ledger["tests"] if t["id"] == "playlists")
    assert t["status"] == "running" and t["started"] == "2026-11-06"
    assert "Yes, make the playlists" in t["approved"]
    assert playlists.gate()


# ---------------------------------------------------------------- the audience

def test_the_audience_pull_shares_and_merges(tmp_path):
    assert audience.shares([["US", 30], ["IN", 10]]) == [
        {"key": "US", "views": 30, "share": 0.75}, {"key": "IN", "views": 10, "share": 0.25}]
    p = tmp_path / "traffic_sources.csv"
    audience.upsert_sources([["2026-11-01", "SHORTS", 100], ["2026-11-01", "PLAYLIST", 0]], p)
    audience.upsert_sources([["2026-11-01", "SHORTS", 120], ["2026-11-02", "SHORTS", 90]], p)
    rows = p.read_text().splitlines()
    assert rows == ["date,source,views", "2026-11-01,PLAYLIST,0", "2026-11-01,SHORTS,120", "2026-11-02,SHORTS,90"]


def test_the_jobs_run_the_new_work_and_never_fail_a_post():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pull-analytics.yml").read_text())
    steps = {s.get("name"): s for s in wf["jobs"]["analytics"]["steps"]}
    pull = steps["Pull the audience (countries, traffic sources)"]
    assert pull["run"] == "python scripts/audience.py" and pull["continue-on-error"] is True
    assert "data/audience.json" in steps["Commit analytics"]["run"]
    daily = yaml.safe_load((ROOT / ".github" / "workflows" / "daily-short.yml").read_text())
    steps = {s.get("name"): s for s in daily["jobs"]["post"]["steps"]}
    pl = steps["File the edits into playlists (Cicero's test 3)"]
    assert pl["run"] == "python scripts/playlists.py" and pl["continue-on-error"] is True
    assert "data/playlists.json" in steps["Commit log and backups"]["run"]
