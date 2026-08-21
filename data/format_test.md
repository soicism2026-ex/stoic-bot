# Format test — 20 videos, one question

_Designed 2026-08-19 after the finding that changed the diagnosis: **210 videos,
zero above 1,255 views, none above 5,000.** This channel has never had a
breakout. That is not a distribution problem to be tuned — it is evidence that
the format has a ceiling._

## The one question

> **Does any video exceed 5,000 views?**

Not medians. Not retention. Not "did it improve." A format that cannot produce
a single breakout in five attempts is not the format, and knowing that in three
weeks beats discovering it in three months.

5,000 is chosen deliberately: it is **4× the best video this channel has ever
made**. Anything less is inside existing noise.

## Why these four

The current format's first frame is a gold-serif quote card over a marble
statue. That is the most saturated aesthetic on Shorts — it reads as
"inspirational content" in under 200ms, which is exactly when the thumb decides.
**Every candidate below differs first and foremost in what the opening frame
looks like**, because that is the only thing that gets a chance to matter.

They also differ in rhythm, so we are not testing four coats of paint.

---

### F1 — FIRST PERSON
**Opening frame:** a human scene (someone sitting on the edge of a bed at 2am).
No card, no statue, no branding.
**Sound:** the owner's own voice, cloned locally from `assets/voice/reference.wav`.
**Text:** big centred captions only. No quote card at any point.
**Shape:** a confession, then the turn. "I lost my temper today. Here's what I
came back to."
**The bet:** authenticity. It looks like a person talking, not a quote account.
This is the only format that uses the one asset no competitor can copy.
**Needs:** reference recording committed + `CHATTERBOX_LOCAL=1`.

### F2 — THE SCREEN
**Opening frame:** a phone notes app or a message thread, rendered full-bleed.
**Sound:** voice reads the message as if typing it.
**Text:** the UI *is* the design — no overlay card.
**Shape:** a message someone needed to receive. "Sent this to a friend at 1am."
**The bet:** pattern interrupt. A screenshot does not look like content, so the
thumb pauses before it classifies it. Native-looking media outperforms designed
media on every short-form platform.
**Needs:** a new render path (draw the UI in ffmpeg). Largest build of the four.

### F3 — THE QUESTION
**Opening frame:** one hard question, plain type, near-black. Nothing else.
**Sound:** SILENCE for the first ~2 seconds. Then the voice answers.
**Text:** question holds, answer replaces it.
**Shape:** "What are you still angry about?" … silence … the Stoic answer.
**The bet:** in a feed engineered to be loud, two seconds of silence and a
direct question is the strongest pattern interrupt available — and it costs
nothing to build. The three-act machinery already does silence timing.
**Needs:** almost nothing. Cheapest test on the list.

### F4 — THE COUNTDOWN
**Opening frame:** a large numeral and a promise. "3 things Marcus did before
sunrise."
**Sound:** brisk, not meditative.
**Text:** hard cuts on each item, number burned in.
**Shape:** list, fast, finish before they decide to leave.
**The bet:** list formats are the most reliably viral structure in the niche and
this channel has never once tried fast pacing. It is the deliberate opposite of
the calm baseline, which is the point — we are testing the axis, not the trim.
**Needs:** pacing changes; `list` format already exists in the schema, unused.

---

## Protocol

**Sample:** 5 videos per format, 20 total. At 3 posts/day that is ~7 days.

**Interleave, never block.** Order is F1, F2, F3, F4, repeat. Posting five F1s
in a row would confound the format with the day, the time slot, and whatever
the algorithm happened to be doing that afternoon.

**Control:** the existing 210 videos. Do not spend test slots re-proving the
baseline — its distribution is already measured (p50 221, p90 787, max 1,255).

**FREEZE EVERYTHING ELSE.** No voice changes, no grade changes, no hook-rule
changes, no rotation changes for the duration. Four unproven variables in
flight at once is how the last three weeks became unreadable. This is the
hardest rule here and the most important one.

## Reading the result

| Outcome | Read | Action |
|---|---|---|
| One format produces a >5,000 view video | That format works | Drop the other three. Make 20 more of it. |
| Two or more do | Both work | Multiply the better one, keep the other as the B slot. |
| None do, but one clearly lifts the median | Directional only at n=5 | Extend that one to 10 more before believing it. |
| **None do, no lift** | **The format was never the problem** | Positioning/niche is wrong. Stop making Stoicism-quote Shorts and reconsider what this channel is. |

That last row is the whole reason to run the test. It is the outcome three
weeks of polish could never have surfaced, and the one worth paying seven days
to find out.

## What this test cannot tell you

- Whether 3/day is right. That is a separate variable, deliberately frozen.
- Whether the niche is saturated. Only a null result across all four hints at it.
- Anything on n=5 medians. **Five videos cannot establish a median.** The test
  is powered to detect a breakout, not to rank formats — do not let a tidy
  leaderboard at the end tempt anyone into treating it as one.
