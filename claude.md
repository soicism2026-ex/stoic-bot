Create a file called CLAUDE.md in the repo root with this content:

# Stoic Shorts Bot
Faceless Stoicism YouTube Shorts generator. Runs daily on GitHub Actions (.github/workflows/daily-short.yml); analytics via pull-analytics.yml.

## Pipeline (src/)
- main.py: orchestrator
- content.py: Claude API picks quote/script/caption/hashtags
- tts.py: ElevenLabs voiceover
- render.py: ffmpeg builds 1080x1920 MP4 (text over background, voiceover muxed)
- publish.py: uploads to YouTube Data API as a Short
- analytics.py: pulls view/like/comment stats to data/analytics.csv
- logbook.py: appends each post to data/posts.csv

## Key facts
- Secrets live in GitHub Actions, NOT in the repo. Never commit keys.
- Backgrounds currently static MP4s in assets/backgrounds/ (only 7, they repeat).
- ffmpeg and fonts-dejavu are installed by the workflow on the runner.
- Quotes must stay genuine public-domain Stoic text (Marcus Aurelius, Seneca, Epictetus).
