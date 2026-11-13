---
name: crew-review
description: The weekly crew review of the painted look (owner 2026-11-11: "continuously improve the shorts utilizing the agents specific tasks"): Zeuxis fixes the week's most frequent picture defect at the root in src/painter.py, Plutarch rewrites the upcoming scenes that share it, Callimachus fixes one type fault, each with a test and an HQ log line. Thursdays 20:23 UTC, in a fresh session.
---
# The weekly crew review

Each crew member makes ONE improvement in their own specialty, from evidence, never from taste alone. Budget: at most
one small frame sheet read, no agents, no design-lab run (the lab shares Cloudflare's free painting allowance with the
posts; the Thursday run is after the day's posts, but the evidence below is enough).

1. Load `hq-protocol`; run `hq-inbox` if anything waits. `git fetch origin main && git merge --ff-only origin/main`.
2. Gather the week: `data/inspector.csv` (every live painted shot: pass / flagged / stock with the problems named; count
   the problem words of the last 7 days), `data/longinus.csv` (what Longinus rewrote by eye),
   `python3 scripts/marketer.py` (Cicero's "new-look" test: views at 3 days, before against after) and
   `data/strategy.md` (Frontinus). `docs/reference.md` has the file map if you need it.
3. Zeuxis (the picture, `src/painter.py`): take the week's most frequent defect class and fix it at the root in the
   painter's prompt rules (the way `PERSON` keeps people-words out of empty shots, `LAMP` writes Roman lamps and
   `PERIOD_WORDS` names materials), with a test in `tests/test_painter.py`. Nothing recurring: improve the weakest kind
   of shot instead (the inspector's "least broken" airs, `tries` 3).
4. Plutarch (the scenes): rewrite the upcoming scenes (next 14 days in air order: simulate `edits.pick` over
   `data/posts.csv`) that share that failure pattern, following `docs/scene_writing.md`; add the lesson as a line of
   rule 6 or 7. Never touch a quote already rehearsed for tomorrow (its paintings are cached). Validate with
   `shelf.scene_problems`.
5. Callimachus (the type, `src/edit_type.py`, `data/edit_type.json`): from the rehearsal (`python3 scripts/up_next.py
   fetch /tmp/upnext`, one sheet read) look for a hook with one lonely word on a line, text over a busy patch, or gold
   on the wrong word, and fix one with a test (`tests/test_edit_type.py`).
6. Anything that changes the LOOK itself (fonts, colours, layout, motion, music) goes to the owner first as an `asks/`
   card with a before/after, never straight to air. Defect fixes ship directly.
7. `python3 -m pytest -q tests/test_painter.py tests/test_shelf.py tests/test_edit_type.py tests/test_inspector.py
   tests/test_painted_daily_post.py`, commit, push to main (merge origin/main first, never force). One `hq/log` line per
   crew member who changed something (who "Zeuxis" / "Plutarch" / "Callimachus", kind "done", the change in plain
   words, the real time). Reply with those lines and stop.
