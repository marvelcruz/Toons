"""Offline tests for fast Visual Bible generation and safe checkpoints."""
import json
import time
import unittest
from unittest.mock import Mock, patch

import requests
import workflow


class VisualBibleFastTests(unittest.TestCase):
    def setUp(self):
        self.responses = [
            {"visual_direction": {"overall_style": "cinematic"}, "characters": [{"name": "A"}]},
            {"supporting_characters": [{"name": "B"}], "character_groups": [{"name": "Group"}]},
            {"locations": [{"name": "Village"}]},
            {"props": [{"name": "Staff"}], "global_continuity_rules": ["Consistent colours"]},
        ]
        workflow._VISUAL_BIBLE_BLOCKED_UNTIL.clear()

    def _run(self, *, cached=None, outputs=None, error=None):
        events = []
        saved = []
        checkpoints = []
        outcomes = list(outputs if outputs is not None else self.responses)
        if error is not None:
            outcomes = [self.responses[0], error]
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-test"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "load_json", return_value={}),
            patch.object(workflow, "_read_visual_bible_checkpoints", return_value=cached or {}),
            patch.object(workflow, "_save_visual_bible_checkpoint",
                         side_effect=lambda *args: checkpoints.append(args)),
            patch.object(workflow, "_fast_visual_bible_json",
                         side_effect=outcomes) as ai,
            patch.object(workflow, "save_json",
                         side_effect=lambda *args: saved.append(args)),
        ):
            if error is None:
                result = workflow.build_character_bible(
                    "episode-test", progress=lambda pct, msg: events.append((pct, msg))
                )
            else:
                with self.assertRaisesRegex(RuntimeError, "provider down"):
                    workflow.build_character_bible(
                        "episode-test", progress=lambda pct, msg: events.append((pct, msg))
                    )
                result = None
        return result, events, saved, checkpoints, ai.call_count

    def test_four_passes_save_only_completed_bible(self):
        result, events, saved, checkpoints, calls = self._run()
        self.assertEqual(calls, 4)
        self.assertEqual([pct for pct, _ in events], [0, 5, 25, 25, 50, 50, 75, 75, 95, 100])
        self.assertEqual(result["characters"][0]["name"], "A")
        self.assertEqual(result["props"][0]["name"], "Staff")
        self.assertEqual([x[1] for x in saved], ["character_bible_json"])
        self.assertEqual([x[2] for x in checkpoints],
                         ["major", "support", "locations", "props"])

    def test_failed_pass_preserves_earlier_checkpoint(self):
        _, events, saved, checkpoints, calls = self._run(error=RuntimeError("provider down"))
        self.assertEqual(calls, 2)
        self.assertEqual(saved, [])
        self.assertEqual([x[2] for x in checkpoints], ["major"])
        self.assertNotIn(100, [pct for pct, _ in events])

    def test_resume_from_completed_checkpoint(self):
        result, _, saved, checkpoints, calls = self._run(
            cached={"major": self.responses[0]}, outputs=self.responses[1:]
        )
        self.assertEqual(calls, 3)
        self.assertEqual([x[2] for x in checkpoints], ["support", "locations", "props"])
        self.assertEqual(result["characters"][0]["name"], "A")
        self.assertEqual(len(saved), 1)

    def test_rebuild_does_not_reuse_old_completed_bible_checkpoints(self):
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-test"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "load_json", return_value={"characters": [{"name": "Old"}]}),
            patch.object(workflow, "_read_visual_bible_checkpoints") as load_checkpoints,
            patch.object(workflow, "_save_visual_bible_checkpoint"),
            patch.object(workflow, "_fast_visual_bible_json", side_effect=self.responses) as fast_ai,
            patch.object(workflow, "save_json"),
        ):
            workflow.build_character_bible("episode-test")
        load_checkpoints.assert_not_called()
        self.assertEqual(fast_ai.call_count, 4)

    def test_provider_deadline_prevents_any_request(self):
        with (
            patch.object(workflow, "_openrouter_keys") as or_keys,
            patch("requests.post") as post,
        ):
            with self.assertRaisesRegex(TimeoutError, "budget"):
                workflow._fast_visual_bible_json(
                    "system", "prompt", "major characters", ("characters",),
                    deadline=time.monotonic() + 1,
                )
        post.assert_not_called()
        or_keys.assert_not_called()

    def test_openrouter_returns_valid_json_in_one_attempt(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "model": "test/free",
            "choices": [{"message": {"content": json.dumps(self.responses[0])}}],
        }
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[
                {"name": "OPENROUTER_API_KEY_A", "value": "test"}
            ]),
            patch.object(workflow, "_api_keys_for", return_value=[
                {"name": "GEMINI_API_KEY_I", "value": "test"}
            ]) as gemini,
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=response) as call,
        ):
            result = workflow._fast_visual_bible_json(
                "system", "prompt", "major characters", ("characters",),
                deadline=time.monotonic() + 100,
            )
        self.assertEqual(result["characters"][0]["name"], "A")
        self.assertEqual(call.call_count, 1)
        self.assertTrue(call.call_args.kwargs["json"]["provider"]["require_parameters"])

    def test_malformed_openrouter_falls_back_to_gemini_without_google_search(self):
        bad = Mock(ok=True, status_code=200)
        bad.json.return_value = {
            "choices": [{"message": {"content": '{"characters":["Jesus"],"visual_direction":{}}'}}]
        }
        good = Mock(ok=True, status_code=200)
        good.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(self.responses[0])}]}}]
        }
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[
                {"name": "OPENROUTER_API_KEY_A", "value": "test"}
            ]),
            patch.object(workflow, "_api_keys_for", return_value=[
                {"name": "GEMINI_API_KEY_I", "value": "test"}
            ]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", side_effect=[bad, good]) as call,
        ):
            result = workflow._fast_visual_bible_json(
                "sys", "prompt", "major characters", ("characters",),
                deadline=time.monotonic() + 100,
            )
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result["characters"][0]["name"], "A")
        self.assertNotIn("tools", call.call_args.kwargs["json"])
        self.assertLessEqual(call.call_args_list[0].kwargs["timeout"][1], 45)
        self.assertLessEqual(call.call_args_list[1].kwargs["timeout"][1], 15)

    def test_quota_error_is_not_retried_again_and_again(self):
        rate_limited = Mock(ok=False, status_code=429)
        rate_limited.json.return_value = {
            "error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}
        }
        with (
            patch.object(workflow, "_openrouter_keys", return_value=[]),
            patch.object(workflow, "_api_keys_for", return_value=[
                {"name": "GEMINI_API_KEY_I", "value": "test"}
            ]),
            patch.object(workflow, "record_ai_usage"),
            patch("requests.post", return_value=rate_limited) as call,
        ):
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    workflow._fast_visual_bible_json(
                        "sys", "prompt", "major characters", ("characters",),
                        deadline=time.monotonic() + 100,
                    )
        self.assertEqual(call.call_count, 1)

    def test_schema_validation_rejects_plain_strings(self):
        with self.assertRaisesRegex(ValueError, "entry 1 must be an object"):
            workflow._validate_visual_bible_pass(
                {"visual_direction": {}, "characters": ["Jesus"]},
                "major characters", ("characters",),
            )


if __name__ == "__main__":
    unittest.main()
