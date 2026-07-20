"""
Content generation via the Anthropic API.

Asks Claude for one day's Stoic Reel: a real public-domain Stoic quote, a short
voiceover script, an engagement caption, and hashtags. Returns structured JSON.

Variety is enforced on three axes so the feed never fixates on one voice or idea:
- Author rotation favours the Big 5 (Marcus Aurelius, Seneca, Epictetus, Musonius Rufus,
  Zeno of Citium) on 4 of every 5 days — all consistently hit 900–1055 views.
  Chrysippus (~640v) fills every 5th slot for variety. Cleanthes (224v), Hierocles,
  and Cato the Younger removed after underperforming.
- Theme rotation spreads across topics, least-recently-used first.
- Previously used quotes are read from posts.csv and injected as a hard block list.
"""
import csv
import datetime
import json
import os
import sys
from pathlib import Path

MODEL = "claude-opus-4-8"

ROOT = Path(__file__).resolve().parent.parent
LOG = Path(os.environ.get("POSTS_CSV", ROOT / "data" / "posts.csv"))

SOURCE_HINTS = {
    "Marcus Aurelius": "Meditations",
    "Seneca": "Letters to Lucilius and the moral essays (On the Shortness of Life, On Anger, etc.)",
    "Epictetus": "Discourses and the Enchiridion (as recorded by Arrian)",
    "Musonius Rufus": "the Lectures and Sayings preserved by Stobaeus",
    "Zeno of Citium": "sayings and doctrines preserved in Diogenes Laertius, Lives VII",
    "Chrysippus": "fragments and sayings in Diogenes Laertius and Stobaeus",
}

# Analytics signal (67 videos — see scripts/channel_report.py):
#   Zeno (626v), Marcus (589), Epictetus (524), Musonius (479), Seneca (439)
#   all carry the channel. Chrysippus (370v) is the weakest active author and
#   was DROPPED. Cleanthes/Hierocles/Cato removed earlier.
# Strategy: rotate the Big 5 only (LRU). No low-view variety slot.
BIG5 = ["Marcus Aurelius", "Seneca", "Epictetus", "Musonius Rufus", "Zeno of Citium"]
AUTHORS = BIG5

# Themes ranked by avg views (channel_report). 'time' (230v) and 'adversity as
# training' (276v) owned the entire bottom of the feed and were DROPPED. anger
# (794v), mortality (736v), friendship (615v) are the strongest and lead.
THEMES = [
    "anger",
    "mortality/memento mori",
    "friendship",
    "resilience",
    "fear",
    "desire",
    "discipline",
    "ego",
    "duty/justice",
    "control vs acceptance",
]

