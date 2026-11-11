"""
The painted picture: REEL_PICTURE=painted (Zeuxis, the crew's painter).

Owner, 2026-11-10, in the HQ: "Deploy agents to design higher quality
videos." The audit of the live edit found black-and-white stock clips with
weak relevance ("gold coins" returned muddy hands), washed out or murky, a
letterboxed clip, and an empty cloud shot at the end; the niche's winners are
full-colour, painterly-cinematic scenes of the Roman world living the line.
This module is everything about that picture except the HTTP call
(imagegen.generate_still): what each shot shows, how it moves, how it's
graded, and that it fills the frame.

OFF unless REEL_PICTURE=painted (REEL_EDIT_LOOK=painted turns it on with the
rest of the new look in scripts/daily_post.py). With it off nothing here runs
and the live edit renders exactly as before (tests/test_painter_render.py).

What a shot is
  * `scenes` on the quote (data/edit_quotes.json, written by the scene
    writer): 6-8 one-line shots, in order, each a concrete subject + action +
    setting + named light, optionally with cast tokens {marcus} {seneca}
    {epictetus} {man}. Every slot is one painted still from them.
  * no scenes: the quote's `visuals` (today's stock keywords) go through a
    template (scene_from_visual) into the classical world: "luxury car"
    becomes a gilded chariot, "man boxing" the recurring young Roman training
    with leather hand-wraps; "still:" lines are already scenes.
  * a scene that fails the free prompt check (src/prompt_lint.py: writing,
    mirrors, anachronisms) or negates a colour falls back to the template,
    then to its theme's scene: a refused prompt costs a picture, never a post.

The look (STYLE, appended by code to every prompt): colour, painterly
cinematic realism in the classical world, a named warm physical light, a rich
but restrained palette, the subject in the middle third of a tall frame,
detail kept in the shadows. Never a negated colour (decisions 2026-08-07: "not
red" renders red); never the words that make image models paint letterbox
bars ("film still", "widescreen").

How it moves: one slow push, pull or drift per shot, varied shot to shot, by
ffmpeg's `perspective` filter evaluated per frame with cubic interpolation, so
the window moves in 1/256-pixel steps. zoompan crops at whole pixels, which is
the judder the owner vetoed on 2026-10-01 ("I dont like the shaking images").
Measured on a rendered clip: see tests/test_painter_render.py.

How it's graded: each still is exposure-normalised on its own (per-channel
exposure solved from its histogram) so every shot lands in the same luminance
band, above doctrine 6's floor ("the frame must be visible"); then one warm
grade for the whole Short, a light bloom, fine grain and a light vignette.

Frame fill: bars baked into a source (a cinematic still painted with black
bands, a stock clip uploaded letterboxed: the live edit of 2026-11-10 showed
one) are found and cropped before the frame is filled, and the finished render
is checked (check_frame_fill); a slot that still shows bars is banned for the
retry, which then fills it from stock.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import proc

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920


def enabled() -> bool:
    """The painted picture is on for this render. Read at call time: the QA
    retry loop changes the environment between attempts."""
    return os.environ.get("REEL_PICTURE", "").strip().lower() == "painted"


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# THE CAST. A scene may name {marcus}, {seneca}, {epictetus} or {man}; each is
# written out to the same look every time, and a hand-written scene that names
# one is painted on that person's fixed seed, so the same face comes back
# across shots and days. {man} is the viewer's stand-in (doctrine 1: one man,
# 18-34, on a self-improvement arc), the recurring young Roman.
# Change a look or a seed only to recast deliberately: every cached still of
# that person changes with it.
# ---------------------------------------------------------------------------
CAST: dict[str, dict] = {
    "man": {
        "label": "a young Roman man",
        "look": ("The young Roman man is in his late twenties, with short dark "
                 "hair, a short dark beard and a strong, calm face, and wears a "
                 "plain undyed wool tunic."),
        "seed": 410170,
    },
    "marcus": {
        "label": "Marcus Aurelius",
        "look": ("Marcus Aurelius is the Roman emperor in his fifties, with curly "
                 "greying hair, a full curly greying beard and deep-set calm "
                 "eyes, and wears a cream wool toga with a purple border."),
        "seed": 410171,
    },
    "seneca": {
        "label": "Seneca",
        "look": ("Seneca is the Roman philosopher in his sixties, balding, with "
                 "short grey hair at the sides, a short grey beard and a lean, "
                 "thoughtful face, and wears a plain cream wool toga."),
        "seed": 410172,
    },
    "epictetus": {
        "label": "Epictetus",
        "look": ("Epictetus is the Greek philosopher in his sixties, thin and "
                 "wiry, with a bald crown and a long grey beard, and wears a "
                 "plain rough brown wool tunic."),
        "seed": 410173,
    },
}
TOKEN = re.compile(r"\{([A-Za-z_]+)\}")
TOKENS = tuple("{" + k + "}" for k in CAST)


def expand_cast(scene: str) -> tuple[str, list[str]]:
    """The scene with each cast token as the person's name ("a young Roman
    man" first, "the young Roman man" after, so "{man}'s hand" still reads),
    then one sentence per person with the fixed look. Returns the text and the
    cast named, in order of first appearance."""
    named: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1).lower()
        if key not in CAST:
            return m.group(0)
        label = CAST[key]["label"]
        if key in named:
            return label.replace("a young", "the young")
        named.append(key)
        at_start = m.start() == 0 or scene[:m.start()].rstrip().endswith((".", ":"))
        return label[0].upper() + label[1:] if at_start else label

    text = TOKEN.sub(sub, scene or "")
    looks = " ".join(CAST[k]["look"] for k in named)
    return (f"{_clean(text)}. {looks}" if looks else text), named


def unknown_tokens(scene: str) -> list[str]:
    return [m.group(0) for m in TOKEN.finditer(scene) if m.group(1).lower() not in CAST]


# ---------------------------------------------------------------------------
# THE LOOK. Appended by code to every scene, so the shelf's scenes carry no
# style words and all eight shots of a Short (and every Short) share one look.
# ---------------------------------------------------------------------------
STYLE = (
    "painterly cinematic realism, like a classical oil painting brought to "
    "life, set in the ancient Greco-Roman world, rich but restrained colour: "
    "warm ochre, terracotta, burnished bronze, deep umber, muted olive and "
    "soft sky blue, {light}, soft atmospheric depth, detail kept in the "
    "shadows, controlled midtones, the subject in the middle third of a tall "
    "vertical frame, a full-bleed composition reaching every edge of the frame"
)
# A named physical source carries its own colour temperature (decisions
# 2026-08-07); a scene that already names its light keeps it as the only one.
DEFAULT_LIGHT = "lit by warm, low golden sunlight"
OWN_LIGHT = "its warm physical light glowing on skin, cloth and stone"
# A shot with nobody in it must not be told about skin, clothing, hands or a
# face: the first real renders (design lab, 2026-11-11) grew a pair of hands
# and a robe out of "rain running down the face of a grey boulder", because the
# prompt's own light and anatomy lines described a person.
OWN_LIGHT_EMPTY = "its warm physical light glowing on stone, wood and water"
PERSON = re.compile(
    r"\{(?:man|marcus|seneca|epictetus)\}|\b(?:man|men|woman|women|boy|girl|figure|person|"
    r"people|crowd|soldiers?|fisherman|friends?|celebrants|guests|emperor|philosopher|"
    r"servants?|slaves?|merchants?|guards?|farmers?|sailors?|child|children|hands?|"
    r"fingers?|fists?|arms?|eyes|shoulders?|feet|sandals|he|his|him|she|her|they|their)\b"
    r"|\bface\b(?! of)", re.I)
LIGHT_WORDS = re.compile(
    r"\b(light|lights|lit|lamp|lamps|torch|torches|torchlight|candle|candles|"
    r"candlelight|fire|firelight|flame|flames|sun|sunlight|sunrise|sunset|dawn|"
    r"dusk|moon|moonlight|glow|glowing|embers|hearth|brazier|lantern)\b", re.I)
# Period, stated as physical things (prompt_lint's lesson: name what IS there).
ERA = ("period-accurate antiquity: stone, marble, plaster, terracotta and "
       "timber, wool and linen clothing, clay and bronze oil lamps")
# The same period for a shot with nobody in it: things, not clothing or hands.
ERA_EMPTY = ("period-accurate antiquity: stone, marble, plaster, terracotta, "
             "timber and bronze")
SAFE_EMPTY = "only the objects and the place described, natural proportions, plain unmarked surfaces"

# "not red" renders red. Any negated colour in a scene or in the style is a bug.
_COLOURS = (r"red|orange|yellow|green|blue|purple|violet|magenta|pink|cyan|teal|"
            r"gold|golden|brown|black|white|grey|gray|colou?rs?|tints?|hues?|"
            r"saturation|saturated|desaturated|monochrome|sepia")
NEGATED_COLOUR = re.compile(
    r"\b(no|not|non|without|never|avoid|avoiding|zero|less|minus)[\s-]+"
    r"(?:\w+[\s-]+){0,2}?(" + _COLOURS + r")\b", re.I)
# Words that ask an image model for letterbox bars or another look entirely.
BAR_WORDS = re.compile(r"\b(film still|movie still|widescreen|anamorphic|"
                       r"letterbox\w*|cinemascope|aspect ratio|frame border|"
                       r"vignette)\b", re.I)
# Style words a scene line should not carry (the code adds the look).
STYLE_WORDS = re.compile(r"\b(cinematic|chiaroscuro|dramatic|moody|black and white|"
                         r"monochrome|high contrast|photorealistic|hyperrealistic|"
                         r"4k|8k|35mm|film grain|black background|dark background)\b",
                         re.I)


def negates_colour(text: str) -> bool:
    return NEGATED_COLOUR.search(text or "") is not None


def has_person(scene: str) -> bool:
    """Is anyone (or any part of anyone) in this shot?"""
    return PERSON.search(scene or "") is not None


def style_for(scene: str) -> str:
    own = OWN_LIGHT if has_person(scene) else OWN_LIGHT_EMPTY
    light = own if LIGHT_WORDS.search(scene or "") else DEFAULT_LIGHT
    return STYLE.format(light=light)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s*,(\s*,)+", ",", text)
    return text.strip(" ,.;")


def strip_style_words(text: str) -> str:
    """A "still:" line from the stock era carries its own style ("dramatic
    side light, black background"): the look is added by code, and a black
    background is exactly the unreadable frame doctrine 6 forbids."""
    out = STYLE_WORDS.sub("", text or "")
    out = BAR_WORDS.sub("", out)
    return _clean(out)


# ---------------------------------------------------------------------------
# THE TEMPLATE: today's stock keywords -> a painted scene in the Roman world.
# ("act", phrase) follows a person ("{man} training as a boxer ..."), ("obj",
# phrase) is a thing in the frame, None = nothing classical to paint (the
# theme's own scene is used instead).
# ---------------------------------------------------------------------------
_CLASSICAL: list[tuple[str, tuple[str, str] | None]] = [
    (r"\b(writ\w*|calendar|sticky notes|chalkboard|notes|price tag|stop sign|"
     r"traffic light|security camera|rubik|disco ball|slot machine|credit card|"
     r"trash can|mouse trap|balloon|binoculars|vinyl|microphone|ceiling fan|"
     r"window blinds|zipper|burnt toast|cucumber|lemon|basketball|skateboard|"
     r"mirror)\b", None),
    (r"\b(box(ing|er)|punching bag)\b",
     ("act", "training as a boxer with leather hand-wraps in a Roman palaestra")),
    (r"\b(weightlift\w*|weight training|gym|push ups|training)\b",
     ("act", "lifting a heavy stone in a Roman palaestra")),
    (r"\b(cold shower|cold water)\b",
     ("act", "pouring cold water over his head at a stone fountain")),
    (r"\b(desk work|working late|office night|office|working)\b",
     ("act", "working late at a wooden table by a clay oil lamp")),
    (r"\b(phone|social media|notifications|screen|scrolling)\b",
     ("obj", "a blank wax tablet and a bronze stylus on a wooden table")),
    (r"\b(alarm clock|clock|watch|metronome|timelapse|time lapse)\b",
     ("obj", "a bronze sundial casting a long shadow across stone")),
    (r"\b(meditat\w*|breathing|eyes closeup|thinking)\b",
     ("act", "sitting still with his eyes closed, breathing slowly")),
    (r"\b(waking up|sleeping|resting)\b",
     ("act", "waking at first light on a simple straw bed")),
    (r"\b(eating alone|cooking|simple meal|bread)\b",
     ("obj", "a simple meal of bread and water on a wooden table")),
    (r"\b(guitar|piano)\b", ("act", "playing a wooden lyre")),
    (r"\b(reading|open book|book|library|old photographs|student)\b",
     ("obj", "rolled papyrus scrolls on a wooden shelf")),
    (r"\b(luxury car|car|traffic|flat tire|windshield|rearview)\b",
     ("obj", "a gilded chariot on a Roman road")),
    (r"\b(mansion)\b", ("obj", "a marble villa with a colonnaded garden")),
    (r"\b(stock market)\b", ("obj", "merchants trading in the Roman forum")),
    (r"\b(airplane|train|airport|subway|suitcase|backpack)\b",
     ("obj", "a horse-drawn travelling cart on a long Roman road")),
    (r"\b(city|skyline|skyscraper|crowd|street|rush hour)\b",
     ("obj", "a busy street of ancient Rome")),
    (r"\b(stadium|finish line|starting line|running track)\b",
     ("obj", "the running track of an ancient stadium")),
    (r"\b(trophy|medal)\b", ("obj", "a golden laurel wreath on a marble plinth")),
    (r"\b(money|coins|wallet|gold watch)\b",
     ("obj", "Roman gold coins spilling across a wooden table")),
    (r"\b(coffee|kettle|whiskey)\b",
     ("obj", "steam rising from a clay cup on a wooden table")),
    (r"\b(chess|dice|domino\w*|puzzle)\b",
     ("obj", "a Roman board game with glass counters on a stone table")),
    (r"\b(handshake|signing contract|old telephone|mentor)\b",
     ("obj", "two Roman men clasping forearms in greeting")),
    (r"\b(fireworks)\b", ("obj", "sparks rising from a great bonfire at night")),
    (r"\b(galaxy|night sky)\b", ("obj", "the Milky Way above a Greek temple at night")),
    (r"\b(lighthouse)\b", ("obj", "a stone lighthouse with a fire at its top above a stormy sea")),
    (r"\b(sail\w*|fishing boat|ship|shipwreck|rowing)\b",
     ("obj", "a Roman ship with a square sail on a rough sea")),
    (r"\b(chains|broken chain|prison bars)\b",
     ("obj", "broken iron chains on a stone floor")),
    (r"\b(street lamps?)\b", ("obj", "a burning torch on a stone wall at night")),
    (r"\b(sneakers|old boots)\b", ("obj", "worn leather sandals on a dusty road")),
]
_CLASSICAL_RE = [(re.compile(p, re.I), v) for p, v in _CLASSICAL]
CLASSICAL_WORDS = re.compile(
    r"\b(roman|rome|greek|greece|ancient|antiquity|temple|forum|villa|palaestra|"
    r"toga|tunic|marble|amphitheat\w*|colosseum|stoa|legion\w*|centurion|chariot|"
    r"lyre|papyrus|sundial|aqueduct|statue|bust)\b", re.I)
_WEATHER = re.compile(r"^(\w+ing) (rain|snow|fog|storm|wind|forest|field|desert|dark)$")
_ALONG = re.compile(r"^(\w+ing) (beach|road|river|bridge|mountain|hill|stairs)$")

# The theme's own scene: the floor under every refusal. One per theme in
# edits.py's set, each with a named warm light and nothing the prompt check
# refuses.
THEME_SCENES = {
    "discipline": "{man} training alone at dawn in an empty stone courtyard, lit by low golden sunrise",
    "mortality": "a weathered marble tomb beside an ancient Roman road at dusk, lit by the last warm sunlight",
    "control": "{man} standing calm on a sea cliff as waves break below, lit by golden light through storm clouds",
    "ego": "a toppled marble statue lying in tall grass among Roman ruins, lit by warm afternoon sun",
    "resilience": "{man} walking up a steep mountain road into the wind, lit by a break of warm evening light",
    "anger": "{man} sitting still beside a glowing bronze brazier, his jaw set, lit by firelight",
    "desire": "gold coins and silver cups on a table in a quiet Roman villa, lit by a single clay oil lamp",
    "time": "a bronze sundial in a Roman garden at sunset, its long shadow across the stone",
    "fear": "{man} standing at the edge of a dark forest at dusk, holding a burning torch",
    "friendship": "two Roman men sharing bread at a wooden table, lit by warm clay oil lamps",
    "duty": "{man} standing watch on a stone city wall at dawn, lit by low golden sunrise",
    "adversity": "{man} hauling a heavy cart up a muddy hill in the rain, lit by warm light from a farmhouse doorway",
}
DEFAULT_SCENE = "the ruins of a Roman temple on a hill at golden hour, lit by low warm sunlight"


def theme_scene(theme: str) -> str:
    t = (theme or "").lower()
    for k, v in THEME_SCENES.items():
        if k in t:
            return v
    return DEFAULT_SCENE


def scene_from_visual(visual: str, theme: str = "") -> str:
    """One of today's stock keywords as a painted scene in the classical world."""
    v = _clean(visual)
    if not v:
        return theme_scene(theme)
    if v.lower().startswith("still:"):
        return strip_style_words(v[6:]) or theme_scene(theme)
    low = v.lower()
    m = re.match(r"^(old man|men|man)\b\s*(.*)$", low)
    person = {"old man": "an old Roman man", "men": "two Roman men", "man": "{man}"}[m.group(1)] if m else ""
    rest = (m.group(2) if m else low).strip()
    hit = next(((rx, val) for rx, val in _CLASSICAL_RE if rx.search(rest or low)), None)
    if hit and hit[1] is None:
        return theme_scene(theme)
    if hit:
        kind, phrase = hit[1]
        if kind == "act":
            scene = f"{person or '{man}'} {phrase}"
        else:
            scene = f"{person} beside {phrase}" if person else phrase
    else:
        g = _WEATHER.match(rest) or _ALONG.match(rest)
        if g:
            prep = "through the" if _WEATHER.match(rest) else "along the"
            rest = f"{g.group(1)} {prep} {g.group(2)}"
        scene = f"{person} {rest}".strip() if person else rest
    if not CLASSICAL_WORDS.search(scene) and "{" not in scene:
        scene += ", in the ancient Greco-Roman world"
    elif "{" in scene and not CLASSICAL_WORDS.search(scene):
        scene += ", in ancient Rome"
    return _clean(scene)


# ---------------------------------------------------------------------------
# Scene -> prompt (+ seed), with the free prompt check.
# ---------------------------------------------------------------------------
def scene_problems(scene: str) -> list[tuple[str, str]]:
    """[(level, message)] for one scene line: what refuses it (ERROR) and what
    only weakens it (WARN). For the scene writer's shelf check, and at render."""
    import prompt_lint as lint
    out: list[tuple[str, str]] = []
    if not isinstance(scene, str) or not scene.strip():
        return [("ERROR", "empty scene")]
    for tok in unknown_tokens(scene):
        out.append(("ERROR", f"unknown cast token {tok} (known: {', '.join(TOKENS)})"))
    if negates_colour(scene):
        out.append(("ERROR", "negates a colour (\"not red\" renders red): name a light source instead"))
    if BAR_WORDS.search(scene):
        out.append(("ERROR", "asks for a film frame or bars: image models paint letterbox bands"))
    expanded, _ = expand_cast(scene)
    for level, msg in lint.check_shot({"picture": expanded}):
        out.append((level, msg))
    if STYLE_WORDS.search(scene):
        out.append(("WARN", "style words in a scene line: the look is added by code"))
    if not LIGHT_WORDS.search(scene):
        out.append(("WARN", "no named light: the default warm low sun is used"))
    if len(scene) > 320:
        out.append(("WARN", f"long scene ({len(scene)} chars): one shot, one line"))
    return out


def refused(scene: str) -> str:
    """The first ERROR for this scene, or ""."""
    return next((m for lvl, m in scene_problems(scene) if lvl == "ERROR"), "")


# Objects whose everyday word paints the wrong century. Seen on the first real
# FLUX.2 [klein] renders (design lab, 2026-11-11): "oil lamp" came out twice as
# a glass hurricane lantern on a brass stand, though the style already says
# "clay and bronze oil lamps": the scene's own words outweigh the style's. So
# the scene itself names the Roman object. "lamplight"/"lamplit" are left alone.
LAMP = re.compile(r"\b(?:(?:small|clay|bronze|terracotta) )*(?:oil[- ])?lamp(s)?\b"
                  r"(?:\s+(glow|light|glowing)\b)?", re.I)


def _roman_lamp(m: re.Match) -> str:
    if m.group(2):
        # "oil lamp glow" describes LIGHT: naming the lamp made it the subject
        # (it took the wine cup's place in a close-up, 2026-11-11).
        return "warm lamplight"
    return ("small terracotta Roman oil lamps with open flames" if m.group(1)
            else "small terracotta Roman oil lamp with an open flame")


def period_objects(text: str) -> str:
    """The scene with its lamps written as the Roman objects they are. One
    pass; a scene that already names a Roman oil lamp is left as written."""
    if "roman oil lamp" in (text or "").lower():
        return text or ""
    return LAMP.sub(_roman_lamp, text or "")


def build_prompt(scene: str) -> str:
    """The final prompt: the scene with its cast written out, its objects in
    their period form, the look, the period, and the anatomy/no-lettering
    guard (positive phrasing only)."""
    import prompt_lint as lint
    expanded, _ = expand_cast(scene)
    expanded = _clean(period_objects(expanded))
    if has_person(scene) or has_person(expanded):
        return f"{expanded}. {style_for(expanded)}. {ERA}. {lint.SAFE_POSITIVE}."
    return f"{expanded}. {style_for(expanded)}. {ERA_EMPTY}. {SAFE_EMPTY}."


def seed_for(scene: str, key: str = "", slot: int = 0, handwritten: bool = True) -> int:
    """A hand-written scene naming a cast member uses that person's seed (the
    same face across shots and days). Everything else gets a stable seed from
    the quote, the slot and the text: stable so the rehearsal and the live run
    ask for the same image (and the cache serves it), keyed by quote so the
    same template line ("man walking alone" is on nine quotes) never airs the
    identical picture twice."""
    _, named = expand_cast(scene)
    if handwritten and named:
        return int(CAST[named[0]]["seed"])
    h = hashlib.sha256(f"{key}|{slot}|{scene}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 2_000_000_000


def slot_scene(slot: int, theme: str = "") -> tuple[str, bool, str]:
    """(scene, handwritten, why) for a render slot, from the environment
    daily_post sets: REEL_PAINT_SCENE<i> (a hand-written scene) else the
    template from REEL_BG_FLAVOR<i> (the stock keyword), each checked; the
    theme's scene is the floor."""
    suffix = str(slot) if slot else ""
    own = os.environ.get(f"REEL_PAINT_SCENE{suffix}", "").strip()
    flavor = os.environ.get(f"REEL_BG_FLAVOR{suffix}", "").strip()
    why = ""
    if own:
        bad = refused(own)
        if not bad:
            return own, True, ""
        why = f"scene refused ({bad[:70]}); template instead"
    if flavor:
        t = scene_from_visual(flavor, theme)
        bad = refused(t)
        if not bad:
            return t, False, why
        why = f"{why + '; ' if why else ''}template refused ({bad[:60]}); theme scene"
    return theme_scene(theme), False, why


# ---------------------------------------------------------------------------
# Sources: bars and exposure.
# ---------------------------------------------------------------------------
def _gray(path: Path, width: int, *, seek: float | None = None, frames: int = 1,
          vf_extra: str = "") -> tuple[int, int, list[bytes]]:
    """Grey frames at `width` px (area-averaged), as raw rows of bytes."""
    w, h = probe_size(path)
    if not w or not h:
        return 0, 0, []
    tw = max(16, width)
    th = max(16, int(round(h * tw / w / 2)) * 2)
    cmd = ["ffmpeg", "-v", "error"]
    if seek is not None:
        cmd += ["-ss", f"{seek:.2f}"]
    cmd += ["-i", str(path)]
    vf = f"{vf_extra + ',' if vf_extra else ''}scale={tw}:{th}:flags=area,format=gray"
    cmd += ["-vf", vf, "-frames:v", str(frames), "-f", "rawvideo", "-"]
    raw = proc.run(cmd, capture_output=True, timeout=120).stdout or b""
    size = tw * th
    out = [raw[i * size:(i + 1) * size] for i in range(len(raw) // size)]
    return tw, th, out


def probe_size(path: Path) -> tuple[int, int]:
    """Displayed size (a phone clip stored sideways with a rotation flag is
    decoded upright by ffmpeg, so its width and height swap)."""
    import json as _json
    try:
        out = proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height:stream_tags=rotate:"
                        "stream_side_data=rotation", "-of", "json", str(path)],
                       capture_output=True, text=True).stdout
        st = (_json.loads(out or "{}").get("streams") or [{}])[0]
        w, h = int(st.get("width") or 0), int(st.get("height") or 0)
        rot = st.get("tags", {}).get("rotate")
        for sd in st.get("side_data_list") or []:
            rot = sd.get("rotation", rot)
        if rot is not None and abs(int(float(rot))) % 180 == 90:
            w, h = h, w
        return w, h
    except Exception:  # noqa: BLE001
        return 0, 0


# A bar row: every pixel near black (24/255 is cropdetect's own default) AND
# flat. Flatness is what tells a letterbox from a dark picture: a bar is one
# value edge to edge; a night sky or a shadowed floor next to it has texture.
# (A first version demanded a sharp full-width edge after the bar instead, and
# missed a real bar sitting above a dark floor.)
BAR_MAX = 24
BAR_FLAT = 8


def bar_edges(rows, w: int, h: int, *, limit: int = BAR_MAX, flat: int = BAR_FLAT) -> dict:
    """Thickness in rows/columns of the bars on each side of one grey frame
    (or of a per-pixel MAX over several frames): runs of near-black, flat
    lines from each edge."""
    def row(y):
        return rows[y]

    def col(x):
        return bytes(rows[y][x] for y in range(h))

    def is_bar(line) -> bool:
        hi = max(line)
        return hi <= limit and hi - min(line) <= flat

    def run(get, n):
        k = 0
        while k < n and is_bar(get(k)):
            k += 1
        return 0 if k >= n else k

    return {
        "top": run(row, h),
        "bottom": run(lambda i: row(h - 1 - i), h),
        "left": run(col, w),
        "right": run(lambda i: col(w - 1 - i), w),
    }


PAIR_RATIO = 2.5


def paired(e: dict) -> dict:
    """Keep only bars that come in pairs. A letterbox has a top AND a bottom
    band, a pillarbox a left AND a right, of similar size; a dark band on one
    side only is a dark wall or a night sky (three of the six real FLUX stills
    in samples/frames have one), and cropping it would cut the picture."""
    out = dict(e)
    for a, b in (("top", "bottom"), ("left", "right")):
        lo, hi = sorted((out.get(a, 0), out.get(b, 0)))
        if lo <= 0 or hi > PAIR_RATIO * lo:
            out[a] = out[b] = 0
    return out


def _frame(raw: bytes, w: int, h: int) -> list[bytes]:
    return [raw[y * w:(y + 1) * w] for y in range(h)]


def still_bars(path: Path) -> dict:
    """Bars painted into a generated still, in SOURCE pixels {top,bottom,left,right}."""
    sw, sh = probe_size(path)
    tw, th, frames = _gray(path, 216)
    if not frames:
        return {"top": 0, "bottom": 0, "left": 0, "right": 0}
    e = bar_edges(_frame(frames[0], tw, th), tw, th)
    return _scale_edges(e, tw, th, sw, sh)


def _scale_edges(e: dict, tw: int, th: int, sw: int, sh: int) -> dict:
    """Thumbnail rows -> source pixels, one row of margin past the edge, and
    nothing at all if the 'bars' would take most of the frame (that is a dark
    picture, not a letterbox)."""
    out = {}
    for side, n in e.items():
        if n <= 0:
            out[side] = 0
            continue
        total = th if side in ("top", "bottom") else tw
        src = sh if side in ("top", "bottom") else sw
        out[side] = int(math.ceil((n + 1) * src / total))
    out = paired(out)
    if out["top"] + out["bottom"] > 0.45 * sh:
        out["top"] = out["bottom"] = 0
    if out["left"] + out["right"] > 0.45 * sw:
        out["left"] = out["right"] = 0
    # Under 1.5% is a soft dark edge, not a bar worth losing picture over.
    for side in out:
        lim = sh if side in ("top", "bottom") else sw
        if out[side] < 0.015 * lim:
            out[side] = 0
    return out


def clip_bars(path: Path, samples: int = 5) -> dict:
    """Bars baked into a STOCK clip: rows black in EVERY sampled frame (content
    moves, a letterbox does not), in source pixels. The live edit of
    2026-11-10 ("luxury car" -> a sky clip) carried 22% of black rows: the
    clip was uploaded letterboxed, and cover-scaling a letterboxed frame
    keeps its bars."""
    sw, sh = probe_size(path)
    if not sw or not sh:
        return {"top": 0, "bottom": 0, "left": 0, "right": 0}
    try:
        dur = float(proc.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)], capture_output=True,
                             text=True).stdout.strip() or 0)
    except ValueError:
        dur = 0.0
    tw = 192
    th = max(16, int(round(sh * tw / sw / 2)) * 2)
    peak = bytearray(tw * th)
    got = 0
    for i in range(max(1, samples)):
        t = (dur * (i + 0.5) / samples) if dur > 0 else None
        _, _, fr = _gray(path, tw, seek=t)
        if not fr or len(fr[0]) != tw * th:
            continue
        got += 1
        f = fr[0]
        for j in range(len(peak)):
            if f[j] > peak[j]:
                peak[j] = f[j]
    if not got:
        return {"top": 0, "bottom": 0, "left": 0, "right": 0}
    e = bar_edges(_frame(bytes(peak), tw, th), tw, th, flat=255)
    return _scale_edges(e, tw, th, sw, sh)


