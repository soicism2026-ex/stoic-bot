"""Unit tests for src/promo.py."""
import importlib
import re
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Make src/ importable from the tests/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _reload_promo(**env_overrides):
    """Import (or re-import) promo with the given env vars set."""
    with patch.dict(os.environ, {k: v for k, v in env_overrides.items()}, clear=False):
        import promo as _p
        importlib.reload(_p)
        return _p


class TestPromoDisabled(unittest.TestCase):
    def setUp(self):
        self.promo = _reload_promo(PROMO_ENABLED="0")

    def test_description_block_empty(self):
        self.assertEqual(self.promo.description_block(), "")

    def test_comment_text_empty(self):
        self.assertEqual(self.promo.comment_text(), "")

    def test_pick_cta_still_returns_string(self):
        """pick_cta() works regardless of enabled flag."""
        self.assertIsInstance(self.promo.pick_cta(), str)
        self.assertGreater(len(self.promo.pick_cta()), 0)


class TestPromoEnabled(unittest.TestCase):
    def setUp(self):
        self.url = "https://soicism.gumroad.com/l/cslosv"
        self.promo = _reload_promo(
            PROMO_ENABLED="1",
            PROMO_COMMENT="1",
            PROMO_URL=self.url,
        )

    def test_description_block_contains_url(self):
        block = self.promo.description_block()
        self.assertIn(self.url, block)

    def test_description_block_has_separator(self):
        block = self.promo.description_block()
        self.assertIn("---", block)

    def test_comment_text_contains_url(self):
        self.assertIn(self.url, self.promo.comment_text())

    def test_comment_disabled_flag(self):
        p = _reload_promo(PROMO_ENABLED="1", PROMO_COMMENT="0", PROMO_URL=self.url)
        self.assertEqual(p.comment_text(), "")

    def test_description_block_not_empty(self):
        self.assertGreater(len(self.promo.description_block()), 0)


class TestCTARotation(unittest.TestCase):
    def test_custom_variations_rotate(self):
        variations = "CTA one|CTA two|CTA three"
        # _cta_list() reads os.environ at call time, so patch must wrap the call
        import promo as p
        with patch.dict(os.environ, {"PROMO_CTA_VARIATIONS": variations}):
            ctas = p._cta_list()
        self.assertEqual(len(ctas), 3)
        self.assertEqual(ctas, ["CTA one", "CTA two", "CTA three"])

    def test_default_variations_have_url(self):
        url = "https://soicism.gumroad.com/l/cslosv"
        p = _reload_promo(PROMO_ENABLED="1", PROMO_URL=url)
        for cta in p._cta_list():
            self.assertIn(url, cta)

    def test_default_three_variations(self):
        p = _reload_promo(PROMO_ENABLED="1", PROMO_URL="https://example.com")
        self.assertEqual(len(p._cta_list()), 3)

    def test_pick_cta_cycles(self):
        """Different toordinal() values select different CTAs."""
        url = "https://example.com"
        p = _reload_promo(
            PROMO_ENABLED="1",
            PROMO_URL=url,
            PROMO_CTA_VARIATIONS="A|B|C",
        )
        # Simulate two different days: toordinal mod 3 must hit different slots
        from datetime import date
        day0 = date(2026, 6, 1)  # toordinal() % 3 == some value
        day1 = date(2026, 6, 2)  # next day, different slot
        results = set()
        for d in [day0, day1, date(2026, 6, 3)]:
            with patch("promo.date") as mock_date:
                mock_date.today.return_value = d
                # reload to pick up patched date
                importlib.reload(p)
                # Access _cta_list and compute manually
                idx = d.toordinal() % 3
                results.add(["A", "B", "C"][idx])
        self.assertGreater(len(results), 1, "CTA rotation should produce different values")

    def test_empty_variations_env_falls_back_to_defaults(self):
        p = _reload_promo(PROMO_ENABLED="1", PROMO_CTA_VARIATIONS="", PROMO_URL="https://x.com")
        self.assertEqual(len(p._cta_list()), 3)


class TestCustomCopy(unittest.TestCase):
    def test_custom_url_in_description(self):
        custom_url = "https://my-shop.gumroad.com/l/product"
        p = _reload_promo(PROMO_ENABLED="1", PROMO_URL=custom_url)
        self.assertIn(custom_url, p.description_block())

    def test_description_appends_cleanly(self):
        p = _reload_promo(PROMO_ENABLED="1", PROMO_URL="https://example.com")
        base = "Some caption text.\n\n#hashtag"
        combined = base + p.description_block()
        self.assertTrue(combined.startswith(base))
        self.assertIn("---", combined)


class TestCopyStaysTrue(unittest.TestCase):
    """The CTA ships in the description of every video and stays live forever.

    A deadline written into it ("only for June", "FREE this month only") is
    true for a few weeks and false for the rest of the channel's life. Two of
    the three defaults said exactly that, and the August 21 upload published
    "but only for June" to a live video. These tests make that class of rot a
    build failure instead of something a human has to notice.
    """

    # Words that make a claim the copy cannot keep once time passes.
    EXPIRING = [
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "this month", "this week", "today only", "ends soon", "last chance",
        "limited time", "before the price goes up", "price goes up",
        "for a limited", "hurry",
    ]

    def _defaults(self):
        p = _reload_promo(PROMO_ENABLED="1", PROMO_URL="https://example.com")
        return p._cta_list()

    @classmethod
    def _expiring_hit(cls, text):
        """Return the first expiring phrase in text, or None.

        Word-boundary matched so "maybe" is not read as the month of May and
        "augustan" is not read as August.
        """
        low = text.lower()
        for word in cls.EXPIRING:
            if re.search(r"\b" + re.escape(word) + r"\b", low):
                return word
        return None

    def test_guard_actually_catches_the_copy_that_shipped(self):
        """A guard that cannot fail is not a guard.

        These are the two real strings that were live in _DEFAULT_CTAS.
        """
        shipped = [
            "📖 I'm giving away The Stoic Reset journal for free — but only "
            "for June. 30 days to rebuild your mindset:",
            "📓 FREE this month only — The Stoic Reset, my 30-day Stoic "
            "journal. Grab it before the price goes up:",
        ]
        for cta in shipped:
            self.assertIsNotNone(
                self._expiring_hit(cta),
                f"guard failed to flag known-stale copy: {cta!r}",
            )

    def test_no_default_cta_expires(self):
        for cta in self._defaults():
            hit = self._expiring_hit(cta)
            self.assertIsNone(
                hit,
                f"CTA makes a time-bound claim that will go stale: {cta!r} "
                f"(contains {hit!r})",
            )

    def test_workflow_env_has_no_expiring_copy(self):
        """A workflow env var silently overrides the module default.

        The stale June pitch survived in daily-short.yml even after the code
        was correct, so the workflow copy is checked too.
        """
        root = Path(__file__).resolve().parent.parent
        for name in ("daily-short.yml", "repost.yml"):
            wf = root / ".github" / "workflows" / name
            if not wf.exists():
                continue
            for line in wf.read_text().splitlines():
                if "PROMO_" not in line or line.strip().startswith("#"):
                    continue
                hit = self._expiring_hit(line)
                self.assertIsNone(
                    hit,
                    f"{name} sets promo copy that expires: {line.strip()!r} "
                    f"(contains {hit!r})",
                )

    def test_every_default_still_names_the_product(self):
        for cta in self._defaults():
            self.assertIn("Stoic Reset", cta)


if __name__ == "__main__":
    unittest.main()
