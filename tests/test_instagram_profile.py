"""The Instagram profile the owner pastes in (HQ 2026-11-10: "Write a bio for
the instagram"), and the "link in bio" line Reels carry only once the link is
there and he said yes (HQ ask instagram-bio)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import promo  # noqa: E402
import publish_instagram as ig  # noqa: E402

PROFILE = json.loads((ROOT / "data" / "instagram_profile.json").read_text(encoding="utf-8"))


def _utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def test_the_profile_fits_instagrams_limits():
    assert 0 < _utf16(PROFILE["bio"]) <= 150            # Instagram's bio limit
    assert 0 < len(PROFILE["name"]) <= 64               # and the name's
    assert not re.search(r"https?://|www\.|\.com", PROFILE["bio"])   # bio text links aren't tappable
    assert "#" not in PROFILE["bio"]


def test_the_links_are_the_live_ones():
    urls = [x["url"] for x in PROFILE["links"]]
    assert urls[0] == promo.PROMO_URL                   # the journal first: it shows under the bio
    assert "youtube.com/@forged.in.stoicism" in urls[1]
    assert all(x["title"] for x in PROFILE["links"])


def test_the_bio_names_only_philosophers_we_quote():
    quotes = json.loads((ROOT / "data" / "edit_quotes.json").read_text(encoding="utf-8"))
    authors = {q["author"] for q in quotes}
    for name in ("Marcus Aurelius", "Seneca", "Epictetus"):
        assert name in PROFILE["bio"] and name in authors


def _profile(tmp_path, monkeypatch, **flags):
    p = tmp_path / "instagram_profile.json"
    p.write_text(json.dumps({**PROFILE, **flags}))
    monkeypatch.setattr(ig, "PROFILE", p)


def _caption():
    return ig.caption("Snapped over something small", "Q.", "Seneca", "On Anger", ["#stoicism", "#seneca"])


def test_reels_say_nothing_about_the_bio_until_both_are_true(tmp_path, monkeypatch):
    _profile(tmp_path, monkeypatch, onProfile=False, reelsPointToBio=False)
    assert "link in bio" not in _caption()
    _profile(tmp_path, monkeypatch, onProfile=False, reelsPointToBio=True)   # said yes, not pasted yet
    assert "link in bio" not in _caption()
    _profile(tmp_path, monkeypatch, onProfile=True, reelsPointToBio=False)   # pasted, said no
    assert "link in bio" not in _caption()


def test_once_on_every_reel_points_to_the_journal(tmp_path, monkeypatch):
    _profile(tmp_path, monkeypatch, onProfile=True, reelsPointToBio=True)
    c = _caption()
    assert ig.BIO_LINE in c
    assert c.index(ig.FOLLOW_LINE) < c.index(ig.BIO_LINE) < c.index("#stoicism")


def test_a_missing_or_broken_profile_file_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "PROFILE", tmp_path / "nope.json")
    assert not ig.points_to_bio()
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert not ig.points_to_bio(bad)
