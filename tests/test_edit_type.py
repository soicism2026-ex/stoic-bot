"""Callimachus's type for the edit format (REEL_TYPE=v2, src/edit_type.py).

Owner, 2026-11-10, in the HQ: "Deploy agents to design higher quality
videos." The audit of the edit's text: frame 0 showed the hook at 40% opacity,
system fonts under a thick black outline, a small high quote, a tiny author,
and ~2 s of picture with no text at the end. v2 is the premium type the
niche's winners use. It ships behind REEL_TYPE and changes nothing until the
owner picks it (tests/test_type_classic_golden.py pins the classic path).
"""
import datetime as dt
import importlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import edit_type as T  # noqa: E402

SHELF = json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))
HOOK = "Winning right now? Hold it loosely."
QUOTE = "Receive wealth or prosperity without arrogance; and be ready to let it go."
AUTHOR = "Marcus Aurelius"


def _plain(ass_text: str) -> str:
    """The text field of Dialogue lines (or bare event text), without
    override blocks."""
    parts = [l.split(",", 9)[9] if l.startswith("Dialogue:") else l
             for l in ass_text.split("\n")]
    return re.sub(r"\{[^}]*\}", "", " ".join(parts))


# --- the flag and its knobs ------------------------------------------------

def test_only_v2_turns_the_new_type_on():
    assert T.enabled("v2") and T.enabled(" V2 ")
    for off in (None, "", "classic", "v1", "true", "1"):
        assert not T.enabled(off)


def test_watermark_defaults_to_the_handle_and_empty_turns_it_off():
    assert T.watermark_text(None) == "@forged.in.stoicism"
    assert T.watermark_text("") == ""
    assert T.watermark_text("  @other ") == "@other"
    assert T.watermark_events("", 0, 10) == []


def test_source_line_drops_the_translator():
    assert T.source_line("Meditations 10.16, trans. George Long") == "Meditations 10.16"
    assert T.source_line("Moral Letters 18, trans. Richard M. Gummere") == "Moral Letters 18"
    assert T.source_line("Discourses I.18") == "Discourses I.18"
    assert T.source_line("") == ""


# --- fonts -----------------------------------------------------------------

def _family(path: Path) -> str:
    """nameID 1 (Windows, English) of a TrueType file."""
    data = path.read_bytes()
    n = struct.unpack(">H", data[4:6])[0]
    for i in range(n):
        tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        if tag == b"name":
            count, str_off = struct.unpack(">HH", data[off + 2: off + 6])
            for r in range(count):
                pid, eid, lang, nid, ln, o = struct.unpack(
                    ">HHHHHH", data[off + 6 + 12 * r: off + 18 + 12 * r])
                if pid == 3 and nid == 1:
                    s = off + str_off + o
                    return data[s: s + ln].decode("utf-16-be")
    return ""


def test_fonts_ship_with_the_repo_small_named_and_licensed():
    """The GitHub runner has only DejaVu and Liberation: every face the design
    uses travels in assets/fonts/ttf, under the family name the ASS asks for,
    with its SIL Open Font License."""
    total = 0
    for (family, _italic), name in T.FONT_FILES.items():
        p = T.FONTS_DIR / name
        assert p.exists(), name
        assert _family(p) == family, name
        total += p.stat().st_size
    assert total < 400_000, "keep assets/fonts small (only the weights used)"
    for lic in ("OFL-Anton.txt", "OFL-CormorantGaramond.txt", "OFL-Cinzel.txt"):
        text = (T.FONTS_DIR.parent / lic).read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE VERSION 1.1" in text.upper()
    assert sorted(p.name for p in T.FONTS_DIR.iterdir()) == sorted(T.FONT_FILES.values()), \
        "only fonts in the fontsdir libass scans"


