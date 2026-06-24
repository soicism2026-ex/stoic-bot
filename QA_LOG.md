# QA Log

Automated render-quality results appended by `scripts/daily_post.py`.
Each entry records the date, attempt number, severity, and issues found.
Entries with `uploaded: true` were posted despite issues (minor imperfections
accepted over a missed day). Entries with `uploaded: false` triggered a
backup-bank upload instead.

The `auto-improve.yml` workflow reads this file daily and implements fixes
for any recurring defects.

---

## 2026-06-12 — attempt 1
- uploaded: False
- severity: high
- issues:
  - Major audio/transcript mismatch: The actual audio significantly diverges from the intended Hierocles quote. The narration adds extensive original content about fear, self-care, character, and friendship that is not part of the original quote.
  - The sequence structure suggests this is part of a multi-part series ('tomorrow Hierocles turns...'), but presented as a standalone quote attribution to Hierocles, which is misleading.
  - Text contrast issue: Some yellow/gold text on the cave/water background has marginal readability in certain frames, particularly in the mid-section.
  - Quote authenticity problem: The attribution to Hierocles is incomplete/inaccurate given the substantial narrative additions that frame and extend the original philosophical statement.

## 2026-06-12 — attempt 2
- uploaded: False
- severity: high
- issues:
  - Major audio/caption mismatch: Transcript shows the quote has been heavily modified and expanded with additional commentary about Heracles that is not in the original Hierocles quote. The actual spoken content differs significantly from the intended attribution.
  - Caption accuracy: The quote presented claims to be from Hierocles but the audio/transcript reveals added material about 'Heracles' and extended philosophical commentary that is not part of the original source material.
  - Text contrast issue: Yellow/gold text on red atmospheric background has marginal contrast in several frames, making reading difficult in places.
  - Misleading attribution: Attributing the expanded narration to Hierocles when much of the content appears to be editorial additions or from different sources.

## 2026-06-12 — attempt 3
- uploaded: False
- severity: high
- issues:
  - Major audio mismatch: Actual narration significantly differs from intended Hierocles quote. The video presents an expanded philosophical interpretation rather than the original quote.
  - Caption accuracy: Text overlays present a modified/extended version of the quote, not the original attribution.
  - Misleading attribution: The quote is credited to 'Hierocles' but the content and phrasing have been substantially altered from the historical source.
  - Sequence integrity: The vertical short strings together multiple philosophical statements that don't follow the original source material coherently.

## Visual QA — 2026-06-23 10:54 UTC
**File:** `2026-06-23_reel.mp4` | **Verdict:** `FLAG`
**Hook:** You blame your circumstances.
**Scores:** hook_strength=7.0 | text_legibility=8.5 | pacing=4.5 | scroll_stop_potential=6.0
**Reasoning:** Hook text 'You blame your circumstances.' is a direct, accusatory second-person statement that creates mild discomfort and curiosity, earning a solid 7 — though it's a fairly common Stoic-content opener that won't stop every scroller. Text legibility is strong: the bold yellow all-caps with dark outline reads instantly against the purple sky in frames 1-4 (8.5), while the body quote in frames 5-6 uses a thinner serif over a busier sky/sunset that slightly reduces contrast. Pacing is weak — the first four hook frames are visually near-identical (static text on a barely-shifting purple mountain), giving almost no motion or rhythm in the critical opening 1.5s (4.5). Scroll-stop potential is moderate: the purple-toned landscape is pleasant and the hook is provocative, but nothing is visually arresting or motion-driven in frame 1, so many viewers may keep scrolling (6).
**Issues:**
- Hook frames 1-4 are visually static with identical text — no movement or visual progression during the crucial first 1.5 seconds
- Body quote serif font has lower contrast against the bright sunset background in frame 6, slightly harder to read than the hook
**Suggestions:**
- Add subtle motion to the hook — animated text reveal, zoom/parallax on the mountain, or word-by-word emphasis — to break the static feel and boost scroll-stop power
- Increase contrast on the body quote by adding a semi-transparent dark panel or stronger text shadow, and consider matching the bold hook font for visual consistency
**Flagged dims:** pacing


