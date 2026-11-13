#!/usr/bin/env python3
"""Wallpaper packs for Gumroad (owner 2026-11-13: "create some Desktop & Mobile
Wallpaper Packs I can sell on Gumroad as well for the channel").

One PACK at a time = one philosopher x one screen. Each wallpaper is a colour
painting from the channel's painter (FLUX.2 [klein] on Cloudflare via
src/imagegen.py, the Shorts' own look) with one verified quote set over it in
the channel's type (Cormorant Garamond Bold, Cinzel gold).

    python scripts/wallpapers.py render  --pack marcus --size phone   [--out DIR] [--limit 10] [--force]
    python scripts/wallpapers.py package --pack marcus --size phone   [--out DIR]
    python scripts/wallpapers.py publish --pack marcus --size phone   [--out DIR]   # GitHub release `wallpapers`

BUDGET: Cloudflare's free 10,000 neurons a day are shared with the daily
posts, which paint before 20:00 UTC. A phone picture costs ~208 neurons, a
desktop one ~312, so `render` refuses before 20:00 UTC unless --force, and
prints the estimate first. A picture that cannot be painted is SKIPPED, never
swapped for stock. Keys: CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN (never
printed); without them `render` exits 2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FONTS = ROOT / "assets" / "fonts" / "ttf"
QUOTE_FONT = FONTS / "CormorantGaramond-Bold.ttf"
AUTHOR_FONT = FONTS / "Cinzel-SemiBold.ttf"
try:                                   # the channel's own gold, one source of truth
    from edit_type import GOLD as _GOLD
except Exception:                      # noqa: BLE001
    _GOLD = "F3BF4C"
GOLD = tuple(int(_GOLD[i:i + 2], 16) for i in (0, 2, 4))
PARCHMENT = (244, 235, 214)
WATERMARK = "forged.in.stoicism"

YOUTUBE = "https://www.youtube.com/@forged.in.stoicism"
GUMROAD = "https://soicism.gumroad.com/l/cslosv"
REPO = "soicism2026-ex/stoic-bot"
TAG = "wallpapers"

PACKS = {"marcus": "Marcus Aurelius", "seneca": "Seneca", "epictetus": "Epictetus"}
# size -> (final w, h, quote line cap, paint size, label)
SIZES = {
    "phone": {"w": 1170, "h": 2532, "cap": 32, "paint": "1024x1920",
              "label": "Phone", "dims": "1170x2532 (iPhone; fits most phones)"},
    "desktop": {"w": 3840, "h": 2160, "cap": 48, "paint": "1920x1088",
                "label": "Desktop", "dims": "3840x2160 (4K; fits any 16:9 screen)"},
}
GUARD_HOUR_UTC = 20
EXIT_NO_KEYS, EXIT_GUARD = 2, 3


# ----------------------------------------------------------------------------
# quotes
# ----------------------------------------------------------------------------
def load_quotes(pack: str, limit: int = 10, path: Path | None = None) -> list[dict]:
    """The pack's quotes: that author's, shortest first (they fit best), at most `limit`."""
    author = PACKS[pack]
    rows = json.loads((path or ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))
    mine = [q for q in rows if q.get("author") == author and q.get("quote")]
    mine.sort(key=lambda q: (len(q["quote"]), q.get("id", "")))
    return mine[:max(0, limit)]


def scene_for(q: dict) -> tuple[str, bool]:
    """(scene, handwritten): the quote's first painted scene, else its theme's."""
    import painter
    scenes = q.get("scenes") or []
    if scenes and str(scenes[0]).strip():
        return str(scenes[0]).strip(), True
    return painter.theme_scene(q.get("theme", "")), False


def prompt_for(q: dict) -> tuple[str, int]:
    import painter
    scene, hand = scene_for(q)
    return painter.build_prompt(scene), painter.seed_for(scene, key=q.get("id", ""), slot=0, handwritten=hand)


# ----------------------------------------------------------------------------
# text
# ----------------------------------------------------------------------------
def wrap_quote(text: str, cap: int) -> list[str]:
    """Break by sense: the fewest lines of at most `cap` characters, as even as
    possible (no one-word orphan), preferring a break after punctuation."""
    words = text.split()
    if not words:
        return []
    if len(text) <= cap:
        return [text]
    n = math.ceil(len(text) / cap)

    def greedy(width: int) -> list[str]:
        lines, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > width:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        lines.append(cur)
        return lines

    best, best_score = None, None
    for width in range(max(len(max(words, key=len)), math.ceil(len(text) / n)), cap + 1):
        lines = greedy(width)
        if len(lines) > n and best is not None:
            continue
        longest = max(len(x) for x in lines)
        ragged = sum((longest - len(x)) ** 2 for x in lines)
        punct = sum(1 for x in lines[:-1] if x[-1] in ",;:.—-?!")
        score = (len(lines), ragged - 40 * punct)
        if best_score is None or score < best_score:
            best, best_score = lines, score
    return best or greedy(cap)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def fit_quote(text: str, cap: int, box_w: int, box_h: int, max_size: int, min_size: int,
              leading: float = 1.14) -> tuple[list[str], ImageFont.FreeTypeFont, int]:
    """The largest type (then the fewest lines) that sets `text` in the box."""
    caps = [cap] + [c for c in (cap - 6, cap - 12, 22, 18) if 10 < c < cap]
    for size in range(max_size, min_size - 1, -2):
        font = _font(QUOTE_FONT, size)
        for c in caps:
            lines = wrap_quote(text, c)
            if (max(font.getlength(x) for x in lines) <= box_w
                    and len(lines) * size * leading <= box_h):
                return lines, font, size
    font = _font(QUOTE_FONT, min_size)
    return wrap_quote(text, caps[-1]), font, min_size


def tracked(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, track: float = 0.0,
            anchor: str = "l") -> float:
    """Letter-spaced text; `anchor` l/m/r is horizontal. Returns the width."""
    widths = [font.getlength(c) + track for c in text]
    total = sum(widths) - track
    x, y = xy
    if anchor == "m":
        x -= total / 2
    elif anchor == "r":
        x -= total
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=font, fill=fill)
        x += w
    return total


def _band(w: int, h: int, top: int, peak: float, horizontal: bool) -> Image.Image:
    """An 'L' mask: 0 at `top`, easing to peak*255 at the bottom; for the desktop
    also fading from the left edge so the type sits on the darkest corner."""
    g = Image.linear_gradient("L").resize((w, h - top))
    g = g.point(lambda v: int(255 * peak * (v / 255) ** 1.5))
    mask = Image.new("L", (w, h), 0)
    mask.paste(g, (0, top))
    if horizontal:
        hx = Image.linear_gradient("L").transpose(Image.ROTATE_90).resize((w, h))   # left 0 -> right 255
        hx = ImageOps.invert(hx).point(lambda v: int(255 * (0.45 + 0.55 * (v / 255) ** 1.2)))
        mask = ImageChops.multiply(mask, hx)
    return mask


def layout(kind: str) -> dict:
    s = SIZES[kind]
    w, h = s["w"], s["h"]
    if kind == "phone":
        return dict(w=w, h=h, cap=s["cap"], x=96, box_w=w - 192, block_bottom=int(h * 0.895),
                    top_limit=int(h * 0.60), max_size=88, min_size=44, align="m",
                    author_size=46, source_size=32, mark_size=28, mark_xy=(w // 2, h - 118),
                    mark_anchor="m", band_top=int(h * 0.50), band_peak=0.82, side=False, gap=64)
    return dict(w=w, h=h, cap=s["cap"], x=230, box_w=2100, block_bottom=h - 270,
                top_limit=int(h * 0.50), max_size=100, min_size=56, align="l",
                author_size=58, source_size=40, mark_size=36, mark_xy=(w - 130, h - 130),
                mark_anchor="r", band_top=int(h * 0.38), band_peak=0.86, side=True, gap=70)


def compose_text(img: Image.Image, quote: str, author: str, source: str, kind: str) -> Image.Image:
    """The painting with the soft dark band, the quote, the author and the
    watermark. Phone: lower 40%, centred, top clear for the clock. Desktop:
    lower-left."""
    L = layout(kind)
    img = img.convert("RGB")
    assert img.size == (L["w"], L["h"]), f"painting must be {L['w']}x{L['h']}, got {img.size}"
    w, h = img.size
    black = Image.new("RGB", (w, h), (6, 5, 4))
    img = Image.composite(black, img, _band(w, h, L["band_top"], L["band_peak"], L["side"]))

    qa, ar = f"“{quote}”", author.upper()
    above = L["author_size"] * 1.2 + L["source_size"] * 1.5 + L["gap"] + 40
    box_h = L["block_bottom"] - L["top_limit"] - above
    lines, qfont, qsize = fit_quote(qa, L["cap"] + 2, L["box_w"], box_h, L["max_size"], L["min_size"])
    lead = qsize * 1.14
    block_h = len(lines) * lead + above
    y = L["block_bottom"] - block_h

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = w // 2 if L["align"] == "m" else L["x"]
    for ln in lines:
        d.text((cx, y), ln, font=qfont, fill=PARCHMENT + (255,), anchor="ma" if L["align"] == "m" else "la")
        y += lead
    y += L["gap"] * 0.55
    rule_w = 120
    rx0 = cx - rule_w // 2 if L["align"] == "m" else cx
    d.line([(rx0, y), (rx0 + rule_w, y)], fill=GOLD + (255,), width=3)
    y += L["gap"] * 0.45
    afont, sfont = _font(AUTHOR_FONT, L["author_size"]), _font(AUTHOR_FONT, L["source_size"])
    tracked(d, (cx, y), ar, afont, GOLD + (255,), track=L["author_size"] * 0.16, anchor=L["align"])
    y += L["author_size"] * 1.35
    if source:
        tracked(d, (cx, y), source, sfont, PARCHMENT + (190,), track=L["source_size"] * 0.06,
                anchor=L["align"])
    mfont = _font(AUTHOR_FONT, L["mark_size"])
    tracked(d, L["mark_xy"], WATERMARK, mfont, PARCHMENT + (150,), track=L["mark_size"] * 0.12,
            anchor=L["mark_anchor"])

    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(max(4, w // 400))).point(lambda v: int(v * 0.75)))
    out = Image.alpha_composite(img.convert("RGBA"), shadow)
    return Image.alpha_composite(out, layer).convert("RGB")


def source_line(citation: str) -> str:
    """'Meditations 10.16, trans. George Long' -> as given (already verified)."""
    return (citation or "").strip()


# ----------------------------------------------------------------------------
# pictures
# ----------------------------------------------------------------------------
def _upscale(src: Path, w: int, h: int, fit: str = "cover") -> Image.Image:
    """src scaled to w x h (cover = crop to the ratio) with ffmpeg lanczos and a
    light unsharp; Pillow's lanczos when ffmpeg is missing."""
    if fit == "cover":
        vf = f"scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=increase,crop={w}:{h},unsharp=5:5:0.6:5:5:0.0"
    else:   # height-fit, width free
        vf = f"scale=-2:{h}:flags=lanczos,unsharp=5:5:0.6:5:5:0.0"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "o.png"
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, str(out)],
                           check=True, capture_output=True, timeout=120)
            return Image.open(out).convert("RGB").copy()
        except (OSError, subprocess.SubprocessError):
            im = Image.open(src).convert("RGB")
            if fit == "cover":
                return ImageOps.fit(im, (w, h), Image.LANCZOS)
            return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)


