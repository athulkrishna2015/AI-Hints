import unittest
import sys
import os
import re
import html
import json

# Add addon directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from addon.card_parser import CardParser

class MockCard:
    def __init__(self, id, ord):
        self.id = id
        self.ord = ord

class MockNote(dict):
    def __init__(self, fields):
        super().__init__(fields)
        self.id = 123
    def keys(self):
        return list(super().keys())
    def values(self):
        return list(super().values())
    def cards(self):
        return [MockCard(1, 0), MockCard(2, 1)]

class TestJsonOnlyStorage(unittest.TestCase):
    def setUp(self):
        # Initialize parser WITHOUT storage_mode (now hardcoded to 'json')
        self.parser = CardParser()

    def test_new_generation_is_json(self):
        """Ensure all new generations produce invisible JSON blocks by default."""
        note = MockNote({"Front": "Text with {{c1::cloze}}"})
        card = MockCard(101, 0)
        data = {"hints": ["H1"], "options": ["A", "B"]}
        
        self.parser.update_note_with_hints(note, data, card=card)
        
        # Verify result format
        self.assertIn('class="ai-hints-json"', note["Front"])
        self.assertIn('style="display:none"', note["Front"])
        self.assertNotIn('ai-hints-container', note["Front"]) # HTML class should not be used for wrapping new JSON

    def test_merging_legacy_html_into_json(self):
        """Verify that existing HTML blocks are correctly converted and merged into JSON."""
        legacy_html = """
Text
<div class="ai-hints-container" data-ai-hints-card-ord="0">
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>Legacy Hint</li></ul>
</div>
        """
        note = MockNote({"Front": legacy_html})
        
        # New generation for card 2 (c2)
        card2 = MockCard(102, 1)
        data2 = {"hints": ["New JSON Hint"], "options": ["C"]}
        
        self.parser.update_note_with_hints(note, data2, card=card2)
        
        # Result should be a SINGLE JSON block containing both
        self.assertIn('class="ai-hints-json"', note["Front"])
        self.assertNotIn('ai-hints-container', note["Front"]) # Should have been replaced
        
        # Verify data integrity
        match = re.search(r'ai-hints-json.*?>(.*?)</div>', note["Front"], re.DOTALL)
        payload = json.loads(html.unescape(match.group(1)))
        self.assertEqual(payload["c1"]["hints"], ["Legacy Hint"])
        self.assertEqual(payload["c2"]["hints"], ["New JSON Hint"])

if __name__ == "__main__":
    unittest.main()
