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
- **2026-08-19 OWNER'S OWN VOICE via local cloning.** Owner: *"we have to use
  trending audios, and real people voices from real inspiring people."* The
  instinct is right — a human who believes the words beats any TTS — but the
  two literal versions both backfire:
  - **Trending audio CONFLICTS WITH MONETISATION.** Licensed tracks from the
    Shorts audio library route Shorts revenue to the rights holders, so a video
    using one cannot earn. Given the owner asked to be monetised by January,
    this trades the goal for the tactic. It also fights the voiceover, and
    YouTube exposes no API for "what's trending" — it would be manual, daily.
  - **Cloning a public figure is someone else's likeness** — not monetisable,
    risks the channel, and puts words in a real person's mouth they never said.
  **The version that gets the whole benefit: clone the OWNER'S OWN voice.**
  Free, legal, monetisable, unique, and impossible for a competitor to copy.
  `_synthesize_chatterbox_local` now passes `audio_prompt_path` (it previously
  could NOT clone at all — the free path only ever used Chatterbox's stock
  voice, which is exactly why the engine was disabled). Drop a 30-60s recording
  at `assets/voice/reference.wav`, set `CHATTERBOX_LOCAL=1`. A missing or
  truncated file falls back to edge-tts rather than cloning noise 3x/day.
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
- **2026-08-21 F3 "THE QUESTION" IS LIVE** (owner picked it from the four).
  One hard question, plain type, near-black, **two seconds of REAL silence**,
  then the voice answers. Verified on decoded samples, not asserted from
  config: lead 0.0000 rms → answer 0.0814 → read beat 0.0000 → lesson 0.0814.
  - The hook is **NOT spoken** for this format — reading the question aloud
    while the viewer reads it destroys the pause the format exists for.
  - Every cinematic default is deliberately OFF (motion, atmosphere, captions,
    hook sound; heavy darkening) — they all work against a still, silent,
    near-black first frame, which is the entire pattern interrupt.
  - **Concurrent control, not blocked:** `question` takes every third rotation
    slot, so the existing format runs as a live control in the same days and
    time slots. Better than the blocked design in `format_test.md` — it removes
    the time confound instead of averaging it out. 5 F3 posts in ~5 days.
  - Posts are tagged `experiment=ftest:the_question`; `scripts/format_test.py`
    schedules only formats in `BUILT` so it cannot claim an unbuilt arm is next.
  **Bar: does any exceed 5,000 views (4x the all-time best of 1,255).**
- **2026-08-16 RETENTION IS THE METRIC, NOT VIEWS.** `data/retention.csv` (175
  rows) had never been used for anything. Views measure how hard the algorithm
  pushed a video ONCE; retention decides whether it pushes the next one. Three
  changes, all measured from this channel's own data:
  1. **Rotation weighted to `minimal`** — 70.9% median retention (n=27) vs
     quote 53.5% and rule 50.3%. Rotation is `[minimal, quote, minimal, rule]`
     — the mix AND the order matter: `[minimal, quote, rule, minimal]` has the
     same proportions but repeats minimal across the cycle boundary.
  2. **Hooks capped at FOUR WORDS.** Retention by hook length, n=100,
     r=-0.29: 1-3w **68.8%**, 4-5w 57.3%, 6-7w 54.5%, 8+w 50.0%. The old median
     was 5 words. Best hooks ever: "Not tomorrow." (255%), "It's already
     given." (202%), "Let it be." (166%).
  3. **Winning hooks fed BACK into the prompt.** It carried SEVEN avoid-blocks
     and not one example of something that worked — the model was told what not
     to do and never what to aim at. Top 6 by retention (min 60 views, capped
     at 300% so one freak loop cannot dominate) are injected each generation as
     "match their energy and length, do not reuse their words".
  **Rule: rank content decisions by retention, not views. When the two
  disagree, retention wins.**
- **2026-08-13 CUT + VARIETY (paired — never do one without the other).**
  Owner: *"more variety, shorts out."* Two instructions that pull against each
  other, resolved together.
  **CUT.** Formats → `[quote, rule, minimal]`. Age-corrected medians at 1 day:
  quote 253 (n=23), rule 253 (n=16), minimal 209 (n=30), letter 188 (n=10),
  story 132 (n=24) — and in the last week letter/story WERE the floor (four of
  the six worst posts were letters at 17v/20v/27v). Themes → 8, dropping
  friendship (155) and desire (170), the two weakest; anger/fear/resilience
  lead so LRU reaches them first.
  **VARIETY.** Three formats over 3 posts/day means each returns DAILY, which
  raises the exact repetition risk that most likely caused the 77% collapse.
  So the cut ships with a hard OPENER VARIETY rule in the system prompt plus a
  dynamically computed ban list: any word opening ≥2 of the last 15 hooks is
  named and forbidden. On live data that currently bans "rule", "the",
  "nothing".
  **Rule: do not narrow the pool further without strengthening variety inside
  it. Themes were deliberately kept at 8, not 3, for the same reason.**
