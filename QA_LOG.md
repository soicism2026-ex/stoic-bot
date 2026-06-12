# QA Log

Automated render-quality results appended by `scripts/daily_post.py`.
Each entry records the date, attempt number, severity, and issues found.
Entries with `uploaded: true` were posted despite issues (minor imperfections
accepted over a missed day). Entries with `uploaded: false` triggered a
backup-bank upload instead.

The `auto-improve.yml` workflow reads this file daily and implements fixes
for any recurring defects.

---
