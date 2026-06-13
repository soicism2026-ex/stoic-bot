# Improvements Log

Tracks every change made by the `auto-improve.yml` workflow (Claude Code).
Claude appends here after each improvement and will never repeat or revert
a change listed below.

Format per entry:
- **Date** — what changed, which file(s), and why (analytics or QA signal).

---

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
