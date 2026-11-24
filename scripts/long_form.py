"""Long videos: a 5-minute 16:9 video on ONE Stoic theme, every other week.

Owner, 2026-11-24, in the HQ ("Long videos: 5-10 minutes on one Stoic theme"):
"Every other week, 5 minutes (free)". Brian narrates an original script that
walks through 4-6 verified quotes (Marcus Aurelius, Seneca, Epictetus) over
painted scenes in the channel's look, with chapters. No new cost: the free
Cloudflare painting allowance (at night), the ElevenLabs Starter characters
the script fits in, the approved music bed.

    python3 scripts/long_form.py script [--theme anger] [--from FILE]   # write/validate data/long_form/<date>.json
    python3 scripts/long_form.py gate [--date D] [--force]              # prints run=true|false (every other Sunday)
    python3 scripts/long_form.py paint [--limit N] [--force]            # paint the stills (spare allowance only), into the cache
    python3 scripts/long_form.py paint-status [--gh-output]             # unfinished=true while the next long video lacks paintings (wallpapers yield)
    python3 scripts/long_form.py render [--out DIR]                     # voice + stills -> long_form.mp4, thumbnail
    python3 scripts/long_form.py upload [--out DIR]                     # YouTube, PRIVATE until the owner says yes
    python3 scripts/long_form.py approve [--redo]                       # the owner's answer to the preview card

THE FIRST ONE IS A PRIVATE PREVIEW. `upload` is PRIVATE unless
data/long_form/state.json says "public_after_approval": true, which only
`approve` (run when the owner taps "Publish it" on the HQ card) sets. The first
upload also files an HQ ask card (`long-form-preview`) carrying the video's link.

THE WORDS: the narration is original; the quotes are copied verbatim from the
shelf (data/edit_quotes.json, itself checked against data/sources/) and every
script is validated with scripts/validate_quotes.py's checks before it can be
voiced (`validate_script`). The voice costs ElevenLabs characters: `render`
stops plainly when the month's characters cannot cover the script.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

DIR = ROOT / "data" / "long_form"
STATE = DIR / "state.json"
W, H = 1920, 1080
SHOT_SECONDS = 9.0                       # one painting per ~9 s
GAP = 0.55                               # silence between parts (s)
MIN_WORDS, MAX_WORDS, MAX_CHARS = 650, 750, 4500
MIN_QUOTES, MAX_QUOTES = 4, 6
MIN_SCENES = 30
MUSIC_VOLUME = 0.10                      # a low bed under the voice
ANCHOR = dt.date(2026, 11, 29)           # the first long-video Sunday; then every 14 days
THEMES = ["anger", "discipline", "letting go", "fear", "time", "control", "resilience", "ego"]
CARD_RED = "EF3B2D"
PARCHMENT = "F4EAD8"
GOLD = "F3BF4C"
PAINT_SIZE = "1920x1088"                 # the model's multiple-of-16 landscape (scripts/wallpapers.py desktop)


# ------------------------------------------------------------------ the calendar
def serves_sunday(day: dt.date) -> dt.date:
    """The Sunday a run on `day` is for: Friday and Saturday (night painting) and
    Sunday itself all serve that weekend's Sunday."""
    return day + dt.timedelta(days=(6 - day.weekday()) % 7)


def is_long_week(day: dt.date) -> bool:
    """Every other Sunday, from ANCHOR."""
    sun = serves_sunday(day)
    return ((sun - ANCHOR).days // 7) % 2 == 0 and (sun - ANCHOR).days >= 0


# ------------------------------------------------------------------ state
def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"public_after_approval": False, "first_preview_sent": False, "uploaded": []}