def test_widths_match_an_independent_reader():
    try:
        from PIL import ImageFont
    except ImportError:                              # no Pillow, or one without its C core
        pytest.skip("Pillow unavailable")
    for (family, italic), name in T.FONT_FILES.items():
        f = T.font(family, italic)
        fs = 100.0 * f.cell / f.upm                  # an em of exactly 100 px
        try:
            ref = ImageFont.truetype(str(T.FONTS_DIR / name), size=100).getlength(
                "Receive WEALTH, or let it go?")
        except ImportError:                          # a Pillow without its C core
            pytest.skip("Pillow cannot load fonts here")
        assert abs(f.width("Receive WEALTH, or let it go?", fs) - ref) / ref < 0.01, name


# --- emphasis --------------------------------------------------------------

def test_emphasis_matches_whole_words_case_and_punctuation_free():
    words = QUOTE.split()
    m = T.emphasis_mask(words, "ARROGANCE|let it go|nowhere|be")
    marked = [w for w, e in zip(words, m) if e]
    assert marked == ["arrogance;", "be", "let", "it", "go."]
    assert T.emphasis_mask(words, "") == [False] * len(words)
    assert T.emphasis_mask(words, "arrog") == [False] * len(words), "whole words only"
    assert T.emphasis_unmatched(QUOTE, "arrogance|not here|let it go") == ["not here"]


def test_emphasised_punctuation_stays_roman():
    block = T.layout_quote(QUOTE, AUTHOR, "arrogance")
    ev = "\n".join(T.quote_events(block, [], 0, 5))
    assert "{\\i1\\1c" in ev and "}arrogance{\\i0" in ev and "{\\i0\\1c&HD8EAF4&\\2c&HD8EAF4&};" in ev


# --- layout: every hook and quote on the shelf fits ------------------------

def _line_w(block, k, roman, italic=None):
    words = [block.words[i] for i in block.lines[k]]
    emph = [block.emph[i] for i in block.lines[k]]
    if italic is None:
        return roman.width(" ".join(words), block.fs)
    return sum(T._word_width(w, e, block.fs, roman, italic) for w, e in zip(words, emph)) \
        + roman.width(" ", block.fs) * (len(words) - 1)


def test_every_hook_on_the_shelf_fits_three_lines_inside_the_phone():
    f = T.font(T.HOOK_FONT)
    for e in SHELF:
        b = T.layout_hook(e["hook"])
        assert 1 <= len(b.lines) <= 3, e["id"]
        assert b.fs >= T.HOOK_FS_MIN, e["id"]
        assert " ".join(b.words) == e["hook"].upper(), e["id"]
        for k in range(len(b.lines)):
            assert _line_w(b, k, f) <= T.TEXT_W + 0.5, (e["id"], b.line_text(k))
        assert T.TEXT_TOP <= b.top and b.bottom <= T.TEXT_BOTTOM, e["id"]


def test_hooks_break_where_the_sense_breaks():
    b = T.layout_hook(HOOK)
    assert [b.line_text(k) for k in range(len(b.lines))] == ["WINNING", "RIGHT NOW?", "HOLD IT LOOSELY."]
    b = T.layout_hook("Can't resist it yet? Don't stand near it.")
    assert [b.line_text(k) for k in range(len(b.lines))] == ["CAN'T RESIST IT YET?", "DON'T STAND NEAR IT."]


def test_every_quote_on_the_shelf_fits_verbatim_and_clear_of_the_watermark():
    roman, italic = T.font(T.QUOTE_FONT), T.font(T.QUOTE_FONT, True)
    for e in SHELF:
        b = T.layout_quote(e["quote"], e["author"], "", T.source_line(e["citation"]))
        assert len(b.lines) <= T.QUOTE_HARD_MAX_LINES, e["id"]
        assert b.fs >= T.QUOTE_FS_FLOOR, e["id"]
        assert [b.words[i] for ln in b.lines for i in ln] == e["quote"].split(), "verbatim, in order"
        for k in range(len(b.lines)):
            assert _line_w(b, k, roman, italic) <= T.TEXT_W + 0.5, (e["id"], b.line_text(k))
        assert T.TEXT_TOP <= b.top and b.bottom <= T.TEXT_BOTTOM < T.MARK_Y - 40, e["id"]


