"""
Pre-upload visual QA gate using Claude Opus.

Extracts ~6 frames (4 from the hook — first 1.5 s — and 2 from the body),
then scores the video on four dimensions using Claude Opus vision:

  hook_strength         (0–10): Does the opening compel the viewer to stay?
  text_legibility       (0–10): Are all text overlays clear and readable?
  pacing                (0–10): Does visual rhythm match the audio pacing?
  scroll_stop_potential (0–10): Would a casual scroller stop on the first frame?

Verdicts
--------
  pass  — all dimension scores ≥ their pass threshold
  flag  — at least one score < pass threshold but ≥ fail threshold
           (logged; video still uploads)
  fail  — at least one score < fail threshold
           (triggers retry when VQA_BLOCK_ON_FAIL=1; default: just logged)

Thresholds are configurable via environment variables:
  VQA_HOOK_PASS, VQA_HOOK_FAIL, VQA_TEXT_PASS, VQA_TEXT_FAIL,
  VQA_PACING_PASS, VQA_PACING_FAIL, VQA_SCROLL_PASS, VQA_SCROLL_FAIL

All Claude calls use structured JSON output; parsing errors degrade to
"flag" (never "fail") so a broken API response never silently blocks uploads.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODEL = "claude-opus-4-8"

# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "hook_strength":         {"pass": 6.0, "fail": 3.0},
    "text_legibility":       {"pass": 7.0, "fail": 4.0},
    "pacing":                {"pass": 5.0, "fail": 2.0},
    "scroll_stop_potential": {"pass": 6.0, "fail": 3.0},
}

_ENV_MAP: dict[str, tuple[str, str]] = {
    "VQA_HOOK_PASS":   ("hook_strength",         "pass"),
    "VQA_HOOK_FAIL":   ("hook_strength",         "fail"),
    "VQA_TEXT_PASS":   ("text_legibility",       "pass"),
    "VQA_TEXT_FAIL":   ("text_legibility",       "fail"),
    "VQA_PACING_PASS": ("pacing",                "pass"),
    "VQA_PACING_FAIL": ("pacing",                "fail"),
    "VQA_SCROLL_PASS": ("scroll_stop_potential", "pass"),
    "VQA_SCROLL_FAIL": ("scroll_stop_potential", "fail"),
}

DIMENSIONS = list(DEFAULT_THRESHOLDS.keys())


def load_thresholds() -> dict[str, dict[str, float]]:
    """Return thresholds, overriding defaults with env vars where set."""
    t = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    for env_key, (dim, level) in _ENV_MAP.items():
        raw = os.environ.get(env_key)
        if raw:
            try:
                t[dim][level] = float(raw)
            except ValueError:
                pass
    return t


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VisualQAResult:
    verdict: str       # "pass" | "flag" | "fail"
    scores: dict       # {dimension: float}
    reasoning: str     # one-paragraph explanation from Claude
    issues: list       # [str] specific problems
    suggestions: list  # [str] actionable fixes
    hard_fails: list   # [str] dimensions below fail threshold
    flags: list        # [str] dimensions below pass but above fail


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_hook_frames(
    video_path: Path,
    n_hook: int = 4,
    n_body: int = 2,
    hook_window: float = 1.5,
) -> list[Path]:
    """
    Extract frames dense in the hook window (first hook_window seconds)
    and sparse across the body. Returns JPEG paths in chronological order.
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    out_dir = Path(tempfile.mkdtemp())
    frames: list[Path] = []

    hook_end = min(hook_window, duration - 0.05)
    for i in range(n_hook):
        ts = (i / max(n_hook - 1, 1)) * hook_end
        out_path = out_dir / f"hook_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", str(video_path),
             "-vframes", "1", "-vf", "scale=540:-2", "-q:v", "4", str(out_path)],
            capture_output=True, check=True,
        )
        if out_path.exists():
            frames.append(out_path)

    if duration > hook_window and n_body > 0:
        body_span = duration - hook_window
        for i in range(n_body):
            ts = hook_window + (i + 0.5) / n_body * body_span
            out_path = out_dir / f"body_{i:02d}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", str(video_path),
                 "-vframes", "1", "-vf", "scale=540:-2", "-q:v", "4", str(out_path)],
                capture_output=True, check=True,
            )
            if out_path.exists():
                frames.append(out_path)

    return frames


# ---------------------------------------------------------------------------
# Claude prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a YouTube Shorts performance analyst specialising in vertical-format \
philosophy and mindset content.

