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
