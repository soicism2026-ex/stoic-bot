"""
Fama, the Roman goddess of news (owner 2026-11-16: "Pivot the shorts to
something more relevant to today's world and news everyday or find a way to
figure out what's trending the day before posting and post relating to that
event").

Before each Short is rehearsed, Fama reads what the US is talking about today
(Google Trends, Wikipedia's most-read, Google News; free, keyless). A plain
code screen drops tragedy, harm, politics and anything about a minor BEFORE a
model sees a word. A model then picks, among the next 12 quotes the rotation
would air, the one that a safe trend fits, and writes a hook, a description
lead, a question and tags that tie the timeless quote to the event. Code
validates all of it. The QUOTE ITSELF IS NEVER CHANGED.

Every failure (network, model, parsing, validation) means "no topical plan":
the Short airs as the rotation chose, never an exception that stops a post.

    python3 scripts/fama.py plan     # decide for the next post, write data/topical.json
    python3 scripts/fama.py show     # print the stored plan
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PLAN = ROOT / "data" / "topical.json"
POSTS = ROOT / "data" / "posts.csv"
DOCTRINE = ROOT / "data" / "doctrine.md"

USER_AGENT = "stoic-bot/1.0 (+https://github.com/soicism2026-ex/stoic-bot)"
TIMEOUT = 15
FEATURE = "topical"
MIN_FIT = 7
KEEP_AGE_H = 20
N_CANDIDATES = 12
N_TRENDS = 15

TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"
WIKI_FEED = "https://api.wikimedia.org/feed/v1/wikipedia/en/featured/{y}/{m}/{d}"
NEWS_RSS = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

# ---------------------------------------------------------------------------
# The safety screen: ONE constant. A topic or headline touching any of these
# never reaches the model, and no word of them may appear in what it writes.
# Kept: sports, entertainment, technology and products, money and markets,
# lotteries and shopping days, weather without casualties, holidays and
# seasons, science and space, viral culture.
# ---------------------------------------------------------------------------
TRAGEDY_WORDS = (
    "death", "died", "dies", "killed", "dead", "obituary", "funeral", "shooting",
    "shot", "murder", "stabbing", "attack", "terror", "war", "missile", "airstrike",
    "invasion", "hostage", "crash", "collapse", "earthquake", "hurricane", "tornado",
    "flood", "wildfire", "explosion", "victims", "injured", "abuse", "assault",
    "rape", "suicide", "overdose", "cancer", "diagnosis", "hospitalized",
    "missing child", "kidnap", "arrest", "charged", "indicted", "sentenced",
    "lawsuit", "sued", "trial", "verdict", "scandal", "accused", "allegations",
)
POLITICS_WORDS = (
    "election", "vote", "candidate", "senator", "congress", "president", "governor",
    "campaign", "voting", "voter", "democrat", "republican", "party", "trump", "biden", "harris",
    "policy", "bill", "court", "supreme court", "abortion", "immigration", "border",
    "deport", "gun", "protest", "riot", "religion", "church", "mosque", "israel",
    "gaza", "ukraine", "russia", "china-taiwan",
)
# Anything about a named minor: ages under 18 and words for young people.
MINOR_WORDS = ("teen", "teenager", "minor", "child", "children", "kid", "kids",
               "boy", "girl", "toddler", "infant", "schoolboy", "schoolgirl", "student")
BLOCKED = TRAGEDY_WORDS + POLITICS_WORDS + MINOR_WORDS
_MINOR_AGE = re.compile(r"\b(?:[0-9]|1[0-7])[- ]?(?:year|yr)s?[- ]?old\b", re.I)
_BLOCK_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in sorted(BLOCKED, key=len, reverse=True))
    + r")(?:s|es|ed|ing)?(?![a-z0-9])", re.I)

# What the plan's text may never ask for.
ASK_RE = re.compile(r"\b(comment|comments|subscribe|subscribers?|like and|follow|link)\b", re.I)


def blocked_words(text: str) -> list[str]:
    """Every screened word (or a minor's age) found in `text`."""
    found = [m.group(0).lower() for m in _BLOCK_RE.finditer(text or "")]
    found += [m.group(0).lower() for m in _MINOR_AGE.finditer(text or "")]
    return found


def is_safe(trend: dict) -> bool:
    text = " . ".join([trend.get("topic", "")] + list(trend.get("headlines") or []))
    return not blocked_words(text)


def screen(trends: list[dict]) -> list[dict]:
    """Drop every trend whose topic or headlines touch tragedy, harm, politics
    or a minor. Plain code, run before any model sees a trend."""
    return [t for t in trends if is_safe(t)]


# ---------------------------------------------------------------------------
# Fetching: free, keyless, each source independent
# ---------------------------------------------------------------------------
def _get(url: str) -> bytes:
    import requests
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def _num(text: str) -> float:
    """'200K+' -> 200000, '2M+' -> 2000000, '5,000+' -> 5000."""
    m = re.match(r"\s*([\d,.]+)\s*([KkMm]?)", text or "")
    if not m:
        return 0.0
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    return v * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_trends_rss(xml_bytes: bytes) -> list[dict]:
    out = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        topic, traffic, heads = "", "", []
        for el in item:
            n = _local(el.tag)
            if n == "title":
                topic = (el.text or "").strip()
            elif n == "approx_traffic":
                traffic = el.text or ""
            elif n == "news_item":
                for sub in el:
                    if _local(sub.tag) == "news_item_title" and (sub.text or "").strip():
                        heads.append(html.unescape(sub.text.strip()))
        if topic:
            out.append({"topic": topic, "score": _num(traffic), "headlines": heads[:3],
                        "source": "google-trends"})
    return out


def parse_wikipedia(data: dict) -> list[dict]:
    skip = ("Main_Page", "Main Page", "Special:", "Wikipedia:", "Portal:", "File:", "Help:", "Category:", "-")
    out = []
    for a in (data.get("mostread") or {}).get("articles") or []:
        title = (a.get("normalizedtitle") or a.get("title") or "").strip()
        if not title or title == "-" or any(title.startswith(s) for s in skip[:-1]):
            continue
        desc = (a.get("description") or "").strip()
        out.append({"topic": title, "score": float(a.get("views") or 0),
                    "headlines": [desc] if desc else [], "source": "wikipedia"})
    for n in data.get("news") or []:
        story = re.sub(r"<[^>]+>", "", html.unescape(n.get("story") or "")).strip()
        links = [(link.get("normalizedtitle") or link.get("title") or "").strip()
                 for link in (n.get("links") or [])]
        if story and links and links[0]:
            out.append({"topic": links[0], "score": 0.0, "headlines": [story],
                        "source": "wikipedia-news"})
    return out


def parse_news_rss(xml_bytes: bytes) -> list[dict]:
    out = []
    for i, item in enumerate(ET.fromstring(xml_bytes).iter("item")):
        title = ""
        for el in item:
            if _local(el.tag) == "title":
                title = html.unescape((el.text or "").strip())
        # Google News appends " - Publisher"
        title = re.sub(r"\s+-\s+[^-]{2,40}$", "", title)
        if title:
            out.append({"topic": title, "score": float(max(1, 100 - i)),
                        "headlines": [title], "source": "google-news"})
    return out


def dedupe(trends: list[dict]) -> list[dict]:
    """Best first; a topic seen twice keeps the higher score and gathers the
    headlines of both."""
    by: dict[str, dict] = {}
    for t in trends:
        key = re.sub(r"[^a-z0-9]+", " ", t["topic"].lower()).strip()
        if not key:
            continue
        if key in by:
            have = by[key]
            for h in t["headlines"]:
                if h not in have["headlines"]:
                    have["headlines"].append(h)
            have["headlines"] = have["headlines"][:3]
            if t["score"] > have["score"]:
                have["score"], have["source"] = t["score"], t["source"]
        else:
            by[key] = {**t, "headlines": list(t["headlines"])[:3]}
    # sources use different scales: rank within each source, then interleave
    ranked: dict[str, list[dict]] = {}
    for t in sorted(by.values(), key=lambda t: -t["score"]):
        ranked.setdefault(t["source"], []).append(t)
    out, i = [], 0
    while any(i < len(v) for v in ranked.values()):
        for v in ranked.values():
            if i < len(v):
                out.append(v[i])
        i += 1
    return out


def fetch(today: dt.date | None = None) -> list[dict]:
    """[{topic, score, headlines[:3], source}], deduplicated. A source that
    fails is skipped; all failing gives []."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    got: list[dict] = []
    jobs = (
        (TRENDS_RSS, parse_trends_rss),
        (WIKI_FEED.format(y=today.year, m=f"{today.month:02d}", d=f"{today.day:02d}"),
         lambda b: parse_wikipedia(json.loads(b))),
        (NEWS_RSS, parse_news_rss),
    )
    for url, parse in jobs:
        try:
            got += parse(_get(url))
        except Exception as e:  # noqa: BLE001
            print(f"  [fama] {url.split('/')[2]} skipped: {str(e)[:80]}", file=sys.stderr)
    return dedupe(got)


# ---------------------------------------------------------------------------
# Candidates: the next quotes the rotation would air
# ---------------------------------------------------------------------------
def _rows() -> list[dict]:
    return list(csv.DictReader(open(POSTS, encoding="utf-8"))) if POSTS.exists() else []


def candidates(rows: list[dict] | None = None, n: int = N_CANDIDATES) -> list[dict]:
    import edits
    sim = [dict(r) for r in (rows if rows is not None else _rows())]
    out = []
    for _ in range(n):
        q = edits.rotation_pick(sim)
        if not q:
            break
        out.append({"id": q["id"], "author": q["author"], "theme": q["theme"],
                    "quote": q["quote"], "hook": q["hook"]})
        sim.append({"experiment": f"edit:{q['id']}", "author": q["author"],
                    "theme": q["theme"], "quote": q["quote"]})
    return out


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------
def _doctrine_10() -> str:
    try:
        text = DOCTRINE.read_text(encoding="utf-8")
        m = re.search(r"^## 10\..*?(?=^## \d+\.|\Z)", text, re.S | re.M)
        return m.group(0).strip() if m else ""
    except OSError:
        return ""


def system_prompt() -> str:
    return (
        "You are Fama, the news desk of a faceless Stoicism YouTube Shorts channel. "
        "Each Short airs ONE timeless Stoic quote. You never change a quote. Today you may tie "
        "ONE quote to ONE trending, harmless event so the Short feels like today.\n\n"
        "RULES\n"
        "- The event is the doorway; the quote is the point. Never exploit tragedy, never take a "
        "political side, never mock, never name a private person.\n"
        "- hook: 2-9 words, speaks to the VIEWER's own life through the event (their feeling, "
        "choice or temptation). It may be a question. It takes a stance or poses a choice so "
        "people want to answer (a dilemma, a mild provocation). It NEVER asks for comments, "
        "likes, follows or subscribes, and states no fact about the event beyond its name.\n"
        "- punch: ONE word taken from the hook, the word to highlight.\n"
        "- lead: ONE sentence, at most 22 words, that opens the description by connecting the "
        "event to the quote. Use only names and numbers found in the trend.\n"
        "- question: one line the viewer answers from their own life, often a choice between two "
        "(at most 20 words).\n"
        "- tags: 3 to 6 search keywords for the trend, plain words, no #.\n"
        "- fit: 0-10, how naturally the quote answers the event. Below 7 means answer none.\n"
        "- If nothing fits well, answer {\"none\": true}.\n\n"
        "Answer with STRICT JSON only, no prose: "
        "{\"trend_index\": int, \"quote_id\": str, \"fit\": int, \"hook\": str, \"punch\": str, "
        "\"lead\": str, \"question\": str, \"tags\": [str]} or {\"none\": true}.\n\n"
        "THE OWNER'S DESCRIPTION STYLE (doctrine 10):\n" + _doctrine_10()
    )


def user_prompt(trends: list[dict], cands: list[dict]) -> str:
    tl = [{"index": i, "topic": t["topic"], "source": t["source"],
           "headlines": t["headlines"]} for i, t in enumerate(trends)]
    cl = [{"id": c["id"], "author": c["author"], "theme": c["theme"], "quote": c["quote"],
           "usual_hook": c["hook"]} for c in cands]
    return ("TODAY'S TRENDS (already screened):\n" + json.dumps(tl, ensure_ascii=False)
            + "\n\nTHE NEXT QUOTES (pick one):\n" + json.dumps(cl, ensure_ascii=False))


def parse_reply(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


# ---------------------------------------------------------------------------
# Validation in code: all must pass or there is no plan
# ---------------------------------------------------------------------------
_STARTERS = {"a", "an", "the", "when", "what", "why", "how", "do", "does", "did", "is", "are",
             "will", "would", "who", "you", "your", "if", "it", "its", "this", "that", "there",
             "they", "we", "he", "she", "i", "and", "but", "so", "or", "can", "should", "could",
             "have", "has", "stop", "start", "while", "before", "after", "still", "even", "all",
             "no", "not", "one", "every", "some", "let", "keep", "don't", "dont", "ever"}


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower()).split())


def _names(text: str) -> list[str]:
    """Capitalised multi-word names. The first word of a sentence is dropped
    when it is an ordinary starter ("When", "Your")."""
    names = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = re.findall(r"[A-Za-z][A-Za-z'’-]*|\d[\d,.]*", sent)
        run: list[str] = []
        for i, w in enumerate(words + [""]):
            cap = bool(w) and w[0].isupper() and w not in ("I", "I'm", "I'll")
            if cap and not (i == 0 and w.lower() in _STARTERS):
                run.append(w)
                continue
            if len(run) >= 2:
                names.append(" ".join(run))
            run = []
    return names


def _numbers(text: str) -> list[str]:
    return [m.replace(",", "").rstrip(".") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def validate(raw: dict, trends: list[dict], cands: list[dict], post_hooks: set[str]) -> tuple[dict | None, str]:
    """(clean plan fields, "") or (None, reason)."""
    if not isinstance(raw, dict) or raw.get("none"):
        return None, "the model found no fit"
    try:
        fit = float(raw.get("fit"))
        idx = int(raw.get("trend_index"))
    except (TypeError, ValueError):
        return None, "fit or trend_index missing"
    if fit < MIN_FIT:
        return None, f"fit {fit:g} is under {MIN_FIT}"
    if not 0 <= idx < len(trends):
        return None, f"trend_index {idx} not offered"
    cand = next((c for c in cands if c["id"] == raw.get("quote_id")), None)
    if cand is None:
        return None, f"quote {raw.get('quote_id')!r} not offered"
    hook, punch = str(raw.get("hook") or "").strip(), str(raw.get("punch") or "").strip()
    lead, question = str(raw.get("lead") or "").strip(), str(raw.get("question") or "").strip()
    if any("#" in str(x) for x in [hook, lead, question] + list(raw.get("tags") or [])):
        return None, "contains '#'"
    tags = [str(t).strip() for t in (raw.get("tags") or []) if str(t).strip()]
    if not 2 <= len(hook.split()) <= 9:
        return None, "hook is not 2-9 words"
    if _norm(punch) not in [_norm(w) for w in hook.split()] or not punch or len(punch.split()) != 1:
        return None, "punch is not one word of the hook"
    if not lead or len(lead.split()) > 22:
        return None, "lead is empty or over 22 words"
    if not question or len(question.split()) > 20:
        return None, "question is empty or over 20 words"
    if not 3 <= len(tags) <= 6:
        return None, "tags are not 3-6"
    text = " | ".join([hook, lead, question] + tags)
    if "#" in text:
        return None, "contains '#'"
    if ASK_RE.search(text):
        return None, "asks for a comment, follow, subscribe or link"
    bad = blocked_words(text)
    if bad:
        return None, f"uses a screened word: {bad[0]}"
    trend = trends[idx]
    source = _norm(" ".join([trend["topic"]] + trend["headlines"]))
    for name in _names(hook) + _names(lead):
        if _norm(name) not in source:
            return None, f"invented name: {name}"
    src_nums = set(_numbers(" ".join([trend["topic"]] + trend["headlines"])))
    for n in _numbers(hook + " " + lead):
        if n not in src_nums:
            return None, f"invented number: {n}"
    if _norm(hook) in {_norm(h) for h in post_hooks}:
        return None, "hook already aired"
    return {"trend": trend, "edit": cand["id"], "theme": cand["theme"], "hook": hook,
            "punch": punch, "lead": lead, "question": question, "tags": tags}, ""


# ---------------------------------------------------------------------------
# plan()
# ---------------------------------------------------------------------------
def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _read_plan() -> dict | None:
    try:
        return json.loads(PLAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(plan: dict) -> None:
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _none(for_post: int, reason: str, now: dt.datetime) -> dict:
    return {"forPost": for_post, "decidedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "none": reason}


def decide(rows: list[dict], now: dt.datetime) -> dict:
    """The plan for the next post, or a {"none": reason} record. Never raises."""
    import edits
    import llm
    for_post = edits.edit_post_count(rows)
    try:
        trends = screen(fetch(now.date()))[:N_TRENDS]
        if not trends:
            return _none(for_post, "no safe trend today", now)
        cands = candidates(rows)
        if not cands:
            return _none(for_post, "the shelf is empty", now)
        if not llm.available(FEATURE):
            return _none(for_post, f"no model ({llm.reason(FEATURE)})", now)
        reply = llm.chat(system_prompt(), user_prompt(trends, cands), max_tokens=500,
                         feature=FEATURE, anthropic_model="claude-haiku-4-5-20251001")
        raw = parse_reply(reply)
        if raw is None:
            return _none(for_post, "the model's answer was not JSON", now)
        hooks = {r.get("hook", "") for r in rows if r.get("hook")}
        ok, why = validate(raw, trends, cands, hooks)
        if ok is None:
            return _none(for_post, why, now)
        import airday
        t = ok.pop("trend")
        return {"forPost": for_post, "airDay": airday.next_air_day(rows, airday.live_cap()).isoformat(),
                "decidedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trend": {"topic": t["topic"], "score": t["score"], "source": t["source"],
                          "headlines": t["headlines"]},
                **ok, "model": getattr(llm, "CF_MODEL", "") if llm.provider(FEATURE) == "cloudflare"
                else "claude-haiku-4-5"}
    except Exception as e:  # noqa: BLE001  Fama never stops a post
        return _none(for_post, f"error: {str(e)[:120]}", now)


def plan(now: dt.datetime | None = None) -> dict:
    """Plan ONCE per post: a plan for the same post decided under 20 hours ago
    is kept unchanged, whatever it says."""
    import edits
    now = now or _now()
    rows = _rows()
    for_post = edits.edit_post_count(rows)
    have = _read_plan()
    if have and have.get("forPost") == for_post:
        try:
            at = dt.datetime.fromisoformat(str(have["decidedAt"]).replace("Z", "+00:00"))
            if dt.timedelta(0) <= now - at < dt.timedelta(hours=KEEP_AGE_H):
                print(f"  [fama] kept: {describe(have)}")
                return have
        except (KeyError, ValueError):
            pass
    out = decide(rows, now)
    _write(out)
    print(f"  [fama] {describe(out)}")
    return out


def describe(p: dict) -> str:
    if p.get("none"):
        return f"no topical plan for post {p.get('forPost')}: {p['none']}"
    return (f"post {p.get('forPost')}: {p['edit']} airs on \"{p['trend']['topic']}\" "
            f"({p['trend']['source']}) with the hook \"{p['hook']}\"")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "show"
    if cmd == "plan":
        plan()
        return 0
    if cmd == "show":
        p = _read_plan()
        print(describe(p) if p else "no plan yet")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
