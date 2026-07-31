# The GUIDE — prompt set for the recurring statue character

The channel has one recurring on-screen character: a **weathered marble bust of a
Stoic philosopher**. It opens every short and closes every short (clips 0 and 5
of 6), and it's the face on every thumbnail. Right now those bookends come from
stock search, which means it's a *different* bust every day — visual noise
wearing a character's clothes.

This document is the one-sitting job that fixes that permanently: generate
20–30 clips of the **same** subject, commit them once, and the pipeline uses
them forever at zero ongoing cost.

**You do not need to read the rest of this file to use the library.** Drop clips
in, run the prep script, commit. There is no flag to set — `src/backgrounds.py`
picks up `assets/guide/*.mp4` automatically for the bookend slots and falls back
to stock search when the folder is empty.

```bash
python scripts/prep_guide_clips.py ~/Downloads/guide_clips
git add -f assets/guide/*.mp4 && git commit -m "guide: curated statue library"
```

---

## 1. Character bible — keep these words in EVERY prompt

The whole exercise fails if the clips don't look like the same object. Paste
this block verbatim into every generation, then add the shot-specific line.

> A weathered white Carrara marble bust of an ancient Greek Stoic philosopher.
> Middle-aged male face, deep-set eyes, heavy brow, short curled beard, straight
> nose, calm closed-mouth expression. Fine hairline cracks and grey veining in
> the stone, dusty patina in the crevices, one chipped edge on the left brow.
> Museum-quality carving, no pedestal text, no plaque.

Lighting and grade, also every time:

> Single hard key light from the upper left, deep chiaroscuro, 90% of the frame
> in near-black shadow, warm candle-temperature highlight on the cheekbone and
> brow, cool blue-grey fill in the shadows. Matte black void background.
> Anamorphic cinematic look, shallow depth of field, subtle film grain.

Why these choices: the render applies a teal-orange grade, warm halation and a
deep vignette on top. Footage that arrives already dark and already
warm-highlight/cool-shadow *survives* that grade. Bright, flat, evenly-lit
statues turn to grey mud.

---

## 2. Global settings

| Setting | Value | Why |
|---|---|---|
| Aspect ratio | **9:16 vertical** | The canvas is 1080×1920. Generating 16:9 and cropping throws away the face. |
| Duration | **4–5 s** | Each clip is a ~3 s bookend. Longer costs more credits for footage nobody sees. |
| Motion | **minimum / "slow"** preset | The render adds its own Ken Burns push. Motion on motion = seasick. |
| Camera move | one only, named in the prompt | Never "dynamic camera" — it whip-pans and breaks the calm. |
| Frame rate | 24 or 30 | Prep script normalises to 30. |
| Audio | off if optional | Stripped anyway; it's dead weight in git. |
| Watermark | **must be off** | A watermark disqualifies the clip. Check the output, not the plan. |

**Negative prompt (paste every time):**

> text, letters, watermark, logo, subtitles, caption, timestamp, human skin,
> living person, blinking eyes, moving mouth, talking, modern clothing, colour
> paint on marble, bright daylight, flat even lighting, white background, blur,
> warping, melting features, extra faces, multiple statues, fast camera
> movement, zoom whip, lens flare spam, cartoon, 3D render look, plastic

`human skin` / `living person` / `moving mouth` matter more than they look. Video
models love to animate a bust into an uncanny talking head. Kill it in the
negative prompt and reject any clip where the face moves.

---

## 3. Composition rule — leave room for the text

The render puts **hook text across the top third** and **quote + author dead
centre**, both in white and gold. So:

- Keep the **top 20% of the frame near-black** — no bright forehead filling it.
- Keep the bust's face in the **middle-lower half**, or let it sit **off-centre
  left/right** with the empty side falling where the text lands.
- No busy background detail anywhere. Void is the friend of legible text.

Shots below are written to obey this. If you improvise, obey it too.

---

## 4. The prompts

Format for each: `[character bible] + [lighting block] + the line below +
[negative prompt]`.

### 4A. Openers — 12 shots (used as clip 0, under the hook text)

These need presence and stillness. The viewer meets the guide in the first
second.

1. **Slow push in.** Head-on three-quarter view, bust centred low in frame, camera pushes in very slowly over 5 seconds. Top of frame falls away into black.
2. **Emerging from dark.** The bust begins almost entirely in shadow; the key light strengthens slowly until the brow and cheekbone are lit. No camera movement.
3. **Profile, right-facing.** Strict side profile on the right third of frame, lit from behind so the nose and brow read as a rim of light against black. Left two-thirds empty.
4. **Profile, left-facing.** Mirror of the above, bust on the left third.
5. **Low angle, looking up.** Camera below eye line looking up at the jaw and brow, statue looming, ceiling void above it. Slow, almost imperceptible tilt up.
6. **Dust in the beam.** A single shaft of light crosses the frame diagonally; fine dust drifts through it. The bust is half-lit where the beam touches it. No camera move. *(Generate two takes — dust results vary wildly and the good one is worth the extra credit.)*
7. **Rack focus.** Foreground stone edge blurred, focus pulls back to the bust's eyes over 3 seconds. Camera static.
8. **Orbit, quarter turn left.** Camera arcs slowly a few degrees around the bust from front to three-quarter. Very slow.
9. **Orbit, quarter turn right.** Mirror of the above.
10. **Candlelight flicker.** Warm unstable candle key from the lower left, shadows breathing on the wall behind. Bust static, camera static.
11. **Top-down key.** Hard light from directly above; eye sockets fall into deep shadow, cheekbones catch the light. Camera holds.
12. **Wide, small in frame.** Bust small in the lower third of a tall black void, a single pool of light around it. Enormous negative space above for the hook text.

