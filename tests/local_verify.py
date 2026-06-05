import sys
import os
import json
import re
from unittest.mock import MagicMock
from typing import Dict, List, Tuple

# 1. Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

# 2. Mock Anki/Qt
from types import ModuleType
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
           'QDialogButtonBox', 'QStyledItemDelegate']
for cls in classes:
    setattr(mock_qt, cls, MagicMock)

from aqt import mw
mw.addonManager = MagicMock()
mw.addonManager.getConfig.return_value = {}

# 3. Import addon modules
from addon.latex_fixer.latex_fixer import normalize_math_text
from addon.ai_client import AIClient
from addon.reviewer_hooks import generate_hints

def run_tests():
    print("Testing add-on initialization...")
    try:
        import addon
        print("SUCCESS: Add-on imported and initialized successfully.")
    except Exception as e:
        print(f"FAILED: Add-on import failed: {e}")
        sys.exit(1)

    print("Testing MathJax normalization logic...")
    test_cases = [
        (r"Matrix: \[ begin{pmatrix} a & b \\ c & d end{pmatrix} \]", 
         r"Matrix: \[ \begin{pmatrix} a & b \\ c & d \end{pmatrix} \]"),
        (r"Cases: \[ f(x)=begin{cases} x^2 & x ge 0 \\ -x & x < 0 end{cases} \]",
         r"Cases: \[ f(x)=\begin{cases} x^2 & x \ge 0 \\ -x & x < 0 \end{cases} \]"),
        (r"Vector: vec{v} cdot hat{n}", 
         r"Vector: \( \vec{v} \) \( \cdot \) \( \hat{n} \)")
    ]
    
    for input_text, expected in test_cases:
        normalized = normalize_math_text(input_text)
        # Using simplified check for readability
        if expected.replace(" ", "") in normalized.replace(" ", ""):
            pass
        else:
            print(f"FAILED: MathJax normalization incorrect for: {input_text}")
            print(f"Got: {normalized}")
            sys.exit(1)
    print("SUCCESS: MathJax normalization tests passed.")

    print("Testing model normalization...")
    client = AIClient({})
    if client._normalize_model("gemini", "gemini-1.5-flash") == "gemini-2.0-flash":
        print("SUCCESS: Model normalization works.")
    else:
        print("FAILED: Model normalization failed.")
        sys.exit(1)

    print("\nAll local verification tests passed.")

if __name__ == "__main__":
    run_tests()
