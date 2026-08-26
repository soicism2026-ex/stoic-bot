# Stoic Shorts Bot — CLAUDE.md

Faceless Stoicism YouTube Shorts channel. Fully automated: content → voiceover → render → upload → comment reply. Runs on GitHub Actions, zero human intervention per day.

> **MEMORY PROTOCOL (read first):** `data/decisions.md` is the owner's decision
> log — every directive, veto, and preference from chat sessions. READ IT before
> making changes; HONOR everything in it; APPEND a dated entry whenever the
> owner issues a new decision (newest wins on conflict; never delete history).
> Creative philosophy lives in `data/doctrine.md` (injected into every content
> call). If the owner says "remember X" or states a preference — it goes in
> decisions.md (operational) or doctrine.md (creative) in the same turn.

**Channel:** forged.in.stoicism  
**Posting cadence:** 3 videos/day; crons fire 03:00, 07:00, 11:00 UTC (six slots are over-provisioned at 03/07/11/15/19/23 and MAX_POSTS_PER_DAY=3 means the first three always win) (restored 2026-07-24 after 1/day starved views; safe volume because every video is now distinct — 5 formats, statue guide, scene-matched b-roll, cinematic look; goal: 500 subs + 3M Shorts views/90d)  
**Product:** The Stoic Reset journal — https://soicism.gumroad.com/l/cslosv

---

## Skills (`.claude/skills/`)

| Skill | Use when |
|-------|----------|
| `channel-report` | "How's the bot doing" — age-corrected performance read, leaderboards, honest verdict + one recommendation |
| `pipeline-doctor` | "It's not posting" / "changes aren't showing up" — walks every known silent-failure mode (QA rejecting good renders, stale/empty backup bank, dropped crons, push races, oversized files) and verifies the fix with a real post |
| `remember` | Owner states a decision, veto, or preference — writes it to `data/decisions.md` (operational) or `data/doctrine.md` (creative) with its reasoning, same turn |
| `preview-short` | Any visual/audio change — renders a test short locally and shows frames through the iPhone crop before anything publishes |

---

## Pipeline

Each run of `scripts/daily_post.py` does:

1. **Guard** — reads `data/posts.csv`; skips if `posts_today >= MAX_POSTS_PER_DAY` (env, default 3)
2. **Content** — `src/content.py` calls Claude Opus 4.8 for quote, hook, voiceover script, CTA, caption, hashtags, callout words, pinned comment
3. **Voice** — `src/tts.py` calls ElevenLabs with-timestamps endpoint; falls back to edge-tts if no key
4. **Music** — `src/music.py` downloads a royalty-free Pixabay track to `assets/music/`
5. **Render** — `src/render.py` builds 1080×1920 MP4 via ffmpeg (6 background clips: a recurring marble-statue GUIDE opens+closes, 4 scene-matched b-roll clips track the narration in real time; hook text, quote text, cinematic score mixed)
6. **QA** — `scripts/qa_check.py` checks for frozen frames, audio desync, unreadable text; up to 5 render attempts with auto-corrections
7. **Upload** — `src/publish.py` posts to YouTube as a Short with optimised title/tags/description
8. **Thumbnail** — `render.py:generate_thumbnail()` generates 1080×1920 JPEG (big hook text, dark cinematic grade, gold accent), uploaded via YouTube API
9. **Comments** — pinned engagement question + promo CTA posted as comments
10. **Log** — `src/logbook.py` appends row to `data/posts.csv`
11. **Backup top-up** — if backup bank < 3 videos, renders and QA-checks one evergreen short and stores it in `backups/`

After the main post loop, the workflow runs:
- `src/analytics.py` — pulls view/like/comment counts to `data/analytics.csv`
- `scripts/prune_videos.py` — unlists under-performers older than 7 days below an ADAPTIVE threshold: max(300 floor, 0.5× recent median views) — the bar rises automatically as the channel improves
- `scripts/reply_to_comments.py` — auto-replies to up to 5 top viewer comments with Claude Haiku

---

## Source files

