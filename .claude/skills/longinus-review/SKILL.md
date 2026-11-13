---
name: longinus-review
description: Longinus's review of the NEXT Short before it airs (owner 2026-11-11: "the generated images sometimes look off, continuously improve the shorts"): fetch Apelles' rehearsal, check the painted shots the automatic inspector passed, rewrite a scene that still looks off, re-rehearse, log it in the HQ. Daily, 04:41 and 08:41 UTC, in a fresh session.
---
# Longinus: review the next Short

The automatic inspector (`src/inspector.py`, a free vision model) checks every painted shot and repaints a flagged one;
you are the human-eye pass on what slipped through. Budget: ONE image read, no agents, no design lab.

1. Load `hq-protocol`; run the `hq-inbox` steps first if anything waits (it usually doesn't).
2. `git fetch origin main && git merge --ff-only origin/main` (fresh sessions already have main).
   `python3 scripts/up_next.py fetch /tmp/upnext` prints the rehearsal's JSON: `edit`, `hook`, `airDay`, `renderedAt`,
   `shots` (each painted shot's scene, seed, tries, inspector verdict, problems). If `ok` is false, or `renderedAt` is
   older than the last post in `data/posts.csv`, find out why in edit-preview's latest run (`mcp__github__actions_list`
   / `get_job_logs`, repo soicism2026-ex/stoic-bot), fix the cause if it is ours (then push to main and dispatch
   `edit-preview.yml` with `up_next: true`), log it, and stop.
3. Look once: `ffmpeg -v error -y -i /tmp/upnext/up-next.mp4 -vf "fps=0.75,crop=560:1280:80:0,scale=130:-2,tile=8x1"
   -frames:v 1 /tmp/sheet.png` and Read that one sheet. Look at a single larger frame only if a shot seems off
   (`-ss <sec> -frames:v 1 -vf scale=360:-2`).
4. Judge each shot: uncanny anatomy (hands, faces), a face or figure hidden in an object, two objects fused, any
   writing, anything modern (glass, lanterns, modern clothes), the same person twice, a shot that doesn't show its
   scene or doesn't serve the line, type that is hard to read over the picture.
5. If a shot is off: rewrite THAT scene in `data/edit_quotes.json` (same position) following `docs/scene_writing.md`
   (rules 6 and 7: name the material of every object; keep people-words out of empty shots); check with
   `python3 -c "import json,sys; sys.path.insert(0,'scripts'); import shelf; q=[x for x in json.load(open('data/edit_quotes.json')) if x['id']=='<edit>'][0]; print(shelf.scene_problems(q))"`
   (prints `[]`). A new KIND of failure gets one line in rule 6. Append `date,edit,shot,problem,fix` to
   `data/longinus.csv`. Commit `scenes: <edit> shot N rewritten (Longinus)`, push to main (merge origin/main first, never
   force), then dispatch `edit-preview.yml` (`mcp__github__actions_run_trigger`, ref main, inputs voice brian, sfx on,
   up_next true): only the changed shot is repainted, the rest comes from the stills cache.
6. HQ: one `hq/log` line, who "Longinus", kind "done": "Checked <hook>: clean" or "Rewrote shot N of <hook>: <problem
   in plain words>". Real current time. Reply with that line and stop.

Never change the look itself (fonts, colours, layout: that is an `asks/` card for the owner), never run the design lab
(it shares the free painting allowance with the posts), and message the owner only if something needs his call.
