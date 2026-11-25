"""The painted look's wiring: the edit style pack (scripts/daily_post.py
_paint_edit) and the quote's new fields (src/edits.py as_content)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import daily_post  # noqa: E402
import edits  # noqa: E402
import edit_type  # noqa: E402

BANK = json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))
WITH = next(q for q in BANK if q.get("scenes"))
WITHOUT = next(q for q in BANK if not q.get("scenes"))


def _pack(q, monkeypatch, look="", picture="", type_=""):
    for k, v in (("REEL_EDIT_LOOK", look), ("REEL_PICTURE", picture), ("REEL_EDIT_TYPE", type_)):
        if v:
            monkeypatch.setenv(k, v)
        else:
            monkeypatch.delenv(k, raising=False)
    content = edits.as_content(q)
    broll = content["broll_queries"]
    pack = {"REEL_MONO": "1", "REEL_BG_CLIPS": str(len(broll))}
    for i, v in enumerate(broll):
        pack[f"REEL_BG_FLAVOR{i if i else ''}"] = v
    daily_post._paint_edit(pack, content, "edit", broll, len(broll))
    daily_post._type_edit(pack, content, "edit")
    return pack, content


def test_as_content_carries_the_scene_writers_shots():
    assert edits.as_content(WITH)["_scenes"] == WITH["scenes"]
    assert edits.as_content(WITHOUT)["_scenes"] == []


def test_nothing_changes_unless_the_look_is_asked_for(monkeypatch):
    pack, _ = _pack(WITH, monkeypatch)
    assert pack["REEL_MONO"] == "1" and "REEL_PICTURE" not in pack
    assert not any(k.startswith(("REEL_PAINT", "REEL_TYPE", "REEL_MASTER", "REEL_QUOTE_EMPH"))
                   for k in pack)


def test_the_whole_look(monkeypatch):
    pack, content = _pack(WITH, monkeypatch, look="painted")
    assert pack["REEL_PICTURE"] == "painted" and pack["REEL_MONO"] == "0"
    assert pack["REEL_TYPE"] == "v2" and pack["REEL_MASTER_LUFS"] == "-14"
    for k in daily_post.PAINTED_PICTURE:
        assert k in pack
    assert pack["REEL_PAINT_KEY"] == WITH["id"]
    # the scene writer's shots drive the cut, in order, each with its stock fallback
    n = len(WITH["scenes"])
    assert pack["REEL_BG_CLIPS"] == str(n)
    for i, s in enumerate(WITH["scenes"]):
        sfx = i if i else ""
        assert pack[f"REEL_PAINT_SCENE{sfx}"] == s
        assert pack[f"REEL_BG_FLAVOR{sfx}"] == WITH["visuals"][i % len(WITH["visuals"])]
    assert f"REEL_BG_FLAVOR{n}" not in pack            # no stale slot past the last shot
    # the type: Callimachus's gold words for this quote (data/edit_type.json) and its source line
    hook_e, quote_e = edit_type.emphasis_for(WITH["id"])
    assert pack["REEL_QUOTE_EMPHASIS"] == quote_e and pack["REEL_HOOK_EMPHASIS"] == hook_e
    assert quote_e and hook_e                      # every quote to air has its gold words
    assert pack["REEL_QUOTE_SOURCE"] == edit_type.source_line(WITH["citation"])


def test_type_only_is_the_new_type_on_todays_picture(monkeypatch):
    """The design lab's "type" look: REEL_EDIT_TYPE=v2 from the environment."""
    pack, _ = _pack(WITH, monkeypatch, type_="v2")
    assert pack["REEL_TYPE"] == "v2" and pack["REEL_QUOTE_EMPHASIS"]
    assert pack["REEL_MONO"] == "1" and "REEL_PICTURE" not in pack and "REEL_MASTER_LUFS" not in pack


