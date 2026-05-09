import html
import json
import os
import re
import sys
import unittest

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


class FakeCard:
    def __init__(self, card_id, ord_):
        self.id = card_id
        self.ord = ord_


def json_payload_from_field(value):
    match = re.search(
        r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
        value,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise AssertionError("No AI-Hints JSON block found")
    return json.loads(html.unescape(match.group(1)))


class CardParserTests(unittest.TestCase):
    def test_configured_basic_fields_preserve_front_and_back(self):
        note = FakeNote(
            "Basic",
            {
                "Front": "What is &alpha;?<br><b>Choose.</b>",
                "Back": "<span>Alpha</span>",
            },
        )
        parser = CardParser([], {"Basic": ["Front", "Back"]})

        front, back = parser.get_note_content(note)

        self.assertEqual(front, "What is α? Choose.")
        self.assertEqual(back, "Alpha")

    def test_inline_mathjax_format_uses_dollar_delimiters(self):
        parser = CardParser(["Back"], mathjax_format="inline")

        data = parser.normalize_hint_data({"options": ["x_i"]})

        self.assertEqual(data["options"], ["$x_i$"])

    def test_keyed_json_updates_merge_sibling_cards(self):
        note = FakeNote("Cloze", {"Text": "Prompt", "Back": ""})
        parser = CardParser(["Back"], storage_mode="json")

        self.assertTrue(parser.update_note_with_hints(note, {"hints": ["h1"], "options": ["o1"]}, card=FakeCard(1, 0)))
        self.assertTrue(parser.update_note_with_hints(note, {"hints": ["h2"], "options": ["o2"]}, card=FakeCard(2, 1)))

        payload = json_payload_from_field(note["Back"])
        self.assertEqual(payload["c1"]["hints"], ["h1"])
        self.assertEqual(payload["c2"]["options"], ["o2"])
        self.assertEqual(note["Back"].count("ai-hints-json"), 1)

    def test_missing_keyed_card_is_not_reported_or_cleared(self):
        note = FakeNote("Cloze", {"Text": "Prompt", "Back": ""})
        parser = CardParser(["Back"], storage_mode="json")
        parser.update_note_with_hints(note, {"hints": ["h1"], "options": ["o1"]}, card=FakeCard(1, 0))
        original = note["Back"]

        self.assertIsNone(parser.find_hints_block(note, FakeCard(2, 1)))
        self.assertFalse(parser.clear_hints_from_note(note, FakeCard(2, 1)))
        self.assertEqual(note["Back"], original)

    def test_html_mode_escapes_non_math_tags(self):
        parser = CardParser(["Back"], storage_mode="html")

        block = parser.build_hints_block(
            {
                "hints": ["<script>alert(1)</script>", "<anki-mathjax>x</anki-mathjax>"],
                "options": [],
            }
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", block)
        self.assertNotIn("<script>alert(1)</script>", block)
        self.assertIn("<anki-mathjax>x</anki-mathjax>", block)


if __name__ == "__main__":
    unittest.main()
