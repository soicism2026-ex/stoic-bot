---
name: hq-protocol
description: How every session reports into the owner's HQ app (https://claude.ai/artifact/8MtajequXptMk8RUQnSsmx) and reads his messages and decisions - the hq/now, hq/log, hq/config, hq/upnext, asks and notes documents, their shapes, pinned writes, the Ideas board and the autonomy rule. Load it before the first ArtifactData or ArtifactComments call of a session, when an "[HQ ...]" message arrives, and before telling the owner anything that should show in the HQ.
---
# The HQ protocol

The owner runs the channel from the HQ app on his phone (pinned in his Claude sidebar). Every Claude session on this
project reports into it; he reads `hq/now` and `hq/log` as status reports, so write them in plain words with the REAL
current time (`date -u`), never a time ahead of the clock.

## Tools
- `ArtifactData` (ToolSearch `select:ArtifactData` if not loaded), url `https://claude.ai/artifact/8MtajequXptMk8RUQnSsmx`.
  Read with `get`; write with `update`/`set` and ALWAYS `if_version` = the version you just read (a refused write names
  the current version: read again, write again). Several writes = one `batch`.
- `ArtifactComments` for the owner's message threads: `read`, `reply` (only on threads he sent to Claude), `resolve`.

## Documents
The owner watches every agent here from a phone (it is pinned in the Claude sidebar), like the head of a business, and gives feedback here. Source: `hq/forged-hq.html`. Republish with the Artifact tool (`file_path` + `url` from another session). **Every Claude session on this project reports into it.**

- **Live by itself:** the owner's Claude sessions and scheduled tasks (Claude Code Remote connector, from the page, as the owner).
- **`hq/studio`** (bots + channel numbers + next quote on air): built ONLY by `scripts/hq_snapshot.py` (bot runs from GitHub's API, or from the `hq-status` branch that `hq-status.yml` keeps current) and written by the **HQ sync** scheduled task (`trig_01SkthKZdtqimpWg4VpNVUrV`, 6×/day at :47 after each poster cron, no notifications; the app's "Refresh now" fires it). Never hand-edit it.
- **`hq/now`** `{state: working|waiting|idle, headline, detail, next, since, updated, session, helpers[{name,task,status,since}], alerts[{level: warn|bad, text, fix}]}`. Update it (ArtifactData, pinned `if_version`) when you start or finish real work, launch or finish a helper, or start waiting on the owner. Write in plain words: the owner reads it as a status report.
- **`hq/log`** `{items: [{t, who, kind: work|done|post|decision|alert|you, text}]}`: newest first, ≤ 80 items. Add one line per milestone. Bot runs and posts are derived from `hq/studio` automatically: don't log them.
- **`hq/upnext`** `{edit, quote, hook, author, citation, airDay, voice, renderedAt, run, asset, retired[]}`: Apelles' rehearsal of the next Short (see "Quote shelf and rehearsals"). Written ONLY by the HQ sync from the `up-next` release; the page plays `asset` under Next on air only when `edit` is the quote that airs next. `retired` lists replaced rehearsal videos; Varro's weekly shift deletes them.
- **`hq/config`** also maps scheduled tasks to crew: `syncTrigger` (Hermes), `librarian` (Varro, `trig_0131CeoTYCTKpM5pQx4adBsn`), and `crewTriggers` {trigger id: crew}: Longinus's review (`trig_01SX5RppvhbfmVw3NoMwAg2b`, `inspector`, 04:41 and 08:41 UTC daily: looks at the next Short's rehearsal by eye, rewrites any shot that still looks off, re-rehearses) and the weekly crew review (`trig_01EnHkKKxCico4AoYt3GZ2e9`, `review`, Thursdays 20:23 UTC: Zeuxis, Plutarch and Callimachus each make one improvement from data/inspector.csv, data/longinus.csv and Cicero's numbers; changes to the look itself go to the owner first). Both fire into the chief session.
- **Ideas board** (owner 2026-11-11: "brainstorm more ideas so i can review the work"): `asks/<id>` docs with `kind: "idea"`, plus `pitch`, `why` (the evidence), `impact` (high/medium/low), `cost`, `needsYou?`, `options` go/no/stop. Open ideas show under "Ideas to review" on the Now tab (best `order` first) with Go / Not now; a Go'd idea (`status: answered, answer: go`) shows as running with its `outcome` until `closed: true`. The owner's tap sends "[HQ idea] <title>: Go|Not now|Stop" to Claude. Ideas never count in the decisions badge. The autonomy rule (decisions.md 2026-11-11): words-and-timing tests start on their own as running cards; look, voice, music, cadence, product, price and anything with a cost wait for Go. Cicero's shift (`trig_01JAMtZAfVzZxRCADuaCBNjU`, Fridays 10:53 UTC) judges, starts the queued, proposes one.
- **`asks/<id>`** `{title, question, options[{id,label,hint}], status: open, order, created, video?, videos?[{id,label}], crew?}`: `crew` names the bot whose work waits on the answer (e.g. `composer`): the lineup shows it as "Needs you". put every decision you need from the owner here, not just in chat. `video` is an artifact asset id (upload with Artifact `asset: true`). The owner answers in the app, which sets `status: answered, answer, answeredAt` and sends "[HQ decision] <title>: <option>" to Claude. When you act on it, set `outcome` (one line).
- **Messages from the owner** arrive as artifact comments sent to Claude ("[HQ] …" / "[HQ, about X] …") and wake the session that published or watches the HQ. When you pick one up, set its `notes/<id>` to `status: working` (the app shows "Claude is on it" instead of "Not picked up yet"); when it's handled, reply in the thread (ArtifactComments) and set `status: done, reply`. If no session was connected, the note waits in `notes` with `sent: false`. **On session start, read `notes` (status new) and `asks` (answered, no `outcome`) before anything else.** A wake can lag: on 2026-10-21 three messages took 22 hours to arrive. The app flags anything not picked up after 15 minutes and links the owner to this chat, where any message wakes the session.

---


## Logging rules
- One `hq/log` line per milestone (`{t, who, kind, text}`; newest first; keep at most 80 items): who = the crew member
  (Longinus, Zeuxis, Plutarch, Callimachus, Cicero, Varro, Echo) or "Claude"; kind = work | done | post | decision | alert.
- `hq/now`: update when real work starts or finishes or when you wait on the owner; `alerts` only for what he must act on.
- Decisions you need from him go in `asks/<id>` (and ideas in `asks/<id>` with `kind: "idea"`), never only in chat.
- Keep every HQ write small: the owner reads them on a phone.
