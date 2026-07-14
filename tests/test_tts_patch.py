import sys
import os
from unittest.mock import MagicMock, patch

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Mock logger
mock_logger = MagicMock()
sys.modules['logger'] = mock_logger
sys.modules['.logger'] = mock_logger

# Mock Anki/Qt modules
from types import ModuleType
aqt = ModuleType('aqt')
sys.modules['aqt'] = aqt
aqt.editor = MagicMock()
sys.modules['aqt.editor'] = aqt.editor
from aqt.editor import EditorMode

from addon.tts_addon_patch import setup_tts_addon_patch

def test_tts_addon_patch():
    print("--- Running TTS Patch tests ---")

    # Mock the modules of addon 428593773
    mock_remove_codes = ModuleType("remove_codes")
    mock_remove_codes.remove_codes_from_text = lambda text: text
    
    mock_add_audio = ModuleType("add_audio_to_card")
    mock_add_audio.on_success = MagicMock()

    # We mock importlib.import_module to return our mock modules when imported
    def mock_import(name):
        if name == "428593773.bulk_add_voices.remove_codes":
            return mock_remove_codes
        if name == "428593773.add_cards.add_audio_to_card":
            return mock_add_audio
        raise ModuleNotFoundError(f"Mocked out: {name}")

    with patch("importlib.import_module", side_effect=mock_import):
        setup_tts_addon_patch()

    # 1. Verify remove_codes_from_text is wrapped and successfully strips AI data
    raw_text = 'Hello World <div class="ai-hints-json" style="display:none;">{"c1": {"hints": ["H1"], "options": ["O1"]}}</div>'
    res = mock_remove_codes.remove_codes_from_text(raw_text)
    print("Patched remove_codes result:", repr(res))
    if "ai-hints-json" not in res and "Hello World" in res:
        print("  PASS: remove_codes_from_text successfully wrapped and strips AI data.")
    else:
        print("  FAIL: remove_codes_from_text did not strip AI data or corrupted text.")
        exit(1)

    # 2. Verify on_success wrapper is installed and calls loadNoteKeepingFocus
    mock_webview = MagicMock()
    mock_webview.kind = MagicMock()
    mock_webview.editor = MagicMock()
    mock_webview.editor.editorMode = MagicMock()
    
    # Test case A: EDIT_CURRENT mode (should call loadNoteKeepingFocus)
    mock_webview.editor.editorMode = "edit_current"
    mock_add_audio.on_success(mock_webview, 1.0)
    
    if mock_webview.editor.loadNoteKeepingFocus.called:
        print("  PASS: on_success reloads editor note in edit_current mode.")
    else:
        print("  FAIL: loadNoteKeepingFocus was not called.")
        exit(1)

    # Test case B: ADD_CARDS mode (should NOT call loadNoteKeepingFocus)
    mock_webview.editor.loadNoteKeepingFocus.reset_mock()
    # Mock EditorMode.ADD_CARDS
    from aqt.editor import EditorMode
    EditorMode.ADD_CARDS = "add_cards"
    mock_webview.editor.editorMode = "add_cards"
    mock_add_audio.on_success(mock_webview, 1.0)
    
    if not mock_webview.editor.loadNoteKeepingFocus.called:
        print("  PASS: on_success does not reload editor note in add_cards mode.")
    else:
        print("  FAIL: loadNoteKeepingFocus was incorrectly called in add_cards mode.")
        exit(1)

if __name__ == "__main__":
    test_tts_addon_patch()
