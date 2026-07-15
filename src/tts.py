"""
Text-to-speech via edge-tts (Microsoft Neural — free, no API key required).

edge-tts uses the same engine as Azure Cognitive Services Neural TTS but at
zero cost through the Edge browser TTS endpoint.  No account, no key, no rate
limits at our posting frequency.

edge-tts depends on an undocumented Microsoft endpoint that can refuse cloud
IPs (e.g. GitHub Actions), so gTTS (Google Translate TTS — free, no key) is a
hard fallback: if edge-tts fails for any reason we still ship a real voiceover
rather than a silent Short.

ElevenLabs is retained as an optional upgrade: set ELEVENLABS_API_KEY +
ELEVENLABS_VOICE_ID to override the free engine on any run.

synthesize_voice() returns (audio_path, word_timings) where word_timings is a
list of (word, start_seconds, end_seconds). The timings drive the karaoke
captions in render.py.

Voice pool — three deep Microsoft Neural voices tuned for the Stoic niche:
  Guy         — deep, dominant American; closest to high-view Stoic Shorts style
  Ryan        — deep British, measured and philosophical
  Christopher — authoritative American, confident narrator register
Rotates analytics-weighted once each voice has ≥5 posts of view data; uses LRU
equal rotation before that.
"""
import asyncio
import csv
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Voice pool — edge-tts Microsoft Neural (free)
# ---------------------------------------------------------------------------

# edge-tts free voice pool. "Guy" was DROPPED — it averaged 152v across 12 posts,
# far below Christopher (428v) and the paid ElevenLabs voices; channel_report
# flagged it as the single worst voice. Christopher leads (best free performer).
# Free edge-tts pool, upgraded to Microsoft's newest-generation narrators.
# Andrew and (free) Brian are a different class from the old Guy/Christopher
# voices — deep, warm, podcast-natural. Each entry carries its own rate/pitch
# profile, and all edge output runs through _master_voice() (warmth EQ + gentle
# compression) to close the gap with ElevenLabs. Goal: once analytics show a
# tuned free voice matching paid Brian (852v / 93% retention), drop ElevenLabs.
VOICE_POOL = [
    # already deep — only a gentle slow-down + slight drop, or they get boomy
    {"name": "Andrew",    "id": "en-US-AndrewNeural", "rate": "-4%", "pitch": "-2Hz"},
    {"name": "BrianEdge", "id": "en-US-BrianNeural",  "rate": "-4%", "pitch": "-2Hz"},
    # best of the old generation, kept as the control for the A/B
    {"name": "Christopher", "id": "en-US-ChristopherNeural", "rate": "+0%", "pitch": "-8Hz"},
]

# ElevenLabs A/B: analytics say the paid voices dominate (Brian 852v, Adam 728v
# vs the free edge voices' ~150–430v). To switch, add ONE secret —
# ELEVENLABS_API_KEY — and it defaults to Brian automatically. Override the voice
# with ELEVENLABS_VOICE_ID. If the paid call ever fails it falls back to edge-tts.
_EL_KEY          = os.environ.get("ELEVENLABS_API_KEY", "").strip()
_EL_BRIAN_VOICE  = "Gubgw9l4dtIoQA9YZHgx"  # "Brian" from the owner's ElevenLabs library — top performer (852v, 93% retention)
_EL_VOICE_ID     = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or (
    _EL_BRIAN_VOICE if _EL_KEY else ""
)

MIN_POSTS_FOR_WEIGHT = 5

WordTiming = tuple  # (word: str, start: float, end: float)


def _load_analytics() -> dict[str, int]:
    """Return {video_id: peak_views} from data/analytics.csv."""
    ROOT = Path(__file__).resolve().parent.parent
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


