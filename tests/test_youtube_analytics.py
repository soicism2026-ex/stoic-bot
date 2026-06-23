"""Tests for src/youtube_analytics.py — quota handling, cache logic, metric parsing."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import youtube_analytics as yta


class TestCache(unittest.TestCase):

    def test_load_missing_file_returns_empty(self):
        with patch.object(yta, "CACHE_PATH", Path("/nonexistent/path.json")):
            result = yta.load_cache()
        self.assertEqual(result, {})

    def test_load_corrupt_file_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{")
            tmp = Path(f.name)
        try:
            with patch.object(yta, "CACHE_PATH", tmp):
                result = yta.load_cache()
            self.assertEqual(result, {})
        finally:
            tmp.unlink(missing_ok=True)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            data = {"vid123": {"views": 500, "avg_view_percentage": 65.0}}
            with patch.object(yta, "CACHE_PATH", cache_path):
                yta.save_cache(data)
                loaded = yta.load_cache()
            self.assertEqual(loaded["vid123"]["views"], 500)
            self.assertAlmostEqual(loaded["vid123"]["avg_view_percentage"], 65.0)

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "subdir" / "cache.json"
            with patch.object(yta, "CACHE_PATH", cache_path):
                yta.save_cache({"v1": {"views": 1}})
            self.assertTrue(cache_path.exists())


class TestFetchAndCache(unittest.TestCase):

    def _make_cache(self, video_ids: list[str], hours_old: float = 0) -> dict:
        fetched_at = (datetime.utcnow() - timedelta(hours=hours_old)).isoformat()
        return {
            vid: {"views": 100, "avg_view_percentage": 50.0, "fetched_at": fetched_at}
            for vid in video_ids
        }

    def test_fresh_cache_not_refetched(self):
        cache = self._make_cache(["v1", "v2"], hours_old=1)
        with patch.object(yta, "load_cache", return_value=cache), \
             patch.object(yta, "fetch_video_metrics") as mock_fetch, \
             patch.object(yta, "save_cache"):
            result = yta.fetch_and_cache(["v1", "v2"], min_age_hours=48)
        mock_fetch.assert_not_called()
        self.assertIn("v1", result)
        self.assertIn("v2", result)

    def test_stale_cache_triggers_refetch(self):
        cache = self._make_cache(["v1"], hours_old=72)  # older than 48h
        fresh_data = {
            "v1": {
                "views": 999, "avg_view_percentage": 80.0,
                "fetched_at": datetime.utcnow().isoformat()
            }
        }
        with patch.object(yta, "load_cache", return_value=cache), \
             patch.object(yta, "fetch_video_metrics", return_value=fresh_data) as mock_fetch, \
             patch.object(yta, "save_cache"):
            result = yta.fetch_and_cache(["v1"], min_age_hours=48)
        mock_fetch.assert_called_once()
        self.assertEqual(result["v1"]["views"], 999)

    def test_force_refetches_even_fresh(self):
        cache = self._make_cache(["v1"], hours_old=0)
        fresh_data = {"v1": {"views": 500, "fetched_at": datetime.utcnow().isoformat()}}
        with patch.object(yta, "load_cache", return_value=cache), \
             patch.object(yta, "fetch_video_metrics", return_value=fresh_data) as mock_fetch, \
             patch.object(yta, "save_cache"):
            result = yta.fetch_and_cache(["v1"], min_age_hours=48, force=True)
        mock_fetch.assert_called_once()
        self.assertEqual(result["v1"]["views"], 500)

    def test_missing_from_cache_fetched(self):
        fresh_data = {
            "new_vid": {"views": 200, "fetched_at": datetime.utcnow().isoformat()}
        }
        with patch.object(yta, "load_cache", return_value={}), \
             patch.object(yta, "fetch_video_metrics", return_value=fresh_data) as mock_fetch, \
             patch.object(yta, "save_cache"):
            result = yta.fetch_and_cache(["new_vid"], min_age_hours=48)
        mock_fetch.assert_called_once()
        self.assertIn("new_vid", result)

    def test_returns_only_requested_videos(self):
        cache = self._make_cache(["v1", "v2", "v3"], hours_old=0)
        with patch.object(yta, "load_cache", return_value=cache), \
             patch.object(yta, "fetch_video_metrics", return_value={}), \
             patch.object(yta, "save_cache"):
            result = yta.fetch_and_cache(["v1"], min_age_hours=48)
        self.assertIn("v1", result)
        self.assertNotIn("v2", result)
        self.assertNotIn("v3", result)


class TestMetricParsing(unittest.TestCase):

    def _mock_response(self, rows: list[list]) -> dict:
        return {
            "columnHeaders": [
                {"name": "video"}, {"name": "views"},
                {"name": "estimatedMinutesWatched"}, {"name": "averageViewDuration"},
                {"name": "averageViewPercentage"}, {"name": "likes"},
                {"name": "comments"}, {"name": "shares"}, {"name": "subscribersGained"},
            ],
            "rows": rows,
        }

    def test_swipe_away_rate_computed(self):
        mock_resp = self._mock_response([["vid1", "1000", "500", "25", "60.0", "50", "5", "2", "10"]])
        mock_client = MagicMock()
        mock_client.reports().query().execute.return_value = mock_resp

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["vid1"])

        self.assertIn("vid1", result)
        self.assertAlmostEqual(result["vid1"]["avg_view_percentage"], 60.0)
        self.assertAlmostEqual(result["vid1"]["swipe_away_rate"], 0.4, places=2)

    def test_100pct_gives_zero_swipe_away(self):
        mock_resp = self._mock_response([["v2", "500", "250", "30", "100.0", "25", "3", "1", "5"]])
        mock_client = MagicMock()
        mock_client.reports().query().execute.return_value = mock_resp

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["v2"])

        self.assertAlmostEqual(result["v2"]["swipe_away_rate"], 0.0)

    def test_zero_pct_gives_full_swipe_away(self):
        mock_resp = self._mock_response([["v3", "100", "0", "0", "0.0", "0", "0", "0", "0"]])
        mock_client = MagicMock()
        mock_client.reports().query().execute.return_value = mock_resp

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["v3"])

        self.assertAlmostEqual(result["v3"]["swipe_away_rate"], 1.0)

    def test_negative_swipe_clamped_to_zero(self):
        # avg_view_percentage > 100 (e.g. looped views) should not give negative swipe
        mock_resp = self._mock_response([["v4", "100", "50", "30", "110.0", "5", "0", "0", "0"]])
        mock_client = MagicMock()
        mock_client.reports().query().execute.return_value = mock_resp

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["v4"])

        self.assertGreaterEqual(result["v4"]["swipe_away_rate"], 0.0)

    def test_empty_rows_returns_empty(self):
        mock_resp = {"columnHeaders": [], "rows": []}
        mock_client = MagicMock()
        mock_client.reports().query().execute.return_value = mock_resp

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["vid_missing"])

        self.assertEqual(result, {})


class TestQuotaHandling(unittest.TestCase):

    def test_quota_budget_stops_early(self):
        mock_client = MagicMock()
        mock_client.reports().query().execute.return_value = {
            "columnHeaders": [{"name": "video"}, {"name": "views"},
                              {"name": "estimatedMinutesWatched"},
                              {"name": "averageViewDuration"},
                              {"name": "averageViewPercentage"},
                              {"name": "likes"}, {"name": "comments"},
                              {"name": "shares"}, {"name": "subscribersGained"}],
            "rows": [],
        }

        # 30 videos with BATCH_SIZE=25 = 2 batches; budget=1 should stop after first
        video_ids = [f"vid{i}" for i in range(30)]
        call_count = 0

        def mock_execute():
            nonlocal call_count
            call_count += 1
            return {"columnHeaders": [], "rows": []}

        mock_client.reports().query().execute = mock_execute

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            yta.fetch_video_metrics(video_ids, quota_budget=1)

        self.assertLessEqual(call_count, 1)

    def test_403_error_stops_gracefully(self):
        mock_client = MagicMock()
        mock_client.reports().query().execute.side_effect = Exception("403 Forbidden quota exceeded")

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["v1", "v2"])

        self.assertEqual(result, {})

    def test_400_error_stops_with_message(self):
        mock_client = MagicMock()
        mock_client.reports().query().execute.side_effect = Exception("400 Bad Request")

        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"):
            result = yta.fetch_video_metrics(["v1"])

        self.assertEqual(result, {})

    def test_client_build_failure_returns_empty(self):
        # Pass channel_id directly to skip get_channel_id() (which needs google libs)
        with patch.object(yta, "build_analytics_client", side_effect=Exception("auth failed")):
            result = yta.fetch_video_metrics(["v1"], channel_id="UC123")
        self.assertEqual(result, {})


class TestBatching(unittest.TestCase):

    def test_25_videos_one_batch(self):
        calls = []

        def mock_execute():
            calls.append(1)
            return {"columnHeaders": [], "rows": []}

        mock_client = MagicMock()
        mock_client.reports().query().execute = mock_execute

        video_ids = [f"vid{i}" for i in range(25)]
        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"), \
             patch.object(yta, "BATCH_SIZE", 25):
            yta.fetch_video_metrics(video_ids, quota_budget=100)

        self.assertEqual(len(calls), 1)

    def test_26_videos_two_batches(self):
        calls = []

        def mock_execute():
            calls.append(1)
            return {"columnHeaders": [], "rows": []}

        mock_client = MagicMock()
        mock_client.reports().query().execute = mock_execute

        video_ids = [f"vid{i}" for i in range(26)]
        with patch.object(yta, "build_analytics_client", return_value=mock_client), \
             patch.object(yta, "get_channel_id", return_value="UC123"), \
             patch.object(yta, "BATCH_SIZE", 25):
            yta.fetch_video_metrics(video_ids, quota_budget=100)

        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
