"""
Background video sourcing for the daily Short.

Source chain (first that succeeds wins):
  1. Pixabay — portrait clip, works reliably from GitHub Actions (PIXABAY_API_KEY)
  2. Pexels  — secondary source; free-tier keys may 403 from cloud IPs (PEXELS_API_KEY)
  3. Synthetic — ffmpeg lavfi dark-gradient; always available, no network needed
  4. Local rotation — assets/backgrounds/ deterministic fallback

A run never breaks: every stage catches its own errors and tries the next.
"""
import os
import subprocess
import sys
from pathlib import Path
from datetime import date

import requests

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "assets" / "backgrounds"

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

# Each theme maps to 3 query options that rotate by date (+ bg_offset).
# This means consecutive days with the same theme still get visually different
# results, and themes that previously all fell to "nature cinematic dark" now
# have their own distinctive visual identity.
# Hard Stoic symbolism, split by register:
#   MARBLE/RUINS (contemplative, timeless) — wisdom, virtue, mortality, time,
#     control, justice, friendship, impermanence
#   STORM/FORGE (intense, brooding) — resilience, anger, adversity, fear,
#     desire, ego, discipline, purpose
# Every query is dark, dramatic and classical so the gold text + grade reads.
THEME_QUERY_POOLS: dict[str, list[str]] = {
    # ---- marble & ruins register ----
    # Queries deliberately avoid terms that return human figures ("bust", "statue",
    # "figure", "warrior", "climber") — Pixabay's semantic search surfaces classical
    # reclining/standing figures for those terms. Keep to architecture, fire, nature.
    "mortality":    ["roman stone pillars dramatic shadow dark", "ancient roman ruins fog dark", "candle flame dark dramatic still"],
    "time":         ["weathered marble columns decay dark", "crumbling ancient ruins storm clouds", "stone archway dust mist dark"],
    "control":      ["still reflecting pool temple dark", "rain falling stone temple dark", "zen stone monolith mist"],
    "virtue":       ["roman stone columns noble dramatic light", "greek temple golden hour dark", "ancient stone inscription tablet dark"],
    "wisdom":       ["ancient library candlelight stone", "stone archway shadow contemplative dark", "old manuscripts dark desk candle"],
    "impermanence": ["crumbling stone wall erosion moss dark", "ash embers floating dark", "withered ruins overgrown fog"],
    "justice":      ["marble scales balance dramatic dark", "roman columns shafts light dark", "ancient columns storm dramatic dark"],
    "friendship":   ["roman stone archway warm light dark", "roman columns warm sunset", "ancient stone relief carving dark"],
    # ---- storm & forge register ----
    "discipline":   ["blacksmith forge sparks dark dramatic", "lightning storm dramatic rain dark", "mountain peak blizzard dark stormy"],
    "resilience":   ["lone tree lightning storm dark", "waves crashing black rocks dark", "wind storm dark dramatic cliffs"],
    "purpose":      ["mountain summit storm clouds dark", "lighthouse dark stormy sea", "blacksmith hammer anvil sparks dark"],
    "ego":          ["shattered stone dark dramatic ruins", "crumbling stone ruins shadow dark", "storm clouds dramatic dark sky"],
    "anger":        ["molten forge fire sparks dark", "volcanic lava flow night dramatic", "violent stormy sea waves dark"],
    "desire":       ["fire embers slow motion dark", "golden flame shadow black dramatic", "molten gold pour dark"],
    "fear":         ["dark stormy forest fog dramatic", "lightning night sky dramatic", "dark stone corridor fog dramatic"],
    "adversity":    ["blizzard mountain cliff dark ice storm", "blacksmith hammer anvil sparks", "rough sea storm cliff rocks dark"],
}

# Fallback pool — used only if no keyword matches. Three options so even the
# fallback rotates rather than always looking the same.
DEFAULT_QUERIES = [
    "ancient marble ruins atmospheric dark",
    "dramatic storm clouds cinematic dark",
    "classical stone columns shadow fog dark",
]

