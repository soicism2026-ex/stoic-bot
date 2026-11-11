"""The quote shelf: how many days of verified edits are left, and the one door
new quotes come in through.

    python scripts/shelf.py status            # runway: fresh quotes, days left, per author
    python scripts/shelf.py status --json     # the same, for scripts/hq_snapshot.py
    python scripts/shelf.py winners           # aired edits by views: write more like the top
    python scripts/shelf.py check new.json    # every rule a new quote must pass; writes nothing
    python scripts/shelf.py add new.json      # check, then append the ones that pass

Why it exists (2026-10-23): the edit bank had 36 unused quotes, 18 days at 2
posts a day; the story bank had 1; and the last fallback, generated content,
needs Anthropic API credit the account did not have. Nothing watched that
runway, so the channel would have gone quiet around 2026-11-10 while every bot
still reported success. The Librarian, a weekly Claude shift (CLAUDE.md "Quote
shelf"), keeps it at TARGET_DAYS or more; the HQ shows the runway and warns
below WARN_DAYS.

A new quote passes only if ALL of these hold (each one is a past failure or a
standing rule):
  * verbatim in the public-domain source, and cited where the source has it
    (scripts/validate_quotes.py; the bank once cited Letter 104 for a line
    that is only in Letter 28)
  * never aired in any format, and not overlapping a quote already shelved
    (rising_to_work re-aired a 2026-09-03 quote on 2026-10-19)
  * short enough for a ~15 s edit, with a hook of at most 9 words
  * stock searches are short keywords, and people shots ask for a man
    (doctrine §1; tests/test_edits.py)
  * no shame in the hook (doctrine §5)
  * a description and a question in the owner's style (2026-11-06, a viral
    Short's description he sent "as inspiration for our next shorts"): 2-3
    short paragraphs that speak to the viewer about his own life, and one
    question for the comments; no links, hashtags or shame
  * optional `scenes` (Plutarch, docs/scene_writing.md): 6-8 paintable shots,
    validated by scene_problems(). The gold words for the type live in ONE
    place, data/edit_type.json (Callimachus; tests/test_edit_type.py)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import airday  # noqa: E402
import edits  # noqa: E402
import prompt_lint  # noqa: E402
import validate_quotes as vq  # noqa: E402

TARGET_DAYS = 30      # the Librarian tops the shelf up to this
WARN_DAYS = 14        # the HQ raises an alert below this

AUTHORS = {"Marcus Aurelius", "Seneca", "Epictetus"}
THEMES = {"discipline", "control", "resilience", "time", "fear", "desire", "anger",
          "mortality", "ego", "friendship", "adversity", "duty"}
CITATION = {
    "Marcus Aurelius": re.compile(r"^Meditations \d{1,2}\.\d{1,3}, trans\. George Long$"),
    "Seneca": re.compile(r"^Moral Letters \d{1,3}, trans\. Richard M\. Gummere$"),
    "Epictetus": re.compile(r"^(?:Discourses [IV]{1,3}\.\d{1,2}|Enchiridion \d{1,2}), "
                            r"trans\. George Long$"),
}
KEYS = ["id", "author", "citation", "quote", "hook", "theme", "description", "question", "visuals"]
# Plutarch's scene-writer fields (docs/scene_writing.md): optional, in this order
# after KEYS. Older quotes have none; the painter and the typographer read them.
SCENE_KEYS = ["scenes"]
# The same words tests/test_edits.py checks: these return women's fitness
# footage unless the query names a man.
PEOPLE = {"boxer", "boxing", "training", "weight", "weightlifting", "lifting",
          "running", "runner", "eyes", "breathing", "punching"}
SHAME = ("pathetic", "loser", "worthless", "coward", "nobody is coming",
         "nobody's coming", "no one is coming", "no one's coming")
QUOTE_WORDS = (3, 36)   # "Everywhere means nowhere." (3) to the bank's longest (36, ~13 s read)
DESC_WORDS = (35, 95)   # the owner's example is 82 words in 3 paragraphs
QUESTION_CHARS = 100    # one line in the comments
TAGS = re.compile(r"https?://|www\.|#\w|@\w|[<>]")   # YouTube refuses < and >


def _rows() -> list[dict]:
    p = ROOT / "data" / "posts.csv"
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def posts_per_day() -> int:
    return airday.live_cap()


def _fresh(bank: list[dict], rows: list[dict]) -> list[dict]:
    used, jammed, aired = edits._used(rows), edits.jammed_ids(), edits._aired_quotes(rows)
    return [q for q in bank if q["id"] not in used and q["id"] not in jammed
            and not edits._already_aired(q, aired)]


def status(today: dt.date | None = None, rows: list[dict] | None = None,
           bank: list[dict] | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    rows = _rows() if rows is None else rows
    bank = edits.load() if bank is None else bank
    fresh = _fresh(bank, rows)
    per_day = posts_per_day()
    days = len(fresh) // per_day
    by_author = {a: sum(1 for q in fresh if q["author"] == a) for a in sorted(AUTHORS)}
    return {
        "left": len(fresh),
        "perDay": per_day,
        "days": days,
        "runsOut": (today + dt.timedelta(days=days)).isoformat(),
        "byAuthor": by_author,
        "target": TARGET_DAYS,
        "warn": WARN_DAYS,
        "low": days < WARN_DAYS,
        "toTarget": max(0, TARGET_DAYS * per_day - len(fresh)),
    }


def _norm(t: str) -> str:
    return edits._norm(t)


def description_problems(q: dict) -> list[str]:
    """What is wrong with a quote's description and question (empty = fine):
    the layout of the owner's example, short, and kind (doctrine §5)."""
    out = []
    d, ask = q.get("description"), q.get("question")
    if not isinstance(d, str) or not d.strip():
        out.append("description: 2-3 short paragraphs about the viewer's own life")
    else:
        paras = d.split("\n\n")
        if not 2 <= len(paras) <= 3 or any(not p.strip() or "\n" in p for p in paras):
            out.append("description: 2-3 paragraphs, each one line, a blank line between them")
        n = len(d.split())
        if not DESC_WORDS[0] <= n <= DESC_WORDS[1]:
            out.append(f"description is {n} words; {DESC_WORDS[0]}-{DESC_WORDS[1]}")
        if TAGS.search(d):
            out.append("description: no links, hashtags, @names, < or > (the hashtags and links are added)")
    if not isinstance(ask, str) or not ask.strip():
        out.append("question: one question for the comments")
    else:
        if not ask.endswith("?") or "\n" in ask or len(ask) > QUESTION_CHARS or len(ask.split()) < 4:
            out.append(f"question: one line, 4+ words, at most {QUESTION_CHARS} characters, ending in '?'")
        if TAGS.search(ask):
            out.append("question: no links, hashtags, @names, < or >")
    text = f"{d if isinstance(d, str) else ''} {ask if isinstance(ask, str) else ''}".lower()
    if any(s in text for s in SHAME):
        out.append("description or question shames the viewer (doctrine §5)")
    return out