def save_state(st: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def privacy(st: dict | None = None) -> str:
    """PRIVATE until the owner has approved a long video."""
    return "public" if (st if st is not None else load_state()).get("public_after_approval") else "private"


# ------------------------------------------------------------------ the script
def spoken_parts(script: dict) -> list[str]:
    return [(p.get("text") if p.get("kind") == "narration" else p.get("quote", "")) for p in script["parts"]]


def spoken_text(script: dict) -> str:
    return " ".join(spoken_parts(script))


def quotes_of(script: dict) -> list[dict]:
    return [p for p in script["parts"] if p.get("kind") == "quote"]


def validate_script(script: dict) -> list[str]:
    """Everything that must hold before a script is voiced. [] = good."""
    import validate_quotes as vq
    import shelf
    out: list[str] = []
    text = spoken_text(script)
    words, chars = len(text.split()), len(text)
    if not MIN_WORDS <= words <= MAX_WORDS:
        out.append(f"narration is {words} words (need {MIN_WORDS}-{MAX_WORDS})")
    if chars > MAX_CHARS:
        out.append(f"narration is {chars} characters (limit {MAX_CHARS}: the ElevenLabs Starter budget)")
    qs = quotes_of(script)
    if not MIN_QUOTES <= len(qs) <= MAX_QUOTES:
        out.append(f"{len(qs)} quotes (need {MIN_QUOTES}-{MAX_QUOTES})")
    for p in qs:
        r = vq.check(p.get("quote", ""), p.get("author", ""))
        if r != "ok":
            out.append(f"quote not verbatim in its source ({r}): {p.get('quote', '')[:60]}")
        c = vq.check_citation(p.get("quote", ""), p.get("author", ""), p.get("citation", ""))
        if c.startswith("WRONG") or not p.get("citation"):
            out.append(f"citation {p.get('citation')!r}: {c}")
        for k in (p.get("key") or "").split("|"):
            if k and k.lower() not in p.get("quote", "").lower():
                out.append(f"key words {k!r} are not in the quote")
    chapters = [p for p in script["parts"] if p.get("chapter")]
    if len(chapters) < 3 or not script["parts"] or not script["parts"][0].get("chapter"):
        out.append("chapters: need 3 or more, the first on the opening part (YouTube needs 0:00)")
    if len(script.get("title", "")) > 90 or not script.get("title"):
        out.append("title: 1-90 characters")
    scenes = script.get("scenes") or []
    if len(scenes) < MIN_SCENES:
        out.append(f"{len(scenes)} scenes (need at least {MIN_SCENES}: one per ~{SHOT_SECONDS:.0f} s)")
    for s in scenes:
        for pr in shelf.scene_problems({"scenes": [s]}):
            if "shots, got" not in pr:
                out.append(f"scene {s[:40]!r}: {pr}")
    return out


def write_script(script: dict, day: dt.date | None = None) -> Path:
    problems = validate_script(script)
    if problems:
        raise ValueError("script rejected:\n  " + "\n  ".join(problems))
    DIR.mkdir(parents=True, exist_ok=True)
    p = DIR / f"{script.get('date') or (day or dt.date.today()).isoformat()}.json"
    p.write_text(json.dumps(script, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def shelf_quotes(theme: str, limit: int = 12) -> list[dict]:
    """Verified shelf quotes on a theme (data/edit_quotes.json), the three authors only."""
    try:
        shelf_data = json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    ok = ("Marcus Aurelius", "Seneca", "Epictetus")
    return [q for q in shelf_data if q.get("theme") == theme and q.get("author") in ok][:limit]


def next_theme(done: list[str] | None = None) -> str:
    done = done if done is not None else [s.get("theme") for s in (load_state().get("scripts") or [])]
    for t in THEMES:
        if t not in done:
            return t
    return THEMES[0]


def generate_script(theme: str, day: dt.date, chat=None) -> dict:
    """The crew writes the next script from the quote shelf (an LLM call, then validate)."""
    import llm
    chat = chat or llm.chat
    qs = shelf_quotes(theme)
    if len(qs) < MIN_QUOTES:
        raise ValueError(f"the shelf has only {len(qs)} {theme} quotes")
    doctrine = (ROOT / "data" / "doctrine.md").read_text(encoding="utf-8")[:6000]
    system = ("You write a 5-minute YouTube video script for a Stoicism channel. The narrator speaks to ONE man "
              "(18-34, self-improvement, feels behind). Calm, direct, concrete, never insulting. Reply with JSON only.")
    user = (f"Theme: {theme}.\nDoctrine:\n{doctrine}\n\nQuote shelf (choose 4-6 of these; I copy them in myself, "
            "give only their ids): " + json.dumps([{"id": q["id"], "quote": q["quote"], "author": q["author"]} for q in qs])
            + f"\n\nReturn JSON: {{\"title\": ..., \"lead\": ..., \"tags\": [...], \"thumbnail_text\": ..., "
              f"\"parts\": [{{\"kind\":\"narration\",\"text\":..., \"chapter\": optional title}} or "
              f"{{\"kind\":\"quote\",\"id\":<shelf id>,\"key\":\"1-3 key words from the quote, pipe separated\"}}], "
              f"\"scenes\": [{MIN_SCENES + 6} shots, each ONE paintable picture in ancient Rome with a named light "
              f"source, using {{man}} {{marcus}} {{seneca}} {{epictetus}} for people, no negations, no style words]}}. "
              f"Original narration of {MIN_WORDS + 30}-{MAX_WORDS - 30} words in total including the quotes, "
              f"under {MAX_CHARS - 300} characters, the first part opens a chapter, 4-6 chapters.")
    raw = chat(system, user, 6000, feature="longform")
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    by_id = {q["id"]: q for q in qs}
    parts = []
    for p in data["parts"]:
        if p.get("kind") == "quote":
            q = by_id[p["id"]]
            parts.append({"kind": "quote", "quote": q["quote"], "author": q["author"],
                          "citation": q["citation"], "key": p.get("key", "")})
        else:
            parts.append({k: p[k] for k in ("kind", "text", "chapter") if k in p})
    return {"date": day.isoformat(), "theme": theme, "title": data["title"], "lead": data.get("lead", ""),
            "tags": data.get("tags", []), "thumbnail": {"text": data.get("thumbnail_text", theme.upper()),
                                                        "scene": data["scenes"][0]},
            "parts": parts, "scenes": data["scenes"]}


def current_script_path() -> Path | None:
    """The oldest script not yet uploaded."""
    done = {u.get("date") for u in load_state().get("uploaded", [])}
    for p in sorted(DIR.glob("2*.json")):
        if p.stem not in done:
            return p
    return None


# ------------------------------------------------------------------ the voice
def voice_check(script: dict, remaining: int | None) -> tuple[bool, str]:
    """Can the month's ElevenLabs characters cover this script? Plainly no when unknown."""
    need = len(spoken_text(script)) + 200
    if remaining is None:
        return False, "cannot read the ElevenLabs balance; not spending on the voice"
    if remaining < need:
        return False, f"ElevenLabs has {remaining} characters left this month, the script needs about {need}: stopping"
    return True, f"ElevenLabs budget ok ({remaining} characters left, need about {need})"


def narrate(script: dict, work: Path, synth=None) -> dict:
    """Voice every part (one request each), join them with a short gap.
    Returns {audio, starts: [start of each part], ends, duration}."""
    import tts
    import proc
    synth = synth or (lambda text, out: tts._synthesize_elevenlabs(text, out, tts._EL_VOICE_ID))
    work.mkdir(parents=True, exist_ok=True)
    files, durs = [], []
    for i, text in enumerate(spoken_parts(script)):
        f = work / f"voice_{i:02d}.mp3"
        synth(text, f)
        files.append(f)
        durs.append(tts._audio_duration(f))
    starts, t = [], 0.0
    for d in durs:
        starts.append(round(t, 3))
        t += d + GAP
    ins, fl = [], []
    for i, f in enumerate(files):
        ins += ["-i", str(f)]
        fl.append(f"[{i}:a]aresample=44100,apad=pad_dur={GAP}[a{i}]")
    graph = ";".join(fl) + ";" + "".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[out]"
    out = work / "narration.m4a"
    proc.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, "-map", "[out]",
              "-c:a", "aac", "-b:a", "192k", str(out)], check=True, capture_output=True, timeout=600)
    return {"audio": out, "starts": starts, "ends": [round(s + d, 3) for s, d in zip(starts, durs)], "duration": round(t, 3)}


def chapters_from(script: dict, starts: list[float]) -> list[tuple[float, str]]:
    return [(starts[i], p["chapter"]) for i, p in enumerate(script["parts"]) if p.get("chapter")]


def stamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def description(script: dict, chapters: list[tuple[float, str]]) -> str:
    import promo
    lines = [f"{stamp(t)} {title}" for t, title in chapters]
    quotes = "\n".join(f"- {q['author']}, {q['citation']}" for q in quotes_of(script))
    return (f"{script.get('lead', '')}\n\nChapters\n" + "\n".join(lines)
            + f"\n\nWords quoted in this video\n{quotes}\n" + promo.description_block()
            + "\n\n#Stoicism #MarcusAurelius #Seneca #Epictetus")


# ------------------------------------------------------------------ the pictures
def shot_plan(duration: float) -> list[float]:
    n = max(1, round(duration / SHOT_SECONDS))
    return [duration / n] * n


def scene_for(script: dict, i: int) -> str:
    sc = script["scenes"]
    return sc[i % len(sc)]


def paint_shots(script: dict, n: int, limit: int | None = None, painter_fn=None) -> list[Path | None]:
    """The painted still for each of n shots (None where the allowance ran out;
    the caller reuses a neighbour)."""
    import painter
    os.environ.setdefault("REEL_PAINT_SIZE", PAINT_SIZE)
    painter_fn = painter_fn or (lambda prompt, seed, scene: painter.painted_still(prompt, seed, scene))
    out: list[Path | None] = []
    spent = 0                                  # paintings made now (a cache hit is free)
    for i in range(n):
        if limit is not None and spent >= limit:
            out.append(None)                   # tonight's share is done; the next night continues
            continue
        scene = scene_for(script, i)
        prompt = painter.build_prompt(scene)
        seed = painter.seed_for(scene, "longform:" + script.get("date", ""), i, True)
        got = painter_fn(prompt, seed, scene)
        if got and not got.get("cached"):
            spent += 1
        out.append(Path(got["path"]) if got and got.get("path") else None)
    return out


def shot_count(script: dict) -> int:
    """How many paintings the narration needs (one per ~9 s at 2.4 words a second)."""
    return max(1, round((len(spoken_text(script).split()) / 2.4) / SHOT_SECONDS))


def cached_still(prompt: str, seed) -> Path | None:
    """The painting already in the still cache for this prompt and seed (any model
    of the chain), or None. Never paints, never spends a neuron."""
    import imagegen
    os.environ.setdefault("REEL_PAINT_SIZE", PAINT_SIZE)
    cache = imagegen.still_cache_dir()
    if not cache:
        return None
    for model in imagegen.paint_models():
        w, h = imagegen.paint_size(model)
        hit = imagegen._cache_lookup(cache, imagegen.still_key(model, prompt, seed, w, h))
        if hit:
            return hit
    return None


def _cached_only(prompt: str, seed, scene: str) -> dict | None:
    hit = cached_still(prompt, seed)
    return {"path": str(hit), "cached": True} if hit else None


def unpainted(script: dict) -> tuple[int, int]:
    """(scenes with no painting in the cache yet, scenes the video needs)."""
    import painter
    n = shot_count(script)
    missing = 0
    for i in range(n):
        scene = scene_for(script, i)
        seed = painter.seed_for(scene, "longform:" + script.get("date", ""), i, True)
        if not cached_still(painter.build_prompt(scene), seed):
            missing += 1
    return missing, n


def paint_unfinished(today: dt.date | None = None) -> tuple[bool, str]:
    """Is the next due long video still short of paintings? Wallpapers yield to it
    (a long video needs ~37 scenes, ~7,700 neurons: more than one night's spare).
    True when a script is waiting with unpainted scenes, or, Monday to Saturday of
    a long-video week, when its script is still to be written (it is written
    tonight, then painted)."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    path = current_script_path()
    if path:
        try:
            script = json.loads(path.read_text(encoding="utf-8"))
            missing, n = unpainted(script)
        except Exception as e:  # noqa: BLE001
            return False, f"long video script unreadable ({e}): not yielding"
        if missing:
            return True, f"the long video {path.stem} still has {missing} of {n} scenes unpainted"
        return False, f"the long video {path.stem} has all {n} scenes painted"
    if is_long_week(today) and today.weekday() != 6:
        return True, "a long video is due this week and its script is not written yet"
    return False, "no long video is waiting for paintings"


def fill_gaps(stills: list[Path | None]) -> list[Path]:
    """A shot with no painting reuses the nearest painted one (never a failure)."""
    have = [i for i, s in enumerate(stills) if s]
    if not have:
        raise RuntimeError("no painted stills at all: the free painting allowance is used up; try tomorrow night")
    return [stills[min(have, key=lambda j: abs(j - i))] for i in range(len(stills))]


# ------------------------------------------------------------------ the picture graph
def quote_card(part: dict, out: Path) -> Path:
    """The quote set in the v2 type for a 16:9 frame: serif, key words in red, a gold author line."""
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    fonts = ROOT / "assets" / "fonts" / "ttf"
    regular = ImageFont.truetype(str(fonts / "CormorantGaramond-Bold.ttf"), 76)
    italic = ImageFont.truetype(str(fonts / "CormorantGaramond-BoldItalic.ttf"), 76)
    author = ImageFont.truetype(str(fonts / "Cinzel-SemiBold.ttf"), 34)
    keys = [k.strip().lower() for k in (part.get("key") or "").split("|") if k.strip()]
    quote = part["quote"]
    red = [False] * len(quote)
    for k in keys:
        s = quote.lower().find(k)
        if s >= 0:
            for j in range(s, s + len(k)):
                red[j] = True
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 250, W, H - 250], fill=(8, 6, 4, 150))
    lines = textwrap.wrap(quote, width=38)
    lh = 92
    y = H // 2 - (len(lines) * lh) // 2 - 30
    pos = 0
    for line in lines:
        # the line's characters keep their index into `quote` so the red mask lines up
        start = quote.index(line, pos)
        pos = start + len(line)
        width = sum(d.textlength(c, font=italic if red[start + k] else regular) for k, c in enumerate(line))
        x = (W - width) / 2
        for k, c in enumerate(line):
            f = italic if red[start + k] else regular
            d.text((x, y), c, font=f, fill="#" + (CARD_RED if red[start + k] else PARCHMENT))
            x += d.textlength(c, font=f)
        y += lh
    tag = f"{part['author'].upper()}  ·  {part['citation'].split(',')[0].upper()}"
    tw = d.textlength(tag, font=author)
    d.text(((W - tw) / 2, y + 24), tag, font=author, fill="#" + GOLD)
    img.save(out)
    return out


def video_graph(n_shots: int, shot_dur: list[float], cards: list[tuple[float, float]]) -> str:
    """The filter graph: n looped stills (inputs 0..n-1) each with its own camera move, joined, graded
    and bloomed, then the quote cards (inputs n..) faded over their spoken ranges -> [vout]."""
    import painter
    seg = []
    for i in range(n_shots):
        frames = max(2, round(shot_dur[i] * 30))
        seg.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
                   f"setsar=1,fps=30,trim=0:end={shot_dur[i]:.3f},setpts=PTS-STARTPTS,"
                   f"{painter.motion_filter(i, frames)}[s{i}]")
    seg.append("".join(f"[s{i}]" for i in range(n_shots)) + f"concat=n={n_shots}:v=1[raw]")
    seg.append(f"[raw]{','.join(painter.grade_parts(0.0, 0.0))}[graded]")
    seg.append(painter.enhance_graph("graded", "enh"))
    last = "enh"
    for k, (a, b) in enumerate(cards):
        idx = n_shots + k
        seg.append(f"[{idx}:v]format=rgba,fade=t=in:st=0:d=0.5:alpha=1,fade=t=out:st={max(0.0, b - a - 0.5):.2f}:d=0.5:alpha=1,"
                   f"setpts=PTS+{a:.3f}/TB[c{k}]")
        seg.append(f"[{last}][c{k}]overlay=enable='between(t,{a:.3f},{b:.3f})':eof_action=pass[o{k}]")
        last = f"o{k}"
    seg.append(f"[{last}]format=yuv420p[vout]")
    return ";".join(seg)


def thumbnail(script: dict, still: Path, out: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance
    img = Image.open(still).convert("RGB")
    img = ImageEnhance.Brightness(img.resize((1280, 720))).enhance(0.8)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(ROOT / "assets" / "fonts" / "ttf" / "Anton-Regular.ttf"), 150)
    text = script.get("thumbnail", {}).get("text") or script["title"].split(":")[0]
    words = text.upper().split()
    mid = (len(words) + 1) // 2
    lines = [" ".join(words[:mid]), " ".join(words[mid:])] if len(words) > 1 else [text.upper()]
    y = 720 - 60 - 160 * len(lines)
    for line in lines:
        d.text((60, y), line, font=f, fill="#" + PARCHMENT, stroke_width=8, stroke_fill="black")
        y += 160
    img.save(out, quality=88)
    return out


# ------------------------------------------------------------------ render / upload
def cmd_render(a) -> int:
    import proc
    import tts
    import master
    import imagegen
    path = current_script_path()
    if not path:
        print("long-form: no script waiting (run `script` first)")
        return 1
    script = json.loads(path.read_text(encoding="utf-8"))
    bad = validate_script(script)
    if bad:
        print("long-form: the script is invalid:\n  " + "\n  ".join(bad))
        return 1
    ok, why = voice_check(script, tts._el_credits_remaining() if tts._EL_KEY else None)
    print(f"long-form: {why}")
    if not ok:
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    voice = narrate(script, out)
    shots = shot_plan(voice["duration"] + 1.5)
    # The Sunday render NEVER paints in the day (the allowance belongs to the Shorts): only
    # what the nights cached; a scene still unpainted gets the nearest painted picture.
    got = paint_shots(script, len(shots), painter_fn=_cached_only)
    lacking = sum(1 for g in got if not g)
    if lacking:
        print(f"long-form: {lacking} of {len(got)} scenes fell back to a neighbouring painting "
              "(not in the cache; the render does not paint)")
    stills = fill_gaps(got)
    cards = []
    inputs = []
    for i, s in enumerate(stills):
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{shots[i]:.3f}", "-i", str(s)]
    for i, p in enumerate(script["parts"]):
        if p.get("kind") == "quote":
            png = quote_card(p, out / f"card_{i:02d}.png")
            a0, b0 = voice["starts"][i], voice["ends"][i] + 0.4
            cards.append((a0, b0))
            inputs += ["-loop", "1", "-framerate", "30", "-t", f"{b0 - a0 + 0.1:.3f}", "-i", str(png)]
    audio_in = len(stills) + len(cards)
    music = _music(out, voice["duration"])
    inputs += ["-i", str(voice["audio"])]
    a_graph = f"[{audio_in}:a]aresample=44100[v]"
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        a_graph += (f";[{audio_in + 1}:a]aresample=44100,volume={MUSIC_VOLUME},atrim=0:{voice['duration']:.2f}[m];"
                    f"[v][m]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        a_graph += ";[v]anull[aout]"
    video = out / "long_form.mp4"
    graph = video_graph(len(stills), shots, cards) + ";" + a_graph
    proc.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
              "-t", f"{voice['duration']:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(video)],
             check=True, capture_output=True, timeout=3000)
    print("long-form: mastering to -14 LUFS:", master.master(video))
    thumbnail(script, stills[0], out / "thumbnail.jpg")
    chs = chapters_from(script, voice["starts"])
    (out / "meta.json").write_text(json.dumps({
        "script": path.name, "title": script["title"], "tags": script.get("tags", []),
        "description": description(script, chs), "chapters": [[t, c] for t, c in chs],
        "duration": voice["duration"]}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"long-form: rendered {video} ({voice['duration'] / 60:.1f} min, {len(stills)} shots)")
    return 0


def preview_card(title: str, url: str) -> dict:
    """The HQ ask card for the first long video (answer: publish | redo)."""
    return {"kind": "idea", "title": "First long video: publish it?",
            "pitch": f"The first long video is up as a PRIVATE preview: {url}",
            "question": f"Watch it, then tell me: publish \"{title}\" and keep the next ones public, or change it first?",
            "why": "Nothing goes public until you say so.", "crew": "review", "order": 0,
            "needsYou": True, "cost": "Free", "impact": "high",
            "options": [{"id": "publish", "label": "Publish it", "hint": "makes this video public; later ones go public by themselves"},
                        {"id": "redo", "label": "Change it first", "hint": "tell me what to change in the HQ"}]}


def file_preview_card(title: str, url: str) -> None:
    import hq_outbox
    hq_outbox.append({"ask": "long-form-preview", "create": preview_card(title, url)})


def cmd_upload(a) -> int:
    import publish
    out = Path(a.out)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    video = out / "long_form.mp4"
    st = load_state()
    mode = privacy(st)
    res = publish.publish_longform(video, meta["title"], meta["description"], meta["tags"], privacy=mode)
    thumb = out / "thumbnail.jpg"
    if thumb.exists():
        publish.set_thumbnail(res["video_id"], thumb)
    date = Path(meta["script"]).stem
    st.setdefault("uploaded", []).append({"date": date, "video_id": res["video_id"], "privacy": mode})
    st.setdefault("scripts", []).append({"date": date, "theme": json.loads((DIR / meta["script"]).read_text())["theme"]})
    if not st.get("first_preview_sent") and mode == "private":
        file_preview_card(meta["title"], res["url"])
        st["first_preview_sent"] = True
    save_state(st)
    print(f"long-form: uploaded {mode}: {res['url']}")
    return 0


def cmd_approve(a) -> int:
    st = load_state()
    st["public_after_approval"] = not a.redo
    save_state(st)
    print(f"long-form: public_after_approval = {st['public_after_approval']}")
    return 0


def _music(work: Path, seconds: float) -> Path | None:
    try:
        import csv
        import edit_music
        rows = list(csv.DictReader(open(ROOT / "data" / "posts.csv", encoding="utf-8")))
        t = edit_music.pick(rows, dt.date.today().isoformat())
        return edit_music.fetch(t, work / "music.m4a", seconds + 5) if t else None
    except Exception as e:  # noqa: BLE001
        print(f"long-form: no music bed ({e})")
        return None


def cmd_script(a) -> int:
    day = dt.date.today()
    if a.if_needed and current_script_path():
        print(f"long-form: a script is already waiting ({current_script_path().name})")
        return 0
    if a.src:
        script = json.loads(Path(a.src).read_text(encoding="utf-8"))
    else:
        script = generate_script(a.theme or next_theme(), day)
    p = write_script(script, day)
    print(f"long-form: wrote {p.relative_to(ROOT)} ({len(spoken_text(script).split())} words)")
    return 0


def cmd_gate(a) -> int:
    day = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(dt.timezone.utc).date()
    go = bool(a.force) or is_long_week(day)
    print(f"run={'true' if go else 'false'}")
    return 0


def cmd_paint(a) -> int:
    if not a.force:
        import spare_paint
        ok, why = spare_paint.check()
        if not ok:
            print(f"long-form: not painting now: {why}")
            return 0
    path = current_script_path()
    if not path:
        print("long-form: no script waiting")
        return 0
    script = json.loads(path.read_text(encoding="utf-8"))
    missing, n = unpainted(script)
    if not missing:
        print(f"long-form: all {n} scenes of {path.stem} are painted (cached); nothing to paint")
        return 0
    got = paint_shots(script, n, limit=a.limit)
    left, _ = unpainted(script)
    print(f"long-form: {sum(1 for g in got if g)}/{n} stills painted or cached; {left} left for the next night")
    return 0


def cmd_paint_status(a) -> int:
    """For wallpapers: does the next long video still need the free allowance?"""
    busy, why = paint_unfinished()
    print(f"long-form: {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if a.gh_output and out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"unfinished={'true' if busy else 'false'}\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("script"); s.add_argument("--theme"); s.add_argument("--from", dest="src")
    s.add_argument("--if-needed", action="store_true", help="only when no script is waiting")
    g = sub.add_parser("gate"); g.add_argument("--date"); g.add_argument("--force", action="store_true")
    p = sub.add_parser("paint"); p.add_argument("--limit", type=int); p.add_argument("--force", action="store_true")
    ps = sub.add_parser("paint-status"); ps.add_argument("--gh-output", action="store_true")
    for name in ("render", "upload"):
        r = sub.add_parser(name); r.add_argument("--out", default=str(ROOT / "data" / "long_form" / "out"))
    ap_ = sub.add_parser("approve"); ap_.add_argument("--redo", action="store_true")
    ns = ap.parse_args(argv)
    return {"script": cmd_script, "gate": cmd_gate, "paint": cmd_paint, "paint-status": cmd_paint_status, "render": cmd_render,
            "upload": cmd_upload, "approve": cmd_approve}[ns.cmd](ns)


if __name__ == "__main__":
    sys.exit(main())
