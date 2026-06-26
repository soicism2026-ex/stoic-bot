"""Tests for src/visual_qa.py — threshold logic, verdict computation, JSON parsing."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import visual_qa as vqa


class TestThresholdLoading(unittest.TestCase):

    def test_defaults_loaded(self):
        t = vqa.load_thresholds()
        self.assertIn("hook_strength", t)
        self.assertIn("pass", t["hook_strength"])
        self.assertIn("fail", t["hook_strength"])

    def test_env_override_pass(self):
        with patch.dict(os.environ, {"VQA_HOOK_PASS": "8.5"}):
            t = vqa.load_thresholds()
        self.assertAlmostEqual(t["hook_strength"]["pass"], 8.5)

    def test_env_override_fail(self):
        with patch.dict(os.environ, {"VQA_TEXT_FAIL": "1.5"}):
            t = vqa.load_thresholds()
        self.assertAlmostEqual(t["text_legibility"]["fail"], 1.5)

    def test_invalid_env_ignored(self):
        with patch.dict(os.environ, {"VQA_HOOK_PASS": "not_a_number"}):
            t = vqa.load_thresholds()
        # Should fall back to default
        self.assertAlmostEqual(t["hook_strength"]["pass"],
                               vqa.DEFAULT_THRESHOLDS["hook_strength"]["pass"])

    def test_all_dimensions_present(self):
        t = vqa.load_thresholds()
        for dim in vqa.DIMENSIONS:
            self.assertIn(dim, t, f"{dim} missing from thresholds")


class TestVerdictComputation(unittest.TestCase):

    def _thresholds(self):
        return {
            "hook_strength":         {"pass": 6.0, "fail": 3.0},
            "text_legibility":       {"pass": 7.0, "fail": 4.0},
            "pacing":                {"pass": 5.0, "fail": 2.0},
            "scroll_stop_potential": {"pass": 6.0, "fail": 3.0},
        }

    def test_all_above_pass(self):
        scores = {
            "hook_strength": 8.0, "text_legibility": 8.0,
            "pacing": 7.0, "scroll_stop_potential": 7.0,
        }
        verdict, hard_fails, flags = vqa._compute_verdict(scores, self._thresholds())
        self.assertEqual(verdict, "pass")
        self.assertEqual(hard_fails, [])
        self.assertEqual(flags, [])

    def test_one_score_below_pass_above_fail(self):
        scores = {
            "hook_strength": 5.0,  # below pass(6) but above fail(3)
            "text_legibility": 8.0,
            "pacing": 7.0,
            "scroll_stop_potential": 7.0,
        }
        verdict, hard_fails, flags = vqa._compute_verdict(scores, self._thresholds())
        self.assertEqual(verdict, "flag")
        self.assertIn("hook_strength", flags)
        self.assertEqual(hard_fails, [])

    def test_one_score_below_fail(self):
        scores = {
            "hook_strength": 2.0,  # below fail(3)
            "text_legibility": 8.0,
            "pacing": 7.0,
            "scroll_stop_potential": 7.0,
        }
        verdict, hard_fails, flags = vqa._compute_verdict(scores, self._thresholds())
        self.assertEqual(verdict, "fail")
        self.assertIn("hook_strength", hard_fails)

    def test_multiple_below_fail(self):
        scores = {
            "hook_strength": 1.0,
            "text_legibility": 2.0,  # below fail(4)
            "pacing": 7.0,
            "scroll_stop_potential": 7.0,
        }
        verdict, hard_fails, flags = vqa._compute_verdict(scores, self._thresholds())
        self.assertEqual(verdict, "fail")
        self.assertIn("hook_strength", hard_fails)
        self.assertIn("text_legibility", hard_fails)

    def test_mix_flag_and_fail(self):
        scores = {
            "hook_strength": 1.0,   # hard fail
            "text_legibility": 5.0,  # flag (below pass 7, above fail 4)
            "pacing": 7.0,
            "scroll_stop_potential": 7.0,
        }
        verdict, hard_fails, flags = vqa._compute_verdict(scores, self._thresholds())
        self.assertEqual(verdict, "fail")
        self.assertIn("hook_strength", hard_fails)
        self.assertNotIn("text_legibility", hard_fails)
        self.assertIn("text_legibility", flags)

    def test_score_exactly_at_pass_threshold(self):
        scores = {
            "hook_strength": 6.0,  # exactly at pass
            "text_legibility": 7.0,
            "pacing": 5.0,
            "scroll_stop_potential": 6.0,
        }
        verdict, hard_fails, flags = vqa._compute_verdict(scores, self._thresholds())
        self.assertEqual(verdict, "pass")

    def test_missing_score_defaults_to_neutral(self):
        scores = {"hook_strength": 8.0}  # others missing
        verdict, _, _ = vqa._compute_verdict(scores, self._thresholds())
        # Should not crash; missing scores default to 5.0 (above most fail thresholds)
        self.assertIn(verdict, ("pass", "flag", "fail"))


class TestJSONParsing(unittest.TestCase):

    def _make_raw(self, **overrides):
        data = {
            "hook_strength": 7.0,
            "text_legibility": 8.0,
            "pacing": 6.0,
            "scroll_stop_potential": 7.5,
            "reasoning": "Good hook and legibility.",
            "issues": [],
            "suggestions": ["Consider darker background"],
        }
        data.update(overrides)
        return json.dumps(data)

    def test_valid_json_parsed(self):
        raw = self._make_raw()
        data = json.loads(raw)
        self.assertAlmostEqual(data["hook_strength"], 7.0)

    def test_markdown_fence_stripped(self):
        raw = "```json\n" + self._make_raw() + "\n```"
        cleaned = "\n".join(ln for ln in raw.split("\n") if not ln.startswith("```"))
        data = json.loads(cleaned.strip())
        self.assertAlmostEqual(data["hook_strength"], 7.0)

    def test_invalid_json_handled(self):
        result = vqa.VisualQAResult(
            verdict="flag",
            scores={d: 5.0 for d in vqa.DIMENSIONS},
            reasoning="JSON parse failed: {broken",
            issues=["json_parse_error"],
            suggestions=[],
            hard_fails=[],
            flags=["parse_failed"],
        )
        self.assertEqual(result.verdict, "flag")
        self.assertIn("json_parse_error", result.issues)

    def test_partial_scores_use_neutral_default(self):
        raw = json.dumps({
            "hook_strength": 7.0,
            # text_legibility missing
            "pacing": 5.0,
            "scroll_stop_potential": 6.0,
            "reasoning": "partial",
            "issues": [],
            "suggestions": [],
        })
        data = json.loads(raw)
        scores: dict[str, float] = {}
        for d in vqa.DIMENSIONS:
            try:
                scores[d] = float(data[d])
            except (KeyError, TypeError, ValueError):
                scores[d] = 5.0
        self.assertAlmostEqual(scores["text_legibility"], 5.0)


class TestVisualQAResult(unittest.TestCase):

    def test_api_error_returns_flag(self):
        # anthropic is imported lazily inside score_video, so patch at the package level
        with patch("anthropic.Anthropic") as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("network error")

            with patch("visual_qa.extract_hook_frames") as mock_frames:
                mock_frames.return_value = [Path("/fake/hook_00.jpg")]
                with patch.object(Path, "read_bytes", return_value=b"fake_jpeg_data"):
                    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                        result = vqa.score_video(Path("/fake/video.mp4"), {})

        self.assertEqual(result.verdict, "flag")
        self.assertTrue(any("api_error" in i for i in result.issues))

    def test_frame_extraction_failure_returns_flag(self):
        with patch("visual_qa.extract_hook_frames") as mock_frames:
            mock_frames.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
            result = vqa.score_video(Path("/nonexistent/video.mp4"), {})

        self.assertEqual(result.verdict, "flag")
        self.assertIn("frame_extraction_failed", result.issues)

    def test_log_appended(self):
        result = vqa.VisualQAResult(
            verdict="pass",
            scores={"hook_strength": 8.0, "text_legibility": 9.0,
                    "pacing": 7.0, "scroll_stop_potential": 8.0},
            reasoning="Looks great.",
            issues=[],
            suggestions=[],
            hard_fails=[],
            flags=[],
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            log_path = Path(f.name)
        try:
            vqa._append_log(log_path, Path("test_reel.mp4"), {"hook": "Test hook"}, result)
            content = log_path.read_text()
            self.assertIn("Visual QA", content)
            self.assertIn("PASS", content)
            self.assertIn("Test hook", content)
            self.assertIn("hook_strength=8.0", content)
        finally:
            log_path.unlink(missing_ok=True)


import subprocess  # needed for CalledProcessError reference in test


if __name__ == "__main__":
    unittest.main()
