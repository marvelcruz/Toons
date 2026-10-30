"""Regression coverage for episode-specific style preparation."""
import unittest
from unittest.mock import patch

import reference_library
import workflow


class StylePreparationTests(unittest.TestCase):
    def setUp(self):
        self.new_episode = {
            "id": "episode-new", "story_name": "Daniel in the Lions' Den",
            "bible_reference": "Daniel 6", "target_minutes": 10,
            "style_brief_json": None, "treatment_json": None,
            "writer_room_json": None, "script_json": None,
        }

    def test_new_episode_requires_style_before_treatment(self):
        with patch.object(workflow, "get_project", return_value=self.new_episode):
            with self.assertRaisesRegex(RuntimeError, "Prepare Story Style"):
                workflow.develop_treatment("episode-new")

    def test_preparation_is_local_and_saves_a_specific_reference_brief(self):
        saved = []
        sample = """Daniel was taken to Babylon. The story of Daniel...
This is the story of an impossible choice, and what happened next.
Stay with us until the end to see what courage costs."""
        with (
            patch.object(workflow, "get_project", return_value=self.new_episode),
            patch.object(reference_library, "active_reference_corpus",
                         return_value=(sample, "private Supabase reference library")),
            patch.object(workflow, "save_json", side_effect=lambda *args: saved.append(args)),
            patch.object(workflow, "call_json") as ai,
        ):
            report = workflow.prepare_episode_style("episode-new")
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["story_name"], "Daniel in the Lions' Den")
        self.assertGreater(len(report["relevant_reference_excerpts"]), 0)
        self.assertEqual(saved[0][1], "style_brief_json")
        ai.assert_not_called()

    def test_saved_brief_is_reused_in_writers_room(self):
        brief = {"status": "ready", "story_name": "Ruth", "relevant_reference_excerpts": [
            {"relevance_score": 12, "excerpt": "Test reference style example"}
        ]}
        project = dict(self.new_episode, style_brief_json=brief)
        result = reference_library.writer_reference_context(project)
        self.assertEqual(result["prepared_story_style"], brief)
        self.assertEqual(result["relevant_reference_excerpts"], brief["relevant_reference_excerpts"])

    def test_old_work_in_progress_remains_accessible(self):
        legacy = dict(self.new_episode, treatment_json={"core_story": "Existing story"})
        self.assertIsNone(workflow._require_prepared_story_style(legacy))

    def test_new_approved_brief_unlocks_treatment(self):
        ready = dict(self.new_episode, style_brief_json={"status": "ready"})
        self.assertEqual(workflow._require_prepared_story_style(ready), {"status": "ready"})

    def test_incomplete_or_empty_corpus_never_reports_completion(self):
        with patch.object(reference_library, "active_reference_corpus", return_value=("", "none")):
            with self.assertRaisesRegex(RuntimeError, "No reference transcripts"):
                reference_library.prepare_story_style(self.new_episode)

    def test_private_reference_status_tracks_completeness(self):
        with patch.object(reference_library, "active_reference_corpus",
                          return_value=("line\n" * 7325 + "bible", "private Supabase reference library")):
            stat = reference_library.reference_source_status()
        self.assertFalse(stat["full_corpus_loaded"])
        self.assertEqual(stat["lines"], 7326)


if __name__ == "__main__":
    unittest.main()
