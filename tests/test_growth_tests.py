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
    def __init__(self, fail_after=None):
        self.inserted, self.made, self.fail_after = [], [], fail_after
        yt = self

        class Playlists:
            def list(self, **k):
                return _Req({"items": []})

            def list_next(self, req, resp):
                return None

            def insert(self, part, body):
                yt.made.append(body["snippet"]["title"])
                return _Req({"id": f"PL{len(yt.made)}"})

        class Items:
            def insert(self, part, body):
                if yt.fail_after is not None and len(yt.inserted) >= yt.fail_after:
                    return _Req(RuntimeError("quotaExceeded"))
                yt.inserted.append((body["snippet"]["playlistId"], body["snippet"]["resourceId"]["videoId"],
                                    body["snippet"]["position"]))
                return _Req({})

        self._p, self._i = Playlists(), Items()

    def playlists(self):
        return self._p

    def playlistItems(self):
        return self._i


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
    assert [v for _, v, _ in yt.inserted] == ["v1", "v2", "v3"]            # oldest first, each at the top
    assert all(pos == 0 for _, _, pos in yt.inserted)                       # so the newest ends up first
    st = json.loads(playlists.STATE.read_text())
    assert st["filed"] == {"v1": "Marcus Aurelius", "v2": "Seneca", "v3": "Marcus Aurelius"}
    yt2 = _YT()
    playlists.run(yt=yt2)                                                   # nothing twice
    assert yt2.made == [] and yt2.inserted == []


def test_a_quota_stop_keeps_what_was_filed(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    playlists.run(yt=_YT(fail_after=1))
    assert json.loads(playlists.STATE.read_text())["filed"] == {"v1": "Marcus Aurelius"}


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
    pl = steps["File the edits into playlists (Cicero, needs the owner's yes)"]
    assert pl["run"] == "python scripts/playlists.py" and pl["continue-on-error"] is True
    assert "data/playlists.json" in steps["Commit log and backups"]["run"]
