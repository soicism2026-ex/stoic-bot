# Roadmap — realistic goals, Sept 2026 → Jan 2027

_Written 2026-08-19 from measured rates, not aspiration. Every number here is
derived in `scripts/goal_check.py`, which prints actual-vs-target on demand._

**Baseline on the day this was written:** 228 subs · 57,341 all-time views ·
+1.71 subs/day · +337 views/day (7-day rate, consistent with the 30-day rate).

---

## The finding that shapes everything

YPP's two requirements are wildly asymmetric at this channel's scale:

| Requirement | Status |
|---|---|
| 500 subscribers | **159 days away** at the current rate — reachable |
| 3,000,000 valid public Shorts views / rolling 90 days | **99× short** |

3M views in 90 days is **33,333 views/day**, or **11,111 views per video per
day** at 3 posts/day. The channel does 337/day total. Even a full recovery to
the pre-collapse baseline (~4×) gets to ~1,300/day — still 25× short.

**So: monetisation via YPP is NOT a 5-month goal.** Any plan that treats it as
one is lying. Subscribers are reachable; the view threshold is a different
channel entirely, and reaching it requires repeated genuine virality, not
incremental improvement.

**What this means practically:** the product (The Stoic Reset, Gumroad) is the
realistic revenue path in this window, because it has no threshold. One buyer
today is worth more than a monetisation milestone 18 months out. Views still
matter — they are the top of that funnel — but they are the *input*, not the
finish line.

---

## Monthly targets

Base case assumes the current rate holds with mild compounding as the catalogue
grows. "Stretch" assumes the Aug-2026 recovery works and content quality
compounds. **Miss the base case two months running and the strategy is wrong,
not the execution** — see Tripwires.

| By | Subs (base) | Subs (stretch) | Views/day (base) | 90-day views |
|---|---|---|---|---|
| **19 Sep** (M1) | 280 | 300 | 500 | ~40k |
| **19 Oct** (M2) | 330 | 380 | 800 | ~60k |
| **19 Nov** (M3) | 385 | 470 | 1,200 | ~90k |
| **19 Dec** (M4) | 435 | 560 | 1,800 | ~135k |
| **19 Jan** (M5) | **500** | 650 | 2,500 | ~200k |

500 subs lands at month 5 on the base case and month 4 on the stretch. The view
column is a 7× improvement over five months — ambitious but each step is only
~50% on the one before, which compounding catalogue plus better content can do.

**Primary metric each month is `views/day`, not subs.** Subs are a lagging
consequence of views; optimising subs directly is chasing the shadow.

---

## Risk register

Ordered by expected damage. Each has a mitigation that is already built or is
named as the next thing to build.

### 1. The suppression does not lift _(highest)_
1-day median views fell 77% on 2026-08-05 (242 → 56) and had not recovered as
of 19 Aug. The working theory is repetition-driven demotion.
- **Mitigation (done):** format cut, opener-variety ban list, rule-shape
  rotation, five music beds, hook dedup across all history.
- **If it fails:** the theory is wrong. Next hypothesis is a channel-level
  quality signal, which needs a different response — pausing to post less but
  much better, or starting a clean channel with the same pipeline.
- **Decision date: 2026-08-24.** If the 1-day median is still under 100, say so
  and change theory rather than defending this one.

### 2. Single point of failure: one YouTube account
Everything routes through one channel and one refresh token. A strike, a
suspension, or a revoked token ends the project.
- **Mitigation:** the pipeline is already platform-agnostic —
  `publish_instagram.py` exists but is dormant. **Build: activate a second
  platform.** Same renders, second audience, and insurance against losing the
  first. This is the highest-value unbuilt thing on the list.

### 3. Free-tier dependencies disappear
Cloudflare Workers AI (backgrounds), edge-tts (voice), Pixabay/Pexels (stock),
GitHub Actions (compute) are all free tiers that can change terms without
notice.
- **Mitigation (done):** every one has a fallback chain that degrades rather
  than fails. Cloudflare → OpenAI → stock → synthetic. Voice → edge-tts → gTTS.
- **Residual:** a Cloudflare withdrawal costs quality, not uptime.

### 4. Silent breakage
The recurring failure mode of this project: no error, plausible-looking output,
and only real usage reveals the truth. Rule 7 thirteen times, one music bed
thirty times, a stale CSV header blinding five rotations, a chipmunk voice, a
disconnected retention feed.
- **Mitigation (done):** `variety_check.py` judges output not code, a live test
  guards the posts.csv header, and every A/B is pinned by tests.
- **Rule:** any new feedback loop must have a test proving its input is FRESH,
  not merely present.

### 5. Quality regression from optimising the wrong metric
Views and retention disagreed once already; views would have pushed the channel
toward its worse formats.
- **Mitigation (done):** retention outranks views in all content decisions, and
  it is now pulled daily so the signal cannot go stale.

### 6. Owner-taste drift
Three voice rounds were spent filtering a voice that needed recasting, and
captions were removed entirely when only their collision with the quote was
the problem.
- **Mitigation:** ship samples/frames for judgement BEFORE changing defaults.
  `audition-voices.yml` and `preview-backgrounds.yml` exist for exactly this.
- **Rule:** taste questions get an artifact to react to, never a third guess.

---

## Tripwires — how we know to stop and rethink

- **2026-08-24:** 1-day median still under 100 → repetition theory is wrong.
- **Two consecutive months** under base-case views/day → the strategy is wrong,
  not the execution. Change the plan, do not work harder at it.
- **Any month with sub growth negative** → something is actively repelling
  viewers; audit content tone against doctrine §5 before touching anything else.
- **Product revenue still zero at M3** → the funnel is broken somewhere other
  than views, and more views will not fix it.
