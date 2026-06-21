# Stoic Shorts Bot — CLAUDE.md

Faceless Stoicism YouTube Shorts channel. Fully automated: content → voiceover → render → upload → comment reply. Runs on GitHub Actions, zero human intervention per day.

**Channel:** forged.in.stoicism  
**Posting cadence:** 4 videos/day at 07:00, 12:00, 17:00, 22:00 UTC  
**Product:** The Stoic Reset journal — https://soicism.gumroad.com/l/cslosv

---

## Pipeline

Each run of `scripts/daily_post.py` does:

1. **Guard** — reads `data/posts.csv`; skips if `posts_today >= MAX_POSTS_PER_DAY (4)`
2. **Content** — `src/content.py` calls Claude Opus 4.8 for quote, hook, voiceover script, CTA, caption, hashtags, callout words, pinned comment
3. **Voice** — `src/tts.py` calls ElevenLabs with-timestamps endpoint; falls back to edge-tts if no key
4. **Music** — `src/music.py` downloads a royalty-free Pixabay track to `assets/music/`
5. **Render** — `src/render.py` builds 1080×1920 MP4 via ffmpeg (3 background clips, hook text, quote text, music mixed at 7% volume)
6. **QA** — `scripts/qa_check.py` checks for frozen frames, audio desync, unreadable text; up to 3 render attempts with auto-corrections
7. **Upload** — `src/publish.py` posts to YouTube as a Short with optimised title/tags/description
8. **Thumbnail** — `render.py:generate_thumbnail()` generates 1080×1920 JPEG (big hook text, dark cinematic grade, gold accent), uploaded via YouTube API
9. **Comments** — pinned engagement question + promo CTA posted as comments
10. **Log** — `src/logbook.py` appends row to `data/posts.csv`
11. **Backup top-up** — if backup bank < 3 videos, renders and QA-checks one evergreen short and stores it in `backups/`

After the main post loop, the workflow runs:
- `src/analytics.py` — pulls view/like/comment counts to `data/analytics.csv`
- `scripts/prune_videos.py` — unlists videos below a view threshold
- `scripts/reply_to_comments.py` — auto-replies to up to 5 top viewer comments with Claude Haiku

---

## Source files

| File | Role |
|------|------|
| `src/content.py` | Claude Opus content generation. Author rotation (Big5 × 4 days, Chrysippus × 1), theme LRU rotation, format rotation (3 quote : 1 list). Hard block-list of previously used quotes injected into prompt. |
| `src/tts.py` | ElevenLabs primary (Brian → George → Adam, analytics-weighted). edge-tts fallback when no key. Returns per-word timings for karaoke. |
| `src/render.py` | ffmpeg pipeline. 3-clip background (clip 0 = theme query, clip 1 = dramatic nature, clip 2 = ancient stone). Hook text at top, quote + author centred, music mixed. Captions OFF by default (`REEL_CAPTIONS=0`). |
| `src/backgrounds.py` | Pixabay primary, Pexels secondary, synthetic lavfi fallback. `clip_idx` drives diversity: idx 0 = theme-specific query, idx 1 = `DIVERSITY_QUERIES[0]` (nature), idx 2 = `DIVERSITY_QUERIES[1]` (stone). |
| `src/music.py` | 3-track pool: `dark_ambient`, `ancient_minimal`, `focus_underscore`. Analytics-weighted after 5 posts per track, LRU before that. Pixabay music API. |
| `src/publish.py` | YouTube Data API v3 upload. `set_thumbnail()` requires `youtube.force-ssl` scope. |
| `src/promo.py` | Configurable CTA injection into description + comment. All copy in env vars. Toggle with `PROMO_ENABLED`. |
| `src/analytics.py` | Pulls YouTube stats to `data/analytics.csv`. |
| `src/logbook.py` | Appends each post to `data/posts.csv`. |
| `src/publish_instagram.py` | Cross-posts to Instagram Reels via Meta Graph API. Requires `IG_ACCESS_TOKEN` + `IG_USER_ID`. Currently skipped (Meta dev account pending). |
| `scripts/daily_post.py` | Main orchestrator. Self-healing retry loop. Backup bank logic. |
| `scripts/qa_check.py` | Video QA: frozen frames, audio desync, contrast, safe-zone clipping. Returns pass/fail + severity. |
| `scripts/reply_to_comments.py` | Auto-replies to best viewer comments. Filters own channel by `videoOwnerChannelId == authorChannelId` (channel ID comparison, not display name). Max 5 replies/run. |
| `scripts/rethumbnail.py` | One-off: re-generates and uploads thumbnails for all past videos. `--only-missing` skips videos that already have a `maxres` thumbnail. |
| `scripts/improve_loop.py` | The brain of the continuous improvement loop. Joins posts.csv + analytics.csv, evaluates last run's outcome, picks next focus area, writes a data-grounded prompt to `data/improve_prompt.txt`, and saves run memory to `data/improve_state.json`. |
| `scripts/prune_videos.py` | Unlists underperforming videos. |

---

## GitHub Actions workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `daily-short.yml` | cron 4×/day | Main pipeline: post → analytics → prune → reply |
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

**Format rotation**: `["quote", "quote", "quote", "list"]` — 3 personal quote posts then 1 numbered-rules list

**Voice rotation**: Brian (preferred) → George → Adam, analytics-weighted after 5 posts each, LRU before that. Override with `ELEVENLABS_VOICE_ID`.

---

## Video structure (render.py)

```
[0:00–0:02] Hook text fades in (top of frame, large white caps)
[0:02+    ] Quote text + author name centred (gold accent, serif)
[full     ] Background: 3 × ~10s clips with Ken Burns zoom + cinematic grade
[full     ] Background music at 7% volume under voiceover
```

Background grade: unsharp sharpen → bloom → film grain → vignette → eq darken → per-clip colour LUT.

Thumbnail: 1080×1920 JPEG. Hook text at 130px all-caps (last line in gold #FFB830), layered dark gradient overlay, thin gold separator line, author credit below, gold corner brackets.

---

## Data files

| File | Contents |
|------|----------|
| `data/posts.csv` | All posts: date, theme, quote, author, caption, video_url, video_id, voice_name, music_track |
| `data/analytics.csv` | Per-video view/like/comment snapshots |
| `data/replied_comments.csv` | Comment IDs the bot has already replied to |
| `data/improve_state.json` | Improvement loop memory: iteration count, current focus, focus history with before/after metrics and verdicts, metrics snapshot at each focus start |
| `backups/*.json` + `backups/*.mp4` | Evergreen backup bank (3 videos) used when QA fails |
| `QA_LOG.md` | Per-run QA issue log |

---

## Key invariants

- Background MP4s are gitignored (`assets/backgrounds/*.mp4`). Never commit video files.
- Quotes must be genuine public-domain Stoic text. Never fabricate or misattribute.
- The `youtube.force-ssl` scope is required for thumbnails AND comments. If either returns 403, the refresh token needs re-scoping via `scripts/auth_setup.py`.
- `data/posts.csv` is the single source of truth for rotation history and quote dedup. Do not delete rows.

---

### Boil the ocean

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to 'table this for later' when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't 'good enough' — it's 'holy shit, that's done.' Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.
