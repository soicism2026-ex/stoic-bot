"""Long videos (scripts/long_form.py): no network, no paid voice."""
import copy
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import long_form as lf  # noqa: E402
import hq_outbox  # noqa: E402
import publish  # noqa: E402

FIRST = ROOT / "data" / "long_form" / "2026-11-24.json"


@pytest.fixture
def script():
    return json.loads(FIRST.read_text(encoding="utf-8"))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(lf, "DIR", tmp_path)
    monkeypatch.setattr(lf, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(hq_outbox, "OUTBOX", tmp_path / "outbox.jsonl")
    return tmp_path


# ------------------------------------------------------------------ the first script
def test_the_first_script_is_valid_and_within_every_limit(script):
    assert lf.validate_script(script) == []
    text = lf.spoken_text(script)
    assert lf.MIN_WORDS <= len(text.split()) <= lf.MAX_WORDS and len(text) <= lf.MAX_CHARS
    assert 4 <= len(lf.quotes_of(script)) <= 6 and script["theme"] == "anger"
    assert script["parts"][0]["chapter"]                        # YouTube needs a chapter at 0:00


def test_every_quote_is_verbatim_from_the_sources_and_the_shelf(script):
    import validate_quotes as vq
    shelf = {q["quote"]: q for q in json.loads((ROOT / "data" / "edit_quotes.json").read_text())}
    for p in lf.quotes_of(script):
        assert vq.check(p["quote"], p["author"]) == "ok"
        assert vq.check_citation(p["quote"], p["author"], p["citation"]) == "ok"
        assert p["quote"] in shelf and shelf[p["quote"]]["citation"] == p["citation"]


def test_too_long_too_short_and_too_many_characters_are_rejected(script):
    long_ = copy.deepcopy(script)
    long_["parts"][0]["text"] += " word" * 200
    assert any("words" in p for p in lf.validate_script(long_))
    assert any("characters" in p for p in lf.validate_script(
        {**long_, "parts": [{**long_["parts"][0], "text": "x" * 4600}] + long_["parts"][1:]}))
    short = copy.deepcopy(script)
    short["parts"][0]["text"] = "Short."
    assert any("words" in p for p in lf.validate_script(short))


def test_an_invented_or_misquoted_quote_is_rejected(script):
    bad = copy.deepcopy(script)
    q = next(p for p in bad["parts"] if p["kind"] == "quote")
    q["quote"] = "Anger is a short madness that every wise man keeps in a locked drawer."
    assert any("not verbatim" in p for p in lf.validate_script(bad))
    wrong = copy.deepcopy(script)
    q = next(p for p in wrong["parts"] if p["kind"] == "quote")
    q["citation"] = "Enchiridion 1, trans. George Long"          # the first quote is Enchiridion 20
    assert any("citation" in p for p in lf.validate_script(wrong))


def test_quote_count_scenes_and_key_words_are_checked(script):
    few = copy.deepcopy(script)
    few["parts"] = [p for p in few["parts"] if p["kind"] != "quote"][:6]
    assert any("quotes" in p for p in lf.validate_script(few))
    nos = copy.deepcopy(script)
    nos["scenes"] = nos["scenes"][:5]
    assert any("scenes" in p for p in lf.validate_script(nos))
    key = copy.deepcopy(script)
    next(p for p in key["parts"] if p["kind"] == "quote")["key"] = "not in the quote at all"
    assert any("key words" in p for p in lf.validate_script(key))


def test_write_script_refuses_an_invalid_one(sandbox, script):
    script["parts"][0]["text"] = "Short."
    with pytest.raises(ValueError):
        lf.write_script(script)
    assert not list(sandbox.glob("2*.json"))


def test_the_crew_script_writer_copies_quotes_from_the_shelf_not_the_model(sandbox, script):
    shelf = {q["quote"]: q for q in json.loads((ROOT / "data" / "edit_quotes.json").read_text())}
    parts = []
    for p in script["parts"]:
        parts.append({"kind": "quote", "id": shelf[p["quote"]]["id"], "key": p["key"]} if p["kind"] == "quote" else p)
    reply = json.dumps({"title": script["title"], "lead": "x", "tags": ["a"], "thumbnail_text": "ANGER", "parts": parts,
                        "scenes": script["scenes"]})
    got = lf.generate_script("anger", dt.date(2026, 12, 13), chat=lambda *a, **k: "Sure:\n" + reply)
    assert [q["quote"] for q in lf.quotes_of(got)] == [q["quote"] for q in lf.quotes_of(script)]
    assert lf.validate_script(got) == []
    assert lf.write_script(got).name == "2026-12-13.json"


# ------------------------------------------------------------------ every other week
def test_the_alternate_week_gate():
    sun = dt.date(2026, 11, 29)
    assert lf.is_long_week(sun) and not lf.is_long_week(sun + dt.timedelta(days=7))
    assert lf.is_long_week(sun + dt.timedelta(days=14)) and lf.is_long_week(sun + dt.timedelta(days=28))
    # Friday and Saturday painting serves the coming Sunday
    assert lf.is_long_week(dt.date(2026, 11, 27)) and lf.is_long_week(dt.date(2026, 11, 28))
    assert not lf.is_long_week(dt.date(2026, 12, 4)) and not lf.is_long_week(dt.date(2026, 12, 5))
    assert not lf.is_long_week(dt.date(2026, 11, 22))                 # before the first one


def test_gate_prints_run_true_false(capsys):
    lf.main(["gate", "--date", "2026-11-29"])
    lf.main(["gate", "--date", "2026-12-06"])
    lf.main(["gate", "--date", "2026-12-06", "--force"])
    assert capsys.readouterr().out.split() == ["run=true", "run=false", "run=true"]


def test_the_workflow_schedules_paint_nights_and_the_sunday_render():
    wf = (ROOT / ".github" / "workflows" / "long-form.yml").read_text()
    for cron in ('"47 20 * * *"', '"47 21 * * *"', '"47 22 * * *"', '"17 14 * * 0"'):
        assert cron in wf                      # paint every evening of a long week, render Sunday
    assert "workflow_dispatch" in wf and "workflow_run" in wf and "spare_paint.py check" in wf
    assert "long_form.py gate" in wf and "render" in wf and "PRIVATE" in wf
    for secret in ("ELEVENLABS_API_KEY", "YOUTUBE_REFRESH_TOKEN", "CLOUDFLARE_API_TOKEN"):
        assert f"secrets.{secret}" in wf
    assert "data/still_cache" in wf


# ------------------------------------------------------------------ private by default
def _upload_setup(sandbox, monkeypatch, script):
    out = sandbox / "out"
    out.mkdir()
    (out / "long_form.mp4").write_bytes(b"x")
    (sandbox / "2026-11-24.json").write_text(json.dumps(script))
    (out / "meta.json").write_text(json.dumps({"script": "2026-11-24.json", "title": "T", "tags": ["a"],
                                              "description": "D", "chapters": [], "duration": 300}))
    seen = {}

    def fake(video, title, desc, tags, privacy="public"):
        seen["privacy"] = privacy
        return {"video_id": "VID1", "url": "https://youtube.com/watch?v=VID1"}
    monkeypatch.setattr(publish, "publish_longform", fake)
    monkeypatch.setattr(publish, "set_thumbnail", lambda *a, **k: True)
    return out, seen


def test_upload_is_private_by_default_and_files_the_preview_card_once(sandbox, monkeypatch, script):
    out, seen = _upload_setup(sandbox, monkeypatch, script)
    assert lf.privacy() == "private"
    lf.main(["upload", "--out", str(out)])
    assert seen["privacy"] == "private"
    cards = [json.loads(x) for x in (sandbox / "outbox.jsonl").read_text().splitlines()]
    assert len(cards) == 1 and cards[0]["ask"] == "long-form-preview"
    c = cards[0]["create"]
    assert c["title"] == "First long video: publish it?" and "https://youtube.com/watch?v=VID1" in c["pitch"]
    assert [o["id"] for o in c["options"]] == ["publish", "redo"] and c["crew"] == "review" and c["order"] == 0
    assert lf.load_state()["first_preview_sent"] and lf.load_state()["uploaded"][0]["privacy"] == "private"
    lf.main(["upload", "--out", str(out)])                      # a second private upload: no second card
    assert len((sandbox / "outbox.jsonl").read_text().splitlines()) == 1


def test_the_owners_yes_makes_later_uploads_public_and_redo_takes_it_back(sandbox, monkeypatch, script):
    out, seen = _upload_setup(sandbox, monkeypatch, script)
    lf.main(["approve"])
    assert lf.privacy() == "public"
    lf.main(["upload", "--out", str(out)])
    assert seen["privacy"] == "public"
    assert not (sandbox / "outbox.jsonl").exists()              # no preview card once approved
    lf.main(["approve", "--redo"])
    assert lf.privacy() == "private"


def test_publish_longform_sends_the_privacy_to_youtube(tmp_path):
    cap = {}

    def insert(part, body, media_body):
        cap["body"] = body
        req = MagicMock()
        req.next_chunk.return_value = (None, {"id": "V"})
        return req
    yt = MagicMock()
    yt.videos.return_value.insert.side_effect = insert
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    with patch.object(publish, "_service", lambda *a, **k: yt), patch("googleapiclient.http.MediaFileUpload", MagicMock()):
        publish.publish_longform(v, "T", "D", [], privacy="private")
        assert cap["body"]["status"]["privacyStatus"] == "private"
        publish.publish_longform(v, "T", "D", [])               # the Shorts-era default is untouched
        assert cap["body"]["status"]["privacyStatus"] == "public"


# ------------------------------------------------------------------ the voice guard
def test_the_voice_guard_stops_plainly(script):
    ok, why = lf.voice_check(script, 30000)
    assert ok and "budget ok" in why
    ok, why = lf.voice_check(script, 1000)
    assert not ok and "stopping" in why and "1000" in why
    ok, why = lf.voice_check(script, None)
    assert not ok and "not spending" in why


def test_render_stops_without_spending_when_the_month_cannot_cover_it(sandbox, monkeypatch, script, capsys):
    (sandbox / "2026-11-24.json").write_text(json.dumps(script))
    import tts
    monkeypatch.setattr(tts, "_EL_KEY", "k")
    monkeypatch.setattr(tts, "_el_credits_remaining", lambda: 500)
    monkeypatch.setattr(lf, "narrate", lambda *a, **k: pytest.fail("the voice must not be called"))
    assert lf.main(["render", "--out", str(sandbox / "o")]) == 1
    assert "stopping" in capsys.readouterr().out


# ------------------------------------------------------------------ chapters, description, shots
def test_chapters_and_the_description(script, monkeypatch):
    import promo
    monkeypatch.setattr(promo, "PROMO_ENABLED", True)
    starts = [i * 20.0 for i in range(len(script["parts"]))]
    chs = lf.chapters_from(script, starts)
    assert chs[0] == (0.0, script["parts"][0]["chapter"]) and len(chs) >= 3
    d = lf.description(script, chs)
    assert d.splitlines()[2] == "Chapters" and "0:00 The bill you keep paying" in d
    assert lf.stamp(65) == "1:05" and lf.stamp(3725) == "1:02:05"
    assert "Meditations 11.18" in d and "\n---\n" in d                  # the quotes' citations, then the journal line
    assert d.count("#Shorts") == 0


def test_shots_are_about_nine_seconds_and_gaps_reuse_a_neighbour(script):
    plan = lf.shot_plan(290.0)
    assert abs(sum(plan) - 290.0) < 1e-6 and all(8 <= d <= 10 for d in plan)
    a, b = Path("a.png"), Path("b.png")
    assert lf.fill_gaps([a, None, None, b]) == [a, a, b, b]
    with pytest.raises(RuntimeError):
        lf.fill_gaps([None, None])


def test_painting_stops_at_tonights_share_and_a_cache_hit_is_free(script):
    calls = []

    def fake(prompt, seed, scene):
        calls.append(scene)
        return {"path": f"/x/{len(calls)}.png", "cached": len(calls) <= 2}
    got = lf.paint_shots(script, 8, limit=3, painter_fn=fake)
    assert sum(1 for g in got if g) == 5 and got[5:] == [None, None, None]     # 2 free + 3 painted
    assert "16:9" not in json.dumps(script)


def test_the_graph_has_a_move_per_shot_and_a_card_per_quote(script):
    g = lf.video_graph(4, [9, 9, 9, 9], [(2.0, 8.0), (20.0, 30.0)])
    assert g.count("perspective=") == 4 and "concat=n=4" in g and g.count("overlay=") == 2
    assert "1920:1080" in g and g.endswith("[vout]") and "between(t,2.000,8.000)" in g


def _tone(path: Path, seconds: float):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
                    str(path)], check=True)


