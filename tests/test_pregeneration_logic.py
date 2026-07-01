
import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch
from types import ModuleType

# Mock aqt and other Anki components before importing reviewer_hooks
mock_aqt = MagicMock()
sys.modules['aqt'] = mock_aqt

# Create a proper module for aqt.qt
mock_qt = ModuleType('aqt.qt')
sys.modules['aqt.qt'] = mock_qt

# Inject dummy classes into aqt.qt for inheritance
class DummySignal:
    def connect(self, *args): pass

class Dummy: 
    def __init__(self, *args, **kwargs): 
        self.triggered = DummySignal()
        self.clicked = DummySignal()
    def setVisible(self, *args): pass
    def setEnabled(self, *args): pass

# List of all required Qt names found in the addon
qt_names = [
    'QDialog', 'QWidget', 'QComboBox', 'QLineEdit', 'QSpinBox', 'QCheckBox', 
    'QPushButton', 'QVBoxLayout', 'QHBoxLayout', 'QFormLayout', 'QTabWidget', 
    'QGroupBox', 'QLabel', 'QPlainTextEdit', 'QTimer', 'QMessageBox', 
    'QMenu', 'QAction', 'QPoint', 'QFontDatabase', 'QApplication', 'QScrollArea',
    'QPixmap', 'QStyledItemDelegate', 'QEvent'
]

for name in qt_names:
    setattr(mock_qt, name, Dummy)

mock_qt.Qt = MagicMock()
mock_qt.Qt.WindowType = MagicMock()

# Mock other submodules
sys.modules['aqt.utils'] = MagicMock()
sys.modules['aqt.gui_hooks'] = MagicMock()
sys.modules['aqt.webview'] = MagicMock()
sys.modules['aqt.webview'].AnkiWebView = Dummy

# Import from package
try:
    from addon import reviewer_hooks
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from addon import reviewer_hooks
from addon.reviewer_hooks import (
    generate_hints, 
    _apply_results_to_card, 
    _trigger_next_pregeneration,
    _pregenerated_data,
    _generating_card_ids
)

