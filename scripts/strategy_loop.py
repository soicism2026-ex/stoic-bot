"""
Post-publish performance loop.

Runs daily (via .github/workflows/strategy-update.yml) after a configurable
delay so YouTube metrics have time to settle. For each video in the rolling
window it:
  1. Pulls extended analytics via src/youtube_analytics.py (cached).
  2. Downloads the video's YouTube thumbnail for visual analysis.
  3. Sends the windowed dataset + thumbnails to Claude Opus.
  4. Parses the structured analysis response.
  5. Writes a versioned data/strategy.md and commits it to git.

The resulting strategy.md is injected into src/content.py's system prompt so
future content generation is guided by real performance patterns.

Configuration (all via env vars):
  STRATEGY_WINDOW_DAYS     Rolling window in days          (default: 21)
  STRATEGY_MIN_AGE_HOURS   Min hours after upload          (default: 48)
  STRATEGY_MAX_VIDEOS      Max videos sent to Claude       (default: 20)
  STRATEGY_MIN_VIDEOS      Min videos needed to run        (default: 5)
  STRATEGY_COMMIT          Commit and push after writing   (default: 1)
"""

import csv
import json
import os
import subprocess
import sys
import urllib.request
import base64
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import youtube_analytics as yt_a  # noqa: E402

STRATEGY_PATH = ROOT / "data" / "strategy.md"
MODEL = "claude-opus-4-8"

WINDOW_DAYS = int(os.environ.get("STRATEGY_WINDOW_DAYS", "21"))
MIN_AGE_HOURS = float(os.environ.get("STRATEGY_MIN_AGE_HOURS", "48"))
MAX_VIDEOS = int(os.environ.get("STRATEGY_MAX_VIDEOS", "20"))
MIN_VIDEOS = int(os.environ.get("STRATEGY_MIN_VIDEOS", "5"))
SHOULD_COMMIT = os.environ.get("STRATEGY_COMMIT", "1") not in ("0", "false", "False")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load_posts(posts_csv: Path) -> list[dict]:
    if not posts_csv.exists():
        return []
    with open(posts_csv, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _peak_views(analytics_csv: Path) -> dict[str, int]:
    """Return {video_id: max_views} across all analytics snapshots."""
    if not analytics_csv.exists():
        return {}
    out: dict[str, int] = {}
    with open(analytics_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "")
            try:
                v = int(float(row.get("views", 0)))
            except (ValueError, TypeError):
                v = 0
            if vid:
                out[vid] = max(out.get(vid, 0), v)
    return out


def _select_window(
    posts: list[dict],
    window_days: int,
    min_age_hours: float,
) -> list[dict]:
    """
    Return posts within the last window_days days and at least min_age_hours
    old. One entry per video_id (first seen wins; CSV is chronological).
    """
    cutoff_date = (date.today() - timedelta(days=window_days)).isoformat()
    age_cutoff = datetime.utcnow() - timedelta(hours=min_age_hours)
    seen: dict[str, dict] = {}
    for row in posts:
        post_date = row.get("date", "")
        if not post_date or post_date < cutoff_date:
            continue
        try:
            # Treat date-only strings as noon UTC to avoid timezone edge cases
            d = date.fromisoformat(post_date[:10])
            posted_at = datetime(d.year, d.month, d.day, 12, 0, 0)
        except ValueError:
            continue
        if posted_at > age_cutoff:
            continue
        vid = row.get("video_id", "")
        if vid and vid not in seen:
            seen[vid] = row
    return list(seen.values())


# ---------------------------------------------------------------------------
# Thumbnail fetching
# ---------------------------------------------------------------------------

def _fetch_thumbnail_b64(video_id: str) -> str | None:
    """Download a YouTube thumbnail and return base64-encoded JPEG or None."""
    for url in [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                if len(data) > 5_000:
                    return base64.standard_b64encode(data).decode("ascii")
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

_STRATEGY_SYSTEM = """\
You are a YouTube Shorts performance strategist for a faceless Stoicism channel.

You receive a rolling window of recent videos with their content metadata and \
settled YouTube Analytics metrics (views, average view percentage / retention, \
swipe-away rate, average view duration in seconds). Thumbnails are provided \
for visual analysis.

Your task: identify patterns across the WINDOW — not individual videos. \
Do not over-fit to a single viral hit or single flop. Focus on patterns that \
hold across 3+ videos.

Return ONLY valid JSON, no markdown fences, no text outside the braces:

{
  "what_works": {
    "hooks": "<hook patterns that correlate with high views or low swipe-away>",
    "authors": "<per-author performance patterns>",
    "themes": "<per-theme performance patterns>",
    "retention": "<what correlates with high avg_view_percentage>",
    "visual_style": "<thumbnail / background observations from the provided images>"
  },
  "what_doesnt_work": "<consistent patterns in low-performing or high-swipe-away videos>",
  "top_recommendations": [
    "<specific, actionable rec 1 — e.g. use theme X more, avoid hook phrasing Y>",
    "<rec 2>",
    "<rec 3>"
  ],
  "confidence": "low|medium|high",
  "confidence_note": "<reason for confidence level — e.g. sample size, variance>"
}"""


def _build_analysis_prompt(
    window: list[dict],
    analytics: dict[str, dict],
    existing_strategy: str,
) -> list[dict]:
    """Build the multimodal Claude message: thumbnails + data table + task."""
    parts: list[dict] = []

    # Sort by views descending so Claude sees top performers first
    enriched = sorted(
        ((row, analytics.get(row.get("video_id", ""), {})) for row in window),
        key=lambda x: x[1].get("views", x[0].get("_views_basic", 0)),
        reverse=True,
    )

    n_thumbs = 0
    for row, a in enriched[:MAX_VIDEOS]:
        vid = row.get("video_id", "")
        b64 = _fetch_thumbnail_b64(vid)
        if b64:
            parts.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })
            views = a.get("views", row.get("_views_basic", "?"))
            hook_preview = row.get("caption", "")[:80]
            parts.append({
                "type": "text",
                "text": (
                    f"[{vid}] views={views} "
                    f"avg_view_pct={a.get('avg_view_percentage', '?')}% "
                    f"swipe_away={a.get('swipe_away_rate', '?')} "
                    f"avd_s={a.get('avg_view_duration_s', '?')} "
                    f"| {row.get('author', '')} / {row.get('theme', '')} "
                    f"| caption: {hook_preview}"
                ),
            })
            n_thumbs += 1

    # Data table
    header = (
        f"{'video_id':<15} {'date':<12} {'author':<18} {'theme':<25} "
        f"{'views':>6} {'avg_view%':>9} {'swipe_away':>10} {'avd_s':>6} {'likes':>6}"
    )
    sep = "-" * len(header)
    rows_text = [header, sep]
    for row, a in enriched[:MAX_VIDEOS]:
        vid = row.get("video_id", "")
        views = a.get("views", row.get("_views_basic", 0))
        rows_text.append(
            f"{vid[:15]:<15} {row.get('date','')[:12]:<12} "
            f"{row.get('author','')[:18]:<18} {row.get('theme','')[:25]:<25} "
            f"{str(views):>6} {str(a.get('avg_view_percentage','?'))+'%':>9} "
            f"{str(a.get('swipe_away_rate','?')):>10} "
            f"{str(a.get('avg_view_duration_s','?')):>6} "
            f"{str(a.get('likes','?')):>6}"
        )

    n_with_analytics = sum(1 for _, a in enriched if a)
    rows_text.append(
        f"\n{len(enriched)} videos in window | "
        f"{n_with_analytics} with extended analytics | "
        f"{n_thumbs} thumbnails loaded"
    )
    parts.append({"type": "text", "text": "\n".join(rows_text)})

    if existing_strategy.strip():
        parts.append({
            "type": "text",
            "text": (
                "\nEXISTING STRATEGY (context only — update or replace as data warrants):\n"
                + existing_strategy[:3000]
            ),
        })

    parts.append({
        "type": "text",
        "text": (
            "\nAnalyse the performance window above. "
            "Identify cross-video patterns (not outliers). "
            "Return the JSON schema only."
        ),
    })
    return parts


