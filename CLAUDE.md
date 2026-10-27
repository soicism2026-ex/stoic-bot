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
**Posting cadence:** 2 videos/day since 2026-10-18 (owner: "push it more"; `MAX_POSTS_PER_DAY` defaults to 2 in daily-short.yml). `POST_SLOT_HOURS="0,15"` makes the second post wait for 15:00 UTC so the two are spread; edits rotate authors (`edits.pick`). Six cron slots (03/07/11/15/19/23 UTC) are over-provisioned because GitHub silently drops scheduled runs. Every edit quote AND its citation is checked against the source text (`scripts/validate_quotes.py`, tests). Goal: 500 subs + 3M Shorts views/90d.  
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

## HQ app — the owner's live view (https://claude.ai/artifact/8MtajequXptMk8RUQnSsmx)

The owner watches every agent here from a phone (it is pinned in the Claude sidebar), like the head of a business, and gives feedback here. Source: `hq/forged-hq.html`. Republish with the Artifact tool (`file_path` + `url` from another session). **Every Claude session on this project reports into it.**

- **Live by itself:** the owner's Claude sessions and scheduled tasks (Claude Code Remote connector, from the page, as the owner).
- **`hq/studio`** (bots + channel numbers + next quote on air): built ONLY by `scripts/hq_snapshot.py` (bot runs from GitHub's API, or from the `hq-status` branch that `hq-status.yml` keeps current) and written by the **HQ sync** scheduled task (`trig_01SkthKZdtqimpWg4VpNVUrV`, 6×/day at :47 after each poster cron, no notifications; the app's "Refresh now" fires it). Never hand-edit it.
- **`hq/now`** `{state: working|waiting|idle, headline, detail, next, since, updated, session, helpers[{name,task,status,since}], alerts[{level: warn|bad, text, fix}]}`. Update it (ArtifactData, pinned `if_version`) when you start or finish real work, launch or finish a helper, or start waiting on the owner. Write in plain words: the owner reads it as a status report.
- **`hq/log`** `{items: [{t, who, kind: work|done|post|decision|alert|you, text}]}`: newest first, ≤ 80 items. Add one line per milestone. Bot runs and posts are derived from `hq/studio` automatically: don't log them.
- **`hq/upnext`** `{edit, quote, hook, author, citation, airDay, voice, renderedAt, run, asset, retired[]}`: Apelles' rehearsal of the next Short (see "Quote shelf and rehearsals"). Written ONLY by the HQ sync from the `up-next` release; the page plays `asset` under Next on air only when `edit` is the quote that airs next. `retired` lists replaced rehearsal videos; Varro's weekly shift deletes them.
- **`hq/config`** also maps scheduled tasks to crew: `syncTrigger` (Hermes), `librarian` (Varro, `trig_0131CeoTYCTKpM5pQx4adBsn`).
- **`asks/<id>`** `{title, question, options[{id,label,hint}], status: open, order, created, video?, videos?[{id,label}], crew?}`: `crew` names the bot whose work waits on the answer (e.g. `composer`): the lineup shows it as "Needs you". put every decision you need from the owner here, not just in chat. `video` is an artifact asset id (upload with Artifact `asset: true`). The owner answers in the app, which sets `status: answered, answer, answeredAt` and sends "[HQ decision] <title>: <option>" to Claude. When you act on it, set `outcome` (one line).
- **Messages from the owner** arrive as artifact comments sent to Claude ("[HQ] …" / "[HQ, about X] …") and wake the session that published or watches the HQ. When you pick one up, set its `notes/<id>` to `status: working` (the app shows "Claude is on it" instead of "Not picked up yet"); when it's handled, reply in the thread (ArtifactComments) and set `status: done, reply`. If no session was connected, the note waits in `notes` with `sent: false`. **On session start, read `notes` (status new) and `asks` (answered, no `outcome`) before anything else.** A wake can lag: on 2026-10-21 three messages took 22 hours to arrive. The app flags anything not picked up after 15 minutes and links the owner to this chat, where any message wakes the session.

---

## Quote shelf and rehearsals (owner 2026-10-23: "Why is everybody on call? Get them working")

