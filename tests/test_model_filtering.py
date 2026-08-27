import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from addon.ai_client import AIClient


class TestModelFiltering(unittest.TestCase):
    def setUp(self):
        self.client = AIClient({}, is_pregen=False, is_batch=False)

    def test_non_chat_detection(self):
        non_chat = [
            "mistral-embed",
            "mistral-embed-2312",
            "codestral-embed",
            "mistral-ocr-2512",
            "mistral-ocr-latest",
            "mistral-moderation-2603",
            "voxtral-mini-tts-2603",
            "voxtral-mini-transcribe-realtime-2602",
            "voxtral-mini-realtime-latest",
            "labs-leanstral-1-5",
            "openai/tts-1",
        ]
        for m in non_chat:
            self.assertTrue(
                self.client._is_non_chat_model(m),
                f"{m} should be detected as a non-chat model",
            )

    def test_chat_models_kept(self):
        chat = [
            "mistral-large-latest",
            "ministral-14b-latest",
            "magistral-small-latest",
            "codestral-latest",
            "devstral-latest",
            "voxtral-small-latest",
            "voxtral-small-2507",
            "mistral-medium",
            "gpt-4o",
            "claude-3-7-sonnet-latest",
        ]
        for m in chat:
            self.assertFalse(
                self.client._is_non_chat_model(m),
                f"{m} should be treated as a chat model",
            )

    def test_chat_only_models_strips_non_chat(self):
        models = [
            "mistral-large-latest",
            "mistral-embed",
            "mistral-ocr-latest",
            "voxtral-small-latest",
            "voxtral-mini-tts-2603",
            "codestral-latest",
        ]
        result = self.client._chat_only_models(models)
        self.assertEqual(
            result,
            ["mistral-large-latest", "voxtral-small-latest", "codestral-latest"],
        )

    def test_fetch_models_filters_non_chat(self):
        fake_models = [
            {"id": "mistral-large-latest"},
            {"id": "mistral-embed"},
            {"id": "mistral-ocr-2512"},
            {"id": "voxtral-small-latest"},
            {"id": "voxtral-mini-realtime-latest"},
            {"id": "ministral-8b-latest"},
        ]

        original = self.client._get_json
        try:
            self.client._get_json = lambda *a, **k: {"data": fake_models}
            # patch the network resolution so fetch_models hits our mock
            self.client._available_api_keys = lambda p: ["dummy-key"]
            result = self.client.fetch_models("mistral")
        finally:
            self.client._get_json = original

        self.assertIn("mistral-large-latest", result)
        self.assertIn("voxtral-small-latest", result)
        self.assertIn("ministral-8b-latest", result)
        self.assertNotIn("mistral-embed", result)
        self.assertNotIn("mistral-ocr-2512", result)
        self.assertNotIn("voxtral-mini-realtime-latest", result)


if __name__ == "__main__":
    unittest.main()
