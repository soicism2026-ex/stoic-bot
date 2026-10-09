"""
Make original music for stoic edits, free, with ACE-Step 1.5 on a plain CPU.

Owner, 2026-10-08: "we have to find a way to use them royalty free versions"
(Hans Zimmer, Me and the Devil, L'Amour Toujours, ...). No royalty-free
version of a copyrighted song exists, so this makes ORIGINAL tracks in the
same style instead, which the channel owns outright (see src/edit_music.py).

    setup     build acestep.cpp at a pinned commit and download the models
    generate  one style from data/edit_music_styles.json -> mp3 + entry JSON
    add       an already-generated wav -> mp3 + entry JSON
    merge     entry JSONs + mp3s -> assets/music/edit/ + data/edit_music.json

Rules every track follows (tests/test_edit_music.py checks the bank):
  * the prompt describes the STYLE only (instruments, tempo, key, mood): no
    song titles, no artist names;
  * "[Instrumental]": no lyrics, no vocals;
  * no reference audio and no source audio: nothing copyrighted goes in;
  * provenance (model, prompt, seeds, date) is recorded with the track;
  * every new track is "approved": false. Only the owner approves.

ACE-Step 1.5 is MIT-licensed and its makers allow commercial use of the
output; it was trained on licensed and royalty-free music. acestep.cpp
(MIT) is a C++ build of it that runs on an ordinary CPU.
"""
from __future__ import annotations

import argparse
import array
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "edit_music.json"
STYLES = ROOT / "data" / "edit_music_styles.json"
OUT_DIR = ROOT / "assets" / "music" / "edit"

ACE_REPO = "https://github.com/ServeurpersoCom/acestep.cpp"
ACE_COMMIT = "d881ad2c080bac65cc73cb3bbcc831f79462b98b"   # pinned, reviewed
HF_MODELS = "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/main/"
DIT = {"standard": "acestep-v15-turbo-Q8_0.gguf", "xl": "acestep-v15-xl-turbo-Q8_0.gguf"}
LM = "acestep-5Hz-lm-1.7B-Q8_0.gguf"
COMMON = ["Qwen3-Embedding-0.6B-Q8_0.gguf", "vae-BF16.gguf", LM]

TARGET_LUFS = -16.0
LEAD = 1.5          # seconds of build before the drop
SECTION = 16.0      # an edit uses at most ~16s of music
HOP = 0.5


# ----------------------------------------------------------------- setup ---

def _run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def setup(work: Path, size: str) -> None:
    src = work / "acestep.cpp"
    if not (src / ".git").exists():
        _run(["git", "clone", "-q", ACE_REPO, str(src)])
    _run(["git", "-C", str(src), "checkout", "-q", ACE_COMMIT])
    _run(["git", "-C", str(src), "submodule", "update", "-q", "--init", "--recursive"])
    # The build assumes hyperthreading and uses half the logical CPUs. Allow
    # ACE_THREADS to override (a 4-core VM without SMT ran at half speed).
    h = src / "src" / "backend.h"
    t = h.read_text()
    if "ACE_THREADS" not in t:
        t = t.replace(
            "static int backend_cpu_n_threads(void) {\n",
            "static int backend_cpu_n_threads(void) {\n"
            "    if (const char * e = std::getenv(\"ACE_THREADS\")) {\n"
            "        int t = std::atoi(e);\n"
            "        if (t > 0) return t;\n"
            "    }\n", 1)
        h.write_text("#include <cstdlib>\n" + t)
    build = src / "build"
    if not (build / "ace-synth").exists():
        build.mkdir(exist_ok=True)
        _run(["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"], cwd=build,
             stdout=subprocess.DEVNULL)
        _run(["cmake", "--build", ".", "--config", "Release", "-j", str(os.cpu_count() or 2),
              "--target", "ace-lm", "ace-synth"], cwd=build, stdout=subprocess.DEVNULL)
    models = work / "models"
    models.mkdir(exist_ok=True)
    for f in COMMON + [DIT[size]]:
        if (models / f).exists():
            continue
        part = models / (f + ".part")
        for attempt in range(6):
            r = subprocess.run(["curl", "-sSL", "-C", "-", "--retry", "5", "--retry-all-errors",
                                "-o", str(part), HF_MODELS + f])
            if r.returncode == 0:
                break
            time.sleep(3 * (attempt + 1))
        part.rename(models / f)
        print(f"model {f}: {(models / f).stat().st_size // 2**20} MB", flush=True)


