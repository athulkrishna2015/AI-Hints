import sys
import os
from unittest.mock import MagicMock

# 1. Setup Mock Anki Environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock aqt and its submodules before importing addon
mock_aqt = MagicMock()
mock_mw = MagicMock()
mock_aqt.mw = mock_mw

# Mock Qt classes that are used as base classes
class MockQDialog: pass
class MockQWidget: pass
class MockQTabWidget: pass

mock_qt = MagicMock()
mock_qt.QDialog = MockQDialog
mock_qt.QWidget = MockQWidget
mock_qt.QTabWidget = MockQTabWidget

sys.modules['aqt'] = mock_aqt
sys.modules['aqt.qt'] = mock_qt
sys.modules['aqt.utils'] = MagicMock()
sys.modules['aqt.gui_hooks'] = MagicMock()
sys.modules['aqt.webview'] = MagicMock()
sys.modules['aqt.reviewer'] = MagicMock()

# 2. Test Import and Initialization
try:
    print("Testing add-on initialization...")
    import addon
    print("SUCCESS: Add-on imported and initialized successfully.")
    
    # 3. Test Config Dialog call (the recent bug)
    print("Testing config dialog entry point...")
    from addon.config_ui import on_config_dialog
    
    # Simulate Anki calling it without arguments
    try:
        # Mock ConfigDialog to not actually open a window
        import addon.config_ui
        addon.config_ui.ConfigDialog = MagicMock()
        
        on_config_dialog()
        print("SUCCESS: on_config_dialog() works without arguments.")
    except TypeError as e:
        print(f"FAILED: on_config_dialog() still has TypeError: {e}")
        sys.exit(1)
        
    # 4. Test Reviewer Hooks and Future handling
    print("Testing reviewer hooks and future handling...")
    from addon.reviewer_hooks import generate_hints
    
    # Mock card and reviewer state
    mock_card = MagicMock()
    mock_note = MagicMock()
    # Mock dict-like behavior for note
    mock_note.keys.return_value = ["Front", "Back"]
    mock_note.items.return_value = [("Front", "Q"), ("Back", "A")]
    mock_note.__getitem__.side_effect = lambda k: "current value"
    mock_note.model.return_value = {"name": "Basic"}
    mock_card.note.return_value = mock_note
    mock_mw.reviewer.card = mock_card
    
    # Setup mock for run_in_background to execute callback immediately
    def mock_run_in_background(task, on_done):
        class MockFuture:
            def result(self):
                return {"hints": ["Hint 1"], "options": ["Option 1", "Option 2"]}
        on_done(MockFuture())
        
    mock_mw.taskman.run_in_background = mock_run_in_background
    
    # This should not raise TypeError anymore
    generate_hints()
    print("SUCCESS: generate_hints() handles Dict results correctly.")

    # 5. Test JSON storage mode
    print("Testing JSON storage mode...")
    from addon.card_parser import CardParser
    
    json_parser = CardParser(target_fields=["Back"], storage_mode="json")
    mock_note_json = MagicMock()
    mock_note_json.keys.return_value = ["Back"]
    mock_note_json.__getitem__.return_value = "original"
    mock_note_json.model.return_value = {"name": "Basic"}
    
    json_parser.update_note_with_hints(mock_note_json, {"hints": ["H"], "options": ["O"]})
    
    # Check if JSON was correctly set
    set_value = mock_note_json.__setitem__.call_args[0][1]
    if 'class="ai-hints-json"' in set_value and '"hints": ["H"]' in set_value:
        print("SUCCESS: CardParser correctly formats JSON storage mode.")
    else:
        print(f"FAILED: CardParser incorrect JSON formatting: {set_value}")
        sys.exit(1)

    # 6. Test options_count injection in AIClient
    print("Testing options_count injection...")
    from addon.ai_client import AIClient
    
    config = {"options_count": 5, "system_prompt": "Prompt.", "ai_provider": "openai"}
    client = AIClient(config)
    
    # We can't easily test the network call, but we can check if it tries to use the right prompt
    # Let's mock _call_openai_compatible to see what system_prompt it receives
    client._call_openai_compatible = MagicMock(return_value={"hints": [], "options": []})
    client.generate_options("F", "B")
    
    received_system_prompt = client._call_openai_compatible.call_args[0][1]
    if "exactly 5 options" in received_system_prompt:
        print("SUCCESS: AIClient correctly injects options_count into prompt.")
    else:
        print(f"FAILED: AIClient incorrect prompt injection: {received_system_prompt}")
        sys.exit(1)

except Exception as e:
    print(f"CRITICAL FAILURE during add-on load: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nAll local verification tests passed.")