def pick_voice(rows: list[dict]) -> dict:
    """Return a voice from VOICE_POOL using analytics-weighted selection.

    Strategy:
      - Exploration (< MIN_POSTS_FOR_WEIGHT data per voice): LRU rotation.
      - Exploitation (enough data): block most-recent, pick highest avg-views.
    """
    analytics = _load_analytics()

    def avg_views(voice_name: str) -> float | None:
        matching = [r for r in rows
                    if r.get("voice_name") == voice_name and r.get("video_id")]
        if len(matching) < MIN_POSTS_FOR_WEIGHT:
            return None
        return sum(analytics.get(r["video_id"], 0) for r in matching) / len(matching)

    avgs = {v["name"]: avg_views(v["name"]) for v in VOICE_POOL}
    recent_voices = [r.get("voice_name") for r in reversed(rows) if r.get("voice_name")]
    block = recent_voices[0] if recent_voices else None

    if any(val is None for val in avgs.values()):
        candidates = [v for v in VOICE_POOL if v["name"] != block] or VOICE_POOL
        return candidates[date.today().toordinal() % len(candidates)]

    candidates = [v for v in VOICE_POOL if v["name"] != block] or VOICE_POOL
    return max(candidates, key=lambda v: avgs.get(v["name"], 0))


# ---------------------------------------------------------------------------
# Audio validation
# ---------------------------------------------------------------------------

def _audio_ok(audio_path: Path) -> bool:
    """Return True if the audio file exists and has meaningful content (>100 bytes)."""
    try:
        return audio_path.exists() and audio_path.stat().st_size > 100
    except Exception:
        return False


def _mean_volume_db(audio_path: Path) -> float:
    """Return the mean volume in dB via ffmpeg volumedetect.

    Real speech sits around -35..-15 dB; digital silence reports about -91 dB.
    Returns -91.0 if it can't be measured, so callers treat 'unknown' as silent.
    """
    try:
        out = subprocess.run(
            ["ffmpeg", "-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", out.stderr)
        return float(m.group(1)) if m else -91.0
    except Exception:
        return -91.0


def _voice_audio_is_real(audio_path: Path, text: str) -> tuple[bool, float, float]:
    """Guard against silent / truncated voiceovers reaching the render.

    A voiceover is 'real' only if it is non-empty, long enough for the script
    (>= ~0.1s per word, floor 1.5s), and actually audible (mean volume above
    -50 dB — well above the ~-91 dB of silence). Returns (ok, duration, mean_dB)
    so the caller can log the numbers either way.
    """
    if not _audio_ok(audio_path):
        return False, 0.0, -91.0
    dur = _audio_duration(audio_path)
    mean_db = _mean_volume_db(audio_path)
    n_words = len(_tokenize(text))
    min_dur = max(1.5, 0.10 * n_words)
    ok = dur >= min_dur and mean_db > -50.0
    return ok, dur, mean_db


# ---------------------------------------------------------------------------
# edge-tts synthesis (primary)
# ---------------------------------------------------------------------------

async def _edge_stream(text: str, out_path: Path, voice_id: str,
                       rate: str = "+0%", pitch: str = "-8Hz") -> list:
    """Async core: stream edge-tts, collect audio + word boundaries.

    rate/pitch come from the voice's profile in VOICE_POOL. (A previous global
    -15% slowdown read as "too slow" — keep adjustments per-voice and subtle.)
    """
    import edge_tts  # lazy import keeps startup fast when EL override is used

    communicate = edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch)
    audio_chunks: list[bytes] = []
    word_timings: list[tuple] = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            # Microsoft reports offsets in 100-nanosecond ticks
            start = chunk["offset"] / 1e7
            dur   = chunk["duration"] / 1e7
            word_timings.append((chunk["text"], start, start + dur))

    out_path.write_bytes(b"".join(audio_chunks))
    return word_timings


