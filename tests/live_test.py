import sys
import os
import json
import asyncio
from unittest.mock import MagicMock

# Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

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

# Import AIClient
from addon.ai_client import AIClient

async def run_live_tests():
    # Load config from meta.json if available
    meta_path = os.path.join(ADDON_DIR, 'meta.json')
    if not os.path.exists(meta_path):
        print(f"Error: {meta_path} not found. Please ensure your API keys are in meta.json.")
        return
        
    with open(meta_path, 'r') as f:
        full_meta = json.load(f)
        config = full_meta.get("config", {})
            
    client = AIClient(config)
    
    test_note = {
        "fields": {
            "Text": "What is the formula for the area of a circle?",
            "Back": "A = \\pi r^2"
        },
        "modelName": "Basic"
    }
    
    # Try current provider
    primary = config.get("ai_provider", "gemini")
    print(f"\nTesting provider: {primary}")
    
    try:
        front = test_note['fields']['Text']
        back = test_note['fields']['Back']
        
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, client.generate_options, front, back)
        result = await future
        
        if result and (result.get("hints") or result.get("options")):
            print(f"SUCCESS: Received data from {primary}:")
            print(json.dumps(result, indent=2))
        else:
            print(f"FAILED: No data generated for {primary}.")
            
    except Exception as e:
        print(f"ERROR during generation: {e}")

if __name__ == "__main__":
    asyncio.run(run_live_tests())
