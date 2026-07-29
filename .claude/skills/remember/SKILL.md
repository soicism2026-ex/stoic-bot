---
name: remember
description: Capture an owner directive, preference, veto, or creative rule into the project's permanent memory files. Use when the owner says remember this, save this, from now on, never do X again, always do Y, I prefer, stop doing, or states any standing decision — and proactively whenever they give a taste verdict or policy that future sessions must honor.
---

# Remember this

Chat context dies. These files don't. Anything the owner decides must be written
down **in the same turn they say it**, or it will be lost and later violated.

## Which file

**`data/decisions.md`** — operational decisions, vetoes, policy, process.
Cadence, voices rejected, thresholds, workflow rules, "ignore that warning",
anything about how the system is run. Append-only, dated, newest wins.

**`data/doctrine.md`** — creative standing orders. ICP, hook psychology, tone,
what the content should feel like. **This file is injected into every content
generation call**, so it directly shapes the videos. Only put creative direction
here — operational rules belong in decisions.md.

**`CLAUDE.md`** — technical documentation of how the system works. Update when
behaviour changes, not for preferences.

## How to write the entry

Date it (`YYYY-MM-DD`), state the decision, and — this is the part that matters —
**record the reason or the evidence**. A rule without its "why" gets re-litigated
or reverted by a future session.

```markdown
- **2026-07-20** VETO: pov + challenge formats — owner rejected on execution;
  also weakest of the exploration week (59v/0v, 34v) and broke the channel's
  visual identity. Code kept dormant for future tests.
```

Rules:
- **Never delete history.** Superseding a decision means striking through
  (`~~old~~`) and adding the new entry, so the reasoning trail survives. The
  cadence history (6→4→1→3/day) is valuable precisely because it records what
  failed and why.
- Put it under the right heading (Voice / Cadence / Content & creative /
  Production quality / Community / Pruning / Goals / Process).
- Taste vetoes are decisions too. "I don't like this voice" is a permanent rule.

## Then

Commit and push with everything else in the turn — memory that isn't on `main`
doesn't exist for the next session:

```bash
git add data/decisions.md data/doctrine.md CLAUDE.md
git commit -F /tmp/msg.txt   # use a file; long messages break shell quoting
git push origin HEAD:main
```

Confirm to the owner in one line what was recorded and where, so they know it's
durable.
