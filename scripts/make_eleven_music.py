"""
Edit music from ElevenLabs Music v2.5: the "much better music" Orpheus was
asked to find (owner, 2026-10-25: "All these still kinda suck ... we really do
need to find much better music so have an agent work on it").

    python scripts/make_eleven_music.py preflight                 # free: key permission + prompt filter
    python scripts/make_eleven_music.py generate [--ids a,b]      # spends plan credits: compose, master, encrypt
    python scripts/make_eleven_music.py sampler out.mp4 [--ids a,b]

Why ElevenLabs (research 2026-10-25): the Starter plan the channel already
pays for includes 17 minutes of music a month, allows online commercial use
with no attribution, and its v2.5 model is trained on licensed catalogues.
Composition plans fix every section's length, so each track's drop lands
exactly where an edit starts (a 5 s build, then the drop). Two plans are
conditioned on the owner's "best for now" picks (songs 1 and 9) to rebuild
them at a higher quality.

The licence forbids making the tracks available for others to download, and
this repo is public, so every track is committed only as an AES-256 gpg file
(src/vault.py, key = the MUSIC_KEY secret). Every new track enters
data/edit_music.json UNAPPROVED: nothing airs until the owner picks it by ear.

Spend guard: the run refuses to start unless the month's remaining credits
cover the round plus RESERVE for Brian's narration. A compose request that
times out is never retried (ElevenLabs charges per request); only 429 and 5xx
are, twice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import vault  # noqa: E402
import make_edit_music as mem  # noqa: E402  (loudness and drop-finding helpers)

API = "https://api.elevenlabs.io"
MODEL = "music_v2_5"
PLANS = ROOT / "data" / "edit_music_plans_eleven.json"
BANK = ROOT / "data" / "edit_music.json"
OUT_DIR = ROOT / "assets" / "music" / "edit"
CREDITS_PER_MIN = 900          # Eleven Music, from the shared monthly pool
RESERVE = 12_000               # left untouched for Brian's narration
USED_SECONDS = 16.0            # an edit uses ~16 s from the start point
LICENSE = ("ElevenLabs Music Terms (updated 2026-10-09), {tier} plan: online commercial "
           "use permitted, no attribution required; stored encrypted, never made available "
           "to third parties (section 4.2)")


def _key() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    return k


def load_plans(ids: list[str] | None = None) -> list[dict]:
    plans = json.loads(PLANS.read_text(encoding="utf-8"))
    return [p for p in plans if not ids or p["id"] in ids]


def plan_seconds(p: dict) -> float:
    return sum(c["duration_ms"] for c in p["chunks"]) / 1000


def round_cost(plans: list[dict]) -> int:
    """Credits for composing these plans plus uploading their references
    (an upload costs what generating the same length does)."""
    secs = sum(plan_seconds(p) for p in plans)
    refs = {(p["conditioning"]["track"], p["conditioning"]["start_ms"], p["conditioning"]["end_ms"])
            for p in plans if p.get("conditioning")}
    secs += sum((e - s) / 1000 for _, s, e in refs)
    return int(round(secs / 60 * CREDITS_PER_MIN))


def summary_prompt(p: dict) -> str:
    """One sentence from the plan's own styles, for the free /plan preflight."""
    first, drop = p["chunks"][0], p["chunks"][1]
    styles = first["positive_styles"][:3] + drop["positive_styles"][:3]
    return "Instrumental. " + ", ".join(styles) + "."


def subscription() -> dict:
    r = requests.get(f"{API}/v1/user/subscription", headers={"xi-api-key": _key()}, timeout=30)
    r.raise_for_status()
    return r.json()


def credits_left(sub: dict) -> int:
    return int(sub.get("character_limit", 0)) - int(sub.get("character_count", 0))


def preflight(plans: list[dict]) -> list[dict]:
    """POST /v1/music/plan costs no credits: it proves the key may use music
    and that every prompt passes ElevenLabs' copyright filter."""
    out = []
    for p in plans:
        r = requests.post(f"{API}/v1/music/plan", headers={"xi-api-key": _key()},
                          json={"prompt": summary_prompt(p), "music_length_ms": int(plan_seconds(p) * 1000),
                                "model_id": MODEL}, timeout=120)
        if r.status_code == 200:
            verdict = "ok"
        elif r.status_code in (401, 403):
            verdict = "no permission: tick Music on the ElevenLabs API key"
        else:
            verdict = f"HTTP {r.status_code}: {r.text[:240]}"
        out.append({"id": p["id"], "verdict": verdict})
        print(f"  {p['id']}: {verdict}", flush=True)
    return out


