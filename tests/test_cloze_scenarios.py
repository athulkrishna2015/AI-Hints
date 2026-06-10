import unittest
import os
import sys

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from addon.card_parser import CardParser

class MockCard:
    def __init__(self, ord, id=12345):
        self.ord = ord
        self.id = id

class MockNote(dict):
    def __init__(self, fields, model_name="Cloze", cards=None):
        super().__init__(fields)
        self._model = {"name": model_name, "type": 1 if "cloze" in model_name.lower() else 0}
        self._cards = cards or []
    def items(self):
        return list(super().items())
    def model(self):
        return self._model
    def values(self):
        return list(super().values())
    def cards(self):
        return self._cards


class TestClozeScenarios(unittest.TestCase):
    def setUp(self):
        self.parser = CardParser()

    def test_nested_cloze_extraction(self):
        # {{c1::outer {{c2::inner}}}}
        text = "{{c1::outer {{c2::inner}}}}"
        note = MockNote({"Text": text})
        
        # Test C1 extraction
        card1 = MockCard(0)
        front1, back1 = self.parser.get_note_content(note, card1)
        self.assertIn("outer inner", back1)
        self.assertIn("Current cloze deletion: [...]", front1)

        # Test C2 extraction
        card2 = MockCard(1)
        front2, back2 = self.parser.get_note_content(note, card2)
        self.assertEqual(back2, "inner")
        self.assertIn("outer Current cloze deletion: [...]", front2)

    def test_cloze_with_hint(self):
        # {{c1::answer::hint}}
        text = "{{c1::Paris::Capital}}"
        note = MockNote({"Text": text})
        
        card1 = MockCard(0)
        front1, back1 = self.parser.get_note_content(note, card1)
        self.assertEqual(back1, "Paris")
        self.assertIn("[...] (existing hint: Capital)", front1)

    def test_broken_cloze(self):
        # Missing closing braces
        text = "This is {{c1::broken"
        note = MockNote({"Text": text})
        
        card1 = MockCard(0)
        front1, back1 = self.parser.get_note_content(note, card1)
        # Should ideally handle it gracefully
        # Current implementation might fail or return empty back
        self.assertEqual(back1, "") # It currently skips malformed tags

    def test_mathjax_inside_cloze(self):
        text = "{{c1::\\(x^2\\)}}"
        note = MockNote({"Text": text})
        
        card1 = MockCard(0)
        front1, back1 = self.parser.get_note_content(note, card1)
        self.assertEqual(back1, "\\(x^2\\)")
        self.assertIn("[...]", front1)

    def test_cloze_inside_mathjax(self):
        text = "\\( {{c1::x}}^2 \\)"
        note = MockNote({"Text": text})
        
        card1 = MockCard(0)
        front1, back1 = self.parser.get_note_content(note, card1)
        self.assertEqual(back1, "x")
        self.assertIn("\\( Current cloze deletion: [...]^2 \\)", front1)

    def test_get_orphaned_hints_detects_cloze_orphan_when_card_exists_but_no_tag(self):
        # Text has c1 and c2, but NOT c3
        text = (
            "{{c1::Paris}}, {{c2::France}} "
            "<div class=\"ai-hints-json\" style=\"display:none\">"
            "{\"c1\": {\"hints\": [\"a\"]}, \"c2\": {\"hints\": [\"b\"]}, \"c3\": {\"hints\": [\"c\"]}}"
            "</div>"
        )
        # However, note.cards() has cards for ord 0, 1, 2 (meaning card 3 still exists in DB)
        cards = [MockCard(0, 101), MockCard(1, 102), MockCard(2, 103)]
        note = MockNote({"Text": text}, model_name="Cloze", cards=cards)
        
        orphans = self.parser.get_orphaned_hints(note)
        # It should detect c3 as orphaned because the {{c3::}} tag is missing from fields
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0][1], "c3")
        self.assertEqual(orphans[0][2], {"hints": ["c"]})

    def test_get_orphaned_hints_non_cloze_note(self):
        # A non-cloze (Basic) note with active template card 0 (ord=0)
        # JSON has c1 and c2
        text = (
            "Front content"
            "<div class=\"ai-hints-json\" style=\"display:none\">"
            "{\"c1\": {\"hints\": [\"a\"]}, \"c2\": {\"hints\": [\"b\"]}}"
            "</div>"
        )
        cards = [MockCard(0, 201)] # card ord 0 exists, card ord 1 does not
        note = MockNote({"Text": text}, model_name="Basic", cards=cards)
        
        orphans = self.parser.get_orphaned_hints(note)
        # It should detect c2 as orphaned because non-cloze card ord 1 is missing
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0][1], "c2")


if __name__ == "__main__":
    unittest.main()
