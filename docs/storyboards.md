# Storyboards — the next five shorts

**Status: DRAFT FOR OWNER APPROVAL.** Nothing here airs until approved
(standing rule: "dont ship anything until i approve it").

Written 2026-09-23 to the owner's two directions (doctrine §8):
lead with the viewer's problem, then the ancient proof; land in 30–40 seconds.

## The device: "the same moment, 2,000 years apart"

Every short opens on a modern man living the viewer's problem, then **match-cuts
to the ancient figure in the same pose, the same light, the same framing.** The
viewer's first thought is "that's me"; the cut answers "and it was him too".
That turns the channel's whole argument — *you are not the first* — into a
picture instead of a claim, and it is a look no other Stoic channel has.

Rules for every board:
- Shot 1 poses a question the picture cannot answer (doctrine §6).
- Follow the script's own images, never its mood (§6). Never show what the
  voice is literally saying at that second — meet it, don't repeat it.
- A cut every 3–4 seconds (§7). Nothing holds.
- Frames must be visibly lit — warm practical light, not murk (§6, luma floor).
- No text in the generated footage; the hook and quote are drawn by render.py.
- Quotes and citations are verbatim from `data/stories.json`. Scripts are
  TRIMMED, never extended with new claims.

## How the pictures get made (and what it costs)

Measured from the Higgsfield API docs, 2026-09-23:

- **Kling 2.5 text-to-video has no aspect-ratio setting** — it would arrive
  landscape and lose two thirds of the frame in a vertical crop. **Image-to-video
  follows the start image's shape.** So every shot is two steps:
  1. a 9:16 **keyframe still** (image model),
  2. **Kling 2.5 image-to-video**, 5 seconds, animates it.
- Consistency: the modern man and the ancient figure are each described ONCE
  per story (the "cast" line below) and that exact description is reused in
  every keyframe prompt. This is the fix for the smoke test, where the man in
  the close-up was visibly a different person.
- **Cost at the 7-day discount** (Kling 2.5 from $0.021/s): 5s × $0.021 =
  ~$0.11 a shot; 8 shots ≈ **~$0.85 a short** plus keyframes. After the
  discount ends it roughly doubles to ~$1.70.
- 5-second clips, cut to ~3.5s on screen — the spare second is the handle the
  editor trims from, so the cut lands on motion, not on a start frame.

Timing uses the voice's measured rate, 2.65 words/second, plus the 2.4s silent
read beat when the quote comes up.

---

## 1 · `before_breakfast` — Marcus Aurelius · ~35s

**Cast.** Modern: *a man in his early thirties, short dark hair, grey t-shirt,
plain modern apartment.* Ancient: *Marcus Aurelius in his fifties, curly
greying beard, plain wool tunic and cloak, Roman military camp.*

**Script (for approval)**

> **Hook:** Dreading tomorrow's people doesn't make you weak.
> The Emperor of Rome felt it too. Marcus Aurelius wrote himself a script for
> the morning, and book two of his notebook opens with it.
> **[quote on screen, silent read beat]** *Begin the morning by saying to
> thyself, I shall meet with the busybody, the ungrateful, arrogant, deceitful,
> envious, unsocial.* — Meditations 2.1, trans. George Long
> That isn't bitterness. It's a forecast, so nine o'clock isn't an ambush. Have
> tomorrow's meeting now, in your head, where it's cheap. Tonight, say out loud
> who'll be hard work. Naming them takes the charge out.

| # | Time | Voice over it | Picture | Camera |
|---|---|---|---|---|
| 1 | 0.0–3.5 | "Dreading tomorrow's people…" | Modern man sitting on the edge of his bed in the dark, phone alarm glowing beside him, not moving to switch it off. | Static wide, slow creep in |
| 2 | 3.5–7.0 | "The Emperor of Rome felt it too." | **MATCH CUT.** Marcus on the edge of a camp cot in a leather tent, same pose, one oil lamp where the phone was. | Same framing as 1 |
| 3 | 7.0–10.5 | "…wrote himself a script…" | Close: an old hand with a stylus pressing into a wax tablet, lamp flicker. | Macro, locked |
| 4 | 10.5–14.0 | "…book two… opens with it." | Tent flap stirring; beyond it, rows of tents in blue pre-dawn, smoke from a fire. | Slow push toward the flap |
| 5 | 14.0–19.5 | *(quote on screen)* | Marcus in profile, eyes closed, lips moving slightly — rehearsing. Held long enough to read the card. | Very slow push |
| 6 | 19.5–23.0 | "That isn't bitterness. It's a forecast…" | Modern man at the bathroom mirror, still, eyes steady, mouthing names. | Mirror shot, static |
| 7 | 23.0–27.0 | "…nine o'clock isn't an ambush." | Lift doors opening onto a bright office; he walks in and nods to someone, unbothered. | Handheld follow |
| 8 | 27.0–35.0 | "Tonight, say out loud…" | Night: he sits on the bed edge again, same as shot 1, but relaxed, lamp on, lying back. The opening image, resolved. | Same framing as 1 |

