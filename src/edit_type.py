"""
Callimachus's type for the edit format: every letter on screen, REEL_TYPE=v2.

Owner, 2026-11-10, in the HQ: "Deploy agents to design higher quality videos."
The crew's audit of the edit format's text (the next Short to air, rendered by
the real pipeline): frame 0 showed the hook at 40% opacity, grey on a pale
picture, because each word only brightened when spoken; system fonts (DejaVu
Sans Bold caps under a thick black outline, Liberation Serif Bold for the
quote); the quote small and high; a tiny author line; and the last ~2 s of
picture with no text at all. The niche's winners set premium centred type:
heavy condensed caps hooks, serif quotes with key words in gold italic, the
author in spaced capitals, a small @handle.

This module is that type system. render.py calls it only when REEL_TYPE=v2;
with the flag unset (or "classic") nothing here runs and the classic look is
byte-identical (tests/test_type_classic_golden.py).

  Hook    Anton (heavy condensed sans), white caps, centred, at most 3 lines
          inside what an iPhone shows, fully legible on frame 0. The spoken
          word turns gold as the voice reads it (a moving highlight, never by
          dimming the rest). REEL_HOOK_EMPHASIS: words set in gold from the
          first frame.
  Quote   Cormorant Garamond Bold, warm parchment, centred in the safe area,
          sized to its length, sense-based line breaks. Karaoke kept: spoken
          words full strength, unread ones at 75%. REEL_QUOTE_EMPHASIS
          ("arrogance|let it go"): those words in gold italic.
  Author  Cinzel, spaced Roman capitals in gold under the quote; an optional
          source line beneath (REEL_QUOTE_SOURCE, e.g. "Meditations 8.33").
  Mark    REEL_WATERMARK ("@forged.in.stoicism" by default; "" = off), small,
          inside every safe zone, clear of the text and YouTube's buttons.
  Legible on any picture: a soft blurred shadow under every glyph and a soft
  dark gradient band behind each text block. No thick outlines, no boxes.

Fonts (SIL Open Font License 1.1, files and licences in assets/fonts/) are
static instances cut from the Google Fonts releases and given to libass with
the ass filter's fontsdir, so the GitHub runner (DejaVu and Liberation only)
renders exactly what was designed. Layout is computed here from the fonts'
own metrics (a small TrueType reader, no extra dependency), so every line
break, size and position is decided before libass draws a pixel.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts" / "ttf"

W, H = 1080, 1920

# ---------------------------------------------------------------------------
# Fonts. Family names are the ones written inside the committed TTFs
# (scripts/make_type_fonts.py cuts them); libass finds them by these names.
# ---------------------------------------------------------------------------
HOOK_FONT = "Anton"
QUOTE_FONT = "Cormorant Garamond Bold"
AUTHOR_FONT = "Cinzel SemiBold"

FONT_FILES = {
    (HOOK_FONT, False): "Anton-Regular.ttf",
    (QUOTE_FONT, False): "CormorantGaramond-Bold.ttf",
    (QUOTE_FONT, True): "CormorantGaramond-BoldItalic.ttf",
    (AUTHOR_FONT, False): "Cinzel-SemiBold.ttf",
}


class Font:
    """Advance widths and vertical metrics straight from a TrueType file.

    libass sizes a font so that usWinAscent + usWinDescent (the "real
    dimension") equals the requested \\fs in pixels, so one font unit is
    fs / (winAscent + winDescent) pixels, and that is how widths are scaled
    here. Kerning is ignored: it only ever tightens these faces' Latin pairs,
    so a measured line is never narrower than the drawn one.
    """

    def __init__(self, path: Path):
        data = Path(path).read_bytes()
        self.path = Path(path)
        n = struct.unpack(">H", data[4:6])[0]
        tables = {}
        for i in range(n):
            tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
            tables[tag.decode("latin-1")] = (off, length)

        def tbl(tag):
            off, length = tables[tag]
            return data[off: off + length]

        head = tbl("head")
        self.upm = struct.unpack(">H", head[18:20])[0]
        hhea = tbl("hhea")
        n_hmetrics = struct.unpack(">H", hhea[34:36])[0]
        os2 = tbl("OS/2")
        self.win_ascent, self.win_descent = struct.unpack(">HH", os2[74:78])
        version = struct.unpack(">H", os2[0:2])[0]
        self.x_height = self.cap_height = 0
        if version >= 2 and len(os2) >= 90:
            self.x_height, self.cap_height = struct.unpack(">hh", os2[86:90])
        hmtx = tbl("hmtx")
        adv = [struct.unpack(">H", hmtx[4 * i: 4 * i + 2])[0] for i in range(n_hmetrics)]
        self._adv = adv
        self._cmap = self._read_cmap(tbl("cmap"))
        self.cell = self.win_ascent + self.win_descent

    @staticmethod
    def _read_cmap(cmap: bytes) -> dict:
        n = struct.unpack(">H", cmap[2:4])[0]
        subs = {}
        for i in range(n):
            pid, eid, off = struct.unpack(">HHI", cmap[4 + 8 * i: 12 + 8 * i])
            subs[(pid, eid)] = off
        for key in ((3, 10), (0, 4), (3, 1), (0, 3)):
            if key not in subs:
                continue
            off = subs[key]
            fmt = struct.unpack(">H", cmap[off: off + 2])[0]
            if fmt == 4:
                seg2 = struct.unpack(">H", cmap[off + 6: off + 8])[0]
                segs = seg2 // 2
                p = off + 14
                ends = struct.unpack(f">{segs}H", cmap[p: p + seg2])
                p += seg2 + 2
                starts = struct.unpack(f">{segs}H", cmap[p: p + seg2])
                p += seg2
                deltas = struct.unpack(f">{segs}h", cmap[p: p + seg2])
                p += seg2
                ro_pos = p
                ros = struct.unpack(f">{segs}H", cmap[p: p + seg2])
                out = {}
                for s in range(segs):
                    for c in range(starts[s], ends[s] + 1):
                        if c == 0xFFFF:
                            continue
                        if ros[s] == 0:
                            g = (c + deltas[s]) & 0xFFFF
                        else:
                            gp = ro_pos + 2 * s + ros[s] + 2 * (c - starts[s])
                            g = struct.unpack(">H", cmap[gp: gp + 2])[0]
                            if g:
                                g = (g + deltas[s]) & 0xFFFF
                        if g:
                            out[c] = g
                return out
            if fmt == 12:
                ngroups = struct.unpack(">I", cmap[off + 12: off + 16])[0]
                out = {}
                for gi in range(ngroups):
                    s, e, g0 = struct.unpack(">III", cmap[off + 16 + 12 * gi: off + 28 + 12 * gi])
                    for c in range(s, min(e, 0x2FFFF) + 1):
                        out[c] = g0 + (c - s)
                return out
        return {}

    def has(self, ch: str) -> bool:
        return ord(ch) in self._cmap

    def advance(self, ch: str) -> int:
        g = self._cmap.get(ord(ch), 0)
        return self._adv[g] if g < len(self._adv) else self._adv[-1]

    def width(self, text: str, fs: float, spacing: float = 0.0) -> float:
        """Pixel width of `text` at libass size `fs` with \\fsp `spacing`."""
        units = sum(self.advance(c) for c in text)
        return units * fs / self.cell + spacing * len(text)

    def px(self, units: float, fs: float) -> float:
        return units * fs / self.cell


@lru_cache(maxsize=None)
def font(family: str, italic: bool = False) -> Font:
    return Font(FONTS_DIR / FONT_FILES[(family, italic)])


# ---------------------------------------------------------------------------
# Geometry. A Short is 1080x1920; an iPhone shows x 120..960 of it, YouTube's
# search bar covers the top 8%, the title/channel/sound the bottom 22%, and
# the like/comment/share column the right edge from y ~1000 down.
# ---------------------------------------------------------------------------
CROP_L, CROP_R = 120, 960
TEXT_W = 720                       # 60 px of air inside the crop on each side
TOP_UI, BOTTOM_UI = 154, 1498
BUTTONS_X, BUTTONS_Y = 930, 1000
TEXT_TOP, TEXT_BOTTOM = 300, 1370  # the hook and the quote block live in here
CENTER_Y = 820                     # optical centre shared by hook and quote

# Colours (hex RGB). One gold for everything gold: the spoken hook word, the
# emphasis words, the author.
WHITE = "FFFFFF"
GOLD = "F3BF4C"
PARCHMENT = "F4EAD8"
UNREAD_ALPHA = 0x40                # quote words not yet spoken: 75% opaque

# Hook: Anton, sized to fill the measure in at most 3 lines.
HOOK_FS_MAX, HOOK_FS_MIN = 236, 120
HOOK_FS_GOOD = 196                 # cap height ~97 px: big enough to stop a thumb
HOOK_LEADING = 1.08                # line pitch in ems (caps only, so tight)
HOOK_MAX_LINES = 3
# The thumbnail's hook: the same face and treatment at poster scale.
THUMB_MAX_LINES, THUMB_FS_MAX, THUMB_FS_GOOD, THUMB_TEXT_W = 4, 330, 290, 780

# Quote: Cormorant Garamond Bold. 140 = x-height 39 px (today's 84 px
# Liberation Serif has 34); long quotes step down to keep the block calm.
QUOTE_FS_MAX, QUOTE_FS_MIN, QUOTE_FS_FLOOR = 140, 96, 80
QUOTE_LEADING = 1.16
QUOTE_MAX_LINES = 6                # the usual ceiling; the longest quotes may take 8
QUOTE_HARD_MAX_LINES = 8

AUTHOR_FS, AUTHOR_SPACING = 50, 6
SOURCE_FS = 56
MARK_FS, MARK_SPACING = 40, 1.5
MARK_Y = 1450                      # watermark baseline: above the bottom UI
MARK_ALPHA = 0x66                  # 60% opaque: there, but quiet
DEFAULT_WATERMARK = "@forged.in.stoicism"

FUNCTION_WORDS = frozenset(
    "a an the of to in on at by for with and or but nor as if that than then "
    "thy thou thee his her your my our their its is be are was not no so from "
    "into upon this these those which who whom about over under through "
    "without before after against toward towards like".split())
PRONOUNS = frozenset("i you we they he she it you're they're we're it's "
                     "i'm you've we've they've i've".split())


def enabled(value) -> bool:
    """REEL_TYPE: "v2" turns this type on; "", "classic" or anything else is
    today's type."""
    return str(value or "").strip().lower() == "v2"


TYPE_DATA = ROOT / "data" / "edit_type.json"


def emphasis_for(edit_id: str) -> tuple:
    """(hook emphasis, quote emphasis) for an edit from data/edit_type.json;
    ("", "") when it has no entry or the file cannot be read."""
    try:
        import json
        e = json.loads(TYPE_DATA.read_text(encoding="utf-8"))["emphasis"].get(edit_id or "", {})
    except Exception:  # noqa: BLE001  no data never stops a render
        return "", ""
    return e.get("hook", ""), e.get("quote", "")


def style_env(content: dict) -> dict:
    """What the edit style pack adds to air this edit in v2 type: the flag,
    its emphasis and the source under the author. `content` is
    edits.as_content(): it carries _edit_id and _citation. The watermark is
    left to its default (the channel's handle)."""
    hook_e, quote_e = emphasis_for(content.get("_edit_id", ""))
    return {"REEL_TYPE": "v2", "REEL_HOOK_EMPHASIS": hook_e,
            "REEL_QUOTE_EMPHASIS": quote_e,
            "REEL_QUOTE_SOURCE": source_line(content.get("_citation", ""))}


def watermark_text(value) -> str:
    """REEL_WATERMARK: unset = the channel's handle; an empty string = off."""
    if value is None:
        return DEFAULT_WATERMARK
    return str(value).strip()


def source_line(citation: str) -> str:
    """The quote's source as it sits under the author: "Meditations 10.16,
    trans. George Long" -> "Meditations 10.16" (the translator stays in the
    description, where the full citation is)."""
    c = (citation or "").strip()
    c = re.split(r",\s*(?:trans\.|translated|tr\.)", c, maxsplit=1, flags=re.I)[0]
    return c.strip(" ,;")


# ---------------------------------------------------------------------------
# Words, emphasis
# ---------------------------------------------------------------------------
_PARTS = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


def _split(word: str) -> tuple:
    """("(", "difficulties", ")"): leading punctuation, the word, trailing."""
    lead, core, trail = _PARTS.match(word).groups()
    if not core:                       # pure punctuation ("—")
        return "", word, ""
    return lead, core, trail


def _norm(s: str) -> str:
    return s.lower().replace("’", "'").replace("‘", "'")


def emphasis_mask(words: list, spec: str) -> list:
    """Which words of `words` the pipe-separated `spec` marks ("arrogance|let
    it go"): whole words, case-insensitive, punctuation ignored. A phrase that
    is not in the text is ignored."""
    mask = [False] * len(words)
    cores = [_norm(_split(w)[1]) for w in words]
    for phrase in (spec or "").split("|"):
        toks = [_norm(_split(t)[1]) for t in phrase.split()]
        toks = [t for t in toks if t]
        if not toks:
            continue
        for i in range(len(words) - len(toks) + 1):
            if cores[i:i + len(toks)] == toks:
                for j in range(i, i + len(toks)):
                    mask[j] = True
    return mask


def emphasis_unmatched(text: str, spec: str) -> list:
    """The phrases of `spec` that are NOT in `text` (for data checks)."""
    words = text.split()
    return [p.strip() for p in (spec or "").split("|")
            if p.strip() and not any(emphasis_mask(words, p))]


# ---------------------------------------------------------------------------
# Line breaking
# ---------------------------------------------------------------------------
def _break_bonus(word: str) -> float:
    """How good a place the end of `word` is to break a line: by sense."""
    t = word.rstrip("”’\"')")
    if t.endswith((".", "!", "?", ":", ";")):
        return 1.0
    if t.endswith((",", "—", "–", "-")):
        return 0.55
    core = _norm(_split(word)[1])
    if core in FUNCTION_WORDS:
        return -1.0                    # never end a line on "the", "of", "to"
    if core in PRONOUNS:
        return -0.5                    # "you / have": a subject leans on its verb
    return 0.0


def _balanced_lines(widths: list, space: float, words: list, max_w: float, n: int):
    """Split into exactly n lines, each <= max_w, as even as the sense allows.
    Returns (cost, [[word indices], ...]) or (inf, None)."""
    N = len(widths)
    INF = float("inf")
    if n > N:
        return INF, None
    target = (sum(widths) + space * (N - 1)) / n
    best = [[INF] * (N + 1) for _ in range(n + 1)]
    back = [[0] * (N + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for k in range(1, n + 1):
        for j in range(k, N + 1):
            for i in range(k - 1, j):
                if best[k - 1][i] == INF:
                    continue
                w = sum(widths[i:j]) + space * (j - i - 1)
                if w > max_w:
                    continue
                last = k == n and j == N
                c = ((target - w) / max_w) ** 2 * 10
                if last and w < target:
                    c *= 0.5           # a slightly short last line is fine
                if not last:
                    c -= 0.9 * _break_bonus(words[j - 1])
                if j - i == 1 and n > 1:
                    c += 1.2 if last else 0.6      # a widow, a lone word
                if best[k - 1][i] + c < best[k][j]:
                    best[k][j] = best[k - 1][i] + c
                    back[k][j] = i
    if best[n][N] == INF:
        return INF, None
    lines, j = [], N
    for k in range(n, 0, -1):
        i = back[k][j]
        lines.append(list(range(i, j)))
        j = i
    return best[n][N], lines[::-1]


def _min_lines(widths: list, space: float, max_w: float) -> int:
    n, cur = 1, -space
    for w in widths:
        if w > max_w:
            return 10 ** 6
        if cur + space + w > max_w:
            n, cur = n + 1, w
        else:
            cur += space + w
    return n


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------
@dataclass
class Block:
    """A laid-out text block: lines of word indices and their baselines."""
    words: list
    emph: list
    fs: int
    lines: list
    baselines: list
    top: float                         # ink top of the first line
    bottom: float                      # ink bottom of the block
    extra: dict = field(default_factory=dict)

    def line_text(self, k: int) -> str:
        return " ".join(self.words[i] for i in self.lines[k])


def _word_width(word: str, emph: bool, fs: float, roman: Font, italic: Font) -> float:
    if not emph:
        return roman.width(word, fs)
    lead, core, trail = _split(word)
    return roman.width(lead, fs) + italic.width(core, fs) + roman.width(trail, fs)


def layout_hook(hook: str, emphasis: str = "", caps: bool = True,
                center_y: float = CENTER_Y, max_lines: int = HOOK_MAX_LINES,
                fs_max: int = HOOK_FS_MAX, fs_good: int = HOOK_FS_GOOD,
                text_w: int = TEXT_W) -> Block:
    """The hook as big as it can be in at most 3 lines inside the measure,
    broken where the sense breaks ("WINNING / RIGHT NOW? / HOLD IT LOOSELY.").
    The thumbnail asks for a poster: 4 lines, a wider measure, bigger type."""
    from itertools import combinations
    text = hook.upper() if caps else hook
    words = text.split()
    emph = emphasis_mask(words, emphasis)
    f = font(HOOK_FONT)
    unit = [f.width(w, 1.0) for w in words]          # width per 1 px of fs
    space = f.width(" ", 1.0)
    N = len(words)
    best = None
    for n in range(1, min(max_lines, N) + 1):
        for cut in combinations(range(N - 1), n - 1):
            bounds = [0, *[c + 1 for c in cut], N]
            lines = [list(range(bounds[k], bounds[k + 1])) for k in range(n)]
            widths = [sum(unit[i] for i in ln) + space * (len(ln) - 1) for ln in lines]
            fs = min(fs_max, int(text_w / max(widths)))
            # Size counts in full up to fs_good (already a poster), then
            # little: past it, reading by sense matters more than pixels.
            score = min(fs, fs_good) + 0.15 * max(0, fs - fs_good)
            score += 24 * sum(_break_bonus(words[ln[-1]]) for ln in lines[:-1])
            for ln in lines:
                # a sentence that ends inside a line ("NOW? HOLD") while
                # another line breaks mid-phrase reads as one run-on
                score -= 22 * sum(1 for i in ln[:-1] if _break_bonus(words[i]) == 1.0)
                if len(ln) == 1 and n > 1:
                    w = words[ln[0]]
                    letters = len(_split(w)[1])
                    score -= (6 if _break_bonus(w) == 1.0 else 12) if letters >= 5 else 24
            if n > 1:
                score -= 22 * (max(widths) - min(widths)) / max(widths)
            score -= 6 * (n - 1)
            if best is None or score > best[0]:
                best = (score, fs, lines)
    _, fs, lines = best
    fs = max(HOOK_FS_MIN, fs)
    em = fs * f.upm / f.cell
    cap = em * f.cap_height / f.upm
    pitch = em * HOOK_LEADING
    height = (len(lines) - 1) * pitch + cap
    top = center_y - height / 2
    baselines = [top + cap + k * pitch for k in range(len(lines))]
    return Block(words, emph, fs, lines, baselines, top, top + height,
                 {"cap": cap, "pitch": pitch, "em": em})


def layout_quote(quote: str, author: str, emphasis: str = "", source: str = "",
                 center_y: float = CENTER_Y) -> Block:
    """The quote, a gold rule, the author and the source as one block centred
    on center_y: the biggest size whose sense-broken lines fit (6 lines, 8
    for the longest quotes), never past TEXT_TOP..TEXT_BOTTOM."""
    words = quote.split()
    emph = emphasis_mask(words, emphasis)
    roman, italic = font(QUOTE_FONT), font(QUOTE_FONT, True)
    auth = font(AUTHOR_FONT)
    chosen = None
    # 6 lines at the biggest size down to QUOTE_FS_MIN; only a quote that
    # would need smaller type than that gets a 7th line, then an 8th.
    for max_lines, lo in ((QUOTE_MAX_LINES, QUOTE_FS_MIN),
                          (QUOTE_MAX_LINES + 1, (QUOTE_FS_MIN + QUOTE_FS_FLOOR) // 2),
                          (QUOTE_HARD_MAX_LINES, QUOTE_FS_FLOOR)):
        first = None                   # the biggest size that fits at all
        for fs in range(QUOTE_FS_MAX, lo - 1, -2):
            if first is not None and fs < first - 16:
                break
            widths = [_word_width(w, e, fs, roman, italic) for w, e in zip(words, emph)]
            space = roman.width(" ", fs)
            n0 = _min_lines(widths, space, TEXT_W)
            if n0 > max_lines:
                continue
            if _quote_geometry(fs, n0, roman, auth, bool(source))["height"] > TEXT_BOTTOM - TEXT_TOP:
                continue
            for n in (n0, n0 + 1):
                if n <= max_lines:
                    cost, lines = _balanced_lines(widths, space, words, TEXT_W, n)
                    if lines:
                        first = fs if first is None else first
                        # up to 16 px of size is worth one bad break avoided
                        score = cost + 0.8 * (n - n0) + 0.06 * (first - fs)
                        if chosen is None or score < chosen[0]:
                            chosen = (score, fs, lines)
        if chosen:
            chosen = chosen[1:]
            break
    if not chosen:                     # pathological: a word wider than the measure
        chosen = (QUOTE_FS_FLOOR, [[i] for i in range(len(words))])
    fs, lines = chosen
    geo = _quote_geometry(fs, len(lines), roman, auth, bool(source))
    top = max(TEXT_TOP, min(center_y - geo["height"] / 2, TEXT_BOTTOM - geo["height"]))
    baselines = [top + geo["asc"] + k * geo["pitch"] for k in range(len(lines))]
    rule_y = baselines[-1] + geo["desc"] + geo["gap_rule"]
    author_base = rule_y + geo["gap_author"] + geo["author_cap"]
    source_base = author_base + geo["gap_source"] + geo["source_x"] if source else author_base
    extra = dict(geo, rule_y=rule_y, author_base=author_base, source_base=source_base,
                 author=author.upper(), source=source)
    return Block(words, emph, fs, lines, baselines, top, top + geo["height"], extra)


def _quote_geometry(fs: int, n_lines: int, roman: Font, auth: Font, has_source: bool) -> dict:
    em = fs * roman.upm / roman.cell
    asc = em * roman.cap_height / roman.upm * 1.12     # caps plus ascender overshoot
    desc = em * 0.24                                   # descenders of the last line
    pitch = em * QUOTE_LEADING
    author_cap = AUTHOR_FS * auth.cap_height / auth.cell
    source_x = SOURCE_FS * roman.x_height / roman.cell
    g = dict(em=em, asc=asc, desc=desc, pitch=pitch, author_cap=author_cap,
             source_x=source_x, gap_rule=em * 0.42, gap_author=em * 0.40,
             gap_source=author_cap * 1.05)
    h = asc + (n_lines - 1) * pitch + desc + g["gap_rule"] + g["gap_author"] + author_cap
    if has_source:
        h += g["gap_source"] + source_x + SOURCE_FS * 0.12
    g["height"] = h
    return g


# ---------------------------------------------------------------------------
# ASS
# ---------------------------------------------------------------------------
def _c(hexrgb: str) -> str:
    """RRGGBB -> an ASS colour override value &HBBGGRR&."""
    h = hexrgb.lstrip("#").upper()
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&"


def _t(sec: float) -> str:
    """Seconds -> ASS H:MM:SS.cc (the same rounding as render._ass_time)."""
    cs = int(round(max(0.0, sec) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def _baseline_pos(f: Font, fs: float, baseline: float) -> int:
    """\\pos y for bottom-centre alignment (\\an2) that puts the baseline at
    `baseline`: libass aligns the bottom of the line box, winDescent below it."""
    return int(round(baseline + fs * f.win_descent / f.cell))


def _dialogue(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{_t(start)},{_t(end)},{style},,0,0,0,,{text}"


def ass_styles() -> list:
    """Style lines for the [V4+ Styles] section (events override most fields)."""
    def style(name, fontname, fs, primary, secondary):
        return (f"Style: {name},{fontname},{fs},{primary},{secondary},&H00000000,"
                f"&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1")
    parch = _c(PARCHMENT)[2:-1]
    return [
        style("TypeHook", HOOK_FONT, HOOK_FS_MAX, "&H00FFFFFF", "&H00FFFFFF"),
        style("TypeQuote", QUOTE_FONT, QUOTE_FS_MAX, f"&H00{parch}", f"&H{UNREAD_ALPHA:02X}{parch}"),
        style("TypeAuthor", AUTHOR_FONT, AUTHOR_FS, f"&H00{_c(GOLD)[2:-1]}", f"&H00{_c(GOLD)[2:-1]}"),
        style("TypeShade", HOOK_FONT, HOOK_FS_MAX, "&H00000000", "&H00000000"),
    ]


SHADES = (
    # (y offset, outline, blur, alpha): a wide soft shadow that lifts the
    # type off any picture, and a tight one that defines the letter edges
    # on bright skies, both soft enough never to read as an outline.
    (10, 0, 24, 0x40),
    (4, 2, 5, 0x60),
)


def _shade_events(layer, start, end, fade, fontname, fs, x, y, text, spacing=0.0, italic=False):
    out = []
    it = "\\i1" if italic else ""
    for dy, bord, blur, alpha in SHADES:
        out.append(_dialogue(layer, start, end, "TypeShade",
                             f"{{\\an2\\pos({x},{y + dy})\\q2\\fn{fontname}\\fs{fs}\\fsp{spacing:g}"
                             f"{it}\\bord{bord}\\shad0\\blur{blur}"
                             f"\\1c&H000000&\\3c&H000000&\\1a&H{alpha:02X}&\\3a&H{alpha:02X}&{fade}}}{text}"))
    return out


# The band: two blurred full-width rectangles, (padding past the text, alpha,
# blur): 22% black reaching 150 px beyond the block, 44% black hugging it.
# Together ~56% at the text and nothing 270 px away, so a white word reads on
# a white sky with no box and no outline.
BAND_LAYERS = ((150, 0xC8, 120), (34, 0x90, 80))
_BAND_W = W + 600                  # drawn from x = -300: its soft ends are off every screen


def _band_shape(h: int) -> str:
    return f"m 0 0 l {_BAND_W} 0 {_BAND_W} {h} 0 {h}{{\\p0}}"


def band_events(top: float, bottom: float, start: float, end: float, fade: str = "") -> list:
    """A soft dark gradient band behind one text block."""
    out = []
    for pad, alpha, blur in BAND_LAYERS:
        y0, h = int(top - pad), int(bottom - top + 2 * pad)
        out.append(_dialogue(0, start, end, "TypeShade",
                             f"{{\\an7\\pos(-300,{y0})\\p1\\bord0\\shad0\\blur{blur}"
                             f"\\1c&H000000&\\1a&H{alpha:02X}&{fade}}}" + _band_shape(h)))
    return out


# How much band a picture needs, from its brightness under the text (mean
# luma 0-255): none on a dark shot (the soft shadows carry the words, and the
# frame keeps its light: the preflight gate fails a frame under 45, and the
# owner has called frames too dark before), the full band on a bright sky.
BAND_LUMA_NONE, BAND_LUMA_FULL = 80, 170


def band_strength(luma) -> float:
    """0..1 band for a shot whose text region has mean luma `luma`; a shot
    that could not be measured gets the full band (legibility first)."""
    if luma is None:
        return 1.0
    return max(0.0, min(1.0, (luma - BAND_LUMA_NONE) / (BAND_LUMA_FULL - BAND_LUMA_NONE)))


def picture_luma(path, at: float = 0.5):
    """Mean luma (0-255) of the region the text sits on (the phone-visible
    width, TEXT_TOP..TEXT_BOTTOM) in one frame of a clip, or None."""
    import proc
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"crop={CROP_R - CROP_L}:{TEXT_BOTTOM - TEXT_TOP}:{CROP_L}:{TEXT_TOP},"
          "scale=42:54,format=gray")
    try:
        r = proc.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, at):.2f}", "-i", str(path),
                      "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-"],
                     capture_output=True, timeout=60)
        data = r.stdout or b""
    except Exception:  # noqa: BLE001
        return None
    return sum(data) / len(data) if len(data) == 42 * 54 else None


def bands(hook_block, hook_span, quote_block, quote_span, plan=None) -> list:
    """The band behind the hook and then the quote. With both, it is ONE band
    that moves and reshapes from the hook's extent to the quote's while one
    hands over to the other (\\move + \\t on its height), so the picture never
    brightens for a beat between them. hook_span = (start, end, fade_in_ms),
    quote_span = (start, end). `plan` = [(start, end, strength)] per shot
    (band_strength of its picture): each shot gets the band it needs, and a
    change of strength lands on a cut, where the picture changes anyway."""
    if not (hook_block or quote_block):
        return []
    start = hook_span[0] if hook_block else quote_span[0]
    end = quote_span[1] if quote_block else hook_span[1]
    out = []
    for s0, s1, k in (plan or [(start, end, 1.0)]):
        a, b = max(s0, start), min(s1, end)
        if b - a >= 0.01 and k > 0.02:
            out += _band_piece(hook_block, hook_span, quote_block, quote_span, a, b, k)
    return out


def _band_piece(hook_block, hook_span, quote_block, quote_span, a, b, k) -> list:
    def geo(block, pad):
        return int(block.top - pad), int(block.bottom - block.top + 2 * pad)
    fade_in = hook_span[2] if hook_block else 220
    first = abs(a - (hook_span[0] if hook_block else quote_span[0])) < 0.005
    fade = f"\\fad({fade_in if first else 0},{320 if (hook_block and not quote_block and abs(b - hook_span[1]) < 0.005) else 0})"
    out = []
    for pad, alpha, blur in BAND_LAYERS:
        a_k = 255 - int(round((255 - alpha) * k))
        head = f"\\p1\\bord0\\shad0\\blur{blur}\\1c&H000000&\\1a&H{a_k:02X}&{fade}"
        if hook_block and quote_block:
            (y_h, hh), (y_q, hq) = geo(hook_block, pad), geo(quote_block, pad)
            r1 = int(round((hook_span[1] - 0.32 - a) * 1000))
            r2 = max(r1 + 120, int(round((quote_span[0] + 0.22 - a) * 1000)))
            if r2 <= 0:                       # the quote's band
                tags = f"\\an7\\pos(-300,{y_q})"
                h = hq
            elif r1 >= (b - a) * 1000:        # the hook's band
                tags = f"\\an7\\pos(-300,{y_h})"
                h = hh
            else:                             # reshaping during this shot
                tags = (f"\\an7\\move(-300,{y_h},-300,{y_q},{r1},{r2})"
                        f"\\t({r1},{r2},\\fscy{100 * hq / hh:.2f})")
                h = hh
        else:
            y, h = geo(hook_block or quote_block, pad)
            tags = f"\\an7\\pos(-300,{y})"
        out.append(_dialogue(0, a, b, "TypeShade", "{" + tags + head + "}" + _band_shape(h)))
    return out


def hook_events(block: Block, word_starts: list, start: float, end: float,
                fade_in_ms: int = 0, fade_out_ms: int = 320) -> list:
    """The hook, one event per line at its own baseline, fully drawn from
    `start` (frame 0 for edits: no dimmed words, no fade-in). With word
    starts, each word turns gold as the voice reaches it and settles back
    when the next one begins; emphasis words are gold throughout."""
    f = font(HOOK_FONT)
    follow = bool(word_starts) and len(word_starts) == len(block.words)
    fade = f"\\fad({fade_in_ms},{fade_out_ms})"
    gold, white = _c(GOLD), _c(WHITE)
    out = []
    for k, line in enumerate(block.lines):
        y = _baseline_pos(f, block.fs, block.baselines[k])
        parts, plain = [], []
        for i in line:
            w = _esc(block.words[i])
            base = gold if block.emph[i] else white
            tag = f"\\1c{base}"
            if follow and base == white:
                a = int(round((word_starts[i] - start) * 1000))
                tag += f"\\t({a},{a + 60},\\1c{gold})"
                if i + 1 < len(word_starts):
                    b = int(round((word_starts[i + 1] - start) * 1000))
                    tag += f"\\t({b},{b + 120},\\1c{white})"
            parts.append(f"{{{tag}}}{w}")
            plain.append(w)
        out += _shade_events(1, start, end, fade, HOOK_FONT, block.fs, 540, y, " ".join(plain))
        out.append(_dialogue(2, start, end, "TypeHook",
                             f"{{\\an2\\pos(540,{y})\\q2\\fn{HOOK_FONT}\\fs{block.fs}\\bord0\\shad0{fade}}}"
                             + " ".join(parts)))
    return out


def quote_events(block: Block, times: list, start: float, end: float,
                 fade_in_ms: int = 220) -> list:
    """The quote, its gold rule, author and source. With per-word `times`
    ((start, end) of each word, from the narration) the words fill as they
    are spoken: unread ones at 75%, spoken ones full; without, all full.
    Emphasis words are set in gold italic (their punctuation stays roman)."""
    roman = font(QUOTE_FONT)
    karaoke = bool(times) and len(times) == len(block.words)
    fade = f"\\fad({fade_in_ms},0)"
    gold, parch = _c(GOLD), _c(PARCHMENT)
    out = []
    for k, line in enumerate(block.lines):
        y = _baseline_pos(roman, block.fs, block.baselines[k])
        parts, plain = [], []
        if karaoke:
            lead = int(round((times[line[0]][0] - start) * 100))
            if lead > 0:
                parts.append(f"{{\\k{lead}}}")
        for n, i in enumerate(line):
            word = block.words[i]
            sep = " " if n < len(line) - 1 else ""
            k_tag = ""
            if karaoke:
                nxt = times[i + 1][0] if i + 1 < len(times) else times[i][1]
                k_tag = f"\\k{max(1, int(round((nxt - times[i][0]) * 100)))}"
            if block.emph[i]:
                lead_p, core, trail = (_esc(p) for p in _split(word))
                parts.append(f"{{{k_tag}}}{lead_p}{{\\i1\\1c{gold}\\2c{gold}}}{core}"
                             f"{{\\i0\\1c{parch}\\2c{parch}}}{trail}{sep}")
                plain.append(f"{lead_p}{{\\i1}}{core}{{\\i0}}{trail}{sep}")
            else:
                parts.append((f"{{{k_tag}}}" if k_tag else "") + _esc(word) + sep)
                plain.append(_esc(word) + sep)
        out += _shade_events(1, start, end, fade, QUOTE_FONT, block.fs, 540, y, "".join(plain))
        unread = "" if karaoke else "\\2a&H00&"
        out.append(_dialogue(2, start, end, "TypeQuote",
                             f"{{\\an2\\pos(540,{y})\\q2\\fn{QUOTE_FONT}\\fs{block.fs}\\bord0\\shad0"
                             f"\\1c{parch}\\2c{parch}{unread}{fade}}}" + "".join(parts)))
    x = block.extra
    # a short gold rule between the words and the name
    out.append(_dialogue(2, start, end, "TypeShade",
                         f"{{\\an5\\pos(540,{int(round(x['rule_y']))})\\p1\\bord0\\shad0\\blur0.6"
                         f"\\1c{gold}\\1a&H20&{fade}}}m 0 0 l 84 0 84 3 0 3{{\\p0}}"))
    auth = font(AUTHOR_FONT)
    ay = _baseline_pos(auth, AUTHOR_FS, x["author_base"])
    name = _esc(x["author"])
    out += _shade_events(1, start, end, fade, AUTHOR_FONT, AUTHOR_FS, 540, ay, name, AUTHOR_SPACING)
    out.append(_dialogue(2, start, end, "TypeAuthor",
                         f"{{\\an2\\pos(540,{ay})\\q2\\fn{AUTHOR_FONT}\\fs{AUTHOR_FS}"
                         f"\\fsp{AUTHOR_SPACING}\\bord0\\shad0\\1c{gold}{fade}}}{name}"))
    if x.get("source"):
        sy = _baseline_pos(roman, SOURCE_FS, x["source_base"])
        src = _esc(x["source"])
        out += _shade_events(1, start, end, fade, QUOTE_FONT, SOURCE_FS, 540, sy, src, italic=True)
        out.append(_dialogue(2, start, end, "TypeQuote",
                             f"{{\\an2\\pos(540,{sy})\\q2\\fn{QUOTE_FONT}\\fs{SOURCE_FS}\\i1"
                             f"\\bord0\\shad0\\1c{parch}\\1a&H40&{fade}}}{src}"))
    return out


def watermark_events(text: str, start: float, end: float) -> list:
    """The channel's handle, small and quiet, centred above YouTube's title
    and clear of the button column, on screen the whole video."""
    if not text:
        return []
    f = font(AUTHOR_FONT)
    y = _baseline_pos(f, MARK_FS, MARK_Y)
    t = _esc(text)
    return [
        _dialogue(3, start, end, "TypeShade",
                  f"{{\\an2\\pos(540,{y + 3})\\q2\\fn{AUTHOR_FONT}\\fs{MARK_FS}\\fsp{MARK_SPACING:g}"
                  f"\\bord1\\shad0\\blur4\\1c&H000000&\\3c&H000000&\\1a&H80&\\3a&H80&}}{t}"),
        _dialogue(3, start, end, "TypeAuthor",
                  f"{{\\an2\\pos(540,{y})\\q2\\fn{AUTHOR_FONT}\\fs{MARK_FS}\\fsp{MARK_SPACING:g}"
                  f"\\bord0\\shad0\\1c&HFFFFFF&\\1a&H{MARK_ALPHA:02X}&}}{t}"),
    ]


def thumbnail_document(hook: str, author: str, emphasis: str = "", caps: bool = True) -> str:
    """A complete .ass file for the thumbnail: frame 0's hook (same face,
    size, breaks, gold), the band behind it, and the author in gold under a
    short rule, for one still frame. Thumbnails are seen at card size, so the
    hook is set as a poster: up to 4 lines, inside the phone crop, bigger."""
    block = layout_hook(hook, emphasis, caps, center_y=860, max_lines=THUMB_MAX_LINES,
                        fs_max=THUMB_FS_MAX, fs_good=THUMB_FS_GOOD, text_w=THUMB_TEXT_W)
    events = band_events(block.top, block.bottom + 150, 0, 10)
    events += hook_events(block, [], 0, 10, 0, 0)
    auth = font(AUTHOR_FONT)
    rule_y = int(round(block.bottom + 70))
    ay = _baseline_pos(auth, AUTHOR_FS, rule_y + 40 + AUTHOR_FS * auth.cap_height / auth.cell)
    events.append(_dialogue(2, 0, 10, "TypeShade",
                            f"{{\\an5\\pos(540,{rule_y})\\p1\\bord0\\shad0\\blur0.6\\1c{_c(GOLD)}"
                            f"\\1a&H20&}}m 0 0 l 84 0 84 3 0 3{{\\p0}}"))
    name = _esc(author.upper())
    events += _shade_events(1, 0, 10, "", AUTHOR_FONT, AUTHOR_FS, 540, ay, name, AUTHOR_SPACING)
    events.append(_dialogue(2, 0, 10, "TypeAuthor",
                            f"{{\\an2\\pos(540,{ay})\\q2\\fn{AUTHOR_FONT}\\fs{AUTHOR_FS}"
                            f"\\fsp{AUTHOR_SPACING}\\bord0\\shad0\\1c{_c(GOLD)}}}{name}"))
    return document(events)


def document(events: list, extra_styles: list = ()) -> str:
    """A whole .ass file around `events` (for the thumbnail and the tests)."""
    return (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n"
            f"WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            + "\n".join([*extra_styles, *ass_styles()])
            + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n" + "\n".join(events) + "\n")
