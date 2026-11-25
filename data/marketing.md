# Marketing: how the channel reaches people

_Updated 2026-11-24 by Cicero (scripts/marketer.py, free, no paid API)._

## The funnel

- Views a day, last 7 days: **431** (the 7 before: 987, -56%)
- New subscribers a day: **1.1** (the 7 before: 1.7); 291 in all
- Subscribers per 1,000 views: 2.6
- Likes per 100 views (Shorts of the last 14 days): 3.4

## Reach by upload hour (UTC)

Each Short's day-1 views against the Shorts aired within a week of it.

| Hour (UTC) | Shorts | Reach vs its week | Stalled (<0.4x) |
|---|---|---|---|
| 00-03 | 98 | 1.21x | 14 |
| 04-07 | 29 | 1.01x | 5 |
| 08-11 | 81 | 1.03x | 11 |
| 12-15 | 31 | 0.69x | 7 |
| 16-19 | 58 | 0.66x | 11 |
| 20-23 | 47 | 0.81x | 9 |

## Who watches (last 28 days, pulled 2026-11-24)

- Countries: US 66%, IN 15%, CA 6%, GB 4%, DE 3%, ZA 1%
- How they find the Shorts: SHORTS 92%, YT_SEARCH 4%, YT_OTHER_PAGE 2%, YT_CHANNEL 2%, EXT_URL 0%
- Subscribed or not: UNSUBSCRIBED 97%, SUBSCRIBED 3%
- What they typed into YouTube before watching (since June): "stoicism" (61), "marcus aurelius" (18), "stoic" (18), "stoicism marcus aurelius" (18), "stoicism motivation" (17), "epictetus" (11), "stoicism philosophy" (11), "marcus aurelius meditations" (10), "stoic mindset" (8), "stoic wisdom" (8)

## The goal

- **A million views and 1,000 subscribers in 2027** (by 2027-12-31)
- Views in 2027: 0 of 1,000,000 (starts; 702 a day now, 2,740 needed)
- Subscribers: 291 of 1,000 (behind; 1.7 a day now, 1.8 needed)
- Next checkpoint 2027-03-31: behind
- Every test below is judged by whether it moves these numbers.

## Tests (one change at a time, each only with the owner's yes)

### Does the second Short reach more people in the morning than in the afternoon?

- Status: **done** since 2026-11-06
- Change: The second Short goes out from 07:00 UTC (about 3-5 AM Toronto) instead of 15:00 UTC (about 11 AM-1 PM Toronto). Still 2 a day; the evening Short stays put.
- Why: Across 294 Shorts, each against its own week: 00-03 UTC 1.15x, 04-11 UTC 1.0x, 12-19 UTC 0.75x. Since October 19 the afternoon Short got a median 0.63x of the same day's evening Short, and six of them stalled under 90 views.
- Judged by: The second Short's day-1 views divided by the same day's first Short's, for 14 days, against the median before.
- Before: median 0.61x over 18 days
- Verdict: **win** (The second Short goes out from 07:00 UTC (about 3-5 AM Toronto) instead of 15:00 UTC (about 11 AM-1 PM Toronto). Still 2 a day; the evening Short stays put.x)

### Do a real description and a question under each Short get viewers talking?

