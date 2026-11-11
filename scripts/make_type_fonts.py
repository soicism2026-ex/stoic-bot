"""Cut the edit format's v2 fonts (REEL_TYPE=v2, src/edit_type.py).

Developer tool, run by hand, never in CI: the output is committed under
assets/fonts/ttf/ and the bot only reads it. Needs fontTools
(`pip install fonttools`), which the bot itself does not.

    python scripts/make_type_fonts.py            # download, cut, subset, write
    python scripts/make_type_fonts.py --check    # print what is committed

Sources are the Google Fonts releases (SIL Open Font License 1.1). Three of the
four faces ship there only as variable fonts, which libass does not select by
weight reliably, so each is cut to ONE static instance at the weight the
design uses, given one family name libass can find it by, and subset to Latin
(Basic, Latin-1, Extended-A) plus general punctuation: everything an English
Stoic quote needs, at a fraction of the size. None of these families has a
Reserved Font Name, so the cut fonts keep their names (OFL section 3).
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "fonts" / "ttf"
RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

# (source file in google/fonts ofl/, weight, family name, style, italic, output)
FACES = [
    ("anton/Anton-Regular.ttf", None, "Anton", "Regular", False, "Anton-Regular.ttf"),
    ("cormorantgaramond/CormorantGaramond[wght].ttf", 700,
     "Cormorant Garamond Bold", "Regular", False, "CormorantGaramond-Bold.ttf"),
    ("cormorantgaramond/CormorantGaramond-Italic[wght].ttf", 700,
     "Cormorant Garamond Bold", "Italic", True, "CormorantGaramond-BoldItalic.ttf"),
    ("cinzel/Cinzel[wght].ttf", 600, "Cinzel SemiBold", "Regular", False, "Cinzel-SemiBold.ttf"),
]
LICENCES = {"anton/OFL.txt": "OFL-Anton.txt",
            "cormorantgaramond/OFL.txt": "OFL-CormorantGaramond.txt",
            "cinzel/OFL.txt": "OFL-Cinzel.txt"}

# Latin + punctuation an English quote can carry (curly quotes, dashes, ellipsis).
UNICODES = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x180))
            + list(range(0x2010, 0x2028)) + [0x2030, 0x2032, 0x2033, 0x2039, 0x203A,
                                              0x2044, 0x20AC, 0x2122, 0x2212])


def fetch(path: str) -> bytes:
    with urllib.request.urlopen(RAW + urllib.parse.quote(path), timeout=60) as r:
        return r.read()


def cut(src: Path, weight, family: str, style: str, italic: bool, out: Path) -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    f = TTFont(src)
    if "fvar" in f:
        f = instancer.instantiateVariableFont(f, {"wght": float(weight)}, updateFontNames=False)
    for tag in ("STAT", "MVAR", "HVAR", "avar", "cvar", "fvar", "gvar"):
        if tag in f:
            del f[tag]
    name = f["name"]
    full = family if style == "Regular" else f"{family} {style}"
    ps = (family + ("" if style == "Regular" else "-" + style)).replace(" ", "")
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
            name.removeNames(nameID=rec.nameID)
    for plat, enc, lang in ((3, 1, 0x409), (1, 0, 0)):
        name.setName(family, 1, plat, enc, lang)
        name.setName(style, 2, plat, enc, lang)
        name.setName(f"{ps}; cut for the edit format (static, Latin subset)", 3, plat, enc, lang)
        name.setName(full, 4, plat, enc, lang)
        name.setName(ps, 6, plat, enc, lang)
    os2 = f["OS/2"]
    if weight:
        os2.usWeightClass = int(weight)
    os2.fsSelection = (os2.fsSelection & ~(1 | 32 | 64)) | (1 if italic else 64)
    f["head"].macStyle = 2 if italic else 0

    opts = subset.Options()
    opts.layout_features = ["kern", "liga", "clig", "calt", "ccmp", "locl", "mark", "mkmk"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = False                # libass renders these unhinted
    opts.glyph_names = False
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(f)
    f.save(out)


def main() -> int:
    if "--check" in sys.argv:
        for p in sorted(OUT.glob("*.ttf")):
            print(f"{p.name:36s} {p.stat().st_size:>7d} B  sha256 {hashlib.sha256(p.read_bytes()).hexdigest()[:16]}")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for src_path, weight, family, style, italic, out_name in FACES:
            src = Path(tmp) / src_path.replace("/", "__")
            src.write_bytes(fetch(src_path))
            cut(src, weight, family, style, italic, OUT / out_name)
            print("cut", out_name, (OUT / out_name).stat().st_size, "B")
    for src_path, out_name in LICENCES.items():
        (OUT.parent / out_name).write_bytes(fetch(src_path))
        print("licence", out_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
