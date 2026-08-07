"""
Background music selection and download for the daily Short.

Tracks are fetched from the Pixabay music API (royalty-free, no attribution).
Downloaded once per track and cached in assets/music/.  A run never breaks:
every failure falls back gracefully so music is simply omitted on that day.

Analytics-weighted rotation: once a track has ≥5 posts worth of view data,
the track with the highest average views is preferred.  Below that threshold
all tracks rotate equally (LRU) to gather data.
"""
import csv
import os
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"

PIXABAY_MUSIC_URL = "https://pixabay.com/api/music/"

# Three distinct moods to vary the feel across the week.  Queries tuned for
# Stoic/philosophical Shorts — brooding, minimalist, contemplative.
MUSIC_POOL = [
    {"name": "dark_ambient",     "query": "dark ambient cinematic"},
    {"name": "ancient_minimal",  "query": "ancient meditation minimal"},
    {"name": "focus_underscore", "query": "deep focus cinematic underscore"},
]

# Volume for the background music relative to the voice (0.0–1.0).
MUSIC_VOLUME = float(os.environ.get("MUSIC_VOLUME", "0.07"))  # ~-23 dB under voice

MIN_POSTS_FOR_WEIGHT = 5  # require this many posts per track before analytics-weighting


# ---------------------------------------------------------------------------
# Analytics-weighted selection
# ---------------------------------------------------------------------------

def _load_analytics() -> dict[str, int]:
    """Return {video_id: views} from data/analytics.csv using peak views per video."""
    path = ROOT / "data" / "analytics.csv"
    if not path.exists():
        return {}
    peak: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            v = int(row.get("views") or 0)
            if vid and v > peak.get(vid, 0):
                peak[vid] = v
    return peak


def _avg_views(track_name: str, rows: list[dict], analytics: dict[str, int]) -> float | None:
    """Average views for posts that used this track.  Returns None if not enough data."""
    matching = [r for r in rows
                if r.get("music_track") == track_name and r.get("video_id")]
    if len(matching) < MIN_POSTS_FOR_WEIGHT:
        return None
    views = [analytics.get(r["video_id"], 0) for r in matching]
    return sum(views) / len(views)


def pick_music(rows: list[dict]) -> dict:
    """Return a track from MUSIC_POOL using analytics-weighted selection.

    Strategy:
      - If any track lacks ≥5 data posts: rotate LRU (equal exploration).
      - Once all tracks have data: prefer highest avg-views; block most recent
        to avoid repeating the same track two days running.
    """
    if not MUSIC_POOL:
        return MUSIC_POOL[0]

    analytics = _load_analytics()
    avgs = {t["name"]: _avg_views(t["name"], rows, analytics) for t in MUSIC_POOL}

    # Exploration phase: not enough data on at least one track → LRU rotation.
    if any(v is None for v in avgs.values()):
        recent = [r.get("music_track") for r in reversed(rows) if r.get("music_track")]
        block = recent[0] if recent else None
        candidates = [t for t in MUSIC_POOL if t["name"] != block] or MUSIC_POOL
        day = date.today().toordinal()
        return candidates[day % len(candidates)]

    # Exploitation phase: block most recent, pick highest avg views from rest.
    recent = [r.get("music_track") for r in reversed(rows) if r.get("music_track")]
    block = recent[0] if recent else None
    candidates = [t for t in MUSIC_POOL if t["name"] != block] or MUSIC_POOL
    return max(candidates, key=lambda t: avgs.get(t["name"], 0))


# Every cinematic bed, in rotation order. Cinematic mode overrides pick_music()
# for classic posts, so without this the score never changes.
CINEMATIC_SCORES = [
    "cinematic_score", "cinematic_score_d", "cinematic_score_f",
    "cinematic_score_c", "cinematic_score_g",
]


def pick_cinematic_score(rows: list[dict]) -> dict:
    """LRU-rotate the cinematic bed, blocking the last two used.

    Blocking TWO is deliberate: with a 5-bed pool and 3 posts a day, blocking
    only the previous one still lets a bed come back the same afternoon, which
    is exactly the sameness this fixes.
    """
    recent = [r.get("music_track") for r in reversed(rows) if r.get("music_track")]
    block = {t for t in recent[:2] if t}
    candidates = [n for n in CINEMATIC_SCORES if n not in block] or CINEMATIC_SCORES
    return {"name": candidates[date.today().toordinal() % len(candidates)]}