# When a render uses 3 background clips, clips 1 and 2 pull from these
# diversity pools so each clip has a distinctly different look.
DIVERSITY_QUERIES = [
    # Clip 1 — dramatic nature: ocean, mountains, wilderness
    [
        "dramatic ocean waves crashing dark cinematic",
        "mountain peak storm clouds dark cinematic",
        "waterfall mist dark dramatic cinematic",
        "desert dunes wind dramatic dark",
    ],
    # Clip 2 — ancient stone / architecture
    [
        "ancient roman ruins atmospheric dark fog",
        "stone cathedral archway shadow dark",
        "crumbling temple stone overgrown dark",
        "old stone monastery corridor dark",
    ],
]


def _bg_offset() -> int:
    """Offset for the deterministic-by-date pick. Set by the QA retry loop
    (REEL_BG_OFFSET=attempt) so a failed render gets a different clip on retry.
    Read at call time, not import time, because daily_post.py changes it
    between attempts without reimporting this module."""
    try:
        return int(os.environ.get("REEL_BG_OFFSET", "0"))
    except ValueError:
        return 0

# For refresh_backgrounds.py backward-compat — flat list of all queries.
THEME_QUERIES = [(kw, qs[0]) for kw, qs in THEME_QUERY_POOLS.items()]
DEFAULT_QUERY = DEFAULT_QUERIES[0]

# Dark colour palettes (hex) for synthetic backgrounds, keyed by theme keyword.
_SYNTHETIC_COLOURS = {
    "mortality":    "0x0b0c1e",
    "discipline":   "0x0a1015",
    "time":         "0x100e08",
    "control":      "0x091212",
    "virtue":       "0x0e0c18",
    "wisdom":       "0x120f0a",
    "resilience":   "0x0a0f0a",
    "purpose":      "0x12100a",
    "impermanence": "0x0e0c0a",
    "justice":      "0x140a0a",
    "ego":          "0x10100a",
    "anger":        "0x180808",
    "desire":       "0x140c08",
    "fear":         "0x080810",
    "friendship":   "0x0a0e14",
    "adversity":    "0x0c0c0c",
}


def _search_term(theme: str, clip_idx: int = 0) -> str:
    """Return a query string for the given theme and clip index.

    clip_idx=0 uses the theme-specific query pool.
    clip_idx>0 uses a diversity pool so consecutive clips look visually distinct.
    """
    day = date.today().toordinal() + _bg_offset()
    if clip_idx > 0:
        slot = DIVERSITY_QUERIES[(clip_idx - 1) % len(DIVERSITY_QUERIES)]
        return slot[day % len(slot)]
    t = (theme or "").lower()
    for keyword, queries in THEME_QUERY_POOLS.items():
        if keyword in t:
            return queries[day % len(queries)]
    return DEFAULT_QUERIES[day % len(DEFAULT_QUERIES)]


def _rotate_local() -> Path:
    """Original fallback: rotate deterministically by day over local clips."""
    clips = sorted(BG_DIR.glob("*.mp4"))
    if not clips:
        raise FileNotFoundError(
            f"No background clips in {BG_DIR}. Drop a few royalty-free vertical "
            f"MP4s there (Pexels Videos)."
        )
    return clips[(date.today().toordinal() + _bg_offset()) % len(clips)]


def _pick_vertical_file(video: dict) -> str | None:
    """Pick the best vertical MP4 link from a Pexels video result.

    Prefers portrait video_files (height >= width); if none exist (some Pexels
    portrait videos only have landscape-dimensioned file variants) falls back to
    any MP4 — the search was already filtered with orientation=portrait so the
    video itself is vertical.
    """
    all_mp4 = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and f.get("link")
    ]
    if not all_mp4:
        return None

    portrait = [f for f in all_mp4 if (f.get("height") or 0) >= (f.get("width") or 0)]
    pool = portrait or all_mp4  # fall back to any MP4 if no portrait variants

    # Quality-first: pick the highest-resolution variant up to 4K tall. Stock 4K
    # downscaled to 1080p is far crisper than a native-1080p file, so we deliberately
    # prefer the largest source the enhancement chain can sharpen from. Files taller
    # than ~4K are skipped (huge download, no visible gain after the 1080p crop).
    MAX_H = 3840

    def _res(f: dict) -> int:
        h = f.get("height") or 0
        return h if h <= MAX_H else -1   # over-4K ranks below everything usable

    pool.sort(key=_res, reverse=True)
    return pool[0]["link"]


