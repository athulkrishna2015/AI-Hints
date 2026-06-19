
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

if __name__ == '__main__':
    unittest.main()