## Visual QA — 2026-06-23 16:24 UTC
**File:** `2026-06-23_reel.mp4` | **Verdict:** `FLAG`
**Hook:** You snapped again today.
**Scores:** hook_strength=8.0 | text_legibility=9.0 | pacing=3.5 | scroll_stop_potential=7.0
**Reasoning:** The hook 'You snapped again today.' is direct, personal, and accusatory in a way that creates immediate self-reflection — strong for the anger theme, though it relies entirely on text rather than a visually arresting opener. Text legibility is excellent in the hook: bold yellow caps with dark outline pop against the moody purple seascape; the body quote uses a thinner serif that is slightly less punchy but still readable. Pacing is the weak point — frames 1–4 are nearly identical static shots of the same coastline with no movement, transition, or zoom, so the opening 1.5s feels frozen; only the body switches scenery (coast to pyramid). Scroll-stop potential is solid thanks to the confrontational hook line and atmospheric color grade, but the static first frame won't grab everyone purely on visuals.
**Issues:**
- Hook frames 1-4 are visually static — no motion or transition during the critical first 1.5 seconds
- Body quote uses a thin serif font that is lower-impact than the bold hook style and could be harder to read at a glance
**Suggestions:**
- Add a subtle zoom-in or parallax push on the coastline during the hook to inject motion and stop scrollers
- Animate the hook text in word-by-word (e.g. 'snapped' punching in) to add kinetic energy and emphasize the key word
**Flagged dims:** pacing


## Visual QA — 2026-06-23 19:34 UTC
**File:** `2026-06-23_reel.mp4` | **Verdict:** `PASS`
**Hook:** 5 Rules to Kill Endless Wanting
**Scores:** hook_strength=7.5 | text_legibility=8.5 | pacing=6.5 | scroll_stop_potential=7.0
**Reasoning:** Hook text '5 RULES TO KILL ENDLESS WANTING' is strong copy — numbered listicle plus the aggressive verb 'kill' creates curiosity and promises value, earning 7.5; the dramatic fiery molten visual is genuinely arresting but slightly abstract. Text legibility is high at 8.5 thanks to bold yellow caps with dark outline against dark backgrounds, though the bright molten orange in frames 3-4 reduces contrast on the lower edge. Pacing scores 6.5 — the first four hook frames are nearly identical with only subtle movement in the lava, so the opening feels visually static before the strong transition to the quote and pyramid backdrop. Scroll-stop potential is 7.0: the glowing fire and high-contrast text would catch many feeds, but the molten texture is somewhat ambiguous and not instantly tied to the Stoicism theme.
**Issues:**
- First four hook frames are nearly static with only minor lava movement, wasting the critical 1.5s window
- Fiery molten background is visually striking but thematically ambiguous — doesn't immediately signal Stoicism/desire
**Suggestions:**
- Add a punchy motion or scale/zoom on the hook text within the first 0.5s to inject energy and stop the scroll
- Animate the rules as a quick numbered count-up (1...5) or briefly flash a face/eyes in the hook to anchor the human/philosophical angle


## Visual QA — 2026-06-23 22:11 UTC
**File:** `2026-06-23_reel.mp4` | **Verdict:** `PASS`
**Hook:** You begged for an easy life.
**Scores:** hook_strength=8.0 | text_legibility=8.5 | pacing=5.5 | scroll_stop_potential=7.5
**Reasoning:** Hook scores high — 'You begged for an easy life' is a confrontational, second-person statement that creates immediate tension and curiosity, paired with a moody crashing-wave visual that fits the resilience theme. Text legibility is strong: bold yellow all-caps with dark outline sits clearly against the purple ocean backdrop, though the busy water texture costs it a perfect score. Pacing is the weakest dimension — the first four hook frames are nearly identical (same wave, same text, minimal motion), so the opening 1.5s feels static rather than energetic; the body does introduce a strong scene change to the pyramid which helps. Scroll-stop potential is solid thanks to the vivid purple/magenta color grade and the accusatory hook line, but the slow-moving water and conventional quote-card aesthetic mean some scrollers will pass.
**Issues:**
- First four hook frames are virtually identical with negligible visual change, making the critical opening feel static
- Body quote text uses a serif font that is lower-contrast and slightly harder to read at speed than the bold hook caption, especially over the bright pyramid sky in frame 6
**Suggestions:**
- Add motion to the hook window — a punch-in zoom, a word-by-word text reveal, or a faster wave clip — so the opening 1.5s has visible momentum
- Boost contrast on the body quote (heavier weight, stronger drop shadow or a subtle dark scrim behind the text) and consider chunking it into shorter timed lines synced to the voiceover for better readability and pacing


