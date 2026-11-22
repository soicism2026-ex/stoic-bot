"""
VIDEO BACKGROUNDS: three of a Short's paintings animated by Seedance 2.0 Mini
(image-to-video on Higgsfield's REST API), a one-month test.

Owner, 2026-11-22, in the HQ ("Video backgrounds: which storyboard?"): "Cheapest:
Seedance Mini", and "test cheapest for 1 month". The ledger test is `video-bg`
in data/marketing_tests.json: ONE Short a day (the first post of each air day,
src/airday.py, so the rehearsal and the live post agree), from 2026-11-23 to
2026-12-22 inclusive, then it switches itself off.

What it does: for the chosen Short, shots 0 (the hook's), n/3 and 2n/3 are cut
in as 5 s clips made from the exact painted still the painter cached for that
shot; every other shot stays a painted still. Type, music, sound and mastering
are untouched. ANY failure leaves that shot a painted still: never a stopped
post.

Money (owner's rule: never bill by accident):
  * at most MAX_GEN_PER_DAY (3) generations a day, counted in a daily ledger
    (video_credits.json in the still cache, like imagegen's neurons.json) and
    at most that many per process;
  * a submit is sent ONCE (an Idempotency-Key from the cache key, no retry):
    a call that may have been accepted is never repeated, it would charge again;
  * clips are cached by (model, image hash, prompt, seed, duration) beside the
    stills (REEL_STILL_CACHE, actions/cache), so the rehearsal pays and the
    live post reuses; with no rehearsal the live post generates;
  * a hard deadline per clip (VIDEO_BG_DEADLINE, 300 s).

API (docs.higgsfield.ai, read 2026-11-22): POST https://api.higgsfield.ai/<model>
with {image_url, prompt, duration, resolution, generate_audio}: no aspect_ratio
and no seed (the framing follows the image; additionalProperties is false), the
image must be a public URL, so the still goes up through POST /files/generate-upload-url
then a PUT. Submit returns {request_id, status_url}; poll until completed (video.url)
or failed/nsfw/canceled. 403 without a `code` is "insufficient balance".
NOT VERIFIED against the live API: the docs list Seedance 2.0 and 2.5 but no
"mini" id; VIDEO_BG_MODEL defaults to the pattern guess below. A wrong id is a
404/422: logged, and every shot stays painted.
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

import proc

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("VIDEO_BG_API", "https://api.higgsfield.ai").rstrip("/")
MODEL = os.environ.get("VIDEO_BG_MODEL", "bytedance/seedance-2.0-mini/image-to-video")
RESOLUTION = os.environ.get("VIDEO_BG_RESOLUTION", "480p")
SECONDS = 5
MAX_GEN_PER_DAY = int(os.environ.get("VIDEO_BG_MAX_PER_DAY", "3"))
CREDITS_PER_CLIP = float(os.environ.get("VIDEO_BG_CREDITS_PER_CLIP", "5"))
DEADLINE = float(os.environ.get("VIDEO_BG_DEADLINE", "300"))
POLL_EVERY = float(os.environ.get("VIDEO_BG_POLL_EVERY", "5"))
HTTP_TIMEOUT = 60
TEST_ID = "video-bg"
WINDOW = (_dt.date(2026, 11, 23), _dt.date(2026, 12, 22))     # inclusive
PROMPT_TAIL = ("slow natural motion, gentle camera move, the oil painting stays an oil "
               "painting, no text, no new people")
CSV_PATH = ROOT / "data" / "video_bg.csv"
TESTS_PATH = ROOT / "data" / "marketing_tests.json"
POSTS_PATH = ROOT / "data" / "posts.csv"
NO_CREDITS = "no Higgsfield credits: painted stills used"

_LOCK = threading.Lock()
_GENERATED = 0            # this process
_STOPPED = ""             # a reason that ends every further call this run
_CLIPS: dict = {}         # slot -> clip path (ok) or None (failed), this run
_FAILS = 0


class NoCredits(RuntimeError):
    pass


def reset() -> None:
    global _GENERATED, _STOPPED, _FAILS
    _GENERATED, _STOPPED, _FAILS = 0, "", 0
    _CLIPS.clear()


def api_key() -> str:
    key = (os.environ.get("HIGGSFIELD_API_KEY") or os.environ.get("HF_KEY") or "").strip()
    return key if key and ":" in key else ""


def _headers(extra: dict | None = None) -> dict:
    return {"Authorization": f"Key {api_key()}", "Content-Type": "application/json", **(extra or {})}


# ------------------------------------------------------------------ the gate
def _test_running() -> bool:
    """The ledger test must exist and be running (the owner can stop it by
    setting its status)."""
    try:
        for t in json.loads(TESTS_PATH.read_text(encoding="utf-8")).get("tests", []):
            if t.get("id") == TEST_ID:
                return t.get("status") == "running"
    except Exception:  # noqa: BLE001
        pass
    return False


def in_window(day: _dt.date) -> bool:
    return WINDOW[0] <= day <= WINDOW[1]


def _rows(path: Path) -> list[dict]:
    try:
        return list(csv.DictReader(open(path, encoding="utf-8"))) if path.exists() else []
    except Exception:  # noqa: BLE001
        return []


def first_post_of_day(day: _dt.date, posts: list[dict] | None = None) -> bool:
    posts = _rows(POSTS_PATH) if posts is None else posts
    return not any(r.get("date") == day.isoformat() for r in posts)


def already_done(day: _dt.date, log: list[dict] | None = None) -> bool:
    """One video Short a day: a logged row with clips that worked ends the day
    (a row with none lets a later run try again, within the day's ledger)."""
    log = _rows(CSV_PATH) if log is None else log
    return any(r.get("date") == day.isoformat() and int(r.get("clips_ok") or 0) > 0 for r in log)


def active(day: _dt.date | None = None) -> bool:
    """Should this render animate shots? Painted look, key present, the test
    running, inside the window, and the first post of its air day."""
    if os.environ.get("REEL_VIDEO_BG", "1") in ("0", "false", "False", ""):
        return False
    if not api_key():
        return False
    import airday
    day = day or airday.today()
    return (in_window(day) and _test_running() and first_post_of_day(day)
            and not already_done(day))


def plan(n_slots: int) -> list[int]:
    """The hook's shot first, then two more spread across the Short."""
    if n_slots < 1:
        return []
    return sorted({0, round(n_slots / 3), round(2 * n_slots / 3)} & set(range(n_slots)))


# ------------------------------------------------------------------ the ledger
def _cache() -> Path | None:
    import imagegen
    return imagegen.still_cache_dir()


def _ledger_file() -> Path | None:
    c = _cache()
    return (c / "video_credits.json") if c else None


def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def spent_today() -> tuple[int, float]:
    """(generations, credits) today (UTC)."""
    lp = _ledger_file()
    try:
        if lp and lp.exists():
            d = json.loads(lp.read_text(encoding="utf-8"))
            if d.get("day") == _today():
                return int(d.get("generations", 0)), float(d.get("credits", 0.0))
    except Exception:  # noqa: BLE001
        pass
    return 0, 0.0


def _ledger_add(credits: float) -> None:
    lp = _ledger_file()
    if not lp:
        return
    g, c = spent_today()
    try:
        lp.write_text(json.dumps({"day": _today(), "generations": g + 1,
                                  "credits": round(c + credits, 2)}), encoding="utf-8")
    except OSError:
        pass


def _may_generate() -> bool:
    g, _ = spent_today()
    return _GENERATED < MAX_GEN_PER_DAY and g < MAX_GEN_PER_DAY


# ------------------------------------------------------------------ the cache
def clip_prompt(scene: str) -> str:
    return f"{(scene or '').strip().rstrip('.')}. {PROMPT_TAIL}"[:900]


def cache_key(image: Path, prompt: str, seed) -> str:
    h = hashlib.sha256(Path(image).read_bytes()).hexdigest()
    raw = "|".join([MODEL, h, prompt, str(seed), str(SECONDS), RESOLUTION])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _cached(key: str) -> Path | None:
    c = _cache()
    p = (c / f"vid_{key}.mp4") if c else None
    return p if p and p.exists() and p.stat().st_size > 10_000 else None


# ------------------------------------------------------------------ the API
def _upload(image: Path) -> str:
    ext = image.suffix.lower()
    ctype = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")
    r = requests.post(f"{API}/files/generate-upload-url", json={"content_type": ctype},
                      headers=_headers(), timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    put = requests.put(d["upload_url"], data=image.read_bytes(),
                       headers=d.get("upload_headers") or {"Content-Type": ctype}, timeout=HTTP_TIMEOUT)
    put.raise_for_status()
    return d["public_url"]


def request_body(image_url: str, prompt: str) -> dict:
    """The request, exactly: the schema allows no other field."""
    return {"image_url": image_url, "prompt": prompt, "duration": SECONDS,
            "resolution": RESOLUTION, "generate_audio": False}


def _check(r: requests.Response) -> None:
    if r.status_code == 403:
        try:
            code = (r.json() or {}).get("code")
        except Exception:  # noqa: BLE001
            code = None
        if not code:
            raise NoCredits(NO_CREDITS)
    r.raise_for_status()


def _submit(body: dict, idem: str) -> dict:
    """ONE attempt. Never retried: a submit that may have been accepted would
    charge again."""
    r = requests.post(f"{API}/{MODEL}", json=body, headers=_headers({"Idempotency-Key": idem}),
                      timeout=HTTP_TIMEOUT)
    _check(r)
    return r.json()


def _poll(status_url: str, deadline: float) -> dict:
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("clip exceeded VIDEO_BG_DEADLINE")
        try:
            r = requests.get(status_url, headers=_headers(), timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            d = r.json()
        except requests.RequestException as e:            # a status read is safe to repeat
            print(f"  [animator] status read failed ({e}); trying again", file=sys.stderr, flush=True)
            time.sleep(POLL_EVERY)
            continue
        st = (d.get("status") or "").lower()
        if st == "completed":
            return d
        if st in ("failed", "nsfw", "canceled"):
            raise RuntimeError(f"generation {st}: {d.get('error', '')}")
        time.sleep(POLL_EVERY)


def _download(url: str, out: Path) -> Path:
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(out, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
    if out.stat().st_size < 10_000:
        raise RuntimeError("download produced no usable file")
    return out


def _normalise(raw: Path, out: Path) -> Path:
    """1080x1920, 30 fps, no audio: interchangeable with a painted-still clip."""
    import painter
    proc.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw),
              "-vf", f"scale={painter.W}:{painter.H}:force_original_aspect_ratio=increase:flags=lanczos,"
                     f"crop={painter.W}:{painter.H},setsar=1,fps=30,format=yuv420p",
              "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
              "-pix_fmt", "yuv420p", str(out)], check=True, capture_output=True, timeout=240)
    if not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError("normalised clip is unusable")
    return out


def generate(image: Path, scene: str, seed, work: Path) -> tuple[Path | None, str]:
    """One shot's clip -> (path or None, how: 'cache' | 'generated' | reason).
    Never raises."""
    global _GENERATED, _STOPPED
    try:
        prompt = clip_prompt(scene)
        key = cache_key(image, prompt, seed)
        hit = _cached(key)
        if hit:
            return hit, "cache"
        with _LOCK:
            if _STOPPED:
                return None, _STOPPED
            if not _may_generate():
                return None, f"spend cap ({MAX_GEN_PER_DAY} generations a day) reached"
            _GENERATED += 1
            _ledger_add(CREDITS_PER_CLIP)                  # counted BEFORE the call: it may be accepted
        deadline = time.monotonic() + DEADLINE
        sub = _submit(request_body(_upload(image), prompt), "vbg-" + key)
        data = sub if (sub.get("status") or "").lower() == "completed" else _poll(
            sub.get("status_url") or f"{API}/requests/{sub['request_id']}/status", deadline)
        url = (data.get("video") or {}).get("url")
        if not url:
            raise RuntimeError(f"completed with no video url: {data}")
        work.mkdir(parents=True, exist_ok=True)
        raw = _download(url, work / f"vbg_{key}.raw.mp4")
        c = _cache() or work
        final = _normalise(raw, c / f"vid_{key}.mp4")
        raw.unlink(missing_ok=True)
        return final, "generated"
    except NoCredits:
        with _LOCK:
            _STOPPED = NO_CREDITS
        return None, NO_CREDITS
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:200]


