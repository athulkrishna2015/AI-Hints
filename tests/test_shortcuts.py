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
           'QDialogButtonBox', 'QFrame', 'QIcon', 'QSize', 'QMovie', 'QStyledItemDelegate', 'QEvent']
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
                "toggle-options": "3",
                "toggle-hints": "2",
                "clear": "4",
                "refresh": "5",
                "show-json": "6"
            }
        }
        import addon.reviewer_hooks
        addon.reviewer_hooks.mw.addonManager.getConfig.return_value = self.mock_config
        addon.reviewer_hooks.mw.reviewer.state = "question"


    def test_reviewer_shortcuts_registered_with_alt(self):
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        # Verify the length and contents
        self.assertEqual(len(self.shortcuts_list), 12)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertIn("Alt+1", shortcut_keys)
        self.assertIn("Alt+2", shortcut_keys)
        self.assertIn("Alt+3", shortcut_keys)
        self.assertIn("Alt+4", shortcut_keys)
        self.assertIn("Alt+5", shortcut_keys)
        self.assertIn("Alt+6", shortcut_keys)
        self.assertIn("1", shortcut_keys)
        self.assertIn("2", shortcut_keys)
        self.assertIn("3", shortcut_keys)
        self.assertIn("4", shortcut_keys)
        self.assertIn("5", shortcut_keys)
        self.assertIn("6", shortcut_keys)

    def test_reviewer_shortcuts_registered_with_ctrl(self):
        self.mock_config["shortcuts"]["modifier"] = "ctrl"
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertIn("Ctrl+1", shortcut_keys)
        self.assertIn("1", shortcut_keys)

    def test_reviewer_shortcuts_registered_with_none_modifier(self):
        self.mock_config["shortcuts"]["modifier"] = "none"
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertIn("1", shortcut_keys)
        self.assertEqual(shortcut_keys.count("1"), 1)

    def test_no_shortcuts_for_non_review_state(self):
        on_state_shortcuts_will_change("overview", self.shortcuts_list)
        self.assertEqual(len(self.shortcuts_list), 0)

    def test_empty_or_missing_keys_skipped(self):
        self.mock_config["shortcuts"]["generate"] = ""
        self.mock_config["shortcuts"]["toggle-options"] = " "
        on_state_shortcuts_will_change("review", self.shortcuts_list)
        
        shortcut_keys = [s[0] for s in self.shortcuts_list]
        self.assertNotIn("Alt+1", shortcut_keys)
        self.assertNotIn("Alt+3", shortcut_keys)
        self.assertIn("Alt+2", shortcut_keys)  # toggle-hints still present
        self.assertNotIn("1", shortcut_keys)
        self.assertNotIn("3", shortcut_keys)
        self.assertIn("2", shortcut_keys)

    def test_bare_shortcut_action_only_runs_on_question_side(self):
        import addon.reviewer_hooks as hooks
        with patch.object(hooks, "trigger_js_click") as trigger:
            on_state_shortcuts_will_change("review", self.shortcuts_list)
            bare_hints = dict(self.shortcuts_list)["2"]
            bare_hints()
            trigger.assert_called_once_with("Hints", "💡")

            trigger.reset_mock()
            hooks.mw.reviewer.state = "answer"
            bare_hints()
            trigger.assert_not_called()

if __name__ == "__main__":
    unittest.main()