def test_narration_joins_the_parts_and_times_each_one(sandbox, script):
    lengths = iter([1.0, 2.0] * 20)

    def synth(text, out):
        _tone(out, next(lengths))
        return out, []
    small = {"parts": script["parts"][:2]}
    got = lf.narrate(small, sandbox / "v", synth=synth)
    assert got["starts"][0] == 0.0 and got["starts"][1] == pytest.approx(1.0 + lf.GAP, abs=0.15) and got["ends"][1] == pytest.approx(1.0 + lf.GAP + 2.0, abs=0.15)
    assert got["duration"] == pytest.approx(3.0 + 2 * lf.GAP, abs=0.3) and got["audio"].exists()


def test_the_real_graph_renders_with_ffmpeg_and_a_card(sandbox, script):
    """Three tiny stills, one quote card: the graph must actually run and make 1920x1080."""
    from PIL import Image
    stills = []
    for i, c in enumerate([(120, 60, 40), (40, 90, 120), (90, 120, 50)]):
        p = sandbox / f"s{i}.png"
        Image.new("RGB", (1920, 1088), c).save(p)
        stills.append(p)
    card = lf.quote_card(next(p for p in script["parts"] if p["kind"] == "quote"), sandbox / "card.png")
    assert Image.open(card).size == (1920, 1080) and Image.open(card).mode == "RGBA"
    inputs = []
    for s in stills:
        inputs += ["-loop", "1", "-framerate", "30", "-t", "0.8", "-i", str(s)]
    inputs += ["-loop", "1", "-framerate", "30", "-t", "1.2", "-i", str(card)]
    out = sandbox / "t.mp4"
    graph = lf.video_graph(3, [0.8, 0.8, 0.8], [(0.2, 1.8)])
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[vout]", "-t", "2.4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert probe == "1920,1080"


