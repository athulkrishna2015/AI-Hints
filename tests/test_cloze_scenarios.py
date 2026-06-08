import unittest
import os
import sys

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from addon.card_parser import CardParser

class MockCard:
    def __init__(self, ord):
        self.ord = ord
        self.id = 12345

class MockNote(dict):
    def __init__(self, fields, model_name="Cloze"):
        super().__init__(fields)
        self._model = {"name": model_name, "type": 1}
    def items(self):
        return list(super().items())
    def model(self):
        return self._model
    def values(self):
        return super().values()

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

    def test_active_cloze_map_with_nesting(self):
        text = "{{c1::outer {{c2::inner}}}}"
        note = MockNote({"Text": text})
        
        cloze_map = self.parser._get_active_clozes_map(note)
        # Normalized versions
        self.assertIn("c1", cloze_map)
        self.assertIn("c2", cloze_map)
        
        # c1 answer should be "outer inner" (normalized)
        # Note: _normalized_answer_text strips whitespace
        self.assertIn("outerinner", list(cloze_map["c1"]))
        self.assertIn("inner", list(cloze_map["c2"]))

    def test_mathjax_with_double_braces_not_cloze(self):
        # Some LaTeX uses {{ }} which is not a cloze if it doesn't match c\d+::
        text = "\\( \\text{val} = {{ value }} \\)"
        note = MockNote({"Text": text})
        
        cloze_map = self.parser._get_active_clozes_map(note)
        self.assertEqual(len(cloze_map), 0)

if __name__ == "__main__":
    unittest.main()
