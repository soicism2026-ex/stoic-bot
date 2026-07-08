"""
Experiment agent — structured A/B testing for the parts of a Short that drive
retention: how it OPENS (intro sound) and how it LOOKS (colour world).

Every post is assigned one combo from the grid below (round-robin so samples
accumulate evenly at 4 posts/day). The combo name is logged to posts.csv and
scripts/channel_report.py ranks combos by average views, so after a few days
the data — not taste — says which opening and look stick with viewers.

Intro variants (the first 1–2 seconds decide the swipe):
  cold_open — NO intro sound at all. The voice hits first, alone, loud.
              The pattern most big Stoic channels use.
  punch     — short bass impact + snap under the first word (hype energy).
  swell     — cinematic orchestral swell into the first line (drama energy).

Grade variants (colour world):
  warm_gold — candlelit bronze; warm highs that flatter the gold type.
  obsidian  — cold marble/steel; desaturated museum register.

To retire a loser or add a challenger, edit the two lists — everything else
(assignment, logging, reporting) adapts automatically.
"""

INTRO_VARIANTS = [
    # (name, env overrides)
    ("cold_open", {"REEL_HOOK_SOUND": "0"}),
    ("punch",     {"REEL_HOOK_SOUND": "1", "REEL_HOOK_SOUND_PRESET": "bass_impact"}),
    ("swell",     {"REEL_HOOK_SOUND": "1", "REEL_HOOK_SOUND_PRESET": "cinematic"}),
]

GRADE_VARIANTS = [
    ("warm_gold", {"REEL_GRADE_VARIANT": "warm_gold"}),
    ("obsidian",  {"REEL_GRADE_VARIANT": "obsidian"}),
]


def grid() -> list[tuple[str, dict]]:
    """Full combo grid: intro x grade -> (name, merged env)."""
    combos = []
    for iname, ienv in INTRO_VARIANTS:
        for gname, genv in GRADE_VARIANTS:
            combos.append((f"{iname}+{gname}", {**ienv, **genv}))
    return combos


def pick_experiment(rows: list[dict]) -> tuple[str, dict]:
    """Assign this post's combo, round-robin over the grid by post count.

    Deterministic (no randomness) so a QA retry of the same post renders the
    same variant, and samples spread evenly across combos.
    """
    combos = grid()
    name, env = combos[len(rows) % len(combos)]
    return name, dict(env)
