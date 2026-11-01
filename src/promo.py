"""
Product promo injection for YouTube Shorts uploads.

When PROMO_ENABLED=1, appends a configurable CTA to every video description
and optionally posts a promo comment after upload (PROMO_COMMENT=1).

All copy lives in env vars so you can update product name, pitch, URL, or
CTA copy without touching any logic.

PROMO_CTA_VARIATIONS: pipe-delimited (|) list of CTA strings that rotate
  deterministically by date. If not set, the built-in default is used (the
  owner's own line since 2026-11-01).
  Each variation should include {url} or the full URL literally.

Set PROMO_ENABLED=0 to disable all promo behaviour without code changes.

The CTA strings are the only copy knob. (There used to be a PROMO_PITCH
env var too; nothing ever read it, so editing it silently did nothing.
It is gone — edit PROMO_CTA_VARIATIONS or _DEFAULT_CTAS instead.)
"""
import os
from datetime import date

PROMO_ENABLED = os.environ.get("PROMO_ENABLED", "0") not in ("0", "false", "False")
PROMO_COMMENT_ENABLED = os.environ.get("PROMO_COMMENT", "1") not in ("0", "false", "False")

PROMO_PRODUCT_NAME = os.environ.get("PROMO_PRODUCT_NAME", "The Stoic Reset")
PROMO_URL = os.environ.get("PROMO_URL", "https://soicism.gumroad.com/l/cslosv")

_DEFAULT_CTAS = [
    # The owner's own line (HQ, 2026-11-01): the journal is a paid product now
    # (C$5.99 on Gumroad, about US$4.29), so the three old lines, which all
    # said "free", went out. Evergreen only: these strings ship in the
    # description of every video and stay live forever, so a deadline ("only
    # for June", "this month only") becomes a lie the moment the month turns.
    # tests/test_promo.py enforces both.
    "Try our 30-Day Guided Journal ONLY $5.99 - {url}",
]


def _cta_list() -> list[str]:
    """Return the active list of CTA strings, with {url} already substituted."""
    raw = os.environ.get("PROMO_CTA_VARIATIONS", "").strip()
    if raw:
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if parts:
            return parts
    return [c.format(url=PROMO_URL) for c in _DEFAULT_CTAS]


def pick_cta() -> str:
    """Return today's CTA variation, rotating through all options by calendar date."""
    ctas = _cta_list()
    return ctas[date.today().toordinal() % len(ctas)]


def description_block() -> str:
    """Promo block to append to the video description.

    Returns an empty string when PROMO_ENABLED is falsy so callers can
    unconditionally concatenate without an if-check.
    """
    if not PROMO_ENABLED:
        return ""
    return f"\n\n---\n{pick_cta()}"


def refresh(description: str) -> str:
    """The description with today's CTA in place of the promo block it was
    written with. A backup is rendered weeks before it airs: the bank still
    carried "FREE this month only" and "free, but only for June" on
    2026-11-01, when the journal cost C$5.99."""
    return description.split("\n\n---\n", 1)[0] + description_block()


def comment_text() -> str:
    """Promo comment text to post after upload.

    Returns an empty string when disabled (PROMO_ENABLED=0 or PROMO_COMMENT=0).
    """
    if not PROMO_ENABLED or not PROMO_COMMENT_ENABLED:
        return ""
    return pick_cta()
