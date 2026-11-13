---
name: hq-inbox
description: Pick up and answer the owner's messages and decisions from the HQ app in a fresh, small session - the notes with status new and the asks he answered that have no outcome yet. Fired by the "HQ inbox" scheduled task when he sends a message from the app; also the first step of every crew shift.
---
# HQ inbox

Load `hq-protocol` first. Then, with `ArtifactData` on https://claude.ai/artifact/8MtajequXptMk8RUQnSsmx:

1. `query` collection `notes` where `status == "new"`, and `query` collection `asks` where `status == "answered"`
   (keep only those without an `outcome`). Nothing waiting: reply "Inbox empty" and stop.
2. For each note, in order: set it `status: "working"` (pinned write), read `data/decisions.md` (grep the last 60 lines)
   and do what he asked within the autonomy rule (decisions.md 2026-11-11: words-and-timing changes ship; the look,
   voice, music, cadence, product, price and anything that costs money become an `asks/` card and wait for his Go).
   A request that needs hours of building: make it an `asks/` idea card with `status: "answered", answer: "go"` and an
   `outcome` saying it is queued for the chief session, and say so in your reply.
3. Answer in his thread (`ArtifactComments reply`, thread id = the note's `thread`; if the thread was not sent to
   Claude, put the answer in the note's `reply` only), then set the note `status: "done", reply: <one line>`.
4. For each answered ask: act on the answer (commit to main when it is code or data; merge origin/main first, never
   force-push), then set its `outcome` (one plain line) and, on an idea he stopped, `closed: true`.
5. Add one `hq/log` line per message handled (who "Claude", kind "you"). Record any new standing decision in
   `data/decisions.md` (dated entry, his words) in the same commit.

Keep it short: batch shell work, no image reads, no agents, no design-lab runs, one final line.
