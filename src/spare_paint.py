"""The spare-painting rule: when may anything that is NOT a Short paint?

Cloudflare Workers AI's free allowance is 10,000 neurons a day and resets at
00:00 UTC. After midnight that allowance belongs to THAT day's Shorts: their
rehearsals (after the ~00:00, 07:00 and 19:00 posts), Longinus's re-rehearsals
(04:41 / 08:41), pushed scene changes. Live posts reuse the rehearsal's cached
stills. On 2026-11-24 a wallpaper pack painted at 02:44 UTC and a design-lab run
at 03:02 used the day up, and the 19:00 Short aired unpainted. So wallpapers,
the long video's stills and the design lab paint only on what is LEFT after the
day's last rehearsal:

  1. the UTC hour is 20-23 (never 00-19);
  2. the next Short's rehearsal (the `up-next` release) is for a day after
     today's UTC date, i.e. the 19:00 post has aired and tomorrow's first Short
     is rehearsed (that rehearsal is the day's last big spend);
  3. every shot in that rehearsal is painted (when the Shorts paint at all:
     REEL_EDIT_LOOK=painted and the record has shots).

Anything unreadable refuses. `python3 scripts/spare_paint.py check [--force]`
prints the reason and exits 0 (allowed or forced) or 3 (refused).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY") or "soicism2026-ex/stoic-bot"
UP_NEXT_URL = f"https://github.com/{REPO}/releases/download/up-next/up-next.json"
FIRST_HOUR_UTC = 20
LAST_HOUR_UTC = 23
EXIT_REFUSED = 3


def fetch_up_next(url: str = UP_NEXT_URL, timeout: float = 20.0) -> dict | None:
    """The next Short's rehearsal record, or None when it cannot be fetched or read."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "stoic-bot-spare-paint"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (a fixed https URL)
            data = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _painted_look() -> bool:
    return os.environ.get("REEL_EDIT_LOOK", "").strip().lower() == "painted"


def spare_ok(now_utc: dt.datetime, up_next: dict | None, today: dt.date | None = None) -> tuple[bool, str]:
    """(allowed, plain-English reason). Pure: all inputs are arguments (the
    environment's REEL_EDIT_LOOK is the only thing read)."""
    now = now_utc.astimezone(dt.timezone.utc) if now_utc.tzinfo else now_utc
    today = today or now.date()
    hour = now.hour
    if not FIRST_HOUR_UTC <= hour <= LAST_HOUR_UTC:
        return False, (f"it is {now:%H:%M} UTC: after midnight UTC Cloudflare's free painting belongs to "
                       f"that day's Shorts; spare painting runs only {FIRST_HOUR_UTC}:00-23:59 UTC")
    if not isinstance(up_next, dict):
        return False, "the next Short's rehearsal could not be read, so what is left of today's allowance is unknown"
    air = str(up_next.get("airDay") or "")
    try:
        air_day = dt.date.fromisoformat(air)
    except ValueError:
        return False, f"the next Short's rehearsal has no readable air day ({air or 'none'})"
    if air_day <= today:
        return False, (f"the next Short is rehearsed for {air_day}, not for a day after {today}: today's "
                       "Shorts have not all aired and tomorrow's first one is not rehearsed yet")
    shots = up_next.get("shots") or []
    if _painted_look() and shots:
        bad = [s for s in shots if not (isinstance(s, dict) and s.get("painted") is True)]
        if bad:
            return False, (f"{len(bad)} of {len(shots)} shots in tomorrow's rehearsal ({air_day}) are not "
                           "painted yet: they need what is left of the allowance")
        return True, (f"{now:%H:%M} UTC, tomorrow's first Short ({air_day}) is rehearsed with all "
                      f"{len(shots)} shots painted: the rest of today's allowance is spare")
    return True, (f"{now:%H:%M} UTC, tomorrow's first Short ({air_day}) is rehearsed and the Shorts "
                  "need no more painting: the rest of today's allowance is spare")


def check(now_utc: dt.datetime | None = None, force: bool = False, fetch=None) -> tuple[bool, str]:
    """The rule with the real clock and the real release. `force` always allows.
    The release is not even fetched outside hours 20-23."""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if force:
        return True, "forced: painting now eats into the Shorts' free allowance"
    if not FIRST_HOUR_UTC <= now.hour <= LAST_HOUR_UTC:
        return spare_ok(now, None)
    return spare_ok(now, (fetch or fetch_up_next)())
