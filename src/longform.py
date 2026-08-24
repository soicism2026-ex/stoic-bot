"""
Long-form video assembly: themed readings of public-domain Stoic texts.

WHY THIS EXISTS (data/decisions.md, 2026-08-25): the Shorts path to YouTube
monetisation needs 3,000,000 views in 90 days. The channel does 314/day — 106x
short, with reach falling. The SAME 500-subscriber tier has a second door:
3,000 public watch hours in 12 months. Shorts watch time does not count toward
it; long-form does. At 35% retention a 20-minute video needs ~70 views/day to
clear it, and the channel already does 314/day. This module produces the
format that can actually count.

THE WORDS ARE NEVER GENERATED. Every spoken sentence is read verbatim out of
data/texts/*.txt, which scripts/fetch_source_texts.py downloads from Project
Gutenberg and validates. A model asked to recite Meditations will produce
fluent, plausible, invented Marcus Aurelius; over twenty minutes that would be
a channel-ending amount of fabricated philosophy. Claude is used here for the
title and description only — never for a word that is spoken.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_DIR = ROOT / "data" / "texts"

# Words per minute for a calm, deliberate reading. Used to hit a target
# duration; the real duration comes from the TTS timings at render time.
WORDS_PER_MIN = 130

# Passages shorter than this are headings, numerals or fragments; longer ones
# lose a listener. Both bounds are in words.
MIN_WORDS = 25
MAX_WORDS = 220

# Theme -> words that mark a passage as being about it. Deliberately plain
# substring matching: it is auditable, deterministic, and cannot hallucinate.
THEMES: dict[str, list[str]] = {
    "anger":       ["anger", "angry", "wrath", "rage", "provoked", "offend"],
    "mortality":   ["death", "die", "dying", "mortal", "perish", "grave"],
    "discipline":  ["duty", "labour", "labor", "work", "rise", "toil", "idle"],
    "control":     ["in our power", "not in our power", "control", "will",
                    "opinion", "external"],
    "adversity":   ["endure", "bear", "hardship", "misfortune", "suffer",
                    "adversity"],
    "ego":         ["praise", "fame", "reputation", "glory", "vanity",
                    "esteem"],
    "time":        ["time", "present", "moment", "brief", "short", "hour"],
    "fear":        ["fear", "afraid", "terror", "dread", "anxious"],
}


@dataclass
class Passage:
    text: str
    source: str          # e.g. "meditations"
    index: int           # position in the source, for ordering + citation

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Reading:
    """A complete long-form script, ready for TTS and render."""
    theme: str
    source: str
    author: str
    title: str
    passages: list[Passage] = field(default_factory=list)

    @property
    def body(self) -> str:
        """Exactly what gets spoken from the source, passages separated by a
        pause marker the TTS layer turns into real silence."""
        return "\n\n".join(p.text for p in self.passages)

    @property
    def word_count(self) -> int:
        return sum(p.words for p in self.passages)

    @property
    def est_minutes(self) -> float:
        return self.word_count / WORDS_PER_MIN


def _normalise(raw: str) -> str:
    """Join hard-wrapped lines into paragraphs.

    Gutenberg texts wrap at ~70 columns, so a naive line split would cut
    sentences into fragments and the reading would stutter.
    """
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    # A blank line is a paragraph break; a single newline is just wrapping.
    paras = re.split(r"\n\s*\n", raw)
    return "\n\n".join(" ".join(p.split()) for p in paras if p.strip())


_HEADING = re.compile(
    r"^(the\s+\w+\s+book|book\s+[ivxlc\d]+|chapter\s+[ivxlc\d]+|"
    r"[ivxlc]+\.?|\d+\.?|notes?|appendix|introduction|preface|contents)$",
    re.I)


def load_passages(source: str, text_dir: Path = None) -> list[Passage]:
    """Split a source text into readable passages.

    Returns [] when the file is missing, so a caller can fall back rather than
    crash a scheduled run.
    """
    d = text_dir or TEXT_DIR
    p = d / f"{source}.txt"
    if not p.exists():
        return []
    out: list[Passage] = []
    for i, para in enumerate(_normalise(p.read_text(encoding="utf-8")).split("\n\n")):
        para = para.strip()
        if not para or _HEADING.match(para):
            continue
        # Strip a leading section numeral ("IV. ", "23. ") — it is an artifact
        # of the edition, not something to read aloud.
        para = re.sub(r"^([IVXLC]+|\d{1,3})\.\s+", "", para)
        n = len(para.split())
        if MIN_WORDS <= n <= MAX_WORDS:
            out.append(Passage(text=para, source=source, index=i))
    return out


def score_passage(p: Passage, theme: str) -> int:
    """How strongly a passage speaks to a theme. Plain keyword hits."""
    low = p.text.lower()
    return sum(low.count(w) for w in THEMES.get(theme, []))


def build_reading(source: str, author: str, theme: str,
                  target_minutes: float = 20.0,
                  text_dir: Path = None) -> Reading | None:
    """Select the passages that best fit a theme, up to a target duration.

    Returns None when there is not enough material — a short, padded video is
    worse than no video, and silently shipping one would poison the very
    retention metric this format exists to earn.
    """
    passages = load_passages(source, text_dir)
    if not passages:
        return None
    scored = [(score_passage(p, theme), -p.words, p) for p in passages]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]))

    budget = int(target_minutes * WORDS_PER_MIN)
    chosen: list[Passage] = []
    used = 0
    for _, _, p in scored:
        if used + p.words > budget:
            continue
        chosen.append(p)
        used += p.words
        if used >= budget * 0.92:
            break
    if used < budget * 0.5:      # not enough on-theme material
        return None

    # Read in the order the author wrote them, not in score order — a reading
    # that jumps around sounds like a shuffle, which is what it would be.
    chosen.sort(key=lambda p: p.index)
    return Reading(theme=theme, source=source, author=author,
                   title="", passages=chosen)


def chapters(reading: Reading, per_chapter: int = 4) -> list[tuple[int, str]]:
    """(passage_index_in_reading, label) marks for a YouTube description.

    Real timestamps are filled in after TTS, when durations are known —
    guessing them would put every chapter mark in the wrong place.
    """
    out = []
    for i in range(0, len(reading.passages), per_chapter):
        out.append((i, f"Part {i // per_chapter + 1}"))
    return out