def test_quotes_are_larger_than_today_and_long_ones_stay_calm():
    """Today: 84 px Liberation Serif Bold, x-height ~34 px. v2: a typical
    quote gets a bigger x-height; no quote runs past 8 lines (today's
    longest ran to 10)."""
    roman = T.font(T.QUOTE_FONT)
    xh = lambda fs: fs * roman.x_height / roman.cell  # noqa: E731
    b = T.layout_quote(QUOTE, AUTHOR)
    assert xh(b.fs) > 34 and len(b.lines) <= 5
    sizes = sorted(T.layout_quote(e["quote"], e["author"]).fs for e in SHELF)
    assert xh(sizes[len(sizes) // 2]) > 34, "the median quote is larger than today's"


# --- events ----------------------------------------------------------------

def test_hook_is_fully_drawn_on_frame_zero_and_the_spoken_word_turns_gold():
    b = T.layout_hook(HOOK, "loosely")
    starts = [1.2 + 0.31 * i for i in range(len(b.words))]
    ev = T.hook_events(b, starts, 0.0, 3.4, 0, 320)
    text = [e for e in ev if ",TypeHook," in e]
    assert len(text) == len(b.lines)
    for e in text:
        assert e.startswith("Dialogue: 2,0:00:00.00,"), "on screen from frame 0"
        assert "\\fad(0,320)" in e, "no fade-in"
        assert "\\1a" not in e and "\\alpha" not in e and "&H99" not in e, "no dimmed words"
    joined = "".join(text)
    gold = T._c(T.GOLD)
    # WINNING (spoken at 1.20 s) turns gold over 60 ms and settles at RIGHT (1.51 s)
    assert f"\\t(1200,1260,\\1c{gold})\\t(1510,1630,\\1c&HFFFFFF&)}}WINNING" in joined
    # the emphasis word is gold from the start and never transformed
    assert f"{{\\1c{gold}}}LOOSELY." in joined
    assert _plain("\n".join(text)).split() == HOOK.upper().split()


def test_quote_karaoke_reads_unspoken_words_at_75_percent_and_keeps_its_words():
    b = T.layout_quote(QUOTE, AUTHOR, "arrogance|let it go", "Meditations 8.33")
    times = [(4.0 + 0.32 * i, 4.27 + 0.32 * i) for i in range(len(b.words))]
    ev = T.quote_events(b, times, 3.7, 12.0)
    style = [s for s in T.ass_styles() if s.startswith("Style: TypeQuote,")][0]
    assert ",&H40D8EAF4," in style, "unread words 75% opaque, not 40%"
    lines = [e for e in ev if ",TypeQuote," in e and "\\k" in e]
    assert len(lines) == len(b.lines)
    assert all(",0:00:12.00,TypeQuote" in e for e in lines)
    assert _plain("\n".join(lines)).split() == QUOTE.split(), "verbatim"
    first = lines[0]
    assert "{\\k30}" in first, "silent lead until the first spoken word"
    names = [e for e in ev if ",TypeAuthor," in e]
    assert names and "MARCUS AURELIUS" in names[0]
    assert any("Meditations 8.33" in e for e in ev)


def test_one_band_reshapes_from_hook_to_quote():
    h = T.layout_hook(HOOK)
    q = T.layout_quote(QUOTE, AUTHOR)
    ev = T.bands(h, (0.0, 3.4, 0), q, (3.7, 11.0))
    assert len(ev) == len(T.BAND_LAYERS)
    assert all("\\move(-300," in e and "\\fscy" in e for e in ev)
    assert all(e.startswith("Dialogue: 0,0:00:00.00,0:00:11.00,") for e in ev)


# --- render.py integration --------------------------------------------------

EDIT_PACK = {
    "REEL_HOOK_CAPS": "1", "REEL_HOOK_WRAP": "16", "REEL_HOOK_SOUND": "0",
    "REEL_FRAME": "0", "REEL_CINEMATIC": "0", "REEL_EXTRA_DARKEN": "0",
    "REEL_BRIGHTNESS": "-0.02", "REEL_MONO": "1", "REEL_HOOK_ASS_FONTSIZE": "96",
    "REEL_HOOK_FROM_START": "1", "REEL_QUOTE_ASS_FS": "84", "REEL_TAIL": "2.0",
    "REEL_SFX": "0", "REEL_BG_CLIPS": "8", "REEL_QUOTE_APPEAR": "3.10", "REEL_QUOTE_SPOKEN": "1",
}


def _timings(quote=QUOTE):
    wt, t = [], 1.2
    for w in HOOK.split():
        wt.append((w, round(t, 3), round(t + 0.26, 3)))
        t += 0.30
    t += 0.7
    for w in quote.split():
        wt.append((w, round(t, 3), round(t + 0.28, 3)))
        t += 0.33
    return wt


@pytest.fixture
def v2_render(tmp_path, monkeypatch):
    """render_reel with the edit pack and REEL_TYPE=v2, ffmpeg captured."""
    def run(extra=None, timings=None, quote=QUOTE):
        for k in list(os.environ):
            if k.startswith("REEL_"):
                monkeypatch.delenv(k, raising=False)
        for k, v in {**EDIT_PACK, "REEL_TYPE": "v2", **(extra or {})}.items():
            monkeypatch.setenv(k, v)
        import render
        importlib.reload(render)
        calls = []

        class _Done:
            returncode, stdout, stderr = 0, b"", b""
        monkeypatch.setattr(render, "_air_day", lambda: dt.date(2026, 11, 11))
        monkeypatch.setattr(render, "_generated_backgrounds_active", lambda: False)
        monkeypatch.setattr(render, "fetch_background", lambda theme, path, clip_idx=0: Path(path))
        monkeypatch.setattr(render, "_audio_duration",
                            lambda p: 9.0 if str(p).endswith((".mp3", ".m4a", ".wav")) else 30.0)
        monkeypatch.setattr(render.proc, "run", lambda cmd, **kw: calls.append(cmd) or _Done())
        out = tmp_path / "reel.mp4"
        render.render_reel(quote=quote, author=AUTHOR, audio_path=tmp_path / "voice.mp3",
                           out_path=out, theme="desire", word_timings=timings or _timings(),
                           hook=HOOK, callout_words=[], music_path=None, mission="")
        ass = (tmp_path / "reel.captions.ass").read_text(encoding="utf-8")
        return render, calls[-1], ass
    yield run
    monkeypatch.undo()
    import render
    importlib.reload(render)


def _graph(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


def test_v2_render_uses_the_shipped_fonts_and_no_drawtext_cards(v2_render):
    render, cmd, ass = v2_render()
    graph = _graph(cmd)
    assert f":fontsdir='{T.FONTS_DIR}'" in graph
    assert "drawtext" not in graph, "every letter is drawn by the ASS pass"
    assert "Style: TypeHook,Anton," in ass and "Style: TypeQuote,Cormorant Garamond Bold," in ass


def test_v2_text_stays_to_the_last_frame(v2_render):
    """Classic hid the quote when the voice ended: ~2 s of bare picture."""
    render, cmd, ass = v2_render()
    dur = float(cmd[cmd.index("-t") + 1])            # 9.0 s of voice + 2.0 s tail
    end = T._t(dur)
    quote_ev = [l for l in ass.splitlines() if ",TypeQuote," in l]
    assert quote_ev and all(f",{end},TypeQuote," in l for l in quote_ev)
    assert any(f",{end},TypeAuthor," in l and "MARCUS AURELIUS" in l for l in ass.splitlines())
    assert "@forged.in.stoicism" in ass, "watermark on by default in v2"
    hook_ev = [l for l in ass.splitlines() if ",TypeHook," in l]
    assert hook_ev and all(l.startswith("Dialogue: 2,0:00:00.00,") for l in hook_ev)


def test_v2_knobs_reach_the_frame(v2_render):
    render, cmd, ass = v2_render({"REEL_WATERMARK": "", "REEL_QUOTE_SOURCE": "Meditations 8.33",
                                  "REEL_QUOTE_EMPHASIS": "arrogance|let it go",
                                  "REEL_HOOK_EMPHASIS": "loosely"})
    assert "@forged.in.stoicism" not in ass, "REEL_WATERMARK='' turns it off"
    assert "Meditations 8.33" in ass
    assert ass.count("\\i1\\1c") == 4, "arrogance + let + it + go in gold italic"
    assert f"{{\\1c{T._c(T.GOLD)}}}LOOSELY." in ass


def test_v2_falls_back_to_a_static_quote_when_the_voice_said_other_words(v2_render):
    other = _timings("Something else entirely was read by the voice that day instead.")
    render, cmd, ass = v2_render(timings=other)
    quote_ev = [l for l in ass.splitlines() if ",TypeQuote," in l and "MARCUS" not in l]
    assert quote_ev, "the quote still shows"
    assert not any("\\k" in l for l in quote_ev), "no karaoke without timings"
    assert _plain("\n".join(quote_ev)).split() == QUOTE.split()
    assert "drawtext" not in _graph(cmd)


def test_v2_thumbnail_is_the_first_frame_as_a_poster(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith("REEL_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REEL_TYPE", "v2")
    monkeypatch.setenv("REEL_HOOK_EMPHASIS", "loosely")
    import render
    importlib.reload(render)
    calls = []
    monkeypatch.setattr(render.proc, "run", lambda cmd, **kw: calls.append(cmd))
    out = render.generate_thumbnail(HOOK, AUTHOR, tmp_path / "bg.mp4", tmp_path / "t.jpg")
    assert out == tmp_path / "t.jpg"
    vf = calls[0][calls[0].index("-vf") + 1]
    assert f"fontsdir='{T.FONTS_DIR}'" in vf and "drawtext" not in vf
    doc = (tmp_path / "t.thumb.ass").read_text(encoding="utf-8")
    assert "LOOSELY." in doc and "MARCUS AURELIUS" in doc and T._c(T.GOLD) in doc
    monkeypatch.undo()
    importlib.reload(render)


# --- libass really draws the shipped faces ----------------------------------

@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg with libass")
def test_libass_draws_anton_from_the_fontsdir_at_the_measured_width(tmp_path):
    """If the fontsdir were not read, libass would fall back to DejaVu and the
    line would come out a different width from the one the layout measured."""
    b = T.layout_hook("WINNING")
    doc = T.document(T.hook_events(b, [], 0, 1, 0, 0))
    ass = tmp_path / "w.ass"
    ass.write_text(doc, encoding="utf-8")
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=1080x1920:d=0.2",
         "-vf", f"ass='{ass}':fontsdir='{T.FONTS_DIR}',format=gray", "-frames:v", "1",
         "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    assert len(raw) == 1080 * 1920
    rows = [raw[y * 1080:(y + 1) * 1080] for y in range(1920)]
    ink = [(y, r) for y, r in enumerate(rows) if max(r) > 200]
    left = min(next(i for i, v in enumerate(r) if v > 200) for _, r in ink)
    right = max(1079 - next(i for i, v in enumerate(reversed(r)) if v > 200) for _, r in ink)
    want = T.font(T.HOOK_FONT).width("WINNING", b.fs)
    assert abs((right - left) - want) / want < 0.05, (right - left, want)
    top, bottom = ink[0][0], ink[-1][0]
    cap = b.fs * T.font(T.HOOK_FONT).cap_height / T.font(T.HOOK_FONT).cell
    assert abs((bottom - top) - cap) / cap < 0.06, "cap height as laid out"
    assert abs(bottom - b.baselines[0]) <= 3, "baseline where the layout put it"
