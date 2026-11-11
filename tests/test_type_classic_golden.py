"""The classic type must render EXACTLY as before REEL_TYPE existed.

Owner's rule for the crew (2026-11-10, "Deploy agents to design higher quality
videos"): nothing ships until he picks, so every change sits behind a flag
that defaults OFF, and with the flag off the current video renders exactly as
now. Callimachus's flag is REEL_TYPE ("" or "classic" = today's type, "v2" =
the new type system in src/edit_type.py).

This test pins the classic path byte for byte: the full ffmpeg command
render_reel builds (inputs, the whole filter graph, the encode), the .ass
subtitle file it writes, the thumbnail command, and _build_ass on its own,
for a story-style render and for the live edit format's style pack. The
fixture (tests/fixtures/type_classic.json) was captured from src/render.py
BEFORE the REEL_TYPE code was added.

If a deliberate change to the classic look is ever approved, regenerate it:
    WRITE_TYPE_GOLDEN=1 python3 -m pytest -q tests/test_type_classic_golden.py
and say so in the commit.
"""
import importlib
import json
import os
import sys
import datetime as dt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = ROOT / "tests" / "fixtures" / "type_classic.json"

# The live edit format's style pack as of 2026-11-10 (scripts/daily_post.py,
# STYLE_PACKS["edit"]) plus what daily_post adds per post: 8 shots, the
# spoken quote and the moment it starts. A snapshot, not an import: the pack
# may grow new keys (REEL_TYPE among them); this pins today's look.
EDIT_PACK = {
    "REEL_HOOK_CAPS": "1", "REEL_HOOK_WRAP": "16", "REEL_HOOK_SOUND": "0",
    "REEL_FRAME": "0", "REEL_CINEMATIC": "0", "REEL_EXTRA_DARKEN": "0",
    "REEL_BRIGHTNESS": "-0.02", "REEL_MONO": "1", "MUSIC_VOLUME": "0.38",
    "REEL_IMAGE_TAGGED_ONLY": "1", "REEL_HOOK_ASS_FONTSIZE": "96",
    "REEL_HOOK_FROM_START": "1", "REEL_QUOTE_ASS_FS": "84",
    "REEL_KLING_BG": "0", "REEL_TAIL": "2.0", "REEL_BG_STRICT": "1",
    "REEL_SFX": "0", "REEL_BG_CLIPS": "8",
    "REEL_QUOTE_APPEAR": "3.10", "REEL_QUOTE_SPOKEN": "1",
}

HOOK = "Winning right now? Hold it loosely."
QUOTE = "Receive wealth or prosperity without arrogance; and be ready to let it go."
AUTHOR = "Marcus Aurelius"


def _timings():
    """Edit narration: 1.2s lead-in, the hook, a breath, then the quote."""
    wt, t = [], 1.2
    for w in HOOK.split():
        wt.append((w, round(t, 3), round(t + 0.26, 3)))
        t += 0.30
    t += 0.7
    for w in QUOTE.split():
        wt.append((w, round(t, 3), round(t + 0.28, 3)))
        t += 0.33
    return wt


def _story_timings():
    words = ("Two thousand years ago a man wrote his friend a letter. "
             "He said the same thing you feel tonight.").split()
    return [(w, round(0.3 + i * 0.36, 3), round(0.6 + i * 0.36, 3))
            for i, w in enumerate(words)]


@pytest.fixture(autouse=True)
def _render_reset(monkeypatch):
    """Put the environment back and reload render, so the edit pack's module
    constants loaded here never leak into the next test file."""
    yield
    monkeypatch.undo()
    import render
    importlib.reload(render)


def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("REEL_") or k in ("MUSIC_VOLUME", "IMAGE_BG", "DRY_RUN"):
            monkeypatch.delenv(k, raising=False)


def _patch(render, monkeypatch, calls):
    monkeypatch.setattr(render, "_air_day", lambda: dt.date(2026, 11, 11))
    monkeypatch.setattr(render, "_generated_backgrounds_active", lambda: False)
    monkeypatch.setattr(render, "fetch_background",
                        lambda theme, path, clip_idx=0: Path(path))
    monkeypatch.setattr(render, "_audio_duration",
                        lambda p: 9.0 if str(p).endswith((".mp3", ".m4a", ".wav")) else 30.0)

    class _Done:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, **kw):
        calls.append([str(c) for c in cmd])
        return _Done()
    monkeypatch.setattr(render.proc, "run", fake_run)


