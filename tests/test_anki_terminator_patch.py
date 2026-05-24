import unittest
import sys
import os

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from addon.anki_terminator_patch import clean_ai_hints_from_text, CleanNoteProxy, CleanCardProxy

class FakeNote(dict):
    def __init__(self, fields, fields_list=None):
        super().__init__(fields)
        self._fields_list = fields_list or list(fields.values())

    @property
    def fields(self):
        return self._fields_list

    def some_method(self):
        return "original_method_value"

class FakeCard:
    def __init__(self, note):
        self._note = note
        self.id = 12345

    def note(self):
        return self._note

    def other_card_method(self):
        return "card_method_value"

class TestAnkiTerminatorPatch(unittest.TestCase):

    def test_clean_ai_hints_from_text(self):
        # 1. Plain text should remain untouched
        self.assertEqual(clean_ai_hints_from_text("Simple text value"), "Simple text value")

        # 2. Text with only hidden JSON should be completely cleared
        hidden_json = '<div class="ai-hints-json" style="display:none">{"hints": ["h1"], "options": ["o1"]}</div>'
        self.assertEqual(clean_ai_hints_from_text(hidden_json), "")

        # 3. Text with both hidden JSON and visible container should be completely cleared
        mixed = (
            'Some start text\n'
            '<div class="ai-hints-json" style="display:none">{"hints": ["h1"], "options": ["o1"]}</div>\n'
            '<div class="ai-hints-container">\n'
            '<b>AI Hints:</b><ul><li>Hint 1</li></ul>\n'
            '</div>\n'
            'Some end text'
        )
        cleaned = clean_ai_hints_from_text(mixed)
        self.assertIn("Some start text", cleaned)
        self.assertIn("Some end text", cleaned)
        self.assertNotIn("ai-hints-json", cleaned)
        self.assertNotIn("ai-hints-container", cleaned)
        self.assertNotIn("Hint 1", cleaned)

    def test_clean_note_proxy_getitem(self):
        note = FakeNote({
            "Front": "What is alpha?<br><div class=\"ai-hints-json\" style=\"display:none\">payload</div>",
            "Back": "Alpha"
        })
        proxy = CleanNoteProxy(note)

        # Accessing Front should be cleaned
        self.assertEqual(proxy["Front"], "What is alpha?")
        # Accessing Back should be unchanged
        self.assertEqual(proxy["Back"], "Alpha")

    def test_clean_note_proxy_methods(self):
        note = FakeNote({
            "Front": "Front <div class=\"ai-hints-json\">payload</div>",
            "Back": "Back"
        })
        proxy = CleanNoteProxy(note)

        # Test keys()
        self.assertEqual(list(proxy.keys()), ["Front", "Back"])

        # Test values()
        self.assertEqual(proxy.values(), ["Front", "Back"])

        # Test items()
        self.assertEqual(proxy.items(), [("Front", "Front"), ("Back", "Back")])

        # Test get()
        self.assertEqual(proxy.get("Front"), "Front")
        self.assertEqual(proxy.get("Back"), "Back")
        self.assertEqual(proxy.get("NonExistent", "default"), "default")

        # Test len()
        self.assertEqual(len(proxy), 2)

        # Test __contains__
        self.assertTrue("Front" in proxy)
        self.assertFalse("NonExistent" in proxy)

        # Test attribute access delegation
        self.assertEqual(proxy.some_method(), "original_method_value")

        # Test fields property
        self.assertEqual(proxy.fields, ["Front", "Back"])

    def test_clean_card_proxy(self):
        note = FakeNote({
            "Text": "Base text <div class=\"ai-hints-json\">payload</div>"
        })
        card = FakeCard(note)
        proxy = CleanCardProxy(card)

        # Attribute lookup should be delegated
        self.assertEqual(proxy.id, 12345)
        self.assertEqual(proxy.other_card_method(), "card_method_value")

        # card.note() should return a CleanNoteProxy
        card_note = proxy.note()
        self.assertTrue(isinstance(card_note, CleanNoteProxy))
        self.assertEqual(card_note["Text"], "Base text")

if __name__ == "__main__":
    unittest.main()
