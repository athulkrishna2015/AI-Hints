import sys
import os
import urllib.error
from io import BytesIO
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
    import addon.config_ui
    original_config_dialog = addon.config_ui.ConfigDialog
    
    # Simulate Anki calling it without arguments
    try:
        # Mock ConfigDialog to not actually open a window
        addon.config_ui.ConfigDialog = MagicMock()
        
        on_config_dialog()
        print("SUCCESS: on_config_dialog() works without arguments.")
    except TypeError as e:
        print(f"FAILED: on_config_dialog() still has TypeError: {e}")
        sys.exit(1)

    print("Testing malformed raw config normalization...")
    normalized_config = original_config_dialog._normalize_config(None, {
        "api_keys": ["bad"],
        "models": ["bad"],
        "model_fallbacks": ["bad"],
        "local_endpoint": ["bad"],
        "custom_providers": ["bad"],
        "note_type_fields": ["bad"],
        "options_count": "999",
    })
    if (
        isinstance(normalized_config["api_keys"], dict)
        and isinstance(normalized_config["custom_providers"], dict)
        and normalized_config["options_count"] == 10
    ):
        print("SUCCESS: malformed raw config is normalized safely.")
    else:
        print(f"FAILED: malformed raw config normalization incorrect: {normalized_config}")
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

    print("Testing generated data is pushed and cached for stale note renders...")
    import addon.reviewer_hooks as reviewer_hooks
    eval_calls = [call[0][0] for call in mock_mw.reviewer.web.eval.call_args_list]
    if any("aiHintsUpdateData" in call for call in eval_calls):
        print("SUCCESS: generate_hints() pushes generated data to the current webview.")
    else:
        print(f"FAILED: generate_hints() did not push generated data: {eval_calls}")
        sys.exit(1)

    mock_note.values.return_value = ["Front", "Back without saved block yet"]
    web_content = SimpleNamespace(head="", body="", css=["reviewer.css"])
    reviewer_hooks.on_webview_will_set_content(web_content, SimpleNamespace(name="reviewer", card=mock_card))
    if "Hint 1" in web_content.body and "ai-hints-json" in web_content.body:
        print("SUCCESS: cached generated data is injected during stale redraws.")
    else:
        print(f"FAILED: cached generated data was not injected: {web_content.body}")
        sys.exit(1)

    print("Testing reviewer refresh compatibility...")
    refresh_calls = []
    original_reviewer = mock_mw.reviewer
    original_get_card = mock_mw.col.getCard
    old_refresh_card = SimpleNamespace(id=321, timer_started=123)
    fresh_refresh_card = SimpleNamespace(id=321, timer_started=None)
    mock_mw.col.getCard = lambda cid: fresh_refresh_card
    mock_mw.reviewer = SimpleNamespace(
        card=old_refresh_card,
        state="question",
        _showQuestion=lambda: refresh_calls.append("question"),
    )
    reviewer_hooks.refresh_current_card()
    refreshed_card = mock_mw.reviewer.card
    mock_mw.reviewer = original_reviewer
    mock_mw.col.getCard = original_get_card
    if (
        refresh_calls == ["question"]
        and refreshed_card is fresh_refresh_card
        and getattr(refreshed_card, "timer_started", None) == 123
    ):
        print("SUCCESS: refresh_current_card() reloads and redraws the current reviewer card.")
    else:
        print(f"FAILED: refresh_current_card() did not reload/redraw correctly: {refresh_calls} / {refreshed_card}")
        sys.exit(1)

    print("Testing browser context menu clears selected card hints...")
    class FakeNote:
        def __init__(self, fields):
            self.fields = dict(fields)
            self.flush_count = 0

        def keys(self):
            return list(self.fields.keys())

        def values(self):
            return list(self.fields.values())

        def __getitem__(self, key):
            return self.fields[key]

        def __setitem__(self, key, value):
            self.fields[key] = value

        def flush(self):
            self.flush_count += 1

    shared_note = FakeNote({
        "Back": (
            'A <div class="ai-hints-json" data-ai-hints-card-id="701">one</div> '
            'B <div class="ai-hints-json" data-ai-hints-card-id="702">two</div> C'
        )
    })
    browser_cards = {
        701: SimpleNamespace(id=701, ord=0, nid=9001, note=lambda: shared_note),
        702: SimpleNamespace(id=702, ord=1, nid=9001, note=lambda: shared_note),
    }
    original_get_card = getattr(mock_mw.col, "get_card", None)
    mock_mw.col.get_card = lambda cid: browser_cards.get(cid)
    browser_refresh_calls = []
    fake_browser = SimpleNamespace(
        selectedCards=lambda: [701, 702],
        onReset=lambda: browser_refresh_calls.append("reset"),
    )
    selected_count, changed_cards, changed_notes = reviewer_hooks.clear_ai_hints_from_browser_selection(fake_browser)
    mock_mw.col.get_card = original_get_card
    if (
        selected_count == 2
        and changed_cards == 2
        and changed_notes == 1
        and "ai-hints-json" not in shared_note.fields["Back"]
        and shared_note.flush_count == 1
        and browser_refresh_calls == ["reset"]
    ):
        print("SUCCESS: browser selected-card clear removes AI-Hints and refreshes once.")
    else:
        print(
            "FAILED: browser selected-card clear result incorrect: "
            f"{selected_count}, {changed_cards}, {changed_notes}, "
            f"{shared_note.fields}, flush={shared_note.flush_count}, refresh={browser_refresh_calls}"
        )
        sys.exit(1)

    print("Testing browser context menu action is added...")
    class FakeSignal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

    class FakeAction:
        def __init__(self, text):
            self.text = text
            self.enabled = None
            self.triggered = FakeSignal()

        def setEnabled(self, enabled):
            self.enabled = enabled

    class FakeMenu:
        def __init__(self):
            self.actions = []
            self.separators = 0

        def addSeparator(self):
            self.separators += 1

        def addAction(self, text):
            action = FakeAction(text)
            self.actions.append(action)
            return action

    fake_menu = FakeMenu()
    reviewer_hooks.on_browser_context_menu(fake_browser, fake_menu)
    if (
        fake_menu.separators == 1
        and fake_menu.actions
        and fake_menu.actions[0].text == "Clear AI-Hints"
        and fake_menu.actions[0].enabled is True
        and fake_menu.actions[0].triggered.callback is not None
    ):
        print("SUCCESS: browser context menu includes Clear AI-Hints action.")
    else:
        print(f"FAILED: browser context menu action incorrect: {fake_menu.__dict__}")
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

    print("Testing clear_hints_from_note only writes changed fields...")
    scoped_html = '<div class="ai-hints-json" data-ai-hints-card-id="456">payload</div>'
    other_html = '<div class="ai-hints-json" data-ai-hints-card-id="999">payload</div>'
    multi_field_note = MagicMock()
    multi_field_note.keys.return_value = ["Back", "Extra"]
    multi_field_values = {"Back": f"A {scoped_html} B", "Extra": f"C {other_html} D"}
    multi_field_note.__getitem__.side_effect = multi_field_values.__getitem__
    if not json_parser.clear_hints_from_note(multi_field_note, mock_card_json):
        print("FAILED: clear_hints_from_note returned False for multi-field note.")
        sys.exit(1)
    set_calls = multi_field_note.__setitem__.call_args_list
    if len(set_calls) == 1 and set_calls[0][0] == ("Back", "A  B"):
        print("SUCCESS: clear_hints_from_note leaves unchanged fields untouched.")
    else:
        print(f"FAILED: clear_hints_from_note wrote unexpected fields: {set_calls}")
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

    print("Testing HTML cleanup for correct answer options...")
    html_answer_client = AIClient({
        "options_count": 2,
        "ai_provider": "openai",
        "api_keys": {"openai": "test-key"},
    })
    html_answer_client._call_openai_compatible = MagicMock(return_value={
        "hints": ["H"],
        "options": ["Distractor", "Other"],
    })
    html_answer_result = html_answer_client.generate_options("Q", "<b>Paris</b><br>France")
    if "Paris France" in html_answer_result["options"]:
        print("SUCCESS: AIClient strips HTML from inserted correct answer.")
    else:
        print(f"FAILED: AIClient kept HTML in correct answer: {html_answer_result}")
        sys.exit(1)

    print("Testing raw config robustness for non-string model/header values...")
    raw_client = AIClient({
        "ai_provider": "custom",
        "custom_providers": {
            "custom": {
                "url": "http://example.invalid/v1/chat/completions",
                "api_key": 123,
                "model": 456,
                "headers": ["not", "a", "dict"],
            }
        },
    })
    if not raw_client.has_ready_provider("custom"):
        print("FAILED: AIClient rejected string-coercible custom provider config.")
        sys.exit(1)
    raw_models = raw_client._models_for_provider("custom", 456, [789])
    raw_headers = raw_client._json_headers(123)
    if raw_models[:2] == ["456", "789"] and raw_headers.get("Authorization") == "Bearer 123":
        print("SUCCESS: AIClient handles raw config values defensively.")
    else:
        print(f"FAILED: AIClient raw config handling incorrect: {raw_models} / {raw_headers}")
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

    print("Testing Gemini quota skip to speed provider fallback...")
    gemini_client = AIClient({
        "ai_provider": "gemini",
        "api_keys": {"gemini": "test-key"},
        "models": {"gemini": "quota-model"},
        "model_fallbacks": {"gemini": ["slow-fallback-model"]},
    })
    gemini_attempts = []

    def fake_gemini_post_json(url, data, headers):
        gemini_attempts.append(url)
        body = b'{"error":{"status":"RESOURCE_EXHAUSTED","message":"Quota exceeded. See rate-limits."}}'
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, BytesIO(body))

    gemini_client._post_json = fake_gemini_post_json
    gemini_result = gemini_client._call_gemini("system", "prompt")
    if len(gemini_attempts) == 1 and gemini_result == {"hints": [], "options": []}:
        print("SUCCESS: Gemini quota errors skip remaining Gemini models.")
    else:
        print(f"FAILED: Gemini quota skip incorrect: attempts={len(gemini_attempts)} result={gemini_result}")
        sys.exit(1)

except Exception as e:
    print(f"CRITICAL FAILURE during add-on load: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nAll local verification tests passed.")