**Why it works:** shot 8 answers shot 1 — the same frame, the same man, the
posture changed. The viewer watches the problem get solved without being told.

---

## 2 · `why_i_am_poor` — Seneca · ~33s

**Cast.** Modern: *a man in his late twenties, stubble, hoodie, small dark
bedroom.* Ancient: *Seneca in his sixties, balding, short grey beard, fine
white toga, lamp-lit study with scrolls.*

**Script (for approval)**

> **Hook:** You don't have to fix how you waste time. Just find it.
> Seneca wrote the most quoted line there is about time, and in the same letter
> admitted he was still wasting his.
> **[quote on screen]** *While we are postponing, life speeds by.*
> — Moral Letters 1, trans. Richard M. Gummere
> His words: I can give you the reasons why I am a poor man. He didn't claim to
> have fixed it. He kept the accounts. Tonight, name the one hour you lose every
> day, and where it goes. You're allowed to lose it again tomorrow.

Caveat honoured: absolution first, and the "poor man" confession is kept.

| # | Time | Voice over it | Picture | Camera |
|---|---|---|---|---|
| 1 | 0.0–3.5 | "You don't have to fix…" | Modern man in bed, face lit blue by a phone, thumb scrolling. The clock on the wall behind him reads 1:40. | Static, slight drift |
| 2 | 3.5–7.0 | "Seneca wrote the most quoted line…" | **MATCH CUT.** Seneca at a desk at night, face lit gold by one lamp, unrolling a scroll with the same thumb motion. | Same framing as 1 |
| 3 | 7.0–10.5 | "…still wasting his." | His hand pauses mid-unroll. He looks out of the window at the dark. | Slow push to face |
| 4 | 10.5–16.0 | *(quote on screen)* | Close: an hourglass on the desk, sand falling, lamp behind it. | Locked macro |
| 5 | 16.0–20.0 | "I can give you the reasons why I am a poor man." | Seneca writing figures in a ledger column, a half smile — a man keeping honest books. | Over-shoulder |
| 6 | 20.0–24.0 | "He kept the accounts." | Modern man sitting up, phone face-down, writing one line on a sticky note. | Top-down |
| 7 | 24.0–28.0 | "…name the one hour…" | The sticky note stuck to the phone: a single short line (illegible, no real text). | Macro push |
| 8 | 28.0–33.0 | "You're allowed to lose it again tomorrow." | The room dark, the phone dark, a streetlight moving slowly across the ceiling. He's asleep. | Static |

---

## 3 · `off_the_boat` — Seneca · ~36s

**Cast.** Modern: *a man in his thirties, work shirt, open-plan office.*
Ancient: *Seneca in his sixties, balding, short grey beard, heavy wool cloak.*

Spacing caveat checked: must not air within two weeks of `first_hit` or
`serenus_not_ill`.

**Script (for approval)**

> **Hook:** You've been saying "fine" since March.
> Seneca did the same, until a short boat trip across the bay of Naples made him
> so sick he forced the captain to put him ashore on the rocks.
> **[quote on screen]** *Therefore I laid down the law to my pilot, forcing him
> to make for the shore, willy-nilly.* — Moral Letters 53, trans. Gummere
> Then his point: no one confesses what's wrong with him while he's still
> inside it. Saying it out loud is proof you're surfacing. Tonight, say one
> true sentence to one person who knows you.

| # | Time | Voice over it | Picture | Camera |
|---|---|---|---|---|
| 1 | 0.0–3.5 | "You've been saying 'fine'…" | Modern man at his desk, a colleague's hand on his shoulder, he smiles and nods; the smile drops the second the hand leaves. | Static medium |
| 2 | 3.5–7.0 | "Seneca did the same…" | **MATCH CUT.** Seneca on a small wooden boat, gripping the rail, the same dropped smile, grey water behind. | Same framing as 1 |
| 3 | 7.0–10.5 | "…so sick…" | The boat pitching on a grey swell under a flat sky. | Wide, horizon rolling |
| 4 | 10.5–14.0 | "…put him ashore on the rocks." | Wet black rocks at the waterline, a cloaked figure dropping over the side into the shallows. | Low angle from rocks |
| 5 | 14.0–19.5 | *(quote on screen)* | Seneca hauling himself up the stones, soaked, and standing upright. Holds. | Slow tilt up |
| 6 | 19.5–24.0 | "…no one confesses…" | Modern man alone in a stairwell, phone in hand, thumb over a name. | Static, tight |
| 7 | 24.0–29.0 | "…proof you're surfacing." | He presses call. We don't hear it; we see his shoulders drop as someone answers. | Slow push |
| 8 | 29.0–36.0 | "…one true sentence…" | Evening: two men on a bench, one talking, the other listening, city lights behind. | Wide, static |

---

## 4 · `the_fifth_hour` — Agrippinus, via Epictetus · ~34s

