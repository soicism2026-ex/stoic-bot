"""
Channel performance analyst (advisory — NEVER changes code or posts).

This replaces the old auto-improve loop's autonomous "pick a change and commit it
to main" behaviour. Instead it reads the data and produces a human-readable
report: how the channel is doing, what's working, what's hurting, and which
pipeline "agents" to add / remove / change. YOU read it and decide; nothing is
applied automatically.

Run:
    python scripts/channel_report.py            # print report to stdout
    python scripts/channel_report.py --write     # also write data/channel_report.md

Data sources:
    data/posts.csv      one row per post (date, theme, author, quote, ...,
                        voice_name, music_track as trailing fields)
    data/analytics.csv  repeated view/like/comment snapshots per video_id

Caveat baked into the report: newer videos have had less time to accumulate
views, so recent-vs-old comparisons are directional, not exact. Recommendations
lean on signals that survive that confound (theme extremes, large voice gaps,
duplicate quotes, engagement rates).
"""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.csv"
ANALYTICS = ROOT / "data" / "analytics.csv"

# Below this average view count a theme/author is a candidate to drop.
WEAK_VIEWS = 320
# A voice/theme needs at least this many posts before we trust its average.
MIN_N = 4


def _load_posts() -> list[dict]:
    """posts.csv carries voice_name + music_track as trailing fields that aren't
    in the header, so parse positionally rather than with DictReader."""
    rows = []
    if not POSTS.exists():
        return rows
    with open(POSTS, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd, None)  # header
        for r in rd:
            if len(r) < 7:
                continue
            rows.append({
                "date": r[0], "theme": r[1], "author": r[2], "quote": r[3],
                "video_id": r[6],
                "voice": r[7] if len(r) > 7 else "",
                "music": r[8] if len(r) > 8 else "",
                "hook": r[9] if len(r) > 9 else "",
                "experiment": r[10] if len(r) > 10 else "",
            })
    return rows