# -------------------------------------------------------------- generate ---

def generate(work: Path, style_id: str, seconds: float, size: str, out: Path,
             tag: str = "") -> Path:
    style = next(s for s in json.loads(STYLES.read_text()) if s["id"] == style_id)
    job = out / f"{style_id}{tag}"
    job.mkdir(parents=True, exist_ok=True)
    req = {"lm_model": LM, "synth_model": DIT[size], "caption": style["caption"],
           "lyrics": "[Instrumental]", "bpm": style["bpm"], "duration": seconds,
           "keyscale": style["key"], "timesignature": "4", "vocal_language": "unknown",
           "inference_steps": 8, "guidance_scale": 1.0, "shift": 3.0,
           "output_format": "wav16"}
    (job / "request.json").write_text(json.dumps(req, indent=1))
    bin_ = work / "acestep.cpp" / "build"
    models = work / "models"
    t0 = time.time()
    with open(job / "lm.log", "w") as log:
        _run([str(bin_ / "ace-lm"), "--models", str(models), "--request",
              str(job / "request.json")], stdout=log, stderr=subprocess.STDOUT)
    t1 = time.time()
    with open(job / "synth.log", "w") as log:
        _run([str(bin_ / "ace-synth"), "--models", str(models), "--request",
              str(job / "request0.json")], stdout=log, stderr=subprocess.STDOUT)
    print(f"{style_id}{tag}: composed in {t1 - t0:.0f}s, rendered in "
          f"{time.time() - t1:.0f}s", flush=True)
    return add(job / "request00.wav", job / "request0.json", f"{style_id}{tag}",
               style["label"], style["style_of"], out)


# ------------------------------------------------------------------- add ---

def integrated_lufs(path: Path, pre: str = "") -> float:
    af = f"{pre}," if pre else ""
    r = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", str(path), "-af",
                        f"{af}ebur128=framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    vals = [ln.split("I:")[1].split("LUFS")[0] for ln in r.stderr.splitlines()
            if ln.strip().startswith("I:")]
    return float(vals[-1])


