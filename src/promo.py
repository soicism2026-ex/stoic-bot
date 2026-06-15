"""
Product promo injection for YouTube Shorts uploads.

When PROMO_ENABLED=1, appends a configurable CTA to every video description
and optionally posts a promo comment after upload (PROMO_COMMENT=1).

All copy lives in env vars so you can update product name, pitch, URL, or
CTA copy without touching any logic.

PROMO_CTA_VARIATIONS: pipe-delimited (|) list of 3–5 CTA strings that rotate
  deterministically by date. If not set, three built-in defaults are used.
  Each variation should include {url} or the full URL literally.

Set PROMO_ENABLED=0 to disable all promo behaviour without code changes.
"""
import os
from datetime import date

PROMO_ENABLED = os.environ.get("PROMO_ENABLED", "0") not in ("0", "false", "False")
PROMO_COMMENT_ENABLED = os.environ.get("PROMO_COMMENT", "1") not in ("0", "false", "False")

PROMO_PRODUCT_NAME = os.environ.get("PROMO_PRODUCT_NAME", "The Stoic Reset")
PROMO_PITCH = os.environ.get(
    "PROMO_PITCH",
    "FREE this month only — The Stoic Reset, my 30-day Stoic journal",
)
PROMO_URL = os.environ.get("PROMO_URL", "https://soicism.gumroad.com/l/cslosv")

_DEFAULT_CTAS = [
    "📓 FREE this month only — The Stoic Reset, my 30-day Stoic journal. Grab it before the price goes up:\n{url}",
    "📖 I'm giving away The Stoic Reset journal for free — but only for June. 30 days to rebuild your mindset:\n{url}",
    "🪨 The Stoic Reset is free right now. A 30-day journal to put quotes like this into daily practice:\n{url}",
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


def comment_text() -> str:
    """Promo comment text to post after upload.

    Returns an empty string when disabled (PROMO_ENABLED=0 or PROMO_COMMENT=0).
    """
    if not PROMO_ENABLED or not PROMO_COMMENT_ENABLED:
        return ""
    return pick_cta()