You receive frames from a Stoicism short in chronological order, plus the \
intended content data. The first 4 frames are from the hook window (opening \
1.5 seconds) and the last 2 are from the body.

Score on exactly four dimensions. Return ONLY valid JSON — no markdown fences, \
no commentary outside the braces.

SCORING RUBRIC

hook_strength (0–10):
  10 = First frame is visually arresting AND hook text creates immediate curiosity.
   7 = Hook is clear and decent but won't stop every scroller.
   4 = Generic; most viewers swipe past.
   0 = No hook text or completely unclear.

text_legibility (0–10):
  10 = All text overlays are crisp, high-contrast, instantly readable at phone size.
   7 = Readable but a minor contrast or font-weight issue is present.
   4 = Hard to read in some frames.
   0 = Unreadable.

pacing (0–10):
  10 = Visual rhythm and transitions feel energetic, well-matched to audio pace.
   7 = Adequate; not jarring but not exciting.
   4 = Feels static or slow.
   0 = No apparent visual pacing.

scroll_stop_potential (0–10):
  10 = Seeing frame 1 in a feed, you would DEFINITELY stop scrolling.
   7 = Probably stop — something visually interesting is there.
   4 = Might stop depending on viewer mood.
   0 = Would swipe immediately.

JSON schema (return ONLY this):
{
  "hook_strength": <float 0-10>,
  "text_legibility": <float 0-10>,
  "pacing": <float 0-10>,
  "scroll_stop_potential": <float 0-10>,
  "reasoning": "<one paragraph — briefly justify each score>",
  "issues": ["<specific issue 1>", "<specific issue 2>"],
  "suggestions": ["<concrete fix 1>", "<concrete fix 2>"]
}"""


def _build_message_content(
    frames: list[Path],
    content_data: dict,
    n_hook: int,
) -> list[dict]:
    parts: list[dict] = []
    for i, fp in enumerate(frames):
        label = "hook" if fp.name.startswith("hook_") else "body"
        b64 = base64.standard_b64encode(fp.read_bytes()).decode("ascii")
        parts.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
        parts.append({"type": "text", "text": f"[Frame {i + 1}/{len(frames)} — {label}]"})

    hook = content_data.get("hook", "")
    quote = content_data.get("quote", "")
    author = content_data.get("author", "")
    theme = content_data.get("theme", "")
    vo = content_data.get("voiceover_text", "")[:500]

    parts.append({
        "type": "text",
        "text": (
            "CONTENT DATA\n"
            f"Theme:     {theme}\n"
            f"Hook:      {hook}\n"
            f"Quote:     {quote}\n"
            f"Author:    {author}\n"
            f"Voiceover: {vo}\n\n"
            f"Frames 1–{n_hook} are from the hook (first 1.5 s). "
            f"Frames {n_hook + 1}–{len(frames)} are from the body.\n"
            "Score this video and return the JSON schema only."
        ),
    })
    return parts


# ---------------------------------------------------------------------------
# Verdict calculation
# ---------------------------------------------------------------------------

def _compute_verdict(
    scores: dict[str, float],
    thresholds: dict[str, dict[str, float]],
) -> tuple[str, list[str], list[str]]:
    """Return (verdict, hard_fails, flags)."""
    hard_fails = [d for d in DIMENSIONS if scores.get(d, 5.0) < thresholds[d]["fail"]]
    flags = [
        d for d in DIMENSIONS
        if d not in hard_fails and scores.get(d, 5.0) < thresholds[d]["pass"]
    ]
    if hard_fails:
        return "fail", hard_fails, flags
    if flags:
        return "flag", hard_fails, flags
    return "pass", hard_fails, flags


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------

def score_video(
    video_path: Path,
    content_data: dict,
    n_hook: int = 4,
    n_body: int = 2,
) -> VisualQAResult:
    """Score a rendered video using Claude Opus vision."""
    import anthropic

    thresholds = load_thresholds()

    try:
        frames = extract_hook_frames(video_path, n_hook=n_hook, n_body=n_body)
    except Exception as e:
        print(f"  [visual_qa] frame extraction failed: {e}", file=sys.stderr)
        return VisualQAResult(
            verdict="flag",
            scores={d: 5.0 for d in DIMENSIONS},
            reasoning=f"Frame extraction failed: {e}",
            issues=["frame_extraction_failed"],
            suggestions=[],
            hard_fails=[],
            flags=list(DIMENSIONS),
        )

    if not frames:
        return VisualQAResult(
            verdict="flag",
            scores={d: 5.0 for d in DIMENSIONS},
            reasoning="No frames extracted.",
            issues=["no_frames"],
            suggestions=[],
            hard_fails=[],
            flags=list(DIMENSIONS),
        )

    content_parts = _build_message_content(frames, content_data, n_hook)

    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=MODEL,
            max_tokens=900,
            system=_SYSTEM,
            messages=[{"role": "user", "content": content_parts}],
        )
        raw = response.content[0].text.strip()
    except Exception as e:
        print(f"  [visual_qa] API call failed: {e}", file=sys.stderr)
        return VisualQAResult(
            verdict="flag",
            scores={d: 5.0 for d in DIMENSIONS},
            reasoning=f"API error: {e}",
            issues=[f"api_error: {e}"],
            suggestions=[],
            hard_fails=[],
            flags=["api_unreachable"],
        )

    if raw.startswith("```"):
        raw = "\n".join(ln for ln in raw.split("\n") if not ln.startswith("```"))

    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return VisualQAResult(
            verdict="flag",
            scores={d: 5.0 for d in DIMENSIONS},
            reasoning=f"JSON parse failed: {raw[:300]}",
            issues=["json_parse_error"],
            suggestions=[],
            hard_fails=[],
            flags=["parse_failed"],
        )

    scores: dict[str, float] = {}
    for d in DIMENSIONS:
        try:
            scores[d] = float(data[d])
        except (KeyError, TypeError, ValueError):
            scores[d] = 5.0

    reasoning = str(data.get("reasoning", ""))
    issues = [str(x) for x in data.get("issues", [])]
    suggestions = [str(x) for x in data.get("suggestions", [])]

    verdict, hard_fails, flags = _compute_verdict(scores, thresholds)

    for d in hard_fails:
        t = thresholds[d]["fail"]
        issues.append(f"HARD FAIL: {d}={scores[d]:.1f} (threshold={t})")

    return VisualQAResult(
        verdict=verdict,
        scores=scores,
        reasoning=reasoning,
        issues=issues,
        suggestions=suggestions,
        hard_fails=hard_fails,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

def _append_log(log_path: Path, video_path: Path, content_data: dict, result: VisualQAResult):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    score_str = " | ".join(f"{k}={v:.1f}" for k, v in result.scores.items())
    lines = [
        f"\n## Visual QA — {ts}",
        f"**File:** `{video_path.name}` | **Verdict:** `{result.verdict.upper()}`",
        f"**Hook:** {content_data.get('hook', 'N/A')}",
        f"**Scores:** {score_str}",
        f"**Reasoning:** {result.reasoning}",
    ]
    if result.issues:
        lines.append("**Issues:**")
        lines.extend(f"- {i}" for i in result.issues)
    if result.suggestions:
        lines.append("**Suggestions:**")
        lines.extend(f"- {s}" for s in result.suggestions)
    if result.flags:
        lines.append(f"**Flagged dims:** {', '.join(result.flags)}")
    lines.append("")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_visual_qa(
    video_path,
    content_data: dict,
    log_path=None,
) -> VisualQAResult:
    """
    Run visual QA on a rendered video and append to QA_LOG.md.

    content_data should contain: hook, quote, author, theme, voiceover_text
    Returns a VisualQAResult with verdict "pass" | "flag" | "fail".
    """
    video_path = Path(video_path)
    if log_path is None:
        log_path = ROOT / "QA_LOG.md"

    result = score_video(video_path, content_data)
    try:
        _append_log(Path(log_path), video_path, content_data, result)
    except Exception as e:
        print(f"  [visual_qa] log write failed: {e}", file=sys.stderr)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run visual QA on a rendered Short")
    parser.add_argument("video", help="Path to the MP4")
    parser.add_argument("--hook", default="")
    parser.add_argument("--quote", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--theme", default="")
    args = parser.parse_args()

    result = run_visual_qa(
        Path(args.video),
        {
            "hook": args.hook,
            "quote": args.quote,
            "author": args.author,
            "theme": args.theme,
        },
    )
    print(json.dumps({
        "verdict": result.verdict,
        "scores": result.scores,
        "reasoning": result.reasoning,
        "issues": result.issues,
        "suggestions": result.suggestions,
        "hard_fails": result.hard_fails,
        "flags": result.flags,
    }, indent=2))
    sys.exit(0 if result.verdict != "fail" else 1)
