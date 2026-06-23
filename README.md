# Stoic Shorts Bot

Fully automated faceless Stoicism YouTube Shorts pipeline. Runs entirely on GitHub Actions — no server, no manual work after setup. Posts daily, self-heals on render failures, and improves itself weekly using analytics.

```
Claude API → ElevenLabs TTS → ffmpeg render → QA check → YouTube upload → pinned comment
```

## What it does

**Every day at 16:00 UTC:**
- Generates a Stoic quote, hook, voiceover script, CTA, and engagement question via Claude
- Synthesises the voice with ElevenLabs (word-level timing for karaoke captions)
- Fetches a fresh portrait background from Pexels → Pixabay → synthetic ffmpeg fallback
- Renders a 1080×1920 Short with karaoke captions, Ken Burns motion, hook card, and hook sound
- Runs an automated QA check (frame extraction + transcript diff via Claude Haiku)
- If QA fails: applies corrections (darken grade, shift margins, swap background) and retries up to 3×
- If all 3 attempts fail: uploads a pre-rendered evergreen backup and opens a GitHub Issue
- Uploads to YouTube with series framing (`Day N | quote — Author`)
- Posts an engagement question as a comment under the video
- Logs everything to `data/posts.csv` and `QA_LOG.md`
- Tops up the backup bank to at least 3 videos after a successful post

**Every day at 06:00 UTC (`auto-improve.yml`):**
- Claude Code reads `QA_LOG.md` and `analytics.json`, fixes any recurring defects in the source files, and on Mondays proposes one analytics-driven strategy improvement

**Every Saturday at 04:00 UTC (`refresh-assets.yml`):**
- Downloads 5 fresh portrait background videos from Pexels/Pixabay into `assets/backgrounds/`
- Checks trending YouTube Shorts and updates `data/hook_preset` to the best-matching hook sound style

---

## One-time setup

### 1. Google Cloud + YouTube OAuth (~15 min, done once)

