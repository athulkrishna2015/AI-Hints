"""Hermetic tests for the custom-provider (Ollama) generation path.

Two guarantees are verified here:

1. The add-on's HTTP -> parse -> normalize pipeline is lossless for UTF-8
   Malayalam: a clean Ollama response round-trips byte-for-byte through
   `_call_custom_provider` with no mojibake / U+FFFD introduced on the add-on
   side (encoding is handled correctly with `json.dumps(...).encode("utf-8")`
   on the request and `.decode("utf-8")` on the response).

2. The defensive corruption guard rejects model output that contains U+FFFD
   replacement characters (a universal corruption marker — some Ollama cloud
   models emit script-mixed garbage), so such generations are treated as
   failures and the fallback/retry loop can pick a working model instead of
   silently committing broken hints to cards.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Neutralize logger references before importing the addon.
mock_logger = MagicMock()
sys.modules["logger"] = mock_logger
sys.modules[".logger"] = mock_logger

from addon.ai_client import AIClient

MALAYALAM_HINTS = [
    "ക്ഷതം എന്ന വാക്കിന്റെ അർത്ഥം മുറിവ് എന്നാണ്",
    "ഹാനിയും അപകടവും സൂചിപ്പിക്കുന്ന പദം",
]
MALAYALAM_OPTIONS = ["മുറിവ്", "ഹാനി", "വേദന", "മരണം"]

CLEAN_JSON = {
    "hints": MALAYALAM_HINTS,
    "options": MALAYALAM_OPTIONS,
    "correct_answer": "മുറിവ്",
}

CORRUPT_JSON = {
    "hints": ["ന�യർ സർവ്വീസ് സൊസൈറ്റിയുട� (NSS) സ്ഥാപകന�ം"],
    "options": ["മന്നത്ത് പത്മനാഭൻ"],
    "correct_answer": "മന്നത്ത് പത്മനാഭൻ",
}


def _config():
    return {
        "custom_providers": {
            "ollama": {
                "url": "http://localhost:11434/v1/chat/completions",
                "api_key": "",
            }
        },
        "thinking_levels": {},
    }


def _completion(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class OllamaUnicodeTests(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(_config())
        self.client._on_combo_success = MagicMock()
        self.client._mark_combo_failed = MagicMock()

    def test_clean_malayalam_roundtrip_is_lossless(self):
        content = __import__("json").dumps(CLEAN_JSON, ensure_ascii=False)
        with patch.object(self.client, "_post_json", return_value=_completion(content)) as post:
            result = self.client._call_custom_provider(
                "ollama", "system", "front/back", override_model="minimax-m3:cloud"
            )
        post.assert_called_once()
        self.assertEqual(result["hints"], MALAYALAM_HINTS)
        self.assertEqual(result["options"], MALAYALAM_OPTIONS)
        self.assertEqual(result["correct_answer"], "മുറിവ്")
        self.assertEqual(result["_provider"], "ollama")

    def test_corrupt_output_rejected_and_marked_failed(self):
        content = __import__("json").dumps(CORRUPT_JSON, ensure_ascii=False)
        with patch.object(self.client, "_post_json", return_value=_completion(content)):
            result = self.client._call_custom_provider(
                "ollama", "system", "front/back", override_model="minimax-m3:cloud"
            )
        # Corrupt generation must NOT be returned as a success.
        self.assertEqual(result.get("hints"), [])
        self.assertIsNone(result.get("correct_answer"))
        self.client._mark_combo_failed.assert_called()

    def test_partial_corruption_rejected(self):
        # Only one hint string is garbage; the whole generation is still
        # rejected so a broken hint never reaches the card.
        bad = {"hints": ["good hint", "s�rved part"], "options": ["a", "b"]}
        content = __import__("json").dumps(bad, ensure_ascii=False)
        with patch.object(self.client, "_post_json", return_value=_completion(content)):
            result = self.client._call_custom_provider("ollama", "s", "f/b", override_model="m")
        self.assertEqual(result.get("hints"), [])
        self.client._mark_combo_failed.assert_called()

    def test_corrupt_content_falls_back_to_reasoning(self):
        # Corrupt content, clean reasoning: must recover the clean block.
        good = __import__("json").dumps(CLEAN_JSON, ensure_ascii=False)
        bad = __import__("json").dumps(CORRUPT_JSON, ensure_ascii=False)
        payload = {"choices": [{"message": {"role": "assistant", "content": bad, "reasoning": good}}]}
        with patch.object(self.client, "_post_json", return_value=payload):
            result = self.client._call_custom_provider("ollama", "s", "f/b", override_model="m")
        self.assertEqual(result["hints"], MALAYALAM_HINTS)
        self.client._mark_combo_failed.assert_not_called()


class CorruptFlagTests(unittest.TestCase):
    def setUp(self):
        self.client = AIClient({})

    def test_flag_true_on_replacement_char(self):
        self.assertTrue(self.client._result_is_corrupt({"hints": ["a�b"]}))
        self.assertTrue(self.client._result_is_corrupt({"options": ["x"] , "distractors": ["y�"]}))
        self.assertTrue(self.client._result_is_corrupt({"correct_answer": "c�"}))

    def test_flag_false_on_clean_text(self):
        self.assertFalse(self.client._result_is_corrupt({"hints": MALAYALAM_HINTS}))
        self.assertFalse(self.client._result_is_corrupt({"hints": [], "options": []}))
        self.assertFalse(self.client._result_is_corrupt({}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
