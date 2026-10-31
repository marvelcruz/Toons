"""Offline tests for the bounded Gemini request path."""
import json
import unittest
from unittest.mock import Mock, patch

import workflow


class GeminiRequestBudgetTests(unittest.TestCase):
    def _response(self, status=200, payload=None, body=""):
        response = Mock(ok=status == 200, status_code=status, text=body)
        response.json.return_value = payload or {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps({"ok": True})}]}
            }]
        }
        return response

    def test_success_uses_assigned_project_and_bounded_timeout(self):
        keys = [{"name": "GEMINI_API_KEY_B", "value": "assigned"}]
        with (
            patch.object(workflow, "_api_keys_for", return_value=keys),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=self._response()) as api,
        ):
            result = workflow._call_gemini_only("system", "prompt", section="script")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.kwargs["headers"]["x-goog-api-key"], "assigned")
        self.assertEqual(api.call_args.kwargs["timeout"], (5, 50))

    def test_quota_response_never_switches_to_spare_project(self):
        keys = [
            {"name": "GEMINI_API_KEY_B", "value": "assigned"},
            {"name": "GEMINI_API_KEY_D", "value": "reserved-spare"},
        ]
        with (
            patch.object(workflow, "_api_keys_for", return_value=keys),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=self._response(
                status=429, body="quota exhausted"
            )) as api,
        ):
            with self.assertRaisesRegex(RuntimeError, "did not switch projects"):
                workflow._call_gemini_only("system", "prompt", section="script")
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.kwargs["headers"]["x-goog-api-key"], "assigned")

    def test_model_error_gets_only_one_alternate_model_attempt(self):
        with (
            patch.object(workflow, "_api_keys_for", return_value=[
                {"name": "GEMINI_API_KEY_B", "value": "assigned"}
            ]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[
                self._response(status=404, body="model not found"),
                self._response(),
            ]) as api,
        ):
            result = workflow._call_gemini_only("system", "prompt", section="script")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(api.call_count, 2)

    def test_timeout_uses_reserved_spare_once_without_retry_loop(self):
        with (
            patch.object(workflow, "_api_keys_for", return_value=[
                {"name": "GEMINI_API_KEY_B", "value": "assigned"},
                {"name": "GEMINI_API_KEY_D", "value": "reserved-spare"},
            ]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[
                __import__("requests").Timeout(),
                self._response(),
            ]) as api,
        ):
            result = workflow._call_gemini_only("system", "prompt", section="script")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(api.call_count, 2)
        self.assertEqual(
            api.call_args_list[1].kwargs["headers"]["x-goog-api-key"],
            "reserved-spare",
        )


if __name__ == "__main__":
    unittest.main()
