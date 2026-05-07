import sys
import os
from types import SimpleNamespace
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
class MockQt:
    class WindowType:
        Window = 1

mock_qt = MagicMock()
mock_qt.QDialog = MockQDialog
mock_qt.QWidget = MockQWidget
mock_qt.QTabWidget = MockQTabWidget
mock_qt.Qt = MockQt
mock_qt.QTimer = MagicMock
mock_qt.QVBoxLayout = MagicMock
mock_qt.QHBoxLayout = MagicMock
mock_qt.QFormLayout = MagicMock
mock_qt.QTabWidget = MockQTabWidget
mock_qt.QPushButton = MagicMock
mock_qt.QLineEdit = MagicMock
mock_qt.QTextEdit = MagicMock
mock_qt.QPlainTextEdit = MagicMock
mock_qt.QCheckBox = MagicMock
mock_qt.QSpinBox = MagicMock
mock_qt.QComboBox = MagicMock
mock_qt.QScrollArea = MagicMock
mock_qt.QGroupBox = MagicMock
mock_qt.QListWidget = MagicMock
mock_qt.QListWidgetItem = MagicMock
mock_qt.QFontDatabase = MagicMock
mock_qt.QApplication = MagicMock
mock_qt.QDesktopServices = MagicMock
mock_qt.QUrl = MagicMock
mock_qt.QPixmap = MagicMock

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
    mock_card.id = 123
    mock_card.ord = 0
    mock_note = MagicMock()
    # Mock dict-like behavior for note
    mock_note.keys.return_value = ["Front", "Back"]
    mock_note.items.return_value = [("Front", "Q"), ("Back", "A")]
    mock_note.__getitem__.side_effect = lambda k: "current value"
    mock_note.model.return_value = {"name": "Basic"}
    mock_card.note.return_value = mock_note
    mock_mw.reviewer.card = mock_card
    mock_mw.reviewer.state = "question"
    mock_mw.addonManager.getConfig.return_value = {
        "ai_provider": "openai",
        "api_keys": {"openai": "test-key"},
        "models": {"openai": "gpt-4o-mini"},
        "target_fields": ["Back"],
        "storage_mode": "json",
        "show_hints_button": True,
        "show_options_button": True,
        "options_count": 2,
    }
    
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

    print("Testing reviewer refresh compatibility...")
    import addon.reviewer_hooks as reviewer_hooks
    redraw_calls = []
    original_reviewer = mock_mw.reviewer
    mock_mw.reviewer = SimpleNamespace(
        card=mock_card,
        state="question",
        _redraw_current_card=lambda: redraw_calls.append("redraw"),
    )
    reviewer_hooks.refresh_current_card()
    mock_mw.reviewer = original_reviewer
    if redraw_calls == ["redraw"]:
        print("SUCCESS: refresh_current_card() works without Reviewer.refresh().")
    else:
        print(f"FAILED: refresh_current_card() did not use redraw fallback: {redraw_calls}")
        sys.exit(1)

    # 5. Test JSON storage mode
    print("Testing JSON storage mode...")
    from addon.card_parser import CardParser
    
    json_parser = CardParser(target_fields=["Back"], storage_mode="json")
    mock_note_json = MagicMock()
    mock_note_json.keys.return_value = ["Back"]
    mock_note_json.__getitem__.return_value = "original"
    mock_note_json.model.return_value = {"name": "Basic"}
    mock_card_json = MagicMock()
    mock_card_json.id = 456
    mock_card_json.ord = 2
    
    json_parser.update_note_with_hints(mock_note_json, {"hints": ["H"], "options": ["O"]}, card=mock_card_json)
    
    # Check if JSON was correctly set
    set_value = mock_note_json.__setitem__.call_args[0][1]
    if (
        'class="ai-hints-json"' in set_value
        and '"hints": ["H"]' in set_value
        and 'data-ai-hints-card-id="456"' in set_value
        and 'data-ai-hints-card-ord="2"' in set_value
    ):
        print("SUCCESS: CardParser correctly formats per-card JSON storage mode.")
    else:
        print(f"FAILED: CardParser incorrect JSON formatting: {set_value}")
        sys.exit(1)

    print("Testing find_hints_block and clear_hints_from_note regex fixes...")
    # Test multiple classes and single quotes
    multi_class_html = '<div class="foo ai-hints-json bar" data-ai-hints-card-id="456">payload</div>'
    mock_note_json.values.return_value = [multi_class_html]
    if json_parser.find_hints_block(mock_note_json, mock_card_json) == multi_class_html:
        print("SUCCESS: find_hints_block matches multi-class div.")
    else:
        print("FAILED: find_hints_block failed on multi-class div.")
        sys.exit(1)

    single_quote_html = "<div class='ai-hints-container' data-ai-hints-card-id='456'>payload</div>"
    mock_note_json.values.return_value = [single_quote_html]
    if json_parser.find_hints_block(mock_note_json, mock_card_json) == single_quote_html:
        print("SUCCESS: find_hints_block matches single quote div.")
    else:
        print("FAILED: find_hints_block failed on single quote div.")
        sys.exit(1)

    # Test clear_hints_from_note
    mock_note_json.keys.return_value = ["Back"]
    note_data = {"Back": f"Prefix {multi_class_html} Suffix"}
    mock_note_json.__getitem__.side_effect = note_data.__getitem__
    
    if json_parser.clear_hints_from_note(mock_note_json, mock_card_json):
        # The method sets the value back using note[f_name] = new_val
        # which calls __setitem__
        set_call = mock_note_json.__setitem__.call_args
        if set_call and set_call[0][0] == "Back" and set_call[0][1] == "Prefix  Suffix":
            print("SUCCESS: clear_hints_from_note removed block.")
        else:
            actual = set_call[0][1] if set_call else "None"
            print(f"FAILED: clear_hints_from_note incorrect result: {actual}")
            sys.exit(1)
    else:
        print("FAILED: clear_hints_from_note returned False.")
        sys.exit(1)

    print("Testing current cloze targeting...")
    cloze_parser = CardParser(target_fields=["Extra"], note_type_fields={"Cloze": ["Text"]}, storage_mode="json")
    mock_cloze_note = MagicMock()
    mock_cloze_note.model.return_value = {"name": "Cloze"}
    mock_cloze_note.__contains__.side_effect = lambda k: k == "Text"
    mock_cloze_note.__getitem__.return_value = "{{c1::first answer}} and {{c2::second answer::hint}}"
    mock_cloze_card = MagicMock()
    mock_cloze_card.ord = 1
    front, back = cloze_parser.get_note_content(mock_cloze_note, mock_cloze_card)
    if "Current cloze deletion: second answer" in front and "first answer" in front and "c1::" not in front:
        print("SUCCESS: CardParser targets only the current cloze.")
    else:
        print(f"FAILED: CardParser did not target current cloze: {front!r} / {back!r}")
        sys.exit(1)

    # 6. Test options_count injection in AIClient
    print("Testing options_count injection...")
    from addon.ai_client import AIClient
    
    config = {
        "options_count": 5,
        "system_prompt": "Prompt.",
        "ai_provider": "openai",
        "api_keys": {"openai": "test-key"},
    }
    client = AIClient(config)
    
    # We can't easily test the network call, but we can check if it tries to use the right prompt
    # Let's mock _call_openai_compatible to see what system_prompt it receives
    client._call_openai_compatible = MagicMock(return_value={"hints": [], "options": []})
    client.generate_options("F", "B")
    
    received_system_prompt = client._call_openai_compatible.call_args[0][1]
    if "exactly 5 options total" in received_system_prompt and "Include the correct answer" in received_system_prompt:
        print("SUCCESS: AIClient correctly injects options_count into prompt.")
    else:
        print(f"FAILED: AIClient incorrect prompt injection: {received_system_prompt}")
        sys.exit(1)

    print("Testing correct answer inclusion in options...")
    answer_client = AIClient({
        "options_count": 4,
        "system_prompt": "Prompt.",
        "ai_provider": "openai",
        "api_keys": {"openai": "test-key"},
    })
    answer_client._call_openai_compatible = MagicMock(return_value={
        "hints": ["H"],
        "options": ["Lyon", "Marseille", "Bordeaux", "Nice"],
    })
    answer_result = answer_client.generate_options("Capital of France?", "Paris")
    if "Paris" in answer_result["options"] and len(answer_result["options"]) == 4:
        print("SUCCESS: AIClient includes the correct answer as an MCQ option.")
    else:
        print(f"FAILED: AIClient did not include correct answer: {answer_result}")
        sys.exit(1)

    print("Testing model fallback after bad output...")
    fallback_client = AIClient({
        "ai_provider": "groq",
        "api_keys": {"groq": "test-key"},
        "models": {"groq": "bad-model"},
        "model_fallbacks": {"groq": ["good-model"]},
        "options_count": 2,
    })
    attempted_models = []

    def fake_post_json(url, data, headers):
        attempted_models.append(data["model"])
        if data["model"] == "bad-model":
            return {"choices": [{"message": {"content": "not json"}}]}
        return {"choices": [{"message": {"content": '{"hints":["H"],"options":["O1","O2"]}'}}]}

    fallback_client._post_json = fake_post_json
    fallback_result = fallback_client._call_openai_compatible("groq", "system", "prompt")
    if attempted_models == ["bad-model", "good-model"] and fallback_result["hints"] == ["H"]:
        print("SUCCESS: AIClient falls back to another model after unusable output.")
    else:
        print(f"FAILED: AIClient model fallback failed: {attempted_models} / {fallback_result}")
        sys.exit(1)

except Exception as e:
    print(f"CRITICAL FAILURE during add-on load: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nAll local verification tests passed.")
