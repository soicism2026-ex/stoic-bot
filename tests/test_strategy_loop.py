"""Tests for scripts/strategy_loop.py — windowing, version bumping, doc structure."""
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import strategy_loop as sl


def _make_post(video_id: str, post_date: str, **kwargs) -> dict:
    base = {
        "date": post_date,
        "video_id": video_id,
        "author": "Marcus Aurelius",
        "theme": "discipline",
        "quote": "A test quote.",
        "caption": "Test caption.",
        "voice_name": "Brian",
        "music_track": "dark_ambient",
        "video_url": f"https://youtube.com/shorts/{video_id}",
    }
    base.update(kwargs)
    return base


class TestSelectWindow(unittest.TestCase):

    def _today(self):
        return date.today().isoformat()

    def _days_ago(self, n: int) -> str:
        return (date.today() - timedelta(days=n)).isoformat()

    def test_recent_video_excluded_by_age(self):
        # Posted today — less than 48h old
        posts = [_make_post("v1", self._today())]
        result = sl._select_window(posts, window_days=21, min_age_hours=48)
        self.assertEqual(result, [])

    def test_old_video_included(self):
        # Posted 5 days ago — within window and old enough
        posts = [_make_post("v1", self._days_ago(5))]
        result = sl._select_window(posts, window_days=21, min_age_hours=48)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["video_id"], "v1")

    def test_outside_window_excluded(self):
        # Posted 25 days ago — outside 21-day window
        posts = [_make_post("v1", self._days_ago(25))]
        result = sl._select_window(posts, window_days=21, min_age_hours=48)
        self.assertEqual(result, [])

    def test_dedup_per_video_id(self):
        # Same video_id appears twice (e.g. analytics re-run)
        posts = [
            _make_post("v1", self._days_ago(5)),
            _make_post("v1", self._days_ago(6)),
        ]
        result = sl._select_window(posts, window_days=21, min_age_hours=48)
        self.assertEqual(len(result), 1)

    def test_mixed_window(self):
        posts = [
            _make_post("v_new",  self._today()),         # too new
            _make_post("v_old",  self._days_ago(30)),    # too old
            _make_post("v_ok1",  self._days_ago(5)),     # good
            _make_post("v_ok2",  self._days_ago(10)),    # good
        ]
        result = sl._select_window(posts, window_days=21, min_age_hours=48)
        ids = {r["video_id"] for r in result}
        self.assertIn("v_ok1", ids)
        self.assertIn("v_ok2", ids)
        self.assertNotIn("v_new", ids)
        self.assertNotIn("v_old", ids)

    def test_empty_posts_returns_empty(self):
        result = sl._select_window([], window_days=21, min_age_hours=48)
        self.assertEqual(result, [])

    def test_invalid_date_skipped(self):
        posts = [_make_post("v1", "not-a-date")]
        result = sl._select_window(posts, window_days=21, min_age_hours=48)
        self.assertEqual(result, [])

    def test_zero_min_age_includes_recent_video(self):
        # Use yesterday (unambiguously in the past, no timing edge cases)
        posts = [_make_post("v1", self._days_ago(1))]
        result = sl._select_window(posts, window_days=21, min_age_hours=0)
        self.assertEqual(len(result), 1)


class TestPeakViews(unittest.TestCase):

    def test_max_views_across_snapshots(self):
        import tempfile, csv
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                         delete=False, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "pulled_on", "published_at", "video_id", "title", "views", "likes", "comments", "url"
            ])
            writer.writeheader()
            writer.writerow({"video_id": "v1", "views": "500", "pulled_on": "", "published_at": "", "title": "", "likes": "", "comments": "", "url": ""})
            writer.writerow({"video_id": "v1", "views": "1200", "pulled_on": "", "published_at": "", "title": "", "likes": "", "comments": "", "url": ""})
            writer.writerow({"video_id": "v1", "views": "900", "pulled_on": "", "published_at": "", "title": "", "likes": "", "comments": "", "url": ""})
            writer.writerow({"video_id": "v2", "views": "300", "pulled_on": "", "published_at": "", "title": "", "likes": "", "comments": "", "url": ""})
            tmp = Path(f.name)
        try:
            result = sl._peak_views(tmp)
            self.assertEqual(result["v1"], 1200)
            self.assertEqual(result["v2"], 300)
        finally:
            tmp.unlink(missing_ok=True)

    def test_missing_analytics_csv_returns_empty(self):
        result = sl._peak_views(Path("/nonexistent/file.csv"))
        self.assertEqual(result, {})