- **2026-08-13 HELPFULNESS OUTRANKS EVERYTHING.** Owner: *"I want the content
  to be more helpful to people, choose stories that if you watched them you'd
  feel better about yourself and make as much people get help as possible."*
  Written into `data/doctrine.md` §5 (injected into every content call) and
  into `content.py`'s system prompt as a HELPFULNESS TEST placed ABOVE the
  emotional-core block. The test: *if a man watched this at 2am on a bad night,
  would he feel better about himself, or smaller?* If smaller, rewrite.
  Concretely: pick stories where the person GOT THROUGH IT (not just endured
  or died nobly); give one usable thing tonight; absolve before instructing;
  write for the ordinary struggle, not the 5am-PR guy — that widens reach AND
  helps more people, which point the same way here.
  **Hard ban:** shame as motivation, "nobody is coming to save you", contempt
  for people struggling, treating needing help as weakness. And if a script
  drifts toward real despair the turn MUST move the viewer toward people —
  never "endure it alone, that's what a strong man does". Isolation dressed as
  strength is the most harmful thing this niche does; this channel does not.
- **2026-08-13 CAPTIONS BACK, BUT STORY-ONLY.** Owner: *"we need the text to
  speech back"* — meaning the spoken words shown on screen, not the voice
  (which was running fine; posts logged Christopher/Steffan). Removing captions
  entirely on 2026-08-07 OVER-CORRECTED: the collision was with the QUOTE, not
  with captions as such. Under the three-act format they no longer conflict —
  during act 1 the quote is not on screen, so captions have the frame to
  themselves, and they stop the instant the quote fades in. `_build_ass` drops
  any chunk starting at/after `QUOTE_APPEAR`. **Rule: never two competing texts
  on screen at once — but read-along during the story is wanted.**
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
- **2026-08-07 FORMAT — THREE ACTS.** Owner: *"can we wait until the story is
  said before showing the quote on screen? and then after the quote is shown
  can we have a voice over of it as a lesson of the video? ... I have a hard
  time reading the quote while also listening to the dialogue."*
  1. **Story** — hook + setup narrated, quote NOT on screen.
  2. **Read beat** — quote fades in, narration STOPS (`REEL_READ_BEAT`, 2.4s).
  3. **Lesson** — narration returns, SPEAKS THE QUOTE ALOUD, then the takeaway.
  Reading and listening compete for the same attention, so the quote card was
  always losing. `content.py` emits `voiceover_story` + `voiceover_lesson`;
  `tts.synthesize_two_part()` inserts real silence and returns the boundary;
  `daily_post` passes it as `REEL_QUOTE_APPEAR` so the card fades in exactly
  when the voice stops. **Rule: never narrate over the quote's reading beat.**
  Degrades to a single take + old timing if either half is missing.
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
- **2026-08-07** GENERATED BACKGROUNDS ARE LIVE and free: Cloudflare Workers AI
  (FLUX.1 schnell) inside the free 10k-neuron/day allowance — ~230 images/day
  free, we need 18. Chain: Cloudflare → OpenAI (only if key) → stock →
  synthetic. The recurring GUIDE is now a fixed seed (`REEL_GUIDE_SEED`), so
  it is literally the same statue daily; the CLOSING bookend keeps the seed but
  appends a different shot, because identical seed + identical prompt returned
  a byte-identical image and the short opened and closed on the same frame.