## Visual QA — 2026-06-24 10:36 UTC
**File:** `2026-06-24_reel.mp4` | **Verdict:** `FLAG`
**Hook:** Your fear is loud.
**Scores:** hook_strength=7.5 | text_legibility=8.0 | pacing=4.5 | scroll_stop_potential=7.0
**Reasoning:** The hook 'YOUR FEAR IS LOUD' is punchy, relatable, and creates emotional curiosity — strong but slightly generic in the saturated Stoicism niche, so 7.5. Text legibility is good: bold yellow/orange caps with dark outline read clearly against the purple forest, though the lower body quote uses a thin serif font that is harder to read at phone size, pulling it to 8.0. Pacing is the weak point — frames 1–4 are essentially identical static shots with the same text, meaning the entire 1.5s hook window has zero visual movement or transition energy, hence 4.5. Scroll-stop potential is solid at 7.0 thanks to the moody, atmospheric purple-lit forest and high-contrast hook text, which is visually distinct enough to interrupt a feed, though it lacks a human face or motion that would push it higher.
**Issues:**
- Hook frames 1-4 are visually static — identical background and text for the full 1.5s opening, no movement or zoom to hold attention
- Body quote uses a thin serif font (frames 5-6) that is lower contrast and harder to read at phone size than the bold hook caps
**Suggestions:**
- Add a subtle slow zoom, parallax, or light flicker to the hook frames so the opening 1.5s feels alive instead of frozen
- Switch the body quote to a bolder, higher-contrast sans-serif or add a stronger drop shadow/background plate to match the legibility of the hook text
**Flagged dims:** pacing


## Visual QA — 2026-06-24 15:49 UTC
**File:** `2026-06-24_reel.mp4` | **Verdict:** `PASS`
**Hook:** Your friends are convenient strangers
**Scores:** hook_strength=8.5 | text_legibility=8.0 | pacing=6.0 | scroll_stop_potential=7.5
**Reasoning:** The hook 'Your friends are convenient strangers' is provocative and pattern-interrupting — it creates immediate cognitive dissonance that makes viewers want the resolution, earning a high hook_strength. Text legibility is strong in the hook frames (bold yellow caps with drop shadow over a dark purple background read instantly), but the body frames switch to a thinner serif font in pale gold over a busy waterfall area, slightly reducing contrast, so 8.0. Pacing is the weakest dimension: frames 1-4 are nearly identical with only a minor 'FRIENDS' kinetic word popping in frame 2, and the background motion (waterfall) moves slowly, so the visual rhythm feels static rather than energetic. Scroll-stop potential is good — the striking yellow headline against the moody purple cascade is eye-catching and the claim is intriguing — but the static feel and generic nature backdrop keep it just under an automatic stop.
**Issues:**
- Hook frames 1, 3, and 4 are nearly identical, creating a static feel during the critical first 1.5 seconds
- Body quote uses a thinner serif gold font that loses contrast against the lighter waterfall and rocks, hurting readability
**Suggestions:**
- Add kinetic typography in the hook window — animate words in word-by-word or add a subtle zoom/punch to keep visual energy high
- Increase body-text contrast by adding a semi-transparent dark panel behind the quote or using a heavier font weight

