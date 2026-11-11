"""Capture the ffmpeg command render.render_reel builds, without running it.

Used by tests/test_painter_render.py to prove that, with the painted picture
off, today's edit renders exactly as before: the command is compared with a
golden captured from render.py before the painter existed
(tests/golden/render_cmd_*.json, written by `python3 tests/render_capture.py
golden`). Paths that differ run to run (the temp dir, the repo root, fonts)
are normalised.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden"

HOOK = "Stop wishing things went differently."
QUOTE = "Seek not that the things which happen should happen as you wish."
# The live edit: daily-short env + the "edit" style pack (scripts/daily_post.py).
LIVE_EDIT = {
    "REEL_HOOK_CAPS": "1", "REEL_HOOK_WRAP": "16", "REEL_HOOK_SOUND": "0",
    "REEL_FRAME": "0", "REEL_CINEMATIC": "0", "REEL_EXTRA_DARKEN": "0",
    "REEL_BRIGHTNESS": "-0.02", "REEL_MONO": "1", "MUSIC_VOLUME": "0.38",
    "REEL_IMAGE_TAGGED_ONLY": "1", "REEL_HOOK_ASS_FONTSIZE": "96",
    "REEL_HOOK_FROM_START": "1", "REEL_QUOTE_ASS_FS": "84", "REEL_KLING_BG": "0",
    "REEL_TAIL": "2.0", "REEL_BG_STRICT": "1", "REEL_SFX": "0", "REEL_BG_CLIPS": "8",
    "REEL_QUOTE_APPEAR": "2.85", "REEL_QUOTE_SPOKEN": "1", "REEL_IMAGE_BG": "1",
    "DRY_RUN": "1", "REEL_TODAY": "2026-11-12",
}
# A classic post (stock motion on, cinematic grade): the other default path.
CLASSIC = {"REEL_BG_CLIPS": "6", "REEL_HOOK_SOUND": "0", "REEL_SFX": "0",
           "DRY_RUN": "1", "REEL_TODAY": "2026-11-13", "REEL_IMAGE_BG": "0"}
CASES = {"live_edit": (LIVE_EDIT, True), "classic": (CLASSIC, False)}
CLEAR = ("REEL_PICTURE", "REEL_EDIT_LOOK", "REEL_TYPE", "REEL_GRADE_VARIANT",
         "REEL_BG_SECONDS", "REEL_BG_OFFSET", "REEL_STYLE", "REEL_CAPTIONS",
         "REEL_MOTION", "REEL_ATMOSPHERE", "REEL_ENHANCE")


def _timings():
    out, t = [], 1.2
    for w in (HOOK + " " + QUOTE).split():
        out.append((w, round(t, 2), round(t + 0.3, 2)))
        t += 0.34
    return out


def capture(render_mod, tmp: Path, case: str) -> list[str]:
    env, generated = CASES[case]
    saved = {k: os.environ.get(k) for k in list(env) + list(CLEAR)}
    try:
        for k in CLEAR:
            os.environ.pop(k, None)
        os.environ.update(env)
        render_mod = importlib.reload(render_mod)
        import imagegen
        clips = [tmp / f"in{i}.mp4" for i in range(16)]
        seen: list[list[str]] = []

        def fake_run(cmd, **kw):
            seen.append([str(c) for c in cmd])
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        patches = [(render_mod, "fetch_background", lambda theme, p, clip_idx=0: clips[clip_idx]),
                   (render_mod, "_audio_duration", lambda p: 9.0),
                   (render_mod.proc, "run", fake_run),
                   (imagegen, "enabled", lambda: generated)]
        old = [(o, n, getattr(o, n)) for o, n, _ in patches]
        for o, n, v in patches:
            setattr(o, n, v)
        try:
            render_mod.render_reel(quote=QUOTE, author="Epictetus", audio_path=tmp / "v.mp3",
                                   out_path=tmp / "out.mp4", theme="control",
                                   word_timings=_timings(), hook=HOOK, callout_words=[],
                                   music_path=None)
        finally:
            for o, n, v in old:
                setattr(o, n, v)
        final = next(c for c in seen if "-filter_complex" in c)
        return normalise(final, tmp, render_mod)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def normalise(cmd: list[str], tmp: Path, render_mod) -> list[str]:
    reps = [(str(tmp), "<TMP>"), (str(ROOT), "<ROOT>")]
    for f in (getattr(render_mod, "FONT", ""), getattr(render_mod, "QUOTE_FONT", "")):
        if f:
            reps.append((str(f), "<FONT>"))
    out = []
    for c in cmd:
        for a, b in reps:
            c = c.replace(a, b)
        out.append(c)
    return out


def _load_render_from(source: Path):
    """render.py from another file, as module `render` (its helpers import it)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("render", source)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render"] = mod
    spec.loader.exec_module(mod)
    return mod


def write_golden(render_source: Path) -> None:
    import tempfile
    sys.path.insert(0, str(ROOT / "src"))
    mod = _load_render_from(render_source)
    GOLDEN.mkdir(exist_ok=True)
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            cmd = capture(mod, Path(d), case)
        (GOLDEN / f"render_cmd_{case}.json").write_text(json.dumps(cmd, indent=0) + "\n")
        print(f"wrote golden {case}: {len(cmd)} args")


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "golden":
    write_golden(Path(sys.argv[2]))