- **2026-08-07 PROMPTING RULE — NEVER NEGATE COLOUR.** FLUX kept returning a
  saturated red/cyan gel-lit statue. Writing "NOT red, NOT magenta, NOT purple"
  made it WORSE: diffusion text encoders have no reliable "not", so those
  tokens simply get rendered. Fixed by naming a PHYSICAL LIGHT SOURCE ("lit by
  a single warm candle flame just out of frame, low golden lantern light") —
  a named source carries its own colour temperature and leaves nothing to
  invent. Also removed "dramatic chiaroscuro" from the guide queries: beside a
  stoic marble bust it sits on top of the red/cyan look that saturates this
  aesthetic online. A test rejects any colour negation in the style block.
- **2026-08-07** Generated stills arrive dark and pre-graded, so render.py's
  grade (tuned for bright flat stock) double-darkened them — the visual QA said
  "too dark and murky" unprompted. `REEL_GEN_BRIGHT_LIFT` lifts brightness and
  eases contrast ONLY when backgrounds are generated.
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
- **2026-08-13 DISABLED.** Gated behind repo variable `PRUNE_ENABLED=1`, off.
  The goal is YPP: 3,000,000 **valid public** Shorts views in 90 days, and
  unlisting a video removes its views from that total permanently. 113 of 196
  videos sit under the 300-view bar. The channel's own numbers show the cost:
  per-video peak views sum to **69,176** while the channel total reads
  **55,290** — roughly 14k views, a fifth of everything ever earned, deleted
  from the exact metric being chased. The theory (hiding weak videos improves
  the channel quality signal) has no evidence behind it here — pruning ran
  throughout the period in which 1-day views fell 77%. Re-enable only after YPP
  is reached, if ever.
- **2026-07-28 CURRENT:** floor 300 views, only videos >7 days old, ADAPTIVE:
  threshold = max(300, 0.5 × recent median) — bar rises as the channel improves.
  (Supersedes: prune disabled during monetization push; 60v/14d interim.)

## Goals & reporting
- **2026-08-19 THE DIAGNOSIS CHANGED. 210 videos, best ever 1,255 views, ZERO
  above 5,000.** This channel has never had a breakout — it is not a suppressed
  channel, it is a channel with a hard ceiling it has never crossed in 210
  attempts. The 77% "collapse" chased for three weeks was real but was
  variation between bad and worse; the pre-collapse baseline (242 median @1d,
  1.09 subs/video) was never good either. **The repetition fixes were genuine
  bugs worth fixing and were never going to cause a breakout.**
  Root read: the format — marble statue + AI voice + gold quote card — is the
  most saturated aesthetic on Shorts. It is excellent execution of a commodity,
  and the first frame reads as "inspirational content" inside 200ms, which is
  when the thumb decides. **More polish cannot fix this.**
  → `data/format_test.md`: 20 videos, 4 genuinely different formats, ONE
  question — does any exceed 5,000 views (4x the all-time best). Interleaved
  never blocked; everything else FROZEN for the duration. A null result across
  all four means positioning/niche is wrong, not execution — which is the
  outcome three weeks of polish could never have surfaced.
- **2026-08-19 ROADMAP + TRIPWIRES.** `data/roadmap.md` holds monthly targets
  Sept 2026 → Jan 2027; `scripts/goal_check.py` prints actual-vs-target and
  fires the tripwires. **The finding that shapes the plan: YPP's two
  requirements are wildly asymmetric.** 500 subs is 159 days away at the
  current +1.71/day — reachable. 3,000,000 views/90d is **99x short**: it needs
  33,333 views/day (currently 337), or 11,111 per video per day. Even a full
  recovery to the pre-collapse baseline is still ~25x short.
  **So YPP is NOT a 5-month goal, and no plan should pretend otherwise.** The
  Gumroad product is the realistic revenue path in this window because it has
  no threshold. Views remain the top of that funnel — the input, not the finish
  line. **Primary monthly metric is views/day, not subs** (subs lag views;
  optimising subs directly chases the shadow).
  **Committed tripwires:** 1-day median under 100 past 2026-08-24 means the
  repetition theory is wrong — change theory rather than defend it; two
  consecutive months under base-case views/day means the STRATEGY is wrong, not
  the execution; negative sub growth means audit tone before touching anything
  else. Highest-value unbuilt mitigation: **a second platform** (Instagram
  cross-post already exists, dormant) — the whole project currently routes
  through one YouTube account and one refresh token.
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
- **2026-08-22** Promo copy must be EVERGREEN. Two of the three default CTAs
  carried deadlines ("FREE this month only", "but only for June"); the
  2026-08-21 upload published "only for June" to a live video in August.
  Descriptions stay live forever, so any dated claim becomes false and reads
  as an abandoned bot. Rewritten to undated copy, and
  `tests/test_promo.py::TestCopyStaysTrue` now fails the build on month names
  or urgency phrases — in `src/promo.py` AND in the workflow env, since
  `daily-short.yml` was overriding the module default. Dead `PROMO_PITCH` knob
  (set in two workflows, read by nothing) removed. Back-catalogue descriptions
  still carry the old text — a bulk rewrite needs the owner's call (~10.5k
  YouTube quota units, over the 10k/day cap).