def _master_voice(audio_path: Path) -> None:
    """Studio-narrator mastering for edge-tts output (in place, best-effort).

    Raw neural TTS reads thin next to ElevenLabs. Chain: rumble cut → low-shelf
    warmth (+2.5dB @ 130Hz) → presence lift (+1.5dB @ 5kHz) → gentle 2.2:1
    compression → limiter. Timing is untouched, so word boundaries stay valid.
    Skippable with REEL_VOICE_MASTER=0. Failure leaves the original file.
    """
    if os.environ.get("REEL_VOICE_MASTER", "1") in ("0", "false", "False"):
        return
    tmp = audio_path.with_suffix(".mastered.mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-af",
             "highpass=f=70,"
             "equalizer=f=130:t=q:w=1:g=2.5,"
             "equalizer=f=5000:t=q:w=1.2:g=1.5,"
             "acompressor=threshold=-21dB:ratio=2.2:attack=15:release=180:makeup=2,"
             "alimiter=limit=0.95",
             "-c:a", "libmp3lame", "-b:a", "160k", str(tmp)],
            check=True, capture_output=True,
        )
        if tmp.exists() and tmp.stat().st_size > 1000:
            tmp.replace(audio_path)
            print("  tts: voice mastered (warmth EQ + compression)")
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        print(f"  tts: mastering skipped ({e})", file=sys.stderr)


def _synthesize_edge(text: str, out_path: Path, voice_id: str) -> tuple:
    """Run edge-tts synthesis and return (out_path, word_timings)."""
    prof = next((v for v in VOICE_POOL if v["id"] == voice_id), {})
    rate, pitch = prof.get("rate", "+0%"), prof.get("pitch", "-8Hz")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        timings = loop.run_until_complete(
            _edge_stream(text, out_path, voice_id, rate=rate, pitch=pitch))
    except RuntimeError:
        timings = asyncio.run(_edge_stream(text, out_path, voice_id, rate=rate, pitch=pitch))

    _master_voice(out_path)

    ok, dur, mean_db = _voice_audio_is_real(out_path, text)
    print(f"  tts: edge-tts audio dur={dur:.1f}s mean_vol={mean_db:.1f}dB "
          f"({'ok' if ok else 'REJECTED — silent/truncated'})")
    if not ok:
        # Empty, truncated, or silent — do NOT ship it. Raising here routes
        # synthesize_voice() to the gTTS fallback so the Short still gets a real
        # voice instead of a silent track that quietly passes downstream checks.
        raise RuntimeError(
            f"edge-tts audio unusable for voice {voice_id} "
            f"(dur={dur:.1f}s, mean_vol={mean_db:.1f}dB)."
        )

    if not timings:
        timings = _estimate_timings(text, dur)
    return out_path, timings


# ---------------------------------------------------------------------------
# gTTS synthesis (reliable fallback)
# ---------------------------------------------------------------------------
# edge-tts talks to an undocumented Microsoft Bing endpoint that frequently
# refuses connections from cloud IPs (e.g. GitHub Actions) or breaks when
# Microsoft rotates its anti-abuse token. When that happens we must still ship
# a voiceover, so gTTS (Google Translate TTS — free, no key, served from
# translate.google.com which is reachable from CI) is the safety net. It does
# not return word boundaries, so timings are estimated from the audio length.

def _synthesize_gtts(text: str, out_path: Path) -> tuple:
    """Synthesize with gTTS. Returns (out_path, estimated_word_timings)."""
    from gtts import gTTS  # lazy import — only needed when edge-tts fails

    out_path = Path(out_path)
    if out_path.suffix.lower() != ".mp3":
        out_path = out_path.with_suffix(".mp3")

    tts = gTTS(text=text, lang="en", tld="com")
    tts.save(str(out_path))

    ok, dur, mean_db = _voice_audio_is_real(out_path, text)
    print(f"  tts: gTTS audio dur={dur:.1f}s mean_vol={mean_db:.1f}dB "
          f"({'ok' if ok else 'STILL BAD'})")
    if not ok:
        raise RuntimeError(
            f"gTTS audio unusable (dur={dur:.1f}s, mean_vol={mean_db:.1f}dB) — "
            "both edge-tts and gTTS failed to produce an audible voiceover."
        )
    return out_path, _estimate_timings(text, dur)