- Status: **done** since 2026-11-06
- Change: Every edit's description opens with three short paragraphs about the viewer's own life and asks one question ("💬 Question: ... Share your thoughts in the comments."), modelled on the viral Short the owner sent; the same question is the channel's comment under the Short, instead of "Which line hit hardest? Write it below." On every Short from November 6: the owner wants it on all of them, so it is not an A/B.
- Why: Through November 5, viewers left 5 comments on 51 edits (0.48 per 1,000 views). Comments are one of the signals YouTube ranks on, and a question about the viewer's own life is easier to answer than one about the video.
- Judged by: Comments from viewers per 1,000 views on the Shorts in the new style (14 days from the start) against the Shorts of the 14 days before; likes per 100 views alongside.
- Before: 9 viewer comments on 28 Shorts (1.38 per 1,000 views)
- Verdict: **loss** (Every edit's description opens with three short paragraphs about the viewer's own life and asks one question ("💬 Question: ... Share your thoughts in the comments."), modelled on the viral Short the owner sent; the same question is the channel's comment under the Short, instead of "Which line hit hardest? Write it below." On every Short from November 6: the owner wants it on all of them, so it is not an A/B.x)

### Do playlists per philosopher bring in extra views?

- Status: **done** since 2026-11-06
- Change: Three public playlists ("Marcus Aurelius quotes: Stoic Shorts", the same for Seneca and Epictetus), with every public edit filed under its philosopher, newest first, and each new Short added the day it airs. A Short the prune bot unlists is taken out, so the playlists show the ones still on the channel.
- Why: Someone who liked one Short can watch that philosopher's others in a row, and the playlists can show up when people search for him.
- Judged by: The share of the channel's views that come from playlists (YouTube's traffic sources), the 14 days after against the 14 before.
- Share of views: 0.0002 before
- Verdict: **no clear change** (Three public playlists ("Marcus Aurelius quotes: Stoic Shorts", the same for Seneca and Epictetus), with every public edit filed under its philosopher, newest first, and each new Short added the day it airs. A Short the prune bot unlists is taken out, so the playlists show the ones still on the channel.x)

### Do the searches people make bring more of them to our Shorts?