def _peak_stats() -> dict:
    """Return {video_id: {views, likes, comments}} using the peak snapshot."""
    peak = defaultdict(lambda: {"views": 0, "likes": 0, "comments": 0, "title": ""})
    if not ANALYTICS.exists():
        return peak
    with open(ANALYTICS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            vid = (r.get("video_id") or "").strip()
            if not vid:
                continue
            v = int(r.get("views") or 0)
            if v >= peak[vid]["views"]:
                peak[vid] = {
                    "views": v,
                    "likes": int(r.get("likes") or 0),
                    "comments": int(r.get("comments") or 0),
                    "title": r.get("title", ""),
                }
    return peak


def _load_retention() -> dict:
    """Return {video_id: {'pct': float, 'sec': float}} from data/retention.csv,
    or {} if the retention agent hasn't been authorised/run yet."""
    path = ROOT / "data" / "retention.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            vid = (r.get("video_id") or "").strip()
            if vid:
                out[vid] = {
                    "pct": float(r.get("avg_view_pct") or 0),
                    "sec": float(r.get("avg_view_seconds") or 0),
                }
    return out


def _avg(xs):
    return statistics.mean(xs) if xs else 0.0


def _by_dimension(tracked, views_of, dim):
    d = defaultdict(list)
    for p in tracked:
        if p.get(dim):
            d[p[dim]].append(views_of(p))
    return sorted(([k, _avg(v), len(v)] for k, v in d.items()), key=lambda x: -x[1])


def build_report() -> str:
    posts = _load_posts()
    peak = _peak_stats()
    views_of = lambda p: peak.get(p["video_id"], {}).get("views", 0)
    tracked = [p for p in posts if p["video_id"] in peak]

    out = []
    w = out.append

    if not tracked:
        return "No analytics data yet — post a few videos and pull analytics first."

    views = [views_of(p) for p in tracked]
    total_v = sum(views)
    likes = sum(peak[p["video_id"]]["likes"] for p in tracked)
    comments = sum(peak[p["video_id"]]["comments"] for p in tracked)
    recent = [views_of(p) for p in tracked[-15:]]
    earlier = [views_of(p) for p in tracked[:-15]]

    w("# Stoic Shorts — Channel Report\n")
    w("## 1. Health snapshot")
    w(f"- Posts with data: **{len(tracked)}** (of {len(posts)} total)")
    w(f"- Total views: **{total_v:,}** · avg **{_avg(views):.0f}** · median "
      f"**{statistics.median(views):.0f}** · best **{max(views):,}** · worst **{min(views)}**")
    w(f"- Engagement: **{100*likes/max(total_v,1):.2f}%** like rate, "
      f"**{100*comments/max(total_v,1):.3f}%** comment rate")
    if earlier:
        delta = _avg(recent) - _avg(earlier)
        arrow = "UP" if delta >= 0 else "DOWN"
        w(f"- Trend: earlier {len(earlier)} posts avg **{_avg(earlier):.0f}** → "
          f"last 15 avg **{_avg(recent):.0f}**  ({arrow} {abs(delta):.0f})")
        w("  - _Caveat: newer videos are younger, so some of this gap is just age._")

    # Retention — the real Shorts ranking signal (needs the retention agent).
    ret = _load_retention()
    w("\n## Retention (the signal that actually drives reach)")
    if not ret:
        w("- ⚠️ **Not enabled yet.** Views alone can't tell you what the algorithm "
          "rewards. Re-run `python src/auth_setup.py` (now requests "
          "`yt-analytics.readonly`), update `YOUTUBE_REFRESH_TOKEN`, and the "
          "retention agent will report avg-view-% per video here.")
    else:
        matched = [(p, ret[p["video_id"]]) for p in tracked if p["video_id"] in ret]
        if matched:
            pcts = [r["pct"] for _, r in matched]
            w(f"- Avg view %: **{_avg(pcts):.1f}%** across {len(matched)} videos")
            top = max(matched, key=lambda m: m[1]["pct"])
            bot = min(matched, key=lambda m: m[1]["pct"])
            w(f"- Best retention: **{top[1]['pct']:.0f}%** — \"{top[0]['quote'][:40]}\"")
            w(f"- Worst retention: **{bot[1]['pct']:.0f}%** — \"{bot[0]['quote'][:40]}\"")
            w("- _Optimise hooks/pacing for the high-retention patterns above._")

    # Per-dimension tables
    for dim, label in [("theme", "theme"), ("author", "author"),
                       ("voice", "voice"), ("music", "music")]:
        rows = _by_dimension(tracked, views_of, dim)
        if not rows:
            continue
        w(f"\n## Avg views by {label}")
        for k, a, n in rows:
            flag = ""
            if n >= MIN_N and a < WEAK_VIEWS:
                flag = "  ⚠️ weak"
            w(f"- {k[:30]:30} **{a:.0f}v**  (n={n}){flag}")

    # Voice gap — usually the single biggest lever
    vrows = [r for r in _by_dimension(tracked, views_of, "voice") if r[2] >= MIN_N]
    if len(vrows) >= 2:
        best, worst = vrows[0], vrows[-1]
        if best[1] > 1.5 * max(worst[1], 1):
            w("\n## ⚑ Voice gap")
            w(f"- Best voice **{best[0]}** ({best[1]:.0f}v) is "
              f"**{best[1]/max(worst[1],1):.1f}×** the current-style voice "
              f"**{worst[0]}** ({worst[1]:.0f}v). Voice may be the biggest lever "
              f"(watch the age confound, but the gap is large).")

    # Duplicate quotes (a real, fixable leak)
    seen = defaultdict(list)
    for p in tracked:
        seen[p["quote"].strip().lower()[:60]].append(p)
    dups = {q: ps for q, ps in seen.items() if len(ps) > 1}
    if dups:
        w("\n## ⚑ Duplicate quotes shipped")
        for q, ps in list(dups.items())[:6]:
            w(f"- \"{ps[0]['quote'][:50]}…\" posted {len(ps)}× "
              f"(views: {', '.join(str(views_of(p)) for p in ps)})")

    # Hook-lab: hooks were only logged from the roll-out of the hook agent, so
    # this fills in as new posts accumulate.
    hooked = [p for p in tracked if p.get("hook")]
    w("\n## Hook-lab")
    if len(hooked) < MIN_N:
        w(f"- Collecting hook data ({len(hooked)} posts logged so far). Once "
          f"~10+ posts carry hooks, this shows which hook lengths/styles win.")
    else:
        buckets = {"2-3 words": [], "4-5 words": [], "6+ words": []}
        for p in hooked:
            n = len(p["hook"].split())
            key = "2-3 words" if n <= 3 else ("4-5 words" if n <= 5 else "6+ words")
            buckets[key].append(views_of(p))
        for k, vs in buckets.items():
            if vs:
                w(f"- {k}: **{_avg(vs):.0f}v** avg (n={len(vs)})")
        best = max(hooked, key=views_of)
        w(f"- Best hook so far: \"{best['hook'][:50]}\" ({views_of(best)}v)")

    # Experiment agent: rank intro-sound + colour-grade combos as data accrues.
    exps = [p for p in tracked if p.get("experiment")]
    w("\n## Experiments (intro sound × colour grade)")
    if len(exps) < MIN_N:
        w(f"- Collecting ({len(exps)} experimental posts so far). Combos rotate "
          f"every post; rankings appear once each combo has a few samples.")
    else:
        combo_views = defaultdict(list)
        intro_views = defaultdict(list)
        grade_views = defaultdict(list)
        for p in exps:
            combo_views[p["experiment"]].append(views_of(p))
            parts = p["experiment"].split("+")
            if len(parts) == 2:
                intro_views[parts[0]].append(views_of(p))
                grade_views[parts[1]].append(views_of(p))
        for k, vs in sorted(combo_views.items(), key=lambda kv: -_avg(kv[1])):
            w(f"- {k:22} **{_avg(vs):.0f}v** (n={len(vs)})")
        if intro_views:
            ranked = sorted(intro_views.items(), key=lambda kv: -_avg(kv[1]))
            w(f"- Intro signal: **{ranked[0][0]}** leads "
              f"({', '.join(f'{k} {_avg(v):.0f}v' for k, v in ranked)})")
        if grade_views:
            ranked = sorted(grade_views.items(), key=lambda kv: -_avg(kv[1]))
            w(f"- Grade signal: **{ranked[0][0]}** leads "
              f"({', '.join(f'{k} {_avg(v):.0f}v' for k, v in ranked)})")

    # Packaging agent: do title patterns move views? Titles live in analytics.csv.
    def title_of(p):
        return peak.get(p["video_id"], {}).get("title", "")
    titled = [p for p in tracked if title_of(p)]
    if titled:
        w("\n## Packaging (titles)")
        day_prefix = [views_of(p) for p in titled if title_of(p).strip().lower().startswith("day ")]
        no_prefix = [views_of(p) for p in titled if not title_of(p).strip().lower().startswith("day ")]
        if day_prefix and no_prefix:
            w(f"- Titles starting with \"Day N …\": **{_avg(day_prefix):.0f}v** "
              f"(n={len(day_prefix)}) vs others **{_avg(no_prefix):.0f}v** (n={len(no_prefix)})")
            if _avg(no_prefix) > _avg(day_prefix) * 1.15:
                w("  - → Drop the \"Day N\" prefix; it isn't earning clicks or search.")
        short_t = [views_of(p) for p in titled if len(title_of(p)) <= 45]
        long_t = [views_of(p) for p in titled if len(title_of(p)) > 45]
        if short_t and long_t:
            w(f"- Shorter titles (≤45 chars): **{_avg(short_t):.0f}v** vs longer "
              f"**{_avg(long_t):.0f}v**")

    # Top / bottom
    ts = sorted(tracked, key=views_of, reverse=True)
    w("\n## Top 5")
    for p in ts[:5]:
        w(f"- {views_of(p):>5}v  {p['author'][:16]:16} {p['theme'][:16]:16} "
          f"{p['quote'][:44]}")
    w("## Bottom 5")
    for p in ts[-5:]:
        w(f"- {views_of(p):>5}v  {p['author'][:16]:16} {p['theme'][:16]:16} "
          f"{p['quote'][:44]}")

    # Data-driven candidate actions
    w("\n## Data-driven candidates (you decide)")
    weak_themes = [k for k, a, n in _by_dimension(tracked, views_of, "theme")
                   if n >= MIN_N and a < WEAK_VIEWS]
    strong_themes = [k for k, a, n in _by_dimension(tracked, views_of, "theme")[:3]]
    weak_authors = [k for k, a, n in _by_dimension(tracked, views_of, "author")
                    if n >= MIN_N and a < WEAK_VIEWS]
    if weak_themes:
        w(f"- Drop / down-weight themes: **{', '.join(weak_themes)}**")
    if strong_themes:
        w(f"- Over-weight themes: **{', '.join(strong_themes)}**")
    if weak_authors:
        w(f"- Down-weight authors: **{', '.join(weak_authors)}**")
    if len(vrows) >= 2 and vrows[0][1] > 1.5 * max(vrows[-1][1], 1):
        w(f"- Test switching default voice away from **{vrows[-1][0]}** toward "
          f"**{vrows[0][0]}**-style delivery.")
    if dups:
        w("- Harden the duplicate-quote guard (same quote shipped twice above).")

    w("\n_Advisory only — nothing here was applied. Tell me which to action._")
    return "\n".join(out)


def main():
    report = build_report()
    print(report)
    if "--write" in sys.argv:
        dest = ROOT / "data" / "channel_report.md"
        dest.write_text(report + "\n", encoding="utf-8")
        print(f"\n[written] {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
