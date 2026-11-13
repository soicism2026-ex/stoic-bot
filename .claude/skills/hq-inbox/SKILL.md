---
name: hq-inbox
description: Pick up and answer the owner's messages and decisions from the HQ app - the notes with status new and the asks he answered that have no outcome yet. For the chief chat, where his messages arrive as artifact comments (the small crew sessions have no HQ tools and report through scripts/hq_outbox.py instead).
---
# HQ inbox

Load `hq-protocol` first. Then, with `ArtifactData` on https://claude.ai/artifact/8MtajequXptMk8RUQnSsmx (the owner's message also arrives as an artifact comment: answer in that thread with `ArtifactComments reply`, then `resolve` it):

1. `query` collection `notes` where `status == "new"`, and `query` collection `asks` where `status == "answered"`
   (keep only those without an `outcome`). Nothing waiting: reply "Inbox empty" and stop.
2. For each note, in order: set it `status: "working"` (pinned write), read `data/decisions.md` (grep the last 60 lines)
   and do what he asked within the autonomy rule (decisions.md 2026-11-11: words-and-timing changes ship; the look,
   voice, music, cadence, product, price and anything that costs money become an `asks/` card and wait for his Go).
   A request that needs hours of building: hand it to ONE helper agent on Sonnet with a brief that names the files
   and the tests, review its diff, run the tests, commit; the chief chat itself stays short.
3. Answer in his thread (`ArtifactComments reply`, thread id = the note's `thread`; if the thread was not sent to
   Claude, put the answer in the note's `reply` only), then set the note `status: "done", reply: <one line>`.
4. For each answered ask: act on the answer (commit to main when it is code or data; merge origin/main first, never
   force-push), then set its `outcome` (one plain line) and, on an idea he stopped, `closed: true`.
5. Add one `hq/log` line per message handled (who "Claude", kind "you"). Record any new standing decision in
   `data/decisions.md` (dated entry, his words) in the same commit.

Keep it short: batch shell work, no image reads, no agents, no design-lab runs, one final line.