# --- scene fields (docs/scene_writing.md) -----------------------------------
CAST = {"marcus", "seneca", "epictetus", "man"}
SCENE_COUNT = (6, 8)
SCENE_WORDS = (8, 45)
# The code adds the look (colour, cinematic, painterly); a shot that names one fights it.
STYLE_WORDS = re.compile(
    r"\b(cinematic|4k|8k|hdr|photo-?realistic|hyper-?realistic|painting|painterly|"
    r"illustration|artstation|render(ed|ing)?|film grain|grainy|black and white|monochrome|"
    r"sepia|bokeh|lens flare|masterpiece|highly detailed|style of)\b", re.I)
# "not red" renders red: a shot says what is there, never what is not.
NEGATION = re.compile(r"\b(no|not|without|never|nor|none|nothing|nobody|neither|\w+n't)\b", re.I)
# The shot must name a physical light source (doctrine §6; the painter needs one).
LIGHT = re.compile(
    r"\b(lamps?|lamplight|lamplit|torch(es|light|lit)?|golden hour|moonlit|candles?|candlelight|firelight|fire|brazier|hearth|"
    r"embers|flames?|moonlight|sun|sunrise|sunset|sunlight|sunlit|dawn|dusk|daylight|noon|"
    r"overcast|window|doorway|skylight|lightning)\b", re.I)
STATUE_OPENER = re.compile(r"\b(statue|bust|sculpture|monument)\b", re.I)
TOKEN = re.compile(r"\{(\w+)\}")


