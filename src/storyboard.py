"""
Storyboards in the daily pipeline.

A story whose storyboard in data/storyboards.json is `"status": "approved"`
gets its background generated shot by shot (src/hfgen.py: Wan 3.0 for places,
Soul -> Kling 2.5 for people) instead of searched from stock. Everything else
about the post — voice, hook, quote card, grade, QA — is unchanged.

Rules this module keeps:
  * ON by default only when there is a key; REEL_STORYBOARDS=0 turns it off
    without touching the secret.
  * A failed shot is NOT fatal. Its slot falls back to a stock search for the
    story's own b-roll query, so the post still goes out.
  * Shots are generated in parallel (they are independent), so eight shots
    cost the wall-clock of about two, not eight — the render budget matters.
  * Timing follows the voice: shots before the quote fill the narration up to
    the moment the quote appears, the quote shot and after fill the rest. The
    plan's proportions survive whatever length the real voiceover comes out.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARDS = ROOT / "data" / "storyboards.json"
WORKERS = int(os.environ.get("STORYBOARD_WORKERS", "4"))


def enabled() -> bool:
    import hfgen
    on = os.environ.get("REEL_STORYBOARDS", "1") not in ("0", "false", "False", "")
    return on and bool(hfgen.key())


def load(story_id: str) -> dict | None:
    """The APPROVED board for this story, or None. Drafts never air."""
    try:
        boards = json.loads(BOARDS.read_text())
    except Exception:  # noqa: BLE001
        return None
    b = boards.get(story_id)
    if isinstance(b, dict) and b.get("status") == "approved" and b.get("shots"):
        return b
    return None


def plan_seconds(board: dict, quote_at: float, total: float) -> list[float]:
    """Absolute on-screen seconds per shot, aligned to the quote.

    Shots before the one marked `quote` are scaled to end exactly when the
    quote card appears; the quote shot and everything after fill the rest.
    Without a quote marker (or a usable quote time) it is a plain scale.
    """
    secs = [float(s["seconds"]) for s in board["shots"]]
    qi = next((i for i, s in enumerate(board["shots"]) if s.get("quote")), None)
    if qi is None or not (0 < quote_at < total) or qi == 0:
        k = total / sum(secs)
        return [x * k for x in secs]
    pre, post = secs[:qi], secs[qi:]
    a, b = quote_at / sum(pre), (total - quote_at) / sum(post)
    return [x * a for x in pre] + [x * b for x in post]


def generate(board: dict, out_dir: Path) -> list[Path | None]:
    """Render every shot; None where a shot failed. Order is preserved."""
    import hfgen
    out_dir.mkdir(parents=True, exist_ok=True)
    cast = board.get("cast", {})

    def one(i_spec):
        i, spec = i_spec
        path = out_dir / f"sb_shot{i:02d}.mp4"
        try:
            got = hfgen.shot(spec, cast, path)
        except Exception as e:  # noqa: BLE001
            print(f"  [storyboard] shot {i + 1} crashed: {e}", file=sys.stderr)
            got = None
        print(f"  [storyboard] shot {i + 1}/{len(board['shots'])} "
              f"{spec['model']:5s} {'OK' if got else 'FAILED -> stock'}", flush=True)
        return got

    with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as pool:
        return list(pool.map(one, enumerate(board["shots"])))
