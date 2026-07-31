# assets/guide/ — the recurring GUIDE character

Drop curated `guide_NN.mp4` clips of the marble-statue guide here. They are
**committed on purpose** (unlike `assets/backgrounds/`, which is gitignored and
re-downloaded every run) because the pipeline must find them on a fresh CI
checkout.

- Empty folder → `src/backgrounds.py` falls through to stock search. Nothing
  breaks; the feature is entirely additive.
- Populated → the bookend clips (first and last of the 6-clip assembly, marked
  by `REEL_GUIDE_SLOTS`) come from here, rotating by date, with the closer
  offset so a short never opens and closes on the same clip.

Prompts to generate them: `docs/guide_clip_prompts.md`
Normalise + compress before committing: `python scripts/prep_guide_clips.py <folder>`

Keep the whole folder under ~80 MB — every CI checkout pays for it, 3× a day.
