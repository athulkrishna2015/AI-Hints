import unittest
from addon.card_parser import CardParser

class MockCard:
    def __init__(self, ord):
        self.ord = ord
        self.id = 12345

class MockNote:
    def __init__(self, fields, model_name="Cloze"):
        self._fields = fields
        self._model = {"name": model_name, "type": 1}
    def items(self):
        return [("Field", f) for f in self._fields]
    def model(self):
        return self._model
    def values(self):
        return self._fields

class TestClozeGeneration(unittest.TestCase):
    def test_c2_content_extraction(self):
        parser = CardParser()
        # User's note content with existing c1 JSON
        json_block = '<div class="ai-hints-json" data-ai-hints-addon-id="2119980872" contenteditable="false" data-show-hints="true" data-show-options="true" style="display:none">{ "c1": { "hints": ["foo"], "options": ["bar"], "correct_answer": "123" } }</div>'
        text = f"{{{{c2::The President can promulgate Ordinances when the Parliament is not in session under}}}} Article {{{{c1::123}}}},&nbsp;{json_block}"
        note = MockNote([text])
        
        # Check c1
        card1 = MockCard(0)
        front1, back1 = parser.get_note_content(note, card1)
        # print(f"\nC1 Front: {front1}")
        # print(f"C1 Back: {back1}")
        self.assertIn("[...]", front1)
        self.assertNotIn("ai-hints-json", front1)
        self.assertNotIn("foo", front1)
        self.assertEqual(back1, "123")
        
        # Check c2
        card2 = MockCard(1)
        front2, back2 = parser.get_note_content(note, card2)
        # print(f"\nC2 Front: {front2}")
        # print(f"C2 Back: {back2}")
        self.assertIn("[...]", front2)
        self.assertNotIn("ai-hints-json", front2)
        self.assertNotIn("foo", front2)
        self.assertEqual(back2, "The President can promulgate Ordinances when the Parliament is not in session under")

if __name__ == "__main__":
    unittest.main()