- **The shelf** is `data/edit_quotes.json`: every edit airs one verified quote, never twice. When it is empty the story bank (1 left) and then generated content (needs Anthropic API credit) take over, so an empty shelf can silence the channel. `python scripts/shelf.py status` = fresh quotes, days left at the live cap, per author; `winners` = recent edits by views (write more like the top); `check FILE` / `add FILE` = the only way new quotes go in (verbatim in `data/sources/`, cited where the source has it, never aired, no overlap, hook 2-9 words without shame, 1-3 `still:` shots, stock searches of at most 3 words, people shots start with "man"). Target 30 days, the HQ warns under 14 (`TARGET_DAYS`, `WARN_DAYS`). Tests: `tests/test_shelf.py`.
- **Varro, the Librarian** = scheduled task `trig_0131CeoTYCTKpM5pQx4adBsn` (Mondays 13:07 UTC), which fires into the chief session: tops the shelf up to 30+ days, data-led by `winners`, copying every quote from the source text, then commits to main. It also deletes the rehearsal videos listed in `hq/upnext.retired`.
- **Apelles' rehearsals**: `edit-preview.yml` runs right after every daily-short run (crons at 08:40 and 19:40 UTC are the backstop: GitHub fired them 2-5 hours late) and renders the NEXT post (DRY_RUN) for the day it airs; its `check` job (`up_next.py need`) skips when that edit is already rehearsed with the sounds the live run will pick (`plan`: music by approval flag + sound effects, so approving music re-rehearses) or two rehearsals failed today: `src/airday.py` sets `REEL_TODAY` so the stock pick, the day's sound pair and the music shuffle match the live run (honoured only in DRY_RUN; a live run can never move its date). `scripts/up_next.py publish` puts `up-next.mp4` (720 px) + `up-next.json` in the `up-next` release (outside git); the HQ sync fetches them (`up_next.py fetch`) and writes `hq/upnext`. A rehearsal that fails shows Apelles as failed hours before the slot. Cost: ~2 extra Brian reads a day. Tests: `tests/test_up_next.py`, `tests/test_airday.py`.

## Pipeline

Each run of `scripts/daily_post.py` does:

