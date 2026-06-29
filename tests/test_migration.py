
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
            
            current_val = parser._update_json_block_in_field(current_val, data, card_key, toggles)
        
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

    def test_clean_naked_json_logic(self):
        """Verify that only unwrapped, raw/naked AI JSON text blocks are removed, while wrapped divs and unrelated content are preserved."""
        import html
        import re
        
        div_pattern = re.compile(
            r'<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )

        def find_json_candidates(text):
            candidates = []
            start = -1
            depth = 0
            for i, char in enumerate(text):
                if char == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif char == '}':
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start != -1:
                            candidates.append((start, i + 1, text[start:i+1]))
            return candidates

        def purge_naked_json(field_val):
            if not isinstance(field_val, str) or '{' not in field_val:
                return field_val, False

            wrapped_ranges = [(m.start(), m.end()) for m in div_pattern.finditer(field_val)]
            candidates = find_json_candidates(field_val)
            if not candidates:
                return field_val, False

            field_changed = False
            for start_idx, end_idx, candidate in reversed(candidates):
                is_wrapped = any(w_start <= start_idx and end_idx <= w_end for w_start, w_end in wrapped_ranges)
                if is_wrapped:
                    continue

                clean_candidate = re.sub(r'<[^>]+>', '', candidate)
                clean_candidate = html.unescape(clean_candidate).strip()

                try:
                    parsed = json.loads(clean_candidate)
                    if isinstance(parsed, dict):
                        is_ai_hints = False
                        if "hints" in parsed or "options" in parsed or "correct_answer" in parsed:
                            is_ai_hints = True
                        elif any(isinstance(val, dict) and ("hints" in val or "options" in val) for val in parsed.values()):
                            is_ai_hints = True

                        if is_ai_hints:
                            left_str = field_val[:start_idx]
                            right_str = field_val[end_idx:]

                            left_str = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', left_str, flags=re.IGNORECASE)
                            right_str = re.sub(r'^(?:<br\s*/?>|\s|&nbsp;)+', '', right_str, flags=re.IGNORECASE)

                            field_val = left_str + right_str
                            field_changed = True
                except Exception:
                    pass

            if field_changed:
                field_val = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', field_val, flags=re.IGNORECASE)
                return field_val.strip(), True
            return field_val, False

        # Test Case 1: Wrapped block (Should not be removed)
        wrapped_block = 'Some Text <div class="ai-hints-json">{"hints": ["H1"]}</div> and more text'
        new_val, changed = purge_naked_json(wrapped_block)
        self.assertFalse(changed)
        self.assertEqual(new_val, wrapped_block)

        # Test Case 2: Naked block (Should be removed)
        naked_block = 'Some Text <br> {"hints": ["H1"]} <br> and more text'
        new_val, changed = purge_naked_json(naked_block)
        self.assertTrue(changed)
        self.assertEqual(new_val, 'Some Textand more text')

        # Test Case 3: Naked block along with a wrapped block (Only naked should be removed)
        mixed_block = 'Intro Text <br> {"hints": ["Naked"]} <br> Middle Text <div class="ai-hints-json">{"hints": ["Wrapped"]}</div> Outro'
        new_val, changed = purge_naked_json(mixed_block)
        self.assertTrue(changed)
        self.assertNotIn("Naked", new_val)
        self.assertIn("Wrapped", new_val)

        # Test Case 4: Non-AI JSON (Should not be removed)
        non_ai_block = 'Some Text {"other_key": "some_value"} and more text'
        new_val, changed = purge_naked_json(non_ai_block)
        self.assertFalse(changed)
        self.assertEqual(new_val, non_ai_block)

if __name__ == "__main__":
    unittest.main()