| File | Role |
|------|------|
| `src/content.py` | Claude Opus content generation. Author rotation (Big5 × 4 days, Chrysippus × 1), theme LRU rotation, format rotation (3 quote : 1 list). Hard block-list of previously used quotes injected into prompt. |
| `src/tts.py` | ElevenLabs primary (Brian → George → Adam, analytics-weighted). edge-tts fallback when no key. Returns per-word timings for karaoke. |
| `src/render.py` | ffmpeg pipeline. 3-clip background (clip 0 = theme query, clip 1 = dramatic nature, clip 2 = ancient stone). Hook text at top, quote + author centred, music mixed. Captions OFF by default (`REEL_CAPTIONS=0`). |
| `src/imagegen.py` | PIVOT: text-to-image backgrounds. When `REEL_IMAGE_BG=1` + `OPENAI_API_KEY`, each clip is an AI cinematic still depicting the exact narration beat (gpt-image-1) → Ken Burns clip. OFF by default; any failure falls back to stock. |
| `src/backgrounds.py` | Guide library (bookend slots only) → generated (imagegen) → Pixabay → Pexels → synthetic lavfi fallback. Stock picks from top-`REEL_BG_TOP` (=3) most-relevant results, not a deep index. `clip_idx` drives diversity: idx 0 = theme-specific query, idx 1 = `DIVERSITY_QUERIES[0]` (nature), idx 2 = `DIVERSITY_QUERIES[1]` (stone). |
| `src/music.py` | 3-track pool: `dark_ambient`, `ancient_minimal`, `focus_underscore`. Analytics-weighted after 5 posts per track, LRU before that. Pixabay music API. |
| `src/publish.py` | YouTube Data API v3 upload. `set_thumbnail()` requires `youtube.force-ssl` scope. |
| `src/promo.py` | Configurable CTA injection into description + comment. All copy in env vars. Toggle with `PROMO_ENABLED`. |
| `src/analytics.py` | Pulls YouTube stats to `data/analytics.csv`. |
| `src/logbook.py` | Appends each post to `data/posts.csv`. |
| `src/publish_instagram.py` | Cross-posts to Instagram Reels via Meta Graph API. Requires `IG_ACCESS_TOKEN` + `IG_USER_ID`. Currently skipped (Meta dev account pending). |
| `scripts/daily_post.py` | Main orchestrator. Self-healing retry loop. Backup bank logic. |
| `scripts/qa_check.py` | Video QA: frozen frames, audio desync, contrast, safe-zone clipping. Returns pass/fail + severity. |
| `scripts/reply_to_comments.py` | Auto-replies to best viewer comments. Filters own channel by `videoOwnerChannelId == authorChannelId` (channel ID comparison, not display name). Max 5 replies/run. Receptivity screen (`_is_receptive`, Haiku + `_is_dismissive` keyword prefilter) engages ONLY viewers who genuinely connect with the message — skips trolls/mockery/bad-faith to build community and avoid amplifying detractors; fails closed. |
| `scripts/rethumbnail.py` | One-off: re-generates and uploads thumbnails for all past videos. `--only-missing` skips videos that already have a `maxres` thumbnail. |
| `scripts/improve_loop.py` | The brain of the continuous improvement loop. Joins posts.csv + analytics.csv, evaluates last run's outcome, picks next focus area, writes a data-grounded prompt to `data/improve_prompt.txt`, and saves run memory to `data/improve_state.json`. |
| `scripts/prune_videos.py` | Unlists underperforming videos. |
| `scripts/prep_guide_clips.py` | Normalises hand-generated GUIDE clips into `assets/guide/` (1080×1920, trimmed, muted, compressed, sequentially named) so they can be committed. Prompts to generate them: `docs/guide_clip_prompts.md`. |
| `scripts/cost_report.py` | Cost agent: reads `data/costs.json` (subscriptions incl. Claude + ElevenLabs, one-time buys), computes monthly burn, all-time spend, cost per Short / per 1k views. Standalone + embedded in the weekly channel report. |

---

## GitHub Actions workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `daily-short.yml` | cron 3×/day | Main pipeline: post → analytics → prune → reply |
| `pull-analytics.yml` | cron daily | Analytics-only pull |
| `refresh-assets.yml` | manual | Pre-download background clips to `data/hook_preset` |
| `rethumbnail.yml` | manual | Backfill thumbnails for old videos |
| `backfill.yml` | manual | Re-process old posts |
| `repost.yml` | manual | Re-upload a specific video |
| `ci.yml` | push/PR | Run tests |
| `auto-improve.yaml` | cron daily 06:00 UTC | Continuous improvement loop: runs `improve_loop.py` to pick a data-driven focus, feeds the output prompt to Claude Code Action, Claude implements the change and commits directly to main |

---

## Secrets required (GitHub Actions)

| Secret | Used by |
|--------|---------|
| `ANTHROPIC_API_KEY` | content.py (Opus), reply_to_comments.py (Haiku) |
| `ELEVENLABS_API_KEY` | tts.py |
| `YOUTUBE_CLIENT_ID` | publish.py, analytics.py, reply_to_comments.py |
| `YOUTUBE_CLIENT_SECRET` | same |
| `YOUTUBE_REFRESH_TOKEN` | same — must include `youtube.force-ssl` scope for thumbnails + comments |
| `PIXABAY_API_KEY` | backgrounds.py, music.py |
| `PEXELS_API_KEY` | backgrounds.py fallback |
| `REPLICATE_API_TOKEN` | tts.py — Chatterbox voice (primary; open-source, beats ElevenLabs in blind tests, pay-per-second) |
| `OPENAI_API_KEY` | imagegen.py — activates AI-generated backgrounds (optional, paid) |
| `IG_ACCESS_TOKEN` | publish_instagram.py (optional) |
| `IG_USER_ID` | publish_instagram.py (optional) |

Never commit secrets. They exist only in GitHub Actions secrets.

---

## Content rotation logic

**Authors** (`src/content.py`):
- Every 5th post (day index % 5 == 4): Chrysippus (~640 avg views, variety slot)
- All other posts: Big5 LRU — Marcus Aurelius, Seneca, Epictetus, Musonius Rufus, Zeno of Citium (all 900–1055 avg views)
- Removed from rotation: Cleanthes (224v), Hierocles, Cato the Younger (underperform)

