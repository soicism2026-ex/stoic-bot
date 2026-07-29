---
name: pipeline-doctor
description: Diagnose why the bot isn't posting, why changes "aren't showing up", missing/short post days, or any suspected silent pipeline failure. Use when the owner says it didn't post, it didn't push, my changes aren't applying, posts are missing, or the channel looks frozen. Runs the full checklist of known silent-failure modes in order.
---

# Pipeline doctor

The pipeline fails **silently and successfully** — workflow runs go green while
nothing gets published. Every "it's not posting" report so far has been a real
bug, never a false alarm. Work the checklist in order; do not stop at the first
plausible cause.

## 0. Ground truth first (60 seconds)

```bash
cd /home/user/stoic-bot && git fetch origin main -q
# Did the config actually land on main? (config on main != channel working)
git show origin/main:.github/workflows/daily-short.yml | grep -c 'cron:'
git show origin/main:scripts/daily_post.py | grep 'MAX_POSTS_PER_DAY = int'
# Are posts actually landing?
git show origin/main:data/posts.csv | python3 -c "
import sys,csv
from collections import Counter
rows=[r for r in csv.reader(sys.stdin)][1:]
c=Counter(r[0] for r in rows)
for d in sorted(c)[-6:]: print(f'  {d}: {c[d]} post(s)')"
```

A day with **fewer posts than the cap** is the symptom. Chase it.

## 1. Known silent-failure modes (all of these have actually happened)

**QA rejecting good renders.** The vision QA once read the karaoke captions as a
"wrong quote" and failed all 5 attempts, every day. Symptom: run duration ~30 min
(normal ≈5), conclusion `success`, no upload. Check the log for
`pass=False severity=high` and read *what* it objected to — if it's describing
intentional features (captions, hook card), the QA prompt is wrong, not the video.

**Empty/stale backup bank.** When all QA attempts fail the bot posts from
`backups/`. If the bank is empty → nothing posts. If it holds videos older than
`BACKUP_MAX_AGE_DAYS` (3) they're expired on load (deliberate: stale backups once
published month-old aesthetics, which is why "changes didn't show up").

**GitHub dropping scheduled runs.** Cron is best-effort; runs get silently
dropped and fire at odd times. That's why the workflow over-provisions 6 slots
for a 3/day target — the daily cap does the limiting, not the cron count.

**Push races between slots.** Concurrent runs collide pushing `posts.csv`; the
commit step rebase-retries. A lost push = a lost log row (the day looks short
even though the video published).

**Oversized files killing the whole run.** Render intermediates >100MB make the
push fail and the entire run error out *after* uploading. The workflow sweeps
`backups/*.bg*.mp4`, sidecars and >95MB files before committing.

**Bad credentials degrading quietly.** `check_secrets.py` warns but never fails
the run (deliberate — a bad ElevenLabs key must not stop posting). A 401 there
means the voice silently fell back, not that posting stopped.

## 2. Read the actual run log

```
mcp__github__actions_list  → list_workflow_runs (daily-short.yml)
mcp__github__actions_list  → list_workflow_jobs (run_id)   # step timings
mcp__github__get_job_logs  → job_id, return_content=true   # the truth
```
Logs are obfuscated (`e`/`de` → `***`); grep loosely. Look for `published:`,
`pass=False`, `[backup]`, `[all high-severity]`, and step durations.

## 3. Verify the fix — never assume

After any fix, trigger a real run and confirm a post landed:
```
mcp__github__actions_run_trigger → run_workflow (daily-short.yml, ref main)
```
then poll `origin/main:data/posts.csv` until the day's count increases. A green
run is **not** proof; a new row in posts.csv with a video URL is.

## 4. Report

State the root cause plainly, what was fixed, and the proof (the new video URL).
If the owner blamed the wrong thing (e.g. "it didn't push" when the push was
fine), say so kindly and show what actually broke — they're debugging blind.
