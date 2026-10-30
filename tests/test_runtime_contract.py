"""Runtime contract tests: script, narration, and master editor safeguards."""
import unittest
from unittest.mock import patch

import runtime_contract as runtime
import workflow


def sample_script(words):
    return {
        "hook": "Opening.",
        "sections": [{
            "name": "Story",
            "narration": " ".join(["scripture-grounded"] * (words - 2)),
            "dialogue": [],
        }],
        "closing": "Closing.",
    }


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.project = {"id": "test-episode", "target_minutes": 10}
        self.room = {"status": "drafts_scored", "providers": {}}

    def test_speaking_text_includes_hook_dialogue_and_closing(self):
        example = {
            "hook": "one two",
            "sections": [{
                "name": "NOT SPOKEN",
                "purpose": "NOT SPOKEN",
                "narration": "three four five",
                "dialogue": [{"line": "six seven"}, "eight"],
            }],
            "closing": "nine ten",
        }
        spoken = runtime.script_narration_text(example)
        self.assertEqual(len(spoken.split()), 10)
        self.assertNotIn("NOT SPOKEN", spoken)

    def test_ten_minute_target_has_explicit_length_contract(self):
        report = runtime.script_runtime_report(sample_script(1500), 10)
        self.assertEqual(report["word_count"], 1500)
        self.assertTrue(report["matches_target"])
        self.assertEqual(report["target_words"], 1500)
        self.assertEqual(report["estimated_seconds"], 600)

    def test_existing_short_script_is_rejected_before_narration(self):
        report = runtime.script_runtime_report(sample_script(941), 10)
        self.assertEqual(report["status"], "too_short")
        self.assertFalse(report["matches_target"])
        self.assertLess(report["estimated_seconds"], 600)

    def test_measured_audio_6_19_fails_ten_minute_contract(self):
        report = runtime.audio_runtime_report(379, 10)
        self.assertEqual(report["actual_seconds"], 379)
        self.assertEqual(report["target_seconds"], 600)
        self.assertEqual(report["difference_seconds"], -221)
        self.assertFalse(report["matches_target"])

    def test_measured_audio_within_tolerance_is_accepted(self):
        self.assertTrue(runtime.audio_runtime_report(591, 10)["matches_target"])

    def test_wrong_length_master_gets_one_automatic_fix_and_then_saves(self):
        draft = sample_script(941)
        fixed = sample_script(1500)
        saved = []
        with (
            patch.object(workflow, "_call_gemini_only", return_value=fixed) as ai,
            patch.object(workflow, "save_json",
                         side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow._finalize_runtime_checked_master(
                "test-episode", self.project, dict(self.room), draft
            )
        self.assertEqual(ai.call_count, 1)
        self.assertEqual(result["status"], "master_ready")
        self.assertEqual(result["runtime_report"]["word_count"], 1500)
        self.assertEqual([x[1] for x in saved],
                         ["writer_room_json", "script_json"])

    def test_persisted_master_does_not_need_extra_ai_call(self):
        with (
            patch.object(workflow, "_call_gemini_only") as ai,
            patch.object(workflow, "save_json") as save,
        ):
            result = workflow._finalize_runtime_checked_master(
                "test-episode", self.project, dict(self.room),
                sample_script(1500)
            )
        ai.assert_not_called()
        self.assertEqual(result["status"], "master_ready")
        self.assertEqual(save.call_count, 2)

    def test_second_invalid_length_does_not_overwrite_approved_script(self):
        saved = []
        with (
            patch.object(workflow, "_call_gemini_only",
                         return_value=sample_script(1000)) as ai,
            patch.object(workflow, "save_json",
                         side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow._finalize_runtime_checked_master(
                "test-episode", self.project, dict(self.room),
                sample_script(941)
            )
        self.assertEqual(ai.call_count, 1)
        self.assertEqual(result["status"], "master_needs_runtime_repair")
        self.assertEqual([x[1] for x in saved], ["writer_room_json"])
        self.assertNotIn("script_json", [x[1] for x in saved])

    def test_api_outage_does_not_approve_short_master(self):
        saved = []
        with (
            patch.object(workflow, "_call_gemini_only",
                         side_effect=RuntimeError("unavailable")),
            patch.object(workflow, "save_json",
                         side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow._finalize_runtime_checked_master(
                "test-episode", self.project, dict(self.room),
                sample_script(941)
            )
        self.assertEqual(result["status"], "master_needs_runtime_repair")
        self.assertEqual(len(saved), 1)


if __name__ == "__main__":
    unittest.main()