def crop_filter(bars: dict, sw: int, sh: int) -> str:
    """ffmpeg crop that removes the bars (even sizes), or ""."""
    if not any(bars.values()) or not sw or not sh:
        return ""
    x, y = bars["left"], bars["top"]
    cw = sw - bars["left"] - bars["right"]
    ch = sh - bars["top"] - bars["bottom"]
    cw -= cw % 2
    ch -= ch % 2
    if cw < sw * 0.5 or ch < sh * 0.5:
        return ""
    return f"crop={cw}:{ch}:{x}:{y}"


# Exposure band. A shot under LOW is lifted to TARGET, one over HIGH is brought
# to HIGH: every shot lands in the same band (consistency), the darkest well
# above doctrine 6's floor. Mean luma in limited-range Y (what preflight and
# signalstats measure): 0.36 of 255 ~ YAVG 92.
TARGET_LUMA = 0.36
LOW_LUMA = 0.33
HIGH_LUMA = 0.56


def _rgb_hist(path: Path, crop: str) -> list[list[int]] | None:
    w, h = probe_size(path)
    if not w:
        return None
    tw = 144
    th = max(16, int(round(h * tw / w)))
    vf = f"{crop + ',' if crop else ''}scale={tw}:{th}:flags=area,format=rgb24"
    raw = proc.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf,
                    "-frames:v", "1", "-f", "rawvideo", "-"],
                   capture_output=True, timeout=120).stdout or b""
    if len(raw) < 3 * 64:
        return None
    hist = [[0] * 256 for _ in range(3)]
    for i in range(0, len(raw) - 2, 3):
        hist[0][raw[i]] += 1
        hist[1][raw[i + 1]] += 1
        hist[2][raw[i + 2]] += 1
    return hist


