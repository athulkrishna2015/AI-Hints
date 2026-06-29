import unittest
import urllib.error
import urllib.request
from unittest.mock import patch, MagicMock
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from addon.ai_client import AIClient, FAILED_KEYS_CACHE, FAILED_MODELS_CACHE, FAILED_COMBOS_CACHE, RATE_LIMIT_STREAK

class TestKeyRotation(unittest.TestCase):
    def setUp(self):
        FAILED_KEYS_CACHE.clear()
        FAILED_MODELS_CACHE.clear()
        FAILED_COMBOS_CACHE.clear()
        self.config = {
            "api_keys": {
                "openai": "key1, key2, key3",
                "anthropic": "  key_anthropic_1; key_anthropic_2  ",
                "gemini": "key_gemini_1\nkey_gemini_2"
            },
            "models": {
                "openai": "gpt-4o",
                "anthropic": "claude-3-5-sonnet-latest",
                "gemini": "gemini-flash-latest"
            },
            "model_cooldown_minutes": 10
        }
        self.client = AIClient(self.config)
        RATE_LIMIT_STREAK.clear()

    def test_api_keys_splitting(self):
        # OpenAI keys split by comma
        self.assertEqual(self.client._api_keys_for("openai"), ["key1", "key2", "key3"])
        
        # Anthropic keys split by semicolon
        self.assertEqual(self.client._api_keys_for("anthropic"), ["key_anthropic_1", "key_anthropic_2"])
        
        # Gemini keys split by newline
        self.assertEqual(self.client._api_keys_for("gemini"), ["key_gemini_1", "key_gemini_2"])

    def test_named_api_keys(self):
        config = {
            "api_keys": {
                "openai": "primary:key1, key2 (backup), key3[third key], key4"
            }
        }
        client = AIClient(config)
        keys = client._api_keys_for("openai")
        self.assertEqual(keys, ["key1", "key2", "key3", "key4"])
        
        # Check name caching and key identifiers
        self.assertEqual(client._key_identifier("openai", "key1"), "'primary' (ending in ...key1)")
        self.assertEqual(client._key_identifier("openai", "key2"), "'backup' (ending in ...key2)")
        self.assertEqual(client._key_identifier("openai", "key3"), "'third key' (ending in ...key3)")
        self.assertEqual(client._key_identifier("openai", "key4"), "ending in ...key4")
        self.assertEqual(client._key_identifier("openai", ""), "empty key")

    def test_disabled_api_keys(self):
        config = {
            "api_keys": {
                "openai": "primary:key1, disabled:key2 (backup), key3[third key], [disabled]disabled_key4"
            }
        }
        client = AIClient(config)
        
        all_parsed = client._parse_all_keys("openai", config["api_keys"]["openai"])
        self.assertEqual(len(all_parsed), 4)
        
        self.assertEqual(all_parsed[0]["key"], "key1")
        self.assertEqual(all_parsed[0]["name"], "primary")
        self.assertTrue(all_parsed[0]["enabled"])
        
        self.assertEqual(all_parsed[1]["key"], "key2")
        self.assertEqual(all_parsed[1]["name"], "backup")
        self.assertFalse(all_parsed[1]["enabled"])
        
        self.assertEqual(all_parsed[2]["key"], "key3")
        self.assertEqual(all_parsed[2]["name"], "third key")
        self.assertTrue(all_parsed[2]["enabled"])
        
        self.assertEqual(all_parsed[3]["key"], "disabled_key4")
        self.assertEqual(all_parsed[3]["name"], "")
        self.assertFalse(all_parsed[3]["enabled"])
        
        keys = client._api_keys_for("openai")
        self.assertEqual(keys, ["key1", "key3"])

    def test_available_api_keys_excludes_failed(self):
        # All available initially
        self.assertEqual(self.client._available_api_keys("openai"), ["key1", "key2", "key3"])
        
        # Mark combo as failed
        self.client._mark_combo_failed("openai", "gpt-4o", "key1", delay_seconds=60)
        
        # Check combo failed status
        self.assertTrue(self.client._is_combo_failed("openai", "gpt-4o", "key1"))
        self.assertFalse(self.client._is_combo_failed("openai", "gpt-4o", "key2"))
        
        # Clear/On success
        self.client._on_combo_success("openai", "gpt-4o", "key1")
        self.assertFalse(self.client._is_combo_failed("openai", "gpt-4o", "key1"))

    def test_available_api_keys_fallback(self):
        # Mark all as failed
        self.client._mark_combo_failed("openai", "gpt-4o", "key1", delay_seconds=60)
        self.client._mark_combo_failed("openai", "gpt-4o", "key2", delay_seconds=60)
        self.client._mark_combo_failed("openai", "gpt-4o", "key3", delay_seconds=60)
        
        # If all fail, it should fall back to returning all of them
        self.assertEqual(self.client._available_api_keys("openai"), ["key1", "key2", "key3"])

    @patch("urllib.request.urlopen")
    def test_key_rotation_on_api_call(self, mock_urlopen):
        # First key fails with 429 Rate Limit
        # Second key succeeds and returns a valid JSON mock response
        
        resp_429 = urllib.error.HTTPError(
            url="http://mock.api",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None
        )
        # Mock fp read for the error body
        resp_429.read = MagicMock(return_value=b'{"error": {"message": "Rate limit reached"}}')
        
        resp_success = MagicMock()
        resp_success.read.return_value = b'{"choices": [{"message": {"content": "{\\"hints\\": [\\"hint1\\"], \\"options\\": [\\"opt1\\"]}"}}]}'
        resp_success.__enter__.return_value = resp_success
        
        # Side effect: first call raises 429, second call succeeds
        mock_urlopen.side_effect = [resp_429, resp_success]
        
        result = self.client._call_openai_compatible("openai", "sys_prompt", "prompt")
        
        # Check that result succeeded
        self.assertEqual(result["hints"], ["hint1"])
        
        # Check that key1 was blacklisted
        self.assertIn(("openai", "gpt-4o", "key1"), FAILED_COMBOS_CACHE)
        
        # Check that key2 is not blacklisted
        self.assertNotIn(("openai", "gpt-4o", "key2"), FAILED_COMBOS_CACHE)

    @patch("urllib.request.urlopen")
    def test_key_rotation_during_model_test(self, mock_urlopen):
        from addon.logger import log_context
        log_context.source = "model_test"
        
        # Test case 1: First key fails with 401, second key succeeds.
        # It should rotate to the second key and succeed!
        resp_401 = urllib.error.HTTPError(
            url="http://mock.api",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )
        resp_401.read = MagicMock(return_value=b'{"error": {"message": "Invalid key"}}')
        
        resp_success = MagicMock()
        resp_success.read.return_value = b'{"choices": [{"message": {"content": "{\\"hints\\": [\\"hint1\\"], \\"options\\": [\\"opt1\\"]}"}}]}'
        resp_success.__enter__.return_value = resp_success
        
        mock_urlopen.side_effect = [resp_401, resp_success]
        
        result = self.client._call_openai_compatible("openai", "sys_prompt", "prompt")
        self.assertEqual(result["hints"], ["hint1"])
        
        # Test case 2: All keys fail. It should raise an Exception on the last key.
        mock_urlopen.side_effect = [resp_401, resp_401, resp_401]
        with self.assertRaises(Exception) as ctx:
            self.client._call_openai_compatible("openai", "sys_prompt", "prompt")
        self.assertIn("Unauthorized", str(ctx.exception))
        
        # Reset log context source
        log_context.source = None

    @patch("urllib.request.urlopen")
    def test_key_rotation_on_gemini_api_key_invalid(self, mock_urlopen):
        # First Gemini key fails with 400 API_KEY_INVALID
        # Second Gemini key succeeds
        resp_400 = urllib.error.HTTPError(
            url="http://mock.api",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None
        )
        resp_400.read = MagicMock(return_value=b'{"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid"}}')
        
        resp_success = MagicMock()
        resp_success.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"hints\\": [\\"hint1\\"], \\"options\\": [\\"opt1\\"]}"}]}}]}'
        resp_success.__enter__.return_value = resp_success
        
        mock_urlopen.side_effect = [resp_400, resp_success]
        
        result = self.client._call_gemini("sys_prompt", "prompt")
        
        # Check that result succeeded
        self.assertEqual(result["hints"], ["hint1"])
        
        # Check that key_gemini_1 was blacklisted
        self.assertIn(("gemini", "gemini-flash-latest", "key_gemini_1"), FAILED_COMBOS_CACHE)
        
        # Check that key_gemini_2 is not blacklisted
        self.assertNotIn(("gemini", "gemini-flash-latest", "key_gemini_2"), FAILED_COMBOS_CACHE)

    def test_key_blacklist_persistence(self):
        import time
        # Clear mock config key if present
        if "model_blacklist_data" in self.client.config:
            del self.client.config["model_blacklist_data"]
            
        try:
            # Mark a combo as failed
            self.client._mark_combo_failed("gemini", "gemini-flash-latest", "my_failed_key", delay_seconds=100)
            
            # Verify it is in cache
            self.assertIn(("gemini", "gemini-flash-latest", "my_failed_key"), FAILED_COMBOS_CACHE)
            
            # Verify it was saved to config
            self.assertIn("model_blacklist_data", self.client.config)
            saved_data = self.client.config["model_blacklist_data"]
            self.assertEqual(saved_data.get("version"), 3)
            self.assertIn("gemini|gemini-flash-latest|my_failed_key", saved_data.get("combos_expiries", {}))
            
            # Clear cache and reload
            FAILED_COMBOS_CACHE.clear()
            self.assertEqual(len(FAILED_COMBOS_CACHE), 0)
            
            self.client._load_blacklist()
            
            # Verify it was reloaded
            self.assertIn(("gemini", "gemini-flash-latest", "my_failed_key"), FAILED_COMBOS_CACHE)
            self.assertGreater(FAILED_COMBOS_CACHE[("gemini", "gemini-flash-latest", "my_failed_key")], time.time())
            
        finally:
            if "model_blacklist_data" in self.client.config:
                del self.client.config["model_blacklist_data"]

    def test_blacklist_save_preserves_live_meta_config(self):
        stripped_batch_config = {
            "ai_provider": "gemini",
            "models": {"gemini": "gemini-flash-latest"},
            "model_cooldown_minutes": 10,
        }
        live_meta_config = {
            "api_keys": {"gemini": "real_saved_key"},
            "additional_system_instructions": "keep this",
            "antigravity_accounts": "keep accounts",
            "provider_priority": ["openrouter", "gemini", "openai"],
            "model_fallbacks": {"gemini": ["gemini-3.1-flash-lite", "gemini-2.5-flash"]},
            "global_model_priority": ["gemini:gemini-3.1-flash-lite", "openrouter:openrouter/auto"],
            "use_global_model_priority": True,
            "disabled_fallback_models": {"gemini": ["gemini-flash-latest"]},
            "model_blacklist_data": {"version": 3, "old": True},
        }

        client = AIClient(stripped_batch_config)
        fake_mw = MagicMock()
        fake_mw.addonManager.getConfig.return_value = dict(live_meta_config)

        with patch.dict(sys.modules, {"aqt": MagicMock(mw=fake_mw)}):
            client._mark_combo_failed("gemini", "gemini-flash-latest", "failed_key", delay_seconds=100)

        fake_mw.addonManager.writeConfig.assert_called()
        _package, saved_config = fake_mw.addonManager.writeConfig.call_args.args
        self.assertEqual(saved_config["api_keys"], live_meta_config["api_keys"])
        self.assertEqual(saved_config["additional_system_instructions"], "keep this")
        self.assertEqual(saved_config["antigravity_accounts"], "keep accounts")
        self.assertEqual(saved_config["provider_priority"], live_meta_config["provider_priority"])
        self.assertEqual(saved_config["model_fallbacks"], live_meta_config["model_fallbacks"])
        self.assertEqual(saved_config["global_model_priority"], live_meta_config["global_model_priority"])
        self.assertEqual(saved_config["use_global_model_priority"], True)
        self.assertEqual(saved_config["disabled_fallback_models"], live_meta_config["disabled_fallback_models"])
        self.assertIn("model_blacklist_data", saved_config)
        self.assertIn(
            "gemini|gemini-flash-latest|failed_key",
            saved_config["model_blacklist_data"].get("combos_expiries", {}),
        )

    @patch("urllib.request.urlopen")
    def test_gemini_rate_limit_checks_other_models_before_blacklisting(self, mock_urlopen):
        # Configure multiple models for gemini
        self.client.config["model_fallbacks"] = {
            "gemini": ["gemini-2.5-pro"]
        }
        
        # First call (gemini-flash-latest, key 1) fails with 429
        resp_429 = urllib.error.HTTPError(
            url="http://mock.api",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None
        )
        resp_429.read = MagicMock(return_value=b'{"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}')
        
        # Second call (gemini-flash-latest, key 2) succeeds
        resp_success = MagicMock()
        resp_success.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"hints\\": [\\"hint_from_model_2\\"], \\"options\\": [\\"opt1\\"]}"}]}}]}'
        resp_success.__enter__.return_value = resp_success
        
        mock_urlopen.side_effect = [resp_429, resp_success]
        
        result = self.client._call_gemini("sys_prompt", "prompt")
        
        # Verify that result succeeded
        self.assertEqual(result["hints"], ["hint_from_model_2"])
        
        # Verify that key_gemini_1 IS blacklisted (because it failed on the model)
        self.assertIn(("gemini", "gemini-flash-latest", "key_gemini_1"), FAILED_COMBOS_CACHE)
        self.assertNotIn(("gemini", "gemini-flash-latest", "key_gemini_2"), FAILED_COMBOS_CACHE)

    @patch("urllib.request.urlopen")
    def test_gemini_rate_limit_blacklists_key_if_all_models_fail(self, mock_urlopen):
        # Configure multiple models for gemini
        self.client.config["model_fallbacks"] = {
            "gemini": ["gemini-2.5-pro"]
        }
        
        resp_429 = urllib.error.HTTPError(
            url="http://mock.api",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None
        )
        resp_429.read = MagicMock(return_value=b'{"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}')
        
        resp_success = MagicMock()
        resp_success.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"hints\\": [\\"hint_from_key_2\\"], \\"options\\": [\\"opt1\\"]}"}]}}]}'
        resp_success.__enter__.return_value = resp_success
        
        # Model 1 key 1 fails, Model 1 key 2 fails.
        # Fallback Model 2: key 1 fails, key 2 succeeds.
        mock_urlopen.side_effect = [resp_429, resp_429, resp_429, resp_success]
        
        result = self.client._call_gemini("sys_prompt", "prompt")
        
        # Verify that result succeeded
        self.assertEqual(result["hints"], ["hint_from_key_2"])
        
        # Verify that key_gemini_1 IS blacklisted (all models failed on it)
        self.assertIn(("gemini", "gemini-flash-latest", "key_gemini_1"), FAILED_COMBOS_CACHE)
        self.assertIn(("gemini", "gemini-2.5-pro", "key_gemini_1"), FAILED_COMBOS_CACHE)
        self.assertNotIn(("gemini", "gemini-2.5-pro", "key_gemini_2"), FAILED_COMBOS_CACHE)

if __name__ == "__main__":
    unittest.main()
