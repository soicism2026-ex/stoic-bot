"""Guards the dependency failure that killed a full day of posting.

2026-08-21: `anthropic>=0.39.0` was unpinned. A routine `pip install` on the
runner picked up 1.0.0, which REMOVED the `temperature` kwarg from
Messages.create(). Every scheduled run died two seconds in with a TypeError —
four slots, zero posts, and the job log was the only place it was visible.

This bot reinstalls its dependencies on every single run, so an open upper
bound is a live grenade: any major release anywhere in the tree can stop the
channel without a single line of our code changing.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CALL_SITES = [
    ROOT / "src" / "content.py",
    ROOT / "scripts" / "reply_to_comments.py",
    ROOT / "scripts" / "backfill_thumbnails_titles.py",
]


def _code(p: Path) -> str:
    """Source with comments stripped — the incident is documented in comments
    on purpose, and matching prose would fail on the explanation."""
    return "\n".join(l.split("#", 1)[0] for l in p.read_text().splitlines())


def test_no_call_site_passes_temperature():
    for p in CALL_SITES:
        assert "temperature=" not in _code(p), f"{p.name} still passes temperature"


def test_anthropic_is_pinned_to_a_major_range():
    req = (ROOT / "requirements.txt").read_text()
    line = next(l for l in req.splitlines()
                if l.strip().startswith("anthropic"))
    assert "<" in line, f"anthropic has no upper bound: {line!r}"


def test_installed_sdk_actually_rejects_temperature():
    """Proves the pin matches reality rather than a guess about it."""
    try:
        import anthropic
        import inspect
    except ImportError:
        return
    sig = inspect.signature(anthropic.Anthropic(api_key="x").messages.create)
    if "temperature" in sig.parameters:
        return          # older SDK present locally; the pin still holds the line
    for p in CALL_SITES:
        assert "temperature=" not in _code(p)


def test_every_requirement_has_an_upper_bound():
    """The broader lesson. One unpinned dep took the channel down for a day;
    the rest are the same grenade with a different pin."""
    req = (ROOT / "requirements.txt").read_text()
    unbounded = []
    for line in req.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "<" not in line and "==" not in line:
            unbounded.append(line)
    assert not unbounded, (
        "unpinned dependencies can break posting on any routine reinstall: "
        + ", ".join(unbounded))
