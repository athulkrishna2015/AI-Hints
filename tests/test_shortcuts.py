import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Mock aqt / mw
from types import ModuleType
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

classes = ['QDialog', 'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QLabel', 
           'QLineEdit', 'QPushButton', 'QComboBox', 'QCheckBox', 'QTextEdit',
           'QScrollArea', 'QGroupBox', 'QFormLayout', 'QSpinBox', 'QDialogButtonBox',
           'QPixmap', 'Qt', 'QApplication', 'QSizePolicy', 'QTimer', 'QTabWidget',
           'QListWidget', 'QListWidgetItem', 'QDesktopServices', 'QUrl', 'QProgressBar',
           'QDialogButtonBox', 'QFrame', 'QIcon', 'QSize', 'QMovie']
for cls in classes:
    setattr(aqt.qt, cls, MagicMock)

from aqt import mw

# Mock ADDON_PACKAGE
sys.modules['addon.logger'] = MagicMock()

# Now import the target module
from addon.reviewer_hooks import on_state_shortcuts_will_change

class TestShortcuts(unittest.TestCase):
    def setUp(self):
        self.shortcuts_list = []
        self.mock_config = {
            "shortcuts": {
                "modifier": "alt",
                "generate": "1",
                "toggle-options": "2",
                "toggle-hints": "3",
                "clear": "4",
                "refresh": "5",
                "show-json": "6"
            }
        }
        mw.addonManager.getConfig.return_value = self.mock_config

    def test_reviewer_shortcuts_registered_with_alt(self):
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        # Verify the length and contents
        self.assertEqual(len(self.shortcuts_list), 6)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertIn("Alt+1", shortcut_keys)
        self.assertIn("Alt+2", shortcut_keys)
        self.assertIn("Alt+3", shortcut_keys)
        self.assertIn("Alt+4", shortcut_keys)
        self.assertIn("Alt+5", shortcut_keys)
        self.assertIn("Alt+6", shortcut_keys)

    def test_reviewer_shortcuts_registered_with_ctrl(self):
        self.mock_config["shortcuts"]["modifier"] = "ctrl"
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertIn("Ctrl+1", shortcut_keys)

    def test_reviewer_shortcuts_registered_with_none_modifier(self):
        self.mock_config["shortcuts"]["modifier"] = "none"
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertIn("1", shortcut_keys)

    def test_no_shortcuts_for_non_review_state(self):
        on_state_shortcuts_will_change("overview", self.shortcuts_list)
        self.assertEqual(len(self.shortcuts_list), 0)

    def test_empty_or_missing_keys_skipped(self):
        self.mock_config["shortcuts"]["generate"] = ""
        self.mock_config["shortcuts"]["toggle-options"] = " "
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertNotIn("Alt+1", shortcut_keys)
        self.assertNotIn("Alt+2", shortcut_keys)
        self.assertIn("Alt+3", shortcut_keys)  # toggle-hints still present

if __name__ == "__main__":
    unittest.main()
