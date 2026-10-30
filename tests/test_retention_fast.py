"""Offline safety tests: never contact AI providers or alter live production records."""
import json
import unittest
from unittest.mock import Mock, patch

import requests
import workflow


class FastRetentionTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "id": "test-episode",
            "target_minutes": 10,
            "bible_reference": "Matthew 1–28",
        }
        self.script = {
            "hook": "Opening hook",
            "sections": [{"name": "Beginning", "narration": "Once upon a time."}],
            "closing": "The end",
        }
        self.review = {
            "score_100": 71,
            "strengths": ["Clear introduction"],
            "problems": ["Needs more character moments"],
        }

    def test_review_one_call_and_no_script_rewrite(self):
        saved = []
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", side_effect=lambda p, name, default=None: self.script if name == "script_json" else {}),
            patch.object(workflow, "_fast_retention_json", return_value=dict(self.review)) as api,
            patch.object(workflow, "save_json", side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow.critique_script("test-episode")
        self.assertEqual(api.call_count, 1)
        self.assertEqual(result["score_100"], 71)
        self.assertFalse(result["quality_gate_passed"])
        self.assertEqual(result["quality_target"], 95)
        self.assertEqual(result["automatic_rewrite_rounds"], 0)
        self.assertEqual([item[1] for item in saved], ["critique_json"])

    def test_manual_improvement_keeps_original_on_worse_score(self):
        saved = []
        revised = {"sections": [{"name": "Beginning", "narration": "Different."}]}
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", side_effect=lambda p, name, default=None: self.script if name == "script_json" else dict(self.review)),
            patch.object(workflow, "_fast_retention_json", return_value=revised) as rewrite,
            patch.object(workflow, "_retention_review_for", return_value={"score_100": 64}),
            patch.object(workflow, "save_json", side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow.improve_script_once("test-episode")
        self.assertEqual(rewrite.call_count, 1)
        self.assertEqual(result["score_100"], 71)
        self.assertEqual(saved, [])

    def test_manual_improvement_saves_only_reviewed_better_draft(self):
        saved = []
        revised = {"sections": [{"name": "Beginning", "narration": "Better."}]}
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", side_effect=lambda p, name, default=None: self.script if name == "script_json" else dict(self.review)),
            patch.object(workflow, "_fast_retention_json", return_value=revised),
            patch.object(workflow, "_retention_review_for", return_value={"score_100": 96}),
            patch.object(workflow, "save_json", side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow.improve_script_once("test-episode")
        self.assertTrue(result["quality_gate_passed"])
        self.assertEqual(result["score_100"], 96)
        self.assertEqual([item[1] for item in saved], ["script_json", "critique_json"])
        self.assertEqual(saved[0][2], revised)

    def test_openrouter_success_skips_fallback(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "model": "openrouter/free",
            "choices": [{"message": {"content": json.dumps(self.review)}}],
        }
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[{"name": "OPENROUTER_API_KEY", "value": "test-token"}]),
            patch.object(workflow, "_api_keys_for", return_value=[{"name": "GEMINI_API_KEY_D", "value": "test-token"}]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=response) as api,
        ):
            result = workflow._fast_retention_json("system", "prompt")
        self.assertEqual(result["score_100"], 71)
        self.assertEqual(api.call_count, 1)

    def test_openrouter_timeout_falls_back_to_one_gemini_call(self):
        gemini_response = Mock(ok=True, status_code=200)
        gemini_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(self.review)}]}}]
        }
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[{"name": "OPENROUTER_API_KEY", "value": "test-token"}]),
            patch.object(workflow, "_api_keys_for", return_value=[{"name": "GEMINI_API_KEY_D", "value": "test-token"}]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[requests.Timeout(), gemini_response]) as api,
        ):
            result = workflow._fast_retention_json("system", "prompt")
        self.assertEqual(result["score_100"], 71)
        self.assertEqual(api.call_count, 2)
        self.assertLessEqual(api.call_args_list[0].kwargs["timeout"][1], 55)
        self.assertLessEqual(api.call_args_list[1].kwargs["timeout"][1], 35)

    def test_no_providers_fails_without_retry(self):
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "_api_keys_for", return_value=[]),
            patch("requests.post") as api,
        ):
            with self.assertRaisesRegex(RuntimeError, "No OpenRouter or Gemini"):
                workflow._fast_retention_json("system", "prompt")
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
