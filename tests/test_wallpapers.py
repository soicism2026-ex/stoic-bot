"""Wallpaper packs (scripts/wallpapers.py). No network, no keys."""
import datetime as dt
import json
import sys
import zipfile
from pathlib import Path

import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import wallpapers as w  # noqa: E402
import wallpapers as wp  # noqa: E402

WF = ROOT / ".github" / "workflows" / "wallpapers.yml"
QUOTES = [
    {"id": "a", "author": "Seneca", "citation": "Letters 1, trans. Gummere", "theme": "time",
     "quote": "It is not that we have a short time to live, but that we waste a lot of it."},
    {"id": "b", "author": "Seneca", "citation": "Letters 2, trans. Gummere", "theme": "fear",
     "quote": "We suffer more often in imagination than in reality.",
     "scenes": ["{seneca} writing at a desk by a window, warm morning light"]},
]


def stand_in(tmp_path):
    def paint(prompt, seed):
        assert prompt and isinstance(seed, int)
        return w.stand_in_painting(tmp_path / "p.png", 1024, 1920, seed)
    return paint


def test_wrap_respects_cap_and_keeps_every_word():
    t = "Nothing happens to any man which he is not formed by nature to bear."
    for cap in (32, 48):
        lines = w.wrap_quote(t, cap)
        assert " ".join(lines) == t
        assert all(len(x) <= cap for x in lines)
    assert w.wrap_quote("Short one.", 32) == ["Short one."]
    assert w.wrap_quote("", 32) == []


def test_wrap_is_balanced_no_orphan():
    lines = w.wrap_quote("Waste no more time arguing what a good man should be. Be one.", 32)
    assert len(lines) == 2 and min(len(x) for x in lines) > 12