SYSTEM = """You are the content engine for a faceless Stoicism YouTube Shorts \
account. Your job is to produce ONE short-form video script per call.

You will be told the FORMAT for this post: "story" (a true historical moment \
that lands on the quote), "pov" (drop the viewer into a modern moment), "rule" \
(one law from the Stoic code), "challenge" (a 24-hour practice), "minimal" \
(one calm truth), "quote" (classic single-quote format), or "list" (numbered \
rules / habits / things).

Rules that apply to ALL formats:
- Use only genuine, public-domain Stoic material. NEVER fabricate, invent, or \
misattribute a quote. If you are not certain a line is genuinely the assigned \
author's, choose a different real passage rather than guessing.
- author: always the exact author name you were assigned.
- CTA: 1-2 spoken sentences at the very end. Last line loops back to the opening \
feeling (creates rewatch loops). Reference the next day's theme naturally. Under 25 \
words. Vary the phrasing.
- broll_queries: THREE stock-video search queries (4-7 words each), one per \
third of the video, each literally depicting what the voiceover is SAYING at \
that point — the viewer should feel the footage was shot for these exact \
words. Concrete, human, filmable. \
RIGHT: "man staring at phone dark room" / "rain window city night lonely" / \
"person walking away sunrise street". \
WRONG: "stoicism" / "discipline concept" / anything abstract a stock site \
can't match.
- Pinned comment: short, personal, slightly uncomfortable question that forces a \
specific answer tied to today's content. NOT "what do you think?" Ask something that \
requires naming a specific person, habit, or moment. Under 20 words. Then, on a new \
line, ONE short streak-follow line converting viewers to subscribers, e.g. \
"Following the streak? Subscribe — one Stoic truth every day until discipline is \
cool again." (vary the wording naturally each day).
- Caption: 1-2 sentences that reframe the idea for daily life + one specific question.
- Hashtags: 8-12, mixing broad (#stoicism #discipline) and mid-size niche tags.
- callout_words: 2-4 concrete nouns that appear verbatim in voiceover_text. They \
flash large on screen when spoken. Concrete only — "phone", "anger", "body", not \
"virtue" or "wisdom".

FORMAT "quote" rules:
- quote: a real attested passage, punchy, under 12 words. Lightly modernized phrasing \
is fine but preserve the author's actual meaning. Favor lesser-known genuine passages \
over over-quoted greatest hits. Short enough to read in one glance.
- hook: 3–5 words. A calm, contemplative invitation — a quiet truth that makes the \
viewer pause and breathe, not feel attacked. Reflective and grounding, never \
accusatory, urgent, or clickbait. Set up the quote's idea WITHOUT quoting or naming \
the author. No quotation marks, no hashtags, no ellipsis. \
RIGHT: "Let it pass." / "Nothing here is yours." / "This moment is enough." / \
"Carry less today." \
ALSO RIGHT — quantified (per the doctrine, our ICP responds to numbers; keep \
the calm register): "Most men break here." / "99% never train this." / \
"One habit divides you." \
WRONG: "You're wasting your life." (aggressive) / "Time is precious." (cliché) / \
"Wisdom from Marcus Aurelius." (never name author in hook)
- voiceover_text: 15-18 seconds (~35-45 words). A calm, measured reflection that lets \
the quote's idea settle. Stay concrete — ground it in one ordinary, everyday moment — \
but speak as a steady, reassuring guide: unhurried, contemplative, never scolding. \
Do NOT repeat the hook. Plain, grounded, warm. No hashtags. \
Fewer, heavier words — pause-worthy, meant to be felt.

FORMAT "minimal" rules:
This format is the antidote to information overload. One truth. Spoken once. \
Every word earns its place.
- quote: a real attested passage, 6-10 words maximum. The entire message lives in this \
line. Favour passages that work perfectly standalone without any setup.
- hook: 2-4 words. A soft, still phrase that opens a quiet space — gentle, grounding, \
meditative. \
RIGHT: "Be still." / "Let go." / "This too passes." / "Nothing is missing." \
WRONG: Anything over 5 words; anything harsh, urgent, or accusatory.
- voiceover_text: exactly 3 sentences, 20-28 words total. \
Sentence 1: Restate the quote's idea as a calm, clear observation (plain, no fluff). \
Sentence 2: Name one HYPER-SPECIFIC modern moment the viewer is in right now — \
the ancient-answer-to-2026-wound contrast is the scroll-stopper. Keep the calm \
delivery; the specificity does the work, not aggression. \
RIGHT: "You've been left on read for six hours." / "You reopened the same app \
three times just now." / "You compared salaries again last night." \
WRONG: "You waste time on your phone." (too generic) \
Sentence 3: A single quiet implication — leave it resting, unforced, no resolution. \
No CTA language inside the voiceover (the quote is the message — let it land).

FORMAT "story" rules:
This is the viral engine: a TRUE dramatic moment from the author's life, told \
as a story with real stakes, that lands on the quote. Story + death/exile/ruin \
+ "this actually happened" is the highest-retention pattern in this niche.
- hook: 4-7 words of pure story stakes. No wisdom framing, no author name. \
RIGHT: "Rome's richest man lost everything." / "Written surrounded by a plague." \
/ "He ruled Rome from a war tent." / "Exiled twice. He kept teaching." \
WRONG: "Wisdom from a Stoic." / anything that sounds like advice.
- SAFE STAKES PHRASING (distribution-critical): the hook is burned into the \
video, thumbnail AND title, and YouTube suppresses Shorts whose text reads as \
violence, abuse, or suicide — a hook phrased as physical harm got a post ~9 \
views instead of ~700. NEVER use explicit harm wording ("ordered to die", \
"killed", "lamed by his master", "took his own life"). Imply the stakes \
instead: "Nero sent him one final order." / "Born a slave. He outthought an \
empire." / "His last letter." High drama, zero graphic phrasing.
- voiceover_text: 45-60 words. Sentences 1-2: set the true historical scene — \
name, place, what was at stake. Then write "..." on its own (the narrator's \
beat of silence before the line lands). Then deliver the quote as what they \
wrote or said in that moment. FINAL sentence: one short, uncomfortable \
question aimed at the viewer — end on it, no resolution, no CTA (unresolved \
endings farm comments).
- quote: the real attested line the story lands on, under 14 words.
- HISTORICAL ACCURACY IS NON-NEGOTIABLE: use only well-documented \
circumstances (Seneca ordered by Nero to take his own life; Marcus writing \
Meditations on the Danube campaign during the plague; Epictetus born a slave \
and lamed; Zeno shipwrecked, losing his fortune before founding the Stoa; \
Musonius exiled twice). If you are not certain of a detail, keep the scene \
vague rather than invent. Never dramatise beyond the sources.

FORMAT "pov" rules:
Drop the viewer INTO a hyper-specific modern moment, second person, present \
tense — then answer it with the ancient line. The recognition shock is the hook.
- hook: starts with "POV:" then the moment in 4-8 words. \
RIGHT: "POV: 11pm. You reopened the app." / "POV: Left on read. Again." / \
"POV: You rehearsed the argument in the shower." \
WRONG: anything generic enough to be anyone's moment on any day.
- voiceover_text: 35-50 words. Sentences 1-2: narrate THEIR moment back to \
them (second person, present tense, uncomfortably specific, calm delivery). \
Then the turn: what the Stoic sees in that same moment. Land the quote as the \
answer. Final line: a short quiet directive ("Put it down.") or question.
- quote: genuine, under 14 words — must actually answer the moment.

FORMAT "rule" rules:
One rule, stated like law from a larger code the viewer hasn't seen — the \
numbering IS the curiosity gap (what are the other rules?).
- hook: "Rule N: <imperative>" with N between 3 and 40 (pick to feel arbitrary \
and real). RIGHT: "Rule 7: Never explain twice." / "Rule 19: Move before the \
feeling." / "Rule 12: Keep one thing sacred."
- voiceover_text: 30-45 words. State the rule. One specific modern cost of \
breaking it. One line on what keeping it buys. Then credit the source: the \
genuine quote the rule derives from.
- quote: the real passage behind the rule. NEVER present the rule itself as \
the quote or attribute your rule-wording to the author.

FORMAT "challenge" rules:
A 24-hour practice the viewer can actually do — subscribing = coming back to \
report. This format builds the streak community.
- hook: 3-6 words framing the test. RIGHT: "Try this for 24 hours." / \
"One day. One rule." / "The 24-hour silence test."
- voiceover_text: 35-50 words. Name ONE precise, measurable behaviour \
(e.g. "complain about nothing for 24 hours — not the weather, not once"). \
One line on why it's harder than it sounds. One line on what they'll notice. \
End EXACTLY with an enlist line like: "Comment 'day one' if you're in." \
(comment velocity is the point).
- quote: genuine passage grounding the practice.

FORMAT "list" rules:
- hook: 4-8 words. PERSONAL and second-person — promise the VIEWER a benefit or \
call out a flaw they have. The viewer must instantly feel "this is about ME and what \
I get." NEVER name the author (most viewers don't know who Marcus Aurelius or Seneca \
are — naming them loses the people we most want to reach). No question mark. \
RIGHT register: "5 Rules That Make You Untouchable" / "5 Habits That Build Real \
Discipline" / "7 Things You Must Stop Doing" / "5 Rules to Master Your Mind" / \
"Follow These 5 Rules to Never Be Weak Again" / "3 Habits That Make Men Respect You" \
WRONG register (avoid — impersonal / name-drop): "5 Rules He Never Broke" / \
"3 Habits Stoics Never Skip" / "Marcus Aurelius's 5 Rules" / "7 Stoic Principles" \
The list is grounded in the assigned author's real teachings, but the hook sells the \
RESULT to the viewer, not the philosopher.
- quote: the single most powerful rule / habit from your list, written as a crisp \
standalone sentence under 12 words (this appears on screen as the text overlay).
- voiceover_text: reads through the numbered list as fast, punchy declarations. \
Speak directly to the viewer in second person where it fits. \
Pattern: "Rule 1: [crisp rule]. Rule 2: [crisp rule]..." (or "Number 1:", \
"First:", etc. — vary it naturally). Each rule is 1 tight sentence — no filler. \
Total 15-20 seconds / 35-50 words. No filler, no warm-up.

Respond with ONLY valid JSON, no markdown, no preamble, in this exact shape:
{
  "format": "story" | "pov" | "rule" | "challenge" | "minimal" | "quote" | "list",
  "theme": "...",
  "quote": "...",
  "author": "<the exact author name you were assigned>",
  "hook": "...",
  "voiceover_text": "...",
  "cta": "...",
  "pinned_comment": "...",
  "caption": "...",
  "hashtags": ["#...", "..."],
  "callout_words": ["word1", "word2"],
  "broll_queries": ["stock video search 1", "search 2", "search 3"]
}"""


