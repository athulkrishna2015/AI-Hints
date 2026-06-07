import unittest
import sys
import os
import json
import html

# Add addon directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from addon.card_parser import CardParser

class MockNote(dict):
    def __init__(self, fields):
        super().__init__(fields)
        self.id = 123
    def keys(self):
        return list(super().keys())
    def values(self):
        return list(super().values())

class TestHTMLConversion(unittest.TestCase):
    def setUp(self):
        self.parser = CardParser(storage_mode="json")

    def test_extract_from_html_blocks(self):
        # 1. Simulate a field with 3 stacked HTML blocks
        field_content = """
<div class="ai-hints-container" data-ai-hints-card-ord="0">
    <hr>
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>Hint 1A</li><li>Hint 1B</li></ul>
    <b>AI Options:</b><br><ul class="ai-hints-list"><li>Opt 1A</li><li>Opt 1B</li></ul>
</div>
<div class="ai-hints-container" data-ai-hints-card-ord="1">
    <hr>
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>Hint 2A</li></ul>
    <b>AI Options:</b><br><ul class="ai-hints-list"><li>Opt 2A</li></ul>
</div>
        """
        note = MockNote({"Field1": field_content})
        
        # 2. Extract data using refactored method
        all_blocks = self.parser._extract_all_hints_from_fields(note)
        
        self.assertEqual(len(all_blocks), 2)
        
        # Block 1 (Ord 0 -> c1)
        self.assertEqual(all_blocks[0]["card_key"], "c1")
        self.assertIn("Hint 1A", all_blocks[0]["data"]["hints"])
        self.assertIn("Opt 1B", all_blocks[0]["data"]["options"])
        
        # Block 2 (Ord 1 -> c2)
        self.assertEqual(all_blocks[1]["card_key"], "c2")
        self.assertIn("Hint 2A", all_blocks[1]["data"]["hints"])

    def test_full_conversion_cycle(self):
        # Test the same logic used in on_convert_html_to_json
        field_content = """
Text before
<div class="ai-hints-container" data-ai-hints-card-ord="0">
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>H1</li></ul>
    <b>AI Options:</b><br><ul class="ai-hints-list"><li>O1</li></ul>
</div>
        """
        note = MockNote({"Front": field_content})
        
        # Step 1: Extract
        all_blocks = self.parser._extract_all_hints_from_fields(note)
        
        # Step 2: Clear
        self.parser._remove_all_hints_from_fields(note)
        self.assertEqual(note["Front"].strip(), "Text before")
        
        # Step 3: Re-inject as JSON
        current_val = note["Front"]
        for block in all_blocks:
            current_val = self.parser._update_json_block_in_field(
                current_val, block["data"], block["card_key"], block.get("toggles", {})
            )
        
        # Verify result is a hidden JSON block
        self.assertIn('class="ai-hints-json"', current_val)
        self.assertIn('style="display:none"', current_val)
        self.assertIn('"c1":', current_val)
        self.assertIn('H1', current_val)

if __name__ == "__main__":
    unittest.main()
