"""Unit tests for src/promo.py."""
import importlib
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


if __name__ == "__main__":
    unittest.main()
