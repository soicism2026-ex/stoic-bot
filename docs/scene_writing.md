# Scene writing: what each Short shows, and which words get the gold

For Varro (the weekly restocker). Every new quote in `data/edit_quotes.json` should
carry three extra fields, validated by `python scripts/shelf.py check FILE`
(`shelf.scene_problems`). They are optional for old quotes; give all three or none.
The painter (image model) reads `scenes`; the typographer reads `emphasis` and
`hook_emphasis`. Field order: after `visuals`, in this order.

## The fields

- `scenes`: 6 to 8 strings, in on-screen order, one per cut (about 1.3 s each over a
  10 s Short). Each is ONE shot an image model can paint, 8 to 45 words.
- `emphasis`: 1 to 3 words or phrases copied exactly from the quote (case does not
  matter): the words the line turns on. Set in gold italic.
- `hook_emphasis`: one word or phrase copied exactly from the hook.

## Writing a shot

1. **Subject + what it is doing + where + a named physical light source.** The light
   is required (oil lamp, torchlight, firelight, dawn, sunset, overcast noon, window,
   doorway...). "Golden hour" and "torchlit" count. A bare "light" does not.
2. **Ancient Roman or Greek world, 1st-2nd century.** Clay, bronze, wool, stone,
   torches, scrolls. The linter bans what did not exist (lantern, book, paper, pen,
   glasses, clock, journal, screen...). A water clock is "water dripping from a bronze
   spout into a basin".
3. **Vertical frame, subject in the middle third.** One or two people at most.
4. **Cast tokens, never names.** `{marcus}`, `{seneca}`, `{epictetus}`, `{man}`
   (a recurring late-20s Roman man: the viewer's stand-in). Other people are plain
   ("a ragged old fisherman", "a friend's broad hand").
5. **Say what is there, never what is not.** No "no", "not", "without", "nothing",
   "never", "n't": the model paints the thing you negate. Name the light instead.
6. **No style words** (cinematic, 4k, painterly, grainy, black and white, bokeh...):
   the code adds the look. **No writing**: no signs, words, letters, notes, labels,
   pages. **No gore**, adults only.

## Directing the six to eight

- **Shot 1 is the stopper**: a person in a situation, colour, drama, something the
  viewer waits on. Never a statue, bust or postcard landscape (doctrine §6).
- **Follow the quote's own image, not its mood, and never illustrate the voice
  literally** (§6): image and words meet, they do not repeat. "A full cup trembling"
  beats "a moody room".
- **Vary scale**: close-up on hands or a face, medium, one wide. Roughly: stopper
  (medium), 2 close-ups, 1 wide, 1 medium, then the resolution.
- **Arc**: tension, then the turn the quote makes, then relief. The last two shots
  are resolve or release, never grimness (doctrine §5: leave him better, never
  smaller; the door is wide: the tired, the stuck, the ashamed).
- Gold words: the two or three that carry the line ("without arrogance", "let it
  go"), not the grammar. Hook gold: the part that names his situation.

## Three worked examples

**pile_of_troubles** (Seneca, anger). Quote: "Nothing need provoke one's anger if
one does not add to one's pile of troubles by getting angry." Hook: "Angry about
it? Now it's two problems." `emphasis`: `pile of troubles`, `getting angry`;
`hook_emphasis`: `two problems`.
1. A clay amphora shattered on a stone courtyard, red wine spreading, {man} staring
   down with clenched fists, hard noon sun (stopper: the first problem, in colour)
2. Close-up of {man}'s face, jaw tight and eyes hot, torchlight flickering from one side
3. A heap of broken pottery on a workshop floor, a second jar toppled onto it, dust
   rising in a shaft of afternoon sun through a doorway (the quote's own image: a pile)
4. {seneca} on a stone garden bench at golden hour, hands folded ... a calm and
   knowing look (the teacher, calm)
5. Close-up of {man} with eyes closed taking one slow breath, soft window light
6. {man} kneeling to gather the shards into a wicker basket with steady hands
7. {man} carrying the basket out through a stone archway, shoulders level, warm dawn
   (he deals with problem one, adds no second: resolve)

**death_behind_you** (Seneca, mortality). Quote: "...the major portion of death has
already passed." Hook: "Death isn't ahead of you." `emphasis`: `already passed`,
`look forward to death`; `hook_emphasis`: `ahead of you`. The picture finds the
quote's own image (time already spent, behind you) rather than a skull: {man} faces
the sea at a clifftop while his long shadow stretches far back behind him in the low
orange sun; a sundial shadow near the edge of its dial; water dripping from a bronze
spout into a basin; {seneca} looking back along a cypress path; a road winding down
the valley he has already walked; cupped hands catching a beam of sun; and the close,
{man} turning to the camera with a small smile. It scares no one: it wakes him up.

**naturally_dull** (Epictetus, discipline). Quote: "What then, since I am naturally
dull, shall I, for this reason, take no pains? I hope not." Hook: "Not naturally
gifted? Read this." `emphasis`: `naturally dull`, `take no pains`; `hook_emphasis`:
`Not naturally gifted`. For the man who feels behind (§1): a sweat-streaked close-up
turning from frustration to resolve under hard noon sun; blistered hands on a wooden
practice sword; a miss at the post in a puff of dust; {epictetus} nodding in a shaded
portico; a chisel chipping a clean line into marble (effort accumulating); the same
strike landing clean mid-swing; and at sunset {man} with a towel over his shoulders,
tired and proud, grinning. Talent decides where you start, and the pictures show where
effort ends up.

## Varro's restock checklist, additions

1. For every new quote, write `scenes`, `emphasis` and `hook_emphasis` after
   `visuals` (keep `visuals`: older render paths and the stock fallback still use it).
2. Read the quote's own image first; write the shots for it, then check shot 1 is a
   person in a situation and the last two shots resolve.
3. Run `python scripts/shelf.py check FILE`: it fails on counts, unknown cast tokens,
   negations, style words, writing requests, anachronisms, a missing light source, a
   statue opener, and emphasis not verbatim in the quote or hook.
4. Review before `add`: would a shot still make sense if the quote were swapped for
   another? Then it is atmosphere, not a shot; rewrite it.