**Themes** (12 total, LRU, block last 3):
`discipline`, `mortality/memento mori`, `control vs acceptance`, `ego`, `resilience`, `anger`, `desire`, `time`, `fear`, `friendship`, `duty/justice`, `adversity as training`

**Format rotation** (subscriber-first consolidation 2026-07-18): `["rule", "quote", "minimal", "story"]` — one of each per day at 4/day, all sharing the classic visual identity. pov + challenge (caption_only style) cut early: weakest numbers and broke the channel's visual coherence (churn risk). "rule" is the exploration star (436v). Style-pack/caption_only code remains for future tests. Style packs (daily_post `STYLE_PACKS`): pov/challenge render `caption_only` (NO quote card; big centred karaoke captions carry the words) with generated diegetic ambience (rain_night / wind_dawn) replacing the music bed; story/rule keep the classic card with an `embers` bed. The content engine emits `broll_queries` — 4 stock-video searches literally depicting successive voiceover beats. daily_post assembles 6 clips: `[statue_guide, b0, b1, b2, b3, statue_guide]` (recurring stoic-statue GUIDE character bookends every short; same subject daily, varied framing) driving `REEL_BG_FLAVOR{,1..5}` with `REEL_BG_CLIPS=6`, so visuals cut with the words (~every 3s)

**Voice rotation**: ElevenLabs "Brian" voices the FIRST `ELEVENLABS_POSTS_PER_DAY` posts of each day (default 1 — sized for the Starter plan's 30k chars/month; live credit-balance guard refuses to overspend). All other posts use the free edge-tts pool — Andrew, BrianEdge (`en-US-BrianNeural`), Christopher — each with a per-voice rate/pitch profile plus an ffmpeg mastering chain (`_master_voice`: warmth EQ + compression) to approach paid quality. Analytics-weighted after 5 posts per voice, LRU before that. `data/posts.csv` logs the voice that ACTUALLY spoke (`tts.LAST_VOICE_NAME`). Goal: when a tuned free voice matches paid Brian on views+retention, cancel ElevenLabs.

---

## Video structure (render.py)

```
[0:00–0:02] Hook text fades in (top of frame, large white caps)
[0:02+    ] Quote text + author name centred (gold accent, serif)
[full     ] Background: 3 × ~10s clips with Ken Burns zoom + cinematic grade
[full     ] Background music at 7% volume under voiceover
```

Background grade: unsharp sharpen → bloom → film grain → vignette → eq darken → per-clip colour LUT. CINEMATIC mode (`REEL_CINEMATIC`, default on): teal-orange colour balance (cool shadows, warm highlights) + filmic S-curve + warm HALATION on the bloom + deeper vignette; a generative `cinematic_score` bed (deep sub-bass Zimmer-register drone) replaces the ambient bed and every classic post opens with the `cinematic` BRAAAM hook sound.

Thumbnail: 1080×1920 JPEG. Hook text at 130px all-caps (last line in gold #FFB830), layered dark gradient overlay, thin gold separator line, author credit below, gold corner brackets.

---

## Data files

| File | Contents |
|------|----------|
| `data/decisions.md` | Owner decision log — the channel's cross-session memory. Every chat directive/veto recorded with dates. Claude reads it first and appends new decisions same-turn. |
| `data/doctrine.md` | The owner's PERMANENT creative standing orders (ICP, hook psychology, format philosophy). Injected into every content generation call. Never overwritten by automation — unlike `data/strategy.md`, which `strategy_loop.py` rewrites daily at 10:00 UTC. |
| `data/posts.csv` | All posts: date, theme, quote, author, caption, video_url, video_id, voice_name, music_track, hook, experiment, format |
| `data/analytics.csv` | Per-video view/like/comment snapshots |
| `data/replied_comments.csv` | Comment IDs the bot has already replied to |
| `data/improve_state.json` | Improvement loop memory: iteration count, current focus, focus history with before/after metrics and verdicts, metrics snapshot at each focus start |
| `data/costs.json` | Editable money registry: subscriptions (Claude, ElevenLabs, API estimates), one-time purchases, free services. ASSUMED/ESTIMATE notes flag guessed numbers. Feeds `scripts/cost_report.py`. |
| `backups/*.json` + `backups/*.mp4` | Evergreen backup bank (3 videos) used when QA fails |
| `QA_LOG.md` | Per-run QA issue log |

---

## Key invariants

- Background MP4s are gitignored (`assets/backgrounds/*.mp4`). Never commit video files. **One deliberate exception:** `assets/guide/*.mp4` — the curated recurring-statue library, which CI must find on a fresh checkout. Keep it under ~80MB.
- Quotes must be genuine public-domain Stoic text. Never fabricate or misattribute.
- The `youtube.force-ssl` scope is required for thumbnails AND comments. If either returns 403, the refresh token needs re-scoping via `scripts/auth_setup.py`.
- `data/posts.csv` is the single source of truth for rotation history and quote dedup. Do not delete rows.

---

### Boil the ocean

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to 'table this for later' when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't 'good enough' — it's 'holy shit, that's done.' Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.
