# Marketing: how the channel reaches people

_Updated 2026-11-13 by Cicero (scripts/marketer.py, free, no paid API)._

## The funnel

- Views a day, last 7 days: **1210** (the 7 before: 492, +146%)
- New subscribers a day: **2.9** (the 7 before: 1.6); 277 in all
- Subscribers per 1,000 views: 2.4
- Likes per 100 views (Shorts of the last 14 days): 3.0

## Reach by upload hour (UTC)

Each Short's day-1 views against the Shorts aired within a week of it.

| Hour (UTC) | Shorts | Reach vs its week | Stalled (<0.4x) |
|---|---|---|---|
| 00-03 | 89 | 1.23x | 13 |
| 04-07 | 29 | 1.01x | 5 |
| 08-11 | 72 | 1.07x | 11 |
| 12-15 | 31 | 0.69x | 7 |
| 16-19 | 53 | 0.72x | 9 |
| 20-23 | 42 | 0.74x | 9 |

## Who watches (last 28 days, pulled 2026-11-12)

- Countries: US 69%, IN 12%, GB 4%, CA 4%, DE 3%, PH 2%
- How they find the Shorts: SHORTS 93%, YT_SEARCH 3%, YT_OTHER_PAGE 2%, YT_CHANNEL 1%, EXT_URL 0%
- Subscribed or not: UNSUBSCRIBED 98%, SUBSCRIBED 2%
- What they typed into YouTube before watching (since June): "stoicism" (60), "stoic" (18), "stoicism marcus aurelius" (18), "stoicism motivation" (17), "marcus aurelius" (16), "epictetus" (11), "stoicism philosophy" (11), "marcus aurelius meditations" (10), "stoic mindset" (8), "stoic wisdom" (8)

## The goal

- **A million views and 1,000 subscribers in 2027** (by 2027-12-31)
- Views in 2027: 0 of 1,000,000 (starts; 674 a day now, 2,740 needed)
- Subscribers: 277 of 1,000 (behind; 1.7 a day now, 1.8 needed)
- Next checkpoint 2027-03-31: behind
- Every test below is judged by whether it moves these numbers.

## Tests (one change at a time, each only with the owner's yes)

### Does the second Short reach more people in the morning than in the afternoon?

- Status: **running** since 2026-11-06
- Change: 1.36
- Why: Across 294 Shorts, each against its own week: 00-03 UTC 1.15x, 04-11 UTC 1.0x, 12-19 UTC 0.75x. Since October 19 the afternoon Short got a median 0.63x of the same day's evening Short, and six of them stalled under 90 views.
- Judged by: The second Short's day-1 views divided by the same day's first Short's, for 14 days, against the median before.
- Before: median 0.61x over 18 days
- During: median 0.83x over 7 days (ends 2026-11-20)

### Do a real description and a question under each Short get viewers talking?

- Status: **running** since 2026-11-06
- Change: Every edit's description opens with three short paragraphs about the viewer's own life and asks one question ("💬 Question: ... Share your thoughts in the comments."), modelled on the viral Short the owner sent; the same question is the channel's comment under the Short, instead of "Which line hit hardest? Write it below." On every Short from November 6: the owner wants it on all of them, so it is not an A/B.
- Why: Through November 5, viewers left 5 comments on 51 edits (0.48 per 1,000 views). Comments are one of the signals YouTube ranks on, and a question about the viewer's own life is easier to answer than one about the video.
- Judged by: Comments from viewers per 1,000 views on the Shorts in the new style (14 days from the start) against the Shorts of the 14 days before; likes per 100 views alongside.
- Old style: 8 viewer comments on 28 Shorts (1.23 per 1,000 views; 4.4 likes per 100 views)
- New style: 1 viewer comments on 14 Shorts (0.12 per 1,000 views; 2.3 likes per 100 views)

### Do playlists per philosopher bring in extra views?

- Status: **running** since 2026-11-06
- Change: Three public playlists ("Marcus Aurelius quotes: Stoic Shorts", the same for Seneca and Epictetus), with every public edit filed under its philosopher, newest first, and each new Short added the day it airs. A Short the prune bot unlists is taken out, so the playlists show the ones still on the channel.
- Why: Someone who liked one Short can watch that philosopher's others in a row, and the playlists can show up when people search for him.
- Judged by: The share of the channel's views that come from playlists (YouTube's traffic sources), the 14 days after against the 14 before.
- Share of views: 0.0002 before, 0.0 during

### Do the searches people make bring more of them to our Shorts?

- Status: **running** since 2026-11-08
- Change: Each Short's description opens with the YouTube search its quote answers ("How to stop overthinking: Epictetus's answer."), a matching hashtag joins #stoicism, and the search goes into the tags. Ten searches, picked from YouTube's own suggestions (data/search_phrases.json, data/search_research.md). The title carries it too only if the owner picks titles.
- Why: Since June, YouTube search brought 225 views, all from broad words (stoicism, marcus aurelius). Searches like "how to stop overthinking" are among YouTube's most popular, and brought us none: our Shorts never use those words.
- Judged by: The share of views from YouTube search, the 14 days after against the 14 before.
- Share of views: 0.0447 before, 0.0169 during

### Does the crew's new look (painted shots, a hook readable on the first frame, YouTube-level sound) bring more views?

- Status: **running** since 2026-11-12
- Change: Every Short from 2026-11-12: each shot a colour painting from the free FLUX.2 model (inspected before it airs), the v2 type with gold key words, sound mastered to -14 LUFS.
- Why: This month's top Stoicism Shorts are painted, colourful and readable on frame one; ours were washed-out black-and-white stock with a grey first frame and quieter sound.
- Judged by: The median edit's views at 3 days old, the 14 days after against the 14 before.
- Before: median 284 views at 3 days over 26 Shorts

### Does a follow line at the end of every description turn more viewers into subscribers?

- Status: **queued**
- Change: The last line of every edit's description, before the hashtags: "One Stoic line a day. Follow for tomorrow's."
- Why: 98% of views come from people who don't follow the channel (Glaux, 28 days to 11-06); it gains about 1.5 subscribers a day and 1,000 by the end of 2027 needs 1.8. The cheapest ask there is.
- Judged by: New subscribers per 1,000 views, the 14 days after against the 14 before (channel_stats.csv).

### Does a third Short a day, in the evening window, add views a day without starving each Short?

- Status: **running** since 2026-11-13
- Change: From 2026-11-13: three posts a day (MAX_POSTS_PER_DAY 3); the third waits for 19:00 UTC (POST_SLOT_HOURS 0,7,19; the 19:00 and 23:00 crons post it), at least 5 hours apart.
- Why: The 2027 goal needs about 2,740 views a day; two Shorts make about 1,200. Each Short reaches 600 to 950 people in its first days whatever the slot, and the evening slot got 1.15x the reach of its week, so a third post should add roughly 40%.
- Judged by: Views a day (Cicero's funnel, the 14 days after against the 14 before) and the median Short's views at 3 days old, so a third post that only splits the same views shows up.
- Before: median 319 views at 3 days over 24 Shorts

