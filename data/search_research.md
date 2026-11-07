# What our audience searches for (research, 2026-11-07)

Owner, in the HQ: *"do some research on things that our audience actually care
about and would watch in our niche. give me a list of 10 things people might
potentially search for. we will use it make our shorts easier to find"*.

## How it was researched

1. **YouTube's own search suggestions** (US, English), for about 160 starting
   phrases: "stoicism", "stoic", "marcus aurelius", "how to stop", "how to
   control", "how to not", "how to stay", the alphabet after "stoicism" and
   "stoic", and searches matching each of our 12 themes. YouTube lists its
   suggestions roughly by how often people search them, so a phrase that
   comes first for a short start ("how to stop" → "how to stop
   overthinking") is one of the most searched.
2. **The searches that already bring people to our Shorts**: YouTube
   Analytics' traffic-source report for YouTube search, pulled by Glaux
   (`scripts/audience.py`, `data/audience.json` → `searchTermsAllTime`).
3. **Who watches**: 84% US, 98% not subscribed, 92% from the Shorts feed and
   4% from search (Glaux, 28 days to 11-06); doctrine 1: men 18-34 on a
   self-improvement arc. Web reading (creator-marketing blogs, so directional
   only) agrees: the niche's viewers are mostly young men looking for calm,
   structure and discipline; Marcus Aurelius is the most popular figure.

## What already finds us (YouTube search, June to Nov 7: 225 views)

stoicism 52 · stoic 18 · marcus aurelius 16 · stoicism marcus aurelius 16 ·
epictetus 11 · stoicism motivation 11 · stoicism philosophy 11 · marcus
aurelius meditations 10 · stoic mindset 8 · stoic wisdom 8 · stoic reset 7 ·
stocism 6 · marcus aurelius quotes 5.

All broad words. **Not one view came from a problem search** ("how to stop
overthinking" and the like), although those are searched far more: our titles
and descriptions never use those words. That is the opening.

## The 10

| # | Search | Evidence (YouTube suggestions) | Our quotes that answer it |
|---|--------|--------------------------------|---------------------------|
| 1 | how to stop overthinking | #1 for "how to stop" | control, fear (13 on the shelf) |
| 2 | how to control your emotions | top for "how to control" and "stoicism how to" | anger (5) |
| 3 | how to not care what others think | #1 for "how to not" | ego (6) |
| 4 | how to stay calm under pressure | top 3 for "how to stay" | resilience (7) |
| 5 | how to stay disciplined | "how to stay disciplined and focused", "self discipline" | discipline, duty (16) |
| 6 | how to stop procrastinating | top 7 for "how to stop"; "how to stop wasting time" | time, mortality (11) |
| 7 | how to get through hard times | "stoic quotes for hard times", "stoic advice for hard times" | adversity (10) |
| 8 | how to deal with toxic people | top 4 for "stoicism how to"; "how to choose friends wisely" | friendship (12) |
| 9 | how to be happy with less | "how to be content with what you have" | desire (6) |
| 10 | marcus aurelius quotes | top 5 for "marcus aurelius"; already brings us viewers | every Marcus Aurelius Short |

Runners-up: how to deal with anxiety, how to let go of the past, how to
handle disrespect (stoic response to disrespect), stoicism for men, how to be
mentally strong, memento mori (its suggestions are mostly songs).

Left out on purpose (doctrine 5): the manosphere corner of the niche
("stoicism for men about women", "stoic manipulation", "how to talk to
women", narcissist content). It gets searches, but it is not who we are.

## How we'd use it (waiting for the owner's yes: HQ `asks/search-phrases`)

Each Short gets the search its quote answers (`data/search_phrases.json`, by
theme): the description opens with it ("How to stop overthinking: Epictetus's
answer."), a matching hashtag joins #stoicism, and the search goes into the
tags. Optionally the title carries it too. Cicero measures it as test 4: the
share of views from YouTube search, the 14 days after against the 14 before.
