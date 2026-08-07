# Owner Decisions Log — the channel's memory

**Purpose:** every directive the owner gives Claude (in chat) is recorded here so
it survives across sessions, context resets, and machines. Claude MUST read this
file at the start of any work on this repo, honor everything in it, and APPEND a
dated entry whenever the owner issues a new preference, veto, or decision.
Newest entry wins on conflict. Never delete history — strike through and add the
superseding entry.

Sibling files:
- `data/doctrine.md` — the CREATIVE philosophy (ICP, hook psychology, emotional
  core). Injected into every content-generation call.
- `CLAUDE.md` — technical/system documentation.
This file is for OPERATIONAL decisions and taste vetoes.

---

## Voice
- **2026-07-15** Paid ElevenLabs "Brian" (owner's library voice `Gubgw9l4dtIoQA9YZHgx`)
  voices the FIRST post of each day. Budget: Starter plan (30k chars/mo);
  `ELEVENLABS_POSTS_PER_DAY=1`; live credit guard; never overspend.
- **2026-07-15** VETO: "Andrew" (en-US-AndrewNeural) — owner listened, rejected after 1 post.
- **2026-07-16** VETO: "BrianEdge" (en-US-BrianNeural) — owner rejected (both caption_only posts).
- **Standing:** Christopher (en-US-ChristopherNeural) is the approved free voice.
  Any new voice requires the owner's ear before becoming default.

- **2026-07-29** PRIMARY VOICE → **Chatterbox** (Resemble AI, MIT) via Replicate,
  owner's choice after finding WanGP. Rationale: open source, beat ElevenLabs in
  blind listener tests (65.3% vs 24.5%), pay-per-second (~$1-3/mo) vs a
  subscription — and the ElevenLabs key was 401'ing anyway. Chain is now
  Chatterbox → ElevenLabs (legacy) → edge-tts → gTTS; any failure degrades the
  voice, never the channel. Tuned calm/deliberate: exaggeration 0.45,
  cfg_weight 0.35. Needs the `REPLICATE_API_TOKEN` secret.
- **2026-07-29** ACCEPTED TRADEOFF: Chatterbox returns no word-level timestamps
  (ElevenLabs did), so karaoke captions use duration-estimated timings. Fine at
  2-word chunk granularity; revisit if captions ever look out of sync.
- **2026-07-29** WanGP (Wan2GP) evaluated: real and excellent, but it is a LOCAL
  app needing a 6GB+ VRAM GPU. Owner's GTX 1650 Super has 4GB → local video
  generation is NOT viable, and CI runners have no GPU at all. Use the hosted
  APIs of the same open models instead. Do not re-propose local WanGP unless the
  GPU changes.

- **2026-07-30** Chatterbox BENCHMARKED on a free CPU runner: ~99s/post,
  8.5x realtime, 4 cores, no GPU — PASS. Repo is public so those minutes cost
  $0. Self-hosted engine (`_synthesize_chatterbox_local`) is built and gated
  behind repo variable `CHATTERBOX_LOCAL=1`; chain is local → Replicate →
  edge-tts → gTTS.
- **2026-07-30** MEASURED pacing (samples/chatterbox_*.mp3, 39-word script):
  single-shot at 0.45/0.35 = 222 wpm AND truncated the script (10.5s vs 15.3s).
  Sentence-chunking is a CORRECTNESS fix, not just pacing. New defaults
  exaggeration 0.35 / cfg_weight 0.25 / 0.40s sentence gap = 153 wpm, inside
  the 120-150 target for calm narration. Awaiting owner's ear before enabling.
- **2026-08-06** VERDICT: owner picked **variant B** by ear — exaggeration 0.45,
  cfg_weight 0.35, 0.25s sentence gap, **180 wpm**. His reason, which is the
  actual rule here: *"I like B since you have some time to think about the
  background video between chunks."* The pauses are the FEATURE — they give the
  viewer a beat to take in the background clip between lines. **Do NOT retune
  toward the 120-150 wpm textbook range**; that measurement was mine, this
  verdict is his ear, and his wins. Locked by `tests/test_voice_config.py`.
- **2026-08-06** `CHATTERBOX_LOCAL` is now **ON by default** (code default and
  workflow), so voice costs $0 with no repo variable to set. Chain: local
  Chatterbox → Replicate → ElevenLabs (legacy) → edge-tts → gTTS. The dep
  install is `continue-on-error` — a broken torch wheel degrades the VOICE,
  never stops the post. Opt out with repo variable `CHATTERBOX_LOCAL=0`.
  ElevenLabs ($5/mo, key currently 401ing) is now dead weight — cancel it once
  a few posts have shipped on the local voice.

- **2026-07-30** Hugging Face free tier evaluated as a voice backend: NOT viable.
  Free accounts get only **$0.10/month** of Inference Provider credits and ~5
  min/day of ZeroGPU (an interactive-Spaces perk, not a stable automation API);
  PRO is $9/mo. Our 3 posts/day need ~5 min/day of compute — right at the free
  ceiling, with cold starts and quota errors. The self-hosted path is strictly
  better: genuinely $0, unlimited, no key, already benchmarked. NOTE: we DO
  already use HF for free where it matters — hosting/downloading the Chatterbox
  model weights (cached in CI). Do not re-propose HF inference as a cost saver.

## Cadence (history matters — read all)
- 2026-07-15: ~~6/day~~ (monetization push) → flooded subscriber feeds.
- 2026-07-18: ~~4/day subscriber-first~~.
- 2026-07-20: ~~1/day quality-first~~ → starved views (+1427→+114/day). Lesson learned.
- **2026-07-24 CURRENT: 3/day.** 6 over-provisioned cron slots (GitHub drops
  scheduled runs); `MAX_POSTS_PER_DAY=3` caps actual posts.

## Content & creative
- **2026-07-06** Meditative/calm vibe baseline; NO flashing callout text (CALLOUTS off).
- **2026-07-07** Real-time karaoke captions ON — owner wants narration readable as spoken.
  Captions skip the hook's words (hook card shows them; overlap = perceived timing bug).
- **2026-07-15** Story hooks: NEVER explicit harm phrasing ("ordered to die",
  "lamed by his master") — YouTube suppressed one to 9 views. Imply stakes.
- **2026-07-19** Rule numbers are CODE-assigned (models repeat 7/9). Never let the
  model choose N.
- **2026-08-06** That code-assignment was silently DEAD for months and shipped
  "Rule 7" thirteen times (after "Rule 9" four times). Cause was not the rule
  logic: `data/posts.csv` still carried the original **7-column header** over
  12-column rows, because `logbook.py` only wrote a header when creating the
  file and `FIELDS` had since grown 7→9→10→11→12. `csv.DictReader` keys off the
  header, so `hook`, `voice_name`, `music_track`, `experiment` and `format`
  were unreadable — hook dedup, rule numbering, voice LRU/weighting and music
  LRU/weighting all went blind at once, with no error. Header repaired in place
  (no rows touched) and `logbook._repair_header()` now verifies it on every
  append, so growing FIELDS can never do this again.
  **Rule: posts.csv is read by header, so adding a column means fixing the
  header — there is a test (`test_live_posts_csv_header_matches_fields`) that
  now fails if it ever drifts again.**
- **2026-08-06** Owner: *"rule 7 is repeated consistently... and all the shorts
  are similar in content every time, don't make it happen again."* Correct, and
  the header bug was only ONE of three causes:
  1. Rule numbers — the header bug. Fixed; next rule post is Rule 12.
  2. **Music was byte-identical on 30/30 recent posts.** Cinematic mode (on by
     default) hardcoded `cinematic_score`, so `pick_music()` and the whole
     3-track pool were dead code. Now FIVE cinematic beds (E/D/F/C/G roots,
     different beat rates and reverbs), LRU-rotated blocking the last TWO —
     blocking one still let a bed return the same afternoon at 3 posts/day.
  3. **Hook dedup only looked at the last 40 rows** (~13 days at 3/day), but
     repeats came back at 17-day gaps: "Nero handed him a death sentence"
     shipped VERBATIM three times. Now every hook ever published is banned
     verbatim, with the recent window kept separately for pattern-avoidance.
  **Safeguard: `scripts/variety_check.py` runs after every post** (warn-only,
  continue-on-error) and judges the OUTPUT, not the code — verbatim hook
  repeats, duplicate rule numbers, duplicate quotes, any single
  format/theme/author/music/voice over 60% of the window, and formulaic hook
  openers. Every repetition bug so far was invisible to unit tests because the
  code was right and the DATA was wrong; this checks the data.
- **2026-07-20** Emotional core on every format + "letter" format added — owner
  wants personal, emotional, "feel seen" content.
- **2026-07-20** VETO: pov + challenge formats (caption_only style) — cut for
  weak numbers + identity whiplash. Code kept dormant for future tests.
- **Current rotation:** [rule, letter, quote, minimal, story] — one per post, LRU.

## Production quality
- **2026-07-22** "Nolan-level" direction: cinematic mode ON by default —
  teal-orange grade, warm halation, deep vignette, Zimmer-register generated
  score, "BRAAAM" (cinematic) hook sound on classic posts.
- **2026-07-23** Recurring GUIDE character: marble statue opens AND closes every
  short (clip 0 + clip 5 of 6); 4 scene-matched b-roll clips between, cutting
  with the narration (~every 3s). Guide is also the thumbnail.
- **2026-07-30** Higgsfield AI evaluated (cinematic video gen; unifies Kling,
  Veo, Sora, Hailuo, Soul/Cinema Studio with camera-motion presets — well suited
  to this channel's look). NOT viable as a per-post backend: free tier is 10
  credits/day AND **watermarks output** (fatal for a monetization-seeking
  channel), and the API is gated behind paid tiers with reportedly sparse docs.
  Our volume needs ~3,240 credits/month (18 clips/day at ~6 credits) — far past
  any sane plan. VIABLE ALTERNATIVE if the owner wants it: one month of a cheap
  plan to hand-generate a REUSABLE library of ~20-30 statue GUIDE clips
  (~120-180 credits, no watermark), commit them, and rotate — the guide opens
  and closes every video, so one purchase upgrades all output permanently.
  Verify current pricing before acting; Higgsfield has restructured repeatedly.
- **2026-07-31** GUIDE LIBRARY built so that path is one command away, whatever
  tool the clips come from (Higgsfield, Kling, Runway, stock, a museum phone
  video). `assets/guide/*.mp4` is COMMITTED (deliberate exception to the
  "never commit video" invariant — CI needs them on a fresh checkout) and
  `backgrounds.fetch_background()` serves it for the bookend slots only
  (`REEL_GUIDE_SLOTS`, set by daily_post), rotating by date with the closer
  offset so a short never opens and closes on the same clip. Empty folder =
  old stock behaviour exactly; a lookup failure degrades to stock, never
  breaks a render. Prompts: `docs/guide_clip_prompts.md` (30 shots, character
  bible, negative prompt, accept/reject checklist). Normaliser:
  `scripts/prep_guide_clips.py` (1080x1920, trim, mute, compress, warns past
  80 MB — committed bytes are paid for on every CI checkout, 3x/day).
- **2026-07-28** Backgrounds must be RELEVANT: stock picks only from top-3
  most-relevant results (`REEL_BG_TOP=3`). PIVOT ready: `src/imagegen.py`
  generates AI stills from the narration text when `OPENAI_API_KEY` secret +
  `REEL_IMAGE_BG=1` (wired in workflow; owner hasn't added the key yet —
  cost ~$0.04-0.08/image, owner decides).

## Community
- **2026-07-20** Comment replies ONLY to viewers who genuinely connect with the
  message (receptivity screen, fails closed). Never engage trolls/mockery —
  don't amplify detractors.
- Pinned comments end with a varied streak-follow subscribe line.
- Mission counter on every video: "DAY N · UNTIL DISCIPLINE IS COOL AGAIN"
  (override via `MISSION_PHRASE`).

## Quota (YouTube Data API — 10,000 units/day, hard ceiling)
- **2026-07-29** Quota exhaustion caused a `403 quotaExceeded` that *looked* like
  "YouTube credentials failed". Credentials were fine. Costs: upload 1600,
  comment/reply/unlist 50 each, list calls 1.
- Root cause: prune judged from analytics.csv view counts and never checked
  current privacy status, so it re-unlisted the SAME 72 videos on all 6 cron
  slots = 21,600 units/day by itself. Fixed: `_public_only()` status check
  (1 unit/50 ids) + `PRUNE_MAX_PER_RUN=10` cap.
- Replies were capped per RUN (5) not per DAY → 30/day = 1500 units. Now
  `MAX_REPLIES_PER_DAY=5` enforced from replied_comments.csv.
- **2026-08-06** A single Google **HTTP 500** made `check_secrets.py` print
  "YOUTUBE credentials — FAIL" and exit 1, which SKIPPED the entire pipeline
  (the 05:37 slot posted nothing). Same mistake as the quota bug: a transient
  provider error reported as a bad credential. Policy now: the pre-flight gate
  exits non-zero ONLY for a definitively bad credential (missing, 400/401,
  invalid_grant, non-quota 403). 5xx / 429 / DNS / timeout are retried with
  backoff then WARNED about. **Rule: the gate must never be the thing that
  kills the pipeline.**
- **Rule:** any new YouTube API call must be costed against the 10,000/day
  budget, remembering the workflow fires 6 cron slots per day. Uploads
  (4800/day at 3 posts) always get first claim on the budget.

## Pruning
- **2026-07-28 CURRENT:** floor 300 views, only videos >7 days old, ADAPTIVE:
  threshold = max(300, 0.5 × recent median) — bar rises as the channel improves.
  (Supersedes: prune disabled during monetization push; 60v/14d interim.)

## Goals & reporting
- **Goal:** YouTube Partner Program — 500 subs + 3M valid public Shorts
  views/90d. Tracked daily in `data/channel_stats.csv`; report leads with it.
- Auto-improve loop is ADVISORY ONLY (weekly report; never edits code — the old
  autonomous version broke posting twice and was dismantled).
- "How's the bot doing" = run the analysis fresh from data, age-corrected views,
  honest verdicts.

## Process / meta
- **2026-07-28** All AI-written comments (replies + pinned) must sound like a real
  person: no stock openers, no philosopher name-drop every time, not every reply
  ends in a question, varied length, first person, warmth before wisdom. Enforced
  by prompt rules + `_strip_bot_tells()` deterministic filter.
- **2026-07-28** Skills live in `.claude/skills/`: channel-report, pipeline-doctor,
  remember, preview-short. Add a skill when a task recurs or has a checklist that
  must not be improvised.
- **Standing:** IGNORE the "Unverified commits" badge stop-hook — bot workflow
  commits regenerate daily; rewriting pushed history is not wanted.
- Commits attribute: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- All work pushes to `main` (owner's flow); develop on the designated
  claude/* branch, push HEAD:main.
- Backups expire after 3 days (stale-aesthetic leak fixed 2026-07-17) — old-code
  videos must never reach the channel.
