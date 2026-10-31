"""Offline tests for bounded story-treatment generation."""
import json
import unittest
from unittest.mock import Mock, patch

import requests
import workflow


class FastTreatmentTests(unittest.TestCase):
    def setUp(self):
        self.treatment = {
            "core_story": "Moses leads Israel out of Egypt.",
            "story_beats": [{"beat": "The call", "purpose": "Set the mission"}],
        }

    def _gemini_response(self, result=None):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps(result or self.treatment)}]}
            }]
        }
        return response

    def _openrouter_response(self, result=None):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "model": "test/free-model",
            "choices": [{
                "message": {"content": json.dumps(result or self.treatment)}
            }],
        }
        return response

    def test_gemini_success_uses_one_grounded_bounded_request(self):
        keys = [
            {"name": "GEMINI_API_KEY_A", "value": "primary-secret"},
            {"name": "GEMINI_API_KEY_D", "value": "spare-secret"},
        ]
        with (
            patch.object(workflow, "_api_keys_for", return_value=keys),
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=self._gemini_response()) as api,
        ):
            result = workflow.call_json(
                "system", "shape Moses", section="treatment"
            )
        self.assertEqual(result["core_story"], self.treatment["core_story"])
        self.assertEqual(api.call_count, 1)
        self.assertIn("gemini-3.8-flash", api.call_args.args[0])
        self.assertEqual(api.call_args.kwargs["timeout"], (8, 55))
        payload = api.call_args.kwargs["json"]
        self.assertEqual(payload["tools"], [{"google_search": {}}])
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 8192)
        self.assertEqual(api.call_args.kwargs["headers"]["x-goog-api-key"], "primary-secret")

    def test_gemini_timeout_falls_back_to_one_openrouter_request(self):
        with (
            patch.object(workflow, "_api_keys_for", return_value=[{
                "name": "GEMINI_API_KEY_A", "value": "gemini-secret"
            }]),
            patch.object(workflow, "_openrouter_keys", return_value=[
                {"name": "OPENROUTER_API_KEY_A", "value": "router-secret"},
                {"name": "OPENROUTER_API_KEY_B", "value": "unused-secret"},
            ]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[
                requests.Timeout(), self._openrouter_response()
            ]) as api,
        ):
            result = workflow._fast_treatment_json("system", "shape Moses")
        self.assertEqual(result["core_story"], self.treatment["core_story"])
        self.assertEqual(api.call_count, 2)
        self.assertEqual(api.call_args_list[0].kwargs["timeout"], (8, 55))
        self.assertEqual(api.call_args_list[1].kwargs["timeout"], (8, 55))
        self.assertEqual(
            api.call_args_list[1].kwargs["headers"]["Authorization"],
            "Bearer router-secret",
        )
        self.assertTrue(
            api.call_args_list[1].kwargs["json"]["provider"]["require_parameters"]
        )

    def test_no_provider_retries_or_key_rotation(self):
        with (
            patch.object(workflow, "_api_keys_for", return_value=[
                {"name": "GEMINI_API_KEY_A", "value": "first"},
                {"name": "GEMINI_API_KEY_D", "value": "second"},
            ]),
            patch.object(workflow, "_openrouter_keys", return_value=[
                {"name": "OPENROUTER_API_KEY_A", "value": "first-router"},
                {"name": "OPENROUTER_API_KEY_B", "value": "second-router"},
            ]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[
                requests.Timeout(), requests.Timeout()
            ]) as api,
        ):
            with self.assertRaisesRegex(RuntimeError, "bounded provider window"):
                workflow._fast_treatment_json("system", "shape Moses")
        self.assertEqual(api.call_count, 2)

    def test_treatment_call_json_uses_fast_route_not_general_retry_chain(self):
        with (
            patch.object(workflow, "_fast_treatment_json", return_value=self.treatment) as fast,
            patch.object(workflow, "_call_gemini_only") as general_gemini,
            patch.object(workflow, "_call_qwen_json") as general_router,
        ):
            result = workflow.call_json(
                "system", "shape Moses", temperature=0.2, section="treatment"
            )
        self.assertEqual(result, self.treatment)
        fast.assert_called_once_with(
            "system", "shape Moses", temperature=0.2, progress=None
        )
        general_gemini.assert_not_called()
        general_router.assert_not_called()

    def test_progress_reports_fallback_and_completion(self):
        messages = []
        with (
            patch.object(workflow, "_api_keys_for", return_value=[{
                "name": "GEMINI_API_KEY_A", "value": "gemini-secret"
            }]),
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=self._gemini_response()),
        ):
            workflow._fast_treatment_json(
                "system", "shape Moses", progress=messages.append
            )
        self.assertTrue(any("Checking Gemini once" in item for item in messages))
        self.assertTrue(any("completed the treatment" in item for item in messages))


if __name__ == "__main__":
    unittest.main()
