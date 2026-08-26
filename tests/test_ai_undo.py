"""Functional tests for the AI-update undo stack (Ctrl+Alt+Z).

Covers the pure core added for option-B undo:
  - _capture_ai_snapshot: finds the current per-card JSON block
  - _apply_restore_to_fields: swaps back a replaced result / strips AI data
  - stack LIFO behaviour incl. per-card isolation and size cap
"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock as _M
from types import ModuleType
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.dont_write_bytecode = True

# Mock aqt / mw exactly like the other GUI-touching suites do.
aqt = ModuleType('aqt')
sys.modules['aqt'] = aqt
aqt.qt = MagicMock()
sys.modules['aqt.qt'] = aqt.qt
aqt.utils = MagicMock()
sys.modules['aqt.utils'] = aqt.utils
aqt.webview = MagicMock()
sys.modules['aqt.webview'] = aqt.webview
aqt.gui_hooks = MagicMock()
sys.modules['aqt.gui_hooks'] = aqt.gui_hooks
aqt.mw = MagicMock()
sys.modules['aqt.mw'] = aqt.mw
for cls in ('QDialog', 'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QLabel',
            'QSpinBox', 'QTimer', 'Qt'):
    setattr(aqt.qt, cls, MagicMock)
aqt.mw.addonManager.getConfig.return_value = {}

sys.modules['addon.logger'] = MagicMock()

from addon.reviewer_hooks import (  # noqa: E402
    _capture_ai_snapshot, _apply_restore_to_fields,
    _push_ai_undo, _pop_ai_undo_for_card, _ai_undo_stack, MAX_AI_UNDO_STACK,
)
from addon.card_parser import CardParser  # noqa: E402


def make_block(cid: str, ord_: int, payload: dict) -> str:
    parser = CardParser()
    return (
        f'<div class="ai-hints-json" data-ai-hints-card-id="{cid}" '
        f'data-ai-hints-card-ord="{ord_}" style="display:none">'
        f'{parser.serialize_json_payload(payload)}</div>'
    )


def payload(hint: str, src: str = "Paris") -> dict:
    return {
        "c1": {
            "hints": [hint, "h2", "h3"],
            "options": ["o1", "o2", "o3", "o4"],
            "correct_answer": "o1",
            "_src": src,
        }
    }


class FakeNote:
    id = 12345

    def __init__(self, fields):
        self.fields = list(fields)

    def values(self):
        return self.fields

    def model(self):
        return {"name": "Cloze", "type": 1}


class FakeCard:
    def __init__(self, note, ord_=0, cid=111):
        self._note = note
        self.ord = ord_
        self.id = cid

    def note(self):
        return self._note


class AiUndoTests(unittest.TestCase):
    def setUp(self):
        _ai_undo_stack.clear()

    def tearDown(self):
        _ai_undo_stack.clear()

    def _make_card(self, hint="h1"):
        block1 = make_block(111, 0, payload(hint))
        note = FakeNote([f'The capital {{{{c1::Paris}}}} is big. {block1}', ''])
        return FakeCard(note), block1

    def test_a_capture_finds_current_block(self):
        card, block1 = self._make_card("h1")
        snap = _capture_ai_snapshot(card)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["card_id"], 111)
        self.assertEqual(snap["field_idx"], 0)
        self.assertIn('"h1"', snap["block_html"])

    def test_b_restore_swaps_replaced_result_back(self):
        card, block1 = self._make_card("h1")
        snap = _capture_ai_snapshot(card)

        # Simulate a second write overwriting the first result (e.g. the
        # higher-priority linger result replacing the fast fallback).
        block2 = make_block(111, 0, payload("LATE"))
        card.note().fields[0] = card.note().fields[0].replace(block1, block2)

        new_fields, msg, changed = _apply_restore_to_fields(
            list(card.note().fields), card, snap
        )
        self.assertTrue(changed)
        self.assertIn(block1, new_fields[0])
        self.assertNotIn(block2, new_fields[0])

    def test_c_restore_none_strips_ai_data_back_to_original(self):
        card, block1 = self._make_card("h1")
        snap_none = {"card_id": 111, "note_id": 12345, "field_idx": 0,
                     "block_html": None}

        new_fields, msg, changed = _apply_restore_to_fields(
            list(card.note().fields), card, snap_none
        )
        self.assertTrue(changed)
        self.assertNotIn("ai-hints-json", new_fields[0])
        self.assertIn("{{c1::Paris}}", new_fields[0])  # note content intact

        # Already clean -> reported as no-op
        _, _, changed2 = _apply_restore_to_fields(new_fields, card, snap_none)
        self.assertFalse(changed2)

    def test_d_stack_is_lifo_per_card_and_capped(self):
        base = {"card_id": 1, "note_id": 9, "field_idx": 0, "block_html": "<div/>"}
        other = {"card_id": 2, "note_id": 9, "field_idx": 0, "block_html": None}
        for i in range(MAX_AI_UNDO_STACK + 5):
            _push_ai_undo(dict(base, block_html=f"<div v{i}/>"))
        _push_ai_undo(other)

        self.assertEqual(len(_ai_undo_stack), MAX_AI_UNDO_STACK)  # cap enforced
        got = _pop_ai_undo_for_card(2)
        self.assertEqual(got["card_id"], 2)          # isolated by card
        got1 = _pop_ai_undo_for_card(1)
        self.assertTrue(got1["block_html"].endswith('/>'))
        self.assertIsNone(_pop_ai_undo_for_card(999))  # unknown card -> None

    def test_e_redo_walks_forward_again(self):
        from addon import reviewer_hooks as rh

        card, block1 = self._make_card("h1")
        # Pre-write snapshot of the fast result...
        snap_fast = {"card_id": 111, "note_id": 12345, "field_idx": 0,
                     "block_html": make_block(111, 0, payload("FAST"))}
        rh._push_ai_undo(snap_fast)
        # ...then the "linger" write replaces it.
        block_late = make_block(111, 0, payload("LATE"))
        card.note().fields[0] = (
            f'The capital {{{{c1::Paris}}}} is big. {block_late}'
        )

        rh.mw.reviewer.card = card
        rh.undo_last_ai_update()   # back to FAST
        self.assertIn('"FAST"', card.note().fields[0])
        self.assertNotIn('"LATE"', card.note().fields[0])

        rh.redo_last_ai_update()   # forward to LATE again
        self.assertIn('"LATE"', card.note().fields[0])
        self.assertNotIn('"FAST"', card.note().fields[0])

        # The redo displaced the FAST state -> undo works once more.
        rh.undo_last_ai_update()
        self.assertIn('"FAST"', card.note().fields[0])

    def test_f_new_write_clears_redo(self):
        from addon import reviewer_hooks as rh

        card, block1 = self._make_card("h1")
        rh._ai_redo_stack.append({"card_id": 111, "note_id": 12345,
                                  "field_idx": 0, "block_html": "<div/>"})
        # Simulate the pre-write hook of a fresh AI write.
        rh._clear_redo_for_card(card.id)
        rh.mw.reviewer.card = card
        rh.redo_last_ai_update()  # must be a safe no-op
        self.assertEqual(len(rh._ai_redo_stack), 0)
        self.assertIn('"h1"', card.note().fields[0])  # note untouched
        rh._ai_redo_stack.clear()

    def test_g_shortcuts_registered(self):
        from addon.reviewer_hooks import on_state_shortcuts_will_change
        aqt.mw.addonManager.getConfig.return_value = {
            "shortcuts": {"modifier": "alt"}
        }
        self.addCleanup(setattr, aqt.mw.addonManager.getConfig, "return_value", {})
        shortcuts_list = []
        on_state_shortcuts_will_change("review", shortcuts_list)
        keys = [s[0] for s in shortcuts_list]
        self.assertIn("Ctrl+Alt+Z", keys)
        self.assertIn("Ctrl+Alt+Shift+Z", keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
