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


def test_publish_replaces_assets_in_the_wallpapers_release(monkeypatch, tmp_path):
    for n in ("a-phone.zip", "a-phone-cover.jpg", "a-phone-manifest.json"):
        (tmp_path / n).write_bytes(b"x")
    calls = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    def gh(*args, check=True):
        calls.append(args)
        return R(1 if args[:2] == ("release", "view") else 0)
    monkeypatch.setattr(w, "_gh", gh)
    names = w.publish("a", "phone", tmp_path)
    assert names[0] == "a-phone.zip"
    assert any(c[:3] == ("release", "create", "wallpapers") for c in calls)
    up = [c for c in calls if c[:2] == ("release", "upload")][0]
    assert "--clobber" in up and any(str(tmp_path / "a-phone.zip") == x for x in up)


def test_workflow_is_dispatch_only_with_the_secrets_and_inputs():
    wf = yaml.safe_load(WF.read_text())
    on = wf.get(True) or wf.get("on")
    assert list(on) == ["workflow_dispatch"]
    ins = on["workflow_dispatch"]["inputs"]
    assert ins["pack"]["options"] == ["marcus", "seneca", "epictetus"]
    assert ins["size"]["options"] == ["phone", "desktop"]
    assert ins["limit"]["default"] == "10" and ins["force"]["default"] is False
    text = WF.read_text()
    assert "secrets.CLOUDFLARE_ACCOUNT_ID" in text and "secrets.CLOUDFLARE_API_TOKEN" in text
    assert "schedule" not in on and "still_cache" in text and "stills-" in text
    assert "wallpapers.py render" in text and "wallpapers.py package" in text and "wallpapers.py publish" in text
    assert "upload-artifact" in text
