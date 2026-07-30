"""
One-off benchmark: can Chatterbox TTS run self-hosted on a GitHub Actions
CPU runner fast enough to voice our Shorts for free?

Measures, separately: model load (incl. first-time weight download), then
synthesis of a realistic ~45-word Stoic voiceover. Prints a realtime factor and
a clear VERDICT so the decision is a number, not a guess.

Writes the audio to bench_chatterbox.wav so it can be uploaded as a workflow
artifact and actually listened to — quality matters as much as speed.

Run: python scripts/bench_chatterbox.py
"""
import os
import sys
import time
from pathlib import Path

# Same calm/deliberate settings the pipeline uses for Chatterbox.
EXAGGERATION = float(os.environ.get("CHATTERBOX_EXAGGERATION", "0.45"))
CFG_WEIGHT = float(os.environ.get("CHATTERBOX_CFG_WEIGHT", "0.35"))

# A real script in the channel's voice — "letter" format, ~45 words, which is
# what an actual post asks the model to speak.
TEXT = (
    "You reopened the app again tonight. Nothing changed except the hour. "
    "Epictetus knew that ceiling too. It is not events that disturb you, but "
    "your judgments about them. Put it down. Tomorrow is lighter than tonight "
    "makes it look."
)

# Our pipeline runs 3 posts/day; a run is only viable if synthesis is
# comfortably under a couple of minutes.
ACCEPTABLE_SECONDS = float(os.environ.get("BENCH_ACCEPTABLE_SECONDS", "120"))


def main() -> int:
    print("=" * 64)
    print("CHATTERBOX CPU BENCHMARK — GitHub Actions runner")
    print("=" * 64)

    import torch
    print(f"torch {torch.__version__} | cuda available: {torch.cuda.is_available()} "
          f"| threads: {torch.get_num_threads()}")
    if torch.cuda.is_available():
        print("NOTE: a GPU was detected — timings will NOT represent the normal runner.")

    t0 = time.time()
    from chatterbox.tts import ChatterboxTTS
    t_import = time.time() - t0
    print(f"[1] import                {t_import:7.1f}s")

    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device="cpu")
    t_load = time.time() - t0
    print(f"[2] load + weights        {t_load:7.1f}s  (first run downloads ~2GB)")

    words = len(TEXT.split())
    print(f"    script: {words} words / {len(TEXT)} chars, "
          f"exaggeration={EXAGGERATION} cfg_weight={CFG_WEIGHT}")

    t0 = time.time()
    wav = model.generate(TEXT, exaggeration=EXAGGERATION, cfg_weight=CFG_WEIGHT)
    t_gen = time.time() - t0

    audio_s = wav.shape[-1] / model.sr
    rtf = t_gen / audio_s if audio_s else float("inf")
    print(f"[3] SYNTHESIS             {t_gen:7.1f}s  ->  {audio_s:.1f}s of audio")
    print(f"    realtime factor       {rtf:7.2f}x  "
          f"({'faster' if rtf < 1 else 'slower'} than realtime)")

    import torchaudio
    out = Path("bench_chatterbox.wav")
    torchaudio.save(str(out), wav, model.sr)
    print(f"[4] wrote {out} ({out.stat().st_size // 1024} KB @ {model.sr} Hz)")

    # Per-post cost in a real run: weights are cached after the first run, so
    # synthesis time is what recurs.
    print("-" * 64)
    print(f"PER-POST COST (weights cached): ~{t_gen:.0f}s")
    print(f"AT 3 POSTS/DAY:                 ~{t_gen * 3 / 60:.1f} min/day of CI time")
    verdict = "PASS" if t_gen <= ACCEPTABLE_SECONDS else "TOO SLOW"
    print(f"VERDICT: {verdict}  (threshold {ACCEPTABLE_SECONDS:.0f}s per post)")
    print("=" * 64)
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"BENCHMARK FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