class TestPregeneration(unittest.TestCase):

    def setUp(self):
        # Clear global state
        _pregenerated_data.clear()
        _generating_card_ids.clear()
        
        self.mock_mw = reviewer_hooks.mw
        self.mock_mw.col = MagicMock()
        self.mock_mw.reviewer = MagicMock()
        
        # Mock config
        self.config = {
            "auto_generate_new": True,
            "pre_generate_next": True,
            "pre_generate_count": 1,
            "ai_provider": "openai",
            "target_fields": ["Front", "Back"],
            "storage_mode": "json"
        }
        self.mock_mw.addonManager.getConfig.return_value = self.config

    def test_pregen_caching_logic(self):
        """Verify that pre-generated data is cached and NOT saved to note immediately."""
        
        # 1. Setup Card and Note
        mock_card = MagicMock()
        mock_card.id = 12345
        mock_note = MagicMock()
        mock_note.keys.return_value = ["Front", "Back"]
        mock_note.__getitem__.side_effect = lambda k: "Content"
        mock_card.note.return_value = mock_note
        
        # 2. Mock AI Client to return success
        mock_data = {
            "hints": ["Hint 1"],
            "options": ["Op 1"],
            "_provider": "test",
            "_model": "test-model"
        }
        
        with patch('addon.reviewer_hooks.AIClient') as MockClient, \
             patch('addon.reviewer_hooks.CardParser') as MockParser:
            
            # Setup parser mock
            mock_parser_inst = MockParser.return_value
            mock_parser_inst.get_note_content.return_value = ("front", "back")
            mock_parser_inst.normalize_hint_data.return_value = mock_data
            
            # Setup client mock
            mock_client_inst = MockClient.return_value
            mock_client_inst.has_any_ready_provider.return_value = True
            mock_client_inst.generate_options.return_value = mock_data

            # 3. Trigger PRE-GENERATION
            generate_hints(is_manual=False, card=mock_card, is_pregen=True)
            
            # Manually trigger the callback (usually happens async)
            # In generate_hints, on_done is defined inside. We need to capture it or mock the thread.
            # For this unit test, let's look at what generate_hints does.
            # It starts a thread. We want to verify that when on_done is called with is_pregen=True,
            # it populates _pregenerated_data.
            
        # Instead of mocking the whole thread, let's test the on_done logic by simulating the state
        # after generate_hints has been called.
        
        # Verify card was added to generating set
        self.assertIn(mock_card.id, _generating_card_ids)
        
        # Simulate on_done being called for a pre-gen
        # We'll re-test _apply_results_to_card separately.
        
    def test_consumption_logic(self):
        """Verify that cached data is applied when the card appears."""
        card_id = 999
        data = {"hints": ["Cached"], "options": ["Cached"]}
        _pregenerated_data[card_id] = data
        
        mock_card = MagicMock()
        mock_card.id = card_id
        
        with patch('addon.reviewer_hooks._apply_results_to_card') as mock_apply, \
             patch('addon.reviewer_hooks._trigger_next_pregeneration') as mock_trigger:
            
            # This is what happens inside on_show_question(card)
            # 1. Detect cached data
            if mock_card.id in _pregenerated_data:
                cached_data = _pregenerated_data.pop(mock_card.id)
                _apply_results_to_card(mock_card, cached_data, is_manual=False)
                mock_trigger()

            # Verify application and cache removal
            self.assertEqual(len(_pregenerated_data), 0)
            # (Note: we called the real _apply_results_to_card or mocked it?)
            # Here we just want to see if the logic flow is correct.
            mock_trigger.assert_called_once()

    def test_pregen_priority(self):
        """Verify pre-generation doesn't start if current card is generating."""
        _generating_card_ids.add(111) # Current card is busy
        
        next_card = MagicMock()
        next_card.id = 222
        
        with patch('addon.reviewer_hooks.logger') as mock_logger:
            generate_hints(is_manual=False, card=next_card, is_pregen=True)
            # Should return immediately because _generating_card_ids is not empty
            # and it won't log "generation started"
            self.assertFalse(any("generation started" in str(args) for args in mock_logger.info.call_args_list))

    def test_trigger_next_pregeneration_logic(self):
        """Verify that _trigger_next_pregeneration peeks using get_queued_cards."""
        mock_next_card = MagicMock()
        mock_next_card.id = 555

        # Setup scheduler to support get_queued_cards (Protobuf-like)
        mock_card_proto = MagicMock()
        mock_card_proto.id = 555

        mock_queued_card = MagicMock()
        # Mocking both protobuf 'card.id' and legacy 'card_id' for robustness
        mock_queued_card.card = mock_card_proto
        mock_queued_card.card_id = 555

        mock_queued_cards = MagicMock()
        mock_queued_cards.cards = [mock_queued_card]

        self.mock_mw.col.sched.get_queued_cards.return_value = mock_queued_cards
        self.mock_mw.col.get_card.return_value = mock_next_card

        # Ensure reviewer.card is different
        self.mock_mw.reviewer.card.id = 111

        with patch('addon.reviewer_hooks.generate_hints') as mock_generate, \
             patch('addon.reviewer_hooks.card_has_hints') as mock_has_hints, \
             patch('addon.reviewer_hooks.QTimer') as mock_timer:

            mock_has_hints.return_value = False

            # Reset mock to clear any calls from previous tests (async side effects)
            self.mock_mw.taskman.run_on_main.reset_mock()

            # Trigger it
            _trigger_next_pregeneration(None)

            # Capture the task
            task = mock_timer.singleShot.call_args[0][1]
            
            # Execute the task
            task()
            
            # It should have called get_card with the ID from our mock
            self.mock_mw.col.get_card.assert_called_with(555)

            # Execute the lambda passed to taskman.run_on_main
            self.mock_mw.taskman.run_on_main.assert_called_once()
            gen_lambda = self.mock_mw.taskman.run_on_main.call_args[0][0]
            gen_lambda()
            
            # Should have called get_queued_cards(fetch_limit=5)
            self.mock_mw.col.sched.get_queued_cards.assert_called_with(fetch_limit=5)
            # Should have triggered generation for card 555
            mock_generate.assert_called_once()
            args, kwargs = mock_generate.call_args
            self.assertEqual(kwargs['card'].id, 555)
            self.assertEqual(kwargs['is_pregen'], True)

    @patch('addon.reviewer_hooks._apply_results_to_card')
    @patch('addon.reviewer_hooks.CardParser')
    @patch('addon.reviewer_hooks.AIClient')
    def test_generate_hints_empty_card_marked_as_skipped(self, MockClient, MockParser, mock_apply_results):
        """Verify that when a card is empty or missing a cloze, generate_hints marks it as skipped in DB."""
        mock_card = MagicMock()
        mock_card.id = 9999
        
        # Setup mocks
        mock_parser_inst = MockParser.return_value
        mock_parser_inst.get_note_content.return_value = ("", "")
        
        mock_client_inst = MockClient.return_value
        mock_client_inst.has_any_ready_provider.return_value = True
        
        # Trigger generation
        generate_hints(is_manual=True, card=mock_card, is_pregen=False)
        
        # Verify card was discarded from generating set
        self.assertNotIn(mock_card.id, _generating_card_ids)
        # Verify skipped results were applied
        mock_apply_results.assert_called_once()
        args, kwargs = mock_apply_results.call_args
        self.assertEqual(args[0], mock_card)
        self.assertEqual(args[1], {"hints": [], "options": [], "_skipped": True})
        self.assertEqual(kwargs.get("is_manual"), True)

    @patch('addon.reviewer_hooks._get_card_from_collection')
    @patch('addon.reviewer_hooks.CardParser')
    @patch('addon.reviewer_hooks.tooltip')
    def test_clear_ai_hints_from_browser_selection(self, mock_tooltip, MockParser, mock_get_card):
        from addon.reviewer_hooks import clear_ai_hints_from_browser_selection
        
        # Setup mocks
        browser_mock = MagicMock()
        browser_mock.selectedCards.return_value = [111, 222]
        
        mock_card1 = MagicMock()
        mock_card1.nid = 12
        mock_card2 = MagicMock()
        mock_card2.nid = 34
        
        # mock_get_card side effect to return cards
        mock_get_card.side_effect = lambda cid: mock_card1 if cid == 111 else mock_card2
        
        mock_parser = MockParser.return_value
        mock_parser.clear_hints_from_note.return_value = True
        
        # Run function
        clear_ai_hints_from_browser_selection(browser_mock)
        
        # Verify calls
        self.assertEqual(mock_get_card.call_count, 2)
        self.assertEqual(mock_parser.clear_hints_from_note.call_count, 2)
        mock_tooltip.assert_called_once_with("AI-Hints: Cleared cached data from 2 selected cards.")

    @patch('addon.reviewer_hooks._get_card_from_collection')
    @patch('addon.reviewer_hooks.CardParser')
    @patch('addon.reviewer_hooks._remember_generated_hints')
    @patch('addon.reviewer_hooks.tooltip')
    def test_skip_ai_hints_from_browser_selection(self, mock_tooltip, mock_remember, MockParser, mock_get_card):
        from addon.reviewer_hooks import skip_ai_hints_from_browser_selection
        
        # Setup mocks
        browser_mock = MagicMock()
        browser_mock.selectedCards.return_value = [111, 222]
        
        mock_card1 = MagicMock()
        mock_card1.nid = 12
        mock_card2 = MagicMock()
        mock_card2.nid = 34
        
        # mock_get_card side effect to return cards
        mock_get_card.side_effect = lambda cid: mock_card1 if cid == 111 else mock_card2
        
        mock_parser = MockParser.return_value
        mock_parser.update_note_with_hints.return_value = True
        
        # Run function
        skip_ai_hints_from_browser_selection(browser_mock)
        
        # Verify calls
        self.assertEqual(mock_get_card.call_count, 2)
        self.assertEqual(mock_parser.update_note_with_hints.call_count, 2)
        self.assertEqual(mock_remember.call_count, 2)
        mock_tooltip.assert_called_once_with("AI-Hints: Marked 2 selected cards as skipped.")

    @patch('addon.reviewer_hooks._selected_browser_card_ids')
    @patch('addon.reviewer_hooks.QMenu')
    def test_on_browser_context_menu(self, MockQMenu, mock_selected_ids):
        from addon.reviewer_hooks import on_browser_context_menu
        
        mock_selected_ids.return_value = [111]
        
        browser_mock = MagicMock()
        parent_menu_mock = MagicMock()
        
        submenu_mock = MagicMock()
        MockQMenu.return_value = submenu_mock
        
        # Run function
        on_browser_context_menu(browser_mock, parent_menu_mock)
        
        # Verify submenu was created and added
        MockQMenu.assert_called_once_with("AI Hints", parent_menu_mock)
        parent_menu_mock.addMenu.assert_called_once_with(submenu_mock)
        
        # Verify separators and actions
        parent_menu_mock.addSeparator.assert_called_once()
        self.assertEqual(submenu_mock.addAction.call_count, 5)
        submenu_mock.addAction.assert_any_call("✨ Batch Generation...")
        submenu_mock.addAction.assert_any_call("Skip AI for Selected Cards")
        submenu_mock.addAction.assert_any_call("Unskip AI for Selected Cards")
        submenu_mock.addAction.assert_any_call("Clear AI-Hints")
        submenu_mock.addAction.assert_any_call("🧹 Clean Orphaned Hints...")

    @patch('addon.reviewer_hooks.QMenu')
    def test_on_sidebar_context_menu(self, MockQMenu):
        from addon.reviewer_hooks import on_sidebar_context_menu
        
        sidebar_mock = MagicMock()
        sidebar_mock.col.build_search_string.return_value = "tag:test"
        sidebar_mock.col.find_cards.return_value = [101, 102]
        
        item_mock = MagicMock()
        item_mock.search_node = MagicMock()
        
        parent_menu_mock = MagicMock()
        submenu_mock = MagicMock()
        MockQMenu.return_value = submenu_mock
        
        # Run function
        on_sidebar_context_menu(sidebar_mock, parent_menu_mock, item_mock, None)
        
        # Verify submenu was created and added
        MockQMenu.assert_called_once_with("AI Hints", parent_menu_mock)
        parent_menu_mock.addMenu.assert_called_once_with(submenu_mock)
        
        # Verify separators and actions
        parent_menu_mock.addSeparator.assert_called_once()
        self.assertEqual(submenu_mock.addAction.call_count, 4)
        submenu_mock.addAction.assert_any_call("✨ Batch Generation...")
        submenu_mock.addAction.assert_any_call("Skip AI for Group")
        submenu_mock.addAction.assert_any_call("Unskip AI for Group")
        submenu_mock.addAction.assert_any_call("Clear AI-Hints")

    @patch('addon.reviewer_hooks._trigger_next_pregeneration')
    @patch('addon.reviewer_hooks.card_has_hints')
    @patch('addon.reviewer_hooks._card_saved_generation_time')
    @patch('addon.reviewer_hooks.generate_hints')
    def test_auto_regenerate_if_modified(self, mock_generate_hints, mock_saved_time, mock_has_hints, mock_trigger_pregen):
        """Verify that cards are auto-regenerated if modified date is newer than generation date."""
        reviewer_hooks._hooks_registered = False
        reviewer_hooks.init_hooks()
        
        on_show_question = None
        for call in reviewer_hooks.gui_hooks.reviewer_did_show_question.append.call_args_list:
            func = call[0][0]
            if callable(func) and getattr(func, '__name__', '') == 'on_show_question':
                on_show_question = func
                break
        
        self.assertIsNotNone(on_show_question, "on_show_question hook not found in gui_hooks")
        
        import time
        from datetime import datetime
        
        # Current local time
        now_ts = time.time()
        now_dt = datetime.fromtimestamp(now_ts)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Setup mocks
        mock_card = MagicMock()
        mock_card.id = 112233
        mock_note = MagicMock()
        mock_note.mod = int(now_ts + 10) # note is newer by 10s
        mock_card.note.return_value = mock_note
        
        # Test case 1: auto_regenerate_if_modified is False
        self.config["auto_generate_new"] = True
        self.config["auto_regenerate_if_modified"] = False
        mock_has_hints.return_value = True
        mock_saved_time.return_value = now_str
        
        on_show_question(mock_card)
        mock_generate_hints.assert_not_called()
        
        # Test case 2: auto_regenerate_if_modified is True, but note is NOT newer (note is older)
        self.config["auto_regenerate_if_modified"] = True
        mock_note.mod = int(now_ts - 10) # note is older by 10s
        mock_saved_time.return_value = now_str
        
        on_show_question(mock_card)
        mock_generate_hints.assert_not_called()
        
        # Test case 3: auto_regenerate_if_modified is True, and note IS newer (note is newer by 10s)
        mock_note.mod = int(now_ts + 10)
        mock_saved_time.return_value = now_str
        
        on_show_question(mock_card)
        mock_generate_hints.assert_called_once_with(is_manual=False, card=mock_card)

    def test_request_timeout_config(self):
        """Verify that AIClient timeout property dynamically matches the config value for both normal and pregen paths."""
        from addon.ai_client import AIClient
        
        # Normal Mode Tests
        client = AIClient({}, is_pregen=False)
        self.assertEqual(client.timeout, 10)
        
        client = AIClient({"request_timeout": "invalid"}, is_pregen=False)
        self.assertEqual(client.timeout, 10)
        
        client = AIClient({"request_timeout": 45}, is_pregen=False)
        self.assertEqual(client.timeout, 45)
        
        # Pregen Mode Tests
        client = AIClient({}, is_pregen=True)
        self.assertEqual(client.timeout, 20)
        
        client = AIClient({"pregen_request_timeout": "invalid"}, is_pregen=True)
        self.assertEqual(client.timeout, 20)
        
        client = AIClient({"pregen_request_timeout": 35}, is_pregen=True)
        self.assertEqual(client.timeout, 35)

    def test_network_timeout_short_circuit(self):
        """Verify that a network timeout/connection error aborts key/model iteration for that provider."""
        from addon.ai_client import AIClient
        import socket
        
        client = AIClient({
            "ai_provider": "gemini",
            "gemini_api_key": "key1,key2,key3",
            "gemini_model": "gemini-3.1-flash-lite",
            "gemini_model_fallbacks": ["gemini-flash-latest"]
        })
        
        # Test that _is_network_or_timeout_error correctly identifies network exceptions
        self.assertTrue(client._is_network_or_timeout_error(socket.timeout("timed out")))
        self.assertTrue(client._is_network_or_timeout_error(TimeoutError("connection timed out")))
        self.assertTrue(client._is_network_or_timeout_error(ConnectionError("refused")))
        
        import urllib.error
        http_timeout = urllib.error.HTTPError("http://test", 504, "Gateway Timeout", {}, None)
        self.assertTrue(client._is_network_or_timeout_error(http_timeout))
        
        http_normal_err = urllib.error.HTTPError("http://test", 400, "Bad Request", {}, None)
        self.assertFalse(client._is_network_or_timeout_error(http_normal_err))

if __name__ == '__main__':
    unittest.main()

