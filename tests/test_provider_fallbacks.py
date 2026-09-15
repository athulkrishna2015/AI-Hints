import unittest
import urllib.error
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon.ai_client import (
    AIClient,
    FAILED_COMBOS_CACHE,
    RATE_LIMIT_STREAK,
    PROVIDER_UNAVAILABLE_UNTIL,
)
from blacklist_helpers import isolate_blacklist


class TestProviderModelFallbacks(unittest.TestCase):

    def setUp(self):
        isolate_blacklist(self)
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


class TestGlobalModelOverrides(unittest.TestCase):

    def setUp(self):
        isolate_blacklist(self)
        FAILED_COMBOS_CACHE.clear()
        RATE_LIMIT_STREAK.clear()

    def _client(self, **extra):
        cfg = {
            "api_keys": {"myprov": "k"},
            "custom_providers": {"myprov": {"url": "http://custom.api/v1", "model": "m1"}},
            "thinking_levels": {"myprov": {"m1": "off"}},
            "model_timeouts": {"myprov": {"m1": 0}},
            "model_cooldown_minutes": 10,
        }
        cfg.update(extra)
        return AIClient(cfg)

    def test_overlay_applies_and_restores(self):
        client = self._client(
            global_thinking_levels={"myprov": {"m1": "high"}},
            global_model_timeouts={"myprov": {"m1": 120}},
        )
        seen = {}

        def spy(client_self, provider, system_prompt, prompt, override_model=""):
            seen["think"] = (client.config.get("thinking_levels") or {}).get("myprov", {}).get("m1")
            seen["timeout"] = (client.config.get("model_timeouts") or {}).get("myprov", {}).get("m1")
            return {"hints": ["h1"], "options": ["a"], "correct_answer": "a"}

        with patch.object(AIClient, "_call_provider", spy):
            with client._global_model_overrides("myprov", "m1"):
                client._call_provider("myprov", "sys", "prompt", override_model="m1")
        self.assertEqual(seen["think"], "high")
        self.assertEqual(seen["timeout"], 120)
        self.assertEqual(client.config["thinking_levels"]["myprov"]["m1"], "off")
        self.assertEqual(client.config["model_timeouts"]["myprov"]["m1"], 0)

    def test_no_override_leaves_config_untouched(self):
        client = self._client()
        before = {"thinking_levels": dict(client.config["thinking_levels"]),
                  "model_timeouts": dict(client.config["model_timeouts"])}
        with client._global_model_overrides("myprov", "m1"):
            pass
        self.assertEqual(client.config["thinking_levels"], before["thinking_levels"])
        self.assertEqual(client.config["model_timeouts"], before["model_timeouts"])

    def test_explicit_off_overrides_inherited_level(self):
        client = self._client(
            thinking_levels={"myprov": {"m1": "high"}},
            global_thinking_levels={"myprov": {"m1": "off"}},
        )
        seen = {}

        def spy2(client_self, provider, system_prompt, prompt, override_model=""):
            seen["think"] = (client.config.get("thinking_levels") or {}).get("myprov", {}).get("m1")
            return {"hints": ["h"], "options": ["a"], "correct_answer": "a"}

        with patch.object(AIClient, "_call_provider", spy2):
            with client._global_model_overrides("myprov", "m1"):
                client._call_provider("myprov", "sys", "prompt", override_model="m1")
        self.assertEqual(seen["think"], "off")
        self.assertEqual(client.config["thinking_levels"]["myprov"]["m1"], "high")


