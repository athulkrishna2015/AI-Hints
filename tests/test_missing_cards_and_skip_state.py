import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from types import ModuleType

# --- Mock aqt/Anki before importing reviewer_hooks (same pattern as test_pregeneration_logic.py)
mock_aqt = MagicMock()
sys.modules['aqt'] = mock_aqt

mock_qt = ModuleType('aqt.qt')
sys.modules['aqt.qt'] = mock_qt

class DummySignal:
    def connect(self, *args): pass

class Dummy:
    def __init__(self, *args, **kwargs):
        self.triggered = DummySignal()
        self.clicked = DummySignal()
    def setVisible(self, *args): pass
    def setEnabled(self, *args): pass

for name in [
    'QDialog', 'QWidget', 'QComboBox', 'QLineEdit', 'QSpinBox', 'QCheckBox',
    'QPushButton', 'QVBoxLayout', 'QHBoxLayout', 'QFormLayout', 'QTabWidget',
    'QGroupBox', 'QLabel', 'QPlainTextEdit', 'QTimer', 'QMessageBox',
    'QMenu', 'QAction', 'QPoint', 'QFontDatabase', 'QApplication', 'QScrollArea',
]:
    setattr(mock_qt, name, Dummy)

mock_qt.Qt = MagicMock()
mock_qt.Qt.WindowType = MagicMock()

sys.modules['aqt.utils'] = MagicMock()
sys.modules['aqt.gui_hooks'] = MagicMock()
sys.modules['aqt.webview'] = MagicMock()
sys.modules['aqt.webview'].AnkiWebView = Dummy

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from anki.errors import NotFoundError
from addon.card_parser import CardParser
from addon import reviewer_hooks
from addon.reviewer_hooks import (
    _get_card_from_collection,
    _trigger_next_pregeneration,
    _get_pregenerated_data,
    _generating_card_ids,
)

# Bind to the lazily-created singleton so test bodies can use it directly.
_pregenerated_data = _get_pregenerated_data()


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


def make_parser():
    return CardParser()


def keyed_block(parser, key, entry, ord_):
    payload = json.dumps({key: entry})
    return (
        f'<div class="{parser.json_class}" data-ai-hints-card-ord="{ord_}" '
        f'style="display:none">{payload}</div>'
    )


class IsCardSkippedTests(unittest.TestCase):
    def test_keyed_current_card_skipped(self):
        parser = make_parser()
        note = FakeNote("Cloze", {
            "Text": 'Hello {{c1::world}}'
                    + keyed_block(parser, "c1", {"hints": [], "options": [], "_skipped": True}, 0)
        })
        self.assertTrue(parser.is_card_skipped(note, FakeCard(111, 0)))

    def test_keyed_other_card_skipped_does_not_match(self):
        parser = make_parser()
        note = FakeNote("Cloze", {
            "Text": '{{c1::a}} {{c2::b}} '
                    + keyed_block(parser, "c2", {"hints": [], "options": [], "_skipped": True}, 1)
        })
        self.assertFalse(parser.is_card_skipped(note, FakeCard(111, 0)))
        self.assertTrue(parser.is_card_skipped(note, FakeCard(111, 1)))

    def test_keyed_with_hints_is_not_skipped(self):
        parser = make_parser()
        note = FakeNote("Basic", {
            "Front": "Q",
            "Back": keyed_block(parser, "c1", {"hints": ["h1"], "options": []}, 0),
        })
        self.assertFalse(parser.is_card_skipped(note, FakeCard(222, 0)))

    def test_legacy_monolithic_skipped(self):
        parser = make_parser()
        payload = json.dumps({"hints": [], "options": [], "_skipped": True})
        note = FakeNote("Basic", {
            "Front": "Q",
            "Back": f'<div class="{parser.json_class}" style="display:none">{payload}</div>',
        })
        self.assertTrue(parser.is_card_skipped(note, FakeCard(333, 0)))

    def test_html_container_skipped(self):
        parser = make_parser()
        note = FakeNote("Basic", {
            "Front": 'Q<div class="{}" data-ai-hints-card-ord="0" '
                     'data-ai-hints-skipped="true"><hr><i>skipped</i></div>'.format(parser.container_class),
        })
        self.assertTrue(parser.is_card_skipped(note, FakeCard(444, 0)))

    def test_no_block_is_not_skipped(self):
        parser = make_parser()
        note = FakeNote("Basic", {"Front": "Q", "Back": "A"})
        self.assertFalse(parser.is_card_skipped(note, FakeCard(555, 0)))

    def test_unskip_parity_detection_matches_mutation(self):
        """After unskip_hints_from_note mutates the note, is_card_skipped must be False."""
        parser = make_parser()
        note = FakeNote("Cloze", {
            "Text": '{{c1::x}}' + keyed_block(parser, "c1", {"hints": ["h"], "options": [], "_skipped": True}, 0)
        })
        card = FakeCard(666, 0)
        self.assertTrue(parser.is_card_skipped(note, card))
        self.assertTrue(parser.unskip_hints_from_note(note, card))
        self.assertFalse(parser.is_card_skipped(note, card))


