import sys
import os
from unittest.mock import MagicMock

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Mock logger
mock_logger = MagicMock()
sys.modules['logger'] = mock_logger
sys.modules['.logger'] = mock_logger

# Mock Anki/Qt
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
aqt.gui_hooks = MagicMock()
sys.modules['aqt.gui_hooks'] = aqt.gui_hooks
aqt.mw = MagicMock()
sys.modules['aqt.mw'] = aqt.mw

from aqt import mw
mw.addonManager = MagicMock()
mw.addonManager.getConfig.return_value = {}

from addon.reviewer_hooks import edit_item, _remember_generated_hints, _cached_hints_for_card
from addon.card_parser import CardParser

def test_edit_item_removal():
    print("--- Running edit_item Removal Tests ---")
    
    # 1. Setup mock card, note, and parser
    class MockNote:
        def __init__(self):
            # Start with a JSON block containing 2 hints and 2 options
            self.data = {
                "Back": 'Original text<div class="ai-hints-json" style="display:none;">{"c1": {"hints": ["Hint 1", "Hint 2"], "options": ["Correct", "Wrong"]}}</div>'
            }
        def __setitem__(self, key, value):
            self.data[key] = value
        def __getitem__(self, key):
            return self.data[key]
        def keys(self):
            return self.data.keys()
        def values(self):
            return self.data.values()
        def items(self):
            return self.data.items()
        def __contains__(self, key):
            return key in self.data

    mock_note = MockNote()
    mock_card = MagicMock()
    mock_card.id = 123
    mock_card.ord = 0
    mock_card.note.return_value = mock_note

    # Mock collection update
    mw.col = MagicMock()

    # Mock cached hints
    import addon.reviewer_hooks as rh
    rh._cached_hints = {} # clear cache

    # Case 1: Edit value to something new (normal edit)
    print("Testing standard edit...")
    edit_item(mock_card, None, "hints", 0, "New Hint 1")
    parser = CardParser()
    block = parser.find_hints_block(mock_note, mock_card)
    if block and "New Hint 1" in block and "Hint 2" in block:
        print("  PASS: Standard edit updated correctly.")
    else:
        print("  FAIL: Standard edit failed. Got block:", block)
        exit(1)

    # Case 2: Edit hint to empty string (removal)
    print("Testing hint removal...")
    edit_item(mock_card, None, "hints", 0, "")
    block = parser.find_hints_block(mock_note, mock_card)
    if block and "New Hint 1" not in block and "Hint 2" in block:
        print("  PASS: Hint successfully removed.")
    else:
        print("  FAIL: Hint removal failed. Got block:", block)
        exit(1)

    # Case 3: Edit option to empty string (removal)
    print("Testing option removal...")
    edit_item(mock_card, None, "options", 1, "   ")
    block = parser.find_hints_block(mock_note, mock_card)
    if block and "Wrong" not in block and "Correct" in block:
        print("  PASS: Option successfully removed.")
    else:
        print("  FAIL: Option removal failed. Got block:", block)
        exit(1)

    # Case 4: Clear last remaining item should invoke clear_hints
    print("Testing clear_hints trigger when all items removed...")
    # Currently: hints = ["Hint 2"], options = ["Correct"]
    # 1. Remove the hint
    edit_item(mock_card, None, "hints", 0, "")
    # 2. Mock clear_hints and remove the last option
    rh.clear_hints = MagicMock()
    edit_item(mock_card, None, "options", 0, "")
    if rh.clear_hints.called:
        print("  PASS: clear_hints triggered correctly when no items remain.")
    else:
        print("  FAIL: clear_hints was not triggered.")
        exit(1)

if __name__ == "__main__":
    test_edit_item_removal()