def _post(path: str, *, timeout: int = 600, **kw) -> requests.Response:
    """POST with retries on 429/5xx only. A timeout is NOT retried: the
    request may still have been charged."""
    for attempt in range(3):
        r = requests.post(f"{API}{path}", headers={"xi-api-key": _key()}, timeout=timeout, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(20 * (attempt + 1))
            continue
        return r
    return r


def upload_reference(track_id: str, start_ms: int, end_ms: int, work: Path) -> str:
    """Cut [start, end] from an approved bank track and upload it as a
    conditioning reference. Returns its song_id."""
    bank = {t["id"]: t for t in json.loads(BANK.read_text(encoding="utf-8"))}
    t = bank[track_id]
    src = vault.plain(ROOT / t["file"], work)
    if src is None:
        raise SystemExit(f"reference {track_id} is not readable")
    cut = work / f"ref_{track_id}.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start_ms / 1000:.2f}", "-t",
                    f"{(end_ms - start_ms) / 1000:.2f}", "-i", str(src), "-c:a", "libmp3lame",
                    "-b:a", "192k", str(cut)], check=True)
    with open(cut, "rb") as fh:
        r = _post("/v1/music/upload", files={"file": (cut.name, fh, "audio/mpeg")}, timeout=300)
    if r.status_code != 200:
        raise SystemExit(f"upload of {track_id} failed: HTTP {r.status_code} {r.text[:200]}")
    return r.json()["song_id"]


def body(p: dict, ref_song: str | None) -> dict:
    chunks = json.loads(json.dumps(p["chunks"]))
    if ref_song:
        c = p["conditioning"]
        chunks[0]["conditioning_ref"] = {"song_id": ref_song,
                                         "range": {"start_ms": 0, "end_ms": c["end_ms"] - c["start_ms"]}}
        chunks[0]["condition_strength"] = c.get("strength", "medium")
    return {"model_id": MODEL, "seed": p["seed"], "composition_plan": {"chunks": chunks}}


def master(raw: Path, out_mp3: Path) -> tuple[float, str, float, float]:
    """One constant gain to -16 LUFS and a limiter, as for every edit track
    (single-pass loudnorm flattened the drop), then find the start point."""
    gain = mem.TARGET_LUFS - mem.integrated_lufs(raw)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
                    f"volume={gain:.2f}dB,alimiter=limit=0.84:level=false,aresample=44100",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)], check=True)
    db = mem.loudness_curve(out_mp3)
    start, how, contrast = mem.find_start(db)
    return start, how, contrast, round(len(db) * mem.HOP, 1)


def words_heard(mp3: Path, start: float, work: Path) -> str:
    """What Scribe hears in the part an edit uses: a check for stray vocals.
    Empty when it hears nothing (or cannot listen)."""
    try:
        import listen_check  # noqa: PLC0415
        seg = work / f"{mp3.stem}_used.mp3"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", str(USED_SECONDS),
                        "-i", str(mp3), str(seg)], check=True)
        text = listen_check.transcribe(seg)
        text = re.sub(r"[\(\[][^)\]]*[\)\]]", " ", text)     # drop "(music)"-style tags
        return " ".join(text.split()) if len(text.split()) >= 3 else ""
    except Exception:  # noqa: BLE001
        return ""


def _bank_format(raw: str) -> bool:
    data = json.loads(raw)
    return json.dumps(data, indent=1, ensure_ascii=True) + "\n" == raw


def save_bank(entries: list[dict]) -> None:
    raw = BANK.read_text(encoding="utf-8")
    ascii_ = _bank_format(raw)
    bank = [t for t in json.loads(raw) if t["id"] not in {e["id"] for e in entries}]
    BANK.write_text(json.dumps(bank + entries, indent=1, ensure_ascii=ascii_) + "\n", encoding="utf-8")


