# Improvements Log

Tracks every change made by the `auto-improve.yml` workflow (Claude Code).
Claude appends here after each improvement and will never repeat or revert
a change listed below.

Format per entry:
- **Date** — what changed, which file(s), and why (analytics or QA signal).

---

- **2026-06-15** — `src/content.py` + `src/render.py` + `scripts/daily_post.py`: Voiceover tightened from 18–35 s to 20–27 s (~50–68 words) with explicit "cut to the hard truth, no padding" directive. Added `callout_words` field to content JSON — Claude picks 2–4 concrete nouns from the voiceover (e.g. "house", "anger") that flash large (112 px, centered) on screen exactly when spoken, driven by ElevenLabs word-level timings. This keeps the viewer's eye moving on list-style content and matches the visual pacing of high-retention Shorts.

- **2026-06-15** — `src/content.py` + `src/publish.py` + `scripts/daily_post.py` + `scripts/sync_video_titles.py` (new): Day counter fixed to use calendar offset from channel start (first post date) instead of `len(rows)+1` — so day numbers never shift when videos are unlisted or pruned, and duplicate posts on the same day no longer inflate the counter. Added `scripts/sync_video_titles.py` to repair existing titles on demand or after pruning (reads posts.csv, computes correct Day N, calls `videos.update` only where wrong; supports `--dry-run`). Removed all "pin in YouTube Studio" messaging (feature requires channel identity verification). Sharpened hook prompt: tighter 3–5 word constraint, second-person accusation register required, explicit GOOD/WRONG examples to steer Claude away from soft/generic openers.

- **2026-06-15** — `src/promo.py` (new) + `scripts/daily_post.py` + `.github/workflows/daily-short.yml` + `README.md`: Product promo injection. Added configurable CTA block appended to every Short description and optional promo comment posted after upload. All copy (product name, pitch, URL, 3–5 rotating CTA variations) lives in workflow env vars — no code changes needed to update. Master toggle `PROMO_ENABLED=0` suppresses all promo behaviour with zero side-effects on existing upload logic. Promo comment uses existing `youtube.force-ssl` scope; no new API permissions required. 15 unit tests added in `tests/test_promo.py`.

- **2026-06-14** — `src/content.py` + `scripts/daily_post.py`: Double-post prevention and roster tightening. After 18 videos across 14 days: (1) The workflow fired 2–4× per day on many days (manual dispatch + scheduled cron), flooding the channel and burning through author rotation — fixed by adding a one-post-per-day guard in `daily_post.py` that exits cleanly if `posts.csv` already has a today entry. (2) Musonius Rufus (1,050v peak) and Zeno of Citium (938v) consistently match the original Big 3 — promoted to the top pool, now "Big 5". (3) Cleanthes (224v final, 4 days old), Hierocles, and Cato the Younger underperformed and were removed from SOURCE_HINTS. (4) Rotation changed from "3 of 5 days Big 3 / 2 of 5 full roster" → "4 of 5 days Big 5 / every 5th day Chrysippus (~640v)". Expected average views/post rises from ~700 to ~900+.

- **2026-06-13** — `src/content.py`: Analytics-driven author weighting. After 8 days
  of data (13 videos, 8,189 views total), Marcus Aurelius / Seneca / Epictetus
  consistently reach 900-1050 views while lesser-known Stoics (Cleanthes, Chrysippus)
  average 200-600 views at lower engagement rates. Changed `_pick_rotation()` to pick
  from the Big 3 on 3 of every 5 days (day_index % 5 < 3) and from the full roster
  on the other 2 days. Also strengthened quote deduplication: the avoid block now
  explicitly calls out quotes by today's required author so Claude cannot re-use the
  same Seneca/Epictetus passages it has strong priors toward (same Seneca "short time"
  quote appeared 4 times in 5 days). Improved pinned comment guidance to ask specific,
  personal, slightly uncomfortable questions rather than generic engagement prompts —
  current videos average 0-1 comments despite 900+ views. Removed the most obscure
  Stoics (Hecato, Posidonius, Panaetius, Aristo, Diogenes of Babylon) whose surviving
  fragments are sparse enough that the model risks hallucinating quotes.
