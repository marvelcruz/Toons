"""Offline tests for Gemini voice selection and extended-library fallback."""
import sys
import types
import unittest
from unittest.mock import patch

import workflow


class VoiceCatalogTests(unittest.TestCase):
    def test_all_30_official_voices_are_always_available(self):
        with patch.object(workflow, "_api_key_for", return_value=("", "")) as api:
            voices = workflow.list_tts_voices()
        api.assert_not_called()
        self.assertEqual(len(voices), 30)
        self.assertEqual(len({v["id"] for v in voices}), 30)
        for name in ("Algenib", "Algieba", "Charon", "Sulafat", "Gacrux", "Kore", "Zephyr"):
            self.assertIn(name, {v["id"] for v in voices})
        self.assertTrue(all("·" in v["display_name"] for v in voices))

    def test_extended_lookup_requires_tts_key_but_never_reduces_base_list(self):
        with patch.object(workflow, "_api_key_for", return_value=("", "")):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                workflow.list_tts_voices(include_extended=True)
            self.assertEqual(len(workflow.list_tts_voices()), 30)

    def test_extended_lookup_deduplicates_and_adds_voices(self):
        class FakeVoice:
            def __init__(self, payload):
                self.payload = payload
            def model_dump(self):
                return self.payload

        class FakeClient:
            def __init__(self, **kwargs):
                self.voices = types.SimpleNamespace(list=self.list_voices)
            def list_voices(self, page_size):
                self.page_size = page_size
                return [
                    FakeVoice({"id": "Algenib", "display_name": "Algenib"}),
                    FakeVoice({"id": "voice_example_123", "display_name": "Narrative voice"}),
                    FakeVoice({"id": "voice_example_123", "display_name": "Duplicate"}),
                ]

        fake_google = types.ModuleType("google")
        fake_google.genai = types.SimpleNamespace(Client=FakeClient)
        with (
            patch.object(workflow, "_api_key_for", return_value=("fake-key", "GEMINI_API_KEY_G")),
            patch.dict(sys.modules, {"google": fake_google}),
        ):
            voices = workflow.list_tts_voices(include_extended=True)
        self.assertEqual(len(voices), 31)
        self.assertEqual(voices[-1]["id"], "voice_example_123")
        self.assertEqual(voices[-1]["source"], "extended")

    def test_extended_failure_reports_error_not_two_voice_fallback(self):
        class FailingClient:
            def __init__(self, **kwargs):
                raise RuntimeError("Test provider outage")

        fake_google = types.ModuleType("google")
        fake_google.genai = types.SimpleNamespace(Client=FailingClient)
        with (
            patch.object(workflow, "_api_key_for", return_value=("fake-key", "GEMINI_API_KEY_G")),
            patch.dict(sys.modules, {"google": fake_google}),
        ):
            with self.assertRaisesRegex(RuntimeError, "could not be loaded"):
                workflow.list_tts_voices(include_extended=True)
            self.assertEqual(len(workflow.list_tts_voices()), 30)


if __name__ == "__main__":
    unittest.main()
