"""
Original music for stoic edits: generated, owned outright, safe from Content ID.

Owner, 2026-10-05: "the music you chose sucks" (the Kevin MacLeod tracks in
epic_music.py) and named the sound he wants: Me and the Devil (slowed), You
Aren't Trying, Freedom (instrumental), Hans Zimmer's S.T.A.Y. / No Time for
Caution / Where We're Going, God's Promise (sped up), L'Amour Toujours
(instrumental), Chubina (slowed). 2026-10-08: "we have to find a way to use
them royalty free versions".

There is no royalty-free version of a copyrighted song. Slowed, sped-up,
instrumental and cover versions all carry the composition's copyright, and
Content ID matches them, so the rights holder takes the revenue or blocks the
video. What CAN be owned outright is an ORIGINAL track in the same style.

Every track in assets/music/edit/ was generated from a written description of
its style only (instruments, tempo, key, mood), with no song or artist names
and no reference or source audio, by ACE-Step 1.5. That model is
MIT-licensed, trained on licensed and royalty-free music, and its makers allow
commercial use of what it generates. data/edit_music.json records each track's
provenance (model, prompt, settings, date) so a wrongful claim can be
disputed with evidence.

Only tracks the owner has approved ("approved": true) ever air. The edit
preview workflow can audition an unapproved track with REEL_EDIT_MUSIC=<id>,
honoured ONLY when DRY_RUN=1, so an unapproved track can never be uploaded.

From 2026-10-25 (owner: "we really do need to find much better music") the
bank also holds ElevenLabs Music tracks (scripts/make_eleven_music.py). Their
licence forbids making them downloadable, so they are stored encrypted
(`<id>.mp3.gpg`, src/vault.py) and decrypted only into a temp file for one
render. Without the MUSIC_KEY secret they are skipped, never broken.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import proc
import shuffle
import vault

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "edit_music.json"
PREFIX = "edit:"


def load() -> list[dict]:
    try:
        data = json.loads(BANK.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return [t for t in data if isinstance(t, dict) and t.get("id") and t.get("file")]


def _exists(t: dict) -> bool:
    p = ROOT / t["file"]
    if p.suffix == vault.SUFFIX and not vault.available():
        return False      # encrypted, and this job has no MUSIC_KEY: skip it
    return p.exists() and p.stat().st_size > 50_000


def approved() -> list[dict]:
    """Tracks the owner has approved whose audio file is actually present."""
    return [t for t in load() if t.get("approved") is True and _exists(t)]


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "0") not in ("0", "", "false", "False")


def pick(post_rows: list[dict], seed: str = "") -> dict | None:
    """A SHUFFLE, like a playlist on shuffle: every approved track airs once
    per cycle, in a random order that changes each cycle, and the same track
    never plays twice in a row (not even across a cycle boundary). None when
    nothing is approved.

    The cycle is rebuilt from data/posts.csv, so it survives restarts, and a
    track approved mid-cycle simply joins the tracks still to play. `seed`
    (the date) makes a retried run on the same day pick the same track.
    """
    forced = os.environ.get("REEL_EDIT_MUSIC", "").strip()
    if forced and _dry_run():
        t = next((x for x in load() if x["id"] == forced and _exists(x)), None)
        if t:
            return t
        print(f"[edit_music] REEL_EDIT_MUSIC={forced} not found", file=sys.stderr)
    by_id = {t["id"]: t for t in approved()}
    tid = shuffle.pick(by_id, played(post_rows), seed)
    return by_id[tid] if tid else None


def played(post_rows: list[dict]) -> list[str]:
    """Ids of the original tracks that aired, oldest first."""
    return [(r.get("music_track") or "").removeprefix(PREFIX) for r in post_rows
            if (r.get("music_track") or "").startswith(PREFIX)]


def planned(post_rows: list[dict], seed: str = "") -> str | None:
    """The id `pick` chooses on a live run, from the approval flags alone, so
    a job without MUSIC_KEY (the rehearsal check) can tell that the owner's
    approvals changed the next Short's music."""
    ids = [t["id"] for t in load() if t.get("approved") is True]
    return shuffle.pick(ids, played(post_rows), seed)


def _length(path: Path) -> float:
    """Seconds of audio in `path`; 0.0 when ffprobe can't tell."""
    try:
        out = proc.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True)
        return float(out.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def cut_start(start: float, seconds: float, length: float) -> float:
    """Where the cut begins: at the drop, unless the track ends before the
    Short does. render.py loops the bed, so a cut that runs out restarts at
    the drop in the last second (el3_upright_tape drops at 24 s of 40 s, and
    edits run to 17 s). Then it starts just early enough to end with the
    track: the drop lands a moment in, and the song ends with the Short."""
    start = max(0.0, start)
    if length > 0 and start + seconds > length - 0.1:
        return max(0.0, length - 0.1 - seconds)
    return start


def fetch(track: dict, out_path: Path, seconds: float) -> Path | None:
    """The track from its drop, `seconds` long, with a short fade in and a
    1.2s fade out. None on any failure, so the caller keeps its fallback."""
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as td:
            # An encrypted track is decrypted into this temp dir only, and the
            # copy is gone when the render's cut is made.
            src = vault.plain(ROOT / track["file"], Path(td))
            if src is None:
                raise RuntimeError("encrypted and no MUSIC_KEY, or the file is missing")
            drop = float(track.get("start", 0.0))
            start = cut_start(drop, seconds, _length(src))
            if start != max(0.0, drop):
                print(f"  [edit_music] {track.get('id')}: the drop at {drop}s leaves too little "
                      f"for {seconds:.1f}s; cutting from {start:.1f}s so the bed never loops")
            fade_out = max(0.0, seconds - 1.2)
            proc.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", str(src),
                      "-t", f"{seconds:.2f}",
                      "-af", f"afade=t=in:d=0.15,afade=t=out:st={fade_out:.2f}:d=1.2",
                      "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
                     check=True, capture_output=True)
        return out_path if out_path.exists() and out_path.stat().st_size > 10_000 else None
    except Exception as e:  # noqa: BLE001
        print(f"[edit_music] {track.get('id')} unavailable ({e})", file=sys.stderr)
        return None