def _expo_lut(k: float) -> list[int]:
    """Filmic exposure: out = (1 - e^(-k v)) / (1 - e^(-k)). k > 0 brightens
    like a gain with a soft highlight shoulder (shadows keep their depth;
    a gamma lift turned dark stills milky in the first test), k < 0 darkens,
    k = 0 is the identity."""
    import math as _m
    if abs(k) < 1e-4:
        return list(range(256))
    d = 1.0 - _m.exp(-k)
    return [min(255, max(0, int(round(255.0 * (1.0 - _m.exp(-k * v / 255.0)) / d))))
            for v in range(256)]


def mean_luma(hist: list[list[int]], k: float = 0.0) -> float:
    """Mean limited-range luma (0-1 of 255, BT.601) after exposure `k`."""
    lut = _expo_lut(k)
    n = sum(hist[0]) or 1
    r = sum(c * lut[v] for v, c in enumerate(hist[0])) / n
    gg = sum(c * lut[v] for v, c in enumerate(hist[1])) / n
    b = sum(c * lut[v] for v, c in enumerate(hist[2])) / n
    y = 16 + 219 * (0.299 * r + 0.587 * gg + 0.114 * b) / 255.0
    return y / 255.0


MAX_EXPOSURE = 9.0     # ~9x gain in the deepest shadows at most: past that it is noise


