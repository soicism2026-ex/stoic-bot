"""
Playlist-style shuffle, shared by everything that rotates through a list.

Owner, 2026-10-05, on the music: "shuffle them". A shuffle is not a fixed
rotation and not independent random picks:
  * every item plays once per cycle,
  * the order is different each cycle,
  * the same item never plays twice in a row, not even across a cycle
    boundary.
The cycle is rebuilt from history (posts.csv), so it survives restarts, and
an item added mid-cycle simply joins the ones still to play.
"""
from __future__ import annotations

import random


def pick(pool_ids, played, seed: str = "") -> str | None:
    """Next id from `pool_ids`, given `played` (oldest first). Ids in the
    history that are no longer in the pool are ignored. `seed` (the date)
    makes a retried run pick the same item."""
    pool = sorted(set(pool_ids))
    if not pool:
        return None
    ids = set(pool)
    played = [p for p in played if p in ids]
    cycle: list[str] = []
    for p in played:
        if len(cycle) >= len(pool) or p in cycle:
            cycle = []
        cycle.append(p)
    left = [i for i in pool if i not in cycle] if len(cycle) < len(pool) else []
    if not left:   # cycle complete: a new one, but never the last item first
        left = [i for i in pool if not played or i != played[-1]] or pool
    return random.Random(f"{seed}|{len(played)}").choice(left)
