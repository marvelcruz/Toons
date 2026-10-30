"""Offline tests for real Visual Bible progress (no external AI or database writes)."""
import unittest
from unittest.mock import patch

import workflow


class VisualBibleProgressTests(unittest.TestCase):
    def setUp(self):
        self.responses = [
            {"visual_direction": {"overall_style": "cinematic"}, "characters": [{"name": "A"}]},
            {"supporting_characters": [{"name": "B"}], "character_groups": [{"name": "Group"}]},
            {"locations": [{"name": "Village"}]},
            {"props": [{"name": "Staff"}], "global_continuity_rules": ["Consistent colours"]},
        ]

    def test_progress_follows_four_completed_passes_and_save(self):
        events = []
        saves = []
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-1"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "call_json", side_effect=self.responses) as ai,
            patch.object(workflow, "save_json", side_effect=lambda *args: saves.append(args)),
        ):
            result = workflow.build_character_bible(
                "episode-1", progress=lambda pct, msg: events.append((pct, msg))
            )
        self.assertEqual(ai.call_count, 4)
        self.assertEqual([pct for pct, _ in events], [0, 5, 25, 25, 50, 50, 75, 75, 95, 100])
        self.assertEqual(result["locations"][0]["name"], "Village")
        self.assertEqual(result["props"][0]["name"], "Staff")
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0][1], "character_bible_json")
        self.assertEqual(saves[0][2], result)
        self.assertIn("saved", events[-1][1].lower())

    def test_failed_generation_does_not_report_completion_or_save(self):
        events = []
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-2"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "call_json", side_effect=[self.responses[0], RuntimeError("provider down")]),
            patch.object(workflow, "save_json") as save,
        ):
            with self.assertRaisesRegex(RuntimeError, "provider down"):
                workflow.build_character_bible(
                    "episode-2", progress=lambda pct, msg: events.append((pct, msg))
                )
        save.assert_not_called()
        self.assertNotIn(100, [pct for pct, _ in events])
        self.assertLess(max(pct for pct, _ in events), 100)

    def test_malformed_character_strings_are_repaired_before_next_pass(self):
        events = []
        saves = []
        invalid_major = {
            "visual_direction": {"overall_style": "cinematic"},
            "characters": ["Jesus", "Mary"],
        }
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-4"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "call_json", side_effect=[
                invalid_major, self.responses[1], self.responses[2], self.responses[3]
            ]) as ai,
            patch.object(workflow, "_call_qwen_json", return_value=self.responses[0]) as repair,
            patch.object(workflow, "save_json", side_effect=lambda *args: saves.append(args)),
        ):
            result = workflow.build_character_bible(
                "episode-4", progress=lambda pct, msg: events.append((pct, msg))
            )
        self.assertEqual(ai.call_count, 4)
        repair.assert_called_once()
        self.assertEqual(result["characters"][0]["name"], "A")
        self.assertEqual(len(saves), 1)
        self.assertTrue(any("Correcting" in message for _, message in events))
        self.assertEqual(events[-1][0], 100)

    def test_malformed_groups_are_repaired_before_accessing_names(self):
        malformed_support = {
            "supporting_characters": [],
            "character_groups": ["Roman soldiers", "Disciples"],
        }
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-5"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "call_json", side_effect=[
                self.responses[0], malformed_support, self.responses[2], self.responses[3],
            ]),
            patch.object(workflow, "_call_qwen_json", return_value=self.responses[1]) as repair,
            patch.object(workflow, "save_json") as save,
        ):
            result = workflow.build_character_bible("episode-5")
        repair.assert_called_once()
        self.assertEqual(result["character_groups"][0]["name"], "Group")
        save.assert_called_once()

    def test_unrepairable_response_is_safe_and_explains_the_problem(self):
        events = []
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-6"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "call_json", return_value={
                "visual_direction": {}, "characters": ["Jesus"]
            }),
            patch.object(workflow, "_call_qwen_json", return_value={
                "visual_direction": {}, "characters": "Jesus"
            }),
            patch.object(workflow, "save_json") as save,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "incorrectly structured data twice"
            ):
                workflow.build_character_bible(
                    "episode-6", progress=lambda pct, msg: events.append((pct, msg))
                )
        save.assert_not_called()
        self.assertNotIn(100, [pct for pct, _ in events])

    def test_wrong_top_level_response_is_repaired(self):
        with (
            patch.object(workflow, "call_json", return_value="Jesus") as initial,
            patch.object(workflow, "_call_qwen_json", return_value=self.responses[0]) as repair,
        ):
            result = workflow._generate_visual_bible_pass(
                "major characters", "Story and schema",
                ("characters",), lambda *_: None, 5
            )
        initial.assert_called_once()
        repair.assert_called_once()
        self.assertEqual(result["characters"][0]["name"], "A")

    def test_existing_callers_do_not_need_progress_callback(self):
        with (
            patch.object(workflow, "get_project", return_value={"id": "episode-3"}),
            patch.object(workflow, "_context", return_value="Story context"),
            patch.object(workflow, "call_json", side_effect=self.responses),
            patch.object(workflow, "save_json") as save,
        ):
            workflow.build_character_bible("episode-3")
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