class TestTransientProviderOutageConfig(unittest.TestCase):

    def setUp(self):
        isolate_blacklist(self)
        PROVIDER_UNAVAILABLE_UNTIL.clear()
        FAILED_COMBOS_CACHE.clear()
        RATE_LIMIT_STREAK.clear()

    def _client(self, **extra):
        config = {"api_keys": {"openai": "k"}, "models": {"openai": "gpt-4o"}}
        config.update(extra)
        client = AIClient(config)
        client._skip_provider_on_transient_outage = True
        return client

    def test_default_codes_skip_429_503_only(self):
        client = self._client()
        self.assertTrue(client._skip_transient_provider_error("openai", 429))
        PROVIDER_UNAVAILABLE_UNTIL.clear()
        self.assertTrue(client._skip_transient_provider_error("openai", 503))
        PROVIDER_UNAVAILABLE_UNTIL.clear()
        self.assertFalse(client._skip_transient_provider_error("openai", 500))

    def test_empty_codes_disables_skip_entirely(self):
        client = self._client(transient_skip_error_codes=[])
        self.assertFalse(client._skip_transient_provider_error("openai", 429))
        self.assertFalse(client._skip_transient_provider_error("openai", 503))

    def test_custom_codes_override_default(self):
        client = self._client(transient_skip_error_codes=[429])
        self.assertTrue(client._skip_transient_provider_error("openai", 429))
        self.assertFalse(client._skip_transient_provider_error("openai", 503))

    def test_provider_exclusion_disables_that_provider(self):
        client = self._client(transient_skip_providers={"openai": []})
        self.assertFalse(client._skip_transient_provider_error("openai", 429))
        self.assertTrue(client._skip_transient_provider_error("anthropic", 429))

    def test_per_provider_codes_override_global(self):
        client = self._client(
            transient_skip_error_codes=[503],
            transient_skip_providers={"openai": [429]},
        )
        self.assertTrue(client._skip_transient_provider_error("openai", 429))
        self.assertFalse(client._skip_transient_provider_error("openai", 503))
        self.assertFalse(client._skip_transient_provider_error("anthropic", 429))
        self.assertTrue(client._skip_transient_provider_error("anthropic", 503))

    def test_flag_off_never_skips(self):
        client = self._client()
        client._skip_provider_on_transient_outage = False
        self.assertFalse(client._skip_transient_provider_error("openai", 429))

    def test_non_last_key_rotates_instead_of_skipping(self):
        client = self._client()
        self.assertFalse(client._skip_transient_provider_error("openai", 503, last_key=False))
        self.assertNotIn("openai", PROVIDER_UNAVAILABLE_UNTIL)

    def test_last_key_skips_provider(self):
        client = self._client()
        self.assertTrue(client._skip_transient_provider_error("openai", 503, last_key=True))
        self.assertIn("openai", PROVIDER_UNAVAILABLE_UNTIL)

    def test_transient_error_on_first_key_tries_next_key(self):
        config = {
            "api_keys": {"openai": "k1,k2"},
            "models": {"openai": "gpt-4o"},
            "model_cooldown_minutes": 10,
        }
        client = AIClient(config)
        client._skip_provider_on_transient_outage = True
        err = urllib.error.HTTPError(url="http://mock.api", code=503,
                                     msg="Service Unavailable", hdrs={}, fp=None)
        err.read = MagicMock(return_value=b'{"error": "overloaded"}')
        ok = {"choices": [{"message": {"content": '{"hints": ["h"], "options": ["a"]}'}}]}
        with patch.object(AIClient, "_timed_post", side_effect=[err, ok]):
            result = client._call_openai_compatible("openai", "sys", "prompt")
        self.assertEqual(result.get("hints"), ["h"])
        self.assertNotIn("openai", PROVIDER_UNAVAILABLE_UNTIL)

    def test_transient_error_on_only_key_skips_provider(self):
        config = {
            "api_keys": {"openai": "k1"},
            "models": {"openai": "gpt-4o"},
            "model_cooldown_minutes": 10,
        }
        client = AIClient(config)
        client._skip_provider_on_transient_outage = True
        err = urllib.error.HTTPError(url="http://mock.api", code=503,
                                     msg="Service Unavailable", hdrs={}, fp=None)
        err.read = MagicMock(return_value=b'{"error": "overloaded"}')
        with patch.object(AIClient, "_timed_post", side_effect=err):
            result = client._call_openai_compatible("openai", "sys", "prompt")
        self.assertEqual(result, {"hints": [], "options": []})
        self.assertIn("openai", PROVIDER_UNAVAILABLE_UNTIL)


if __name__ == "__main__":
    unittest.main()