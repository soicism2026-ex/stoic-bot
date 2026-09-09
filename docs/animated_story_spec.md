# Animated story shorts — production spec

**What this is:** the channel becomes ANIMATED NARRATIVE. Characters on screen,
scenes that connect, events unfolding. Not a voice over stock footage. Not
stills with a slow zoom. The reference the owner gave is a 2D animated faceless
video — lightning strikes a tree, two cavepeople find fire, they carry it home,
they gather round it — where the picture *tells* the story.

**What it replaces:** every short to date has been narration over unrelated
b-roll that cuts every few seconds. The owner's verdict on the last attempt:
*"It's just a video of waves of water... I want it to actually be an engaging
entertaining video like something you would see on an actual YouTube channel."*

---

## The three things that make it a story rather than a montage

1. **A character the viewer follows.** The same person, recognisable across
   every scene. This is the hard part — image models drift, and a different
   face each scene reads as a slideshow, not a story. Solved by locking a
   character reference and passing it into every scene generation.
2. **Cause and effect between shots.** Shot 2 happens *because* of shot 1. The
   cavepeople clip works because lightning → fire → carrying it → the hearth.
   Our current b-roll has no causal chain at all; the clips are interchangeable.
3. **One locked art style.** A single non-photoreal look across all scenes, so
   the video reads as one made thing rather than four stock clips stapled
   together.

---

## Worked example — "The man who is not ill and is not well"

Source: Serenus writing to Seneca, *De Tranquillitate Animi* I.
Runtime target: 40-50s. 7 scenes. Same two characters throughout.

| # | On screen (animated) | Narration |
|---|---|---|
| 1 | A young Roman, SERENUS, sits at a desk at night. One lamp. He writes a line, stops, crosses it out. Crumples the page. Reaches for another. | Two thousand years ago a man wrote his friend a letter that just said: I'm not ill, and I'm not well. |
| 2 | Close on his hand. The page has three crossed-out openings. He finally writes clean: *"I am neither sick nor well."* | His name was Serenus. He wasn't in crisis. Nothing had collapsed. |
| 3 | He looks up and out of a window. The street below is ordinary — people going home. He watches, expressionless. | He just couldn't tell if anything was wrong. |
| 4 | **The metaphor becomes literal.** The room dissolves into a small boat on flat grey water. Serenus sits in it. No storm. The boat rocks very slightly. He looks faintly, persistently unwell. | So he tried to describe it: I am distressed, not by a tempest, but by sea-sickness. No storm. Just the sway. |
| 5 | Pull back — the boat is tiny on an enormous calm sea. Nothing is happening. That is the point. | If you've been flat for weeks and can't point at a reason, that's it. It has a name, and it's old. |
| 6 | Cut to SENECA, older, reading the letter in his own room. He does not frown or lecture. He pulls a fresh sheet toward him and begins to write — and keeps writing, pages stacking. | Seneca didn't tell him to toughen up. He wrote him a whole book back. |
| 7 | Present day. A man on the edge of his bed at night, phone lit in his hand. He types one short line and sends it. Small exhale. Screen goes dark. | Tonight, do the Serenus thing. Text one person the actual sentence: I'm not bad, I'm just off. |

**Why this works and the water clip didn't:** scene 4 is the whole idea made
visible — the viewer *sees* sea-sickness without a storm, which is exactly what
Serenus said and exactly what the viewer feels. The earlier attempt generated
the sea with no man, no boat, no letter, no reason to care.

---

## Production contract

- **Character lock.** Serenus and Seneca are generated once as reference stills
  and passed into every scene, or the video becomes a slideshow of strangers.
- **Style lock.** One art direction across all 30 stories so the channel is
  recognisable in a feed: muted painterly, desaturated blue-grey, soft grain,
  no photoreal faces.
- **The narration already exists.** All 30 scripts are written, verified and
  live in `data/stories.json`. This spec changes only what is on screen.
- **Vertical.** 9:16. The one clip generated so far came back 1024x1024 square
  because `minimax_hailuo` ignores `aspect_ratio` — pick a model that honours
  it (`cinematic_studio_video_v2`, `minimax_h3`) or generate wide and crop.

## Cost, measured not estimated

| Item | Credits |
|---|---|
| Scene still (`gpt_image_2`, 1k) | 0.5 |
| Animated clip, 6s (`minimax_hailuo`) | 6 |
| **7-scene story video** | **~45** |

- 20 videos/month ≈ 900 credits → **Plus, $29/mo annual (1,000)**
- 30 videos/month ≈ 1,350 credits → **Ultra, $70/mo annual (3,000)**

Free tier cannot generate a single frame: image generation returns
*"Requires basic plan or higher."*
