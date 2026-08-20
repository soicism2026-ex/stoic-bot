# assets/voice/ — the reference recording

Drop a short recording of **your own voice** here as `reference.wav` and every
post is spoken in it, for free, forever. Chatterbox clones it locally on the CI
runner — no API, no key, no per-post cost.

## Why your voice

"Real people's voices from real inspiring people" is the right instinct — a
human who actually believes the words beats any TTS. But cloning a public
figure's voice uses someone else's likeness: it risks the channel, it cannot be
monetised, and a synthetic voice putting words in a real person's mouth is a
different thing from being inspired by them.

Your own voice gets the whole benefit with none of that. It is also the one
thing a competitor cannot copy.

## Recording it

- **30–60 seconds** is plenty. Longer is not better.
- Quiet room, no music, no background noise. Phone voice-memo is fine.
- Speak the way you want the channel to sound: **calm, unhurried, certain**.
  Chatterbox copies your delivery as well as your timbre — read it like you
  mean it, not like you are testing a microphone.
- Read something real, not "testing one two three". A paragraph of Seneca is
  ideal since that is what it will be saying.
- Save as `reference.wav` (or mp3 — point `CHATTERBOX_VOICE_FILE` at it).

## Switching it on

1. Commit the file here.
2. Set repo variable `CHATTERBOX_LOCAL=1`
   (Settings → Secrets and variables → Actions → Variables).

That is it. If the file is missing or too small the pipeline ignores it and
falls back to edge-tts, so a bad recording degrades the voice rather than
breaking a post.