# ---------------------------------------------------------------------------
# Download / cache
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Generative ambient beds (ffmpeg lavfi) — the RELIABLE music source.
# Pixabay has no public music API (that endpoint 404s), so downloads never
# worked. A warm synthesized drone at ~7% under the voice reads identically to a
# stock ambient track, needs no key, no network, and can never fail. One
# distinct filtergraph per mood so the three tracks still feel different.
# ---------------------------------------------------------------------------
_MUSIC_SYNTH = {
    # Each bed also mixes in a whisper of low-passed pink noise ("air") — pure
    # sine stacks read as synthetic; the noise floor makes them feel like a
    # recorded room, closer to real dark-ambient stock tracks.
    # deep, brooding drone: sub + fifth + octave, very slow swell, long reverb
    "dark_ambient": (
        "sine=frequency=55:duration={d},volume=0.9[a0];"
        "sine=frequency=82.5:duration={d},volume=0.5[a1];"
        "sine=frequency=110:duration={d},volume=0.35[a2];"
        "sine=frequency=164.8:duration={d},volume=0.12[a3];"
        "anoisesrc=d={d}:c=pink,lowpass=f=500,volume=0.05[air];"
        "[a0][a1][a2][a3][air]amix=inputs=5:duration=longest,"
        "tremolo=f=0.1:d=0.4,aecho=0.8:0.88:150|280:0.3|0.2,"
        "volume=2.4,alimiter=limit=0.9"
    ),
    # singing-bowl bed: warm fundamental + detuned partner (slow beating) + partials
    "ancient_minimal": (
        "sine=frequency=174:duration={d},volume=0.9[a0];"
        "sine=frequency=175.3:duration={d},volume=0.6[a1];"
        "sine=frequency=348:duration={d},volume=0.4[a2];"
        "sine=frequency=470:duration={d},volume=0.16[a3];"
        "anoisesrc=d={d}:c=pink,lowpass=f=800,volume=0.04[air];"
        "[a0][a1][a2][a3][air]amix=inputs=5:duration=longest,"
        "aecho=0.8:0.9:200|360:0.35|0.25,volume=2.2,alimiter=limit=0.9"
    ),
    # CINEMATIC SCORE — a dark, deep, building film bed (Zimmer register): a
    # sub-bass foundation + a slowly beating minor drone for unease + a bare
    # fifth for scale + a filtered-noise "air", swelled slowly and thrown into a
    # big reverb. Sits under the voice like a feature-film underscore.
    #
    # FIVE KEYS, not one. Cinematic mode is on for every classic post, and it
    # used to hardcode ONE bed — so 30 of the last 30 posts shipped with a
    # byte-identical score. The 3-track pool below was dead code in practice and
    # the channel sounded like one long video. Same identity, different root:
    # E1 / D1 / F1 / C1 / G1, each with its own beat rate and reverb so the ear
    # hears a different cue, not a transpose.
    "cinematic_score": (           # E — the original, keeps history comparable
        "sine=frequency=41:duration={d},volume=0.95[sub];"
        "sine=frequency=82:duration={d},volume=0.5[m1];"
        "sine=frequency=82.7:duration={d},volume=0.42[m2];"
        "sine=frequency=98:duration={d},volume=0.3[minor];"
        "sine=frequency=123:duration={d},volume=0.2[fifth];"
        "sine=frequency=164:duration={d},volume=0.1[oct];"
        "anoisesrc=d={d}:c=pink,lowpass=f=340,volume=0.06[air];"
        "[sub][m1][m2][minor][fifth][oct][air]amix=inputs=7:duration=longest,"
        "tremolo=f=0.1:d=0.4,aecho=0.85:0.9:260|430:0.35|0.25,"
        "volume=2.7,alimiter=limit=0.92"
    ),
    "cinematic_score_d": (         # D — a whole tone lower, heavier, slower beat
        "sine=frequency=36.7:duration={d},volume=0.95[sub];"
        "sine=frequency=73.4:duration={d},volume=0.5[m1];"
        "sine=frequency=74.1:duration={d},volume=0.42[m2];"
        "sine=frequency=87.3:duration={d},volume=0.3[minor];"
        "sine=frequency=110:duration={d},volume=0.2[fifth];"
        "sine=frequency=146.8:duration={d},volume=0.1[oct];"
        "anoisesrc=d={d}:c=pink,lowpass=f=300,volume=0.07[air];"
        "[sub][m1][m2][minor][fifth][oct][air]amix=inputs=7:duration=longest,"
        # ffmpeg's tremolo rejects f < 0.1, so the "slower" feel comes from a
        # deeper sweep and a longer echo rather than a lower rate.
        "tremolo=f=0.1:d=0.55,aecho=0.85:0.9:300|470:0.38|0.28,"
        "volume=2.7,alimiter=limit=0.92"
    ),
    "cinematic_score_f": (         # F — brighter, tighter reverb, more urgent
        "sine=frequency=43.7:duration={d},volume=0.92[sub];"
        "sine=frequency=87.3:duration={d},volume=0.5[m1];"
        "sine=frequency=88.1:duration={d},volume=0.42[m2];"
        "sine=frequency=103.8:duration={d},volume=0.3[minor];"
        "sine=frequency=131:duration={d},volume=0.22[fifth];"
        "sine=frequency=174.6:duration={d},volume=0.11[oct];"
        "anoisesrc=d={d}:c=pink,lowpass=f=380,volume=0.06[air];"
        "[sub][m1][m2][minor][fifth][oct][air]amix=inputs=7:duration=longest,"
        "tremolo=f=0.13:d=0.35,aecho=0.8:0.88:220|380:0.32|0.22,"
        "volume=2.7,alimiter=limit=0.92"
    ),
    "cinematic_score_c": (         # C — the deepest, most funereal; memento mori
        "sine=frequency=32.7:duration={d},volume=1.0[sub];"
        "sine=frequency=65.4:duration={d},volume=0.5[m1];"
        "sine=frequency=66:duration={d},volume=0.42[m2];"
        "sine=frequency=77.8:duration={d},volume=0.3[minor];"
        "sine=frequency=98:duration={d},volume=0.2[fifth];"
        "sine=frequency=130.8:duration={d},volume=0.1[oct];"
        "anoisesrc=d={d}:c=pink,lowpass=f=280,volume=0.07[air];"
        "[sub][m1][m2][minor][fifth][oct][air]amix=inputs=7:duration=longest,"
        "tremolo=f=0.1:d=0.62,aecho=0.88:0.92:340|520:0.40|0.30,"
        "volume=2.7,alimiter=limit=0.92"
    ),
    "cinematic_score_g": (         # G — most open/hopeful of the set
        "sine=frequency=49:duration={d},volume=0.9[sub];"
        "sine=frequency=98:duration={d},volume=0.5[m1];"
        "sine=frequency=98.8:duration={d},volume=0.42[m2];"
        "sine=frequency=116.5:duration={d},volume=0.3[minor];"
        "sine=frequency=147:duration={d},volume=0.2[fifth];"
        "sine=frequency=196:duration={d},volume=0.1[oct];"
        "anoisesrc=d={d}:c=pink,lowpass=f=400,volume=0.055[air];"
        "[sub][m1][m2][minor][fifth][oct][air]amix=inputs=7:duration=longest,"
        "tremolo=f=0.11:d=0.38,aecho=0.82:0.9:240|400:0.34|0.24,"
        "volume=2.7,alimiter=limit=0.92"
    ),
    # soft pad with a gentle pulse: low pad + fifth + high pad, slow tremolo
    "focus_underscore": (
        "sine=frequency=65:duration={d},volume=0.7[a0];"
        "sine=frequency=98:duration={d},volume=0.4[a1];"
        "sine=frequency=196:duration={d},volume=0.2[a2];"
        "anoisesrc=d={d}:c=pink,lowpass=f=600,volume=0.045[air];"
        "[a0][a1][a2][air]amix=inputs=4:duration=longest,"
        "tremolo=f=0.5:d=0.4,aecho=0.8:0.85:110|190:0.25|0.18,"
        "volume=2.4,alimiter=limit=0.9"
    ),
}


