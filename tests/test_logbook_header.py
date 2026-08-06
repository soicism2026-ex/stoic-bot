"""posts.csv is the single source of truth for every rotation in the bot.

csv.DictReader keys off the HEADER, not the data. When FIELDS grew (7 -> 12
columns) the header on disk was never rewritten, so five rotation systems went
blind at once — hook dedup, rule numbering, voice LRU, music LRU, format
history — with no error anywhere. These tests lock the repair in.
"""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logbook  # noqa: E402


@pytest.fixture
def log(tmp_path, monkeypatch):
    p = tmp_path / "posts.csv"
    monkeypatch.setattr(logbook, "LOG", p)
    return p


OLD_HEADER = "date,theme,author,quote,caption,video_url,video_id\n"
FULL_ROW = ('2026-08-06,fear,Seneca,"A quote.",cap,https://y/1,vid1,'
            'Brian,cinematic_score,"Rule 7: Do the thing.",exp,rule\n')


def _publish(vid="vid9"):
    return {"url": f"https://youtube.com/shorts/{vid}", "video_id": vid}


# ------------------------------------------------------------------- repair

def test_repairs_stale_header(log):
    log.write_text(OLD_HEADER + FULL_ROW, encoding="utf-8")
    assert logbook._repair_header() is True
    assert log.read_text(encoding="utf-8").splitlines()[0] == ",".join(logbook.FIELDS)


def test_repair_is_a_noop_when_header_is_current(log):
    log.write_text(",".join(logbook.FIELDS) + "\n" + FULL_ROW, encoding="utf-8")
    before = log.read_text(encoding="utf-8")
    assert logbook._repair_header() is False
    assert log.read_text(encoding="utf-8") == before


def test_repair_never_touches_post_rows(log):
    """data/posts.csv rows are sacred — the invariant says never delete one."""
    rows = FULL_ROW * 5
    log.write_text(OLD_HEADER + rows, encoding="utf-8")
    logbook._repair_header()
    assert log.read_text(encoding="utf-8").split("\n", 1)[1] == rows


def test_repair_handles_missing_and_empty_file(log):
    assert logbook._repair_header() is False      # does not exist
    log.write_text("", encoding="utf-8")
    assert logbook._repair_header() is False      # exists but empty


def test_repair_survives_quoted_commas_in_rows(log):
    """Captions contain commas and newlines-turned-slashes; must not corrupt."""
    row = '2026-08-06,fear,Seneca,"One, two, three",cap,u,v,Brian,t,"Rule 3: X",e,rule\n'
    log.write_text(OLD_HEADER + row, encoding="utf-8")
    logbook._repair_header()
    parsed = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
    assert parsed[0]["quote"] == "One, two, three"
    assert parsed[0]["hook"] == "Rule 3: X"


# --------------------------------------------------- the readers, end to end

def test_rotation_columns_are_readable_after_repair(log):
    log.write_text(OLD_HEADER + FULL_ROW, encoding="utf-8")
    logbook._repair_header()
    row = list(csv.DictReader(log.open(newline="", encoding="utf-8")))[0]
    # Every column the rotations depend on:
    assert row["hook"] == "Rule 7: Do the thing."
    assert row["voice_name"] == "Brian"
    assert row["music_track"] == "cinematic_score"
    assert row["format"] == "rule"


def test_short_legacy_rows_still_parse(log):
    """Early rows only have 7 fields. They must read as None, not explode."""
    log.write_text(OLD_HEADER + "2026-06-05,ego,Seneca,q,c,u,v\n", encoding="utf-8")
    logbook._repair_header()
    row = list(csv.DictReader(log.open(newline="", encoding="utf-8")))[0]
    assert row["date"] == "2026-06-05"
    assert not row["hook"]          # None or "" — falsy either way for the filters


# ------------------------------------------------------------ log_post wiring

def test_log_post_repairs_before_appending(log):
    log.write_text(OLD_HEADER + FULL_ROW, encoding="utf-8")
    logbook.log_post("2026-08-07", "anger", "q", "Epictetus", "cap", _publish(),
                     voice_name="Christopher", music_track="dark_ambient",
                     hook="Rule 12: Wait.", experiment="e", content_format="rule")
    rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
    assert len(rows) == 2
    assert rows[1]["hook"] == "Rule 12: Wait."
    assert rows[1]["voice_name"] == "Christopher"


def test_log_post_writes_header_on_a_new_file(log):
    logbook.log_post("2026-08-07", "anger", "q", "Epictetus", "cap", _publish(),
                     hook="h", content_format="rule")
    assert log.read_text(encoding="utf-8").splitlines()[0] == ",".join(logbook.FIELDS)


def test_adding_a_column_self_heals(log, monkeypatch):
    """The exact way this broke: FIELDS grows, header on disk does not."""
    log.write_text(",".join(logbook.FIELDS) + "\n" + FULL_ROW, encoding="utf-8")
    monkeypatch.setattr(logbook, "FIELDS", logbook.FIELDS + ["retention"])
    logbook._repair_header()
    assert "retention" in log.read_text(encoding="utf-8").splitlines()[0]


# ----------------------------------------------- the actual production file

def test_live_posts_csv_header_matches_fields():
    """Guards the committed data file itself, not just the code."""
    live = ROOT / "data" / "posts.csv"
    if not live.exists():
        pytest.skip("no posts.csv in this checkout")
    header = next(csv.reader(live.open(newline="", encoding="utf-8")))
    assert header == logbook.FIELDS, (
        "data/posts.csv header has drifted from logbook.FIELDS — every rotation "
        "that reads those columns is silently blind")
