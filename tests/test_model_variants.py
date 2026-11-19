import unittest
import os
import sys
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon.ai_client import AIClient
from addon.model_variants import known_model_pairs
from blacklist_helpers import isolate_blacklist


class TestModelVariants(unittest.TestCase):
    def setUp(self):
        isolate_blacklist(self)

    def _client(self, provider, model, override):
        return AIClient({
            "api_keys": {provider: "test-key"},
            "models": {provider: model},
            "model_variants": {f"{provider}|{model}": override},
            "rate_limit_backoff_seconds": 0,
        })

    def _capture(self, response):
        captured = {}

        def _fake_post(url, data, headers, label):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return response

        return captured, _fake_post

    def _openai_result(self):
        return {"choices": [{"message": {"content": json.dumps(
            {"hints": ["h"], "options": ["o"]})}}]}

    def test_known_pairs_include_every_fetched_model_source(self):
        config = {
            "models": {"openai": "gpt-active"},
            "model_fallbacks": {"openai": ["gpt-active", "gpt-b"], "x": ["m1"]},
            "disabled_fallback_models": {"x": ["m2"]},
            "global_model_priority": [["g", "gm1"], ["g", "gm2"]],
            "disabled_global_model_priority": [["g", "gm3"], "bad-entry"],
        }
        pairs = known_model_pairs(config)
        self.assertEqual(pairs, sorted([
            ("openai", "gpt-active"), ("openai", "gpt-b"),
            ("x", "m1"), ("x", "m2"),
            ("g", "gm1"), ("g", "gm2"), ("g", "gm3"),
        ]))

    def test_sanitizes_bad_values(self):
        client = self._client("openai", "m", {
            "temperature": "hot", "max_tokens": -3, "reasoning_effort": "ultra",
            "response_format": "yaml", "prompt_caching": "no",
        })
        self.assertEqual(client._model_variant("openai", "m"), {})
        self.assertEqual(client._model_variant("openai", "other"), {})

    def test_openai_variant_applies_request_fields(self):
        client = self._client("openai", "gpt-6-astra", {
            "temperature": 0.2, "max_tokens": 800,
            "reasoning_effort": "high", "response_format": "none",
        })
        captured, fake = self._capture(self._openai_result())
        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("openai", "sys", "card")

        data = captured["data"]
        self.assertEqual(data["temperature"], 0.2)
        self.assertEqual(data["max_tokens"], 800)
        self.assertEqual(data["reasoning_effort"], "high")
        self.assertNotIn("response_format", data)

    def test_variant_can_disable_prompt_caching(self):
        client = self._client("openai", "gpt-6-astra", {"prompt_caching": False})
        captured, fake = self._capture(self._openai_result())
        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_openai_compatible("openai", "sys", "card")
        self.assertNotIn("prompt_cache_key", captured["data"])

    def test_anthropic_variant_sets_thinking_when_valid(self):
        client = self._client("anthropic", "claude-sonnet-4-6", {
            "max_tokens": 4096, "temperature": 0.3, "thinking_budget": 2048,
        })
        response = {"content": [{"type": "text", "text": json.dumps(
            {"hints": ["h"], "options": ["o"]})}]}
        captured, fake = self._capture(response)
        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_anthropic("sys", "card")

        data = captured["data"]
        self.assertEqual(data["max_tokens"], 4096)
        self.assertEqual(data["temperature"], 0.3)
        self.assertEqual(data["thinking"], {"type": "enabled", "budget_tokens": 2048})

    def test_anthropic_thinking_skipped_when_budget_too_large(self):
        client = self._client("anthropic", "claude-sonnet-4-6", {
            "max_tokens": 1024, "thinking_budget": 2048,
        })
        response = {"content": [{"type": "text", "text": json.dumps(
            {"hints": ["h"], "options": ["o"]})}]}
        captured, fake = self._capture(response)
        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_anthropic("sys", "card")
        self.assertNotIn("thinking", captured["data"])

    def test_gemini_variant_applies_generation_config(self):
        result = {"candidates": [{"content": {"parts": [{"text": json.dumps(
            {"hints": ["h"], "options": ["o"]})}]}}]}
        client = self._client("gemini", "gemini-4-hydrogen", {
            "temperature": 0.1, "max_tokens": 900,
            "thinking_budget": 512, "response_format": "none",
        })
        captured, fake = self._capture(result)
        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client._call_gemini("sys", "card")

        gen = captured["data"]["generationConfig"]
        self.assertEqual(gen["temperature"], 0.1)
        self.assertEqual(gen["maxOutputTokens"], 900)
        self.assertEqual(gen["thinkingConfig"]["thinkingBudget"], 512)
        self.assertNotIn("responseMimeType", gen)

    def test_gemini_batch_applies_variant(self):
        client = self._client("gemini", "gemini-4-carbon", {
            "temperature": 0.4, "max_tokens": 700,
        })
        captured, fake = self._capture({"name": "batches/test"})
        with patch.object(AIClient, "_timed_post", side_effect=fake):
            client.submit_gemini_batch([
                {"key": "1", "system_prompt": "sys", "user_prompt": "card"}
            ])

        inner = captured["data"]["batch"]["input_config"]["requests"]["requests"][0]["request"]
        self.assertEqual(inner["generationConfig"]["temperature"], 0.4)
        self.assertEqual(inner["generationConfig"]["maxOutputTokens"], 700)


if __name__ == "__main__":
    unittest.main()
