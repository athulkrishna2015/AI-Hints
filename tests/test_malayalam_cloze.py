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

class TestMalayalamCloze(unittest.TestCase):
    def test_malayalam_multi_cloze_matching(self):
        """Verify that multi-cloze cards with same-ID deletions (common in Malayalam) match correctly."""
        parser = CardParser(fix_latex=True)
        
        # Note has two c2 clozes and one c1 cloze
        note_text = "{{c2::മരുത്}} + {{c2::ലോലിതം}} എന്ന് ചേർത്തെഴുതുമ്പോൾ ലഭിക്കുന്ന പദം {{c1::മരുല്ലോലിതം}} ആണ്."
        note = MockNote({"Text": note_text})
        
        # Test c2 (ord 1) - AI returns comma-separated list
        card_c2 = MockCard(ord=1)
        ai_data_c2 = {
            "hints": ["Hint"],
            "options": ["മരുത്, ലോലിതം", "മരുതം, ലോലിതം"],
            "correct_answer": "മരുത്, ലോലിതം"
        }
        
        # Update
        parser.update_note_with_hints(note, ai_data_c2, card=card_c2)
        
        # Check
        found_block = parser.find_hints_block(note, card_c2)
        self.assertIsNotNone(found_block, "Multi-cloze Malayalam c2 hints block should be matched via comma-splitting")
        
    def test_malayalam_single_cloze_matching(self):
        """Verify standard single cloze matching for Malayalam."""
        parser = CardParser(fix_latex=True)
        note_text = "{{c2::മരുത്}} + {{c2::ലോലിതം}} എന്ന് ചേർത്തെഴുതുമ്പോൾ ലഭിക്കുന്ന പദം {{c1::മരുല്ലോലിതം}} ആണ്."
        note = MockNote({"Text": note_text})
        
        # Test c1 (ord 0)
        card_c1 = MockCard(ord=0)
        ai_data_c1 = {
            "hints": ["Hint"],
            "options": ["മരുല്ലോലിതം", "മരുതലോലിതം"],
            "correct_answer": "മരുല്ലോലിതം"
        }
        
        # Update
        parser.update_note_with_hints(note, ai_data_c1, card=card_c1)
        
        # Check
        found_block = parser.find_hints_block(note, card_c1)
        self.assertIsNotNone(found_block, "Standard Malayalam c1 hints block should be found")

if __name__ == "__main__":
    unittest.main()