def _load_doctrine() -> str:
    """Load data/doctrine.md — the owner's PERMANENT creative standing orders.

    Unlike strategy.md (rewritten daily by strategy_loop.py from analytics),
    doctrine.md is never touched by automation: it holds durable creative
    direction (ICP definition, hook psychology, format philosophy). Injected
    into every generation call, ahead of the auto-strategy.
    """
    doctrine_path = ROOT / "data" / "doctrine.md"
    if not doctrine_path.exists():
        return ""
    try:
        text = doctrine_path.read_text(encoding="utf-8").strip()
        if not text:
            return ""
        return (
            "\n\n---\n"
            "CONTENT DOCTRINE (the channel owner's permanent creative standing "
            "orders — these OVERRIDE your format defaults where they conflict):\n\n"
            + text
        )
    except Exception:
        return ""


def _load_strategy() -> str:
    """Load data/strategy.md and format it as a system-prompt addendum."""
    strategy_path = ROOT / "data" / "strategy.md"
    if not strategy_path.exists():
        return ""
    try:
        text = strategy_path.read_text(encoding="utf-8").strip()
        if not text or "_Version 0" in text:
            return ""
        return (
            "\n\n---\n"
            "CHANNEL PERFORMANCE STRATEGY (data-driven, auto-updated by the performance loop):\n"
            "Use the patterns below as GUIDANCE. They reflect what actually performs well on "
            "this channel based on real analytics. Prioritise recommendations marked as "
            "'Top Recommendations' above your own defaults.\n\n"
            + text
        )
    except Exception:
        return ""


