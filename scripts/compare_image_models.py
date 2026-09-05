#!/usr/bin/env python3
"""
Render the same shot on two Cloudflare image models and put them side by side.

WHY: the channel shipped AI backgrounds in August and a real published frame
turned out to be a MELTED marble bust with garbled pseudo-text ("Pomice
Frausteumer") on the plinth. That was `flux-1-schnell`. Cloudflare now serves
FLUX.2 on the same free tier — `flux-2-dev`, `flux-2-klein-9b`,
`flux-2-klein-4b` — so the question of whether generated stills are usable is
worth re-asking with a model two generations newer, at no cost.

It generates from the REAL shot lists in data/stories.json, not from demo
prompts, because the open question is specifically whether these models can
produce shots a stock library cannot: "a full glass of water trembling on a
table", "an empty rocking chair moving slightly in a still room".

    python scripts/compare_image_models.py --story serenus_not_ill
    python scripts/compare_image_models.py --models flux-1-schnell,flux-2-klein-9b

Writes PNGs to samples/model_compare/ and prints a contact sheet path.
Needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN, so it runs in CI.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import stories  # noqa: E402
import imagegen  # noqa: E402

OUT = ROOT / "samples" / "model_compare"
DEFAULT_MODELS = [
    "@cf/black-forest-labs/flux-1-schnell",     # what shipped the melted bust
    "@cf/black-forest-labs/flux-2-klein-9b",    # fast, distilled, newer
    "@cf/black-forest-labs/flux-2-dev",         # highest quality on the tier
]


def generate(model: str, prompt: str, out_png: Path) -> bool:
    """Generate one image on a named model. Never raises."""
    prev = imagegen.CF_MODEL
    try:
        imagegen.CF_MODEL = model
        data = imagegen._generate_image_cloudflare(prompt, out_png)
        return bool(data) and out_png.exists() and out_png.stat().st_size > 1000
    except Exception as e:  # noqa: BLE001
        print(f"    {model.split('/')[-1]}: FAILED {e}", file=sys.stderr)
        return False
    finally:
        imagegen.CF_MODEL = prev


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--story", default="serenus_not_ill")
    ap.add_argument("--models", help="comma-separated model ids or short names")
    ap.add_argument("--shots", type=int, default=2, help="shots from the story")
    args = ap.parse_args()

    if not imagegen.cloudflare_ready():
        print("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set — "
              "this must run in CI where the secrets exist.", file=sys.stderr)
        return 0

    models = DEFAULT_MODELS
    if args.models:
        models = [m if m.startswith("@cf/") else f"@cf/black-forest-labs/{m}"
                  for m in args.models.split(",")]

    bank = {s["id"]: s for s in stories.load()}
    story = bank.get(args.story)
    if not story:
        print(f"no story {args.story!r}", file=sys.stderr)
        return 1
    shots = story["broll"][:args.shots]

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"=== {args.story}: {len(shots)} shot(s) x {len(models)} model(s) ===")
    made: list[Path] = []
    for si, shot in enumerate(shots):
        print(f"\n  shot {si + 1}: {shot}")
        for model in models:
            short = model.split("/")[-1]
            png = OUT / f"{args.story}_s{si + 1}_{short}.png"
            ok = generate(model, shot, png)
            print(f"    {short:22s} {'ok  ' + str(png.name) if ok else 'FAILED'}")
            if ok:
                made.append(png)

    if len(made) > 1:
        sheet = OUT / f"{args.story}_compare.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y"]
            + sum([["-i", str(p)] for p in made], [])
            + ["-filter_complex",
               f"{''.join(f'[{i}:v]scale=540:-1[v{i}];' for i in range(len(made)))}"
               f"{''.join(f'[v{i}]' for i in range(len(made)))}"
               f"hstack=inputs={len(made)}",
               str(sheet)],
            capture_output=True)
        if sheet.exists():
            print(f"\ncontact sheet: {sheet}")
    print(f"\n{len(made)}/{len(shots) * len(models)} generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