# ---------------------------------------------------------------------------
# Strategy doc writer
# ---------------------------------------------------------------------------

def _current_version(existing: str) -> int:
    for line in existing.splitlines():
        if line.startswith("_Version"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                pass
    return 0


def write_strategy(
    analysis: dict,
    window: list[dict],
    analytics: dict[str, dict],
    existing: str = "",
) -> str:
    """Render the versioned strategy.md content."""
    today = date.today().isoformat()
    version = _current_version(existing) + 1
    dates = [r.get("date", "") for r in window if r.get("date")]
    min_date = min(dates, default="?")
    max_date = max(dates, default="?")

    ww = analysis.get("what_works", {})
    lines = [
        "# Stoic Shorts Content Strategy",
        "",
        f"_Version {version} — Updated {today} by performance-loop_",
        f"_Window: {len(window)} videos posted {min_date} – {max_date}, "
        f"metrics ≥{int(MIN_AGE_HOURS)}h settled_",
        f"_Confidence: {analysis.get('confidence', 'unknown')} — "
        f"{analysis.get('confidence_note', '')}_",
        "",
        "---",
        "",
        "## What Works",
        "",
        "### Hooks",
        ww.get("hooks", "_No data yet._"),
        "",
        "### Authors",
        ww.get("authors", "_No data yet._"),
        "",
        "### Themes",
        ww.get("themes", "_No data yet._"),
        "",
        "### Retention & Completion",
        ww.get("retention", "_No data yet._"),
        "",
        "### Visual Style",
        ww.get("visual_style", "_No data yet._"),
        "",
        "---",
        "",
        "## What Doesn't Work",
        "",
        analysis.get("what_doesnt_work", "_No data yet._"),
        "",
        "---",
        "",
        "## Top Recommendations for Next Posts",
        "",
    ]
    for rec in analysis.get("top_recommendations", []):
        lines.append(f"- {rec}")
    lines += [
        "",
        "---",
        "",
        "## Performance Data Window",
        "",
        "| video_id | date | author | theme | views | avg_view% | swipe_away | avd_s | likes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(window, key=lambda r: r.get("date", ""), reverse=True):
        vid = row.get("video_id", "")
        a = analytics.get(vid, {})
        views = a.get("views", row.get("_views_basic", "?"))
        lines.append(
            f"| {vid} | {row.get('date','')} | {row.get('author','')} "
            f"| {row.get('theme','')} | {views} "
            f"| {a.get('avg_view_percentage','?')}% "
            f"| {a.get('swipe_away_rate','?')} "
            f"| {a.get('avg_view_duration_s','?')} "
            f"| {a.get('likes','?')} |"
        )
    lines.append("")
    if version > 1:
        lines += [f"_Previous: Version {version - 1}_", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Git commit
# ---------------------------------------------------------------------------

def _commit_strategy():
    try:
        for cmd in [
            ["git", "config", "user.name", "stoic-bot"],
            ["git", "config", "user.email", "bot@users.noreply.github.com"],
            ["git", "pull", "--rebase", "origin", "main"],
        ]:
            subprocess.run(cmd, check=True, capture_output=True, cwd=ROOT)

        subprocess.run(
            ["git", "add", str(STRATEGY_PATH), str(yt_a.CACHE_PATH)],
            check=True, capture_output=True, cwd=ROOT,
        )
        diff = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            capture_output=True, cwd=ROOT,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m",
                 "chore: update content strategy from performance loop [skip ci]"],
                check=True, capture_output=True, cwd=ROOT,
            )
            subprocess.run(["git", "push"], check=True, capture_output=True, cwd=ROOT)
            print("  [strategy] committed and pushed strategy.md")
        else:
            print("  [strategy] no changes to commit")
    except subprocess.CalledProcessError as e:
        print(
            f"  [strategy] git error: {e.stderr.decode()[:300]}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import anthropic

    posts_csv = ROOT / "data" / "posts.csv"
    analytics_csv = ROOT / "data" / "analytics.csv"

    posts = _load_posts(posts_csv)
    if not posts:
        print("[strategy] no posts found — exiting")
        return

    window = _select_window(posts, WINDOW_DAYS, MIN_AGE_HOURS)
    print(f"[strategy] window: {len(window)} videos (last {WINDOW_DAYS}d, ≥{int(MIN_AGE_HOURS)}h old)")

    if len(window) < MIN_VIDEOS:
        print(f"[strategy] insufficient data ({len(window)} < {MIN_VIDEOS}) — skipping")
        return

    # Merge basic view counts from analytics.csv for videos where extended
    # analytics aren't available yet (e.g., yt-analytics scope not enabled)
    peak_views = _peak_views(analytics_csv)
    for row in window:
        vid = row.get("video_id", "")
        if vid in peak_views:
            row["_views_basic"] = peak_views[vid]

    # Fetch extended analytics (quota-aware, cached)
    video_ids = [r["video_id"] for r in window if r.get("video_id")]
    analytics = yt_a.fetch_and_cache(
        video_ids,
        min_age_hours=MIN_AGE_HOURS,
        quota_budget=int(os.environ.get("YOUTUBE_ANALYTICS_QUOTA_BUDGET", "200")),
    )
    # Fill in basic views for videos missing from extended analytics
    for vid in video_ids:
        if vid not in analytics:
            row = next((r for r in window if r.get("video_id") == vid), None)
            if row:
                analytics[vid] = {"views": row.get("_views_basic", 0)}

    existing_strategy = (
        STRATEGY_PATH.read_text(encoding="utf-8") if STRATEGY_PATH.exists() else ""
    )

    print("[strategy] building analysis prompt...")
    parts = _build_analysis_prompt(window, analytics, existing_strategy)

    print("[strategy] calling Claude Opus for correlation analysis...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=_STRATEGY_SYSTEM,
            messages=[{"role": "user", "content": parts}],
        )
        raw = response.content[0].text.strip()
    except Exception as e:
        print(f"[strategy] Claude API error: {e}", file=sys.stderr)
        sys.exit(1)

    if raw.startswith("```"):
        raw = "\n".join(ln for ln in raw.split("\n") if not ln.startswith("```"))

    try:
        analysis = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        print(f"[strategy] JSON parse error: {e}\nRaw: {raw[:500]}", file=sys.stderr)
        sys.exit(1)

    doc = write_strategy(analysis, window, analytics, existing_strategy)
    STRATEGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_PATH.write_text(doc, encoding="utf-8")
    print(f"[strategy] wrote {STRATEGY_PATH} ({len(doc)} chars, version {_current_version(doc)})")

    if SHOULD_COMMIT:
        _commit_strategy()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"[strategy] FAILED: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
