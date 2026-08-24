"""Long-form readings — the format that can actually reach monetisation.

The Shorts path needs 3,000,000 views in 90 days; the channel does 314/day,
106x short, with reach falling 7.5x since June measured at identical video
age. The same 500-subscriber tier accepts 3,000 public watch HOURS in 12
months instead, which a 20-minute video clears at ~70 views/day.

The hard constraint on this module is that NOTHING SPOKEN IS GENERATED. Over
twenty minutes, a model asked to recite Marcus Aurelius would produce fluent,
plausible, invented philosophy on a channel whose stated rule is that quotes
are genuine public-domain text. Most of these tests exist to keep that true.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import longform as lf  # noqa: E402
import fetch_source_texts as fst  # noqa: E402


# A stand-in source: hard-wrapped like Gutenberg, with headings and numerals.
FIXTURE = """THE SECOND BOOK

I. Begin the morning by saying to thyself, I shall meet with the
busybody, the ungrateful, and the arrogant. All these things happen to
them by reason of their ignorance of what is good and evil. But I who
have seen the nature of the good, and the bad, can neither be injured
by any of them, nor can I be angry with my kinsman.

II. Whatever this is that I am, it is a little flesh and breath. Death
hangs over thee. While thou livest, while it is in thy power, be good,
and remember that all things mortal must perish and die in their hour.

III.

IV. Short then is the time which every man lives, and small the nook of
the earth where he lives; the present moment is brief, and the hour is
all that any man can lose, for the present is the only time a man
possesses and death takes nothing else from him.

