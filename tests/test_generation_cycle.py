
import sys
import os
import json
import re
from unittest.mock import MagicMock

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

# Mock logger
mock_logger = MagicMock()
sys.modules['logger'] = mock_logger
sys.modules['.logger'] = mock_logger

from addon.ai_client import AIClient
from addon.card_parser import CardParser

def test_full_cycle():
    print("--- Running Full Generation Cycle Tests ---")
    client = AIClient({})
    parser = CardParser()

    # Test cases for hallucinations and malformed output
    test_cases = [
        {
            "name": "JSON Hallucination (User reported)",
            "raw": {
                "hints": ["Element 6", "Organic basis"],
                "options": ["C", "Co", "Ca", "Carbon:C {\"c1\": {\"hints\": [\"...\"], \"options\": [\"...\"]}}"]
            },
            "expected_options": ["C", "Co", "Ca", "Carbon:C"]
        },
        {
            "name": "Escaped JSON Hallucination",
            "raw": {
                "hints": ["Hint 1"],
                "options": ["O", "Oxygen:O {\\\"hints\\\": [\\\"...\\\"]}"]
            },
            "expected_options": ["O", "Oxygen:O"]
        },
        {
            "name": "Answer/Option Prefix",
            "raw": {
                "hints": ["Hint: Use logic"],
                "options": ["Option: Alpha", "Answer: Beta", "Choice: Gamma", "Delta"]
            },
            "expected_options": ["Alpha", "Beta", "Gamma", "Delta"]
        }
    ]

    for case in test_cases:
        print(f"Testing: {case['name']}")
        
        # Simulated flow
        client_cleaned = {
            "hints": [client._clean_ai_math_output(h) for h in case["raw"]["hints"]],
            "options": [client._clean_ai_math_output(o) for o in case["raw"]["options"]]
        }
        
        normalized = parser.normalize_hint_data(client_cleaned)

        if normalized["options"] == case["expected_options"]:
            print(f"  PASS: Cleaned correctly.")
        else:
            print(f"  FAIL: Mismatch.")
            print(f"    Expected: {case['expected_options']}")
            print(f"    Got:      {normalized['options']}")
            exit(1)

    # Verify Note Update and Detection
    print("\nTesting Note Update and Detection...")
    class MockNote:
        def __init__(self):
            self.data = {"Back": "Original content"}
        def __setitem__(self, key, value): self.data[key] = value
        def __getitem__(self, key): return self.data[key]
        def keys(self): return self.data.keys()
        def values(self): return self.data.values()
        def items(self): return self.data.items()
        def __contains__(self, key): return key in self.data

    mock_note = MockNote()
    mock_card = MagicMock()
    mock_card.id = 999
    mock_card.ord = 0
    
    data = {"hints": ["H1"], "options": ["O1", "O2"]}
    parser.update_note_with_hints(mock_note, data, card=mock_card)
    
    block = parser.find_hints_block(mock_note, card=mock_card)
    if block and '"c1"' in block and '"hints"' in block and '"H1"' in block:
        print("  PASS: Note updated and block detected correctly.")
    else:
        print("  FAIL: Note update or detection failed.")
        print("  Got block:", block)
        exit(1)

    # Verify candidate_providers ignores disabled_providers
    print("\nTesting disabled_providers filtering...")
    config = {
        "ai_provider": "openai",
        "api_keys": {
            "openai": "sk-123",
            "anthropic": "sk-456",
            "gemini": "sk-789"
        },
        "provider_priority": ["anthropic", "gemini", "openai"],
        "disabled_providers": ["anthropic"]
    }
    client_test = AIClient(config)
    client_test._is_provider_ready = lambda p, primary=False: True
    candidates = client_test._candidate_providers("openai")
    
    if "anthropic" not in candidates and "gemini" in candidates and "openai" in candidates:
        print("  PASS: disabled_providers successfully filtered out.")
    else:
        print(f"  FAIL: candidate selection did not filter disabled providers. Got: {candidates}")
        exit(1)

    # Verify disabled fallback models are filtered
    print("\nTesting disabled_fallback_models filtering...")
    config2 = {
        "api_keys": {"openai": "sk-123"},
        "model_fallbacks": {
            "openai": ["gpt-4o", "o1-mini", "gpt-4o-mini"]
        },
        "disabled_fallback_models": {
            "openai": ["o1-mini"]
        }
    }
    client_test2 = AIClient(config2)
    client_test2._normalize_model = lambda p, m: m
    fallback_models = client_test2._models_for_provider("openai", "gpt-4o")
    if "o1-mini" not in fallback_models and "gpt-4o-mini" in fallback_models:
        print("  PASS: disabled_fallback_models successfully filtered out.")
    else:
        print(f"  FAIL: disabled fallback models not filtered. Got: {fallback_models}")
        exit(1)

if __name__ == "__main__":
    test_full_cycle()