def loudness_curve(path: Path, rate: int = 8000) -> list[float]:
    """RMS level in dB per HOP seconds, mono."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1",
                          "-ar", str(rate), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    hop = int(rate * HOP)
    out = []
    for i in range(len(a) // hop):
        seg = a[i * hop:(i + 1) * hop]
        ms = sum(v * v for v in seg) / len(seg) / (32768.0 ** 2)
        out.append(10 * math.log10(ms + 1e-12))
    return out


def find_start(db: list[float]) -> tuple[float, str, float]:
    """(start seconds, how, contrast dB).

    The drop is the moment that maximises
        mean(level over the next 8s) - mean(level over the previous 4s):
    where a quieter build gives way to the loudest sustained section. Under
    3 dB of contrast there is no real drop, so use the loudest 14s window.
    The edit starts LEAD seconds before it: the first picture lands on the
    build and the hook lands on the drop.
    """
    n = len(db)
    dur = n * HOP
    best_i, best_c = None, -99.0
    for i in range(8, n - 16):
        c = sum(db[i:i + 16]) / 16 - sum(db[i - 8:i]) / 8
        if c > best_c:
            best_i, best_c = i, c
    win = 28
    loud_i = max(range(max(1, n - win)), key=lambda i: sum(db[i:i + win]))
    if best_i is not None and best_c >= 3.0:
        point, how = best_i * HOP, "drop"
    else:
        point, how = loud_i * HOP, "loudest"
    start = max(0.0, min(point - LEAD, dur - SECTION))
    return round(start, 1), how, round(best_c, 1)


def add(wav: Path, request: Path, track_id: str, label: str, like: str,
        out: Path) -> Path:
    """wav -> out/<id>.mp3 (trailing silence trimmed, one constant gain to
    -16 LUFS, peak-limited) + out/<id>.json (the bank entry)."""
    req = json.loads(Path(request).read_text())
    out.mkdir(parents=True, exist_ok=True)
    mp3 = out / f"{track_id}.mp3"
    # A CONSTANT gain, never single-pass loudnorm: that is dynamic and
    # flattened the first track's build-to-drop contrast from 19.6 to 10.9
    # dB, and the drop is what the whole edit is timed to.
    trim = ("areverse,silenceremove=start_periods=1:start_threshold=-50dB:"
            "start_silence=0.3,areverse")
    gain = TARGET_LUFS - integrated_lufs(wav, trim)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af",
          f"{trim},volume={gain:.2f}dB,alimiter=limit=0.84:level=false,aresample=44100",
          "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)])
    db = loudness_curve(mp3)
    start, how, contrast = find_start(db)
    entry = {
        "id": track_id,
        "file": f"assets/music/edit/{track_id}.mp3",
        "label": label,
        "style_of": like,
        "start": start,
        "start_how": f"{how} ({contrast} dB build-to-drop contrast)",
        "duration": round(len(db) * HOP, 1),
        "approved": False,
        "provenance": {
            "model": (f"ACE-Step 1.5 via acestep.cpp {ACE_COMMIT[:7]} "
                      f"(DiT {req.get('synth_model')}, LM {req.get('lm_model')})"),
            "license": "MIT (ACE-Step 1.5; commercial use of output allowed)",
            "prompt": req.get("caption", ""),
            "lyrics": req.get("lyrics", ""),
            "bpm": req.get("bpm"),
            "key": req.get("keyscale"),
            "seconds": req.get("duration"),
            "seed": req.get("seed"),
            "lm_seed": req.get("lm_seed"),
            "reference_audio": "none",
            "generated": datetime.date.today().isoformat(),
        },
    }
    (out / f"{track_id}.json").write_text(json.dumps(entry, indent=1, ensure_ascii=False))
    print(f"{track_id}: {mp3.stat().st_size // 1024} KB, start {start}s ({how}, "
          f"{contrast} dB), {entry['duration']}s", flush=True)
    return mp3


# ----------------------------------------------------------------- merge ---

def merge(src: Path) -> int:
    """Copy every <id>.mp3 + <id>.json found under src into the bank. An
    existing track keeps its approval; a new one starts unapproved."""
    bank = json.loads(BANK.read_text()) if BANK.exists() else []
    by_id = {t["id"]: t for t in bank}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for j in sorted(src.rglob("*.json")):
        try:
            e = json.loads(j.read_text())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(e, dict) or "provenance" not in e:
            continue
        mp3 = j.with_suffix(".mp3")
        if not mp3.exists():
            continue
        shutil.copy(mp3, OUT_DIR / mp3.name)
        e["approved"] = bool(by_id.get(e["id"], {}).get("approved", False))
        by_id[e["id"]] = e
        n += 1
    BANK.write_text(json.dumps(list(by_id.values()), indent=1, ensure_ascii=False) + "\n")
    print(f"merged {n} track(s); bank has {len(by_id)}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup")
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--size", choices=sorted(DIT), default="xl")
    p = sub.add_parser("generate")
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--style", required=True)
    p.add_argument("--seconds", type=float, default=48)
    p.add_argument("--size", choices=sorted(DIT), default="xl")
    p.add_argument("--tag", default="")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("add")
    p.add_argument("--wav", type=Path, required=True)
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("merge")
    p.add_argument("--src", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "setup":
        setup(a.work, a.size)
    elif a.cmd == "generate":
        generate(a.work, a.style, a.seconds, a.size, a.out, a.tag)
    elif a.cmd == "add":
        style_id = a.id.split("__")[0]
        style = next((s for s in json.loads(STYLES.read_text()) if s["id"] == style_id), None)
        if not style:
            print(f"unknown style {style_id}", file=sys.stderr)
            return 2
        add(a.wav, a.request, a.id, style["label"], style["style_of"], a.out)
    elif a.cmd == "merge":
        merge(a.src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