def solve_exposure(hist, target: float) -> float:
    """Exposure k that puts the mean luma at `target` (bisection)."""
    lo, hi = -6.0, MAX_EXPOSURE
    for _ in range(30):
        mid = (lo + hi) / 2
        if mean_luma(hist, mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def exposure(path: Path, crop: str = "") -> dict:
    """{luma, k, luma_after}: the still's mean luma and the exposure that
    brings it into the band (k = 0 when it is already there)."""
    hist = _rgb_hist(path, crop)
    if not hist:
        return {"luma": None, "k": 0.0, "luma_after": None}
    m = mean_luma(hist)
    low, high = _f("REEL_PAINT_LOW_LUMA", LOW_LUMA), _f("REEL_PAINT_HIGH_LUMA", HIGH_LUMA)
    target = _f("REEL_PAINT_TARGET_LUMA", TARGET_LUMA)
    k = 0.0
    if m < low:
        k = solve_exposure(hist, target)
    elif m > high:
        k = solve_exposure(hist, high)
    return {"luma": round(m, 4), "k": k, "luma_after": round(mean_luma(hist, k), 4)}


def prepare_still(raw: Path, out_clip: Path, seconds: float = 1.0) -> dict | None:
    """A generated still -> a static 1080x1920 30 fps clip for render.py:
    bars cropped, exposure normalised (filmic curve), cover-scaled with lanczos
    (FLUX.2 [klein] paints 1024x1920, so this is a 5% upscale), encoded near
    lossless. The motion is NOT baked in: render.py moves each shot over its
    own segment, so the whole move is always seen."""
    raw, out_clip = Path(raw), Path(out_clip)
    sw, sh = probe_size(raw)
    if not sw or not sh:
        return None
    bars = still_bars(raw)
    crop = crop_filter(bars, sw, sh)
    ex = exposure(raw, crop)
    k = ex["k"]
    parts = [crop] if crop else []
    if abs(k) > 0.01:
        e = f"255*(1-exp(-{k:.4f}*val/255))/(1-exp(-{k:.4f}))"
        parts.append(f"format=rgb24,lutrgb=r='{e}':g='{e}':b='{e}'")
    parts += [f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos",
              f"crop={W}:{H}", "setsar=1", "format=yuv420p"]
    cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-loop", "1",
           "-i", str(raw), "-t", f"{seconds:.2f}", "-vf", ",".join(parts),
           "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
           "-tune", "stillimage", "-pix_fmt", "yuv420p", str(out_clip)]
    try:
        proc.run(cmd, check=True, capture_output=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        print(f"  [painter] could not prepare {raw.name}: {e}", file=sys.stderr)
        return None
    if not out_clip.exists() or out_clip.stat().st_size < 5_000:
        return None
    return {"clip": out_clip, "bars": bars, "crop": crop, **ex}


# ---------------------------------------------------------------------------
# Painting a render slot.
# ---------------------------------------------------------------------------
# What each slot got, for the run log (and the report): reset per render.
SLOTS: dict[int, dict] = {}
# Slots whose picture showed bars in a finished render: the next attempt in
# this process fills them from stock instead (see check_frame_fill).
BANNED_SLOTS: set[int] = set()
# Clips this process painted (already cleaned of bars): source_crops skips
# them. Painted clips sit at the slot's usual path, so the thumbnail step
# (daily_post reads <video>.bg.mp4) finds slot 0 as before.
PAINTED_CLIPS: set[str] = set()


# The inspector's choice per (prompt, seed): the still that airs and its
# verdict, so prefetch and fetch_slot agree and nothing is judged twice.
_CHOSEN: dict = {}


def _alt_seed(seed, n: int) -> int:
    """The n-th repaint's seed: far from the first, the same every run (so the
    live post repeats the rehearsal's choice from the cache)."""
    return (int(seed or 0) + 7919 * n) % 2_147_483_647


def painted_still(prompt: str, seed, scene: str = "") -> dict | None:
    """imagegen.generate_still, then the inspector (src/inspector.py). A still
    with a clear defect is repainted with a new seed, up to
    REEL_INSPECT_RETRIES (2) times; the first that passes airs, else the one
    with the fewest problems. Inspector spending goes in the day's ledger.
    Returns generate_still's dict plus `seed_used`, `tries`, `inspect`."""
    import imagegen
    import inspector
    memo = (prompt, seed)
    if memo in _CHOSEN:
        return _CHOSEN[memo]
    retries = max(0, int(_f("REEL_INSPECT_RETRIES", 2)))
    best = None
    for n in range(retries + 1):
        s = seed if n == 0 else _alt_seed(seed, n)
        got = imagegen.generate_still(prompt, s)
        if not got:
            break                          # no paint left (budget, failure): keep the best so far
        v = inspector.judge(Path(got["path"]), scene)
        if v.neurons:
            imagegen._ledger_add(imagegen.still_cache_dir(), v.neurons)
        got = dict(got, seed_used=s, tries=n + 1, inspect=v.as_dict())
        if v.ok is not False:
            best = got
            break
        print(f"  [inspector] seed {s}: {'; '.join(v.problems)[:160]}"
              f"{' (repainting)' if n < retries else ''}", flush=True)
        if best is None or len(v.problems) < len(best["inspect"]["problems"]):
            best = got
    _CHOSEN[memo] = best
    return best


def _slot_request(slot: int, theme: str) -> tuple[str, int, str, bool, str]:
    scene, handwritten, why = slot_scene(slot, theme)
    key = os.environ.get("REEL_PAINT_KEY", "").strip()
    prompt = build_prompt(scene)
    seed = seed_for(scene, key, slot, handwritten)
    return scene, seed, prompt, handwritten, why


def prefetch(n_slots: int, theme: str = "") -> None:
    """Ask for every slot's still at once (the requests are independent and
    I/O bound), so a Short's eight stills cost the wall-clock of about two.
    Each is inspected (painted_still); fetch_slot reads the choices."""
    from concurrent.futures import ThreadPoolExecutor
    reqs = []
    for i in range(max(0, n_slots)):
        if i in BANNED_SLOTS:
            continue
        scene, seed, prompt, _, _ = _slot_request(i, theme)
        reqs.append((prompt, seed, scene))
    workers = max(1, int(_f("REEL_PAINT_WORKERS", 4)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda r: painted_still(r[0], r[1], r[2]), reqs))


def fetch_slot(slot: int, out_path: Path, theme: str = "") -> Path | None:
    """The painted clip for one render slot, or None (the caller falls back to
    stock for this slot)."""
    import imagegen
    if slot in BANNED_SLOTS:
        PAINTED_CLIPS.discard(str(out_path))
        print(f"  [painter] slot {slot}: banned after showing bars; stock instead", flush=True)
        return None
    scene, seed, prompt, handwritten, why = _slot_request(slot, theme)
    if why:
        print(f"  [painter] slot {slot}: {why}", flush=True)
    got = painted_still(prompt, seed, scene)
    out_path = Path(out_path)
    PAINTED_CLIPS.discard(str(out_path))
    if not got:
        SLOTS[slot] = {"scene": scene, "ok": False}
        return None
    prep = prepare_still(Path(got["path"]), out_path)
    if not prep:
        SLOTS[slot] = {"scene": scene, "ok": False}
        return None
    PAINTED_CLIPS.add(str(out_path))
    SLOTS[slot] = {"scene": scene, "seed": got.get("seed_used", seed), "handwritten": handwritten, "ok": True,
                   "tries": got.get("tries", 1), "inspect": got.get("inspect"),
                   "model": got.get("model"), "cached": got.get("cached"),
                   "neurons": got.get("neurons", 0), "luma": prep["luma"],
                   "exposure": prep["k"], "luma_after": prep["luma_after"],
                   "crop": prep["crop"]}
    verdict = got.get("inspect") or {}
    looked = ("passed" if verdict.get("ok") else "kept the best of " + str(got.get("tries", 1))
              if verdict.get("ok") is False else "not looked at")
    print(f"  [painter] slot {slot}: {got.get('model', '?').split('/')[-1]}"
          f"{' (cache)' if got.get('cached') else ''} seed={got.get('seed_used', seed)} "
          f"inspector {looked}{' after ' + str(got.get('tries')) + ' paintings' if got.get('tries', 1) > 1 and verdict.get('ok') else ''} luma "
          f"{(prep['luma'] or 0):.0%}->{(prep['luma_after'] or 0):.0%}"
          f"{' ' + prep['crop'] if prep['crop'] else ''} | {scene[:60]}", flush=True)
    return prep["clip"]


# ---------------------------------------------------------------------------
# MOTION. One move per shot, chosen by position so neighbours differ; the hook
# shot (0) pushes in. The window always stays inside the frame (zoom >= 1),
# moves at constant speed (zooms are exponential, drifts linear) (a cut every ~1.4 s leaves no time for easing; a
# steady move is what reads as a camera), and is sampled sub-pixel.
# ---------------------------------------------------------------------------
MOVES = ["push", "driftr", "pull", "rise", "push", "driftl", "pull", "fall"]


def _amps(slot: int) -> tuple[float, float]:
    zoom = _f("REEL_PAINT_ZOOM", 0.08)
    if slot == 0:
        zoom = _f("REEL_PAINT_HOOK_ZOOM", 0.10)
    drift = _f("REEL_PAINT_DRIFT", 0.05)
    return max(0.0, min(zoom, 0.25)), max(0.0, min(drift, 0.12))


def window(slot: int, i: int, frames: int, w: int = W, h: int = H) -> tuple[float, float, float, float]:
    """The source rectangle (x0, y0, x1, y1) shown at frame i of a shot: the
    Python twin of motion_filter, for tests and the measurement."""
    move = MOVES[slot % len(MOVES)]
    zoom, drift = _amps(slot)
    p = min(i / max(1, frames - 1), 1.0)
    zd = 1.0 / (1.0 - drift - 0.01)
    cx, cy, z = w / 2, h / 2, 1.0
    if move == "push":
        z = (1.0 + zoom) ** p
    elif move == "pull":
        z = (1.0 + zoom) ** (1 - p)
    elif move in ("driftr", "driftl"):
        z = zd
        cx = w / 2 + (1 if move == "driftr" else -1) * drift * w * (p - 0.5)
    else:
        z = zd
        cy = h / 2 + (-1 if move == "rise" else 1) * drift * h * (p - 0.5)
    hw, hh = w / 2 / z, h / 2 / z
    return cx - hw, cy - hh, cx + hw, cy + hh


def motion_filter(slot: int, frames: int) -> str:
    """ffmpeg perspective filter for one shot. sense=source maps the four
    corners of the moving source window onto the output corners; eval=frame
    re-solves it every frame; cubic interpolation samples between pixels."""
    move = MOVES[slot % len(MOVES)]
    zoom, drift = _amps(slot)
    n = max(2, frames)
    # `in` counts from 1 in ffmpeg's perspective filter (measured: a 0-based
    # phase left the last frame of every shot standing still).
    p = f"min(max((in-1)/{n - 1},0),1)"
    zd = 1.0 / (1.0 - drift - 0.01)
    cx, cy, z = "W/2", "H/2", "1"
    # Exponential zoom: the same relative scale change every frame, so every
    # point of the picture moves at a constant speed (a linear zoom slows
    # down by the zoom factor across the shot).
    if move == "push":
        z = f"pow({1 + zoom:.5f},{p})"
    elif move == "pull":
        z = f"pow({1 + zoom:.5f},1-{p})"
    elif move in ("driftr", "driftl"):
        z = f"{zd:.6f}"
        sign = "+" if move == "driftr" else "-"
        cx = f"(W/2{sign}{drift:.5f}*W*({p}-0.5))"
    else:
        z = f"{zd:.6f}"
        sign = "-" if move == "rise" else "+"
        cy = f"(H/2{sign}{drift:.5f}*H*({p}-0.5))"
    hw, hh = f"(W/2/{z})", f"(H/2/{z})"
    x0, x1 = f"{cx}-{hw}", f"{cx}+{hw}"
    y0, y1 = f"{cy}-{hh}", f"{cy}+{hh}"
    interp = "linear" if os.environ.get("REEL_PAINT_INTERP", "").strip() == "linear" else "cubic"
    return (f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':"
            f"x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}':"
            f"interpolation={interp}:sense=source:eval=frame")


# ---------------------------------------------------------------------------
# GRADE. Colour, warm, one grade for every shot (each shot's exposure was
# already brought into the band); shadows lifted, highlights rolled off; a
# light vignette at most; fine grain.
# ---------------------------------------------------------------------------
def grade_parts(lift: float = 0.0, darken: float = 0.0) -> list[str]:
    sat = _f("REEL_PAINT_SAT", 1.08)
    warm = _f("REEL_PAINT_WARM", 0.05)
    sharpen = _f("REEL_PAINT_SHARPEN", 0.35)
    parts = []
    if sharpen > 0:
        parts.append(f"unsharp=5:5:{sharpen:.2f}:5:5:0.0")
    parts += [
        f"eq=brightness={lift - darken:.3f}:saturation={sat:.3f}:contrast=1.0",
        # warm mids and highlights, a touch of cool left in the shadows so the
        # warmth reads as light, not as a tint
        f"colorbalance=rs={-warm * 0.2:.3f}:bs={warm * 0.3:.3f}:"
        f"rm={warm:.3f}:gm={warm * 0.25:.3f}:bm={-warm * 0.8:.3f}:"
        f"rh={warm * 0.6:.3f}:bh={-warm * 0.6:.3f}",
        # filmic: black point lifted (detail in the shadows), soft shoulder
        "curves=master='0/0.035 0.25/0.24 0.5/0.505 0.75/0.77 1/0.975'",
    ]
    return parts


def enhance_graph(src: str, out: str) -> str:
    """Bloom (luma-only screen, like render._enhance_graph, so it never tints),
    fine grain, light vignette."""
    bloom = _f("REEL_PAINT_BLOOM", 0.16)
    grain = int(_f("REEL_PAINT_GRAIN", 3))
    vig = _f("REEL_PAINT_VIGNETTE", 0.30)   # angle in radians; PI/5 is ffmpeg's default
    tail = []
    if grain > 0:
        tail.append(f"noise=alls={grain}:allf=t")
    if vig > 0:
        tail.append(f"vignette=angle={vig:.3f}")
    tail_s = ("," + ",".join(tail)) if tail else ""
    if bloom <= 0:
        return f"[{src}]null{tail_s}[{out}]"
    return (f"[{src}]split[pbase][pglow];"
            f"[pglow]gblur=sigma=18,eq=brightness=0.02[pglowb];"
            f"[pbase][pglowb]blend=c1_expr=A:c2_expr=A:c0_mode=screen:"
            f"c0_opacity={bloom:.3f}{tail_s}[{out}]")


# ---------------------------------------------------------------------------
# FRAME FILL on the finished render.
# ---------------------------------------------------------------------------
def check_frame_fill(video: Path, seg_bounds: list[float] | None = None,
                     fps: float = 4.0) -> list[dict]:
    """Letterbox or pillarbox bars in a finished render: [{t, side, px, slot}].
    A side counts when flat near-black rows (or columns) run from that edge
    for at least 2% of the frame in two consecutive samples. The painted grade
    lifts every black (detail in the shadows), so only a band with no picture
    in it at all stays this flat and this dark."""
    tw, th = 270, 480
    try:
        raw = proc.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                        f"fps={fps},scale={tw}:{th}:flags=area,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=300).stdout or b""
    except Exception as e:  # noqa: BLE001
        print(f"  [painter] frame-fill check skipped: {e}", file=sys.stderr)
        return []
    size = tw * th
    frames = [raw[i * size:(i + 1) * size] for i in range(len(raw) // size)]
    min_rows, min_cols = int(0.02 * th), int(0.02 * tw)
    hits: list[dict] = []
    prev: dict = {}
    for k, f in enumerate(frames):
        e = bar_edges(_frame(f, tw, th), tw, th, limit=32, flat=10)
        e = paired({side: (n if n >= (min_rows if side in ("top", "bottom") else min_cols) else 0)
                    for side, n in e.items()})
        t = k / fps
        cur = {}
        for side, n in e.items():
            if n > 0:
                cur[side] = n
                if side in prev:
                    scale = H / th if side in ("top", "bottom") else W / tw
                    slot = None
                    if seg_bounds:
                        slot = next((i for i, (a, b) in enumerate(zip(seg_bounds, seg_bounds[1:]))
                                     if a <= t < b), len(seg_bounds) - 2)
                    hits.append({"t": round(t, 2), "side": side,
                                 "px": int(n * scale), "slot": slot})
        prev = cur
    return hits


def source_crops(clips) -> list[str]:
    """Per render input: "crop=W:H:X:Y," that removes bars baked into a stock
    clip (a painted clip was already cleaned in prepare_still), else ""."""
    out = []
    for i, c in enumerate(clips):
        c = Path(c)
        f = ""
        if str(c) not in PAINTED_CLIPS:
            try:
                sw, sh = probe_size(c)
                f = crop_filter(clip_bars(c), sw, sh)
            except Exception as e:  # noqa: BLE001
                print(f"  [painter] bar check skipped for slot {i}: {e}", file=sys.stderr)
            if f:
                print(f"  [painter] slot {i}: stock clip carries bars -> {f}", flush=True)
        out.append(f"{f}," if f else "")
    return out


def frame_fill_failures(video: Path, bounds: list[float]) -> list[dict]:
    """check_frame_fill for render.py: bans the offending slots for the retry
    (they are filled from stock next time) and returns the hits. Off with
    REEL_FRAME_CHECK=0."""
    if os.environ.get("REEL_FRAME_CHECK", "1").strip() in ("0", "false", "False"):
        return []
    hits = check_frame_fill(Path(video), bounds)
    if hits:
        slots = {h["slot"] for h in hits if h.get("slot") is not None}
        BANNED_SLOTS.update(slots)
        print(f"  [painter] FRAME FILL: bars in slots {sorted(slots)}: {hits[:3]}", flush=True)
    else:
        print("  [painter] frame fill: no letterbox or pillarbox bars", flush=True)
    return hits