def snapshot(tmp_path, monkeypatch, reel_type=None) -> dict:
    """Every classic-path output, with machine-specific paths normalised.
    reel_type: None leaves REEL_TYPE unset; a string sets it."""
    _clean_env(monkeypatch)
    if reel_type is not None:
        monkeypatch.setenv("REEL_TYPE", reel_type)
    import render
    importlib.reload(render)
    out: dict = {}

    def norm(s: str) -> str:
        return s.replace(str(tmp_path), "<TMP>").replace(render.QUOTE_FONT, "<QUOTE_FONT>")

    # 1. A story-style render with the module defaults (no style pack).
    calls: list = []
    _patch(render, monkeypatch, calls)
    d1 = tmp_path / "story"
    d1.mkdir()
    render.render_reel(quote="The impediment to action advances action.",
                       author=AUTHOR, audio_path=d1 / "voice.mp3",
                       out_path=d1 / "reel.mp4", theme="discipline",
                       word_timings=_story_timings(),
                       hook="Two thousand years ago a man wrote his friend a letter.",
                       callout_words=[], music_path=None, mission="")
    out["story_cmds"] = [norm(" ".join(c)) for c in calls]
    ass = d1 / "reel.captions.ass"
    out["story_ass"] = ass.read_text(encoding="utf-8") if ass.exists() else ""

    # 2. The live edit format: its style pack, spoken quote, 8 shots.
    for k, v in EDIT_PACK.items():
        monkeypatch.setenv(k, v)
    importlib.reload(render)
    calls = []
    _patch(render, monkeypatch, calls)
    d2 = tmp_path / "edit"
    d2.mkdir()
    render.render_reel(quote=QUOTE, author=AUTHOR, audio_path=d2 / "voice.mp3",
                       out_path=d2 / "reel.mp4", theme="desire",
                       word_timings=_timings(), hook=HOOK, callout_words=[],
                       music_path=None, mission="")
    out["edit_cmds"] = [norm(" ".join(c)) for c in calls]
    out["edit_ass"] = (d2 / "reel.captions.ass").read_text(encoding="utf-8")

    # 3. The thumbnail, as daily_post makes it after an edit render.
    calls = []
    _patch(render, monkeypatch, calls)
    render.generate_thumbnail(hook=HOOK, author=AUTHOR, bg_path=d2 / "reel.bg.mp4",
                              out_path=d2 / "reel.thumb.jpg")
    out["thumb_cmds"] = [norm(" ".join(c)) for c in calls]

    # 4. _build_ass on its own: captions only, hook + captions, the spoken
    #    quote, and the caption_only style.
    wt = _story_timings()
    out["ass_captions"] = render._build_ass(wt, tmp_path / "a.ass").read_text(encoding="utf-8")
    hook = "Two thousand years ago"
    starts = render._hook_word_times(hook, wt)
    out["ass_hook"] = render._build_ass(wt, tmp_path / "b.ass", hook=hook, hook_starts=starts,
                                        hook_hold=2.0, captions_from=2.0).read_text(encoding="utf-8")
    et = _timings()
    qt = render._phrase_times(QUOTE, et, 3.1)
    out["ass_quote"] = render._build_ass(et[6:], tmp_path / "c.ass", quote=QUOTE, author=AUTHOR,
                                         quote_times=qt, quote_hide=qt[-1][1] + 1.0
                                         ).read_text(encoding="utf-8")
    monkeypatch.setenv("REEL_STYLE", "caption_only")
    importlib.reload(render)
    out["ass_caption_only"] = render._build_ass(wt, tmp_path / "d.ass").read_text(encoding="utf-8")
    return out


def test_classic_type_is_byte_identical(tmp_path, monkeypatch):
    got = snapshot(tmp_path, monkeypatch)
    if os.environ.get("WRITE_TYPE_GOLDEN") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.skip("golden fixture written")
    want = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert sorted(got) == sorted(want)
    for key in want:
        assert got[key] == want[key], f"classic output changed: {key}"


def test_classic_type_is_also_what_an_explicit_classic_flag_renders(tmp_path, monkeypatch):
    """REEL_TYPE=classic and an empty REEL_TYPE are the same look as unset."""
    want = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for i, value in enumerate(("classic", "", " Classic ")):
        sub = tmp_path / f"run{i}"
        sub.mkdir()
        got = snapshot(sub, monkeypatch, reel_type=value)
        for key in want:
            assert got[key] == want[key], f"REEL_TYPE={value!r} changed {key}"