# ------------------------------------------------------------------ the Short
def _slot_image(slot: int, theme: str):
    import painter
    scene, seed, prompt, _, _ = painter._slot_request(slot, theme)
    got = painter.painted_still(prompt, seed, scene)
    return (Path(got["path"]), scene, got.get("seed_used", seed)) if got else None


def prefetch(n_slots: int, theme: str, work: Path) -> None:
    """Make (or fetch from the cache) the clips for this Short's three shots, in
    parallel. Results are kept for animate_slot."""
    from concurrent.futures import ThreadPoolExecutor
    global _FAILS
    if not active():
        return
    slots = plan(n_slots)

    def one(s):
        img = _slot_image(s, theme)
        if not img:
            return s, None, "no painted still"
        clip, how = generate(img[0], img[1], img[2], work)
        return s, clip, how

    with ThreadPoolExecutor(max_workers=max(1, len(slots))) as pool:
        for s, clip, how in pool.map(one, slots):
            _CLIPS[s] = clip
            if clip:
                print(f"  [animator] shot {s}: animated ({how})", flush=True)
            else:
                _FAILS += 1
                print(f"  [animator] shot {s}: stays a painted still ({how})", file=sys.stderr, flush=True)


def animate_slot(slot: int, out_path: Path) -> bool:
    """Swap shot `slot`'s painted clip for its animated one. False = unchanged."""
    import painter
    clip = _CLIPS.get(slot)
    if not clip or not Path(clip).exists():
        return False
    try:
        tmp = Path(out_path).with_suffix(".anim.mp4")
        tmp.write_bytes(Path(clip).read_bytes())
        os.replace(tmp, out_path)
    except OSError as e:
        print(f"  [animator] shot {slot}: could not place the clip ({e})", file=sys.stderr, flush=True)
        return False
    painter.ANIMATED.add(slot)
    if slot in painter.SLOTS:
        painter.SLOTS[slot]["animated"] = True
    return True


def record(edit: str, video: str, day: _dt.date) -> None:
    """data/video_bg.csv: date, edit, video id, clips ok, clips failed, credits.
    Only a LIVE post that tried to animate writes a row. Never raises."""
    try:
        import painter
        ok, failed = len(painter.ANIMATED), _FAILS
        if not (ok or failed):
            return
        _, credits = spent_today()
        new = not CSV_PATH.exists()
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "edit", "video_id", "clips_ok", "clips_failed", "credits"])
            w.writerow([day.isoformat(), edit, video, ok, failed, credits])
    except Exception as e:  # noqa: BLE001
        print(f"  [animator] could not log: {e}", file=sys.stderr, flush=True)
