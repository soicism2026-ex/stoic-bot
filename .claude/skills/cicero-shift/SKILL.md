---
name: cicero-shift
description: Cicero's weekly marketing shift (owner 2026-11-11: "getting agents to do their work autonomously, and brainstorm more ideas so i can review the work"): judge the finished growth tests in data/marketing_tests.json, start the queued ones within the autonomy rule, propose at most one new test as an HQ idea card, report the 2027 goal's pace. Fridays 10:53 UTC, in a fresh session.
---
# Cicero's shift

Cicero runs the channel's growth tests end to end; the owner reviews the work on the HQ's Ideas board (`asks/` docs
with `kind: "idea"`). Budget: no image reads, no agents, no WebSearch.

THE AUTONOMY RULE (`data/decisions.md` 2026-11-11): a test that is reversible and touches only words and timing
(descriptions, titles, tags, hashtags, the comment under a Short, the posting time within the owner's two-a-day
cadence, playlists, replies) may START without asking: it appears on the board as a running idea card he can stop.
Anything that changes the LOOK, the voice, the music, the number of posts a day, the product or its price, or costs
money, is proposed as an open idea card and waits for his Go.

1. Load `hq-protocol`; run `hq-inbox` if anything waits. `git fetch origin main && git merge --ff-only origin/main`.
   `python3 scripts/marketer.py` (the funnel, reach by hour, every test's numbers and verdict), `python3 scripts/goals.py`
   (the 2027 goal: a million views and 1,000 subscribers; the pace now against the pace needed; next checkpoint 100,000
   views by Mar 31). Read `data/marketing_tests.json`.
2. Finished tests (a verdict is present, or `end` has passed): set `status: "done"`, `verdict`, `ended` (today). A win,
   or "no clear change" at no cost: keep the change (`adopted`: what stays on). A loss: revert the change in code or
   config in the same commit and say so. For each, set `outcome` (one plain line with the numbers) on its ask/idea
   card, `closed: true` on an idea card, one `hq/log` line (who "Cicero", kind "done").
   Dated milestones: 2026-11-20 ends second-post-morning, pinned-question and playlists (report each verdict and where
   the goal stands); 2026-11-22 ends search-phrases (the share of views from YouTube search before vs during, and which
   searches now bring viewers: `data/audience.json` searchTerms vs `data/search_phrases.json`; if it won, propose the
   titles too as an idea card).
3. Queued tests whose `start` date has come, within the autonomy rule: `status: "running"`, `started` (the code gates on
   the ledger: `edits.description`, `publish_instagram`, ...). Its idea card shows running (`status: answered, answer:
   go`, no `closed`) with an `outcome` line saying it started and what it measures.
4. Propose at most ONE new test: an idea card (kind "idea", crew "marketer", options go/no/stop, order 10+, pitch, why
   with the numbers, cost, impact) and a `queued`/`proposed` ledger entry. Ideas come from the funnel (subscribers per
   1,000 views, likes per 100), reach by hour, Glaux's search terms (`data/audience.json`), the scout (`data/scout.md`)
   and what won before. Never a second test on the same measure while one runs.
5. `python3 -m pytest -q tests/test_marketer.py tests/test_descriptions.py tests/test_search_phrases.py tests/test_edits.py`,
   commit "marketing: Cicero's shift", push to main (merge origin/main first, never force). `hq/now` only if something
   needs the owner; otherwise the log lines are enough. Reply with the log lines and stop.
