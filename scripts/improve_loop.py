"""
Continuous improvement loop for stoic-bot.

Each run:
  1. Joins posts.csv + analytics.csv into per-video performance rows
  2. Loads data/improve_state.json (memory across runs)
  3. Evaluates whether the LAST focus improved the target metric
  4. Selects the NEXT focus area based on what the data says is weakest
  5. Writes a data-grounded, actionable prompt to data/improve_prompt.txt
  6. Saves updated state to data/improve_state.json

The workflow passes data/improve_prompt.txt to Claude Code Action — so the
agent's actual task changes every run without any human involvement.

Focus areas rotate through a priority queue. QA issues always jump the queue.
Each area has a target metric, a measurement window, and a verdict threshold.
"""
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_CSV    = ROOT / "data" / "posts.csv"
ANALYTICS_CSV = ROOT / "data" / "analytics.csv"
STATE_FILE   = ROOT / "data" / "improve_state.json"
PROMPT_FILE  = ROOT / "data" / "improve_prompt.txt"
QA_LOG       = ROOT / "QA_LOG.md"
IMPROVEMENTS = ROOT / "IMPROVEMENTS.md"

# ---------------------------------------------------------------------------
# Focus areas — ordered by impact priority.
# Each area targets one metric. The loop cycles through these, spending at
# least MIN_DAYS_PER_FOCUS days on each before moving on.
# ---------------------------------------------------------------------------

FOCUS_AREAS = [
    "qa_rendering",        # always first if QA issues exist
    "hook_copywriting",    # biggest lever on new-viewer CTR
    "author_rotation",     # direct view-count signal per author
    "content_format_mix",  # quote vs list performance
    "voice_selection",     # per-voice view correlation
    "music_selection",     # per-track view correlation
    "thumbnail_design",    # CTR / first-frame impression
    "description_seo",     # title / tag optimisation
    "comment_strategy",    # comment rate + reply quality
    "cta_optimisation",    # like rate / end-of-video CTA
]

