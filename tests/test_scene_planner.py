"""Offline regression tests for sub-minute Scene Production; no AI calls."""
import unittest
from unittest.mock import patch

import scene_planner
import workflow


class InstantSceneProductionTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "id": "test-episode",
            "story_name": "Test Bible Story",
            "target_minutes": 10,
        }
        self.script = {
            "hook": "A dramatic choice changes this story.",
            "sections": [
                {
                    "name": f"Act {n}",
                    "narration": " ".join(
                        f"At moment {i} the characters consider what happened before."
                        for i in range(16)
                    ),
                    "dialogue": [{"line": "The witness speaks."}],
                } for n in range(1, 9)
            ],
            "closing": "The story ends with a thoughtful resolution.",
        }
        self.bible = {
            "visual_direction": {"overall_style": "Family-friendly historical animation"},
            "characters": [{"name": "Miriam", "identity_lock": "Same character model"}],
            "supporting_characters": [],
            "character_groups": [],
            "locations": [{"name": "Village"}],
            "props": [{"name": "Scroll"}],
        }

    def test_compiler_preserves_every_word_in_order(self):
        output = scene_planner.make_scene_plan(self.script, self.bible, 600)
        self.assertEqual(len(output), 75)
        original = " ".join(text for _, text in scene_planner.script_story_beats(self.script))
        recombined = " ".join(s["narration"] for s in output)
        self.assertEqual(recombined, original)
        self.assertTrue(all(s["scene_number"] == i for i,s in enumerate(output,1)))
        self.assertTrue(all(s["generation_mode"] == "instant_storyboard" for s in output))

    def test_compiled_scenes_work_with_existing_flow_prompt_contract(self):
        scenes = scene_planner.make_scene_plan(self.script, self.bible, 600)
        for scene in scenes:
            for key in (
                "narration", "start_state", "dominant_action", "end_state",
                "frame_prompt", "video_prompt", "location",
                "physical_constraints", "negative_constraints",
                "scene_title", "production_status", "duration_seconds",
            ):
                self.assertIn(key, scene)
            self.assertTrue(scene["frame_prompt"].strip())
            self.assertTrue(scene["video_prompt"].strip())

    def test_workflow_never_contacts_gemini_openrouter_or_claude(self):
        saved = []
        progress = []
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", side_effect=lambda p,key,default=None:
                         self.script if key == "script_json" else self.bible),
            patch.object(workflow, "list_project_assets", return_value=[]),
            patch.object(workflow, "call_json") as ai,
            patch.object(workflow, "_call_qwen_json") as openrouter,
            patch.object(workflow, "_call_gemini_only") as gemini,
            patch.object(workflow, "save_json", side_effect=lambda *args: saved.append(args)),
        ):
            result = workflow.plan_scenes(
                "test-episode", progress=lambda value,msg: progress.append((value,msg))
            )
        self.assertEqual(len(result["scenes"]), 75)
        self.assertEqual(result["planned_runtime_seconds"], 600)
        self.assertEqual(result["runtime_difference_seconds"], 0)
        self.assertEqual(sum(x["duration_seconds"] for x in result["scenes"]), 600)
        self.assertEqual(saved[0][1], "scenes_json")
        self.assertEqual(progress[-1][0], 100)
        ai.assert_not_called()
        openrouter.assert_not_called()
        gemini.assert_not_called()

    def test_saved_narration_timing_is_respected(self):
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", side_effect=lambda p,key,default=None:
                         self.script if key == "script_json" else self.bible),
            patch.object(workflow, "list_project_assets", return_value=[
                {"metadata_json": {"duration_seconds": 600}}
            ]),
            patch.object(workflow, "save_json"),
        ):
            result = workflow.plan_scenes("test-episode")
        self.assertEqual(result["target_runtime_seconds"], 600)
        self.assertEqual(result["timing_source"], "narration audio")
        self.assertLessEqual(abs(result["runtime_difference_seconds"]), 2)

    def test_short_audio_does_not_silently_shrink_a_future_episode(self):
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", side_effect=lambda p,key,default=None:
                         self.script if key == "script_json" else self.bible),
            patch.object(workflow, "list_project_assets", return_value=[
                {"metadata_json": {"duration_seconds": 379}}
            ]),
            patch.object(workflow, "save_json") as save,
        ):
            with self.assertRaisesRegex(RuntimeError, "Scene Production paused"):
                workflow.plan_scenes("test-episode")
        save.assert_not_called()

    def test_no_saved_script_or_bible_does_not_overwrite_work(self):
        with (
            patch.object(workflow, "get_project", return_value=self.project),
            patch.object(workflow, "load_json", return_value={}),
            patch.object(workflow, "save_json") as save,
        ):
            with self.assertRaisesRegex(RuntimeError, "script"):
                workflow.plan_scenes("test-episode")
        save.assert_not_called()

    def test_malformed_story_sections_are_handled_safely(self):
        with self.assertRaisesRegex(ValueError, "invalid sections"):
            scene_planner.make_scene_plan(
                {"hook": "", "sections": "wrong"}, self.bible, 600
            )

    def test_explicit_character_and_location_continuity(self):
        script = {
            "hook": "Miriam walks through Village holding a Scroll.",
            "sections": [{"name": "Journey", "narration": "Miriam turns and reads the Scroll."}],
        }
        scenes = scene_planner.make_scene_plan(script, self.bible, 20)
        self.assertIn("Miriam", scenes[0]["characters"])
        self.assertEqual(scenes[0]["location"], "Village")
        self.assertIn("Scroll", scenes[0]["props"])


if __name__ == "__main__":
    unittest.main()