1. Create the brand's YouTube channel.
2. [console.cloud.google.com](https://console.cloud.google.com) → create a project.
3. **APIs & Services → Library** → enable **YouTube Data API v3**.
4. **OAuth consent screen → External** → fill basics → add your Google account as a **Test user**.
5. **Credentials → Create credentials → OAuth client ID → Desktop app** → download JSON → save as `client_secret.json` in the project root.
6. Locally:
   ```bash
   pip install google-auth-oauthlib google-api-python-client
   python src/auth_setup.py
   ```
   Follow the URL printed, approve in your browser, paste the code back. It prints `CLIENT_ID`, `CLIENT_SECRET`, and `REFRESH_TOKEN`.

### 2. Pexels API key (free)
Sign up at [pexels.com](https://www.pexels.com) → [pexels.com/api/docs](https://www.pexels.com/api/docs) → your key is shown at the top.

### 3. Pixabay API key (free, optional)
Sign up at [pixabay.com](https://pixabay.com) → [pixabay.com/api/docs](https://pixabay.com/api/docs) → your key is shown after login. Falls back to synthetic backgrounds if not set.

### 4. GitHub secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `ELEVENLABS_API_KEY` | elevenlabs.io |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice library (optional, defaults to Adam) |
| `YOUTUBE_CLIENT_ID` | from `auth_setup.py` output |
| `YOUTUBE_CLIENT_SECRET` | from `auth_setup.py` output |
| `YOUTUBE_REFRESH_TOKEN` | from `auth_setup.py` output |
| `PEXELS_API_KEY` | pexels.com/api/docs |
| `PIXABAY_API_KEY` | pixabay.com/api/docs (optional) |

### 5. Test run

**Actions tab → daily-short → Run workflow.**

The first step is a secrets pre-flight check — it makes a lightweight test call to each API and prints PASS/FAIL/SKIP before doing anything else. Fix any FAILs before the workflow proceeds.

---

## Project structure

```
src/
  content.py          — Claude generates quote, hook, voiceover, CTA, pinned comment
  tts.py              — ElevenLabs synthesis with word-timing fallback
  render.py           — ffmpeg: background, Ken Burns, hook card, karaoke captions, hook sound
  backgrounds.py      — Pexels → Pixabay → synthetic lavfi → local rotation
  publish.py          — YouTube upload + comment posting (OAuth)
  promo.py            — product CTA injection for descriptions and comments (PROMO_*)
  analytics.py        — YouTube Data API stats pull
  logbook.py          — posts.csv append
  auth_setup.py       — one-time OAuth token generator (run locally)

tests/
  test_promo.py       — unit tests for promo CTA rotation and enable/disable logic

scripts/
  daily_post.py       — main orchestrator: render → QA → retry → upload → backup
  qa_check.py         — frame extraction + Whisper transcript + Claude Haiku QA
  check_secrets.py    — pre-flight validator; tests every API key before the pipeline runs
  fetch_analytics.py  — pulls analytics.csv → analytics.json for auto-improve
  refresh_backgrounds.py — downloads fresh portrait videos into assets/backgrounds/
  update_hook_sound.py   — checks trending Shorts, writes best preset to data/hook_preset

data/
  posts.csv           — post history (date, theme, quote, author, URL)
  analytics.csv       — per-video view/like/comment stats
  hook_preset         — current hook sound: bass_impact | cinematic | whoosh | minimal

assets/backgrounds/   — portrait MP4s used as fallback / rotated when Pexels is unavailable
backups/              — pre-rendered evergreen Shorts (MP4 + JSON sidecar)

QA_LOG.md             — automated QA results per run
IMPROVEMENTS.md       — changelog written by the auto-improve workflow
```

## Workflows

| Workflow | Schedule | What it does |
|---|---|---|
| `daily-short.yml` | 16:00 UTC daily | Full post pipeline |
| `auto-improve.yaml` | 06:00 UTC daily | Claude Code self-improvement loop |
| `refresh-assets.yml` | 04:00 UTC Saturdays | Download backgrounds + update hook preset |
| `pull-analytics.yml` | Scheduled | Pull YouTube stats → analytics.csv |

---

## Closed-loop self-improvement system

The bot runs two feedback loops that continuously improve content quality without human intervention.

### Loop 1 — Pre-upload visual QA gate (`src/visual_qa.py`)

Every rendered video is scored by Claude Opus **before** it uploads. The gate extracts six frames — four from the hook window (first 1.5 seconds, because the hook matters most) and two from the body — and scores four dimensions:

| Dimension | What it measures |
|---|---|
| `hook_strength` | Does the opening compel a viewer to stay? |
| `text_legibility` | Are all text overlays crisp and readable at phone size? |
| `pacing` | Does visual rhythm match the audio pace? |
| `scroll_stop_potential` | Would a casual scroller stop on the first frame? |

Each dimension is scored 0–10. The gate returns three possible verdicts:

| Verdict | Condition | Action |
|---|---|---|
| `pass` | All scores ≥ pass threshold | Upload normally |
| `flag` | Some scores below pass but above fail | Log to `QA_LOG.md`, upload anyway |
| `fail` | Any score below fail threshold | Log; retry with corrections if `VQA_BLOCK_ON_FAIL=1` |

**Config knobs** (set as env vars in the workflow or locally):

| Env var | Default | Description |
|---|---|---|
| `VQA_ENABLED` | `1` | Set to `0` to skip visual QA entirely |
| `VQA_BLOCK_ON_FAIL` | `0` | Set to `1` to treat hard-fail as a retry trigger |
| `VQA_HOOK_PASS` / `VQA_HOOK_FAIL` | `6.0` / `3.0` | hook_strength thresholds |
| `VQA_TEXT_PASS` / `VQA_TEXT_FAIL` | `7.0` / `4.0` | text_legibility thresholds |
| `VQA_PACING_PASS` / `VQA_PACING_FAIL` | `5.0` / `2.0` | pacing thresholds |
| `VQA_SCROLL_PASS` / `VQA_SCROLL_FAIL` | `6.0` / `3.0` | scroll_stop_potential thresholds |

**Run standalone for debugging:**

```bash
python src/visual_qa.py data/2026-06-23_reel.mp4 \
  --hook "You are wasting your life." \
  --quote "Time is not refunded." \
  --author "Seneca" \
  --theme "time"
```

---

### Loop 2 — Post-publish performance loop (`scripts/strategy_loop.py`)

Runs daily at 10:00 UTC (48+ hours after any upload) via `strategy-update.yml`. For each video in the rolling window:

1. Pulls extended YouTube Analytics metrics: `avg_view_duration`, `avg_view_percentage`, `swipe_away_rate`, `estimated_minutes_watched` (via `src/youtube_analytics.py`, result cached in `data/analytics_extended.json`)
2. Downloads each video's YouTube thumbnail for visual analysis (no re-download of MP4s)
3. Sends the windowed dataset + thumbnails to Claude Opus
4. Claude correlates performance across the window (not single videos, to avoid overfitting)
5. Writes a versioned `data/strategy.md` with "what works" patterns and recommendations
6. Commits and pushes `strategy.md` to main — version history is visible in git log

**The feedback loop closes** because `src/content.py` loads `data/strategy.md` on every content generation call and appends it to the Claude system prompt. Future videos are guided by real performance data automatically.

**Config knobs:**

| Env var | Default | Description |
|---|---|---|
| `STRATEGY_WINDOW_DAYS` | `21` | Rolling analysis window in days |
| `STRATEGY_MIN_AGE_HOURS` | `48` | Min hours after upload before including in analysis |
| `STRATEGY_MAX_VIDEOS` | `20` | Max videos sent to Claude per analysis run |
| `STRATEGY_MIN_VIDEOS` | `5` | Skip if fewer videos available (insufficient data) |
| `STRATEGY_COMMIT` | `1` | Set to `0` to skip git commit (dry-run mode) |
| `YOUTUBE_ANALYTICS_QUOTA_BUDGET` | `200` | Max Analytics API quota units per run |

**Run standalone for debugging:**

```bash
# Dry run — writes strategy.md locally but doesn't commit
STRATEGY_COMMIT=0 python scripts/strategy_loop.py

# Force re-fetch analytics even if cached (useful after token re-scoping)
STRATEGY_COMMIT=0 python src/youtube_analytics.py --window-days 21 --force
```

**YouTube Analytics API scope:**
The extended analytics require the `yt-analytics.readonly` OAuth scope, which is **separate** from the existing scopes. If you see a 403, re-run `scripts/auth_setup.py` with the additional scope and update `YOUTUBE_REFRESH_TOKEN`. The loop fails gracefully on scope errors — it falls back to basic `views` from `analytics.csv` and still generates a strategy doc.

---

## Self-healing retry logic

The pipeline makes up to 3 render attempts. Between each attempt it adjusts env vars based on QA findings:

| QA issue | Correction |
|---|---|
| Text clipped / safe zone | Increase `REEL_CAPTION_MARGINV`, shrink hook font |
| Low contrast / unreadable | Increase `REEL_EXTRA_DARKEN` (+0.08, capped at 0.30), swap background |
| Frozen / black frame | Swap background clip |
| Audio desync | Shift caption margin |

If all 3 attempts are high-severity, a backup video is uploaded and a GitHub Issue is opened.

---

## Hook sound presets

The hook sound is synthesised entirely from ffmpeg lavfi (no binary assets). Updated weekly based on trending Shorts:

| Preset | Description |
|---|---|
| `bass_impact` | Sub-bass punch + transient snap — modern motivation energy (default) |
| `cinematic` | Orchestral harmonic swell → dramatic hit — philosophical/serious |
| `whoosh` | Pink-noise swell + low sine — broadly neutral |
| `minimal` | Clean struck tone + overtone — calm/educational |

---

## Cost

| Service | Cost |
|---|---|
| ElevenLabs | ~$5/mo (Starter plan) |
| Anthropic (Claude) | ~$0.10–0.30/day (Opus for content, Haiku for QA) |
| YouTube Data API | Free (10,000 quota units/day; daily upload uses ~100) |
| Pexels / Pixabay | Free |
| GitHub Actions | Free (public repo) |

---

## Product promo / monetisation link

The bot can automatically append a product CTA to every video description and post a promo comment after each upload. All copy lives in the workflow YAML — no code changes needed to update the link or copy.

### Enable / disable

Set `PROMO_ENABLED` in `.github/workflows/daily-short.yml`:

```yaml
PROMO_ENABLED: "1"   # "0" to disable everything with no side-effects
```

### Config options

| Variable | Default | Description |
|---|---|---|
| `PROMO_ENABLED` | `0` | Master toggle (`1` = on, `0` = off) |
| `PROMO_PRODUCT_NAME` | `The Stoic Reset` | Product name (for reference) |
| `PROMO_PITCH` | `Put Stoicism into practice — my 30-day Stoic journal` | One-line pitch (for reference) |
| `PROMO_URL` | `https://soicism.gumroad.com/l/cslosv` | Gumroad (or any) link included in every CTA |
| `PROMO_COMMENT` | `1` | Post the CTA as a comment after upload (`0` to skip) |
| `PROMO_CTA_VARIATIONS` | *(built-in 3 defaults)* | Pipe-delimited (`\|`) list of 3–5 CTA strings. Rotates daily. Leave unset to use the defaults in `src/promo.py`. |

### Description output (when enabled)

The CTA is appended after the hashtags with a `---` separator:

```
Day 18 of daily Stoic wisdom.

Where in your life is ego blocking your growth?

#stoicism #epictetus ... #Shorts

---
📓 Put Stoicism into practice — The Stoic Reset, my 30-day journal:
https://soicism.gumroad.com/l/cslosv
```

### Custom CTA variations

To override the three built-in CTAs, add `PROMO_CTA_VARIATIONS` to the workflow env with variations separated by `|`:

```yaml
PROMO_CTA_VARIATIONS: "📓 Get The Stoic Reset journal:\nhttps://soicism.gumroad.com/l/cslosv|📖 30 days of Stoic practice:\nhttps://soicism.gumroad.com/l/cslosv"
```

### Required YouTube API scopes

No new scopes are needed. Comment posting (`PROMO_COMMENT=1`) uses `youtube.force-ssl`, which is already requested by `auth_setup.py`. **Pinning** is not available via the YouTube Data API — to pin the promo comment, go to YouTube Studio → Comments → ⋮ → Pin.

---

## Troubleshooting

**Upload fails** → Expired YouTube refresh token. Re-run `python src/auth_setup.py` locally and update `YOUTUBE_REFRESH_TOKEN` in GitHub secrets.

**Comment posting fails with 403** → Refresh token missing `youtube.force-ssl` scope. Re-run `auth_setup.py` (it now requests this scope) and update the secret.

**`quotaExceeded`** → Workflow ran too many times today. YouTube quota resets at midnight Pacific.

**Pexels returns no videos** → Check `PEXELS_API_KEY` is set. The pre-flight check will catch an invalid key. Pipeline falls back to Pixabay → synthetic background automatically.

**Voice too expensive** → Rewrite `synthesize_voice()` in `src/tts.py` — it's isolated on purpose. OpenAI TTS is a drop-in replacement.

**QA always fails** → Check `QA_LOG.md` for the recurring issue. The `auto-improve` workflow reads this and patches the source files automatically.