- Status: **done** since 2026-11-08
- Change: Each Short's description opens with the YouTube search its quote answers ("How to stop overthinking: Epictetus's answer."), a matching hashtag joins #stoicism, and the search goes into the tags. Ten searches, picked from YouTube's own suggestions (data/search_phrases.json, data/search_research.md). The title carries it too only if the owner picks titles.
- Why: Since June, YouTube search brought 225 views, all from broad words (stoicism, marcus aurelius). Searches like "how to stop overthinking" are among YouTube's most popular, and brought us none: our Shorts never use those words.
- Judged by: The share of views from YouTube search, the 14 days after against the 14 before.
- Share of views: 0.0452 before
- Verdict: **no clear change** (Each Short's description opens with the YouTube search its quote answers ("How to stop overthinking: Epictetus's answer."), a matching hashtag joins #stoicism, and the search goes into the tags. Ten searches, picked from YouTube's own suggestions (data/search_phrases.json, data/search_research.md). The title carries it too only if the owner picks titles.x)

### Does the crew's new look (painted shots, a hook readable on the first frame, YouTube-level sound) bring more views?

- Status: **running** since 2026-11-12
- Change: 0.74
- Why: This month's top Stoicism Shorts are painted, colourful and readable on frame one; ours were washed-out black-and-white stock with a grey first frame and quieter sound.
- Judged by: The median edit's views at 3 days old, the 14 days after against the 14 before.
- Before: median 284 views at 3 days over 28 Shorts
- During: median 209 views at 3 days over 29 Shorts (ends 2026-11-26)

### Does a follow line at the end of every description turn more viewers into subscribers?

- Status: **running** since 2026-11-22
- Change: 3.92
- Why: 98% of views come from people who don't follow the channel (Glaux, 28 days to 11-06); it gains about 1.5 subscribers a day and 1,000 by the end of 2027 needs 1.8. The cheapest ask there is.
- Judged by: New subscribers per 1,000 views, the 14 days after against the 14 before (channel_stats.csv).

### Does a third Short a day, in the evening window, add views a day without starving each Short?

- Status: **running** since 2026-11-13
- Change: 0.69
- Why: The 2027 goal needs about 2,740 views a day; two Shorts make about 1,200. Each Short reaches 600 to 950 people in its first days whatever the slot, and the evening slot got 1.15x the reach of its week, so a third post should add roughly 40%.
- Judged by: Views a day (Cicero's funnel, the 14 days after against the 14 before) and the median Short's views at 3 days old, so a third post that only splits the same views shows up.
- Before: median 304 views at 3 days over 28 Shorts
- During: median 209 views at 3 days over 27 Shorts (ends 2026-11-27)

### Does tying a Short's hook, description lead and question to what the US is talking about today add views and comments?

- Status: **running** since 2026-11-16
- Change: 0.52
- Why: The owner finds the Shorts a bit boring and wants them relevant to today's world. A hook that meets viewers in an event they already know should stop more scrolls and give them something to answer.
- Judged by: the median edit's views at 3 days old, 14 days after against 14 before
- Before: median 336 views at 3 days over 31 Shorts
- During: median 176 views at 3 days over 18 Shorts (ends 2026-11-30)

### Does the search in the title bring more viewers from YouTube search?

- Status: **running** since 2026-11-22
- Change: Each Short's title carries the search its quote answers, e.g. "How to control your emotions | Marcus Aurelius" style: the hook, then the search, then the author. The description lead, hashtag and tags stay as in test search-phrases.
- Why: Test search-phrases put the searches in descriptions, hashtags and tags; the title is the field YouTube weighs most for search, and the owner said yes to it once that test ends.
- Judged by: The share of views from YouTube search, the 14 days after against the 14 before (same measure as search-phrases).
- Share of views: 0.0359 before

### Did the Nov 16 changes (news-tied hooks, no comment line) cost views?

- Status: **running** since 2026-11-24
- Change: Nov 20-22, and again Nov 24-30: Shorts open with their own hooks (Fama's news tie-ins paused) and the description's question ends with 'Share your thoughts in the comments.' again. The painted look, the red key words and the owner's personal Shorts stay.
- Why: Shorts posted since Nov 16 average about 105 views on day one, against 186 in October and 265 for the first painted Shorts (Nov 12-15). The Nov 16 changes (news-tied hooks from Fama, and the description no longer ending its question with 'Share your thoughts in the comments.') line up with the drop.
- Judged by: median day-1 and day-3 views of the Shorts posted Nov 24-30 against those posted Nov 16-19 (the first run: Nov 20-21)
- Before: median 109 views at 1 days over 12 Shorts

### Do animated backgrounds bring more views than painted stills?

- Status: **running** since 2026-11-23
- Change: From 2026-11-23 to 2026-12-22: the first Short of each day animates 3 of its paintings (the hook's shot and two more) with Seedance 2.0 Mini on Higgsfield, 5 seconds each; every other shot stays painted. At most 3 clips a day. It starts as soon as Higgsfield has credits.
- Why: owner's choice in the HQ, 2026-11-22
- Judged by: day-3 views of the video Short against the same day's painted Shorts, over the month
- Before: median 237 views at 3 days over 35 Shorts

### Do Shorts with their own hooks and the comment ask beat news-tied hooks over a full week?

- Status: **proposed**
- Change: If the owner says Go: keep Fama's news tie-ins paused (the topical test ends) and keep ' Share your thoughts in the comments.' on the question line, for 7 days.
- Why: The 3-day undo test: 163 day-1 views on 6 Shorts vs 109 on the 12 from Nov 16-19 (1.5x); the news-tied test sits at 147 views at 3 days vs 336 before.
- Judged by: Median day-1 views of the Shorts of the 7 days against Nov 16-19 and against the 14 days before Nov 16.
- Before: median 175 views at 1 days over 34 Shorts

### Does a closing pitch for the journal sell without costing views?

- Status: **running** since 2026-11-25
- Change: The day's third Short (19:00 UTC), from 2026-11-25 for 14 days: Brian reads one closing line after the quote ("If this one hit home, the Stoic Reset is thirty days of exactly this."), a card in the last 2.5 s says THE STOIC RESET / 30 days. One page a day. / Link on our channel page, its pinned comment is the pitch, and its description keeps the journal line with the link https://soicism.gumroad.com/l/cslosv?ref=short-cta. The other Shorts stay as they are. Nothing in it promises more than the product is: a 30-day guided journal, C$5.99.
- Why: Owner, 2026-11-24, in chat: "we need to entice peopl to buy something off gum road on the shorts. And we have to make it feel like they need it or itll chnage thier life forever". The channel has 98% unsubscribed viewers and no sale path inside a Short; the line and card ask once, plainly, and the tracking link shows what it sells.
- Judged by: Views at 3 days of the pitch Short over the median of the day's other Shorts, the 14 days against the days since the third Short began (2026-11-13). Sales: the owner reads Gumroad's dashboard for ref short-cta (the bot has no Gumroad key yet; idea-gumroad-hq asks for one). Retention is not yet read per Short. Days where the pitch Short or the others aired unpainted go in `exclude`.
- Before: median 1.22x over 9 days

