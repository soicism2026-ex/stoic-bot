#!/usr/bin/env bash
# ffmpeg + fonts for the renderer, robust to a stalled Ubuntu package mirror.
#
# 2026-10-22: `apt-get` hung for the whole 60-minute job limit on the 15:00 UTC
# run, then stalled again on the re-run, and no post could render without
# ffmpeg. The order is now:
#   1. apt, time-boxed (90 s update, 180 s install), one try;
#   2. a static ffmpeg build: BtbN on GitHub's CDN (libass, freetype and
#      fontconfig built in), then johnvansickle.com, both independent of the
#      Ubuntu mirrors;
#   3. apt once more, in case the mirror came back.
# Fonts: the runner image already ships DejaVu and Liberation (its Chrome
# depends on them), so a failed apt still leaves the renderer's fonts; the end
# of this script checks and warns.
set -uo pipefail

have_ffmpeg() { command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; }

try_apt() {
  timeout 90 sudo apt-get update -o Acquire::Retries=2 -o Acquire::http::Timeout=20 \
    && timeout 180 sudo apt-get install -y --no-install-recommends ffmpeg fonts-dejavu fonts-liberation
}

try_static() {
  local tmp="${RUNNER_TEMP:-/tmp}/ffstatic" url bin
  for url in \
    https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux64-gpl-7.1.tar.xz \
    https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
    https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz; do
    echo "trying a static ffmpeg build: $url"
    rm -rf "$tmp" && mkdir -p "$tmp"
    if timeout 180 curl -fsSL --retry 2 -o "$tmp/ff.tar.xz" "$url" \
        && timeout 120 tar -xJf "$tmp/ff.tar.xz" -C "$tmp"; then
      bin="$(dirname "$(find "$tmp" -type f -name ffmpeg | head -1)")"
      if [ -x "$bin/ffmpeg" ] && [ -x "$bin/ffprobe" ] \
          && sudo cp "$bin/ffmpeg" "$bin/ffprobe" /usr/local/bin/; then
        return 0
      fi
    fi
  done
  return 1
}

try_apt || echo "apt failed or stalled: falling back to a static build"
have_ffmpeg || try_static || echo "every static build failed"
have_ffmpeg || try_apt || true

if ! have_ffmpeg; then
  echo "::error::no ffmpeg: apt and every static build failed"
  exit 1
fi
ffmpeg -hide_banner -version | head -1
ffmpeg -hide_banner -filters 2>/dev/null | grep -qE '^ ... (subtitles|ass) ' \
  || echo "::warning::this ffmpeg has no libass, so captions and karaoke text will fail"
[ -f /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf ] \
  || echo "::warning::DejaVu Sans Bold is missing; text falls back to another font"
exit 0
