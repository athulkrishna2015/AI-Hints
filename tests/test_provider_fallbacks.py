import unittest
import urllib.error
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from addon.ai_client import (
    AIClient,
    FAILED_COMBOS_CACHE,
    RATE_LIMIT_STREAK,
)


class TestProviderModelFallbacks(unittest.TestCase):

    def setUp(self):
        FAILED_COMBOS_CACHE.clear()
        RATE_LIMIT_STREAK.clear()
        self.base_config = {
            "api_keys": {
                "openai": "sk-openai-key",
                "anthropic": "sk-anthropic-key",
                "gemini": "sk-gemini-key",
            },
            "models": {
                "openai": "gpt-4o",
                "anthropic": "claude-3-7-sonnet-latest",
                "gemini": "gemini-2.5-flash",
            },
            "model_cooldown_minutes": 10,
        }

    def _mock_http_error(self, code=500, body=b'{"error": "boom"}'):
        err = urllib.error.HTTPError(url="http://mock.api", code=code,
                                     msg="Error", hdrs={}, fp=None)
        err.read = MagicMock(return_value=body)
        return err

    def _mock_ok_response(self, hints=None, options=None):
        hints = hints or ["hint_a"]
        options = options or ["opt_a"]
        payload = '{"hints": %s, "options": %s}' % (
            __import__("json").dumps(hints),
            __import__("json").dumps(options),
        )
        resp = MagicMock()
        resp.read.return_value = ('{"choices": [{"message": {"content": %s}}]}' %
                                  __import__("json").dumps(payload)).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    # ------------------------------------------------------------------
    # Model fallback list construction (incl. custom providers)
    # ------------------------------------------------------------------

    def test_models_for_provider_builds_fallback_chain(self):
        """Standard provider: primary model first, then configured model_fallbacks."""
        client = AIClient({
            **self.base_config,
            "model_fallbacks": {
                "openai": ["gpt-4o-mini", "gpt-4-turbo"],
                "anthropic": ["claude-3-5-haiku-latest"],
            },
        })
        chain = client._models_for_provider("openai")
        self.assertEqual(chain, ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"])
        chain_anthropic = client._models_for_provider("anthropic")
        self.assertEqual(chain_anthropic, ["claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"])

    def test_models_for_provider_custom_uses_your_fallbacks(self):
        """Custom provider: entry model + custom_cfg.model_fallbacks + top-level model_fallbacks."""
        config = {
            **self.base_config,
            "custom_providers": {
                "mycustom": {
                    "url": "https://custom.api/v1",
                    "model": "custom-primary",
                    "model_fallbacks": ["custom-fallback-a", "custom-fallback-b"],
                }
            },
            "model_fallbacks": {
                "mycustom": ["global-custom-fallback"],
            },
        }
        client = AIClient(config)
        chain = client._models_for_provider(
            "mycustom",
            client.config["custom_providers"]["mycustom"].get("model", ""),
            client.config["custom_providers"]["mycustom"].get("model_fallbacks", []),
        )
        self.assertEqual(chain, ["custom-primary", "custom-fallback-a",
                                 "custom-fallback-b", "global-custom-fallback"])

    def test_models_for_provider_filters_disabled_fallbacks(self):
        client = AIClient({
            **self.base_config,
            "model_fallbacks": {"openai": ["gpt-4o-mini", "gpt-4.5-turbo"]},
            "disabled_fallback_models": {"openai": ["gpt-4o-mini"]},
        })
        chain = client._models_for_provider("openai")
        self.assertNotIn("gpt-4o-mini", chain)
        self.assertIn("gpt-4.5-turbo", chain)

    # ------------------------------------------------------------------
    # Standard provider: falls back across model_fallbacks
    # ------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_openai_compatible_falls_back_to_next_model(self, mock_urlopen):
        """Primary model fails with HTTP 500 -> next configured fallback model is used."""
        client = AIClient({
            **self.base_config,
            "model_fallbacks": {"openai": ["gpt-4o-mini"]},
        })
        mock_urlopen.side_effect = [
            self._mock_http_error(),
            self._mock_ok_response(),
        ]
        result = client._call_openai_compatible("openai", "sys", "prompt")
        self.assertEqual(result["hints"], ["hint_a"])
        self.assertEqual(result["_model"], "gpt-4o-mini")
        self.assertIn(("openai", "gpt-4o", "sk-openai-key"), FAILED_COMBOS_CACHE)
        self.assertNotIn(("openai", "gpt-4o-mini", "sk-openai-key"), FAILED_COMBOS_CACHE)

    @patch("urllib.request.urlopen")
    def test_openai_compatible_returns_failure_when_all_models_fail(self, mock_urlopen):
        client = AIClient({
            **self.base_config,
            "model_fallbacks": {"openai": ["gpt-4o-mini"]},
        })
        mock_urlopen.side_effect = [
            self._mock_http_error(),
            self._mock_http_error(),
        ]
        result = client._call_openai_compatible("openai", "sys", "prompt")
        self.assertEqual(result, {"hints": [], "options": []})
        self.assertIn(("openai", "gpt-4o", "sk-openai-key"), FAILED_COMBOS_CACHE)
        self.assertIn(("openai", "gpt-4o-mini", "sk-openai-key"), FAILED_COMBOS_CACHE)

    # ------------------------------------------------------------------
    # Custom provider fallback (the one the user asked about)
    # ------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_custom_provider_falls_back_to_next_model(self, mock_urlopen):
        """Custom provider: primary custom model -> its configured model_fallbacks."""
        config = {
            "custom_providers": {
                "mycustom": {
                    "url": "http://custom.api/v1",
                    "model": "custom-primary",
                    "model_fallbacks": ["custom-fallback-a", "custom-fallback-b"],
                    "api_key": "custom-key",
                }
            },
        }
        client = AIClient(config)
        mock_urlopen.side_effect = [
            self._mock_http_error(),
            self._mock_ok_response(),
        ]
        result = client._call_custom_provider("mycustom", "sys", "prompt")
        self.assertEqual(result["hints"], ["hint_a"])
        self.assertEqual(result["_model"], "custom-fallback-a")
        self.assertEqual(result["_provider"], "mycustom")
        self.assertIn(("mycustom", "custom-primary", "custom-key"), FAILED_COMBOS_CACHE)
        self.assertNotIn(("mycustom", "custom-fallback-a", "custom-key"), FAILED_COMBOS_CACHE)

    @patch("urllib.request.urlopen")
    def test_custom_provider_uses_global_model_fallbacks_when_custom_empty(self, mock_urlopen):
        """Custom provider without its own model_fallbacks uses top-level model_fallbacks
        as its enabled model list (the saved provider 'model' is not used when enabled
        fallbacks exist)."""
        config = {
            "custom_providers": {
                "mycustom": {
                    "url": "http://custom.api/v1",
                    "model": "custom-primary",
                    "api_key": "custom-key",
                },
            },
            "model_fallbacks": {
                "mycustom": ["global-custom-fallback"],
            },
        }
        client = AIClient(config)
        mock_urlopen.side_effect = [self._mock_ok_response()]
        result = client._call_custom_provider("mycustom", "sys", "prompt")
        self.assertEqual(result["_model"], "global-custom-fallback")
        self.assertEqual(result["_provider"], "mycustom")
        self.assertNotIn(("mycustom", "global-custom-fallback", "custom-key"), FAILED_COMBOS_CACHE)

    # ------------------------------------------------------------------
    # Blacklisted models are skipped (fallback chain avoids them)
    # ------------------------------------------------------------------

    def test_models_for_provider_skips_blacklisted(self):
        client = AIClient({**self.base_config, "model_fallbacks": {"openai": ["gpt-4o-mini"]}})
        client._mark_combo_failed("openai", "gpt-4o-mini", "sk-openai-key", delay_seconds=1000)
        chain = client._models_for_provider("openai")
        self.assertNotIn("gpt-4o-mini", chain)

    # ------------------------------------------------------------------
    # Custom provider readiness does not block presence in candidate pool
    # ------------------------------------------------------------------

    def test_custom_provider_listed_in_provider_priority(self):
        from addon.ai_client import PROVIDER_ORDER
        config = {
            "custom_providers": {"mycustom": {"url": "http://custom.api/v1", "model": "m"}},
            "api_keys": {"mycustom": "k"},
            "provider_priority": ["openai", "mycustom"],
        }
        client = AIClient(config)
        # 'mycustom' is recognized as a real provider (not blindly added to default order)
        self.assertEqual(client._candidate_providers("mycustom"), ["mycustom"])


if __name__ == "__main__":
    unittest.main()