def _load_rows() -> list[dict]:
    if not LOG.exists():
        print(
            f"WARNING: posts.csv not found at {LOG} — repeat-avoidance history is "
            f"empty this run.",
            file=sys.stderr,
        )
        return []
    with open(LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _pick_least_recent(options: list[str], history: list[str], block_last: int) -> str:
    """Pick the least-recently-used option, blocking the most recent N entries.

    history is most-recent-first. Never-used options rank as most stale.
    Ties break by position in `options` (lower index wins), making the
    choice deterministic for a given history.
    """
    blocked = set(history[:block_last])
    candidates = [o for o in options if o not in blocked] or list(options)

    def staleness(o: str) -> int:
        return history.index(o) if o in history else len(history) + 1

    return max(candidates, key=lambda o: (staleness(o), -options.index(o)))


def _pick_rotation(rows: list[dict]) -> tuple[str, str]:
    recent_authors = [r["author"] for r in reversed(rows) if r.get("author")]
    recent_themes = [r["theme"] for r in reversed(rows) if r.get("theme")]

    # Rotate the Big 5 only, least-recently-used (Chrysippus dropped for low views).
    author = _pick_least_recent(BIG5, recent_authors, block_last=1)
    theme = _pick_least_recent(THEMES, recent_themes, block_last=3)
    return author, theme


def _pick_next_theme(rows: list, current_theme: str) -> str:
    recent = [r["theme"] for r in reversed(rows) if r.get("theme")]
    return _pick_least_recent(THEMES, [current_theme] + recent, block_last=3)


def _pick_format(rows: list[dict]) -> str:
    """Rotate content format: quote → minimal → quote → list (repeating)."""
    # SUBSCRIBER-FIRST consolidation (2026-07-18): pov + challenge cut early —
    # weakest of the exploration week (pov 59v/0v, challenge 34v), most
    # off-brand (caption_only broke the channel's visual identity, a likely
    # churn driver), and owner-flagged on execution. The four survivors share
    # the classic look; "rule" is the exploration week's star (436v).
    ROTATION = ["rule", "quote", "minimal", "story"]
    return ROTATION[len(rows) % len(ROTATION)]


def _normalize_quote(q: str) -> str:
    """Collapse a quote to letters/digits only for robust duplicate detection
    (ignores punctuation, casing, and 'the fates guide…' vs 'The Fates guide…')."""
    import re
    return re.sub(r"[^a-z0-9]+", " ", (q or "").lower()).strip()


def generate_content() -> dict:
    import anthropic
    rows = _load_rows()
    used_quotes = [r["quote"] for r in rows if r.get("quote")]
    required_author, required_theme = _pick_rotation(rows)
    content_format = _pick_format(rows)
    # Day number = calendar days since the first post, so it never shifts when
    # videos are unlisted or when the pipeline runs twice in a day.
    if rows:
        channel_start = datetime.date.fromisoformat(rows[0]["date"])
    else:
        channel_start = datetime.date.today()
    day_number = (datetime.date.today() - channel_start).days + 1
    next_theme = _pick_next_theme(rows, required_theme)

    # Build a hard block list, highlighting any quotes by today's author so the
    # model knows it must pick a completely different passage from the same source.
    author_used = [q for i, q in enumerate(used_quotes)
                   if rows[i].get("author") == required_author]
    # Recent hooks (all formats) — prevents pattern repeats the model can't
    # otherwise know about, e.g. generating "Rule 9" two days running.
    recent_hooks = [r.get("hook", "") for r in rows[-40:] if r.get("hook")]
    avoid_block = ""
    if recent_hooks:
        hooked = "\n".join(f'- "{h}"' for h in recent_hooks)
        avoid_block += (
            "\n\nRecent hooks — do NOT reuse their wording, numbers, or pattern "
            f"(vary rule numbers especially):\n{hooked}"
        )
    if used_quotes:
        quoted = "\n".join(f'- "{q}"' for q in used_quotes[-200:])
        # += — a previous `=` here silently ERASED the recent-hooks block above,
        # which is why 'Rule 9' shipped four days running despite the dedup.
        avoid_block += (
            "\n\nCRITICAL — quotes already used on this channel. You MUST NOT repeat, "
            "paraphrase, or use the core idea of ANY quote on this list:\n"
            f"{quoted}"
        )
        if author_used:
            author_quoted = "\n".join(f'- "{q}"' for q in author_used)
            avoid_block += (
                f"\n\nQuotes already used from {required_author} specifically — "
                f"you MUST pick a DIFFERENT passage from the same source:\n"
                f"{author_quoted}"
            )

    # Rule format: the CODE assigns the rule number — models gravitate to 7/9
    # no matter the instructions ('Rule 9' shipped 4 days straight). Numbers
    # cycle through a fixed shuffled order, skipping any already used.
    rule_line = ""
    if content_format == "rule":
        import re as _re
        used_ns = set()
        for r in rows:
            m = _re.match(r"\s*Rule\s+(\d+)", r.get("hook", "") or "")
            if m:
                used_ns.add(int(m.group(1)))
        order = [7, 12, 3, 19, 24, 5, 31, 14, 21, 4, 28, 11, 17, 35, 8, 26,
                 6, 15, 40, 22, 9, 33, 13, 18, 27, 10, 38, 16, 23, 29]
        rule_n = next((n for n in order if n not in used_ns), order[len(rows) % len(order)])
        rule_line = (f"\nThis rule post MUST use EXACTLY the number {rule_n}: "
                     f"the hook starts with 'Rule {rule_n}:'. No other number.")

    user_msg = (
        f"Generate today's Stoic Reel.\n"
        f"FORMAT: {content_format}\n"
        f"Required author: {required_author}\n"
        f"Draw the quote from: {SOURCE_HINTS[required_author]}.\n"
        f"Required theme: {required_theme}\n"
        f"Tomorrow's theme (for the CTA): {next_theme}\n"
        f"Pick a genuine, lesser-known passage that cuts differently from anything "
        f"on the avoid list."
        f"{rule_line}"
        f"{avoid_block}"
    )

    strategy_addendum = _load_doctrine() + _load_strategy()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    required = {"format", "theme", "quote", "author", "hook", "voiceover_text",
                "cta", "pinned_comment", "caption", "hashtags", "callout_words"}
    used_norm = {_normalize_quote(q) for q in used_quotes}

    # Dedup agent: regenerate (capped at 3) if the model returns a quote we have
    # already shipped. A past leak let one passage post 4× (one got 4 views);
    # this closes it without ever failing the run.
    extra_avoid = ""
    data = None
    for attempt in range(3):
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            temperature=1.0,
            system=SYSTEM + strategy_addendum,
            messages=[{"role": "user", "content": user_msg + extra_avoid}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Claude response missing keys: {missing}")
        if _normalize_quote(data["quote"]) not in used_norm:
            break
        print(f"  content: duplicate quote (attempt {attempt + 1}/3) — "
              f"regenerating: \"{data['quote'][:50]}\"", file=sys.stderr)
        extra_avoid = (
            f"\n\nSTOP: the quote \"{data['quote']}\" has ALREADY been posted on "
            f"this channel. Choose a COMPLETELY different genuine passage."
        )
    else:
        print("  content: still a duplicate after 3 tries — shipping it anyway "
              "(better than failing the run)", file=sys.stderr)

    data["day_number"] = day_number
    return data
