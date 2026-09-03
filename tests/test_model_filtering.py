import unittest
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon import ai_client as ai_mod
from addon.ai_client import AIClient
from blacklist_helpers import isolate_blacklist


class TestModelFiltering(unittest.TestCase):
    def setUp(self):
        isolate_blacklist(self)
        self._net_patch = patch.object(ai_mod, "_check_network_online", lambda: True)
        self._net_patch.start()
        self._netstate_patch = patch.object(ai_mod, "_NETWORK_STATE", {"online": True})
        self._netstate_patch.start()
        self.addCleanup(self._net_patch.stop)
        self.addCleanup(self._netstate_patch.stop)
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


class TestOverrideModelRestrictsTest(unittest.TestCase):
    """Regression: passing override_model to generate_options must test ONLY that
    model, not re-run the provider's whole enabled fallback chain (which would
    make a "Test All" loop appear to only ever check the active model)."""

    def setUp(self):
        isolate_blacklist(self)
        self._net_patch = patch.object(ai_mod, "_check_network_online", lambda: True)
        self._net_patch.start()
        self._netstate_patch = patch.object(ai_mod, "_NETWORK_STATE", {"online": True})
        self._netstate_patch.start()
        self.addCleanup(self._net_patch.stop)
        self.addCleanup(self._netstate_patch.stop)

    def test_generate_options_with_override_model_tries_only_that_model(self):
        from unittest.mock import patch

        cfg = {
            "ai_provider": "mistral",
            "api_keys": {"mistral": "k"},
            "models": {"mistral": "mistral-large-latest"},
            "model_fallbacks": {"mistral": ["mistral-large-latest", "ministral-8b-latest", "magistral-small-latest"]},
        }
        client = AIClient(cfg)

        tried = []

        def fake_post(url, data, headers):
            tried.append(data["model"])
            # Simulate a working response for whatever model is requested
            return {
                "choices": [{"message": {"content": '{"hints": ["h1"], "options": ["a","b"]}'}}],
                "model": data["model"],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        with patch.object(AIClient, "_post_json", side_effect=fake_post):
            res = client.generate_options(
                "Q", "A", override_provider="mistral",
                only_this_provider=True, override_model="ministral-8b-latest",
            )

        self.assertTrue(res.get("hints"))
        # Only the requested model should have been hit, not the full fallback list.
        self.assertEqual(tried, ["ministral-8b-latest"])


if __name__ == "__main__":
    unittest.main()
