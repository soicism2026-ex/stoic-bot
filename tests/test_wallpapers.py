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


def test_guard_refuses_before_20_utc_without_force(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    monkeypatch.setattr(w, "utcnow", lambda: dt.datetime(2026, 11, 14, 9, 30, tzinfo=dt.timezone.utc))
    painted = []
    monkeypatch.setattr(w, "paint_one", lambda p, s: painted.append(s))
    rc = w.main(["render", "--pack", "seneca", "--size", "phone", "--out", str(tmp_path)])
    assert rc == w.EXIT_GUARD and not painted
    assert "20:00 UTC" in capsys.readouterr().err


def test_guard_passes_after_20_and_prints_neuron_estimate(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "y")
    monkeypatch.setenv("REEL_STILL_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(w, "utcnow", lambda: dt.datetime(2026, 11, 14, 20, 5, tzinfo=dt.timezone.utc))
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
    steps = wf["jobs"][next(iter(wf["jobs"]))]["steps"]
    art = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    assert art["with"]["path"].endswith(".zip") and art["with"]["retention-days"] == 90
    pop = next(s for s in steps if "queue --pop" in s.get("run", ""))
    assert "steps.paint.outputs.complete == '1'" in pop["if"]
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
    for n in ("marcus-phone-cover.jpg", "marcus-phone-manifest.json", "marcus-phone.zip"):
        (tmp_path / n).write_bytes(b"x")
    names = wp.publish("marcus", "phone", tmp_path)
    assert names == ["marcus-phone-cover.jpg", "marcus-phone-manifest.json"]
    uploaded = next(a for a in calls if a[:2] == ("release", "upload"))
    assert not any(x.endswith(".zip") for x in uploaded)