class GetCardFromCollectionTests(unittest.TestCase):
    def setUp(self):
        self.mw = reviewer_hooks.mw
        self.mw.col = MagicMock()

    def test_returns_card_on_success(self):
        mock_card = MagicMock()
        self.mw.col.get_card.return_value = mock_card
        self.assertIs(_get_card_from_collection(123), mock_card)

    def test_deleted_card_returns_none(self):
        with patch.object(self.mw.col, "get_card", side_effect=NotFoundError("No such card", None, None, None)):
            self.assertIsNone(_get_card_from_collection(1787254061415))

    def test_missing_collection_returns_none(self):
        original_col = reviewer_hooks.mw.col
        try:
            reviewer_hooks.mw.col = None
            self.assertIsNone(_get_card_from_collection(123))
        finally:
            reviewer_hooks.mw.col = original_col


class PregenDeletedCardTests(unittest.TestCase):
    def setUp(self):
        _pregenerated_data.clear()
        _generating_card_ids.clear()
        self.mw = reviewer_hooks.mw
        self._original_col = self.mw.col
        self._original_config = self.mw.addonManager.getConfig.return_value
        self.mw.col = MagicMock()
        self.mw.reviewer = MagicMock()
        self.mw.addonManager.getConfig.return_value = {
            "auto_generate_new": True,
            "pre_generate_next": True,
            "pre_generate_count": 1,
        }

    def tearDown(self):
        _pregenerated_data.clear()
        _generating_card_ids.clear()
        self.mw.col = self._original_col
        self.mw.addonManager.getConfig.return_value = self._original_config

    def test_deleted_queued_card_is_skipped_and_next_is_generated(self):
        next_card = MagicMock()
        next_card.id = 556

        q_deleted = MagicMock()
        q_deleted.card_id = 555
        q_alive = MagicMock()
        q_alive.card_id = 556

        queued = MagicMock()
        queued.cards = [q_deleted, q_alive]

        def get_card_side_effect(cid):
            if cid == 555:
                raise NotFoundError("No such card", None, None, None)
            return next_card

        self.mw.reviewer.card.id = 111

        with patch.object(self.mw.col.sched, "get_queued_cards", return_value=queued), \
             patch.object(self.mw.col, "get_card", side_effect=get_card_side_effect), \
             patch.object(self.mw.taskman, "run_on_main", side_effect=lambda fn: fn()) as run_on_main, \
             patch('addon.reviewer_hooks.generate_hints') as mock_generate, \
             patch('addon.reviewer_hooks.card_has_hints', return_value=False), \
             patch('addon.reviewer_hooks.AIClient'), \
             patch('addon.reviewer_hooks.QTimer') as mock_timer:
            mock_timer.singleShot.side_effect = lambda delay, fn: fn()

            _trigger_next_pregeneration(current_card_id=111)

            mock_generate.assert_called_once()
            _, kwargs = mock_generate.call_args
            self.assertTrue(kwargs.get("is_pregen"))
            self.assertEqual(kwargs["card"].id, 556)

    def test_all_queued_deleted_triggers_nothing(self):
        q_deleted = MagicMock()
        q_deleted.card_id = 555
        queued = MagicMock()
        queued.cards = [q_deleted]
        self.mw.reviewer.card.id = 111

        with patch.object(self.mw.col.sched, "get_queued_cards", return_value=queued), \
             patch.object(self.mw.col, "get_card", side_effect=NotFoundError("No such card", None, None, None)), \
             patch.object(self.mw.taskman, "run_on_main", side_effect=lambda fn: fn()), \
             patch('addon.reviewer_hooks.generate_hints') as mock_generate, \
             patch('addon.reviewer_hooks.AIClient'), \
             patch('addon.reviewer_hooks.QTimer') as mock_timer:
            mock_timer.singleShot.side_effect = lambda delay, fn: fn()

            _trigger_next_pregeneration(current_card_id=111)
            mock_generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