@pytest.mark.parametrize("kind", ["phone", "desktop"])
def test_layout_sets_text_in_the_right_place(kind, tmp_path):
    s = w.SIZES[kind]
    base = Image.new("RGB", (s["w"], s["h"]), (120, 120, 120))
    out = w.compose_text(base, QUOTES[0]["quote"], "Seneca", "Letters 1, trans. Gummere", kind)
    assert out.size == (s["w"], s["h"])
    H, W = s["h"], s["w"]
    diff = out.convert("L").point(lambda v: 255 if v > 170 else 0)   # the text is the bright part
    box = diff.getbbox()
    assert box, "no text drawn"
    if kind == "phone":
        # bright text only in the lower 40%, clear top for the clock
        assert diff.crop((0, 0, W, int(H * 0.60))).getbbox() is None
        assert box[0] > 40 and box[2] < W - 40
    else:
        # quote in the lower-left; nothing bright in the top half
        assert diff.crop((0, 0, W, int(H * 0.5))).getbbox() is None
        left = diff.crop((0, int(H * 0.5), int(W * 0.7), H)).getbbox()
        assert left is not None
    # the band darkens the bottom
    assert out.getpixel((W // 2, H - 5))[0] < 60


def test_every_shipped_quote_fits_both_sizes():
    for kind in w.SIZES:
        for pack in w.PACKS:
            for q in w.load_quotes(pack, 10):
                L = w.layout(kind)
                lines, font, size = w.fit_quote(f"“{q['quote']}”", L["cap"] + 2, L["box_w"],
                                                 800, L["max_size"], L["min_size"])
                assert size >= L["min_size"] and lines


def test_fonts_have_the_glyphs_the_packs_need():
    from PIL import ImageFont
    for path in (w.QUOTE_FONT, w.AUTHOR_FONT):
        f = ImageFont.truetype(str(path), 60)
        nd = bytes(f.getmask("\uFFFF"))
        for pack in w.PACKS:
            for q in w.load_quotes(pack, 99):
                text = q["quote"] + q["author"] + q.get("citation", "")
                if path == w.AUTHOR_FONT:
                    text = q["author"].upper() + q.get("citation", "") + w.WATERMARK
                for c in set(text):
                    if c.isspace():
                        continue
                    assert bytes(f.getmask(c)) != nd, f"{path.name} lacks {c!r} ({q['id']})"


def test_load_quotes_by_author_shortest_first_and_limited():
    qs = w.load_quotes("seneca", 5)
    assert len(qs) == 5 and all(q["author"] == "Seneca" for q in qs)
    assert [len(q["quote"]) for q in qs] == sorted(len(q["quote"]) for q in qs)
    assert all(q.get("citation") for q in qs)
    assert w.load_quotes("marcus", 0) == []


def test_prompt_uses_scenes_else_theme_and_is_stable():
    p1, s1 = w.prompt_for(QUOTES[1])
    assert "Seneca" in p1 or "seneca" in p1.lower()
    p0, s0 = w.prompt_for(QUOTES[0])
    assert p0 and (p0, s0) == w.prompt_for(QUOTES[0])


@pytest.mark.parametrize("kind", ["phone", "desktop"])
def test_render_and_package_end_to_end(kind, tmp_path):
    out = tmp_path / "out"
    rows = w.render_pack("seneca", kind, out, quotes=QUOTES, painter_fn=stand_in(tmp_path))
    assert len(rows) == 2
    s = w.SIZES[kind]
    for r in rows:
        assert Image.open(out / f"seneca-{kind}" / r["file"]).size == (s["w"], s["h"])
    m = w.package_pack("seneca", kind, out)
    z = zipfile.ZipFile(out / f"seneca-{kind}.zip")
    names = z.namelist()
    assert "README.txt" in names
    assert sorted(f["file"] for f in m["files"]) == sorted(n for n in names if n != "README.txt")
    assert all(n.endswith(".jpg" if kind == "desktop" else ".png") for n in names if n != "README.txt")
    readme = z.read("README.txt").decode()
    assert "not for resale or redistribution" in readme
    assert w.YOUTUBE in readme and w.GUMROAD in readme and QUOTES[0]["quote"] in readme
    man = json.loads((out / f"seneca-{kind}-manifest.json").read_text())
    assert man["count"] == 2 and man["zipSha256"] and all(len(f["sha256"]) == 64 for f in man["files"])
    assert man["title"] == "Forged in Stoicism: Seneca Wallpaper Pack"
    cov = Image.open(out / f"seneca-{kind}-cover.jpg")
    assert cov.width == 1600


def test_unpaintable_quote_is_skipped_never_swapped(tmp_path):
    calls = []

    def paint(prompt, seed):
        calls.append(seed)
        return None if len(calls) == 1 else w.stand_in_painting(tmp_path / "p.png", 1024, 1920)
    rows = w.render_pack("seneca", "phone", tmp_path / "o", quotes=QUOTES, painter_fn=paint)
    assert [r["id"] for r in rows] == ["b"]
    meta = json.loads((tmp_path / "o" / "seneca-phone" / "rendered.json").read_text())
    assert meta["skipped"] == ["a"]


def test_package_without_render_stops(tmp_path):
    with pytest.raises(SystemExit):
        w.package_pack("seneca", "phone", tmp_path)


def rehearsed(monkeypatch, air="2026-11-15", painted=True):
    """tomorrow's first Short is rehearsed (the up-next release), painted or not"""
    monkeypatch.setenv("REEL_EDIT_LOOK", "painted")
    monkeypatch.setattr(w, "fetch_up_next", lambda: {"airDay": air, "shots": [{"painted": painted}] * 6})


def test_guard_refuses_before_20_utc_without_force(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    monkeypatch.setattr(w, "utcnow", lambda: dt.datetime(2026, 11, 14, 9, 30, tzinfo=dt.timezone.utc))
    painted = []
    monkeypatch.setattr(w, "paint_one", lambda p, s: painted.append(s))
    rc = w.main(["render", "--pack", "seneca", "--size", "phone", "--out", str(tmp_path)])
    assert rc == w.EXIT_GUARD and not painted
    assert "20:00" in capsys.readouterr().err


def test_guard_refuses_in_the_evening_until_tomorrows_short_is_rehearsed(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    monkeypatch.setattr(w, "utcnow", lambda: dt.datetime(2026, 11, 14, 21, 0, tzinfo=dt.timezone.utc))
    painted = []
    monkeypatch.setattr(w, "paint_one", lambda p, s: painted.append(s))
    rehearsed(monkeypatch, air="2026-11-14")                       # the rehearsal is still for today
    assert w.main(["render", "--pack", "seneca", "--size", "phone", "--out", str(tmp_path)]) == w.EXIT_GUARD
    rehearsed(monkeypatch, painted=False)                          # tomorrow's, but a shot is unpainted
    assert w.main(["render", "--pack", "seneca", "--size", "phone", "--out", str(tmp_path)]) == w.EXIT_GUARD
    monkeypatch.setattr(w, "fetch_up_next", lambda: None)          # unreadable
    assert w.main(["render", "--pack", "seneca", "--size", "phone", "--out", str(tmp_path)]) == w.EXIT_GUARD
    assert not painted


def test_guard_passes_after_20_and_prints_neuron_estimate(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    monkeypatch.setenv("REEL_STILL_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(w, "utcnow", lambda: dt.datetime(2026, 11, 14, 20, 5, tzinfo=dt.timezone.utc))
    rehearsed(monkeypatch)
    monkeypatch.setattr(w, "paint_one", lambda p, s: w.stand_in_painting(tmp_path / "p.png", 1024, 1920))
    rc = w.main(["render", "--pack", "seneca", "--size", "phone", "--limit", "2", "--out", str(tmp_path / "o")])
    out = capsys.readouterr().out
    assert rc == 0 and "neurons" in out and "208" in out
    assert len(list((tmp_path / "o" / "seneca-phone").glob("*.png"))) == 2


def test_force_overrides_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    monkeypatch.setenv("REEL_STILL_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(w, "utcnow", lambda: dt.datetime(2026, 11, 14, 3, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(w, "fetch_up_next", lambda: None)
    monkeypatch.setattr(w, "paint_one", lambda p, s: w.stand_in_painting(tmp_path / "p.png", 1920, 1088))
    assert w.main(["render", "--pack", "marcus", "--size", "desktop", "--limit", "1",
                   "--out", str(tmp_path / "o"), "--force"]) == 0


def test_missing_keys_exit_2_and_never_print_a_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    rc = w.main(["render", "--pack", "marcus", "--size", "phone", "--out", str(tmp_path), "--force"])
    assert rc == 2
    assert "CLOUDFLARE_API_TOKEN" in capsys.readouterr().err


def test_desktop_accepts_portrait_painting_with_blurred_sides(tmp_path):
    p = w.stand_in_painting(tmp_path / "p.png", 1024, 1920)
    im = w.fit_desktop(p)
    assert im.size == (3840, 2160)
    assert im.getpixel((10, 1000)) != im.getpixel((1920, 1000))


def test_workflow_paints_one_queued_pack_a_night_and_keeps_the_zip_private():
    """The queue (data/wallpapers_queue.json) paints one pack a night after the
    posts (20:33 UTC); a dispatch can name a pack. The zip is a private workflow
    artifact; only the cover and manifest go to the public release."""
    import yaml
    text = (ROOT / ".github" / "workflows" / "wallpapers.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    on = wf.get("on") or wf.get(True)
    assert set(on) == {"schedule", "workflow_dispatch"}
    assert on["schedule"] == [{"cron": "33 20 * * *"}]                  # after the day's posts have painted
    ins = on["workflow_dispatch"]["inputs"]
    assert ins["pack"]["options"] == ["next", "marcus", "seneca", "epictetus"] and ins["pack"]["default"] == "next"
    assert ins["size"]["options"] == ["phone", "desktop"] and ins["force"]["default"] is False
    assert "secrets.CLOUDFLARE_ACCOUNT_ID" in text and "secrets.CLOUDFLARE_API_TOKEN" in text
    assert "still_cache" in text and "stills-" in text
    steps = wf["jobs"]["pack"]["steps"]
    art = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    assert ".zip" in art["with"]["path"] and "-free.zip" in art["with"]["path"] and art["with"]["retention-days"] == 90
    pop = next(s for s in steps if "queue --pop" in s.get("run", ""))
    assert pop["env"]["COMPLETE"] == "${{ steps.paint.outputs.complete }}" and "data/wallpapers.json" in pop["run"]
    queue = json.loads((ROOT / "data" / "wallpapers_queue.json").read_text(encoding="utf-8"))
    assert [(q["pack"], q["size"]) for q in queue][:3] == [("marcus", "phone"), ("seneca", "phone"), ("epictetus", "phone")]


def test_the_queue_hands_out_the_next_pack_and_drops_a_finished_one(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([{"pack": "marcus", "size": "phone"}, {"pack": "seneca", "size": "desktop", "limit": 6}]))
    assert wp.queue_head(q) == {"pack": "marcus", "size": "phone", "limit": 10}
    assert wp.queue_pop("marcus", "phone", q) == 1
    assert wp.queue_head(q) == {"pack": "seneca", "size": "desktop", "limit": 6}
    assert wp.queue_pop("seneca", "desktop", q) == 0 and wp.queue_head(q) is None
    assert wp.queue_head(tmp_path / "missing.json") is None


def test_the_release_carries_only_the_cover_and_the_manifest(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(wp, "_gh", lambda *a, **k: (calls.append(a), type("R", (), {"returncode": 0})())[1])
    for n in ("marcus-phone-cover.jpg", "marcus-phone.zip", "marcus-phone-free.zip"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "marcus-phone-manifest.json").write_text(json.dumps({"count": 10, "free": {"count": 5}}))
    monkeypatch.setattr(wp, "RECORD", tmp_path / "rec.json")
    names = wp.publish("marcus", "phone", tmp_path)
    assert names == ["marcus-phone-cover.jpg", "marcus-phone-manifest.json"]
    uploaded = next(a for a in calls if a[:2] == ("release", "upload"))
    assert not any(x.endswith(".zip") for x in uploaded)

def test_a_published_pack_is_recorded_for_the_hq(tmp_path, monkeypatch):
    out = tmp_path / "out"; out.mkdir()
    (out / "marcus-phone-manifest.json").write_text(json.dumps({"count": 10, "run": "https://x/runs/1"}))
    rec = tmp_path / "wallpapers.json"
    items = wp.record("marcus", "phone", out, rec)
    assert items[0]["cover"].endswith("/releases/download/wallpapers/marcus-phone-cover.jpg") and items[0]["count"] == 10
    (out / "marcus-phone-manifest.json").write_text(json.dumps({"count": 9, "run": "https://x/runs/2"}))
    items = wp.record("marcus", "phone", out, rec)
    assert len(items) == 1 and items[0]["run"] == "https://x/runs/2"               # upserted, not doubled


def test_the_small_hours_are_refused_even_with_a_rehearsal(monkeypatch, tmp_path):
    """11-24: a pack painted at 02:44 UTC and used up the day's allowance, so the 19:00 Short aired
    unpainted. After midnight the allowance belongs to that day's Shorts."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    rehearsed(monkeypatch)
    for hour in (0, 1, 2, 3, 19):
        monkeypatch.setattr(w, "utcnow", lambda h=hour: dt.datetime(2026, 11, 14, h, 4, tzinfo=dt.timezone.utc))
        assert w.main(["render", "--pack", "seneca", "--size", "phone", "--out", str(tmp_path)]) == w.EXIT_GUARD


def test_one_pack_a_night_and_the_long_video_goes_first(monkeypatch, tmp_path):
    rec, q = tmp_path / "rec.json", tmp_path / "q.json"
    q.write_text(json.dumps([{"pack": "seneca", "size": "phone"}]))
    rec.write_text(json.dumps([{"pack": "marcus", "size": "phone", "updated": "2026-11-14T21:30:00Z"}]))
    day = dt.date(2026, 11, 14)
    assert w.night_done(day, rec, q) == "marcus phone"                 # recorded tonight and left the queue
    assert w.night_done(dt.date(2026, 11, 15), rec, q) is None          # a new night
    q.write_text(json.dumps([{"pack": "marcus", "size": "phone"}]))
    assert w.night_done(day, rec, q) is None                            # unfinished packs stay in the queue and resume


def test_the_queue_step_exits_zero_with_an_empty_pack_when_yielding(monkeypatch, tmp_path, capsys):
    out = tmp_path / "gh"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(w, "yield_reason", lambda today=None: "yielding to the long video: 5 of 37 scenes unpainted")
    assert w.main(["queue"]) == 0
    assert "pack=\n" in out.read_text() and "yielding" in capsys.readouterr().out


def test_a_pack_is_never_recorded_without_its_real_count(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    rec = tmp_path / "wallpapers.json"
    with pytest.raises(SystemExit):
        wp.record("marcus", "phone", out, rec)                       # no manifest
    (out / "marcus-phone-manifest.json").write_text(json.dumps({"count": 0, "files": []}))
    with pytest.raises(SystemExit):
        wp.record("marcus", "phone", out, rec)                       # the old "count 0" record
    (out / "marcus-phone-manifest.json").write_text(json.dumps({"files": [{}, {}, {}]}))
    assert wp.record("marcus", "phone", out, rec)[0]["count"] == 3
    assert not rec.exists() or json.loads(rec.read_text())[0]["count"] == 3


def test_a_failed_night_reports_itself_and_a_finished_pack_leaves_the_queue(tmp_path):
    import yaml
    wf = yaml.safe_load(WF.read_text(encoding="utf-8"))
    steps = wf["jobs"]["pack"]["steps"]
    fail = next(s for s in steps if s.get("if") == "failure()")
    assert "hq_outbox.py log" in fail["run"] and "alert" in fail["run"] and "git push" in fail["run"]
    q = tmp_path / "q.json"
    q.write_text(json.dumps([{"pack": "marcus", "size": "phone"}, {"pack": "seneca", "size": "phone"}]))
    assert w.queue_pop("marcus", "phone", q) == 1 and w.queue_head(q)["pack"] == "seneca"


@pytest.mark.parametrize("kind", ["phone", "desktop"])
def test_every_pack_makes_a_free_sample_and_a_full_paid_pack(kind, tmp_path):
    """Owner 2026-11-24: the free zip is small (5 max, 1080x1920 / 1920x1080, JPEG ~80,
    corner mark); the $5 zip is every wallpaper at full quality with no mark."""
    quotes = [dict(QUOTES[i % 2], id=f"q{i}") for i in range(7)]
    out = tmp_path / "out"
    w.render_pack("seneca", kind, out, quotes=quotes, painter_fn=stand_in(tmp_path))
    m = w.package_pack("seneca", kind, out)
    full = zipfile.ZipFile(out / f"seneca-{kind}.zip")
    free = zipfile.ZipFile(out / f"seneca-{kind}-free.zip")
    fnames = [n for n in free.namelist() if n != "README.txt"]
    pnames = [n for n in full.namelist() if n != "README.txt"]
    assert len(pnames) == 7 and len(fnames) == w.FREE_COUNT == 5
    fw, fh = w.FREE_SIZES[kind]
    s = w.SIZES[kind]
    assert (fw, fh) == ((1080, 1920) if kind == "phone" else (1920, 1080))
    free.extractall(tmp_path / "f"); full.extractall(tmp_path / "p")
    for n in fnames:
        assert n.endswith(".jpg") and Image.open(tmp_path / "f" / n).size == (fw, fh)
    for n in pnames:
        assert Image.open(tmp_path / "p" / n).size == (s["w"], s["h"])
    assert sum(len(free.read(n)) for n in fnames) < sum(len(full.read(n)) for n in pnames)
    fr = free.read("README.txt").decode()
    assert "$5" in fr and "free sample" in fr and w.FREE_MARK in fr
    assert "$5" not in full.read("README.txt").decode()
    assert m["free"]["count"] == 5 and m["free"]["zip"] == f"seneca-{kind}-free.zip" and m["count"] == 7
    assert m["free"]["zipSha256"] and m["free"]["dimensions"] == f"{fw}x{fh}"
    man = json.loads((out / f"seneca-{kind}-manifest.json").read_text())
    assert man["free"]["count"] == 5 and man["count"] == 7 and man["zipSha256"] != man["free"]["zipSha256"]


def test_the_free_copy_has_a_corner_mark_and_the_full_one_has_none(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (1170, 2532), (30, 30, 30)).save(src)
    f = w.free_version(src, "phone", tmp_path / "a.jpg")
    im = Image.open(f)
    assert im.size == (1080, 1920) and im.format == "JPEG"
    corner = im.crop((im.width - 400, im.height - 140, im.width, im.height)).convert("L")
    assert corner.getextrema()[1] > 150                      # the white mark shows on the dark picture
    assert Image.open(src).convert("L").getextrema() == (30, 30)  # the full-quality original is untouched


def test_the_record_carries_the_free_count(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    (out / "marcus-phone-manifest.json").write_text(json.dumps({"files": [{}] * 9, "free": {"count": 5}}))
    e = wp.record("marcus", "phone", out, tmp_path / "r.json")[0]
    assert e["count"] == 9 and e["freeCount"] == 5
