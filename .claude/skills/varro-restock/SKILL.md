---
name: varro-restock
description: Varro the Librarian's weekly shift (owner 2026-10-23: "Get them working"): keep the edit quote shelf (data/edit_quotes.json) at 30+ days of verified quotes with scenes, descriptions, questions and gold words, data-led by the winners and the scout; delete the retired rehearsal videos. Mondays 13:07 UTC, in a fresh session.
---
# Varro: restock the quote shelf

Budget: no image reads, no agents. Read `docs/reference.md` "Quote shelf and rehearsals" and `docs/scene_writing.md`
once; everything below is the shift.

1. `git fetch origin main && git merge --ff-only origin/main`. The HQ is written through the outbox here (`scripts/hq_outbox.py`); run `python3 scripts/hq_outbox.py prune` once (it keeps the last 14 days).
   `python3 scripts/shelf.py status` (fresh quotes, days left, per author, `toTarget`).
2. (The retired rehearsal videos in `hq/upnext.retired` are pruned by the chief chat, not here.)
3. Scenes: every quote due to air in the next 14 days must have `scenes` (6-8 paintable shots after `visuals`, cast
   tokens {man} {marcus} {seneca} {epictetus}, a named light, a person in a situation first, relief at the end, the
   material of every object named: rules 6 and 7). List the next 28 quotes in air order (simulate `edits.pick` over
   `data/posts.csv`, appending each pick as an `edit:<id>` row) and write `scenes` for any that lack them. Check:
   `python3 -c "import json,sys; sys.path.insert(0,'scripts'); import shelf; [print(q['id'], shelf.scene_problems(q)) for q in json.load(open('data/edit_quotes.json')) if 'scenes' in q and shelf.scene_problems(q)]"`
   prints nothing when all pass.
4. `toTarget` 0: `python3 scripts/hq_outbox.py log --who Varro --kind done --text "Checked the shelf: N days of
   quotes, no restock needed."` (", wrote scenes for K quotes" when step 3 wrote any). Go to step 6.
5. Otherwise restock. Evidence first (owner 2026-11-07: "you need evidence that they will actually watch these videos
   before you even press record"): `data/scout.md` (what wins on other Stoicism channels this month, by our themes),
   `data/search_research.md` (the 10 searches our audience makes), `python3 scripts/shelf.py winners` (write more like
   the top; doctrine §4), `data/strategy.json`'s hook-form verdict (while "question" wins, two of every three hooks are
   a question the viewer asks himself, the third a plain line). Draft `toTarget + 6` entries, topping up the author
   with the fewest fresh quotes first, copying every quote from `data/sources/` (never from memory), citing where the
   source has it, keeping doctrine §5 (nothing that treats death as an exit). Each entry: `hook` (2-9 words, no shame),
   `description` (2-3 short paragraphs, 35-95 words: the truth about the viewer's own life with the philosopher as
   evidence; what it means this week; one handle for today; no links or hashtags) and one `question` (one line he can
   answer from his own life, often a choice between two) in the owner's style (doctrine §10; match the shelf's
   existing ones), 1-3 `still` shots (stock searches of at most 3 words, people shots start with "man"), `scenes`
   (step 3), and its gold words in `data/edit_type.json` under `emphasis.<id>` (hook: ONE punch word or short phrase
   from the hook; quote: 1-3 phrases from the quote, pipe-separated). `python3 scripts/shelf.py add <file>` until every
   entry passes; read each again for sense and tone; then `python3 -m pytest -q tests/test_edits.py
   tests/test_quotes_verbatim.py tests/test_shelf.py tests/test_descriptions.py tests/test_search_phrases.py
   tests/test_edit_type.py tests/test_painted_daily_post.py tests/test_painter.py`.
6. Commit ("shelf: +N verified quotes (Librarian)" or "shelf: scenes for K quotes (Librarian)"), push to main (merge
   origin/main first, never force). When you restocked: `hq_outbox.py log --who Varro --kind done --text "Restocked the shelf: +N quotes, now D days
   (runs out <date>)"`, committed with the quotes. Something that needs the owner's call: `hq_outbox.py ask
   varro-<slug> --create-json '{...}'` (an open ask card). Reply with the log line and stop.