V. Anger is a thing which is not in our power to avoid feeling, but the
opinion we form of the offence is in our power, and the man who is
angry at a fault is angry at what he cannot control.
"""


@pytest.fixture
def texts(tmp_path):
    (tmp_path / "meditations.txt").write_text(FIXTURE, encoding="utf-8")
    return tmp_path


# ------------------------------------------------- parsing

def test_hard_wrapped_lines_become_whole_paragraphs(texts):
    """Gutenberg wraps at ~70 columns; splitting on newlines would read as
    stuttering fragments."""
    ps = lf.load_passages("meditations", texts)
    assert ps and all("\n" not in p.text for p in ps)


def test_headings_are_not_read_aloud(texts):
    ps = lf.load_passages("meditations", texts)
    assert not any(p.text.strip().upper().startswith("THE SECOND BOOK")
                   for p in ps)


def test_section_numerals_are_stripped(texts):
    """'IV.' is an artifact of the edition, not something to say."""
    ps = lf.load_passages("meditations", texts)
    assert not any(p.text.startswith(("I.", "II.", "IV.", "V."))
                   for p in ps), [p.text[:12] for p in ps]


def test_fragments_are_dropped(texts):
    """'III.' alone is a numeral with no passage after it."""
    ps = lf.load_passages("meditations", texts)
    assert all(p.words >= lf.MIN_WORDS for p in ps)


def test_missing_source_returns_empty_not_crash(tmp_path):
    """A scheduled run must be able to fall back, not die."""
    assert lf.load_passages("nope", tmp_path) == []


# ------------------------------------------------- the no-fabrication rule

def test_every_word_comes_from_the_source_file(texts):
    """The core invariant, asserted directly."""
    source = (texts / "meditations.txt").read_text(encoding="utf-8")
    flat = " ".join(source.split()).lower()
    r = lf.build_reading("meditations", "Marcus Aurelius", "anger",
                         target_minutes=1.0, text_dir=texts)
    assert r is not None
    for p in r.passages:
        # Every passage must appear verbatim in the source (numeral aside).
        assert " ".join(p.text.split()).lower() in flat, p.text[:60]


def test_reading_body_adds_no_words_of_its_own(texts):
    r = lf.build_reading("meditations", "Marcus Aurelius", "mortality",
                         target_minutes=1.0, text_dir=texts)
    assert r is not None
    joined = "".join(r.body.split())
    assert joined == "".join("".join(p.text.split()) for p in r.passages)


# ------------------------------------------------- selection

def test_theme_selection_actually_matches_the_theme(texts):
    r = lf.build_reading("meditations", "Marcus Aurelius", "anger",
                         target_minutes=1.0, text_dir=texts)
    assert r is not None
    assert any("angry" in p.text.lower() or "anger" in p.text.lower()
               for p in r.passages)


def test_passages_are_read_in_the_order_written(texts):
    r = lf.build_reading("meditations", "Marcus Aurelius", "mortality",
                         target_minutes=1.0, text_dir=texts)
    assert r is not None
    idx = [p.index for p in r.passages]
    assert idx == sorted(idx), "a reading that jumps around sounds shuffled"


def test_returns_none_rather_than_padding_a_short_video(texts):
    """A padded 20-minute video would poison the retention this format exists
    to earn. Better to skip the run."""
    assert lf.build_reading("meditations", "Marcus Aurelius", "anger",
                            target_minutes=20.0, text_dir=texts) is None


def test_unknown_theme_yields_nothing_rather_than_random_text(texts):
    assert lf.build_reading("meditations", "Marcus Aurelius", "quantum",
                            target_minutes=1.0, text_dir=texts) is None


def test_duration_estimate_tracks_word_count(texts):
    r = lf.build_reading("meditations", "Marcus Aurelius", "time",
                         target_minutes=1.0, text_dir=texts)
    assert r is not None
    assert r.est_minutes == pytest.approx(r.word_count / lf.WORDS_PER_MIN)


def test_chapters_cover_every_passage(texts):
    r = lf.build_reading("meditations", "Marcus Aurelius", "mortality",
                         target_minutes=1.0, text_dir=texts)
    assert r is not None
    ch = lf.chapters(r, per_chapter=2)
    assert ch[0][0] == 0 and len(ch) == -(-len(r.passages) // 2)


# ------------------------------------------------- the fetcher's guards

def test_gutenberg_boilerplate_is_stripped():
    raw = ("licence blah\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\n"
           "REAL BODY\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\nfooter")
    assert fst.strip_boilerplate(raw) == "REAL BODY"


def test_a_non_gutenberg_file_is_rejected():
    """An error page saved as the text of a video is the failure mode."""
    with pytest.raises(ValueError):
        fst.strip_boilerplate("<html>404 Not Found</html>")


def test_a_truncated_download_is_rejected():
    spec = {"min_chars": 1000, "markers": []}
    with pytest.raises(ValueError, match="truncated or wrong"):
        fst.validate("x", "too short", spec)


def test_the_wrong_book_is_rejected():
    spec = {"min_chars": 1, "markers": ["MARCUS AURELIUS"]}
    with pytest.raises(ValueError, match="not the book it claims"):
        fst.validate("x", "the complete works of somebody else", spec)


def test_a_correct_download_passes():
    spec = {"min_chars": 5, "markers": ["marcus"]}
    fst.validate("x", "a text mentioning Marcus at length", spec)


# ------------------------------------------------- the upload path
#
# The Shorts/long-form distinction IS the strategy. Shorts watch time does not
# count toward the 3,000-hour threshold; long-form does. Publishing one of
# these as a Short would file it in the category that cannot earn what it was
# made to earn.

import publish  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402


def _fake_upload(monkeypatch, capture):
    def fake_service():
        yt = MagicMock()
        def insert(part, body, media_body):
            capture["body"] = body
            req = MagicMock()
            req.next_chunk.return_value = (None, {"id": "VID123"})
            return req
        yt.videos.return_value.insert.side_effect = insert
        return yt
    monkeypatch.setattr(publish, "_service", fake_service)


def test_longform_is_not_tagged_as_a_short(tmp_path, monkeypatch):
    cap = {}
    _fake_upload(monkeypatch, cap)
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    with patch("googleapiclient.http.MediaFileUpload", MagicMock()):
        out = publish.publish_longform(v, "Marcus on Anger", "A reading.", ["stoic"])
    assert "#shorts" not in cap["body"]["snippet"]["description"].lower()
    assert "#shorts" not in cap["body"]["snippet"]["title"].lower()
    assert out["shorts"] is False


def test_longform_gets_a_watch_url_not_a_shorts_url(tmp_path, monkeypatch):
    cap = {}
    _fake_upload(monkeypatch, cap)
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    with patch("googleapiclient.http.MediaFileUpload", MagicMock()):
        out = publish.publish_longform(v, "T", "D", [])
    assert out["url"] == "https://youtube.com/watch?v=VID123"


def test_shorts_path_is_unchanged(tmp_path, monkeypatch):
    """The Shorts pipeline is the live channel — refactoring must not move it."""
    cap = {}
    _fake_upload(monkeypatch, cap)
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    with patch("googleapiclient.http.MediaFileUpload", MagicMock()):
        out = publish.publish_short(v, "T", "D", ["a"])
    assert "#Shorts" in cap["body"]["snippet"]["description"]
    assert out["url"] == "https://youtube.com/shorts/VID123"
    assert out["shorts"] is True