def scene_problems(q: dict) -> list[str]:
    """Rules for `scenes` when present (optional: older quotes have none)."""
    out = []
    if "scenes" not in q:
        return out
    sc = q.get("scenes")
    if sc is not None:
        if not isinstance(sc, list) or not all(isinstance(s, str) for s in sc):
            out.append("scenes: a list of strings")
        else:
            lo, hi = SCENE_COUNT
            if not lo <= len(sc) <= hi:
                out.append(f"scenes: {lo}-{hi} shots, got {len(sc)}")
            if len({s.strip().lower() for s in sc}) != len(sc):
                out.append("scenes: two shots are identical")
            for i, s in enumerate(sc, 1):
                tag = f"scene {i}"
                n = len(s.split())
                if not SCENE_WORDS[0] <= n <= SCENE_WORDS[1]:
                    out.append(f"{tag}: {n} words; one paintable shot is {SCENE_WORDS[0]}-{SCENE_WORDS[1]}")
                toks = TOKEN.findall(s)
                bad = sorted({t for t in toks if t not in CAST})
                if bad:
                    out.append(f"{tag}: unknown cast token {bad}; use {sorted('{' + c + '}' for c in CAST)}")
                if len(toks) > 2:
                    out.append(f"{tag}: more than two people ({len(toks)}) in one shot")
                plain = TOKEN.sub(" ", s)
                if re.search(r"[{}]", plain):
                    out.append(f"{tag}: stray brace")
                m = STYLE_WORDS.search(plain)
                if m:
                    out.append(f"{tag}: style word '{m.group(0)}': the code adds the look")
                m = NEGATION.search(plain)
                if m:
                    out.append(f"{tag}: negation '{m.group(0)}': say what is there, not what is not")
                if prompt_lint._has(prompt_lint.TEXT_ASK, plain):
                    out.append(f"{tag}: asks for writing, signs or words: image models garble letters")
                for a in prompt_lint.ANACHRONISMS:
                    if re.search(r"\b" + re.escape(a) + r"\b", plain, re.I):
                        out.append(f"{tag}: '{a}' did not exist in the ancient world")
                if not LIGHT.search(plain):
                    out.append(f"{tag}: name a physical light source (oil lamp, torchlight, dawn, overcast noon...)")
                if i == 1 and STATUE_OPENER.search(plain):
                    out.append("scene 1: the stopper is a person in a situation, never a statue")
    return out


def problems(q: dict, bank: list[dict], rows: list[dict], batch_ids: set | None = None) -> list[str]:
    """Every rule this candidate breaks; an empty list means it may go on the shelf."""
    out = []
    if list(q.keys()) != KEYS + [k for k in SCENE_KEYS if k in q]:
        out.append(f"keys must be exactly {KEYS} in that order (then optionally {SCENE_KEYS})")
        if not all(k in q for k in KEYS):
            return out
    qid = q["id"]
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", qid or ""):
        out.append("id: lowercase words joined by underscores")
    if qid in {b["id"] for b in bank} or (batch_ids and qid in batch_ids):
        out.append("id already taken")
    if q["author"] not in AUTHORS:
        out.append(f"author must be one of {sorted(AUTHORS)}")
        return out
    if not CITATION[q["author"]].match(q["citation"] or ""):
        out.append("citation format, e.g. 'Meditations 4.24, trans. George Long', "
                   "'Moral Letters 28, trans. Richard M. Gummere', "
                   "'Discourses II.1, trans. George Long' or 'Enchiridion 5, trans. George Long'")
    if vq.check(q["quote"], q["author"]) != "ok":
        out.append("quote is not word for word in the source text")
    else:
        c = vq.check_citation(q["quote"], q["author"], q["citation"])
        if c != "ok":
            out.append(f"citation: {c if c.startswith('WRONG') else 'cannot be located in the source'}")
    n = len(q["quote"].split())
    if not QUOTE_WORDS[0] <= n <= QUOTE_WORDS[1]:
        out.append(f"quote is {n} words; an edit holds {QUOTE_WORDS[0]}-{QUOTE_WORDS[1]}")
    if edits._already_aired(q, edits._aired_quotes(rows)):
        out.append("this quote already aired")
    key = _norm(q["quote"])
    for b in bank:
        other = _norm(b["quote"])
        if key[:50] in other or other[:50] in key:
            out.append(f"overlaps the shelved quote '{b['id']}'")
            break
    hw = len(q["hook"].split())
    if not 2 <= hw <= 9:
        out.append(f"hook is {hw} words; 2-9")
    if any(s in q["hook"].lower() for s in SHAME):
        out.append("hook shames the viewer (doctrine §5)")
    if q["theme"] not in THEMES:
        out.append(f"theme must be one of {sorted(THEMES)}")
    out += description_problems(q)
    out += scene_problems(q)
    vis = q["visuals"]
    if not isinstance(vis, list) or not 6 <= len(vis) <= 10:
        out.append("visuals: 6-10 shots")
        return out
    stills = [v for v in vis if v.startswith("still:")]
    if not 1 <= len(stills) <= 3:
        out.append("visuals: 1-3 'still:' shots, the rest stock video")
    for v in vis:
        if v.startswith("still:"):
            continue
        if len(v.split()) > 3:
            out.append(f"stock search '{v}' is over 3 words: Pixabay matches tags, not sentences")
        if PEOPLE & set(v.split()) and v.split()[0] not in ("man", "men", "old"):
            out.append(f"stock search '{v}' shows people: start it with 'man'")
    return out


