"""
Download fresh background videos and grow assets/backgrounds/.

Sources tried in order: Pexels (page 2+), Pixabay.
Deduplicates via SHA-256 of first 1 MB — won't re-download a file already present.
Run weekly via refresh-assets.yml; safe to run manually at any time.
"""
import hashlib
import os
import sys
from pathlib import Path
from datetime import date

import requests

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "backgrounds"
sys.path.insert(0, str(ROOT / "src"))

from backgrounds import THEME_QUERIES, DEFAULT_QUERY  # noqa: E402

TARGET = 5   # new videos to download per run
QUERIES = [q for _, q in THEME_QUERIES] + [
    DEFAULT_QUERY,
    "forest mist fog",
    "mountain fog clouds",
    "ocean waves sunset",
    "ancient ruins stone",
    "candle flame fire",
    "rain window dark",
    "desert sand dunes",
    "waterfall rocks nature",
    "snow winter cold",
]


def _sha256_mb(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()


def _known_hashes() -> set:
    return {_sha256_mb(p) for p in BG_DIR.glob("*.mp4")}


def _stream_save(url: str, path: Path) -> bool:
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
        return path.stat().st_size > 100_000
    except Exception as e:
        print(f"    download error: {e}", file=sys.stderr)
        path.unlink(missing_ok=True)
        return False


def from_pexels(queries: list, known: set, limit: int) -> int:
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        print("  [pexels] PEXELS_API_KEY not set — skipping")
        return 0

    n = 0
    # Start at page 2 so we don't re-fetch what the daily pipeline already gets
    for page in (2, 3, 4):
        if n >= limit:
            break
        for query in queries:
            if n >= limit:
                break
            try:
                resp = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": key},
                    params={"query": query, "orientation": "portrait",
                            "per_page": 80, "page": page},
                    timeout=30,
                )
                resp.raise_for_status()
                for vid in resp.json().get("videos", []):
                    if n >= limit:
                        break
                    files = [
                        f for f in vid.get("video_files", [])
                        if f.get("file_type") == "video/mp4"
                        and (f.get("height", 0) >= f.get("width", 0))
                    ]
                    if not files:
                        continue
                    files.sort(key=lambda f: abs((f.get("height") or 0) - 1920))
                    link = files[0]["link"]
                    name = f"pexels_{vid['id']}.mp4"
                    dest = BG_DIR / name
                    if dest.exists():
                        continue
                    tmp = BG_DIR / f"_tmp_{name}"
                    if not _stream_save(link, tmp):
                        continue
                    h = _sha256_mb(tmp)
                    if h in known:
                        tmp.unlink()
                        continue
                    tmp.rename(dest)
                    known.add(h)
                    n += 1
                    print(f"  [pexels] +{name}")
            except Exception as e:
                print(f"  [pexels] {query!r} page {page}: {e}", file=sys.stderr)
    return n


def from_pixabay(queries: list, known: set, limit: int) -> int:
    key = os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        print("  [pixabay] PIXABAY_API_KEY not set — skipping")
        return 0

    n = 0
    for query in queries:
        if n >= limit:
            break
        try:
            resp = requests.get(
                "https://pixabay.com/api/videos/",
                params={"key": key, "q": query, "per_page": 20, "order": "popular"},
                timeout=30,
            )
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                if n >= limit:
                    break
                vid_id = hit.get("id")
                url = None
                for size in ("large", "medium"):
                    v = hit.get("videos", {}).get(size, {})
                    if v.get("url") and v.get("height", 0) >= v.get("width", 1):
                        url = v["url"]
                        break
                if not url:
                    continue
                name = f"pixabay_{vid_id}.mp4"
                dest = BG_DIR / name
                if dest.exists():
                    continue
                tmp = BG_DIR / f"_tmp_{name}"
                if not _stream_save(url, tmp):
                    continue
                h = _sha256_mb(tmp)
                if h in known:
                    tmp.unlink()
                    continue
                tmp.rename(dest)
                known.add(h)
                n += 1
                print(f"  [pixabay] +{name}")
        except Exception as e:
            print(f"  [pixabay] {query!r}: {e}", file=sys.stderr)
    return n


def main():
    BG_DIR.mkdir(parents=True, exist_ok=True)
    before = len(list(BG_DIR.glob("*.mp4")))
    print(f"[refresh_backgrounds] library before: {before} videos")

    known = _known_hashes()

    n = from_pixabay(QUERIES, known, TARGET)
    remaining = TARGET - n
    if remaining > 0:
        n += from_pexels(QUERIES, known, remaining)

    after = len(list(BG_DIR.glob("*.mp4")))
    print(f"[refresh_backgrounds] added {n} new videos; library now: {after}")


if __name__ == "__main__":
    main()