**Cast.** Modern: *a man in his thirties, athletic, t-shirt, apartment
hallway.* Ancient: *Agrippinus, Roman senator in his fifties, lean, close-cut
grey hair, toga.*

Caveat honoured: ends at dinner; nothing about his end; the exile is not the
inspiring part.

**Script (for approval)**

> **Hook:** Waiting for an answer doesn't make it come faster.
> A Roman senator was on trial in his absence. Agrippinus couldn't affect it,
> so when word came, he checked the time: the fifth hour, his time for exercise
> and a cold bath. He went. When he came back, they told him: banishment.
> **[quote on screen]** *Let us go to Aricia then, and dine.*
> — Epictetus, Discourses I.1, trans. George Long
> That isn't nerve. It's a rule made in advance. If you're waiting on a reply
> that won't come till Monday, do the ordinary next thing on your list. Then eat.

| # | Time | Voice over it | Picture | Camera |
|---|---|---|---|---|
| 1 | 0.0–3.5 | "Waiting for an answer…" | A phone face-up on a kitchen table, screen lighting and dimming. A man's hand hovers over it, then withdraws. | Top-down, static |
| 2 | 3.5–7.0 | "A Roman senator was on trial…" | **MATCH CUT.** A messenger's hand setting a sealed wax tablet on a stone table; a senator's hand hovers and withdraws. Same framing. | Same as 1 |
| 3 | 7.0–10.5 | "…he checked the time…" | A sundial in a courtyard, the shadow on the fifth line. | Slow push |
| 4 | 10.5–14.0 | "…exercise and a cold bath." | Agrippinus stepping down into a cold plunge pool in a Roman bath, steam and light shafts. | Low, wide |
| 5 | 14.0–17.5 | "…they told him: banishment." | He's drying off, a servant speaking at the doorway; he just nods. | Medium, static |
| 6 | 17.5–23.0 | *(quote on screen)* | A long table in a warm villa at dusk, bread and oil being laid out. | Slow dolly along table |
| 7 | 23.0–28.0 | "…do the ordinary next thing…" | Modern man lacing running shoes in the hallway, phone left on the table behind him. | Low angle |
| 8 | 28.0–34.0 | "Then eat." | He sets a plate down under a warm lamp and sits. The phone lights up on the counter behind him; he doesn't turn. | Static medium |

---

## 5 · `laughed_out` — Musonius Rufus · ~33s

**Cast.** Modern: *a man in his late twenties, suit jacket, conference room.*
Ancient: *Musonius Rufus, philosopher in his forties, dark beard, plain
philosopher's cloak.*

**Script (for approval)**

> **Hook:** The worst thing you did in front of people isn't the last thing
> about you.
> Rome, 69 AD. The philosopher Musonius Rufus walked in among armed soldiers to
> argue for peace.
> **[quote on screen]** *Many thought it ridiculous, more thought it tiresome.*
> — Tacitus, Histories III.81, trans. Church and Brodribb
> He stopped, and walked away having achieved nothing, in front of everyone.
> Then he went home and kept teaching. One of the young men in his room became
> Epictetus. Tonight, name the humiliation once, in the past tense.

| # | Time | Voice over it | Picture | Camera |
|---|---|---|---|---|
| 1 | 0.0–3.5 | "The worst thing you did…" | A man standing at the front of a meeting room, mid-sentence; around the table, people check their phones. | Wide from the back of the room |
| 2 | 3.5–7.0 | "Rome, 69 AD…" | **MATCH CUT.** Musonius standing in an open field, mid-sentence; around him armed soldiers, some turning away. Same framing. | Same as 1 |
| 3 | 7.0–10.5 | "…armed soldiers…" | Close: spear tips and helmets, a soldier's smirk. | Tight, slight handheld |
| 4 | 10.5–16.0 | *(quote on screen)* | The soldiers' backs, walking off; Musonius alone in the trampled grass. | Wide, static |
| 5 | 16.0–20.0 | "He stopped, and walked away…" | Musonius walking down a dirt track alone at dusk. | Tracking from behind |
| 6 | 20.0–24.0 | "…kept teaching." | A small room with benches, lamplight, a few young students; he's talking again. | Slow push |
| 7 | 24.0–28.0 | "…became Epictetus." | One student at the back, listening hard — the face we linger on. | Tight on the student |
| 8 | 28.0–33.0 | "Tonight, name the humiliation…" | The modern man, evening, alone in the empty meeting room, straightening a chair and switching off the light. Not defeated. | Static wide |

---

## Held back: `know_nothing` — needs your decision

This story's quote is **truncated in a way that changes its meaning.** The bank
has *"If you would improve, submit to be considered without sense and foolish."*
Long's full sentence continues **"…with respect to externals."** Epictetus is
saying: don't care whether people think you're foolish for not valuing the
things they value. The script uses it as "be willing to look stupid while you
learn a skill" — a different claim. Options: (a) retire it, (b) rewrite it
around the real meaning, (c) keep as is. Recommendation: (b), or (a) if time is
short. It is currently third in the airing order.
