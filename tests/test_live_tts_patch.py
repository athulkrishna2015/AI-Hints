import sys
import os
from unittest.mock import MagicMock

# 1. Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Add the addon directories to sys.path so we can import them
sys.path.insert(0, "/home/admin/.local/share/Anki2/addons21")

# Mock Anki/Qt modules so we can import them safely
from types import ModuleType
aqt = ModuleType('aqt')
sys.modules['aqt'] = aqt
aqt.editor = MagicMock()
sys.modules['aqt.editor'] = aqt.editor
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

# Mock logger
mock_logger = MagicMock()
sys.modules['logger'] = mock_logger
sys.modules['.logger'] = mock_logger

# 2. Import our patcher
from addon.tts_addon_patch import setup_tts_addon_patch

def test_live_tts_patch():
    print("--- Running LIVE TTS Integration Patch Tests ---")

    # Import the real unpatched remove_codes first to verify it fails initially
    import importlib
    remove_codes_mod = importlib.import_module("428593773.bulk_add_voices.remove_codes")
    subprocess_piper_mod = importlib.import_module("428593773.subprocess_piper")

    raw_text = 'Hello World <div class="ai-hints-json" style="display:none;">{"c1": {"hints": ["H1"], "options": ["O1"]}}</div>'
    
    # Verify unpatched behavior (should output JSON text)
    unpatched_res = remove_codes_mod.remove_codes_from_text(raw_text)
    print("Unpatched remove_codes result:", repr(unpatched_res))
    if "ai-hints-json" in unpatched_res or "H1" in unpatched_res:
        print("  Verified: Real unpatched function fails to strip JSON as expected.")
    else:
        print("  Warning: Unpatched function stripped JSON? Check addon files.")

    # 3. Apply the dynamic runtime patch
    setup_tts_addon_patch()

    # 4. Verify patched behavior on the real remove_codes module
    patched_res = remove_codes_mod.remove_codes_from_text(raw_text)
    print("Patched remove_codes result:  ", repr(patched_res))
    if "ai-hints-json" not in patched_res and "Hello World" in patched_res:
        print("  PASS: Real remove_codes_from_text successfully patched and strips AI data.")
    else:
        print("  FAIL: Real remove_codes_from_text patch did not strip AI data.")
        exit(1)

    # 5. Verify patched behavior on the real subprocess_piper module (used in bulk gen)
    patched_sub_res = subprocess_piper_mod.remove_codes_from_text(raw_text)
    print("Patched subprocess_piper result:", repr(patched_sub_res))
    if "ai-hints-json" not in patched_sub_res and "Hello World" in patched_sub_res:
        print("  PASS: Real subprocess_piper.remove_codes_from_text successfully patched (fixes bulk gen).")
    else:
        print("  FAIL: Real subprocess_piper.remove_codes_from_text patch did not strip AI data.")
        exit(1)

if __name__ == "__main__":
    test_live_tts_patch()
