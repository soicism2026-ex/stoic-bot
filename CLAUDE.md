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
**Posting cadence:** 3 videos/day since 2026-11-13 (owner's Go on the HQ idea card "A third Short a day, in the evening"; 2/day from 2026-10-18, "push it more"; `MAX_POSTS_PER_DAY` defaults to 3 in daily-short.yml). `POST_SLOT_HOURS="0,7,19"` makes the second post wait for 07:00 UTC and the third for 19:00 (and `MIN_GAP_HOURS` 5), so the three are spread: since 2026-11-03, because 12-19 UTC posts got 0.75x the reach of their week (04-11 UTC 1.0x, 00-03 UTC 1.15x); edits rotate authors (`edits.pick`). Six cron slots (03/07/11/15/19/23 UTC) are over-provisioned because GitHub silently drops scheduled runs. Every edit quote AND its citation is checked against the source text (`scripts/validate_quotes.py`, tests). **Goal for 2027 (owner's pick, 2026-11-07): a million views and 1,000 subscribers in 2027**, about 2,700 views a day on average (6x Nov 2026), checkpoints 100k / 300k / 600k views by Mar 31 / Jun 30 / Sep 30 (`data/goals.json`, `scripts/goals.py`, the HQ's goal card; every test and restock is judged by whether it moves it). YouTube's first payout tier (500 subs + 3M Shorts views/90d) is the step after.  
**Look (owner's pick in the HQ, 2026-11-11: "Switch to the new look"):** `REEL_EDIT_LOOK: "painted"` in daily-short.yml AND edit-preview.yml: every shot a colour painting (free FLUX.2 [klein] on Cloudflare, `src/painter.py`, from the quote's `scenes`; a free vision model, `src/inspector.py`, repaints a shot with a clear defect), the v2 type (`src/edit_type.py`, gold words in `data/edit_type.json`), mastering to -14 LUFS (`src/master.py`). `""` = the old black-and-white stock look.  
**Product:** The Stoic Reset, a 30-day guided journal: C$5.99 since 2026-11-01 (it was free) — https://soicism.gumroad.com/l/cslosv. Every description ends with the owner's own line (`src/promo.py`); a backup airs with the current line (`promo.refresh`).

---

## Token rules (owner 2026-11-13: "We keep reaching the limit too quickly")

Every turn re-reads the whole context, so the cost of a session is its context size times its number of turns.
- Keep CLAUDE.md as it is: short. Everything else lives in `docs/reference.md` (pipeline, source files, workflows, secrets, rotation, data files), `docs/scene_writing.md`, `data/decisions.md`: read ONE section with `grep -n '^## '` + `sed -n`, never a whole file.
- Batch shell work into one Bash call; never cat a file you can grep; never re-read a file you just edited.
- Images cost the most: at most ONE small frame sheet (≤ 1,100 px wide) per job, and only when the inspector flagged a shot or a number looks wrong.
- One helper agent at a time, on Sonnet, with a brief that names the files and the tests; never an agent to check an agent.
- Recurring crew work runs in SMALL standing sessions on Sonnet (one per crew member, created by the chief with the repo and push access; their scheduled tasks fire into them; ids in the HQ's `hq/config`), never in a long chat. The owner's HQ messages wake the small inbox session. The chief chat is for the owner's own requests.
- No design-lab runs, re-rehearsals, WebSearch or new scheduled tasks unless the task needs them. Finish with one short report; no narration between steps.

## Skills (`.claude/skills/`)

| Skill | Use when |
|-------|----------|
| `hq-protocol` | Before any HQ write or read: the documents, their shapes, pinned writes, the Ideas board, the autonomy rule |
| `hq-inbox` | An "[HQ …]" message or decision from the owner (fresh sessions fired by the HQ inbox task; also step 1 of every shift) |
| `longinus-review` | Daily 04:41 / 08:41 UTC: look at the next Short's rehearsal, rewrite a shot that still looks off, re-rehearse |
| `crew-review` | Thursdays 20:23 UTC: Zeuxis, Plutarch and Callimachus each fix one thing from the week's evidence |
| `cicero-shift` | Fridays 10:53 UTC: judge, start and propose growth tests; report the goal's pace |
| `varro-restock` | Mondays 13:07 UTC: keep the quote shelf at 30+ days, scenes and gold words included |
| `channel-report` | "How's the bot doing": age-corrected performance read, leaderboards, honest verdict + one recommendation |
| `pipeline-doctor` | "It's not posting" / "changes aren't showing up": every known silent-failure mode, verified with a real post |
| `remember` | The owner states a decision, veto or preference: `data/decisions.md` (operational) or `data/doctrine.md` (creative), same turn |
| `preview-short` | Any visual/audio change: render a test Short locally and show frames through the iPhone crop before anything publishes |

Scheduled tasks (ids in the HQ's `hq/config`: `syncTrigger` = the HQ sync, `librarian`, `inboxTrigger`, `crewTriggers` {id: inspector | review | marketer}) are the crew's shifts above plus the **HQ sync** (6×/day at :47, a fresh session: `scripts/hq_snapshot.py` → `hq/studio`, the rehearsal → `hq/upnext`); all on Sonnet. A pushed scene change re-rehearses by itself (`edit-preview.yml` runs on pushes to `data/edit_quotes.json`; `up_next.py need` compares the scenes).

## HQ app (https://claude.ai/artifact/8MtajequXptMk8RUQnSsmx): the owner's live view

The owner watches every agent here from a phone and gives feedback here. Source `hq/forged-hq.html` (republish with the Artifact tool, `file_path` + `url`). **On session start, read `notes` (status new) and `asks` (answered, no `outcome`) before anything else** (`hq-inbox`). Everything about the documents is in the `hq-protocol` skill.

## Quote shelf and rehearsals

`data/edit_quotes.json` is the shelf: every edit airs one verified quote, never twice; empty = silence (the fallbacks need Anthropic credit). `python scripts/shelf.py status | winners | check FILE | add FILE` (the only door in). Apelles rehearses the next Short after every post (`edit-preview.yml`, DRY_RUN, `scripts/up_next.py` → the `up-next` release → `hq/upnext`); `src/airday.py` keys the rehearsal to its air day. Details: `docs/reference.md` "Quote shelf and rehearsals".

## Pipeline, files, workflows, secrets, data

All in `docs/reference.md` (sections: Pipeline, Source files, GitHub Actions workflows, Secrets required, Content rotation logic, Video structure, Data files). Read the one section you need.

## Key invariants

- Never commit video files (`assets/backgrounds/*.mp4` gitignored); the one exception is the curated `assets/guide/*.mp4` library (keep it under ~80MB).
- Quotes must be genuine public-domain Stoic text, verbatim from `data/sources/`, cited where the source has it. Never fabricate or misattribute.
- The `youtube.force-ssl` scope is required for thumbnails AND comments (403 = re-scope the refresh token with `scripts/auth_setup.py`).
- `data/posts.csv` is the single source of truth for rotation history and quote dedup. Never delete rows.
- Secrets exist only in GitHub Actions secrets: never in code, chat, the HQ or a commit. Never ask the owner to paste a key anywhere but GitHub's secret store.
- Push to main (merge `origin/main` first) and to the session's branch; never force-push; no pull requests unless asked.

### Boil the ocean

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to 'table this for later' when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't 'good enough' — it's 'holy shit, that's done.' Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.
