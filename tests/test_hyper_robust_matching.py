import unittest
import sys
import os

# Add the parent directory to sys.path to import the addon
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from addon.card_parser import CardParser

class MockNote:
    def __init__(self, fields, model_name="Cloze"):
        self._fields = fields
        self._model = {"name": model_name, "type": 1} # 1 = Cloze
    
    def items(self):
        return self._fields.items()
    
    def keys(self):
        return self._fields.keys()
    
    def __getitem__(self, key):
        return self._fields[key]
    
    def __setitem__(self, key, value):
        self._fields[key] = value
        
    def model(self):
        return self._model
    
    def values(self):
        return self._fields.values()

class MockCard:
    def __init__(self, ord=0, id=123):
        self.ord = ord
        self.id = id

class TestHyperRobustMatching(unittest.TestCase):
    def setUp(self):
        self.parser = CardParser(fix_latex=True)

    def test_nested_cloze_extraction(self):
        """Card 1's answer is 'Outer Inner'. Parser should extract it correctly."""
        note_text = "{{c1::Outer {{c2::Inner}} }}"
        note = MockNote({"Text": note_text})
        
        active = self.parser._get_active_clozes_map(note)
        self.assertIn("outerinner", active["c1"])
        self.assertIn("inner", active["c2"])

    def test_nested_with_hints(self):
        note_text = "{{c1::Outer {{c2::Inner::Hint}} }}"
        note = MockNote({"Text": note_text})
        
        active = self.parser._get_active_clozes_map(note)
        # c1's answer should be "Outer Inner" (stripping the inner hint)
        self.assertIn("outerinner", active["c1"])
        self.assertIn("inner", active["c2"])

    def test_surrounding_punctuation(self):
        # AI might add quotes or a period
        stored = '"Answer."'
        note_text = "{{c1::Answer}}"
        note = MockNote({"Text": note_text})
        
        data = {"correct_answer": stored}
        self.assertTrue(self.parser._cloze_data_matches_note(data, "c1", note))

    def test_unicode_normalization(self):
        # Malayalam Chillu characters (different representations)
        # NFC vs NFD
        ans_nfc = "\u0D05\u0D2E\u0D4D\u0D2E" # അമ്മ
        ans_nfd = "\u0D05\u0D2E\u0D4D\u0D2E" # അമ്മ (these are actually same in this case, but let's try a real one)
        
        # Chillu 'n'
        # Old way: \u0D23\u0D4D\u0D20 (na + virama + joiner) - wait that's not right
        # New way: \u0D7A
        n_modern = "\u0D7A" # ൻ
        n_old = "\u0D28\u0D4D\u200D" # na + virama + zwj
        
        note_text = f"{{{{c1::{n_old}}}}}"
        note = MockNote({"Text": note_text})
        
        data = {"correct_answer": n_modern}
        self.assertTrue(self.parser._cloze_data_matches_note(data, "c1", note))

    def test_super_fuzzy_fallback(self):
        # Mismatch in brackets or minor symbols in non-math
        stored = "Economic Growth (Industrial)"
        note_text = "{{c1::Economic Growth Industrial}}"
        note = MockNote({"Text": note_text})
        
        data = {"correct_answer": stored}
        self.assertTrue(self.parser._cloze_data_matches_note(data, "c1", note))

    def test_semicolon_separator(self):
        stored = "Value 1; Value 2"
        note_text = "{{c1::Value 1}} and {{c1::Value 2}}"
        note = MockNote({"Text": note_text})
        
        data = {"correct_answer": stored}
        self.assertTrue(self.parser._cloze_data_matches_note(data, "c1", note))

if __name__ == "__main__":
    unittest.main()
