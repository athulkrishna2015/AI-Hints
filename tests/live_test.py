import sys
import os
import json
import asyncio
from unittest.mock import MagicMock

# Setup absolute paths
PROJECT_ROOT = '/mnt/0946E88701BE265B/portable/anki/addons/AI-Hints'
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

# Mock Anki/Qt
mock_qt = MagicMock()
classes = ['QDialog', 'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QLabel', 
           'QLineEdit', 'QPushButton', 'QComboBox', 'QCheckBox', 'QTextEdit',
           'QScrollArea', 'QGroupBox', 'QFormLayout', 'QSpinBox', 'QDialogButtonBox']
for cls in classes:
    setattr(mock_qt, cls, MagicMock)

sys.modules['aqt'] = MagicMock()
sys.modules['aqt.qt'] = mock_qt
sys.modules['aqt.utils'] = MagicMock()
sys.modules['aqt.theme'] = MagicMock()
sys.modules['aqt.colors'] = MagicMock()

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
            "Text": "The Meissner effect is the expulsion of a magnetic field from a superconductor during its transition to the superconducting state.",
            "Back": "Occurs when cooled below the critical temperature."
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