# ---------------------------------------------------------------------------
# Generated AMBIENCE beds — diegetic soundscapes that match each style pack's
# visual world (rain under city-night b-roll, wind under sunrise training...).
# Pure ffmpeg synthesis: no network, no key, never fails the pipeline.
# ---------------------------------------------------------------------------
_AMBIENCE_SYNTH = {
    # rain on a window: hissy pink noise, dulled highs, slow swell + far rumble
    "rain_night": (
        "anoisesrc=d={d}:c=pink,lowpass=f=1400,highpass=f=250,"
        "tremolo=f=0.1:d=0.25,volume=0.5[rain];"
        "sine=frequency=48:duration={d},volume=0.12[rumble];"
        "[rain][rumble]amix=inputs=2:duration=longest,volume=1.6,alimiter=limit=0.9"
    ),
    # distant city at night: deep hum + soft filtered wash
    "city_hum": (
        "anoisesrc=d={d}:c=pink,lowpass=f=420,tremolo=f=0.1:d=0.3,volume=0.45[wash];"
        "sine=frequency=55:duration={d},volume=0.16[hum];"
        "[wash][hum]amix=inputs=2:duration=longest,volume=1.7,alimiter=limit=0.9"
    ),
    # dawn wind: banded noise breathing slowly
    "wind_dawn": (
        "anoisesrc=d={d}:c=pink,bandpass=f=600:w=500,"
        "tremolo=f=0.12:d=0.6,volume=0.55,"
        "aecho=0.7:0.8:300:0.25,volume=1.5,alimiter=limit=0.9"
    ),
    # low fire-warmth bed: dark noise with a faster flutter (ember crackle feel)
    "embers": (
        "anoisesrc=d={d}:c=pink,lowpass=f=500,"
        "tremolo=f=5:d=0.25,volume=0.4[fl];"
        "sine=frequency=60:duration={d},volume=0.1[warm];"
        "[fl][warm]amix=inputs=2:duration=longest,tremolo=f=0.1:d=0.3,"
        "volume=1.6,alimiter=limit=0.9"
    ),
}