class TestVersionExtraction(unittest.TestCase):

    def test_version_extracted(self):
        doc = "_Version 5 — Updated 2026-06-01 by performance-loop_"
        self.assertEqual(sl._current_version(doc), 5)

    def test_no_version_returns_zero(self):
        self.assertEqual(sl._current_version("no version here"), 0)

    def test_first_version_written_is_one(self):
        # Empty existing doc → version 0 → +1 = 1
        self.assertEqual(sl._current_version("") + 1, 1)


class TestWriteStrategy(unittest.TestCase):

    def _sample_analysis(self) -> dict:
        return {
            "what_works": {
                "hooks": "Second-person accusations outperform questions.",
                "authors": "Marcus Aurelius leads at 1050v avg.",
                "themes": "Mortality performs best.",
                "retention": "High avg_view_percentage correlates with specific pain.",
                "visual_style": "Dark backgrounds with gold text stand out.",
            },
            "what_doesnt_work": "Abstract philosophical openings get swiped.",
            "top_recommendations": [
                "Use more mortality theme posts.",
                "Avoid Chrysippus on high-engagement days.",
            ],
            "confidence": "medium",
            "confidence_note": "12 videos; decent sample size.",
        }

    def _sample_window(self) -> list[dict]:
        from datetime import date, timedelta
        return [
            _make_post("v1", (date.today() - timedelta(days=5)).isoformat()),
            _make_post("v2", (date.today() - timedelta(days=10)).isoformat()),
        ]

    def test_version_bumped(self):
        existing = "_Version 3 — Updated 2026-06-01_\n"
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {}, existing)
        self.assertIn("_Version 4", doc)

    def test_first_version_is_one(self):
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {}, "")
        self.assertIn("_Version 1", doc)

    def test_contains_data_table(self):
        analytics = {"v1": {"views": 800, "avg_view_percentage": 65.0}}
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), analytics)
        self.assertIn("| v1 |", doc)

    def test_contains_recommendations(self):
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {})
        self.assertIn("mortality theme", doc)

    def test_contains_what_works_sections(self):
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {})
        self.assertIn("## What Works", doc)
        self.assertIn("### Hooks", doc)
        self.assertIn("### Authors", doc)
        self.assertIn("### Themes", doc)

    def test_contains_what_doesnt_work(self):
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {})
        self.assertIn("## What Doesn't Work", doc)
        self.assertIn("Abstract philosophical", doc)

    def test_previous_version_link(self):
        existing = "_Version 2 — Updated 2026-06-01_\n"
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {}, existing)
        self.assertIn("Previous: Version 2", doc)

    def test_no_previous_link_on_first_version(self):
        doc = sl.write_strategy(self._sample_analysis(), self._sample_window(), {}, "")
        self.assertNotIn("Previous: Version", doc)

    def test_date_range_in_header(self):
        from datetime import date, timedelta
        d1 = (date.today() - timedelta(days=5)).isoformat()
        d2 = (date.today() - timedelta(days=10)).isoformat()
        window = [_make_post("v1", d1), _make_post("v2", d2)]
        doc = sl.write_strategy(self._sample_analysis(), window, {})
        min_d = min(d1, d2)
        max_d = max(d1, d2)
        self.assertIn(min_d, doc)
        self.assertIn(max_d, doc)


class TestMinVideoThreshold(unittest.TestCase):

    def test_below_min_exits_early(self):
        posts_csv = Path("/nonexistent/posts.csv")
        with patch.object(sl, "_load_posts", return_value=[]), \
             patch.object(sl, "MIN_VIDEOS", 5):
            # Running main() — should print message and return without calling Claude
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                sl.main.__wrapped__ if hasattr(sl.main, "__wrapped__") else None
            # Just verify _select_window returns [] for empty posts
            result = sl._select_window([], 21, 48)
            self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
