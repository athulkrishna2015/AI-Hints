
"""Regression tests: reasoning-model responses whose JSON lives in
`message.reasoning` / `message.reasoning_details` instead of `message.content`.

Minimax / Cline's BYOK gateway (api.cline.bot) returns reasoning models that
frequently leave `content` empty or blank and carry the substantive answer in
`reasoning` (and per-block `reasoning_details[*].text`). Before the fix,
`_extract_content` returned the empty `content`, so `_parse_json_result`
produced nothing and callers saw "returned no parseable hints/options".
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Neutralize the logger module references before importing the addon.
mock_logger = MagicMock()
sys.modules["logger"] = mock_logger
sys.modules[".logger"] = mock_logger

from addon.ai_client import AIClient

GOOD_JSON = '{"hints": ["Ice is less dense than liquid water", "Hydrogen bonding"], "options": ["Ice floats", "Ice sinks", "Ice evaporates", "No effect"], "correct_answer": "Ice floats"}'


class ReasoningExtractTests(unittest.TestCase):
    def setUp(self):
        self.client = AIClient({})
        self.expected_hints = ["Ice is less dense than liquid water", "Hydrogen bonding"]
        self.expected_options = ["Ice floats", "Ice sinks", "Ice evaporates", "No effect"]

    def _payload(self, content="", reasoning=GOOD_JSON, reasoning_details=None):
        message = {"role": "assistant", "content": content}
        if reasoning is not None:
            message["reasoning"] = reasoning
        if reasoning_details is not None:
            message["reasoning_details"] = reasoning_details
        return {"choices": [{"message": message}]}

    def test_content_empty_falls_back_to_reasoning(self):
        # content is an empty string; the JSON is in message.reasoning
        payload = self._payload(content="", reasoning=GOOD_JSON)
        extracted = self.client._extract_content(payload)
        self.assertEqual(extracted, GOOD_JSON)
        parsed = self.client._parse_json_result(extracted)
        self.assertEqual(parsed["hints"], self.expected_hints)
        self.assertEqual(parsed["options"], self.expected_options)

    def test_content_absent_falls_back_to_reasoning(self):
        # content key missing entirely
        payload = self._payload(content=None, reasoning=GOOD_JSON)
        extracted = self.client._extract_content(payload)
        self.assertEqual(extracted, GOOD_JSON)

    def test_reasoning_details_collected(self):
        # content blank, JSON split across reasoning_details blocks
        details = [
            {"format": "unknown", "index": 0, "type": "reasoning.text",
             "text": '{"hints": ["H1", "H2"], "options": ["O1", "O2"], "correct_answer": "O1"}'},
        ]
        payload = self._payload(content="", reasoning="", reasoning_details=details)
        extracted = self.client._extract_content(payload)
        self.assertIn('"hints"', extracted)
        parsed = self.client._parse_json_result(extracted)
        self.assertEqual(parsed["hints"], ["H1", "H2"])

    def test_reasoning_details_with_rationale_prefix_still_parsed(self):
        # reasoning_details text has prose before the JSON; _parse_json_result's
        # find("{") fallback recovers it.
        details = [
            {"text": "Let me think: " + '{"hints": ["A"], "options": ["B", "C"], "correct_answer": "B"}'},
        ]
        payload = self._payload(content="", reasoning="", reasoning_details=details)
        extracted = self.client._extract_content(payload)
        parsed = self.client._parse_json_result(extracted)
        self.assertEqual(parsed["hints"], ["A"])

    def test_populated_content_still_used_first(self):
        # Existing behavior preserved: non-empty content wins over reasoning.
        payload = self._payload(content=GOOD_JSON, reasoning="some thinking")
        extracted = self.client._extract_content(payload)
        self.assertEqual(extracted, GOOD_JSON)

    def test_no_reasoning_returns_empty_and_does_not_raise(self):
        # content absent and no reasoning fields: _extract_content falls through
        # to str(result); _parse_json_result must yield empty hints/options
        # (the "no parseable" path) WITHOUT raising.
        payload = {"choices": [{"message": {"role": "assistant", "content": ""}}]}
        extracted = self.client._extract_content(payload)
        parsed = self.client._parse_json_result(extracted)
        self.assertEqual(parsed, {"hints": [], "options": []})

    # --- _parse_generation_result reasoning fallback ---

    def _gen_payload(self, content, reasoning=None, reasoning_details=None):
        message = {"role": "assistant", "content": content}
        if reasoning is not None:
            message["reasoning"] = reasoning
        if reasoning_details is not None:
            message["reasoning_details"] = reasoning_details
        return {"choices": [{"message": message}]}

    def test_generation_falls_back_to_reasoning_when_content_empty(self):
        # content empty, JSON lives only in reasoning -> recovery
        payload = self._gen_payload("", reasoning=GOOD_JSON)
        parsed = self.client._parse_generation_result(payload)
        self.assertEqual(parsed["hints"], self.expected_hints)
        self.assertEqual(parsed["options"], self.expected_options)

    def test_generation_falls_back_to_reasoning_when_content_garbage(self):
        # content is non-empty prose (unparseable), JSON lives in reasoning
        payload = self._gen_payload("Sorry, I cannot help with that.", reasoning=GOOD_JSON)
        parsed = self.client._parse_generation_result(payload)
        self.assertEqual(parsed["hints"], self.expected_hints)

    def test_generation_falls_back_to_reasoning_details(self):
        details = [
            {"text": 'Here is a hint:' + '{"hints": ["H1", "H2"], "options": ["O1", "O2", "O3", "O4"], "correct_answer": "O1"}'},
        ]
        payload = self._gen_payload("", reasoning="", reasoning_details=details)
        parsed = self.client._parse_generation_result(payload)
        self.assertEqual(parsed["hints"], ["H1", "H2"])

    def test_generation_prefers_content_when_it_parses(self):
        # content is good JSON; must win even if reasoning also has JSON
        payload = self._gen_payload(GOOD_JSON, reasoning=GOOD_JSON)
        parsed = self.client._parse_generation_result(payload)
        self.assertEqual(parsed["hints"], self.expected_hints)

    def test_generation_no_hint_anywhere_returns_empty(self):
        payload = self._gen_payload("no json here", reasoning="just prose")
        parsed = self.client._parse_generation_result(payload)
        self.assertEqual(parsed, {"hints": [], "options": []})

    # --- top-level `data` envelope unwrapping (Cline BYOK gateway) ---

    def _wrap_in_data(self, inner):
        # Cline BYOK API returns {"data": {"choices": [...]}, "success": true};
        # this mirrors what _post_json hands to _extract_content / parsing.
        return {"data": inner, "success": True}

    def test_extract_content_unwraps_data_envelope(self):
        content_json = '{"hints":["H1","H2"],"correct_answer":"A","distractors":["D1","D2"]}'
        message = {"role": "assistant", "content": content_json, "reasoning": "thinking"}
        wrapped = self._wrap_in_data({"choices": [{"message": message}]})
        extracted = self.client._extract_content(wrapped)
        self.assertEqual(extracted, content_json)

    def test_parse_generation_unwraps_data_envelope(self):
        content_json = '{"hints":["H1","H2"],"correct_answer":"A","distractors":["D1","D2"]}'
        message = {"role": "assistant", "content": content_json, "reasoning": "thinking"}
        wrapped = self._wrap_in_data({"choices": [{"message": message}]})
        parsed = self.client._parse_generation_result(wrapped)
        self.assertEqual(parsed["hints"], ["H1", "H2"])
        self.assertEqual(parsed["correct_answer"], "A")

    def test_reasoning_texts_unwraps_data_envelope(self):
        message = {"role": "assistant", "content": "", "reasoning": "the JSON lives here"}
        wrapped = self._wrap_in_data({"choices": [{"message": message}]})
        self.assertEqual(self.client._reasoning_texts(wrapped), ["the JSON lives here"])

    def test_data_envelope_reasoning_fallback_full_pipeline(self):
        # content empty inside a data-wrapped payload -> reasoning fallback fires
        content_json = '{"hints":["H1","H2"],"options":["O1","O2","O3","O4"],"correct_answer":"O1"}'
        message = {"role": "assistant", "content": "", "reasoning": content_json}
        wrapped = self._wrap_in_data({"choices": [{"message": message}]})
        parsed = self.client._parse_generation_result(wrapped)
        self.assertEqual(parsed["hints"], ["H1", "H2"])
        self.assertEqual(parsed["options"], ["O1", "O2", "O3", "O4"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
