import unittest
import os
import sys
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon.ai_client import (
    AIClient,
    _prompt_cache_key,
    FAILED_KEYS_CACHE,
    FAILED_MODELS_CACHE,
    FAILED_COMBOS_CACHE,
    RATE_LIMIT_STREAK,
)
from blacklist_helpers import isolate_blacklist


class TestPromptCaching(unittest.TestCase):
    """The system prompt is the only stable prefix, so it drives caching."""

    def setUp(self):
        isolate_blacklist(self)
        FAILED_KEYS_CACHE.clear()
        FAILED_MODELS_CACHE.clear()
        FAILED_COMBOS_CACHE.clear()
        RATE_LIMIT_STREAK.clear()

    def _client(self, provider, model):
        return AIClient({
            "api_keys": {provider: "test-key"},
            "models": {provider: model},
            "model_cooldown_minutes": 10,
            "rate_limit_backoff_seconds": 0,
        })

    def _openai_result(self):
        return {
            "choices": [{"message": {"content": json.dumps(
                {"hints": ["h"], "options": ["o"]})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                      "prompt_tokens_details": {"cached_tokens": 7}},
        }

    def _capture(self, response):
        captured = {}

        def _fake_post(url, data, headers, label):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return response

        return captured, _fake_post

    def test_cache_key_is_stable_and_hides_prompt(self):
        key = _prompt_cache_key("same prompt")
        self.assertEqual(key, _prompt_cache_key("same prompt"))
        self.assertNotEqual(key, _prompt_cache_key("different prompt"))
        self.assertNotIn("prompt", key)
        self.assertEqual(len(key), 32)

    def test_openai_sends_prompt_cache_key(self):
        client = self._client("openai", "gpt-6-astra")
        captured, fake = self._capture(self._openai_result())

        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("openai", "sys prompt", "card A")

        self.assertEqual(captured["data"]["prompt_cache_key"],
                         _prompt_cache_key("sys prompt"))

    def test_mistral_sends_prompt_cache_key(self):
        client = self._client("mistral", "mistral-large-latest")
        captured, fake = self._capture(self._openai_result())

        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("mistral", "sys prompt", "card A")

        self.assertEqual(captured["data"]["prompt_cache_key"],
                         _prompt_cache_key("sys prompt"))

    def test_grok_sends_conversation_id_header(self):
        client = self._client("grok", "grok-4.7")
        captured, fake = self._capture(self._openai_result())

        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("grok", "sys prompt", "card A")

        flat = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(flat.get("x-grok-conv-id"),
                         _prompt_cache_key("sys prompt"))

    def test_openrouter_anthropic_requests_automatic_cache(self):
        client = self._client("openrouter", "anthropic/claude-sonnet-4-6")
        captured, fake = self._capture(self._openai_result())

        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("openrouter", "sys prompt", "card A")

        self.assertEqual(captured["data"]["cache_control"],
                         {"type": "ephemeral"})

    def test_openrouter_non_anthropic_has_no_cache_control(self):
        client = self._client("openrouter", "google/gemini-4-carbon")
        captured, fake = self._capture(self._openai_result())

        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("openrouter", "sys prompt", "card A")

        self.assertNotIn("cache_control", captured["data"])

    def test_anthropic_system_prompt_has_cache_breakpoint(self):
        client = self._client("anthropic", "claude-sonnet-4-6")
        result = {
            "content": [{"type": "text", "text": json.dumps(
                {"hints": ["h"], "options": ["o"]})}],
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_read_input_tokens": 8},
        }
        captured, fake = self._capture(result)

        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_anthropic("sys prompt", "card A")

        self.assertEqual(captured["data"]["system"], [{
            "type": "text",
            "text": "sys prompt",
            "cache_control": {"type": "ephemeral"},
        }])

    def test_usage_logging_reports_cache_hits(self):
        client = self._client("openai", "gpt-6-astra")
        with patch("addon.ai_client.logger") as mocked:
            client._log_usage(self._openai_result())
        message = mocked.info.call_args[0][0]
        self.assertIn("cached_tokens:7", message)

    def test_usage_logging_reports_gemini_cache_hits(self):
        client = self._client("gemini", "gemini-4-argon")
        with patch("addon.ai_client.logger") as mocked:
            client._log_usage({
                "usageMetadata": {
                    "promptTokenCount": 1200,
                    "candidatesTokenCount": 40,
                    "cachedContentTokenCount": 1000,
                }
            })
        message = mocked.info.call_args[0][0]
        self.assertIn("cachedContentTokenCount:1000", message)


if __name__ == "__main__":
    unittest.main()
