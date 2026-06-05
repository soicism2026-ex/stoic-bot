# Stoic Reels Bot

Fully automated faceless Stoicism Instagram Reels pipeline. Runs on GitHub
Actions (no server to babysit). Posts daily, logs everything to CSV in the repo.

```
Claude API (script) -> ElevenLabs (voice) -> ffmpeg (render) -> Metricool (publish) -> CSV log
```

## One-time setup (~30-45 min, then it's hands-off)

### 1. Accounts you need
- **Anthropic API key** - console.anthropic.com (pay-as-you-go, pennies/day)
- **ElevenLabs API key** - elevenlabs.io (~$5/mo Starter)
- **Metricool Advanced plan** - metricool.com (~$18/mo; required for API access)
- Instagram **Business/Creator** account connected inside Metricool
- A **GitHub** account (free)

### 2. Get this on GitHub
Create a new repo and push these files into it. The two workflows under
`.github/workflows/` schedule themselves automatically once pushed.

### 3. Add background clips (one-time)
Download 5-10 slow, moody, vertical (9:16) royalty-free clips from
**Pexels Videos** (free, no attribution). Put them in `assets/backgrounds/`.
The bot rotates through them by date. Refresh the folder every few months so
your feed doesn't look repetitive. This is essentially your only recurring task.

### 4. Add secrets
Repo -> Settings -> Secrets and variables -> Actions -> New repository secret:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic console |
| `ELEVENLABS_API_KEY` | ElevenLabs profile |
| `ELEVENLABS_VOICE_ID` | (optional) a voice id; defaults to "Adam" |
| `METRICOOL_USER_TOKEN` | Metricool -> API settings |
| `METRICOOL_USER_ID` | Metricool API settings |
| `METRICOOL_BLOG_ID` | the brand/profile id of your IG connection |

### 5. Test it
Actions tab -> **daily-reel** -> Run workflow. Watch the log. It should
generate, render, and schedule one Reel into Metricool. Check Metricool's
planner to see it queued.

## Daily operation
Nothing. The `daily-reel` workflow posts every morning; `pull-analytics`
records numbers each day. Your history lives in `data/posts.csv` and
`data/analytics.csv`, committed automatically.

## Realistic expectations
This reliably *produces and posts*. It does not guarantee views. Faceless
content is saturated. Treat the first 2-3 months as data collection: watch
`analytics.csv`, see which themes/hooks land, and feed winners back into the
`SYSTEM` prompt in `src/content.py`. The system is built so improving it means
editing one prompt, not rebuilding.

## Where things break (and the one file to fix)
- **Publishing fails** -> Metricool changed their API. Fix `src/publish.py` only.
- **Analytics empty** -> same, fix `src/analytics.py` only.
- **Voice too expensive** -> rewrite `synthesize_voice()` in `src/tts.py` to use
  OpenAI TTS (~$1-2/mo). Nothing else changes.

## Cost
~$23/mo (ElevenLabs $5 + Metricool $18) + cents of API usage. Swap to OpenAI
TTS to drop under $20.