def _fetch_from_pexels(theme: str, out_path: Path, query: str = "") -> Path:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY not set")

    if not query:
        query = _search_term(theme)
    resp = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={
            "query": query,
            "orientation": "portrait",
            "per_page": 80,
            "content_filter": "high",  # Pexels strict content filter
        },
        timeout=30,
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"Pexels returned no videos for '{query}'")

    # deterministic-by-date choice so it's varied but reproducible per day;
    # the retry loop shifts the pick via REEL_BG_OFFSET
    video = videos[(date.today().toordinal() + _bg_offset()) % len(videos)]
    link = _pick_vertical_file(video)
    if not link:
        raise RuntimeError("No suitable vertical MP4 in chosen Pexels result")

    with requests.get(link, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in dl.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("Downloaded Pexels clip is empty/too small")

    return out_path


def _fetch_from_pixabay(theme: str, out_path: Path, query: str = "") -> Path:
    """Download a portrait video from Pixabay (requires PIXABAY_API_KEY)."""
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        raise RuntimeError("PIXABAY_API_KEY not set")

    if not query:
        query = _search_term(theme)
    resp = requests.get(
        PIXABAY_VIDEO_URL,
        params={
            "key": api_key,
            "q": query,
            "per_page": 20,
            "order": "popular",
            "safesearch": "true",   # block adult/inappropriate content
            "video_type": "film",   # actual footage, not animation
        },
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    # Prefer portrait (height >= width); fall back to any if none found
    portrait = [
        h for h in hits
        if (h.get("videos", {}).get("large", {}).get("height", 0) >=
            h.get("videos", {}).get("large", {}).get("width", 1))
    ]
    pool = portrait or hits
    if not pool:
        raise RuntimeError(f"Pixabay returned no videos for '{query}'")

    pick = pool[(date.today().toordinal() + _bg_offset()) % len(pool)]
    url = None
    for size in ("large", "medium", "small"):
        v = pick.get("videos", {}).get(size, {})
        if v.get("url"):
            url = v["url"]
            break
    if not url:
        raise RuntimeError("No usable URL in Pixabay response")

    with requests.get(url, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in dl.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("Pixabay clip too small")
    return out_path


def _fetch_synthetic(theme: str, out_path: Path) -> Path:
    """Generate a dark atmospheric background via ffmpeg lavfi (no network needed).

    Produces a 2-second loopable clip. render.py's stream_loop -1 fills the full
    Short duration; Ken Burns zoom makes the still frame feel alive.
    """
    t = (theme or "").lower()
    colour = _SYNTHETIC_COLOURS.get(
        next((k for k in _SYNTHETIC_COLOURS if k in t), ""), "0x0c0c1a"
    )
    # solid dark colour → vignette darkens edges → subtle warmth via hue nudge
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={colour}:size=1080x1920:rate=1:duration=2",
        "-vf", "vignette=PI/3.5:eval=init",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError("Synthetic background generation failed")
    return out_path


def fetch_background(theme: str, out_path: Path, clip_idx: int = 0) -> Path:
    """
    Return a background clip for today's Short.

    clip_idx drives visual diversity: 0=theme-specific, 1=nature, 2=architecture.
    Chain: Pixabay → Pexels → Synthetic (lavfi) → Local rotation.
    Every stage catches its own failures so a run never breaks.
    """
    out_path = Path(out_path)
    query = _search_term(theme, clip_idx=clip_idx)

    for label, fn in [
        ("PIXABAY",   lambda: _fetch_from_pixabay(theme, out_path, query=query)),
        ("PEXELS",    lambda: _fetch_from_pexels(theme, out_path, query=query)),
        ("SYNTHETIC", lambda: _fetch_synthetic(theme, out_path)),
    ]:
        try:
            path = fn()
            print(f"[background] SOURCE={label} query='{query}' file={path.name}", flush=True)
            return path
        except Exception as e:  # noqa: BLE001
            print(f"[background] {label} failed: {e}", file=sys.stderr, flush=True)

    local = _rotate_local()
    print(f"[background] SOURCE=LOCAL_FALLBACK file={local.name}", flush=True)
    return local
