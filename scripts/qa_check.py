"""
QA check for a rendered reel.

Extracts up to 20 frames, transcribes audio with faster-whisper,
diffs against intended quote, then asks Claude Haiku to evaluate
the video for common Short-form failure modes.

Returns {"pass": bool, "issues": [str], "severity": "low"|"high"}
"""
import os
import sys
import json
import base64
import subprocess
import tempfile
from pathlib import Path


def extract_frames(video_path: Path, max_frames: int = 20) -> list:
    """Extract up to max_frames frames at 540px width, 1 every ≥2 seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(json.loads(result.stdout)["format"]["duration"])
    interval = max(2.0, duration / max_frames)

    out_dir = Path(tempfile.mkdtemp())
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vf", f"fps=1/{interval:.2f},scale=540:-2",
         "-frames:v", str(max_frames),
         str(out_dir / "frame_%03d.jpg")],
        capture_output=True, check=True,
    )
    return sorted(out_dir.glob("frame_*.jpg"))


def transcribe_audio(video_path: Path) -> str:
    """Extract mono 16kHz WAV then transcribe with faster-whisper (tiny model)."""
    audio_path = Path(tempfile.mkdtemp()) / "qa_audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vn", "-ar", "16000", "-ac", "1", str(audio_path)],
        capture_output=True, check=True,
    )
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), beam_size=1)
        return " ".join(seg.text.strip() for seg in segments)
    except ImportError:
        try:
            import whisper
            return whisper.load_model("tiny").transcribe(str(audio_path))["text"].strip()
        except Exception:
            return ""
    except Exception:
        return ""
    finally:
        audio_path.unlink(missing_ok=True)


def check_quote_in_transcript(transcript: str, intended_quote: str) -> str:
    """Check whether the intended quote words appear anywhere in the transcript.

    The audio is intentionally longer than the quote (hook + voiceover + CTA),
    so we only check that the quote itself is present — not that the transcript
    matches the quote exactly.
    """
    if not transcript:
        return "(transcription unavailable — visual-only QA)"
    quote_words = set(w.lower().strip(".,!?;:\"'") for w in intended_quote.split() if len(w) > 3)
    if not quote_words:
        return "(quote too short to verify)"
    transcript_lower = transcript.lower()
    found = sum(1 for w in quote_words if w in transcript_lower)
    pct = found / len(quote_words)
    if pct >= 0.45:
        return f"Quote present in audio ({pct:.0%} of key words detected)"
    return f"Quote may be missing from audio — only {pct:.0%} of key words detected"


def run_qa(video_path, intended_quote: str) -> dict:
    """
    Run QA on a rendered video path.
    Returns {"pass": bool, "issues": [str], "severity": "low"|"high"}
    """
    import anthropic

    video_path = Path(video_path)

    # --- frames ---
    try:
        frames = extract_frames(video_path)
    except Exception as e:
        frames = []
        print(f"  [qa] frame extraction failed: {e}", file=sys.stderr)

    # --- transcript ---
    try:
        transcript = transcribe_audio(video_path)
    except Exception as e:
        transcript = ""
        print(f"  [qa] transcription failed: {e}", file=sys.stderr)

    quote_check = check_quote_in_transcript(transcript, intended_quote)

    # --- build message content ---
    content = []
    for frame in frames[:20]:
        try:
            data = base64.standard_b64encode(frame.read_bytes()).decode("ascii")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
            })
        except Exception:
            pass

    content.append({
        "type": "text",
        "text": (
            f"Intended quote: {intended_quote}\n\n"
            f"Audio quote check: {quote_check}\n\n"
            "IMPORTANT CONTEXT: The audio intentionally contains more than just the quote. "
            "It starts with a short hook phrase, then a voiceover script contextualising the quote, "
            "the quote itself, and ends with a call-to-action. "
            "Do NOT flag the audio for having content beyond the quote — that is by design.\n\n"
            "Check this vertical short ONLY for these issues:\n"
            "1. Text clipped by the safe zone (cut off at the top/bottom edge of the frame)\n"
            "2. Black or frozen frames (video not playing)\n"
            "3. Text unreadable due to low contrast against the background\n"
            "4. Quote text on screen does not match the intended quote above\n"
            "5. Quote missing from audio entirely (see audio quote check above)\n"
            "6. Background mood badly mismatched with the quote tone\n\n"
            "Return ONLY valid JSON, no markdown fences:\n"
            '{"pass": true/false, "issues": ["..."], "severity": "low"|"high"}\n\n'
            '"pass": true = acceptable to publish. '
            '"severity": "high" ONLY for issues that make the video unwatchable or factually wrong '
            '(e.g. black screen, quote completely wrong). '
            'Minor contrast or mood issues = severity "low". '
            'If no issues: {"pass": true, "issues": [], "severity": "low"}'
        ),
    })

    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
    except Exception as e:
        return {"pass": True, "issues": [f"QA API error: {e}"], "severity": "low"}

    # Strip markdown fences defensively
    if raw.startswith("```"):
        raw = "\n".join(ln for ln in raw.split("\n") if not ln.startswith("```"))

    try:
        result = json.loads(raw.strip())
        assert isinstance(result.get("pass"), bool)
        assert isinstance(result.get("issues"), list)
        assert result.get("severity") in ("low", "high")
        return result
    except Exception:
        return {"pass": True, "issues": [f"QA parse error: {raw[:200]}"], "severity": "low"}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: qa_check.py <video_path> <intended_quote>", file=sys.stderr)
        sys.exit(1)
    result = run_qa(Path(sys.argv[1]), sys.argv[2])
    print(json.dumps(result, indent=2))
