"""Offline tests for safe AI-provider diagnostics and structured-output routing."""
import unittest
from unittest.mock import Mock, patch

import requests
import workflow


class ProviderDiagnosticsTests(unittest.TestCase):
    def _response(self, status, data):
        response = Mock()
        response.status_code = status
        response.ok = status == 200
        response.json.return_value = data
        return response

    def test_http_400_category_is_safe_and_specific(self):
        response = self._response(
            400,
            {"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key."}},
        )
        self.assertEqual(workflow._gemini_error_category(response), "INVALID_API_KEY")
        generic = self._response(
            400, {"error": {"status": "FAILED_PRECONDITION", "message": "A prerequisite is missing."}}
        )
        self.assertEqual(
            workflow._gemini_error_category(generic),
            "INVALID_REQUEST_OR_PROJECT_PREREQUISITE",
        )

    def test_smoke_test_reports_failures_without_revealing_keys(self):
        failed_c = self._response(400, {
            "error": {"status": "INVALID_ARGUMENT", "message": "API key not valid."}
        })
        working_d = self._response(200, {
            "candidates": [{"content": {"parts": [{"text": '{"connected": true}'}]}}]
        })
        working_openrouter = self._response(200, {
            "choices": [{"message": {"content": '{"connected": true}'}}]
        })
        entries = [
            {"name": "GEMINI_API_KEY_C", "value": "C-super-secret"},
            {"name": "GEMINI_API_KEY_D", "value": "D-super-secret"},
        ]
        with (
            patch.object(workflow, "_api_keys", return_value=entries),
            patch.object(workflow, "_openrouter_keys", return_value=[{
                "name": "OPENROUTER_API_KEY_A", "value": "OR-super-secret"
            }]),
            patch("requests.post", side_effect=[
                failed_c, working_d, working_openrouter
            ]) as api,
        ):
            result = workflow.diagnose_retention_connections()
        self.assertEqual([row["status"] for row in result], [
            "INVALID_API_KEY", "WORKING", "WORKING"
        ])
        self.assertEqual(api.call_count, 3)
        self.assertNotIn("super-secret", str(result))
        self.assertTrue(api.call_args_list[2].kwargs["json"]["provider"]["require_parameters"])

    def test_retention_json_requests_parameter_compatibility(self):
        result = {"score_100": 88, "strengths": [], "problems": []}
        response = self._response(200, {
            "model": "openrouter/free",
            "choices": [{"message": {"content": '{"score_100":88,"strengths":[],"problems":[]}'}}]
        })
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[{
                "name": "OPENROUTER_API_KEY_A", "value": "test"
            }]),
            patch.object(workflow, "_api_keys_for", return_value=[]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=response) as api,
        ):
            output = workflow._fast_retention_json("system", "prompt")
        self.assertEqual(output["score_100"], result["score_100"])
        self.assertTrue(api.call_args.kwargs["json"]["provider"]["require_parameters"])
        self.assertEqual(api.call_count, 1)

    def test_gemini_fallback_low_thinking_and_categorized_http_error(self):
        bad = self._response(400, {
            "error": {"status": "INVALID_ARGUMENT", "message": "API key not valid."}
        })
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "_api_keys_for", return_value=[{
                "name": "GEMINI_API_KEY_D", "value": "not-a-real-key"
            }]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=bad) as api,
        ):
            with self.assertRaisesRegex(RuntimeError, "INVALID_API_KEY"):
                workflow._fast_retention_json("sys", "prompt")
        payload = api.call_args.kwargs["json"]
        self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "low")
        self.assertEqual(api.call_count, 1)


    def test_fallback_uses_compatible_model_after_overload(self):
        busy = self._response(503, {
            "error": {"status": "UNAVAILABLE", "message": "Model overloaded."}
        })
        success = self._response(200, {
            "candidates": [{"content": {"parts": [
                {"text": '{"score_100": 81, "strengths": [], "problems": []}'}
            ]}}]
        })
        keys = [
            {"name": "GEMINI_API_KEY_D", "value": "d"},
            {"name": "GEMINI_API_KEY_C", "value": "c"},
        ]
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "_api_keys_for", return_value=keys),
            patch.object(workflow, "_api_keys", return_value=keys),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[busy, success]) as api,
        ):
            output = workflow._fast_retention_json("system", "prompt")
        self.assertEqual(output["score_100"], 81)
        self.assertEqual(api.call_count, 2)
        self.assertIn("gemini-3.8-flash", api.call_args_list[0].args[0])
        self.assertIn("gemini-3.5-flash-lite", api.call_args_list[1].args[0])

    def test_quota_error_does_not_rotate_gemini_projects(self):
        quota = self._response(429, {
            "error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}
        })
        keys = [
            {"name": "GEMINI_API_KEY_D", "value": "d"},
            {"name": "GEMINI_API_KEY_C", "value": "c"},
        ]
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "_api_keys_for", return_value=keys),
            patch.object(workflow, "_api_keys", return_value=keys),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=quota) as api,
        ):
            with self.assertRaisesRegex(RuntimeError, "Not switching projects"):
                workflow._fast_retention_json("system", "prompt")
        self.assertEqual(api.call_count, 1)

    def test_fenced_json_parser_accepts_markdown_wrapping(self):
        raw = chr(96) * 3 + 'json\n{"score_100": 90}\n' + chr(96) * 3
        self.assertEqual(workflow._extract_json(raw)["score_100"], 90)


if __name__ == "__main__":
    unittest.main()
