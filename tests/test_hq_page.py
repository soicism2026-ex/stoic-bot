"""The HQ page's crew states (owner 2026-10-23: "Why is everybody on call? Get them working").

The page is one HTML file published as a claude.ai artifact, so these read its
source: the rules that decide what the owner sees in the lineup.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "hq" / "forged-hq.html").read_text(encoding="utf-8")


def test_a_finished_shift_reads_done_not_asleep():
    assert 'if (status === "idle" && shiftDone(b)) { status = "done";' in PAGE
    assert 'SHIFT_PILL[b.id] || "Done for today"' in PAGE
    # the producer is done when today's cap is reached, the reporter weekly
    assert 'if (b.id === "producer") return !!(np && np.cap && np.postsToday >= np.cap);' in PAGE
    assert 'if (b.id === "reporter") return within(24 * 7);' in PAGE


def test_work_waiting_on_the_owner_shows_needs_you():
    assert 'const asksFor = (id) => S.asks.filter((a) => a.status === "open" && a.crew === id);' in PAGE
    assert 'status = "waiting"' in PAGE and '"Waiting on you: "' in PAGE


def test_a_message_claude_picked_up_is_not_flagged_as_lost():
    assert 'const pickedUp = (n) => n.status === "done" || n.status === "working";' in PAGE
    assert "Claude is on it" in PAGE
    assert "!pickedUp(n) && Date.now()" in PAGE


def test_the_librarian_stands_in_the_lineup():
    assert "S.config.librarian === t.id" in PAGE and "librarianAgent()" in PAGE
    assert re.search(r'librarian: \{ name: "Varro", title: "Librarian"', PAGE)


def test_every_crew_sprite_is_a_clean_16_by_16_grid():
    pal = json.loads(re.search(r"const PAL = (\{.*?\});", PAGE).group(1))
    block = re.search(r"const SPRITES = \{(.*?)\n  \};", PAGE, re.S).group(1)
    sprites = dict(re.findall(r"(\w+): (\[.*?\]),", block))
    assert {"chief", "smith", "owl", "general", "scribe", "painter", "bard", "librarian"} <= set(sprites)
    for name, rows in sprites.items():
        rows = json.loads(rows)
        assert len(rows) == 16 and all(len(r) == 16 for r in rows), name
        assert set("".join(rows)) - {"."} <= set(pal), name
    crew_sprites = set(re.findall(r'sprite: "(\w+)"', PAGE))
    assert crew_sprites <= set(sprites), crew_sprites - set(sprites)


def test_a_crew_member_on_a_helper_shift_lights_up_in_place():
    """Varro's restock and Orpheus's music search run as Claude helpers: the
    lineup shows that crew member working, not a second, anonymous helper."""
    assert "const CREW_HELPERS = /^(varro|orpheus)$/i;" in PAGE
    assert "const helping = CREW[crew] && CREW[crew].name ? onShift(CREW[crew].name) : null;" in PAGE
    assert '.filter((h) => !CREW_HELPERS.test(h.name || ""))' in PAGE
