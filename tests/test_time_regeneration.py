import unittest
import os
import sys
import json
import html
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from addon.reviewer_hooks import _time_less_than, _card_saved_generation_time
from addon.card_parser import CardParser

class FakeNote(dict):
    def __init__(self, fields):
        super().__init__(fields)
    def keys(self):
        return super().keys()
    def items(self):
        return super().items()
    def model(self):
        return {"name": "Cloze"}

class FakeCard:
    def __init__(self, ord_):
        self.ord = ord_
    def note(self):
        return self._note

class TimeRegenerationTests(unittest.TestCase):
    def test_time_less_than(self):
        # Precise datetime comparison
        self.assertTrue(_time_less_than("2026-06-06 18:49:54", "2026-06-06 19:00:00"))
        self.assertFalse(_time_less_than("2026-06-06 19:00:00", "2026-06-06 18:49:54"))
        self.assertFalse(_time_less_than("2026-06-06 19:00:00", "2026-06-06 19:00:00"))

        # Date only comparison
        self.assertTrue(_time_less_than("2026-06-05", "2026-06-06"))
        self.assertFalse(_time_less_than("2026-06-06", "2026-06-05"))

        # Mixed comparisons (truncating/matching lengths)
        self.assertTrue(_time_less_than("2026-06-05 18:00:00", "2026-06-06"))
        self.assertTrue(_time_less_than("2026-06-06 12:00:00", "2026-06-06 18:00"))
        self.assertFalse(_time_less_than("2026-06-06 18:00:00", "2026-06-06 12:00"))

        # Invalid/Empty inputs
        self.assertFalse(_time_less_than("", "2026-06-06"))
        self.assertFalse(_time_less_than("2026-06-06", ""))

    def test_card_saved_generation_time_extraction(self):
        parser = CardParser(storage_mode="json")
        note = FakeNote({"Text": "Some text", "Back": ""})
        
        # Build hints payload with a generation timestamp
        data = {
            "c1": {
                "hints": ["H1"],
                "options": ["O1"],
                "correct_answer": "Ans",
                "_generated_at": "2026-06-06 18:00:00"
            }
        }
        note["Text"] += "\n\n" + parser.build_hints_block(data)
        
        card = FakeCard(0) # c1
        card._note = note
        
        saved_time = _card_saved_generation_time(card)
        self.assertEqual(saved_time, "2026-06-06 18:00:00")

if __name__ == "__main__":
    unittest.main()