def test_picture_only_keeps_todays_type(monkeypatch):
    """The design lab's "picture" look: REEL_PICTURE=painted from the
    environment. The pack must not undo it with black-and-white."""
    pack, _ = _pack(WITH, monkeypatch, picture="painted")
    assert pack["REEL_PICTURE"] == "painted" and pack["REEL_MONO"] == "0"
    assert "REEL_TYPE" not in pack and "REEL_MASTER_LUFS" not in pack
    assert "REEL_QUOTE_EMPHASIS" not in pack


def test_a_quote_without_scenes_keeps_its_eight_visuals(monkeypatch):
    pack, _ = _pack(WITHOUT, monkeypatch, look="painted")
    assert pack["REEL_BG_CLIPS"] == str(len(WITHOUT["visuals"]))
    assert not any(k.startswith("REEL_PAINT_SCENE") for k in pack)


def test_other_formats_are_never_painted(monkeypatch):
    monkeypatch.setenv("REEL_EDIT_LOOK", "painted")
    pack = {"REEL_MONO": "0"}
    daily_post._paint_edit(pack, {"quote": "q", "hook": "h"}, "story", [], 0)
    daily_post._type_edit(pack, {"quote": "q", "hook": "h"}, "story")
    assert pack == {"REEL_MONO": "0"}


def test_the_edit_pack_still_defaults_to_todays_look():
    src = (ROOT / "scripts" / "daily_post.py").read_text()
    edit = src[src.index('"edit": {'):src.index('"truestory": {')]
    assert '"REEL_MONO": "1"' in edit
    assert "_paint_edit(pack, content, fmt, broll, len(flavors))" in src
    assert "_type_edit(pack, content, fmt)" in src


@pytest.mark.parametrize("q", [q for q in BANK if q.get("scenes")], ids=lambda q: q["id"])
def test_every_quote_with_scenes_fills_six_to_eight_slots(q, monkeypatch):
    pack, _ = _pack(q, monkeypatch, look="painted")
    assert 6 <= int(pack["REEL_BG_CLIPS"]) <= 8


