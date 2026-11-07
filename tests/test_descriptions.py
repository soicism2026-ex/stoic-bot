"""The owner's description style (2026-11-06, on Cicero's test 2: a viral
Short's description "as inspiration for our next shorts").

His example: three short paragraphs that talk to the viewer about his own
life, then "💬 Question: What matters more in life — talent or determination?
Share your thoughts in the comments". Every quote still to air carries its
own paragraphs and question, the question is also the channel's comment
under the Short, and the quote and its source stay in every description."""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import edits  # noqa: E402
import promo  # noqa: E402
import publish_instagram  # noqa: E402
import shelf  # noqa: E402

# Calling the viewer names, not naming a feeling: "needing help isn't
# weakness" absolves him (doctrine 5), "you're weak" shames him.
SHAME = re.compile(r"\b(?:you(?:'re| are)(?: just)?|stop being) (?:so |too )?(?:weak|lazy|soft|pathetic|"
                   r"a loser|worthless|a coward|a failure)\b")


def _fresh() -> list[dict]:
    with open(ROOT / "data" / "posts.csv", newline="", encoding="utf-8") as f:
        posts = list(csv.DictReader(f))
    aired = edits._aired_quotes(posts)
    used = edits._used(posts)
    return [q for q in edits.load() if q["id"] not in used and not edits._already_aired(q, aired)]


def test_every_quote_still_to_air_has_its_paragraphs_and_question():
    fresh = _fresh()
    assert len(fresh) >= 30                                   # the shelf is stocked
    for q in fresh:
        assert not shelf.description_problems(q), (q["id"], shelf.description_problems(q))


def test_the_words_are_kind_and_plain():
    assert SHAME.search("stop being so lazy") and not SHAME.search("needing help isn't weakness")
    for q in _fresh():
        low = (q["description"] + " " + q["question"]).lower()
        assert not SHAME.search(low), (q["id"], SHAME.search(low))   # doctrine 5: no shame
        assert not any(s in low for s in shelf.SHAME), q["id"]
        assert not re.search(r"https?://|www\.|#\w|@\w|[<>]", q["description"] + q["question"]), q["id"]


def test_the_description_follows_the_owners_example():
    q = next(q for q in _fresh())
    c = edits.as_content(q)
    d = edits.description(c)
    lead = edits.search_lead(c)                               # the search line, once the owner says yes
    if lead:
        assert d.startswith(lead + "\n\n")
        d = d[len(lead) + 2:]
    paras = d.split("\n\n")
    body = q["description"].split("\n\n")
    assert paras[:len(body)] == body                          # his layout: the paragraphs open it
    ask = paras[len(body)]
    assert ask == f"\U0001F4AC Question: {q['question']} Share your thoughts in the comments."
    assert paras[len(body) + 1] == f"“{q['quote']}”\n— {q['author']}, {q['citation']}"
    assert paras[-1] == " ".join(c["hashtags"])               # hashtags last, then the promo block
    assert c["pinned_comment"] == q["question"]               # and the same question as the comment
    assert edits.QUESTION_MARK in d                           # Cicero tells old from new by it


def test_a_quote_without_paragraphs_keeps_the_old_layout(tmp_path, monkeypatch):
    q = {"id": "x", "theme": "fear", "quote": "Q.", "author": "Seneca", "citation": "Letters 13",
         "hook": "Stop fearing.", "visuals": []}
    off = tmp_path / "off.json"
    off.write_text('{"tests": []}')
    monkeypatch.setattr(edits, "MARKETING_TESTS", off)                 # the search line off
    d = edits.description(edits.as_content(q))
    assert d.split("\n\n") == ["Stop fearing.", "Q.\n— Seneca, Letters 13", "#stoicism #motivation "
                               "#discipline #stoic #shorts"]
    assert edits.QUESTION_MARK not in d
    on = tmp_path / "on.json"
    on.write_text('{"tests": [{"id": "search-phrases", "status": "running"}]}')
    monkeypatch.setattr(edits, "MARKETING_TESTS", on)                  # on: it opens with the search too
    d = edits.description(edits.as_content(q))
    assert d.split("\n\n")[:2] == ["How to stop overthinking: Seneca's answer.", "Stop fearing."]


def test_youtube_takes_every_description(monkeypatch):
    """YouTube refuses a description over 5,000 bytes or with < or >."""
    monkeypatch.setattr(promo, "PROMO_ENABLED", True)
    for q in _fresh():
        d = edits.description(edits.as_content(q)) + promo.description_block() + "\n\nMusic: a long credit line"
        assert len(d.encode("utf-8")) < 5000 and "<" not in d and ">" not in d, q["id"]


def test_the_producer_uses_it_for_edits_only():
    src = (ROOT / "scripts" / "daily_post.py").read_text(encoding="utf-8")
    assert 'if content.get("format") == "edit":' in src
    assert "description = edits.description(content) + promo.description_block()" in src
    assert 'body=content.get("_description", "")' in src      # and Echo gets the same words


def test_instagram_gets_the_same_words():
    q = next(q for q in _fresh())
    c = edits.as_content(q)
    cap = publish_instagram.caption(c["hook"], c["quote"], c["author"], c["_citation"], c["hashtags"],
                                    body=c["_description"], question=c["_question"])
    assert cap.startswith(q["description"].split("\n\n")[0])
    assert f"Question: {q['question']}" in cap and "#shorts" not in cap
    old = publish_instagram.caption("Hook", "Q.", "Seneca", "Letters 13")
    assert old.startswith("Hook.\n\n“Q.”")              # no paragraphs: as before


def test_the_owners_example_is_kept_in_the_doctrine():
    doc = (ROOT / "data" / "doctrine.md").read_text(encoding="utf-8")
    assert "## 10. Describe it like the viral one" in doc
    assert "What matters more in life — talent or determination?" in doc
    log = (ROOT / "data" / "decisions.md").read_text(encoding="utf-8")
    assert "2026-11-06 — DESCRIPTIONS" in log
