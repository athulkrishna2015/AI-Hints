
import unittest
import os
import sys
import json
import html

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from addon.card_parser import CardParser

class FakeNote(dict):
    def __init__(self, model_name, fields):
        super().__init__(fields)
        self._model_name = model_name

    def model(self):
        return {"name": self._model_name}
    
    def flush(self):
        pass

class MigrationTests(unittest.TestCase):
    def test_migration_logic(self):
        print("--- Testing Migration Logic ---")
        parser = CardParser(storage_mode="json")
        
        # Example data provided by user
        example_block = '<div class="ai-hints-json" data-ai-hints-addon-id="2119980872" style="display:none">{"hints": ["H1"], "options": ["O1"], "correct_answer": "A", "_provider": "gemini", "_model": "gemini-flash"}</div>'
        
        note = FakeNote("Basic", {
            "Front": "Question",
            "Back": "Answer" + example_block,
            "Extra": "Some extra info"
        })
        
        # Simulation of on_migrate_data logic
        fields = list(note.keys())
        first_field = fields[0] # "Front"
        other_fields = fields[1:] # ["Back", "Extra"]
        
        # 1. Extract all blocks from all fields
        all_blocks = parser._extract_all_hints_from_fields(note)
        self.assertEqual(len(all_blocks), 1)
        self.assertEqual(all_blocks[0]["data"]["hints"], ["H1"])
        
        # 2. Check if any blocks are NOT in the first field
        blocks_in_others = []
        for f in other_fields:
            blocks = parser._extract_hints_from_field(note[f], None)
            if blocks:
                blocks_in_others.extend(blocks)
        
        self.assertEqual(len(blocks_in_others), 1)
        
        # 3. Clear and re-inject
        parser._remove_all_hints_from_fields(note)
        self.assertNotIn("ai-hints-json", note["Back"])
        
        current_val = note[first_field]
        for block in all_blocks:
            data = block["data"]
            card_key = block.get("card_key")
            toggles = block.get("toggles", {})
            
            if parser.storage_mode == "json":
                current_val = parser._update_json_block_in_field(current_val, data, card_key, toggles)
            else:
                content = parser.build_hints_block(data, toggles)
                current_val = current_val.strip() + "\n\n" + content
        
        note[first_field] = current_val
        
        self.assertIn("ai-hints-json", note["Front"])
        self.assertIn('"hints"', note["Front"])
        self.assertIn('"H1"', note["Front"])
        self.assertEqual(note["Back"], "Answer")
        print("PASS: Migration logic correctly moved block from Back to Front.")

    def test_auto_format_unformatted_blocks(self):
        """Verify that flat/legacy or unformatted JSON blocks are auto-migrated and pretty-printed."""
        parser = CardParser(storage_mode="json")
        
        # 1. Setup note with a flat, compact, and unicode-escaped legacy JSON block
        escaped_flat_json = '<div class="ai-hints-json" data-ai-hints-addon-id="2119980872" style="display:none">{"hints": ["\\u0d08"], "options": ["O1"], "correct_answer": "A"}</div>'
        note = FakeNote("Basic", {
            "Front": "Question" + escaped_flat_json,
            "Back": "Answer"
        })
        
        # 2. Trigger auto-formatting
        changed = parser.format_unformatted_blocks_in_note(note)
        self.assertTrue(changed)
        
        # 3. Verify it was migrated to keyed 'c1' and unescaped to actual Malayalam characters with pretty indent!
        front_val = note["Front"]
        self.assertIn('"c1"', front_val) # Wrapped in c1
        self.assertIn('"ഈ"', front_val)   # Unescaped from \u0d08 to actual character
        self.assertIn('\n  "c1": {', front_val) # Indented

if __name__ == "__main__":
    unittest.main()
