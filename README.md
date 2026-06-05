# Stoic Shorts Bot

Fully automated faceless Stoicism YouTube Shorts pipeline. Runs on GitHub
Actions (no server). Posts daily, logs everything to CSV in the repo. Free to
run except for AI/voice usage (a few dollars a month total).

```
Claude API (script) -> ElevenLabs (voice) -> ffmpeg (render) -> YouTube Data API (upload) -> CSV log
```

## Why YouTube
The YouTube Data API is free (10,000 quota units/day). A daily upload costs
~100 units, analytics reads cost ~1 each, so you stay free with huge headroom.
No paid scheduler, no app-review gate for posting to your own channel.

## One-time setup

### 1. Google Cloud + YouTube auth (the only fiddly part, ~15 min, done once)
1. Create the brand's YouTube channel (logged in as soicism2026@gmail.com).
2. console.cloud.google.com -> create a project.
3. APIs & Services -> Library -> enable **YouTube Data API v3**.
4. OAuth consent screen -> External -> fill basics -> add soicism2026@gmail.com
   as a **Test user**.
5. Credentials -> Create credentials -> OAuth client ID -> **Desktop app** ->
   download JSON, save as `client_secret.json` in the project folder.
6. Locally:  pip install google-auth-oauthlib google-api-python-client
   then:      python src/auth_setup.py
   A browser opens; log in as the brand, approve. It prints CLIENT_ID,
   CLIENT_SECRET, REFRESH_TOKEN. Keep these for step 4. (Never commit them.)

### 2. Other keys
- **Anthropic**: console.anthropic.com -> API key (you rotated the exposed one).
- **ElevenLabs**: elevenlabs.io -> API key (you rotated the exposed one) +
  optional Voice ID.

### 3. Push repo to GitHub
Upload these files to your repo (already created at github.com/soicism2026-ex/stoic-bot).

### 4. Add GitHub secrets
Repo -> Settings -> Secrets and variables -> Actions:
  ANTHROPIC_API_KEY
  ELEVENLABS_API_KEY
  ELEVENLABS_VOICE_ID        (optional)
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN

### 5. Background clips (one-time)
Drop 5-10 vertical (9:16) royalty-free MP4s into assets/backgrounds/ from
pexels.com/videos. Refresh every few months. This is your only recurring chore.

### 6. Test
Actions tab -> daily-short -> Run workflow. Watch the log. A new Short should
appear on the channel within a minute or two.

## Daily operation
Nothing. daily-short posts each day; pull-analytics records numbers. History
lives in data/posts.csv and data/analytics.csv, committed automatically.

## Realistic expectations
Reliably produces and posts; does not guarantee views. Faceless content is
saturated. Treat the first 2-3 months as data collection: watch analytics.csv,
see which themes land, feed winners back into the SYSTEM prompt in
src/content.py. Improving the bot = editing one prompt.

## If something breaks
- Upload fails -> usually an expired/invalid YouTube refresh token. Re-run
  auth_setup.py and update the secret.
- "quotaExceeded" -> you ran the workflow too many times in a day; resets at
  midnight Pacific.
- Voice too pricey -> rewrite synthesize_voice() in src/tts.py for OpenAI TTS.

## Cost
~$5/mo ElevenLabs + a few cents/day Anthropic. YouTube API: free.