def fit_phone(src: Path) -> Image.Image:
    s = SIZES["phone"]
    return _upscale(src, s["w"], s["h"])


def fit_desktop(src: Path) -> Image.Image:
    """Landscape paintings cover the 4K frame; a portrait one is centred over a
    blurred, darkened copy of itself."""
    s = SIZES["desktop"]
    w, h = s["w"], s["h"]
    with Image.open(src) as im:
        aspect = im.width / im.height
    if aspect >= 1.6:
        return _upscale(src, w, h)
    bg = ImageOps.fit(Image.open(src).convert("RGB"), (w // 8, h // 8), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.BICUBIC)
    bg = Image.eval(bg, lambda v: int(v * 0.45))
    fg = _upscale(src, w, h, fit="height")
    bg.paste(fg, ((w - fg.width) // 2, 0))
    return bg


def stand_in_painting(path: Path, w: int, h: int, hue: int = 0) -> Path:
    """A gradient 'painting' (tests and local samples; never shipped)."""
    top, bot = (96 + hue % 60, 118, 150), (210, 150 - hue % 40, 70)
    g = Image.linear_gradient("L").resize((w, h))
    im = Image.merge("RGB", [ImageChops.add(Image.new("L", (w, h), int(t * (1 - 0.5))),
                                           g.point(lambda v, a=t, b=b: int((b - a) * v / 255 * 0.5)))
                             for t, b in zip(top, bot)])
    ImageDraw.Draw(im).ellipse([w * .25, h * .25, w * .75, h * .5], fill=(250, 232, 180))
    im.save(path)
    return path


# ----------------------------------------------------------------------------
# render
# ----------------------------------------------------------------------------
def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def cf_keys_ok() -> bool:
    return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
                and os.environ.get("CLOUDFLARE_API_TOKEN", "").strip())


def neuron_estimate(kind: str, n: int) -> tuple[float, float]:
    """(per picture, total) at the first model of the painter's chain."""
    import imagegen
    w, h = (int(x) for x in SIZES[kind]["paint"].split("x"))
    per = imagegen.neuron_cost(imagegen.paint_models()[0], w, h)
    return per, round(per * n, 1)


def paint_one(prompt: str, seed: int) -> Path | None:
    import imagegen
    res = imagegen.generate_still(prompt, seed)
    return Path(res["path"]) if res and res.get("path") and Path(res["path"]).exists() else None


def pack_dir(out: Path, pack: str, kind: str) -> Path:
    return out / f"{pack}-{kind}"


def render_pack(pack: str, kind: str, out: Path, limit: int = 10, painter_fn=None,
                quotes: list[dict] | None = None) -> list[dict]:
    """Paint and set every quote of the pack; returns the rows written to
    <out>/<pack>-<kind>/rendered.json. `painter_fn(prompt, seed) -> Path|None`."""
    painter_fn = painter_fn or paint_one
    quotes = quotes if quotes is not None else load_quotes(pack, limit)
    d = pack_dir(out, pack, kind)
    d.mkdir(parents=True, exist_ok=True)
    rows, skipped = [], []
    for i, q in enumerate(quotes, 1):
        prompt, seed = prompt_for(q)
        src = painter_fn(prompt, seed)
        if not src:
            skipped.append(q.get("id"))
            print(f"[wallpapers] {q.get('id')}: could not be painted, skipped (no stock swap)", flush=True)
            continue
        base = fit_phone(src) if kind == "phone" else fit_desktop(src)
        img = compose_text(base, q["quote"], q["author"], source_line(q.get("citation", "")), kind)
        name = f"{pack}-{kind}-{len(rows) + 1:02d}-{q.get('id', i)}.png"
        img.save(d / name, optimize=True)
        rows.append({"id": q.get("id"), "file": name, "quote": q["quote"], "author": q["author"],
                     "citation": q.get("citation", ""), "theme": q.get("theme", ""),
                     "width": img.width, "height": img.height})
        print(f"[wallpapers] {name}", flush=True)
    (d / "rendered.json").write_text(json.dumps({"pack": pack, "size": kind, "skipped": skipped,
                                                 "items": rows}, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8")
    return rows


def cmd_render(a) -> int:
    if not cf_keys_ok():
        print("No Cloudflare keys: set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN "
              "(GitHub secrets) to paint. Nothing was painted.", file=sys.stderr)
        return EXIT_NO_KEYS
    now = utcnow()
    if now.hour < GUARD_HOUR_UTC and not a.force:
        print(f"Refusing: it is {now:%H:%M} UTC. The painter shares Cloudflare's free 10,000 "
              f"neurons a day with the daily posts, which paint before {GUARD_HOUR_UTC}:00 UTC. "
              "Run after 20:00 UTC, or pass --force.", file=sys.stderr)
        return EXIT_GUARD
    quotes = load_quotes(a.pack, a.limit)
    if not quotes:
        print(f"No quotes for {a.pack}.", file=sys.stderr)
        return 1
    # the painter reads its size and caps from the environment, before it is imported
    os.environ["REEL_PAINT_SIZE"] = SIZES[a.size]["paint"]
    os.environ["REEL_PAINT_MAX_PER_RUN"] = str(max(len(quotes), 1))
    os.environ.setdefault("REEL_STILL_CACHE", str(ROOT / "data" / "still_cache"))
    per, total = neuron_estimate(a.size, len(quotes))
    print(f"[wallpapers] {len(quotes)} {a.size} pictures x ~{per:.0f} neurons = ~{total:.0f} neurons "
          f"(free day: 10,000; cached pictures cost 0)", flush=True)
    rows = render_pack(a.pack, a.size, Path(a.out), a.limit, quotes=quotes)
    complete = len(rows) >= len(quotes)
    print(f"[wallpapers] {len(rows)}/{len(quotes)} wallpapers set in {pack_dir(Path(a.out), a.pack, a.size)}"
          f" (complete: {str(complete).lower()})")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"complete={'1' if complete else '0'}\n")
    return 0 if rows else 1


# ----------------------------------------------------------------------------
# the queue: one pack a night, after the day's posts have painted (wallpapers.yml)
# ----------------------------------------------------------------------------
QUEUE = ROOT / "data" / "wallpapers_queue.json"


def queue_head(path: Path | None = None) -> dict | None:
    """The next pack to paint, or None. The file is a list of {pack, size, limit?}."""
    path = path or QUEUE
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for it in items:
        if it.get("pack") in PACKS and it.get("size") in SIZES:
            return {"pack": it["pack"], "size": it["size"], "limit": int(it.get("limit", 10))}
    return None


def queue_pop(pack: str, kind: str, path: Path | None = None) -> int:
    """Remove the first {pack, size} entry; returns how many entries remain."""
    path = path or QUEUE
    items = json.loads(path.read_text(encoding="utf-8"))
    for i, it in enumerate(items):
        if it.get("pack") == pack and it.get("size") == kind:
            del items[i]
            break
    path.write_text(json.dumps(items, indent=1) + "\n", encoding="utf-8")
    return len(items)


def cmd_queue(a) -> int:
    head = queue_head()
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if a.pop:
        left = queue_pop(a.pop[0], a.pop[1])
        print(f"[wallpapers] queue: {a.pop[0]} {a.pop[1]} done, {left} left")
        return 0
    if not head:
        print("[wallpapers] queue: empty")
        if gh_out:
            open(gh_out, "a", encoding="utf-8").write("pack=\nsize=\nlimit=\n")
        return 0
    print(f"[wallpapers] queue: next is {head['pack']} {head['size']} ({head['limit']} quotes)")
    if gh_out:
        open(gh_out, "a", encoding="utf-8").write(f"pack={head['pack']}\nsize={head['size']}\nlimit={head['limit']}\n")
    return 0


# ----------------------------------------------------------------------------
# package
# ----------------------------------------------------------------------------
def title(pack: str) -> str:
    return f"Forged in Stoicism: {PACKS[pack]} Wallpaper Pack"


def readme(pack: str, kind: str, items: list[dict]) -> str:
    s = SIZES[kind]
    lines = [title(pack), "=" * len(title(pack)), "",
             f"{len(items)} {s['label'].lower()} wallpapers, {s['dims']}.",
             "Each one is a colour painting with one line from " + PACKS[pack] + ", set in the "
             "channel's type. The text of every quote is checked against its source.", "", "WHAT IS INSIDE", ""]
    for n, it in enumerate(items, 1):
        lines.append(f"{n:>2}. {it['file']}")
        lines.append(f"    \"{it['quote']}\"")
        lines.append(f"    {it['author']}, {it['citation']}")
    lines += ["", "HOW TO USE IT", "",
              ("Phone: save the picture to your photos, then Settings > Wallpaper > Add New "
               "(iPhone) or long-press the home screen > Wallpaper (Android). The top is left "
               "clear for the lock-screen clock.") if kind == "phone" else
              ("Desktop: right-click the picture > Set as desktop background (Windows), or "
               "System Settings > Wallpaper (Mac). The words sit lower-left, away from icons "
               "on most layouts."),
              "", "LICENCE", "", "For your own screens; not for resale or redistribution.",
              "Please do not share the files, upload them, or put them in another pack.", "",
              "MORE", "", f"YouTube: {YOUTUBE}", f"The Stoic Reset, a 30-day guided journal: {GUMROAD}", ""]
    return "\n".join(lines)


def cover(pack: str, kind: str, files: list[Path], dst: Path) -> Path:
    """A contact sheet of the pack, the title in Cinzel gold."""
    n = len(files)
    cols = 5 if kind == "phone" else (3 if n > 4 else 2)
    rows = max(1, math.ceil(n / cols))
    W, pad, head = 1600, 28, 250
    cell_w = (W - pad * (cols + 1)) // cols
    ratio = SIZES[kind]["h"] / SIZES[kind]["w"]
    cell_h = int(cell_w * ratio)
    H = head + rows * (cell_h + pad) + pad
    sheet = Image.new("RGB", (W, H), (14, 12, 10))
    d = ImageDraw.Draw(sheet)
    tf = _font(AUTHOR_FONT, 60)
    tracked(d, (W // 2, 52), PACKS[pack].upper(), tf, GOLD, track=9, anchor="m")
    sub = f"{n} {SIZES[kind]['label'].upper()} WALLPAPERS  ·  FORGED IN STOICISM"
    tracked(d, (W // 2, 140), sub, _font(AUTHOR_FONT, 28), PARCHMENT, track=4, anchor="m")
    d.line([(W // 2 - 60, 205), (W // 2 + 60, 205)], fill=GOLD, width=3)
    for i, f in enumerate(files):
        im = ImageOps.fit(Image.open(f).convert("RGB"), (cell_w, cell_h), Image.LANCZOS)
        r, c = divmod(i, cols)
        x = pad + c * (cell_w + pad)
        y = head + r * (cell_h + pad)
        sheet.paste(im, (x, y))
        d.rectangle([x - 1, y - 1, x + cell_w, y + cell_h], outline=GOLD, width=1)
    sheet.save(dst, quality=92)
    return dst


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package_pack(pack: str, kind: str, out: Path) -> dict:
    """<out>/<pack>-<kind>.zip (+ -cover.jpg, -manifest.json) from what render left."""
    d = pack_dir(out, pack, kind)
    meta_path = d / "rendered.json"
    if not meta_path.exists():
        raise SystemExit(f"nothing rendered at {d}: run `render` first")
    items = json.loads(meta_path.read_text(encoding="utf-8"))["items"]
    if not items:
        raise SystemExit("rendered.json holds no wallpapers")
    shipped, files = [], []
    for it in items:
        png = d / it["file"]
        if kind == "desktop":                # 4K PNGs are ~10 MB each: JPEG 92 keeps the zip small
            jpg = png.with_suffix(".jpg")
            Image.open(png).convert("RGB").save(jpg, quality=92, subsampling=0, optimize=True)
            f = jpg
        else:
            f = png
        files.append(f)
        shipped.append(dict(it, file=f.name, bytes=f.stat().st_size, sha256=sha256(f)))
    text = readme(pack, kind, shipped)
    (d / "README.txt").write_text(text, encoding="utf-8")
    zpath = out / f"{pack}-{kind}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED if kind == "phone" else zipfile.ZIP_STORED) as z:
        z.write(d / "README.txt", "README.txt")
        for f in files:
            z.write(f, f.name)
    cpath = cover(pack, kind, files, out / f"{pack}-{kind}-cover.jpg")
    manifest = {
        "run": os.environ.get("RUN_URL", ""),
        "title": title(pack), "pack": pack, "author": PACKS[pack], "size": kind,
                "dimensions": f"{SIZES[kind]['w']}x{SIZES[kind]['h']}", "count": len(shipped),
                "zip": zpath.name, "zipBytes": zpath.stat().st_size, "zipSha256": sha256(zpath),
                "cover": cpath.name, "licence": "Personal use; no resale or redistribution",
                "made": utcnow().strftime("%Y-%m-%d"), "files": shipped}
    mpath = out / f"{pack}-{kind}-manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[wallpapers] {zpath.name}: {len(shipped)} files, {zpath.stat().st_size / 1e6:.1f} MB")
    return manifest


def cmd_package(a) -> int:
    m = package_pack(a.pack, a.size, Path(a.out))
    if m["zipBytes"] > 60_000_000:
        print(f"warning: the zip is {m['zipBytes'] / 1e6:.0f} MB (over 60 MB)", file=sys.stderr)
    return 0


# ----------------------------------------------------------------------------
# publish (GitHub release `wallpapers`, outside git)
# ----------------------------------------------------------------------------
def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    repo = os.environ.get("GITHUB_REPOSITORY", REPO)
    return subprocess.run(["gh", *args, "--repo", repo], capture_output=True, text=True, check=check)


def publish(pack: str, kind: str, out: Path) -> list[str]:
    """The cover and the manifest go to the public `wallpapers` release (the
    HQ shows them). The zip itself is the product: it stays OFF the public
    release and travels as a workflow artifact, which only the owner, signed
    in to GitHub, can download (wallpapers.yml)."""
    names = [f"{pack}-{kind}-cover.jpg", f"{pack}-{kind}-manifest.json"]
    paths = [out / n for n in names]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"nothing to publish, missing {missing}: run `package` first")
    if _gh("release", "view", TAG, check=False).returncode != 0:
        _gh("release", "create", TAG, "--prerelease", "--title", "Wallpaper packs",
            "--notes", "Covers and manifests of the finished wallpaper packs, for the HQ app. "
                       "The packs themselves are workflow artifacts of wallpapers.yml (private). "
                       "Auto-managed: do not delete.")
    _gh("release", "upload", TAG, *[str(p) for p in paths], "--clobber")   # --clobber = replace same name
    print(f"[wallpapers] published {', '.join(names)} to release {TAG}")
    return names


def cmd_publish(a) -> int:
    publish(a.pack, a.size, Path(a.out))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queue", help="print the next pack to paint (GITHUB_OUTPUT: pack, size, limit)")
    q.add_argument("--pop", nargs=2, metavar=("PACK", "SIZE"), help="remove a finished pack from the queue")
    q.set_defaults(fn=cmd_queue)
    for name, fn in (("render", cmd_render), ("package", cmd_package), ("publish", cmd_publish)):
        p = sub.add_parser(name)
        p.add_argument("--pack", required=True, choices=sorted(PACKS))
        p.add_argument("--size", required=True, choices=sorted(SIZES))
        p.add_argument("--out", default="wallpapers_out")
        if name == "render":
            p.add_argument("--limit", type=int, default=10)
            p.add_argument("--force", action="store_true", help="paint before 20:00 UTC")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
