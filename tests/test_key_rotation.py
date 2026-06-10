import unittest
import urllib.error
import urllib.request
from unittest.mock import patch, MagicMock
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from addon.ai_client import AIClient, FAILED_KEYS_CACHE, FAILED_MODELS_CACHE

class TestKeyRotation(unittest.TestCase):
    def setUp(self):
        FAILED_KEYS_CACHE.clear()
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
        FAILED_MODELS_CACHE.clear()
        FAILED_MODELS_CACHE[("dummy", "dummy")] = 0.0

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

    def test_available_api_keys_excludes_failed(self):
        # All available initially
        self.assertEqual(self.client._available_api_keys("openai"), ["key1", "key2", "key3"])
        
        # Mark key1 as failed
        self.client._mark_key_failed("openai", "key1", delay_seconds=60)
        
        # key1 should be excluded
        self.assertEqual(self.client._available_api_keys("openai"), ["key2", "key3"])
        
        # Mark key2 as failed
        self.client._mark_key_failed("openai", "key2", delay_seconds=60)
        self.assertEqual(self.client._available_api_keys("openai"), ["key3"])

    def test_available_api_keys_fallback(self):
        # Mark all as failed
        self.client._mark_key_failed("openai", "key1", delay_seconds=60)
        self.client._mark_key_failed("openai", "key2", delay_seconds=60)
        self.client._mark_key_failed("openai", "key3", delay_seconds=60)
        
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
        self.assertIn(("openai", "key1"), FAILED_KEYS_CACHE)
        
        # Check that key2 is not blacklisted
        self.assertNotIn(("openai", "key2"), FAILED_KEYS_CACHE)

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
        
        # Test case 2: Both keys fail. It should raise an Exception on the last key.
        mock_urlopen.side_effect = [resp_401, resp_401]
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
        self.assertIn(("gemini", "key_gemini_1"), FAILED_KEYS_CACHE)
        
        # Check that key_gemini_2 is not blacklisted
        self.assertNotIn(("gemini", "key_gemini_2"), FAILED_KEYS_CACHE)

if __name__ == "__main__":
    unittest.main()
