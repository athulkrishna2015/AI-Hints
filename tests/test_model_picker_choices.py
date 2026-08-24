"""Regression tests: Alt+click model picker includes disabled entries.

_get_model_choices() used to return only ready providers' enabled models,
hiding user-disabled (unchecked) fallback models and disabled/unready
providers entirely. The Alt+click picker must now receive the FULL universe
with explicit flags so users can force generation with any of them:

  - every entry carries `enabled`, `models` (checked ones) and
    `disabled_models` (unchecked fallbacks);
  - disabled/unready providers appear with enabled=false;
  - blacklisted/on-cooldown models remain included among enabled models.
"""
import os
import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)


def _install_aqt_mocks():
    if "aqt" in sys.modules and getattr(sys.modules["aqt"], "__aih_mocked__", False):
        return
    aqt = ModuleType("aqt")
    aqt.qt = MagicMock()
    aqt.utils = MagicMock()
    aqt.webview = MagicMock()
    aqt.theme = MagicMock()
    aqt.gui_hooks = MagicMock()
    aqt.operations = MagicMock()
    aqt.operations.deck = MagicMock()
    mw = MagicMock()
    mw.pm.profileFolder.return_value = ""
    aqt.mw = mw
    sys.modules["aqt"] = aqt
    sys.modules["aqt.qt"] = aqt.qt
    sys.modules["aqt.utils"] = aqt.utils
    sys.modules["aqt.gui_hooks"] = aqt.gui_hooks
    sys.modules["aqt.operations"] = aqt.operations
    sys.modules["aqt.operations.deck"] = aqt.operations.deck
    anki = ModuleType("anki")
    errors = ModuleType("anki.errors")

    class NotFoundError(Exception):
        pass

    errors.NotFoundError = NotFoundError
    sys.modules["anki"] = anki
    sys.modules["anki.errors"] = errors
    aqt.__aih_mocked__ = True


_install_aqt_mocks()

from addon import reviewer_hooks  # noqa: E402
from addon.ai_client import FAILED_COMBOS_CACHE  # noqa: E402


def base_config():
    return {
        "ai_provider": "openai",
        "api_keys": {
            "openai": "k-openai",
            # anthropic deliberately has NO key -> unready -> enabled=False
        },
        "models": {
            "openai": "gpt-active",
            "anthropic": "claude-active",
            "deepseek": "deepseek-chat",
        },
        "model_fallbacks": {
            "openai": ["openai-fb1", "openai-fb2", "openai-fb3"],
            "anthropic": ["claude-fb1"],
            "deepseek": ["deepseek-fb1"],
        },
        # user unchecked these two in the Fallback Priority dialog
        "disabled_fallback_models": {"openai": ["openai-fb2"], "deepseek": ["deepseek-fb1"]},
        # whole provider switched off via the Providers tab
        "disabled_providers": ["deepseek"],
    }


class ModelPickerChoicesTests(unittest.TestCase):
    def setUp(self):
        self.choices = {
            c["provider"]: c for c in reviewer_hooks._get_model_choices(base_config())
        }

    def test_enabled_provider_splits_models_and_disabled(self):
        entry = self.choices.get("openai")
        self.assertIsNotNone(entry)
        self.assertTrue(entry["enabled"])
        self.assertIn("gpt-active", entry["models"])
        self.assertIn("openai-fb1", entry["models"])
        self.assertIn("openai-fb3", entry["models"])
        self.assertNotIn("openai-fb2", entry["models"])
        self.assertEqual(entry["disabled_models"], ["openai-fb2"])

    def test_unkeyed_provider_listed_as_disabled_with_models(self):
        entry = self.choices.get("anthropic")
        self.assertIsNotNone(entry, "unready provider missing from picker")
        self.assertFalse(entry["enabled"])
        self.assertIn("claude-active", entry["models"])
        self.assertIn("claude-fb1", entry["models"])

    def test_disabled_provider_flagged_and_keeps_disabled_models(self):
        entry = self.choices.get("deepseek")
        self.assertIsNotNone(entry, "provider-disabled entry missing from picker")
        self.assertFalse(entry["enabled"])
        self.assertNotIn("deepseek-fb1", entry["models"])
        self.assertIn("deepseek-fb1", entry["disabled_models"])

    def test_no_duplicate_models_across_lists(self):
        for entry in self.choices.values():
            overlap = set(entry["models"]) & set(entry["disabled_models"])
            self.assertEqual(overlap, set(), f"overlap for {entry['provider']}: {overlap}")

    def test_enabled_providers_listed_before_disabled(self):
        ordered = reviewer_hooks._get_model_choices(base_config())
        flags = [c["enabled"] for c in ordered]
        # Stable sort: all True entries first, no False re-appearing later.
        seen_disabled = False
        for flag in flags:
            if not flag:
                seen_disabled = True
            else:
                self.assertFalse(seen_disabled, "enabled provider appears after a disabled one")

    def test_blacklisted_model_reported_but_still_selectable(self):
        # Every key-combo for openai-fb1 (its only key) is on cooldown.
        import time
        FAILED_COMBOS_CACHE[("openai", "openai-fb1", "k-openai")] = time.time() + 600
        try:
            choices = {
                c["provider"]: c for c in reviewer_hooks._get_model_choices(base_config())
            }
        finally:
            FAILED_COMBOS_CACHE.clear()
        entry = choices["openai"]
        self.assertIn("openai-fb1", entry["blacklisted"])
        # Still selectable: it must remain among the models, not moved to disabled.
        self.assertIn("openai-fb1", entry["models"])
        self.assertNotIn("openai-fb2", entry["blacklisted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
