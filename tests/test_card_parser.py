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
    def __init__(self, model_name, fields, templates=None):
        super().__init__(fields)
        self._model_name = model_name
        self._templates = templates or []

    def model(self):
        return {"name": self._model_name, "tmpls": self._templates}


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
        parser = CardParser()

        front, back = parser.get_note_content(note)

        self.assertEqual(front, "What is α? Choose.")
        self.assertEqual(back, "Alpha")

    def test_inline_mathjax_format_uses_dollar_delimiters(self):
        parser = CardParser(mathjax_format="inline", fix_latex=True)

        data = parser.normalize_hint_data({"options": ["x_i"]})

        self.assertEqual(data["options"], ["$x_i$"])

    def test_keyed_json_updates_merge_sibling_cards(self):
        note = FakeNote("Cloze", {"Text": "Prompt", "Back": ""})
        parser = CardParser(storage_mode="json")

        self.assertTrue(parser.update_note_with_hints(note, {"hints": ["h1"], "options": ["o1"]}, card=FakeCard(1, 0)))
        self.assertTrue(parser.update_note_with_hints(note, {"hints": ["h2"], "options": ["o2"]}, card=FakeCard(2, 1)))

        payload = json_payload_from_field(note["Text"])
        self.assertEqual(payload["c1"]["hints"], ["h1"])
        self.assertEqual(payload["c2"]["options"], ["o2"])
        self.assertEqual(note["Text"].count("ai-hints-json"), 1)

    def test_missing_keyed_card_is_not_reported_or_cleared(self):
        note = FakeNote("Cloze", {"Text": "Prompt", "Back": ""})
        parser = CardParser(storage_mode="json")
        parser.update_note_with_hints(note, {"hints": ["h1"], "options": ["o1"]}, card=FakeCard(1, 0))
        original = note["Text"]

        self.assertIsNone(parser.find_hints_block(note, FakeCard(2, 1)))
        self.assertFalse(parser.clear_hints_from_note(note, FakeCard(2, 1)))
        self.assertEqual(note["Text"], original)

    def test_unscoped_legacy_json_does_not_block_sibling_auto_generation(self):
        parser = CardParser(storage_mode="json")
        note = FakeNote(
            "Cloze",
            {
                "Text": "Prompt" + parser.build_hints_block({"hints": ["old"], "options": ["old option"]}),
                "Back": "",
            },
        )

        self.assertIsNotNone(parser.find_hints_block(note, FakeCard(1, 0)))
        self.assertIsNone(parser.find_hints_block(note, FakeCard(2, 1)))

    def test_retains_data_for_other_clozes(self):
        # Verification of the fix: updating one cloze should NOT purge others
        # even if they have different answers (since we removed correct_answer validation).
        parser = CardParser(storage_mode="json")
        note = FakeNote(
            "Cloze",
            {
                "Text": "{{c1::A}} and {{c2::B}}",
                "Back": "",
            },
        )
        
        initial_data = {
            "c1": {"hints": ["h1"], "options": ["o1"]},
            "c2": {"hints": ["h2"], "options": ["o2"]}
        }
        note["Text"] += "\n\n" + parser.build_hints_block(initial_data)
        
        parser.update_note_with_hints(
            note,
            {"hints": ["h1new"], "options": ["o1new"]},
            card=FakeCard(1, 0)
        )
        
        payload = json_payload_from_field(note["Text"])
        self.assertIn("c1", payload)
        self.assertEqual(payload["c1"]["hints"], ["h1new"])
        self.assertIn("c2", payload) # SUCCESS: Retention of other keys

    def test_mismatched_cloze_payload_is_reported_as_existing_if_key_present(self):
        # Behavior changed: we no longer check the 'correct_answer' content, only the key presence.
        parser = CardParser(storage_mode="json")
        note = FakeNote(
            "Cloze",
            {
                "Text": "{{c1::Mumbai}} and {{c2::financial}}",
                "Back": "",
            },
        )
        note["Text"] += parser.build_hints_block({
            "c2": {
                "hints": ["copied but key matches"],
                "options": ["nose ring"],
            },
        })

        self.assertIsNone(parser.find_hints_block(note, FakeCard(1, 0)))
        self.assertIsNotNone(parser.find_hints_block(note, FakeCard(2, 1)))

    def test_html_mode_escapes_non_math_tags(self):
        parser = CardParser(storage_mode="html")

        block = parser.build_hints_block(
            {
                "hints": ["<script>alert(1)</script>", "<anki-mathjax>x</anki-mathjax>"],
                "options": [],
            }
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", block)
        self.assertNotIn("<script>alert(1)</script>", block)
        self.assertIn("&lt;anki-mathjax&gt;x&lt;/anki-mathjax&gt;", block)

    def test_missing_cloze_returns_empty_content(self):
        note = FakeNote("Cloze", {"Text": "This is {{c1::cloze 1}}."})
        parser = CardParser()

        # Card 1 (ord 0) should find c1
        front, back = parser.get_note_content(note, card=FakeCard(1, 0))
        self.assertEqual(back, "cloze 1")

        # Card 2 (ord 1) should NOT find c2 and return empty strings
        front, back = parser.get_note_content(note, card=FakeCard(2, 1))
        self.assertEqual(front, "")
        self.assertEqual(back, "")


    def test_reversed_card_swaps_front_and_back(self):
        """For 'Basic (and reversed card)', card.ord==1 should swap front and back."""
        # Simulate the two templates of 'Basic (and reversed card)'
        templates = [
            {"qfmt": "{{Front}}", "afmt": "{{Back}}"},   # ord 0: normal
            {"qfmt": "{{Back}}",  "afmt": "{{Front}}"},  # ord 1: reversed
        ]
        note = FakeNote(
            "Basic (and reversed card)",
            {"Front": "Capital of France", "Back": "Paris"},
            templates=templates,
        )
        parser = CardParser()

        # Normal card (ord 0): front=Front field, back=Back field
        front, back = parser.get_note_content(note, card=FakeCard(1, 0))
        self.assertEqual(front, "Capital of France")
        self.assertEqual(back, "Paris")

        # Reversed card (ord 1): front=Back field, back=Front field
        front, back = parser.get_note_content(note, card=FakeCard(2, 1))
        self.assertEqual(front, "Paris")
        self.assertEqual(back, "Capital of France")

    def test_reversed_card_with_filters_swaps_front_and_back(self):
        """For 'Basic (and reversed card)' templates with filters or spaces, it should still correctly swap."""
        templates = [
            {"qfmt": "{{type:Front}}", "afmt": "{{Back}}"},   # ord 0: normal
            {"qfmt": "{{type:Back}}",  "afmt": "{{Front}}"},  # ord 1: reversed
        ]
        note = FakeNote(
            "Basic (and reversed card)",
            {"Front": "Capital of France", "Back": "Paris"},
            templates=templates,
        )
        parser = CardParser()

        # Reversed card with filter (ord 1)
        front, back = parser.get_note_content(note, card=FakeCard(2, 1))
        self.assertEqual(front, "Paris")
        self.assertEqual(back, "Capital of France")

    def test_remove_warning_hint_from_note(self):
        parser = CardParser(storage_mode="json")
        note = FakeNote("Cloze", {"Text": "Prompt", "Back": ""})
        
        # Test JSON mode warning removal
        initial_data = {
            "c1": {"hints": ["Fine hint", "⚠️ Warning hint", "Another hint"], "options": []}
        }
        note["Text"] = "Prompt" + parser.build_hints_block(initial_data)
        
        self.assertTrue(parser.remove_warning_hint_from_note(note, card=FakeCard(1, 0)))
        
        payload = json_payload_from_field(note["Text"])
        self.assertEqual(payload["c1"]["hints"], ["Fine hint", "Another hint"])
        
        # Test HTML mode warning removal
        parser_html = CardParser(storage_mode="html")
        note_html = FakeNote("Basic", {"Front": "Front", "Back": ""})
        block = parser_html.build_hints_block({
            "hints": ["First hint", "⚠️ Warning hint", "Third hint"],
            "options": []
        })
        note_html["Back"] = "Back" + block
        
        self.assertTrue(parser_html.remove_warning_hint_from_note(note_html))
        self.assertIn("First hint", note_html["Back"])
        self.assertNotIn("⚠️ Warning hint", note_html["Back"])
        self.assertIn("Third hint", note_html["Back"])

    def test_clear_hints_clears_skipped_state(self):
        parser = CardParser(storage_mode="json")
        note = FakeNote("Cloze", {"Text": "Prompt", "Back": ""})
        
        # Mark card 1 (ord 0) as skipped
        parser.update_note_with_hints(note, {"hints": [], "options": [], "_skipped": True}, card=FakeCard(1, 0))
        self.assertIsNotNone(parser.find_hints_block(note, FakeCard(1, 0)))
        
        # Clear hints
        self.assertTrue(parser.clear_hints_from_note(note, FakeCard(1, 0)))
        
        # Verify block is fully cleared (since there are no other clozes)
        self.assertIsNone(parser.find_hints_block(note, FakeCard(1, 0)))
        self.assertNotIn("ai-hints-json", note["Text"])


if __name__ == "__main__":
    unittest.main()