def test_the_live_workflows_air_the_look_the_owner_picked():
    """The owner picked "Switch to the new look" in the HQ (asks/new-look,
    2026-11-11; decisions.md). It is on in BOTH daily-short.yml and
    edit-preview.yml, so the rehearsal under Next on air is exactly what airs.
    Changing the look again needs his say-so: change this test with the
    decision in decisions.md."""
    import yaml
    for wf in ("daily-short.yml", "edit-preview.yml"):
        w = yaml.safe_load((ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8"))
        envs = [st.get("env") or {} for job in w["jobs"].values() for st in job.get("steps", [])]
        looks = [e["REEL_EDIT_LOOK"] for e in envs if "REEL_EDIT_LOOK" in e]
        assert looks == ["painted"], (wf, looks)
        assert any(e.get("REEL_STILL_CACHE") == "data/still_cache" for e in envs), wf


EMO = next(q for q in BANK if q.get("scenes_emotional"))


def test_as_content_carries_the_emotional_shots():
    assert edits.as_content(EMO)["_scenes_emotional"] == EMO["scenes_emotional"]
    assert edits.as_content(WITHOUT)["_scenes_emotional"] == []


def test_emotional_flag_off_changes_nothing(monkeypatch):
    monkeypatch.delenv("REEL_EMOTION", raising=False)
    pack, _ = _pack(EMO, monkeypatch, look="painted")
    assert pack["REEL_PAINT_SCENE"] == EMO["scenes"][0]
    assert "REEL_EMOTION" not in pack and "REEL_FIRST_SHOT_SECONDS" not in pack
    assert pack["REEL_PAINT_HOOK_ZOOM"] == "0.10"


def test_emotional_flag_airs_the_face_first_shots_and_the_faster_open(monkeypatch):
    monkeypatch.setenv("REEL_EMOTION", "1")
    pack, _ = _pack(EMO, monkeypatch, look="painted")
    shots = EMO["scenes_emotional"]
    assert pack["REEL_PAINT_SCENE"] == shots[0]                      # slot 0: the face (and the poster's frame)
    assert pack["REEL_BG_CLIPS"] == str(len(shots))
    assert pack["REEL_FIRST_SHOT_SECONDS"] == "1.5" and pack["REEL_EMOTION"] == "1"
    assert float(pack["REEL_PAINT_HOOK_ZOOM"]) > 0.10                # a deeper push-in on the face
    assert pack["REEL_TYPE"] == "v2"                                 # the v2 type, so the pop and the poster apply


def test_emotional_flag_falls_back_to_the_plain_scenes_for_a_quote_without_them(monkeypatch):
    monkeypatch.setenv("REEL_EMOTION", "1")
    pack, _ = _pack(WITH if not WITH.get("scenes_emotional") else WITHOUT, monkeypatch, look="painted")
    assert pack["REEL_EMOTION"] == "1"                              # style still applies; shots come from scenes


# ---- The emotional look goes live by the AIR day (owner 2026-11-25 in the HQ:
# "Switch every Short"): REEL_EMOTION_FROM in both workflows. ---------------------
def _find_env(node, key):
    """Every value of `key` anywhere in a workflow (job- or step-level env)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            else:
                yield from _find_env(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _find_env(v, key)


def test_emotion_from_switches_on_by_the_air_day(monkeypatch):
    import datetime as _dt
    monkeypatch.delenv("REEL_EMOTION", raising=False)
    monkeypatch.setenv("REEL_EMOTION_FROM", "2026-11-26")
    assert daily_post.emotion_wanted(_dt.date(2026, 11, 25)) is False   # Nov 25's Shorts keep their rehearsed look
    assert daily_post.emotion_wanted(_dt.date(2026, 11, 26)) is True
    assert daily_post.emotion_wanted(_dt.date(2026, 12, 1)) is True


def test_the_flag_beats_the_date(monkeypatch):
    import datetime as _dt
    monkeypatch.setenv("REEL_EMOTION_FROM", "2026-11-26")
    monkeypatch.setenv("REEL_EMOTION", "0")
    assert daily_post.emotion_wanted(_dt.date(2026, 12, 1)) is False    # an explicit off wins
    monkeypatch.setenv("REEL_EMOTION", "1")
    assert daily_post.emotion_wanted(_dt.date(2026, 11, 1)) is True     # the design lab's explicit on


def test_no_date_or_a_bad_date_keeps_it_off(monkeypatch):
    import datetime as _dt
    monkeypatch.delenv("REEL_EMOTION", raising=False)
    monkeypatch.delenv("REEL_EMOTION_FROM", raising=False)
    assert daily_post.emotion_wanted(_dt.date(2027, 1, 1)) is False
    monkeypatch.setenv("REEL_EMOTION_FROM", "soon")
    assert daily_post.emotion_wanted(_dt.date(2027, 1, 1)) is False


def test_the_pack_follows_the_air_day(monkeypatch):
    """A rehearsal (REEL_TODAY = its air day) and the post itself get the same look."""
    import datetime as _dt
    monkeypatch.delenv("REEL_EMOTION", raising=False)
    monkeypatch.setenv("REEL_EMOTION_FROM", "2026-11-26")
    monkeypatch.setattr(daily_post.airday, "today", lambda: _dt.date(2026, 11, 25))
    pack, _ = _pack(EMO, monkeypatch, look="painted")
    assert "REEL_EMOTION" not in pack and pack["REEL_PAINT_SCENE"] == EMO["scenes"][0]
    monkeypatch.setattr(daily_post.airday, "today", lambda: _dt.date(2026, 11, 26))
    pack, _ = _pack(EMO, monkeypatch, look="painted")
    assert pack["REEL_EMOTION"] == "1" and pack["REEL_PAINT_SCENE"] == EMO["scenes_emotional"][0]


def test_both_workflows_switch_on_the_same_air_day():
    import datetime as _dt
    import yaml
    days = {}
    for name in ("daily-short.yml", "edit-preview.yml"):
        wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
        days[name] = set(_find_env(wf, "REEL_EMOTION_FROM"))
    assert days["daily-short.yml"] == days["edit-preview.yml"] and len(days["daily-short.yml"]) == 1
    (day,) = days["daily-short.yml"]
    _dt.date.fromisoformat(day)                     # a real date, or the look silently stays off