1. **Guard** — reads `data/posts.csv`; skips if `posts_today >= MAX_POSTS_PER_DAY` (env, default 3)
2. **Content** — `src/content.py` calls Claude Opus 4.8 for quote, hook, voiceover script, CTA, caption, hashtags, callout words, pinned comment
3. **Voice** — `src/tts.py` calls ElevenLabs with-timestamps endpoint (Brian; the owner's own clone next if `ELEVENLABS_BACKUP_VOICE_ID` is set); falls back to edge-tts (Steffan)
3b. **Listen-check** — `src/listen_check.py`: ElevenLabs Scribe transcribes the narration and it must match the script (fails on 2+ consecutive missing words, recall < 0.90, or 3+ extra words). A bad read is voiced again once; two DIFFERENT bad reads publish nothing that run and set the content aside after 2 blocked runs. The same words missed twice = the listener's blind spot, so it airs. Any failure to listen fails open. `LISTEN_CHECK=0` switches it off
4. **Music** — `src/music.py` downloads a royalty-free Pixabay track to `assets/music/`
5. **Render** — `src/render.py` builds 1080×1920 MP4 via ffmpeg. The shot list is SIZED TO THE NARRATION by `daily_post.background_flavors()`: each written b-roll beat is requested as many times as needed to keep every frame under `MAX_SECONDS_PER_CLIP` (4.5s), capped at `MAX_SHOTS_PER_BEAT` (3, the size of the stock relevance window). Story format = 4 beats × 3 = 12 clips over ~52s ≈ a cut every 4.4s; guide formats keep `[statue, b0..b3, statue]`. Render time is FLAT in clip count (measured 151s/145s/144s at 4/8/12) because each clip is trimmed to `dur / n_bg`. Hook text, quote text, cinematic score mixed
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
| `src/tts.py` | ElevenLabs Brian narrates every post (with-timestamps endpoint: real per-word timings for karaoke). Steffan (edge-tts) is the fallback; gTTS last. |
| `src/render.py` | ffmpeg pipeline. 3-clip background (clip 0 = theme query, clip 1 = dramatic nature, clip 2 = ancient stone). Hook text at top, quote + author centred, music mixed. Captions OFF by default (`REEL_CAPTIONS=0`). |
| `src/kling.py` | Generated MOTION backgrounds via `api.higgsfield.ai` (Kling 3.0 Standard). OFF unless `REEL_KLING_BG=1` + `HIGGSFIELD_API_KEY`. ONE request per narration beat, not per slot: a 15s `multi_prompt`/`multi_shots` master is cut into the three ~4.4s angle slots that share a query, so a 4-beat story costs 4 requests. Spend cap, hard deadline, and falls through to stock on any failure. |
| `src/imagegen.py` | PIVOT: text-to-image backgrounds. When `REEL_IMAGE_BG=1` + `OPENAI_API_KEY`, each clip is an AI cinematic still depicting the exact narration beat (gpt-image-1) → Ken Burns clip. OFF by default; any failure falls back to stock. |
| `src/backgrounds.py` | Guide library (bookend slots only) → generated (imagegen) → Pixabay → Pexels → synthetic lavfi fallback. Stock picks from top-`REEL_BG_TOP` (=3) most-relevant results, not a deep index. `clip_idx` drives diversity: idx 0 = theme-specific query, idx 1 = `DIVERSITY_QUERIES[0]` (nature), idx 2 = `DIVERSITY_QUERIES[1]` (stone). |
| `src/music.py` | 3-track pool: `dark_ambient`, `ancient_minimal`, `focus_underscore`. Analytics-weighted after 5 posts per track, LRU before that. Pixabay music API. |
| `src/publish.py` | YouTube Data API v3 upload. `set_thumbnail()` requires `youtube.force-ssl` scope. |
| `src/edit_music.py` | Music for the edit format (owner's choice, 2026-10-12): ORIGINAL tracks generated in the style of the songs he named (ACE-Step 1.5, MIT, commercial use allowed; text prompts only, no song names, no reference audio), owned outright so Content ID has nothing to match. `data/edit_music.json` holds each track's drop start, provenance and `approved` flag. Only approved tracks air, playlist-style shuffle rebuilt from posts.csv; Kevin MacLeod (`src/epic_music.py`) is the fallback while nothing is approved. Airing since 2026-10-27: 11 ElevenLabs tracks (the owner's new 1 and 2, then all nine of round 3: "All are good rotate them"). `cut_start` begins a cut early when a late drop would run out before the Short ends (render.py loops the bed). `REEL_EDIT_MUSIC=<id>` auditions a track, honoured only in `DRY_RUN`. |
| `scripts/make_eleven_music.py` | Orpheus's upgrade (owner 2026-10-25: "find much better music"): ElevenLabs Music v2.5 from `data/edit_music_plans_eleven.json` (composition plans: 5 s build, then the drop; two rebuild songs 1 and 9 from 30 s references). `preflight` is free (`/v1/music/plan`: key permission + copyright filter); `generate` keeps a 12k-credit reserve for Brian, never retries a timed-out compose, masters to -16 LUFS, finds the drop, runs a Scribe check for stray words and stores each track ENCRYPTED and UNAPPROVED; `sampler` builds the numbered ear test. Research: scratchpad report summarised in decisions.md 2026-10-25; backup = Google Lyria 3.5 (needs a paid Gemini key), escalation = Epidemic Sound. Done for now (2026-10-27: round 3 approved whole): a new round only when the owner asks. |
| `src/vault.py` | Private storage in a public repo: AES-256 gpg files (`*.mp3.gpg`) with the `MUSIC_KEY` secret. ElevenLabs' Music Terms forbid making tracks downloadable. `edit_music` decrypts into a temp dir for one render; without the key, encrypted tracks are skipped, never broken. |
| `scripts/make_edit_music.py` | `setup` builds acestep.cpp (pinned commit) + downloads the GGUF models; `generate` makes one style from `data/edit_music_styles.json`; `add` imports a wav (constant-gain to -16 LUFS: single-pass loudnorm flattened the drop); `merge` adds tracks to the bank UNAPPROVED. |
| `scripts/music_sampler.py` | One phone video, 14s of each candidate track from its drop behind a numbered title card, for the owner to pick by number. |
| `src/listen_check.py` | The listen-check (pipeline step 3b, owner 2026-10-21): Scribe transcript vs script, word-aligned with forgiveness for split/misspelt names. `check()` never raises: `ok=None` means it could not listen and the caller fails open. Tests: `tests/test_listen_check.py`. |
| `src/sfx.py` | ElevenLabs sound effects for edits: an `impact` on the first frame, a `whoosh` into the quote. LIVE since 2026-10-22: daily-short sets `REEL_EDIT_SFX=1` and the edit style pack turns it into `REEL_SFX`. The owner removed both whooshes ("slash" 2026-10-25, "swoosh" 2026-10-27), so only the two impacts are approved: one on each edit's first frame, picked per day, and no whoosh. Only `approved` sounds air; DRY_RUN previews may audition any (`REEL_SFX_IMPACT=<id>`). render.py mixes them after the voice+music mix (so the music doesn't duck under them). |
| `scripts/make_sfx.py` | Generates the sound bank from written descriptions (`/v1/sound-generation`), trimmed to the first transient, faded, peak-normalised, saved to `assets/sfx/` and recorded UNAPPROVED with provenance. |
| `src/promo.py` | Configurable CTA injection into description + comment. All copy in env vars. Toggle with `PROMO_ENABLED`. |
| `src/analytics.py` | Pulls YouTube stats to `data/analytics.csv`. |
| `src/logbook.py` | Appends each post to `data/posts.csv`. |
| `src/publish_instagram.py` | Cross-posts to Instagram Reels via Meta Graph API. Requires `IG_ACCESS_TOKEN` + `IG_USER_ID`. Currently skipped: since 2026-10-21 the `IG_ACCESS_TOKEN` secret holds a malformed multi-line value (Graph API: "Cannot parse access token"). Its single-letter lines make GitHub mask every `e` and `d` in daily-short logs (logs of workflows that don't read the IG secrets are clean), so read those logs with that in mind. Fix = the owner re-pastes a valid long-lived token as one line, or deletes the secret. |
| `scripts/daily_post.py` | Main orchestrator. Self-healing retry loop. Backup bank logic. |
| `scripts/qa_check.py` | Video QA: frozen frames, audio desync, contrast, safe-zone clipping. Returns pass/fail + severity. |
| `scripts/reply_to_comments.py` | Auto-replies to best viewer comments. Filters own channel by `videoOwnerChannelId == authorChannelId` (channel ID comparison, not display name). Max 5 replies/run. Receptivity screen (`_is_receptive`, Haiku + `_is_dismissive` keyword prefilter) engages ONLY viewers who genuinely connect with the message — skips trolls/mockery/bad-faith to build community and avoid amplifying detractors; fails closed. |
| `scripts/rethumbnail.py` | One-off: re-generates and uploads thumbnails for all past videos. `--only-missing` skips videos that already have a `maxres` thumbnail. |
| `scripts/improve_loop.py` | The brain of the continuous improvement loop. Joins posts.csv + analytics.csv, evaluates last run's outcome, picks next focus area, writes a data-grounded prompt to `data/improve_prompt.txt`, and saves run memory to `data/improve_state.json`. |
| `scripts/prune_videos.py` | Unlists underperforming videos. |
| `scripts/prep_guide_clips.py` | Normalises hand-generated GUIDE clips into `assets/guide/` (1080×1920, trimmed, muted, compressed, sequentially named) so they can be committed. Prompts to generate them: `docs/guide_clip_prompts.md`. |
| `scripts/strategist.py` | Frontinus, the free strategist (owner 2026-10-27: "fire our strategist, find some who will do this for free"): daily, from posts/analytics/retention already in the repo, compares edits at day 3 against the edits aired within a week of them (reach changed a lot between seasons), by theme, author, hook form and length, quote length, music, voice, slot and weekday. Needs 3+ settled edits before calling a winner or loser. Writes `data/strategy.md` (content.py's prompt) and `data/strategy.json`, whose `theme_rank` makes `edits.pick` air winning themes first within the author rotation. Replaced `scripts/strategy_loop.py` (Agrippa: Claude Opus through the paid API, never produced a strategy, now unused). Tests: `tests/test_strategist.py`. |
| `scripts/shelf.py` | The quote shelf: runway (`status`), what's working (`winners`), and the door new quotes come through (`check`/`add`). See "Quote shelf and rehearsals". |
| `scripts/up_next.py` | Carries Apelles' rehearsal of the next Short from edit-preview (`publish`, to the `up-next` release) to the HQ sync (`fetch`). |
| `src/airday.py` | The day a render is FOR: today on a live run; the next post's air day (`REEL_TODAY`) on a DRY_RUN rehearsal. Every day-keyed pick goes through it. |
| `scripts/hq_snapshot.py` | Builds the HQ app's `hq/studio` document: bots' last/next runs from GitHub's public Actions API, the Producer's next posting try (cap, slots, min gap read from daily-short.yml), channel numbers from channel_stats.csv (7/90-day views, goal progress), latest Shorts with views, the next quote on air (with its edit id) and the shelf's runway. Tests: `tests/test_hq_snapshot.py`. |
| `hq/forged-hq.html` | The HQ app's page (see "HQ app" above). Capabilities: db, user, mcp (Claude Code Remote: list_sessions, list_triggers, fire_trigger), comments (sendToClaude), sample ("Explain what's happening"), assets. |
| `scripts/cost_report.py` | Cost agent: reads `data/costs.json` (subscriptions incl. Claude + ElevenLabs, one-time buys), computes monthly burn, all-time spend, cost per Short / per 1k views. Standalone + embedded in the weekly channel report. |

---

## GitHub Actions workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `daily-short.yml` | cron 3×/day | Main pipeline: post → analytics → prune → reply |
| `pull-analytics.yml` | cron daily | Analytics-only pull |
| `strategy-update.yml` | cron daily 10:00 UTC | Frontinus (`scripts/strategist.py --write`): no secrets, no paid API; commits `data/strategy.md` + `data/strategy.json` |
| `refresh-assets.yml` | manual | Pre-download background clips to `data/hook_preset` |
| `rethumbnail.yml` | manual | Backfill thumbnails for old videos |
| `backfill.yml` | manual | Re-process old posts |
| `repost.yml` | manual | Re-upload a specific video |
| `ci.yml` | pull request only | Lint gate: compiles every Python file, validates workflow YAML (it does NOT run pytest, and has not run since June) |
| `edit-preview.yml` | after each daily-short run, 08:40 + 19:40 UTC backstop, manual | Apelles: renders the next edit with the full pipeline, `DRY_RUN` (nothing uploaded or logged), for the day it airs. Scheduled runs (and `up_next: true`) put it in the `up-next` release for the HQ. Manual inputs: `music` auditions a track (never goes to the HQ), `voice` (brian/steffan; brian checks the key and fails if Brian didn't speak), `sfx` on/off |
| `make-sfx.yml` | manual | Generates the ElevenLabs sound effects and commits them UNAPPROVED |
| `make-eleven-music.yml` | manual | Orpheus: `preflight` (free) or `generate` (ElevenLabs Music, ~6.8k credits for 10 tracks): commits the tracks encrypted and unapproved, then puts a numbered sampler, encrypted to the HQ session's one-time public key (`recipient` input, base64), in the `music-sampler` release. Plaintext audio never leaves the runner |
| `make-music.yml` | manual | One parallel job per style: generates original edit tracks on free runners, commits them UNAPPROVED, attaches a sampler video |
| `hq-status.yml` | whenever a bot starts or finishes | Publishes the bots' latest runs to the `hq-status` branch (one force-pushed file) for the HQ app: the HQ sync session has no GitHub API access but can read it over git |
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
| `HF_KEY` | `main.py` — official Higgsfield SDK example (Seedance 2.5). `KEY_ID:KEY_SECRET`. Locally in `.env.local` (git-ignored; template `.env.example`). kling.py also accepts it |
| `HIGGSFIELD_API_KEY` | kling.py — generated MOTION backgrounds (Kling 3.0 REST API). `KEY_ID:KEY_SECRET`. Inert unless `REEL_KLING_BG=1` |
| `REPLICATE_API_TOKEN` | tts.py — Chatterbox voice (primary; open-source, beats ElevenLabs in blind tests, pay-per-second) |
| `OPENAI_API_KEY` | imagegen.py — activates AI-generated backgrounds (optional, paid) |
| `MUSIC_KEY` | src/vault.py: decrypts the ElevenLabs edit tracks (`*.mp3.gpg`). A passphrase the owner made up himself; nobody else ever sees it. daily-short, edit-preview, repost, make-eleven-music |
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

**Format rotation** (subscriber-first consolidation 2026-07-18): `["rule", "quote", "minimal", "story"]` — one of each per day at 4/day, all sharing the classic visual identity. pov + challenge (caption_only style) cut early: weakest numbers and broke the channel's visual coherence (churn risk). "rule" is the exploration star (436v). Style-pack/caption_only code remains for future tests. Style packs (daily_post `STYLE_PACKS`): pov/challenge render `caption_only` (NO quote card; big centred karaoke captions carry the words) with generated diegetic ambience (rain_night / wind_dawn) replacing the music bed; story/rule keep the classic card with an `embers` bed. The content engine emits `broll_queries` — 4 stock-video searches literally depicting successive voiceover beats. daily_post assembles the slot list in `background_flavors()` — `[statue_guide, b0..b3, statue_guide]` for guide formats, and for `truestory` (which drops the bookends) each beat repeated to hit the cut-rhythm bar: `[b0,b0,b0,b1,b1,b1,...]`, 12 slots over ~52s. Adjacent slots sharing a query do NOT return the same footage — render.py offsets the pick per slot (`REEL_BG_OFFSET = base + i*7`) and backgrounds.py picks index `(day + offset) % 3`, so three requests of one query give three different clips, each with a different camera move (`_MOVES[i % 6]`). The camera move is per-segment, so shorter shots also move visibly faster — the fix for `pacing`, the worst-scoring and most-flagged dimension in `QA_LOG.md` (mean 5.4/10 over 206 reviews, 62 flags)

**Voice** (owner's pick by ear in the HQ, 2026-10-21): ElevenLabs "Brian" (library voice `Gubgw9l4dtIoQA9YZHgx`) narrates EVERY post, `ELEVENLABS_POSTS_PER_DAY="4"` in daily-short.yml (both daily posts plus a same-day backup: one narrator). Starter plan, 40k characters a month; 2 posts a day use about 8k. tts.py's live credit guard refuses to overspend, and if ElevenLabs fails or the month runs out the free fallback is Steffan (edge-tts `en-US-SteffanNeural`, the narrator from 2026-08-30 to 2026-10-21, kept as the only voice in `VOICE_POOL`). Chatterbox is off (vetoed 2026-08-07; `CHATTERBOX_LOCAL` 0, no `REPLICATE_API_TOKEN` secret). `data/posts.csv` logs the voice that ACTUALLY spoke (`tts.LAST_VOICE_NAME`); a failed ElevenLabs call is credited to the fallback, never to Brian.

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
| `data/doctrine.md` | The owner's PERMANENT creative standing orders (ICP, hook psychology, format philosophy). Injected into every content generation call. Never overwritten by automation — unlike `data/strategy.md`, which Frontinus (`scripts/strategist.py`) rewrites daily at 10:00 UTC. |
| `data/strategy.json` | Frontinus's daily read: groups with day-3 views, lift against their own week, retention and a verdict; `theme_rank` (2 winning, 1 even or too few, 0 losing) orders the edit shelf. |
| `data/posts.csv` | All posts: date, theme, quote, author, caption, video_url, video_id, voice_name, music_track, hook, experiment, format |
| `data/analytics.csv` | Per-video view/like/comment snapshots |
| `data/replied_comments.csv` | Comment IDs the bot has already replied to |
| `data/improve_state.json` | Improvement loop memory: iteration count, current focus, focus history with before/after metrics and verdicts, metrics snapshot at each focus start |
| `data/edit_music.json` | Edit music bank: file, drop start, label, the song whose style it follows, provenance (model, prompt, seeds, date) and the owner's `approved` flag. Approving a track = setting it `true`. |
| `data/sfx.json` | Sound-effect bank: id, role (impact/whoosh), file, label, provenance (model, prompt, settings, date, licence) and the owner's `approved` flag. |
| `data/edit_music_styles.json` | The 9 style descriptions (one per song the owner named). Sound only: tests fail if a prompt names a song or artist. |
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
