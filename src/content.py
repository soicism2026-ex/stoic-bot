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
# Medians at 1 day old (age-corrected, full history): anger 388, fear 331,
# resilience 289, mortality 244, ego 199, control 194, discipline 188,
# duty 184, desire 170, friendship 155.
# 2026-08-13: friendship and desire DROPPED — the two weakest, and both well
# under half of anger. The strongest three lead the list so the LRU picker
# reaches them first. Eight themes kept deliberately: cutting to the top three
# would triple how often each recurs, and repetition is the thing that hurt us.
THEMES = [
    "anger",
    "fear",
    "resilience",
    "mortality/memento mori",
    "ego",
    "control vs acceptance",
    "discipline",
    "duty/justice",
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
- voiceover_story: the SETUP only — the scene, the tension, the moment. It must \
NOT contain the quote and must not paraphrase it. This plays while the screen \
shows only the hook and b-roll. 2-4 sentences.
- voiceover_lesson: what is said AFTER the quote has appeared on screen and the \
viewer has had a silent beat to read it. It MUST OPEN by speaking the quote \
aloud, word for word, then land the lesson in 1-2 short sentences. Hearing the \
words just read is reinforcement, not repetition.
  WHY THE SPLIT: the owner cannot read the quote and follow narration at the \
same time — "I have a hard time reading the quote while also listening to the \
dialogue". Nothing is ever narrated over the quote's reading beat.
- broll_queries: FOUR stock-video search queries (4-7 words each), in narration \
order — one for each successive beat of the voiceover, each literally depicting \
what is being SAID at that moment so the footage cuts in sync with the words in \
real time. Concrete, human, filmable, cinematic. \
RIGHT: "man staring at phone dark room" / "rain window city night lonely" / \
"hand clenching into fist slow motion" / "person walking away sunrise street". \
WRONG: "stoicism" / "discipline concept" / anything abstract a stock site \
can't match. (A recurring marble-statue "guide" shot is added automatically to \
open and close the video — do NOT include statues here; depict the SCENES.)
- Pinned comment: write it like a REAL PERSON typing under their own video, not \
a brand prompt. Open by saying something true from your own side (why you made \
this one, what it cost you, what you're still bad at), THEN ask one specific \
question that needs a real answer — never "what do you think?" or "let me know \
below". Under 35 words total. First person. Vary the shape every single day: \
sometimes a confession then a question, sometimes just a question asked plainly, \
sometimes an admission with no question at all. \
RIGHT: "I wrote this one after losing my temper at someone who didn't deserve \
it. What's the thing that gets you every time?" \
WRONG: "What do you think? Comment below!" / anything that sounds like a \
marketing prompt. \
Then on a NEW LINE, one short, casual invitation to follow along — phrased \
differently each day, never salesy, e.g. "posting one of these a day if you want \
to follow along" or "day N of doing this daily". Lowercase is fine; it should \
read like a person, not a call-to-action.
- Caption: 1-2 sentences that reframe the idea for daily life + one specific question.
- Hashtags: 8-12, mixing broad (#stoicism #discipline) and mid-size niche tags.
- callout_words: 2-4 concrete nouns that appear verbatim in the voiceover. They \
flash large on screen when spoken. Concrete only — "phone", "anger", "body", not \
"virtue" or "wisdom".

HOOK LENGTH — MEASURED, NOT A STYLE OPINION (2026-08-16):
Retention against hook length across 100 videos on THIS channel:
  1-3 words  68.8%      4-5 words  57.3%      6-7 words  54.5%      8+  50.0%
Correlation -0.29. Every extra word costs retention, and retention is what the
algorithm ranks on. The current median hook is 5 words.
- Write the hook in FOUR WORDS OR FEWER. Two or three is better.
- It must still be a complete thought, not a fragment of one. "Not tomorrow." and "Let it be." are the two highest-retaining hooks this channel has ever published. "Nothing left to prove." held 126%.
- Do not explain the hook. If it needs a second clause to make sense, it is the wrong hook — find the three words that carry the whole idea.
- The ONLY exception is the "rule" format when its assigned shape includes the number; even then, keep the imperative itself to four words.

OPENER VARIETY (hard rule, 2026-08-13):
The format pool is down to three, so each one returns every single day. The words have to carry the difference or the feed reads as one video on repeat — which is what the channel is recovering from: it shipped "Rule 7" nine times, one identical music bed thirty times, and the same hook verbatim three times, and 1-day views fell 77%.
- Your hook must NOT begin with the same word as ANY of the recent hooks you are shown. Recent openers to avoid outright: "Rule", "If", "You", "Nothing", "Nero".
- Vary the SHAPE of the opening, not just the wording. Rotate between: a bare statement, a second-person observation, a concrete image with no verb, a time marker ("2am."), a number, a short question. Never the same shape two days running.
- "rule" format: the number is assigned to you. Do not open every rule post with the word "Rule" — lead with the rule itself and let the number sit after it, or open on the image and arrive at the rule.
- Two hooks that share their first three words are the same hook. Rewrite.

HELPFULNESS TEST (2026-08-13, outranks everything below):
Before you output, read your script back and ask: if a man watched this at 2am on a bad night, would he feel BETTER about himself, or smaller? If smaller, rewrite it. Sharpness is never worth making someone feel worse.
- Choose moments where the person GOT THROUGH IT and was okay afterwards — not just endured, not just died well. A story that proves the thing is survivable helps; a story that proves life is hard does not.
- Give ONE thing he can actually use tonight, with a shape: a sentence to say, a thing to put down, a question to ask himself, one action before sleep. Advice with no handle is decoration.
- ABSOLVE BEFORE YOU INSTRUCT. Name what he is beating himself up about and take the shame off it first ("that is not weakness, it is untrained"), THEN give the practice. Instruction first reads as a lecture and lands as one more failure on the pile.
- Write for the ORDINARY version of the struggle — tired, stuck, lonely, ashamed — not only the man chasing a 5am PR. More people are quietly having a hard week than are optimising.
- If the script drifts toward real despair, the turn MUST move him toward people: call someone, tell someone, let someone in. NEVER "endure it alone, that's what a strong man does". Isolation dressed as strength is the most harmful thing in this niche.
- BANNED: shame as motivation, "nobody is coming to save you" as a closer, contempt for people who are struggling, treating needing help as weakness.

EMOTIONAL CORE (applies to EVERY format — this is what turns a quote card into a \
moment someone remembers):
- Write to ONE real person having a hard night, as a friend who has stood in \
that exact spot — never a teacher lecturing from above. Warmth outranks \
authority every time.
- Name the actual FEELING, physically and specifically: the 2am ceiling stare, \
the tight chest before you hit send, the hollow after you snapped at someone \
you love, the Sunday-night dread. Feelings you can point to — not concepts.
- Earn the comfort. Admit it is genuinely hard BEFORE the Stoic turn. No toxic \
positivity, no "just stop caring." Sit in the ache for one honest beat first.
- Speak with quiet conviction — you truly believe this 2,000-year-old line can \
hold someone together tonight. That belief IS the emotion the viewer feels.
- Land on being SEEN, not being taught. The best last line makes one person \
think "how did they know." Leave them with hope, tenderness, or hard-won calm \
— never a shrug, never a scold.

FORMAT "question" rules (F3, format test 2026-08-21):
This format opens on ONE hard question in SILENCE for two seconds, then the
voice answers. In a feed engineered to be loud, silence and a direct question
is the pattern interrupt. Everything about it must earn that silence.
- hook: the QUESTION itself, and nothing else. Second person, present tense, under six words, ending in a question mark. It must be answerable by one real person about their actual life, not rhetorical and not clever. RIGHT: "What are you still angry about?" / "Who did you stop calling?" / "What did you quit this week?" WRONG: "Have you ever wondered about the nature of virtue?" / anything that sounds like an essay title or a quiz.
- The question must NOT contain the answer or hint at it. If a viewer can guess where it lands, the silence is dead air instead of tension.
- voiceover_story: begins by ANSWERING the question directly in the first sentence — the viewer has been waiting two seconds, do not make them wait longer. Then the scene or the reason. 2-3 sentences.
- voiceover_lesson: the quote spoken aloud, then the turn, as normal.
- The question is on screen alone during the silence, so it carries the whole opening. Write it as if it is the only thing you get to say.

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

FORMAT "letter" rules:
The most personal format — an intimate, direct message to the viewer, like a \
letter from someone who loves them and refuses to lie to them. Pure connection.
- hook: 3-6 words, spoken leaning in close, like the first line of a letter. \
RIGHT: "If today felt heavy—" / "Read this if you're tired." / "You don't have \
to earn rest." / "Still awake? Then this is for you." \
WRONG: anything that sounds like a headline, a rule, or advice.
- voiceover_text: 40-55 words, second person, warm and unhurried. Open by \
naming exactly where they are TONIGHT — specific, tender, true (the unanswered \
text, the pretending-you're-fine, the exhaustion nobody sees). Admit it's hard. \
Then hand them the Stoic truth not as a rule but as something you'd say with a \
hand on their shoulder. Close on ONE line of quiet hope that loops back to the \
hook. First person "I"/"we" is welcome here — shared struggle, never lecture.
- quote: the genuine passage the letter is built around, under 14 words, woven \
in as the heart of the message (still correctly attributed to the author).

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
  "format": "story" | "letter" | "pov" | "rule" | "challenge" | "minimal" | "quote" | "list",
  "theme": "...",
  "quote": "...",
  "author": "<the exact author name you were assigned>",
  "hook": "...",
  "voiceover_story": "...",
  "voiceover_lesson": "...",
  "cta": "...",
  "pinned_comment": "...",
  "caption": "...",
  "hashtags": ["#...", "..."],
  "callout_words": ["word1", "word2"],
  "broll_queries": ["stock video search 1", "search 2", "search 3"]
}"""


def _repair_script_split(data: dict) -> None:
    """Guarantee voiceover_story / voiceover_lesson exist.

    The two-part script is what lets the quote be READ in silence before it is
    spoken — the owner cannot do both at once. But a model that returns the old
    single `voiceover_text` must not fail the run, and backup JSON written
    before this change still has the old shape. So: if the split is missing,
    derive it by putting the last sentences in the lesson, which is where the
    turn lives in every one of these scripts anyway.
    """
    has_story = bool((data.get("voiceover_story") or "").strip())
    has_lesson = bool((data.get("voiceover_lesson") or "").strip())
    if has_story and has_lesson:
        return
    whole = (data.get("voiceover_text") or "").strip()
    if not whole:
        # Nothing to work with; leave it, the required-keys check will complain.
        return
    import re as _re
    parts = [p.strip() for p in _re.split(r"(?<=[.!?])\s+", whole) if p.strip()]
    if len(parts) < 2:
        data.setdefault("voiceover_story", whole)
        data.setdefault("voiceover_lesson", whole)
        return
    cut = max(1, len(parts) - 2)          # last two sentences carry the turn
    data["voiceover_story"] = " ".join(parts[:cut])
    data["voiceover_lesson"] = " ".join(parts[cut:])
    print("  content: model returned a single script — split it into "
          "story/lesson so the quote still gets a silent reading beat",
          file=sys.stderr)


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
    # Emotional-connection era (2026-07-20): 5-format rotation adds "letter" —
    # the intimate direct-message format — for day-to-day variety AND depth. All
    # keep the classic look. EMOTIONAL CORE in SYSTEM raises every format's warmth.
    # 2026-08-13 CUT: letter and story. Age-corrected medians at 1 day old
    # across the full history — quote 253 (n=23), rule 253 (n=16), minimal 209
    # (n=30), letter 188 (n=10), story 132 (n=24) — and in the last week they
    # were the floor outright: four of the six worst posts were letters
    # (17v, 20v, 27v) and a story took 24v.
    #
    # Narrowing the pool RAISES the repetition risk that most likely caused the
    # 77% collapse, so it is paired with a hard opener-variety rule in SYSTEM.
    # Three formats over three posts a day means each returns daily; the words
    # have to carry the difference.
    # WEIGHTED toward minimal (2026-08-16). Views and retention disagreed, and
    # retention wins: minimal holds 70.9% median (n=27) against quote 53.5% and
    # rule 50.3%. Views measure how hard the algorithm pushed a video once;
    # retention decides whether it pushes the next one. With the channel
    # suppressed, retention is the lever that recovers distribution.
    # A 4-slot cycle over 3 posts/day also means the pattern shifts every day
    # rather than locking each format to a time of day.
    # Order matters as much as the mix: ["minimal","quote","rule","minimal"]
    # gives minimal twice in a row at the cycle boundary. Interleaved instead,
    # so minimal is every other post and no format ever repeats back to back.
    # FORMAT TEST (2026-08-21): "question" takes every third slot, so F3 runs
    # ALONGSIDE the existing format rather than replacing it. That is better
    # than the blocked design in data/format_test.md — the control is
    # concurrent, so day-of-week, time-of-day and whatever the algorithm is
    # doing that week hit both arms equally. Five F3 posts land in ~5 days.
    # No format repeats back to back.
    ROTATION = ["question", "minimal", "quote", "question", "minimal", "rule"]
    return ROTATION[len(rows) % len(ROTATION)]


RETENTION_CSV = Path(os.environ.get("RETENTION_CSV", ROOT / "data" / "retention.csv"))


def _winning_hooks(rows: list, top: int = 6, min_views: int = 60) -> list:
    """The best-RETAINED hooks this channel has ever published.

    Until now the content prompt carried SEVEN avoid-blocks and not one example
    of something that worked — the model was told what not to do and never what
    to aim at. 189 posts of performance data sat unused.

    Ranked by retention, not views. Views measure how well the algorithm pushed
    a video; retention measures whether people STAYED, which is what the
    algorithm ranks on next time. A 27-view short at 126% retention taught us
    more than a 700-view one at 40%.

    Retention above 100% is real: Shorts loop, so a short video watched twice
    reports >100%. Those are the strongest signal we have. Capped at 300% so a
    single freak loop cannot dominate the list.
    """
    if not RETENTION_CSV.exists():
        return []
    ret: dict = {}
    try:
        with open(RETENTION_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    ret[r["video_id"]] = (min(float(r["avg_view_pct"]), 300.0),
                                          int(r["views"] or 0))
                except (ValueError, TypeError, KeyError):
                    continue
    except Exception:  # noqa: BLE001
        return []
    scored = []
    for r in rows:
        vid, hook = (r.get("video_id") or "").strip(), (r.get("hook") or "").strip()
        if not vid or not hook or vid not in ret:
            continue
        pct, views = ret[vid]
        if views < min_views:      # tiny samples are noise, not signal
            continue
        scored.append((pct, hook, r.get("format") or ""))
    scored.sort(reverse=True)
    seen, out = set(), []
    for pct, hook, fmt in scored:
        key = hook.lower()[:20]
        if key in seen:
            continue
        seen.add(key)
        out.append((pct, hook, fmt))
        if len(out) >= top:
            break
    return out


def _rule_directive(rows: list) -> str:
    """The rule post's number AND hook shape, both assigned by CODE.

    The number is code-assigned because models gravitate to 7 and 9 no matter
    what the prompt says ("Rule 9" shipped four days straight, then "Rule 7"
    nine times once a stale CSV header blinded the dedup).

    The SHAPE is code-assigned for the same reason, discovered 2026-08-16: the
    old directive ended "the hook starts with 'Rule N:'", a direct order that
    silently overruled the OPENER VARIETY rule in SYSTEM. Result — every single
    rule post opened with the word "Rule", making it the most repeated opening
    word on a channel that was being suppressed for repetition. Two
    contradicting instructions in one prompt, and the specific imperative wins.
    So the code rotates the shape rather than arguing with itself.
    """
    import re as _re
    used_ns = set()
    for r in rows:
        m = _re.match(r"\s*Rule\s+(\d+)", r.get("hook", "") or "")
        if m:
            used_ns.add(int(m.group(1)))
    order = [7, 12, 3, 19, 24, 5, 31, 14, 21, 4, 28, 11, 17, 35, 8, 26,
             6, 15, 40, 22, 9, 33, 13, 18, 27, 10, 38, 16, 23, 29]
    rule_n = next((n for n in order if n not in used_ns),
                  order[len(rows) % len(order)])
    n_rules = sum(1 for r in rows if (r.get("format") or "") == "rule")
    shapes = [
        f"the hook is EXACTLY 'Rule {rule_n}: <imperative>' - this shape only",
        f"the hook LEADS with the imperative and puts the number after it, e.g. "
        f"'<imperative>. Rule {rule_n}.' - it MUST NOT begin with the word Rule",
        f"the hook is the imperative ALONE with no number in it at all; mention "
        f"rule {rule_n} once in voiceover_lesson instead. The hook MUST NOT "
        f"begin with the word Rule",
    ]
    return (f"\nThis rule post MUST use EXACTLY the number {rule_n} and no "
            f"other. Hook shape for this post: {shapes[n_rules % len(shapes)]}.")


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
    # EVERY hook ever used, not a recent window. A 40-row window is only ~13
    # days at 3 posts/day, and the repeats in practice came back at 17-day
    # gaps: "Nero handed him a death sentence" shipped VERBATIM three times
    # (2026-07-17, 07-30, 08-06) while technically obeying the old window.
    # Hooks are one line each, so banning all of them costs little.
    all_hooks = [(r.get("hook") or "").strip() for r in rows]
    all_hooks = [h for h in all_hooks if h]
    recent_hooks = all_hooks[-40:]
    avoid_block = ""
    if all_hooks:
        banned = "\n".join(f'- "{h}"' for h in dict.fromkeys(all_hooks))
        avoid_block += (
            "\n\nCRITICAL — every hook this channel has ever published. You MUST "
            "NOT reuse any of them verbatim, near-verbatim, or with a word "
            "swapped. Do not reuse their opening formula either (if three of "
            "them start with the same proper noun, do not start with it "
            f"again):\n{banned}"
        )
    if recent_hooks:
        hooked = "\n".join(f'- "{h}"' for h in recent_hooks)
        avoid_block += (
            "\n\nThe most recent hooks — avoid their PATTERN and rhythm too, not "
            f"just their words (vary rule numbers especially):\n{hooked}"
        )
        # Name the actual repeated opening words. The model reliably re-uses an
        # opener even while obeying "don't repeat a hook", because a different
        # sentence starting the same way still feels new to it. The variety
        # watchdog caught exactly this: 6 recent hooks opening "Rule", 5 "If",
        # 4 "You".
        from collections import Counter as _C
        openers = _C(h.split()[0].strip('.,:;"\'').lower()
                     for h in recent_hooks[-15:] if h.split())
        overused = [w for w, n in openers.items() if n >= 2]
        if overused:
            avoid_block += (
                "\n\nBANNED OPENING WORDS for this hook — each already opens "
                "two or more recent hooks, and a feed of identical openings is "
                f"what got this channel suppressed: {', '.join(sorted(overused))}"
            )
    # POSITIVE signal — the only one in this prompt. Everything else here is a
    # ban list.
    winners = _winning_hooks(rows)
    if winners:
        won = "\n".join(f'- "{h}"  ({p:.0f}% retention, {f})' for p, h, f in winners)
        avoid_block += (
            "\n\nHOOKS THAT ACTUALLY WORKED on this channel, ranked by how long "
            "people STAYED (over 100% means they watched it twice — Shorts "
            f"loop):\n{won}\n"
            "Match their ENERGY and their LENGTH. Do NOT reuse their words — "
            "every one of them is on the banned list above. Notice what they "
            "have in common: they are short, they are complete thoughts, and "
            "they do not explain themselves."
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
    rule_line = _rule_directive(rows) if content_format == "rule" else ""

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
    required = {"format", "theme", "quote", "author", "hook", "voiceover_story",
                "voiceover_lesson", "cta", "pinned_comment", "caption",
                "hashtags", "callout_words"}
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
            # anthropic 1.0.0 REMOVED temperature from Messages.create()
            # (it is not in output_config either — it is gone). An
            # unpinned `anthropic>=0.39.0` picked up the new major on a
            # routine `pip install` and every post failed 2 seconds in
            # with TypeError, four slots in a row, 2026-08-21.
            # Nothing is lost: it was set to 1.0, the top of the old
            # range, and variety is now enforced structurally (banned
            # openers, full-history hook dedup, format rotation) rather
            # than by a sampling knob.
            system=SYSTEM + strategy_addendum,
            messages=[{"role": "user", "content": user_msg + extra_avoid}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        _repair_script_split(data)
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
    # Everything downstream that just wants "the script" (callout matching,
    # logging, backups written before this change) keeps working.
    data["voiceover_text"] = (
        f"{data['voiceover_story'].strip()} {data['voiceover_lesson'].strip()}"
    ).strip()
    return data