MIN_DAYS_PER_FOCUS = 4   # minimum days before switching focus
MIN_VIDEOS_FOR_SIGNAL = 5  # need at least this many posts to compare


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_posts() -> list[dict]:
    if not POSTS_CSV.exists():
        return []
    with open(POSTS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _peak_views() -> dict[str, int]:
    """Return {video_id: max_views} across all analytics snapshots."""
    if not ANALYTICS_CSV.exists():
        return {}
    peak: dict[str, int] = {}
    with open(ANALYTICS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            try:
                v = int(row.get("views") or 0)
            except ValueError:
                v = 0
            if vid and v > peak.get(vid, 0):
                peak[vid] = v
    return peak


def _peak_likes() -> dict[str, int]:
    if not ANALYTICS_CSV.exists():
        return {}
    peak: dict[str, int] = {}
    with open(ANALYTICS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            try:
                v = int(row.get("likes") or 0)
            except ValueError:
                v = 0
            if vid and v > peak.get(vid, 0):
                peak[vid] = v
    return peak


def _peak_comments() -> dict[str, int]:
    if not ANALYTICS_CSV.exists():
        return {}
    peak: dict[str, int] = {}
    with open(ANALYTICS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("video_id", "").strip()
            try:
                v = int(row.get("comments") or 0)
            except ValueError:
                v = 0
            if vid and v > peak.get(vid, 0):
                peak[vid] = v
    return peak


def build_video_table(posts: list[dict]) -> list[dict]:
    """Join posts + analytics into one row per video with peak stats."""
    views    = _peak_views()
    likes    = _peak_likes()
    comments = _peak_comments()
    result = []
    for r in posts:
        vid = r.get("video_id", "").strip()
        if not vid:
            continue
        v = views.get(vid, 0)
        l = likes.get(vid, 0)
        c = comments.get(vid, 0)
        result.append({
            "date":        r.get("date", ""),
            "video_id":    vid,
            "theme":       r.get("theme", ""),
            "author":      r.get("author", ""),
            "voice":       r.get("voice_name", ""),
            "music":       r.get("music_track", ""),
            "caption":     r.get("caption", ""),
            "views":       v,
            "likes":       l,
            "comments":    c,
            "like_rate":   round(l / v, 4) if v > 0 else 0.0,
            "comment_rate": round(c / v, 4) if v > 0 else 0.0,
        })
    # Sort by date ascending
    result.sort(key=lambda x: x["date"])
    return result


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def groupby_avg(table: list[dict], key: str, metric: str,
                min_count: int = 2) -> dict[str, float]:
    """Return {key_value: avg_metric} for groups with at least min_count rows."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in table:
        k = row.get(key, "")
        if k:
            buckets[k].append(row.get(metric, 0))
    return {k: avg(vs) for k, vs in buckets.items() if len(vs) >= min_count}


def compute_metrics(table: list[dict]) -> dict:
    """Compute current-state metrics across the full video table."""
    if not table:
        return {}
    views = [r["views"] for r in table if r["views"] > 0]
    return {
        "total_videos":     len(table),
        "videos_with_data": len(views),
        "overall_avg_views": round(avg(views), 1),
        "recent_avg_views":  round(avg([r["views"] for r in table[-7:] if r["views"] > 0]), 1),
        "overall_like_rate": round(avg([r["like_rate"] for r in table if r["views"] > 0]), 4),
        "overall_comment_rate": round(avg([r["comment_rate"] for r in table if r["views"] > 0]), 4),
        "per_author":   groupby_avg(table, "author", "views"),
        "per_theme":    groupby_avg(table, "theme", "views"),
        "per_voice":    groupby_avg(table, "voice", "views"),
        "per_music":    groupby_avg(table, "music", "views"),
        "top_5_videos": sorted(table, key=lambda x: x["views"], reverse=True)[:5],
        "bottom_5_videos": [r for r in sorted(table, key=lambda x: x["views"]) if r["views"] > 0][:5],
    }


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "iteration": 0,
        "last_run": None,
        "current_focus": None,
        "focus_start_date": None,
        "focus_history": [],
        "metrics_at_focus_start": {},
        "focus_queue": list(FOCUS_AREAS),
    }


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# QA issue detection
# ---------------------------------------------------------------------------

def has_qa_issues() -> bool:
    if not QA_LOG.exists():
        return False
    text = QA_LOG.read_text(encoding="utf-8")
    # Look for recent high-severity entries (in the last 3 days)
    cutoff = (date.today() - timedelta(days=3)).isoformat()
    for line in text.splitlines():
        if line.startswith("## ") and line[3:13] >= cutoff:
            return "high" in text[text.index(line):text.index(line) + 200].lower()
    return False


# ---------------------------------------------------------------------------
# Focus selection
# ---------------------------------------------------------------------------

def _verdict(before: float, after: float) -> str:
    if before == 0:
        return "no_baseline"
    pct = (after - before) / before
    if pct > 0.10:
        return "improved"
    if pct < -0.05:
        return "hurt"
    return "mixed"


def pick_focus(state: dict, metrics: dict) -> str:
    """Pick the next focus area. QA issues jump the queue."""
    if has_qa_issues():
        return "qa_rendering"

    current = state.get("current_focus")
    start   = state.get("focus_start_date")
    today   = date.today().isoformat()

    # Stay on current focus if we haven't given it enough time
    if current and start:
        days_on_focus = (date.fromisoformat(today) - date.fromisoformat(start)).days
        if days_on_focus < MIN_DAYS_PER_FOCUS:
            return current

    # Evaluate whether last focus worked
    if current and metrics:
        before = state.get("metrics_at_focus_start", {}).get("recent_avg_views", 0)
        after  = metrics.get("recent_avg_views", 0)
        verdict = _verdict(before, after)
        if state.get("focus_history") is not None:
            state["focus_history"].append({
                "focus":       current,
                "date_closed": today,
                "before_avg":  before,
                "after_avg":   after,
                "verdict":     verdict,
            })

    # Cycle through the queue
    queue = state.get("focus_queue", list(FOCUS_AREAS))
    if current in queue:
        idx = queue.index(current)
        queue = queue[idx + 1:] + queue[:idx + 1]  # rotate past current
    if not queue:
        queue = list(FOCUS_AREAS)
    state["focus_queue"] = queue
    return queue[0]


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

def _hook_from_caption(caption: str) -> str:
    for sep in [" /  / ", "\n\n"]:
        if sep in caption:
            return caption.split(sep)[0].strip().rstrip(".")
    return caption[:60].strip()


def _format_table(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"  {r['date']} | {r['views']:>5}v | {r['author'][:18]:<18} | "
            f"{r['theme'][:20]:<20} | {_hook_from_caption(r['caption'])[:45]}"
        )
    return "\n".join(lines)


def _sorted_kv(d: dict) -> str:
    return "\n".join(
        f"  {k:<25} {v:>7.0f} avg views"
        for k, v in sorted(d.items(), key=lambda x: -x[1])
    )


def generate_prompt(focus: str, metrics: dict, state: dict, table: list[dict]) -> str:
    today = date.today().isoformat()
    history_lines = ""
    for h in state.get("focus_history", [])[-5:]:
        history_lines += (
            f"  - {h['date_closed']}: focused on {h['focus']} → "
            f"avg views {h['before_avg']:.0f} → {h['after_avg']:.0f} ({h['verdict']})\n"
        )

    base_context = f"""# Stoic-bot improvement run — {today}
## Focus area: {focus}

### Recent performance
- Total videos posted: {metrics.get('total_videos', '?')}
- Overall avg views: {metrics.get('overall_avg_views', '?')}
- Last-7 avg views:  {metrics.get('recent_avg_views', '?')}
- Avg like rate:     {metrics.get('overall_like_rate', 0) * 100:.2f}%
- Avg comment rate:  {metrics.get('overall_comment_rate', 0) * 100:.3f}%

### Last 5 improvement cycles
{history_lines if history_lines else '  (no history yet)'}

### Top 5 videos by views
{_format_table(metrics.get('top_5_videos', []))}

### Bottom 5 videos by views
{_format_table(metrics.get('bottom_5_videos', []))}

"""

    focus_instructions = {

        "qa_rendering": f"""{base_context}
## Task: Fix QA / rendering issues

Read QA_LOG.md and identify every HIGH or MEDIUM severity issue from the last
7 days. For each issue, find the root cause in the relevant source file and
implement the permanent fix. Do not use workarounds.

Files most likely to need changes: src/render.py, src/tts.py, scripts/qa_check.py,
scripts/daily_post.py.

After fixing, re-run the render smoke test:
  ffmpeg -f lavfi -i sine=duration=10 /tmp/stub.mp3 -y
  REEL_CAPTIONS=0 python -c "
import sys; sys.path.insert(0,'src')
from render import render_reel
from pathlib import Path
render_reel('Test quote here', 'Marcus Aurelius', Path('/tmp/stub.mp3'),
  Path('/tmp/test_out.mp4'), theme='discipline', word_timings=[], hook='Test hook')
assert Path('/tmp/test_out.mp4').stat().st_size > 10000, 'render failed'
print('smoke test passed')
"

Append what you fixed to IMPROVEMENTS.md with today's date and the QA signal
that drove each fix. Then commit all changes directly to main.
""",

        "hook_copywriting": f"""{base_context}
## Task: Improve hook writing rules

The hook is the first 3-5 words the viewer sees and hears. It is the single
biggest lever on CTR for new viewers who don't know the channel yet.

### Performance by hook pattern (manual — read captions from posts.csv)
Top performers tend to have hooks that:
  - Use second-person accusation: "You snapped again today"
  - Are blunt declarations: "Stop performing discipline"
  - Name a specific uncomfortable truth the viewer is living

Bottom performers tend to have hooks that:
  - Are vague or philosophical: "Time is precious"
  - Reference the philosopher by name: "Marcus Aurelius said..."
  - Ask a question: "What's holding you back?"

### Per-author view data (use this to check if certain authors pair better with
certain hook styles)
{_sorted_kv(metrics.get('per_author', {}))}

### What to change
In src/content.py, in the SYSTEM prompt:
1. Add 5 more WRONG hook examples pulled from the bottom-5 video captions above
2. Add 5 more RIGHT hook examples pulled from the top-5 video captions above
3. Tighten the "second-person accusation" rule: every hook must make a specific
   claim about what the viewer is doing wrong RIGHT NOW, not a general truth
4. Add an explicit rule: hooks that contain commas or multi-clause sentences
   are WRONG — one clean punch only
5. For "list" format posts specifically, add better hook examples that sell
   the viewer outcome ("5 Rules That Make You Untouchable") not the author

After editing, verify the SYSTEM string is valid Python (no unclosed quotes).
Append your changes and reasoning to IMPROVEMENTS.md. Commit to main.
""",

        "author_rotation": f"""{base_context}
## Task: Tune author rotation to match view data

### Current per-author performance
{_sorted_kv(metrics.get('per_author', {}))}

### Current rotation code (src/content.py)
BIG5 = ["Marcus Aurelius", "Seneca", "Epictetus", "Musonius Rufus", "Zeno of Citium"]
DIVERSE = ["Chrysippus"]
# 4 of every 5 days: Big5. Every 5th: Diverse.

### What to analyse
1. Does the current Big5 / Diverse split match the performance data above?
2. Is any Big5 author consistently underperforming? Should it move to Diverse?
3. Is any Diverse author outperforming Big5? Should it move up?
4. Do any authors have fewer than 3 posts? They need more data before judging.
5. Which themes correlate with the highest views? Update THEMES list order or
   comments if certain themes consistently outperform.

### What to change
Update BIG5, DIVERSE, and the rotation ratio in _pick_rotation() if the data
supports it. If data is inconclusive (< 3 posts per author), do NOT change the
rotation — instead improve the SOURCE_HINTS for underrepresented authors so
Claude picks more distinctive passages.

Append changes + data rationale to IMPROVEMENTS.md. Commit to main.
""",

        "content_format_mix": f"""{base_context}
## Task: Optimise quote vs list format ratio

### Current rotation: ["quote", "quote", "quote", "list"]

### Per-format performance
Read posts.csv. Posts where the hook starts with a digit or "Rules" or "Habits"
or "Things" are "list" format. Everything else is "quote" format. Compute avg
views for each group.

### Top 5 videos (with format)
{_format_table(metrics.get('top_5_videos', []))}

### What to change
1. If list posts average >20% more views than quote posts: change rotation to
   ["quote", "quote", "list"] (1-in-3 list)
2. If quote posts average >20% more views than list posts: change rotation to
   ["quote", "quote", "quote", "quote", "list"] (1-in-5 list)
3. If parity: leave rotation unchanged but improve the list-format hook prompt
   (see SYSTEM in content.py — list hooks section) to be more viewer-benefit
   focused ("5 Rules That Make You Untouchable" not "5 Rules From Stoicism")

Also check: are the best-performing list videos using numbers (5 Rules) vs
ordinals (First / Second) vs implicit ("Do This Every Day")? Update the
voiceover_text prompt for list format to match what's working.

Append changes + data to IMPROVEMENTS.md. Commit to main.
""",

        "voice_selection": f"""{base_context}
## Task: Tune ElevenLabs voice rotation to match view data

### Current per-voice performance
{_sorted_kv(metrics.get('per_voice', {}))}

### Current voice pool (src/tts.py)
VOICE_POOL = [
    {{"name": "Brian",  "id": "nPczCjzI2devNBz1zQrb"}},
    {{"name": "George", "id": "JBFqnCBsd6RMkjVDRZzb"}},
    {{"name": "Adam",   "id": "pNInz6obpgDQGcFmaJgB"}},
]

### What to analyse
1. Which voice has the highest avg views? Does it have enough posts (≥5) for
   the signal to be reliable?
2. Is there a voice with very few posts that needs more data?
3. Are the VOICE_SETTINGS (stability, similarity_boost, style) tuned for deep,
   authoritative narration? Read the current values and consider if they should
   change.

### What to change
1. Reorder VOICE_POOL so the best-performing voice is first (it's the default)
2. If any voice has ≥5 posts and avg views < 70% of the best voice, consider
   removing it and replacing with a new ElevenLabs voice ID (search the EL
   voices docs for deep, authoritative male voices in the same register)
3. If stability < 0.70, increase it — lower stability makes the voice less
   consistent and hurts watch time
4. Update VOICE_SETTINGS if the current values don't match a commanding,
   measured narration style

Append changes + reasoning to IMPROVEMENTS.md. Commit to main.
""",

        "music_selection": f"""{base_context}
## Task: Tune background music rotation to match view data

### Current per-track performance
{_sorted_kv(metrics.get('per_music', {}))}

### Current music pool (src/music.py)
MUSIC_POOL = [
    {{"name": "dark_ambient",     "query": "dark ambient cinematic"}},
    {{"name": "ancient_minimal",  "query": "ancient meditation minimal"}},
    {{"name": "focus_underscore", "query": "deep focus cinematic underscore"}},
]
MUSIC_VOLUME = 0.07

### What to analyse
1. Which track has the highest avg views? Enough posts (≥5) per track?
2. Is MUSIC_VOLUME right? Too loud distracts from voiceover; too quiet is
   pointless. 0.07 (~-23dB under voice) is safe but conservative.
3. Are there missing track moods? (e.g. brooding orchestral, ancient drums)

### What to change
1. Reorder MUSIC_POOL so best-performing track is first
2. If any track has ≥5 posts and avg views < 70% of the best, replace its
   search query with a different Pixabay music search term that fits the
   Stoic aesthetic better
3. Consider adding one new mood to the pool if all 3 current tracks have data
   and views are plateauing (variety keeps the algorithm interested)

Append changes + data to IMPROVEMENTS.md. Commit to main.
""",

        "thumbnail_design": f"""{base_context}
## Task: Improve thumbnail design for better CTR

The thumbnail is the FIRST thing a viewer sees before clicking. For a faceless
channel, it's almost entirely hook text on dark footage.

### Current thumbnail spec (src/render.py: generate_thumbnail())
- Hook text: DejaVu Sans Bold, 130px, all-caps white / gold last line (#FFB830)
- Overlay: layered dark gradient + mid-band behind text block
- Author credit below a thin gold separator line
- Gold corner brackets

### What to analyse
Read the top-5 and bottom-5 videos above. Are there hook-length patterns?
(Very long hooks wrap onto many lines, which shrinks each line's effective
pixel size at thumbnail resolution.)

Competitive landscape: other top Stoic Shorts channels use hooks under 5 words
that fill the frame in 2-3 lines. More lines = smaller text = less readable.

### What to change in generate_thumbnail()
1. Count characters in hooks for top vs bottom performers. If bottom hooks
   average > 20 chars, tighten wrap width (currently 10) to 8 or reduce
   HOOK_FS floor so short hooks get bigger text.
2. Try adding a subtle top-to-bottom gradient using multiple drawbox layers
   (e.g. black@0.60 at top 30%, transparent in middle, black@0.50 at bottom
   30%) so the footage "bleeds through" in the centre — this looks more cinematic
   and less like a flat filter.
3. Increase punchline size from HOOK_FS+10 to HOOK_FS+16 for a stronger
   visual hierarchy.
4. If FRAME_ON is False, turn it on — the gold corner brackets add perceived
   production value at no quality cost.

After changes, run the smoke test to confirm thumbnails still generate:
  ffmpeg -f lavfi -i sine=duration=2 /tmp/stub.mp3 -y
  ffmpeg -f lavfi -i color=c=0x0c0c1a:size=1080x1920:rate=1:duration=2 \
    -c:v libx264 -pix_fmt yuv420p /tmp/stub_bg.mp4 -y
  REEL_CAPTIONS=0 python -c "
import sys; sys.path.insert(0,'src')
import render
from pathlib import Path
t = render.generate_thumbnail('You quit again today', 'Marcus Aurelius',
  Path('/tmp/stub_bg.mp4'), Path('/tmp/test_thumb.jpg'))
assert t and t.stat().st_size > 5000, 'thumbnail failed'
print('thumbnail smoke test passed:', t.stat().st_size, 'bytes')
"

Append changes + reasoning to IMPROVEMENTS.md. Commit to main.
""",

        "description_seo": f"""{base_context}
## Task: Optimise video titles and descriptions for YouTube discovery

Title = hook + author + "| Stoicism" (current format, capped at 90 chars).
This is strong. The question is whether tags and description are maximising
discovery for new viewers who don't yet follow the channel.

### What to analyse
1. Read the current title/tag logic in scripts/daily_post.py.
2. Compare: do top-performing videos have shorter hooks (more readable in
   the 60-char YouTube title truncation on mobile)?
3. Check the tag list — are the 30 allowed tags covering the right mix of
   broad (#stoicism) + mid-size (#dailystoicism) + specific (#marcusaurelius)?
4. Is "Day N of daily Stoic wisdom" in descriptions helping or hurting? New
   viewers don't care about day N; loyal fans do. Is it placed right?

### What to change
1. If top-performing titles are shorter, add a check in daily_post.py that
   warns when the hook is > 40 chars (likely to truncate on mobile). Do NOT
   truncate automatically — just log a warning so content.py can tighten hooks.
2. Add 3-5 more high-volume stoicism tags to seo_tags in daily_post.py if they
   aren't already there (check YouTube search for "stoicism" related terms that
   appear in top Shorts channel descriptions but aren't in our list).
3. Reorder description: put the caption sentence BEFORE "Day N" so the first
   100 chars of the description (what YouTube shows in search snippets) is the
   hook/insight, not the day counter.

Append changes + reasoning to IMPROVEMENTS.md. Commit to main.
""",

        "comment_strategy": f"""{base_context}
## Task: Improve comment engagement rate

### Current engagement
- Avg comment rate: {metrics.get('overall_comment_rate', 0) * 100:.3f}%
- Avg like rate:    {metrics.get('overall_like_rate', 0) * 100:.2f}%

### Context
The bot posts a pinned comment (from content.py's "pinned_comment" field)
immediately after upload. This is the most visible comment on the video.
The bot also auto-replies to top viewer comments via scripts/reply_to_comments.py.

### What to analyse
1. Read the current "Pinned comment" rule in src/content.py's SYSTEM prompt.
   Does it require a question that forces a SPECIFIC answer? Generic questions
   ("What do you think?") get ignored. Specific ones ("Name the last time you
   let someone's bad mood ruin your whole day") generate real replies.
2. Read scripts/reply_to_comments.py's _generate_reply() system prompt. Is
   the bot's reply voice actually matching the channel tone — calm, direct,
   slightly confrontational? Or is it being too supportive/fluffy?
3. Check data/replied_comments.csv — how many replies have been posted? Are
   they generating further replies (reply threads)?

### What to change
1. Rewrite the "Pinned comment" rule in content.py's SYSTEM to require:
   - The question names a specific MOMENT, PERSON, or HABIT — not a feeling
   - It is uncomfortable enough that the viewer has to think to answer
   - Under 15 words
   - Examples of GOOD: "Name the last excuse you used today."
   - Examples of BAD: "What did you think of this Stoic lesson?"
2. Rewrite _generate_reply() system prompt in reply_to_comments.py to match:
   - 1 sentence max acknowledging their comment
   - 1 sentence that adds a concrete Stoic angle (not a generic principle)
   - Optional: 1 follow-up question that digs one level deeper
   - Never start with "Great comment!" or compliments — go straight to the idea

Append changes + reasoning to IMPROVEMENTS.md. Commit to main.
""",

        "cta_optimisation": f"""{base_context}
## Task: Optimise CTA and like rate

### Current like rate: {metrics.get('overall_like_rate', 0) * 100:.2f}%

The CTA (call to action) is spoken at the end of every voiceover and also
lives in the description. It should drive likes AND set up the next video.

### Current CTA rules (src/content.py SYSTEM)
"CTA: 1-2 spoken sentences at the very end. Last line loops back to the
opening feeling (creates rewatch loops). Reference the next day's theme
naturally. Under 25 words. Vary the phrasing."

### What to analyse
1. Do top-5 videos have CTAs that explicitly ask for a like/save vs ones that
   just tease the next video? Read the captions in posts.csv.
2. Is the like rate trending up or flat over the last 14 days?
3. Read the promo comment text from src/promo.py — is the product CTA
   appearing too soon after the pinned comment (two comments from the same
   account in a row looks spammy)?

### What to change
1. Update the CTA rule in content.py's SYSTEM to include one explicit
   "save this if you need it" or "drop a comment if this hit" direction —
   but keep it subtle, not "LIKE AND SUBSCRIBE". Stoic audience responds to
   understated directness, not hype.
2. If promo comment is enabled AND pinned comment is enabled, add a delay
   in daily_post.py between the two comment posts (10 seconds) to avoid
   triggering YouTube's duplicate-comment filter.
3. If like rate < 1.5%, also add a soft CTA to the video description (below
   the hashtags): a one-line "If this helped, save it." — costs nothing,
   occasionally prompts saves which boost the algorithm.

Append changes + reasoning to IMPROVEMENTS.md. Commit to main.
""",

    }

    return focus_instructions.get(focus, f"{base_context}\n## Task: General review\n\nReview the codebase for any obvious improvements and implement the most impactful one. Append to IMPROVEMENTS.md and commit to main.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = date.today().isoformat()
    print(f"[improve_loop] {today}", file=sys.stderr)

    posts  = _load_posts()
    table  = build_video_table(posts)
    metrics = compute_metrics(table)

    print(f"[improve_loop] {len(table)} videos with data, avg views={metrics.get('overall_avg_views', 0)}", file=sys.stderr)

    state = load_state()
    state["iteration"] = state.get("iteration", 0) + 1
    state["last_run"] = today

    focus = pick_focus(state, metrics)
    print(f"[improve_loop] focus={focus}", file=sys.stderr)

    # Record metrics at the start of this focus period
    if state.get("current_focus") != focus:
        state["current_focus"] = focus
        state["focus_start_date"] = today
        state["metrics_at_focus_start"] = {
            "recent_avg_views": metrics.get("recent_avg_views", 0),
            "overall_avg_views": metrics.get("overall_avg_views", 0),
            "like_rate": metrics.get("overall_like_rate", 0),
            "comment_rate": metrics.get("overall_comment_rate", 0),
        }

    prompt = generate_prompt(focus, metrics, state, table)
    PROMPT_FILE.write_text(prompt, encoding="utf-8")

    save_state(state)
    print(f"[improve_loop] wrote prompt ({len(prompt)} chars) → {PROMPT_FILE}", file=sys.stderr)
    print(f"[improve_loop] state saved → {STATE_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