def generate(plans: list[dict]) -> list[dict]:
    if not vault.available():
        raise SystemExit("MUSIC_KEY is not set: refusing to make tracks that could not be stored privately")
    sub = subscription()
    need, left = round_cost(plans), credits_left(sub)
    print(f"round: {len(plans)} tracks, about {need} credits; {left} left this month "
          f"(reserve {RESERVE} for narration)", flush=True)
    if left - need < RESERVE:
        raise SystemExit("not enough credits this month for this round and Brian's narration")
    tier = sub.get("tier", "unknown")
    entries = []
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        refs: dict[tuple, str] = {}
        for p in plans:
            c = p.get("conditioning")
            ref_song = None
            if c:
                k = (c["track"], c["start_ms"], c["end_ms"])
                if k not in refs:
                    refs[k] = upload_reference(c["track"], c["start_ms"], c["end_ms"], work)
                ref_song = refs[k]
            r = _post("/v1/music", params={"output_format": "mp3_44100_128"}, json=body(p, ref_song))
            if r.status_code != 200:
                print(f"  {p['id']}: HTTP {r.status_code} {r.text[:240]}", flush=True)
                continue
            raw = work / f"{p['id']}_raw.mp3"
            raw.write_bytes(r.content)
            mp3 = work / f"{p['id']}.mp3"
            start, how, contrast, dur = master(raw, mp3)
            heard = words_heard(mp3, start, work)
            enc = vault.encrypt(mp3, OUT_DIR / f"{p['id']}.mp3{vault.SUFFIX}")
            entry = {
                "id": p["id"], "file": str(enc.relative_to(ROOT)), "label": p["label"],
                "style_of": p["style_of"], "start": start,
                "start_how": f"{how} ({contrast} dB build-to-drop contrast)", "duration": dur,
                "approved": False,
                "provenance": {
                    "model": f"ElevenLabs Music v2.5 ({MODEL})", "song_id": r.headers.get("song-id", ""),
                    "seed": p["seed"], "plan": p["chunks"],
                    "conditioning": ({**c, "song_id": ref_song} if c else None),
                    "license": LICENSE.format(tier=tier), "stored": "encrypted (src/vault.py)",
                    "words_heard": heard, "generated": dt.date.today().isoformat(),
                },
            }
            entries.append(entry)
            print(f"  {p['id']}: {dur}s, start {start}s ({how}, {contrast} dB)"
                  + (f", HEARD WORDS: {heard!r}" if heard else ""), flush=True)
    if entries:
        save_bank(entries)
    after = credits_left(subscription())
    print(f"made {len(entries)} of {len(plans)}; {left - after} credits used, {after} left", flush=True)
    return entries


def sampler(out: Path, ids: list[str]) -> Path:
    import music_sampler  # noqa: PLC0415
    bank = {t["id"]: t for t in json.loads(BANK.read_text(encoding="utf-8"))}
    tracks = [bank[i] for i in ids if i in bank]
    if not tracks:
        raise SystemExit("no tracks to sample")
    return music_sampler.build(tracks, out)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preflight", "generate"):
        s = sub.add_parser(name)
        s.add_argument("--ids", default="")
    s = sub.add_parser("sampler")
    s.add_argument("out", type=Path)
    s.add_argument("--ids", default="")
    a = ap.parse_args()
    ids = [i.strip() for i in a.ids.split(",") if i.strip()]
    if a.cmd == "preflight":
        sub_ = subscription()
        print(f"plan {sub_.get('tier')} ({sub_.get('status')}): {credits_left(sub_)} credits left this month")
        res = preflight(load_plans(ids or None))
        return 0 if all(r["verdict"] == "ok" for r in res) else 1
    if a.cmd == "generate":
        plans = load_plans(ids or None)
        made = generate(plans)
        Path(os.environ.get("RUNNER_TEMP", "/tmp")).joinpath("new_music_ids.txt").write_text(
            ",".join(e["id"] for e in made))
        return 0 if made else 1
    if not ids:
        p = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "new_music_ids.txt"
        ids = [i for i in (p.read_text().split(",") if p.exists() else []) if i]
    sampler(a.out, ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
