"""Channel name + About for search (owner 2026-11-16, idea-channel-seo). No network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import channel_seo as cs  # noqa: E402
import promo  # noqa: E402

T = cs.load_target()
PHRASES = [p["phrase"] for p in json.loads((ROOT / "data" / "search_phrases.json").read_text())["phrases"]]


class FakeYT:
    """Just enough of the Data API client: channels().list/update."""
    def __init__(self, live, refuse_title=False, ignore_title=False):
        self.item = {"id": "UC1", "brandingSettings": {"channel": dict(live), "image": {"x": 1}}}
        self.refuse_title, self.ignore_title, self.updates = refuse_title, ignore_title, []

    def channels(self):
        return self

    def list(self, **kw):
        outer = self
        class R:
            def execute(self_inner):
                return {"items": [json.loads(json.dumps(outer.item))]}
        return R()

    def update(self, part, body):
        outer = self
        class R:
            def execute(self_inner):
                ch = body["brandingSettings"]["channel"]
                outer.updates.append(json.loads(json.dumps(body)))
                if outer.refuse_title and ch.get("title") != outer.item["brandingSettings"]["channel"].get("title"):
                    raise RuntimeError("channelTitle can not be updated through the API")
                new = dict(outer.item["brandingSettings"]["channel"])
                for k, v in ch.items():
                    if k == "title" and outer.ignore_title:
                        continue
                    new[k] = v
                outer.item["brandingSettings"]["channel"] = new
                return json.loads(json.dumps(outer.item))
        return R()


def test_the_target_is_valid_and_in_the_owners_plain_style():
    cs.check_target(T)
    d = T["description"]
    assert T["title"] == "Forged in Stoicism | Stoic Quotes"
    assert len(d) < 1000 and 2 <= len(d.splitlines()) <= 4
    for who in ("Marcus Aurelius", "Seneca", "Epictetus"):
        assert who in d
    assert d.endswith(promo._DEFAULT_CTAS[0].format(url=promo.PROMO_URL))   # the journal line
    assert len(T["keywords"]) <= 500
    for p in PHRASES:
        assert p in T["keywords"]


def test_the_about_is_built_from_the_searches():
    d = T["description"].lower()
    hits = sum(1 for w in ("overthinking", "emotions", "calm under pressure", "disciplined", "hard times") if w in d)
    assert hits >= 4


def test_plan_prints_what_it_would_set(capsys):
    assert cs.main(["x", "plan"]) == 0
    out = capsys.readouterr().out
    assert "Forged in Stoicism | Stoic Quotes" in out and "Keywords:" in out and T["description"] in out


def test_check_target_rejects_a_long_or_unnamed_about():
    with pytest.raises(ValueError):
        cs.check_target({**T, "description": "x" * 1000})
    with pytest.raises(ValueError):
        cs.check_target({**T, "description": "Stoic quotes daily."})


def test_apply_sets_everything_and_keeps_other_branding(tmp_path):
    yt = FakeYT({"title": "forged.in.stoicism", "description": "old"})
    res = cs.apply(yt, T, tmp_path / "a.json")
    assert res["status"] == "applied" and not res["titleRefused"]
    sent = yt.updates[0]["brandingSettings"]
    assert sent["image"] == {"x": 1} and sent["channel"]["title"] == T["title"]
    rec = json.loads((tmp_path / "a.json").read_text())
    assert rec["titleRefused"] is None and rec["description"] == T["description"]


def test_nothing_to_do_when_already_applied(tmp_path):
    yt = FakeYT({"title": T["title"], "description": T["description"], "keywords": T["keywords"]})
    res = cs.apply(yt, T, tmp_path / "a.json")
    assert res["status"] == "nothing to do" and yt.updates == []
    assert not (tmp_path / "a.json").exists()


def test_a_refused_name_still_applies_the_about_and_is_not_retried(tmp_path):
    p = tmp_path / "a.json"
    yt = FakeYT({"title": "forged.in.stoicism", "description": "old"}, refuse_title=True)
    res = cs.apply(yt, T, p)
    assert res["status"] == "applied" and "refused the new channel name" in res["titleRefused"]
    assert yt.updates[-1]["brandingSettings"]["channel"]["title"] == "forged.in.stoicism"   # the live name, unchanged
    assert yt.item["brandingSettings"]["channel"]["description"] == T["description"]
    rec = json.loads(p.read_text())
    assert "YouTube Studio" in rec["titleNote"]
    n = len(yt.updates)
    again = cs.apply(yt, T, p)                      # next post run: nothing left to do
    assert again["status"] == "nothing to do" and len(yt.updates) == n


def test_a_name_youtube_silently_keeps_is_reported(tmp_path):
    yt = FakeYT({"title": "forged.in.stoicism"}, ignore_title=True)
    res = cs.apply(yt, T, tmp_path / "a.json")
    assert "kept the old channel name" in res["titleRefused"]


def test_the_workflow_runs_it_after_the_post_and_commits_the_record():
    wf = (ROOT / ".github/workflows/daily-short.yml").read_text()
    i = wf.index("scripts/channel_seo.py apply")
    assert "continue-on-error: true" in wf[wf.rindex("- name:", 0, i):i]
    assert "data/channel_branding_applied.json" in wf
    assert wf.index("Run self-healing post pipeline") < i < wf.index("Commit log and backups")
