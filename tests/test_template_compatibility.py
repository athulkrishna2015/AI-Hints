import html
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from addon.card_parser import CardParser

class FakeNote(dict):
    def __init__(self, fields):
        super().__init__(fields)
    def keys(self):
        return super().keys()
    def items(self):
        return super().items()
    def model(self):
        return {"name": "Basic"}

class FakeCard:
    def __init__(self, ord_):
        self.ord = ord_

class TemplateCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.parser = CardParser(storage_mode="json")

    def test_json_block_structure_for_basic_card(self):
        """Verify that basic cards get a flat JSON or keyed JSON that template.js can handle."""
        note = FakeNote({"Back": ""})
        data = {"hints": ["Hint 1"], "options": ["Option 1"], "correct_answer": "Option 1"}
        
        # For basic cards (no cloze), we currently store them as flat JSON or keyed "c1" depending on how update_note_with_hints is called
        # The template.js handles both.
        self.parser.update_note_with_hints(note, data)
        
        # Extract the JSON from the field
        match = next(iter(self.parser.find_all_hints_blocks(note)))
        import re
        json_match = re.search(r'>(.*?)</div>', match)
        payload = json.loads(html.unescape(json_match.group(1)))
        
        # template.js expects either {hints:[], options:[]} or {c1: {hints:[], options:[]}}
        if "hints" in payload:
            self.assertEqual(payload["hints"], ["Hint 1"])
        else:
            self.assertEqual(payload["c1"]["hints"], ["Hint 1"])

    def test_json_block_structure_for_cloze_card(self):
        """Verify that cloze cards get keyed JSON (c1, c2) that template.js expects."""
        note = FakeNote({"Back": ""})
        card1 = FakeCard(0) # c1
        card2 = FakeCard(1) # c2
        
        data1 = {"hints": ["H1"], "options": ["O1"]}
        data2 = {"hints": ["H2"], "options": ["O2"]}
        
        self.parser.update_note_with_hints(note, data1, card=card1)
        self.parser.update_note_with_hints(note, data2, card=card2)
        
        match = next(iter(self.parser.find_all_hints_blocks(note)))
        import re
        json_match = re.search(r'>(.*?)</div>', match)
        payload = json.loads(html.unescape(json_match.group(1)))
        
        self.assertIn("c1", payload)
        self.assertIn("c2", payload)
        self.assertEqual(payload["c1"]["hints"], ["H1"])
        self.assertEqual(payload["c2"]["hints"], ["H2"])

if __name__ == "__main__":
    unittest.main()