def check(cands: list[dict], bank: list[dict] | None = None,
          rows: list[dict] | None = None) -> tuple[list[dict], list[tuple[str, list[str]]]]:
    bank = edits.load() if bank is None else bank
    rows = _rows() if rows is None else rows
    good, bad, seen = [], [], set()
    for q in cands:
        why = problems(q, bank + good, rows, seen)
        seen.add(q.get("id"))
        if why:
            bad.append((q.get("id", "?"), why))
        else:
            good.append(q)
    return good, bad


def winners(rows: list[dict] | None = None, stats: list[dict] | None = None,
            now: dt.datetime | None = None, days: int = 21, min_age_hours: int = 48) -> list[dict]:
    """Aired edits from the last `days`, at least `min_age_hours` old (views
    settle in the first two days), most viewed first: doctrine §4, multiply
    the winner. Reach grew over October, so compare within this window only."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = _rows() if rows is None else rows
    if stats is None:
        p = ROOT / "data" / "analytics.csv"
        with open(p, newline="", encoding="utf-8") as fh:
            stats = list(csv.DictReader(fh))
    latest: dict[str, dict] = {}
    for a in stats:
        vid = a.get("video_id")
        if vid and (vid not in latest or (a.get("pulled_on") or "") >= (latest[vid].get("pulled_on") or "")):
            latest[vid] = a
    bank = {q["id"]: q for q in edits.load()}
    out = []
    for r in rows:
        exp = r.get("experiment") or ""
        a = latest.get(r.get("video_id") or "")
        if not exp.startswith("edit:") or not a or not a.get("published_at"):
            continue
        pub = dt.datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
        age = (now - pub).total_seconds() / 3600
        if age < min_age_hours or age > days * 24:
            continue
        eid = exp.removeprefix("edit:")
        q = bank.get(eid, {})
        out.append({"id": eid, "date": r.get("date"), "author": r.get("author"),
                    "theme": q.get("theme") or r.get("theme"), "hook": q.get("hook") or r.get("hook"),
                    "views": int(float(a.get("views") or 0))})
    return sorted(out, key=lambda x: -x["views"])


def save(bank: list[dict]) -> None:
    # The file's own format (indent 1, real UTF-8, trailing newline), so a
    # top-up diff shows only the new entries.
    edits.BANK.write_text(json.dumps(bank, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    sub.add_parser("winners")
    for name in ("check", "add"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
    a = ap.parse_args()

    if a.cmd == "status":
        st = status()
        if a.json:
            print(json.dumps(st))
        else:
            by = ", ".join(f"{k} {v}" for k, v in st["byAuthor"].items())
            print(f"{st['left']} fresh quotes = {st['days']} days at {st['perDay']} a day "
                  f"(runs out {st['runsOut']}). By author: {by}.")
            if st["toTarget"]:
                print(f"{st['toTarget']} more needed for {st['target']} days.")
            if st["low"]:
                print(f"LOW: under {st['warn']} days.")
        return 0

    if a.cmd == "winners":
        for w in winners():
            print(f"{w['views']:>6}  {w['date']}  {w['author'][:9]:9}  {w['theme']:10}  {w['hook']}")
        return 0

    cands = json.loads(a.file.read_text(encoding="utf-8"))
    if isinstance(cands, dict):
        cands = [cands]
    good, bad = check(cands)
    for qid, why in bad:
        print(f"REJECT {qid}: " + "; ".join(why))
    print(f"{len(good)} of {len(cands)} pass")
    if a.cmd == "add" and good:
        save(edits.load() + good)
        print(f"added {len(good)} to {edits.BANK.relative_to(ROOT)}")
        print(json.dumps(status()))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
