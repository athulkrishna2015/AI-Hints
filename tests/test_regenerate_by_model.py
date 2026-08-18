import sys
import os
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

# Mock aqt and other Anki components before importing reviewer_hooks
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

qt_names = [
    'QDialog', 'QWidget', 'QComboBox', 'QLineEdit', 'QSpinBox', 'QCheckBox',
    'QPushButton', 'QVBoxLayout', 'QHBoxLayout', 'QFormLayout', 'QTabWidget',
    'QGroupBox', 'QLabel', 'QPlainTextEdit', 'QTimer', 'QMessageBox',
    'QMenu', 'QAction', 'QPoint', 'QFontDatabase', 'QApplication', 'QScrollArea',
    'QPixmap', 'QStyledItemDelegate', 'QEvent'
]
for name in qt_names:
    setattr(mock_qt, name, Dummy)
mock_qt.Qt = MagicMock()
mock_qt.Qt.WindowMode = MagicMock()
mock_qt.Qt.WindowType = MagicMock()
mock_qt.Qt.WindowModality = MagicMock()

sys.modules['aqt.utils'] = MagicMock()
sys.modules['aqt.gui_hooks'] = MagicMock()
sys.modules['aqt.webview'] = MagicMock()
sys.modules['aqt.webview'].AnkiWebView = Dummy

try:
    from addon import reviewer_hooks
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from addon import reviewer_hooks
from addon.reviewer_hooks import (
    collect_stored_models,
    find_cards_by_stored_model,
)


class TestRegenerateByModel(unittest.TestCase):

    def setUp(self):
        self.fresh_mw = MagicMock()
        self.fresh_mw.addonManager.getConfig.return_value = {}
        self.fresh_mw.col.find_notes.return_value = []
        reviewer_hooks.mw = self.fresh_mw

    def _make_note(self, nid, cards, entries):
        note = MagicMock()
        note.id = nid
        note.cards.return_value = cards
        return note

    @patch("addon.card_parser.CardParser._extract_all_hints_from_fields")
    def test_collect_stored_models_dedupes(self, mock_extract):
        note_a = MagicMock()
        note_b = MagicMock()
        # note_a blocks: two models
        mock_extract.side_effect = [
            [{"data": {"_model": "gpt-oss-120b"}, "card_key": None},
             {"data": {"_model": "qwen3"}, "card_key": None}],
            [{"data": {"_model": "gpt-oss-120b"}, "card_key": None}],
        ]
        self.fresh_mw.col.find_notes.return_value = ["1", "2"]
        self.fresh_mw.col.get_note.side_effect = [note_a, note_b]

        models = collect_stored_models()
        self.assertEqual(models, ["gpt-oss-120b", "qwen3"])

    def _card(self, cid, ord=0):
        c = MagicMock()
        c.id = cid
        c.ord = ord
        return c

    @patch("addon.card_parser.CardParser._extract_all_hints_from_fields")
    def test_find_cards_by_model_single(self, mock_extract):
        c = self._card(101, 0)
        note = MagicMock()
        note.cards.return_value = [c]
        self.fresh_mw.col.find_notes.return_value = ["1"]
        self.fresh_mw.col.get_note.return_value = note
        mock_extract.return_value = [{"data": {"_model": "GPT-OSS-120B"}, "card_key": None}]

        found = find_cards_by_stored_model("gpt-oss-120b")
        self.assertEqual(found, [101])

    @patch("addon.card_parser.CardParser._extract_all_hints_from_fields")
    def test_find_cards_by_model_cloze_key(self, mock_extract):
        c1 = self._card(201, 0)
        c2 = self._card(202, 1)
        note = MagicMock()
        note.cards.return_value = [c1, c2]
        self.fresh_mw.col.find_notes.return_value = ["1"]
        self.fresh_mw.col.get_note.return_value = note
        # c1 was generated with gpt-oss, c2 with qwen3
        mock_extract.return_value = [
            {"data": {"_model": "gpt-oss-120b"}, "card_key": "c1"},
            {"data": {"_model": "qwen3"}, "card_key": "c2"},
        ]

        found = find_cards_by_stored_model("gpt-oss-120b")
        # Only c1 (ord 0) should match
        self.assertEqual(found, [201])

    def test_find_cards_by_model_empty_filter(self):
        self.assertEqual(find_cards_by_stored_model("   "), [])


if __name__ == "__main__":
    unittest.main()