# ---------------------------------------------------------------------------
# ElevenLabs synthesis (optional upgrade)
# ---------------------------------------------------------------------------

_EL_MODEL = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
_EL_SETTINGS = {
    "stability":        float(os.environ.get("ELEVENLABS_STABILITY",        "0.72")),
    "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY_BOOST", "0.90")),
    "style":            float(os.environ.get("ELEVENLABS_STYLE",            "0.20")),
    "use_speaker_boost": os.environ.get("ELEVENLABS_SPEAKER_BOOST", "1") not in ("0", "false"),
}
_EL_FORMAT = os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")


def _synthesize_elevenlabs(text: str, out_path: Path, voice_id: str) -> tuple:
    """ElevenLabs path (only called when ELEVENLABS_API_KEY + VOICE_ID are set)."""
    headers = {"xi-api-key": _EL_KEY, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": _EL_MODEL, "voice_settings": _EL_SETTINGS}

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
        resp = requests.post(url, headers={**headers, "Accept": "application/json"},
                             params={"output_format": _EL_FORMAT},
                             json=payload, timeout=120)
        resp.raise_for_status()
        import base64
        data = resp.json()
        out_path.write_bytes(base64.b64decode(data["audio_base64"]))
        alignment = data.get("alignment") or data.get("normalized_alignment")
        timings = _words_from_alignment(text, alignment)
        if timings and _audio_ok(out_path):
            return out_path, timings
    except Exception as e:
        print(f"  tts: ElevenLabs with-timestamps failed ({e}); trying plain endpoint")

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        resp = requests.post(url, headers={**headers, "Accept": "audio/mpeg"},
                             params={"output_format": _EL_FORMAT},
                             json=payload, timeout=120)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        if _audio_ok(out_path):
            return out_path, _estimate_timings(text, _audio_duration(out_path))
        raise ValueError("ElevenLabs plain endpoint returned empty audio")
    except Exception as e:
        print(f"  tts: ElevenLabs plain endpoint also failed ({e}); falling back to edge-tts")
        return _synthesize_edge(text, out_path, VOICE_POOL[0]["id"])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ElevenLabs character budget — sized for the Starter plan (30k chars/month).
#
# 4 posts/day x ~700 chars ≈ 84k/month, which only the Creator tier covers.
# Policy: Brian voices the FIRST N posts of each day (ELEVENLABS_POSTS_PER_DAY,
# default 1 ≈ 21k/month — fits Starter with headroom); edge-tts covers the
# rest, including backup-bank renders (they run after the day's first post, so
# they never touch paid credits). A live subscription check also refuses to
# spend when the remaining monthly credits are lower than the script needs.
# ---------------------------------------------------------------------------
EL_POSTS_PER_DAY = int(os.environ.get("ELEVENLABS_POSTS_PER_DAY", "1"))
_EL_CREDIT_BUFFER = 200  # keep a small reserve so we never hit the hard cap

# The voice that actually synthesized the last call — daily_post logs this so
# a Brian post is never attributed to an edge voice in the analytics.
LAST_VOICE_NAME = ""


def _count_posts_today() -> int:
    """Rows in data/posts.csv dated today (UTC) — mirrors the daily-cap guard."""
    import datetime
    log = Path(__file__).resolve().parent.parent / "data" / "posts.csv"
    if not log.exists():
        return 0
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        with open(log, newline="", encoding="utf-8") as f:
            return sum(1 for row in csv.reader(f) if row and row[0] == today)
    except Exception:
        return 0


def _el_credits_remaining() -> int | None:
    """Remaining monthly characters on the ElevenLabs subscription, or None if
    the check itself fails (caller then lets the synth call decide)."""
    try:
        resp = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": _EL_KEY}, timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        return int(d.get("character_limit", 0)) - int(d.get("character_count", 0))
    except Exception:
        return None


def _el_budget_allows(text: str) -> bool:
    """True if this post is within the daily ElevenLabs allocation AND the
    subscription has enough characters left for it."""
    n_today = _count_posts_today()
    if n_today >= EL_POSTS_PER_DAY:
        print(f"  tts: ElevenLabs daily allocation used ({n_today}/{EL_POSTS_PER_DAY} "
              f"posts today) — edge-tts for this one")
        return False
    remaining = _el_credits_remaining()
    if remaining is not None and remaining < len(text) + _EL_CREDIT_BUFFER:
        print(f"  tts: ElevenLabs credits low ({remaining} left, need "
              f"~{len(text) + _EL_CREDIT_BUFFER}) — edge-tts until the plan resets")
        return False
    if remaining is not None:
        print(f"  tts: ElevenLabs budget ok ({remaining} chars left this month)")
    return True


def synthesize_voice(text: str, out_path: Path, voice_id: str = None) -> tuple:
    """Synthesize `text` to `out_path`. Returns (out_path, word_timings).

    ElevenLabs (Brian) is used when the key is set AND the post fits the daily
    + monthly character budget; otherwise the free edge-tts pool, then gTTS.
    Sets LAST_VOICE_NAME to whichever voice actually spoke.
    Raises RuntimeError only if every engine fails.
    """
    global LAST_VOICE_NAME
    if _EL_KEY and _EL_VOICE_ID and _el_budget_allows(text):
        print(f"  tts: ElevenLabs active (voice {_EL_VOICE_ID})")
        try:
            result = _synthesize_elevenlabs(text, out_path, _EL_VOICE_ID)
            LAST_VOICE_NAME = "Brian"
            return result
        except Exception as e:  # noqa: BLE001
            # Bad key, exhausted credits, or API outage — degrade the voice,
            # never the channel. Fall through to the free edge-tts pool.
            print(f"  tts: ElevenLabs failed ({e}); falling back to edge-tts")

    vid = voice_id or VOICE_POOL[0]["id"]
    name = next((v["name"] for v in VOICE_POOL if v["id"] == vid), vid)
    print(f"  tts: edge-tts voice {name} ({vid})")
    try:
        result = _synthesize_edge(text, out_path, vid)
        LAST_VOICE_NAME = name
        return result
    except Exception as e:  # noqa: BLE001
        # edge-tts is flaky from cloud IPs; never let that ship a silent Short.
        print(f"  tts: edge-tts failed ({e}); falling back to gTTS")
        out_path, timings = _synthesize_gtts(text, out_path)
        print(f"  tts: gTTS fallback succeeded -> {Path(out_path).name}")
        LAST_VOICE_NAME = "gTTS"
        return out_path, timings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list:
    return re.findall(r"\S+", text)


def _words_from_alignment(text: str, alignment) -> list:
    """Fold ElevenLabs per-character alignment into per-word timings."""
    if not alignment:
        return []
    chars  = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends   = alignment.get("character_end_times_seconds")
    if not chars or not starts or not ends:
        return []
    if not (len(chars) == len(starts) == len(ends)):
        return []

    timings = []
    cur_chars, cur_start, cur_end = [], None, None
    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if cur_chars:
                timings.append(("".join(cur_chars), cur_start, cur_end))
                cur_chars, cur_start, cur_end = [], None, None
            continue
        if cur_start is None:
            cur_start = st
        cur_end = en
        cur_chars.append(ch)
    if cur_chars:
        timings.append(("".join(cur_chars), cur_start, cur_end))
    return timings


def _estimate_timings(text: str, duration: float) -> list:
    """Spread words across duration weighted by word length."""
    words = _tokenize(text)
    if not words:
        return []
    weights = [max(1, len(w)) for w in words]
    total = sum(weights)
    timings, t = [], 0.0
    for w, wt in zip(words, weights):
        span = duration * (wt / total)
        timings.append((w, t, t + span))
        t += span
    return timings


def _audio_duration(audio_path: Path) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(audio_path),
        ])
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 20.0