### 4B. Closers — 12 shots (used as the final clip, under the CTA beat)

These need departure — the guide receding, settling, going quiet.

13. **Slow pull back.** Starting on the brow, camera retreats steadily until the whole bust sits small in the frame. The exact inverse of shot 1.
14. **Fade into shadow.** The key light dims over 4 seconds until only the edge of the cheekbone remains visible.
15. **Turn away.** Camera drifts from three-quarter view to full profile, as though the guide is turning back to his own thoughts.
16. **Eyes to black.** Tight on the carved eyes, camera holds absolutely still, light slowly falls off.
17. **Descending tilt.** Camera tilts slowly down from the void above onto the bust and settles. Ends static.
18. **Backlit silhouette.** The bust is a pure black silhouette against a dim warm glow behind it. No detail, all shape.
19. **Cracks in close-up.** Extreme close-up on the hairline cracks and veining of the marble jaw, drifting slowly across the surface. Abstract, textural.
20. **Cold blue key.** Same bust, but the key light is cold moonlight blue instead of candle-warm. Static, still. (Register break — use it on the harder themes.)
21. **Long shadow.** Light from the extreme side throws a long hard shadow of the profile across an unseen wall. The shadow, not the bust, dominates the frame.
22. **Settling dust.** Dust motes settle slowly through a dying shaft of light; the bust barely lit beneath. Camera static.
23. **Off-centre, right.** Bust on the right edge of frame, most of the frame empty black. Camera holds. (Text lives in the empty left.)
24. **Off-centre, left.** Mirror of the above.

### 4C. Range extenders — 6 shots (optional; generate if credits allow)

Not bookends specifically — these keep the library from feeling like 24 near-identical takes.

25. **Shoulders and chest.** Wider carve showing the draped stone shoulders, not just the head. Slow push in.
26. **Rain on marble.** Water beading and running down the stone face, lit hard from the side. Slow, no camera move.
27. **Shallow through-foreground.** An out-of-focus stone column edge in the near foreground on one side; the bust sharp behind it. Static.
28. **Two-thirds shadow split.** A hard vertical line of light splits the face — half lit, half void. Static.
29. **Very slow lateral drift.** Camera slides a few centimetres sideways past the bust, parallax against the black. Nothing else moves.
30. **Ember light.** Low warm flickering light from below, like coals, throwing shadows upward across the brow. Static.

---

## 5. Generating them

Any model that does image-to-video or text-to-video vertically will work. What
actually matters, in order:

1. **Watermark-free output.** Free tiers usually watermark. A watermarked clip
   is unusable — it's on screen for every video, forever.
2. **Character consistency.** The single most reliable trick: generate **one
   still image** of the bust you like (any image model, or one good stock photo),
   then use **image-to-video** for all 30 shots with that same still as the input.
   Text-to-video for all 30 gives you 30 different statues, which defeats the
   entire purpose.
3. **Vertical native.** Cropping 16:9 down to 9:16 loses the composition.

On Higgsfield specifically (evaluated 2026-07-30, see `data/decisions.md`): its
camera-motion presets — *slow push in*, *dolly out*, *orbit*, *crash zoom* — map
almost one-to-one onto the shot list above, which is exactly why it's tempting.
The blockers are that the free tier watermarks and the API sits behind paid
tiers. If you buy a month, this list is the shopping list: at ~6 credits a clip
the whole library is ~120–180 credits, one sitting, then cancel. Verify pricing
first — they restructure it often.

## 6. Accepting a clip — checklist

Reject and regenerate if any of these fail. Being strict here is cheap; a bad
clip appears in every video until you remove it.

- [ ] No watermark, no text, no logo anywhere in frame.
- [ ] It is recognisably the **same statue** as the rest of the library.
- [ ] The face **does not animate** — no blinking, no mouth movement, no drifting features.
- [ ] Top ~20% of the frame is dark enough for white text to read over it.
- [ ] No hard cut, no whip pan, nothing faster than a slow drift.
- [ ] Background is void/black, not a bright gallery or sky.
- [ ] It still looks right when darkened — the render adds a vignette and an eq darken on top.

## 7. Installing the library

```bash
# 1. Put every accepted clip in one folder (any name, any format).
# 2. Normalise: 1080x1920, 4s, muted, compressed, sequentially named.
python scripts/prep_guide_clips.py ~/Downloads/guide_clips

#    Options: --seconds 5 --crf 28 (smaller files) --append (add to existing)

# 3. Commit. assets/guide/*.mp4 is NOT gitignored — that's deliberate:
#    unlike stock backgrounds (re-downloaded daily), these must ship with the repo.
git add -f assets/guide/*.mp4
git commit -m "guide: curated statue library"
git push
```

That's it. `daily_post.py` marks the bookend slots via `REEL_GUIDE_SLOTS`, and
`backgrounds.fetch_background()` serves them from the library, rotating by date
and offsetting the closer so a short never opens and closes on the same clip.

**Repo weight:** these are committed files, so every CI checkout pays for them —
3× a day, forever. The prep script warns past 80 MB. 20–30 clips at 4 s and
CRF 25 should land around 40–70 MB. If it's bigger, raise `--crf`.

**Removing a clip you've gone off:** delete the file and commit. The rotation
adapts to whatever is in the folder; empty the folder entirely and the pipeline
silently returns to stock search.
