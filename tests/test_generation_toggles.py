import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

mock_logger = MagicMock()
sys.modules["logger"] = mock_logger
sys.modules[".logger"] = mock_logger

from addon import ai_client as ai_mod
from addon.ai_client import AIClient


class GenerationToggleTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "addon", "config.json"), "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.front = "What is the capital of France?"
        self.back = "Paris. It is known as the City of Light."
        # Provider trace: records every call to _call_provider (network mocked out)
        self.calls = []
        self._net_patch = patch.object(ai_mod, "_check_network_online", lambda: True)
        self._net_patch.start()
        self._netstate_patch = patch.object(ai_mod, "_NETWORK_STATE", {"online": True})
        self._netstate_patch.start()
        self.addCleanup(self._net_patch.stop)
        self.addCleanup(self._netstate_patch.stop)

    def _make_client(self, **overrides):
        config = dict(self.config)
        config.update(overrides)
        client = AIClient(config)

        def fake_call_provider(provider, system_prompt, prompt, override_model=""):
            self.calls.append((provider, system_prompt))
            return {"hints": ["h1", "h2", "h3"], "options": ["Paris", "Rome", "Madrid"], "correct_answer": "Paris"}

        client._call_provider = fake_call_provider
        client._candidate_providers = lambda primary: ["gemini"]
        client._is_provider_ready = lambda provider, primary=False: True
        return client

    def test_both_enabled_by_default(self):
        client = self._make_client()
        res = client.generate_options(self.front, self.back)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("hints", res)
        self.assertIn("options", res)
        self.assertIn("correct_answer", res)

    def test_both_disabled_no_api_call(self):
        client = self._make_client(
            generate_hints_enabled=False, generate_options_enabled=False
        )
        res = client.generate_options(self.front, self.back)
        self.assertEqual(res, {"hints": [], "options": []})
        self.assertEqual(len(self.calls), 0, "No provider call should happen")

    def test_hints_only(self):
        client = self._make_client(generate_hints_enabled=True, generate_options_enabled=False)
        res = client.generate_options(self.front, self.back)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("hints", res)
        # Prompt must ask for hints only
        self.assertIn("Generate 3 conceptual hints ONLY", self.calls[0][1])
        # Options/correct_answer must be stripped from the result
        self.assertNotIn("options", res)
        self.assertNotIn("correct_answer", res)
        self.assertNotIn("distractors", res)

    def test_options_only(self):
        client = self._make_client(generate_hints_enabled=False, generate_options_enabled=True)
        res = client.generate_options(self.front, self.back)
        self.assertEqual(len(self.calls), 1)
        # Prompt must ask for options and NO hints
        self.assertIn("NO hints", self.calls[0][1])
        self.assertNotIn("hints", res)
        self.assertIn("options", res)

    def test_test_calls_still_work_when_disabled(self):
        # Provider/model testing in settings must keep working even when both toggles are off.
        from addon.logger import log_context
        log_context.source = "model_test"
        try:
            client = self._make_client(
                generate_hints_enabled=False, generate_options_enabled=False
            )
            res = client.generate_options(self.front, self.back)
        finally:
            log_context.source = None
        self.assertEqual(len(self.calls), 1)
        self.assertIn("hints", res)
        self.assertIn("options", res)

    def test_mnemonic_disabled_by_default(self):
        """Without the flag, the prompt must ask for exactly 3 conceptual hints."""
        client = self._make_client()
        client.generate_options(self.front, self.back)
        system_prompt = self.calls[0][1]
        self.assertIn("exactly 3 conceptual hints", system_prompt)
        self.assertNotIn("MNEMONIC HINT", system_prompt)

    def test_mnemonic_enabled_asks_for_4th_hint(self):
        """With mnemonic_hint_enabled, the prompt must request a 4th mnemonic hint."""
        client = self._make_client(mnemonic_hint_enabled=True)
        res = client.generate_options(self.front, self.back)
        system_prompt = self.calls[0][1]
        self.assertIn("MNEMONIC HINT", system_prompt)
        self.assertIn("(3) mnemonic/memory trick", system_prompt)
        self.assertIn("(4) discriminating clue", system_prompt)
        # Result shape unchanged: the mnemonic is just an extra entry in 'hints'.
        self.assertIn("hints", res)

    def test_mnemonic_enabled_hints_only_mode(self):
        """Hints-only mode must also request the mnemonic as hint 3."""
        client = self._make_client(mnemonic_hint_enabled=True, generate_options_enabled=False)
        client.generate_options(self.front, self.back)
        system_prompt = self.calls[0][1]
        self.assertIn("MNEMONIC HINT", system_prompt)
        self.assertIn("4 hints ONLY, in this order: (1) brief context, (2) key concept, (3) mnemonic/memory trick, (4) discriminating clue", system_prompt)

    def test_mnemonic_moves_warning_to_hint_4(self):
        """Factually-wrong warning (⚠️) must move to hint 4 when the mnemonic is hint 3."""
        client = self._make_client(mnemonic_hint_enabled=True)
        client.generate_options(self.front, self.back)
        system_prompt = self.calls[0][1]
        self.assertIn("hint 4 must begin exactly with '⚠️'", system_prompt)
        self.assertIn("overrides any earlier instruction placing the warning on hint 3", system_prompt)

    def test_warning_stays_on_hint_3_without_mnemonic(self):
        """Default (mnemonic off) keeps the original warning-on-hint-3 behavior."""
        client = self._make_client()
        client.generate_options(self.front, self.back)
        system_prompt = self.calls[0][1]
        self.assertIn("hint 3 begin exactly with `⚠️`", system_prompt)

    def test_mnemonic_off_when_hints_disabled(self):
        """Options-only generation must never mention the mnemonic section."""
        client = self._make_client(mnemonic_hint_enabled=True, generate_hints_enabled=False)
        client.generate_options(self.front, self.back)
        system_prompt = self.calls[0][1]
        self.assertNotIn("MNEMONIC HINT", system_prompt)
        self.assertIn("NO hints", system_prompt)


if __name__ == "__main__":
    unittest.main()