def test_thumbnail_is_1280x720(sandbox, script):
    from PIL import Image
    still = sandbox / "s.png"
    Image.new("RGB", (1920, 1088), (90, 60, 40)).save(still)
    out = lf.thumbnail(script, still, sandbox / "t.jpg")
    assert Image.open(out).size == (1280, 720) and out.stat().st_size < 2_000_000


# ------------------------------------------------------------------ the spare-painting rule
import datetime as _dt  # noqa: E402


def _png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 2000)
    return path


@pytest.fixture
def waiting(tmp_path, monkeypatch, script):
    """A script waiting in a sandboxed data/long_form, and an empty still cache."""
    d = tmp_path / "lf"
    d.mkdir()
    (d / "2026-11-24.json").write_text(json.dumps(script))
    monkeypatch.setattr(lf, "DIR", d)
    monkeypatch.setattr(lf, "STATE", d / "state.json")
    monkeypatch.setenv("REEL_STILL_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("REEL_PAINT_SIZE", "1920x1088")
    return script


def _cache_scene(i, script):
    import imagegen
    import painter
    scene = lf.scene_for(script, i)
    seed = painter.seed_for(scene, "longform:" + script.get("date", ""), i, True)
    model = imagegen.paint_models()[0]
    w, h = imagegen.paint_size(model)
    key = imagegen.still_key(model, painter.build_prompt(scene), seed, w, h)
    _png(imagegen.still_cache_dir() / f"{key}.png")


def test_long_form_paints_on_a_tuesday_in_the_window_and_resumes(waiting, monkeypatch, capsys):
    import spare_paint
    n = lf.shot_count(waiting)
    monkeypatch.setattr(spare_paint, "check", lambda *a, **k: (True, "spare"))
    made = []

    def fake(prompt, seed, scene):
        made.append(scene)
        return {"path": "/x.png", "cached": False} if len(made) <= 3 else None     # the allowance ends
    monkeypatch.setattr(lf, "paint_shots", lambda script, n_, limit=None, painter_fn=None: [fake("p", 1, "s") for _ in range(n_)] and [])
    assert lf.cmd_paint(type("A", (), {"force": False, "limit": 24})()) == 0
    assert "left for the next night" in capsys.readouterr().out
    assert lf.unpainted(waiting) == (n, n)                       # nothing cached by the fake: it resumes tomorrow
    for i in range(n):
        _cache_scene(i, waiting)
    assert lf.unpainted(waiting) == (0, n)
    lf.cmd_paint(type("A", (), {"force": False, "limit": 24})())
    assert "nothing to paint" in capsys.readouterr().out


def test_paint_is_refused_outside_the_spare_window_with_one_log_line(waiting, monkeypatch, capsys):
    import spare_paint
    monkeypatch.setattr(spare_paint, "check", lambda *a, **k: (False, "it is 03:00 UTC"))
    called = []
    monkeypatch.setattr(lf, "paint_shots", lambda *a, **k: called.append(1))
    assert lf.cmd_paint(type("A", (), {"force": False, "limit": 24})()) == 0
    out = capsys.readouterr().out
    assert not called and out.count("\n") == 1 and "not painting now" in out


def test_wallpapers_yield_while_the_long_video_is_unfinished_then_run(waiting, monkeypatch):
    day = _dt.date(2026, 11, 25)                                  # a Wednesday of the 11-29 long week
    busy, why = lf.paint_unfinished(day)
    assert busy and "unpainted" in why
    n = lf.shot_count(waiting)
    for i in range(n - 1):
        _cache_scene(i, waiting)
    assert lf.paint_unfinished(day)[0]                            # one scene short: still yielding
    _cache_scene(n - 1, waiting)
    busy, why = lf.paint_unfinished(day)
    assert not busy and "all" in why


def test_a_week_without_a_script_yields_monday_to_saturday_only(tmp_path, monkeypatch):
    monkeypatch.setattr(lf, "DIR", tmp_path)
    monkeypatch.setattr(lf, "STATE", tmp_path / "state.json")
    assert lf.paint_unfinished(_dt.date(2026, 11, 25))[0]          # long week, script still to be written
    assert not lf.paint_unfinished(_dt.date(2026, 11, 29))[0]      # the Sunday itself
    assert not lf.paint_unfinished(_dt.date(2026, 12, 2))[0]       # the off week


def test_the_sunday_render_never_paints_and_counts_its_fallbacks(waiting, monkeypatch, capsys):
    n = lf.shot_count(waiting)
    _cache_scene(0, waiting)
    called = []
    import imagegen
    monkeypatch.setattr(imagegen, "generate_still", lambda *a, **k: called.append(1))
    got = lf.paint_shots(waiting, n, painter_fn=lf._cached_only)
    assert not called and got[0] and not any(got[1:])
    assert len(lf.fill_gaps(got)) == n
