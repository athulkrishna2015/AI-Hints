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
            
    # Set model to a more capable version for testing
    if "models" not in config:
        config["models"] = {}
    config["models"]["gemini"] = "gemini-2.5-flash"
            
    client = AIClient(config)
    
    test_note = {
        "fields": {
            "Text": """<h3>The Standard z-x'-z'' Convention</h3><div>The full Direction Cosine Matrix (DCM) for Euler angles</div><ol><li><div><b>Rotation by&nbsp;<anki-mathjax>\phi</anki-mathjax>&nbsp;(Precession):</b>&nbsp;A rotation about the original&nbsp;<anki-mathjax>z</anki-mathjax>-axis.</div><div><anki-mathjax block="true">D = \begin{pmatrix} [...] \end{pmatrix}</anki-mathjax></div></li><li><div><b>Rotation by&nbsp;<anki-mathjax>\theta</anki-mathjax>&nbsp;(Nutation):</b>&nbsp;A rotation about the intermediate&nbsp;<anki-mathjax>x'</anki-mathjax>-axis.</div><div><anki-mathjax block="true">C = \begin{pmatrix} [...] \end{pmatrix}</anki-mathjax></div></li><li><div><b>Rotation by&nbsp;<anki-mathjax>\psi</anki-mathjax>&nbsp;(Spin):</b>&nbsp;A rotation about the final&nbsp;<anki-mathjax>z''</anki-mathjax>-axis.</div><div><anki-mathjax block="true">B = \begin{pmatrix} [...] \end{pmatrix}</anki-mathjax></div></li></ol>""",
            "Back": "\\cos\\phi &amp; \\sin\\phi &amp; 0 \\\\ -\\sin\\phi &amp; \\cos\\phi &amp; 0 \\\\ 0 &amp; 0 &amp; 1, 1 &amp; 0 &amp; 0 \\\\ 0 &amp; \\cos\\theta &amp; \\sin\\theta \\\\ 0 &amp; -\\sin\\theta &amp; \\cos\\theta, \\cos\\psi &amp; \\sin\\psi &amp; 0 \\\\ -\\sin\\psi &amp; \\cos\\psi &amp; 0 \\\\ 0 &amp; 0 &amp; 1"
        },
        "modelName": "Cloze"
    }
    
    # Try current provider
    primary = config.get("ai_provider", "gemini")
    print(f"\nTesting provider: {primary} with model: {config['models'].get(primary)}")
    
    try:
        front = test_note['fields']['Text']
        back = test_note['fields']['Back']
        
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, client.generate_options, front, back)
        result = await future
        
        if result and (result.get("hints") or result.get("options") or result.get("distractors")):
            print(f"SUCCESS: Received raw data from {primary}:")
            print(json.dumps(result, indent=2))
            
            # Normalize using CardParser
            from addon.card_parser import CardParser
            parser = CardParser()
            normalized = parser.normalize_hint_data(result)
            print("\nNormalized for Anki card display:")
            print(json.dumps(normalized, indent=2))
        else:
            print(f"FAILED: No data generated for {primary}.")
            
    except Exception as e:
        print(f"ERROR during generation: {e}")

if __name__ == "__main__":
    asyncio.run(run_live_tests())
