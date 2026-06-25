import sys
import os
import json
from unittest.mock import MagicMock

# 1. Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 2. Mock Anki/Qt
from types import ModuleType
class PyQtMock(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__()

aqt = ModuleType('aqt')
sys.modules['aqt'] = aqt
aqt.qt = MagicMock()
sys.modules['aqt.qt'] = aqt.qt
aqt.utils = MagicMock()
sys.modules['aqt.utils'] = aqt.utils
aqt.webview = MagicMock()
sys.modules['aqt.webview'] = aqt.webview
aqt.theme = MagicMock()
sys.modules['aqt.theme'] = aqt.theme
aqt.colors = MagicMock()
sys.modules['aqt.colors'] = aqt.colors
aqt.gui_hooks = MagicMock()
sys.modules['aqt.gui_hooks'] = aqt.gui_hooks
aqt.mw = MagicMock()
sys.modules['aqt.mw'] = aqt.mw

mock_qt = aqt.qt
classes = ['QDialog', 'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QLabel', 
           'QLineEdit', 'QPushButton', 'QComboBox', 'QCheckBox', 'QTextEdit',
           'QScrollArea', 'QGroupBox', 'QFormLayout', 'QSpinBox', 'QDialogButtonBox',
           'QPixmap', 'Qt', 'QApplication', 'QSizePolicy', 'QTimer', 'QTabWidget',
           'QListWidget', 'QListWidgetItem', 'QDesktopServices', 'QUrl', 'QProgressBar',
           'QStyledItemDelegate', 'QAction', 'QHeaderView', 'QTableWidget', 'QTableWidgetItem',
           'QAbstractItemView', 'QMenu']
for cls in classes:
    setattr(mock_qt, cls, type(cls, (PyQtMock,), {}))

from aqt import mw
mw.addonManager = MagicMock()
mw.addonManager.getConfig.return_value = {
    "show_hints_button": True,
    "show_options_button": True,
    "mathjax_format": "delimiters"
}

# Mock collection update note
mw.col = MagicMock()
mw.col.update_note = MagicMock()

# Mock tooltip
import addon.reviewer_hooks
addon.reviewer_hooks.tooltip = MagicMock()

from addon.reviewer_hooks import edit_item, _remember_generated_hints, _cached_hints_for_card, _push_hint_data_to_frontend

class MockNote:
    def __init__(self, field_dict):
        self.field_dict = field_dict
        self.fields = list(field_dict.values())

    def keys(self):
        return list(self.field_dict.keys())

    def values(self):
        return list(self.field_dict.values())

    def __getitem__(self, key):
        return self.field_dict[key]

    def __setitem__(self, key, value):
        self.field_dict[key] = value
        self.fields = list(self.field_dict.values())

class MockCard:
    def __init__(self, card_id, ord_val, field_dict):
        self.id = card_id
        self.ord = ord_val
        self._note = MockNote(field_dict)

    def note(self):
        return self._note

def test_inline_editing():
    print("--- Running Inline Editing Unit Tests ---")

    # Setup initial note fields with a JSON block in the first field (Front)
    initial_hints = {
        "hints": ["Hint 1", "Hint 2"],
        "options": ["Correct Option", "Distractor 1", "Distractor 2"],
        "correct_answer": "Correct Option"
    }
    
    # Store this JSON in a mocked field format inside a <div class="ai-hints-json">
    json_block = f'<div class="ai-hints-json" style="display:none">{json.dumps(initial_hints)}</div>'
    fields = {
        "Front": "Front content " + json_block,
        "Back": "Back content"
    }
    
    card = MockCard(card_id=12345, ord_val=0, field_dict=fields)
    web = MagicMock()

    # Verify initial state cache is clean
    assert _cached_hints_for_card(card) is None

    # Mock _push_hint_data_to_frontend
    addon.reviewer_hooks._push_hint_data_to_frontend = MagicMock()

    # 1. Edit a Hint
    print("Testing hint edit...")
    edit_item(card, web, item_type="hints", index=1, new_value="Edited Hint 2")
    
    # Check that update_note was called
    mw.col.update_note.assert_called_once()
    mw.col.update_note.reset_mock()

    # Check cache was updated
    cached = _cached_hints_for_card(card)
    assert cached is not None
    assert cached["data"]["hints"][1] == "Edited Hint 2"
    assert cached["data"]["hints"][0] == "Hint 1"

    # Check frontend was pushed to
    addon.reviewer_hooks._push_hint_data_to_frontend.assert_called_once()
    addon.reviewer_hooks._push_hint_data_to_frontend.reset_mock()

    # 2. Edit an Option (Distractor) at index 2
    print("Testing option (distractor) edit...")
    edit_item(card, web, item_type="options", index=2, new_value="Edited Distractor 2")
    
    # Check note updated and cached correctly
    mw.col.update_note.assert_called_once()
    mw.col.update_note.reset_mock()
    cached = _cached_hints_for_card(card)
    assert cached["data"]["options"][2] == "Edited Distractor 2"
    # correct_answer should remain unchanged
    assert cached["data"]["correct_answer"] == "Correct Option"

    # 3. Edit Option at index 0 (Correct Answer)
    print("Testing option (correct answer) edit & sync...")
    edit_item(card, web, item_type="options", index=0, new_value="New Correct Option")
    
    mw.col.update_note.assert_called_once()
    mw.col.update_note.reset_mock()
    cached = _cached_hints_for_card(card)
    assert cached["data"]["options"][0] == "New Correct Option"
    # correct_answer should be updated as well
    assert cached["data"]["correct_answer"] == "New Correct Option"

    print("\nALL INLINE EDITING TESTS PASSED")

if __name__ == "__main__":
    test_inline_editing()
