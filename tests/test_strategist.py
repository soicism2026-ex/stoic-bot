"""Frontinus, the free strategist (owner 2026-10-27: fire the paid one, but
find someone who does the job for free first)."""
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edits  # noqa: E402
import strategist as st  # noqa: E402

TODAY = dt.date(2026, 10, 27)


def _post(i, day, theme, author="Seneca", hook="Pick one thing.", quote="A short quote here."):
    return {"date": day, "theme": theme, "author": author, "quote": quote, "hook": hook,
            "experiment": f"edit:e{i}", "video_id": f"v{i}", "music_track": "edit:x",
            "voice_name": "Brian"}


def _stats(i, day, views_by_age):
    pub = dt.date.fromisoformat(day)
    return [{"video_id": f"v{i}", "published_at": f"{day}T01:00:00Z",
             "pulled_on": (pub + dt.timedelta(days=age)).isoformat(), "views": str(v)}
            for age, v in views_by_age]


def test_views_are_compared_at_day_3_not_at_whatever_age_a_video_reached():
    stats = (_stats(1, "2026-10-10", [(1, 50), (3, 300), (10, 900)])
             + _stats(2, "2026-10-25", [(1, 40)]))                    # not settled yet
    assert st.day3_views(stats) == {"v1": 300}


def test_each_edit_is_judged_against_its_own_season():
    """Early October drew ~10x fewer views: raw views would blame whatever
    aired then. Relative to the same week, the two eras' winners tie."""
    posts, stats, i = [], [], 0
    for base, start in ((20, 1), (200, 15)):           # a slow season, then a busy one
        for k in range(6):
            i += 1
            day = f"2026-10-{start + k:02d}"
            theme = "fear" if k % 2 else "discipline"
            v = base * (3 if theme == "discipline" else 1)
            posts.append(_post(i, day, theme, author="Marcus Aurelius" if start == 1 else "Seneca"))
            stats += _stats(i, day, [(3, v)])
    r = st.read(posts, stats, [], today=TODAY)
    themes = {g["key"]: g for g in r["groups"]["theme"]}
    assert themes["discipline"]["verdict"] == "winner" and themes["fear"]["verdict"] == "loser"
    authors = {g["key"]: g["lift"] for g in r["groups"]["author"]}
    assert abs(authors["Marcus Aurelius"] - authors["Seneca"]) < 0.3     # not blamed for the season
    assert r["theme_rank"] == {"discipline": 2, "fear": 0}


def test_small_samples_are_reported_never_acted_on():
    posts = [_post(1, "2026-10-20", "anger"), _post(2, "2026-10-21", "fear"),
             _post(3, "2026-10-22", "fear"), _post(4, "2026-10-23", "fear")]
    stats = sum((_stats(i, p["date"], [(3, v)]) for i, p, v in
                 zip(range(1, 5), posts, (900, 100, 100, 100))), [])
    r = st.read(posts, stats, [], today=TODAY)
    anger = next(g for g in r["groups"]["theme"] if g["key"] == "anger")
    assert anger["verdict"] == "too few" and r["theme_rank"]["anger"] == 1


def test_the_read_is_written_for_people_and_for_the_picker(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STRATEGY_MD", tmp_path / "strategy.md")
    monkeypatch.setattr(st, "STRATEGY_JSON", tmp_path / "strategy.json")
    r = st.read(today=TODAY)
    md = st.markdown(r)
    for h in ("## What Works", "## What Doesn't Work", "## Top Recommendations for Next Posts",
              "## Performance Data Window"):
        assert h in md
    assert "no paid API" in md and r["settled_edits"] > 0
    assert set(r["theme_rank"].values()) <= {0, 1, 2}


def test_winning_themes_air_first_within_the_author_rotation(monkeypatch):
    bank = [{"id": f"q{i}", "author": a, "theme": t, "quote": f"quote {i}"}
            for i, (a, t) in enumerate([("Seneca", "control"), ("Seneca", "time"),
                                        ("Seneca", "discipline"), ("Epictetus", "fear")])]
    monkeypatch.setattr(edits, "load", lambda: bank)
    monkeypatch.setattr(edits, "jammed_ids", lambda: set())
    rows = [{"experiment": "edit:old", "author": "Epictetus", "theme": "anger", "quote": "x"}]
    monkeypatch.setattr(edits, "theme_rank", lambda: {})
    assert edits.pick(rows)["id"] == "q0"                         # no read: bank order
    monkeypatch.setattr(edits, "theme_rank", lambda: {"discipline": 2, "control": 0})
    assert edits.pick(rows)["id"] == "q2"                         # the winner first
    monkeypatch.setattr(edits, "theme_rank", lambda: {"control": 0, "time": 0})
    assert edits.pick(rows)["id"] == "q2"                         # losers last
    rows.append({"experiment": "edit:q2", "author": "Seneca", "theme": "discipline", "quote": "quote 2"})
    assert edits.pick(rows)["author"] == "Epictetus"              # the author rotation still rules


def test_the_strategist_runs_free_every_day():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "strategy-update.yml").read_text())
    assert wf["name"] == "Update content strategy"                 # hq-status follows it by name
    src = (ROOT / ".github" / "workflows" / "strategy-update.yml").read_text()
    assert "scripts/strategist.py --write" in src
    assert "secrets." not in src and "strategy_loop.py --" not in src
    assert {c["cron"] for c in wf[True]["schedule"]} == {"0 10 * * *"}
    page = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")
    assert 'strategist: { name: "Frontinus"' in page and "I need Anthropic API credit" not in page