def fetch_ambience(name: str, dur: float = 26.0) -> Path | None:
    """Generate (and cache) a diegetic ambience bed. Returns None only if
    ffmpeg itself fails — callers then fall back to the normal music bed."""
    import subprocess
    fc = _AMBIENCE_SYNTH.get(name)
    if not fc:
        return None
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    cached = MUSIC_DIR / f"amb_{name}.mp3"
    if cached.exists() and cached.stat().st_size > 5_000:
        return cached
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-filter_complex", fc.format(d=dur), "-t", f"{dur:.0f}",
             "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k",
             str(cached)],
            check=True, capture_output=True,
        )
        if cached.exists() and cached.stat().st_size > 5_000:
            print(f"[music] synthesized ambience '{name}' → {cached.name}")
            return cached
    except Exception as e:
        print(f"[music] ambience synth failed for '{name}': {e}", file=sys.stderr)
    return None


def _synthesize_music(track: dict, out_path: Path, dur: float = 24.0) -> Path | None:
    """Generate a calm ambient bed with ffmpeg — no network, never needs a key.

    render.py stream-loops the music to fill the Short, so a 24s loop is plenty.
    Returns out_path, or None only if ffmpeg itself fails.
    """
    import subprocess
    name = track.get("name", "dark_ambient")
    fc = _MUSIC_SYNTH.get(name, _MUSIC_SYNTH["dark_ambient"]).format(d=dur)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-filter_complex", fc, "-t", f"{dur:.0f}",
             "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k",
             str(out_path)],
            check=True, capture_output=True,
        )
        if out_path.exists() and out_path.stat().st_size > 5_000:
            print(f"[music] synthesized ambient bed for '{name}' → {out_path.name}")
            return out_path
    except Exception as e:
        print(f"[music] synthesis failed for '{name}': {e}", file=sys.stderr)
    return None


def _try_pixabay(track: dict, cached: Path) -> Path | None:
    """Best-effort Pixabay download. Pixabay has no public music API, so this
    almost always fails — kept only in case a working key/endpoint is provided."""
    api_key = os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.get(
            PIXABAY_MUSIC_URL,
            params={"key": api_key, "q": track["query"], "per_page": 10, "order": "popular"},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return None
        audio_url = hits[0].get("audio", {}).get("url") or hits[0].get("url", "")
        if not audio_url:
            for h in hits:
                for key in ("mp3", "preview_url", "url"):
                    u = h.get(key, "") or h.get("audio", {}).get(key, "")
                    if u and u.endswith(".mp3"):
                        audio_url = u
                        break
                if audio_url:
                    break
        if not audio_url:
            return None
        with requests.get(audio_url, stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with open(cached, "wb") as fh:
                for chunk in dl.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
        if cached.stat().st_size < 5_000:
            cached.unlink(missing_ok=True)
            return None
        print(f"[music] cached {track['name']} → {cached.name}")
        return cached
    except Exception as e:
        print(f"[music] Pixabay unavailable for '{track['name']}': {e}", file=sys.stderr)
        cached.unlink(missing_ok=True)
        return None


def fetch_music(track: dict, out_path: Path) -> Path | None:
    """Return a music file for the Short. Never returns None in practice.

    Order: per-track cache → best-effort Pixabay download → generative ambient
    bed (guaranteed). The generative bed means every Short gets music.
    """
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    cached = MUSIC_DIR / f"{track['name']}.mp3"
    if cached.exists() and cached.stat().st_size > 5_000:
        return cached

    downloaded = _try_pixabay(track, cached)
    if downloaded:
        return downloaded

    # Guaranteed fallback — synthesize a warm ambient bed so music is never missing.
    return _synthesize_music(track, cached)
