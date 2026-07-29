---
name: channel-report
description: Answer "how's the bot doing" / "how are we doing" / any request for channel status, analytics, subscriber or view performance. Produces an age-corrected, honest performance read with format/voice/experiment leaderboards and a clear recommendation. Use whenever the owner asks about numbers, growth, or how the channel is performing.
---

# Channel status report

The owner asks this constantly. The job is an **honest** read, not a cheerful one.
Raw view totals mislead — younger videos always look worse — so age-correct
before drawing any conclusion.

## Always do this first

```bash
cd /home/user/stoic-bot
git fetch origin main -q && git rebase origin/main -q   # never analyse stale data
```

## 1. Goal + trend (lead with this)

```bash
python3 - <<'PY'
import csv
seen={}
for r in csv.DictReader(open('data/channel_stats.csv')):
    seen[r['pulled_on']]=(int(r['subscribers'] or 0), int(r['total_views'] or 0))
days=sorted(seen)
for i,d in enumerate(days[-8:]):
    j=days.index(d)
    ds=seen[d][0]-seen[days[j-1]][0] if j else 0
    dv=seen[d][1]-seen[days[j-1]][1] if j else 0
    print(f"{d}: {seen[d][0]:4} subs ({ds:+d}) | {seen[d][1]:6} total | day gain +{dv}")
PY
```

**Daily view GAIN is the health metric**, not the running total — the total always
rises. A falling daily gain means the channel is starving even while the total climbs.

Goal: 500 subs + 3M valid public Shorts views / 90 days (YouTube Partner Program).

## 2. Age-corrected performance (never compare raw views across dates)

Compare videos **at the same age**. A post from today with 40 views is not
underperforming a month-old post with 300.

```bash
python3 - <<'PY'
import csv, datetime
from collections import defaultdict
snaps=defaultdict(dict); pub={}
for r in csv.DictReader(open('data/analytics.csv')):
    v=r.get('video_id','').strip()
    if not v: continue
    p=r.get('published_at','')[:10]
    if p: pub[v]=p
    d=r.get('pulled_on','')
    if d: snaps[v][d]=max(snaps[v].get(d,0), int(r.get('views') or 0))
def at_age(v, age=1):
    if v not in pub: return None
    p=datetime.date.fromisoformat(pub[v])
    for d,n in sorted(snaps[v].items()):
        if (datetime.date.fromisoformat(d)-p).days >= age: return n
    return None
rows=[r for r in csv.reader(open('data/posts.csv'))][1:]
by_day=defaultdict(list)
for r in rows:
    v=at_age(r[6]) if len(r)>6 else None
    if v is not None: by_day[r[0]].append(v)
print("avg views at ~1 day old (fair comparison):")
for d in sorted(by_day)[-10:]:
    print(f"  {d}: {sum(by_day[d])/len(by_day[d]):6.0f}  (n={len(by_day[d])})")
PY
```

## 3. Leaderboards — format, voice, experiment, retention

`posts.csv` columns (positional, trailing fields not in header):
`0 date, 1 theme, 2 author, 3 quote, 4 caption, 5 url, 6 video_id, 7 voice, 8 music, 9 hook, 10 experiment, 11 format`

Rank formats/voices/experiments by **median** (not mean — one viral outlier skews
the mean). Join `data/retention.csv` when present for avg-view-% — the signal the
algorithm actually ranks on. Cap retention at 150% when averaging: Shorts loops
inflate short videos past 100%.

Also run the built-in report for the packaged view:
```bash
python3 scripts/channel_report.py
```

## 4. Report honestly

- Lead with the answer: growing, flat, or falling — say it plainly in the first line.
- Small samples (n<5) are **directional only** — say so rather than declaring a winner.
- If something is broken, that outranks any metric. Check `pipeline-doctor` if the
  posts-per-day count looks short.
- Name the single highest-impact next action, and give a recommendation rather than
  a menu of options.
- Never inflate. The owner acts on this — a falsely rosy read costs them real days.
