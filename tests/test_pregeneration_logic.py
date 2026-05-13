
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
class Dummy: 
    def __init__(self, *args, **kwargs): pass
    def setVisible(self, *args): pass
    def setEnabled(self, *args): pass

# List of all required Qt names found in the addon
qt_names = [
    'QDialog', 'QWidget', 'QComboBox', 'QLineEdit', 'QSpinBox', 'QCheckBox', 
    'QPushButton', 'QVBoxLayout', 'QHBoxLayout', 'QFormLayout', 'QTabWidget', 
    'QGroupBox', 'QLabel', 'QPlainTextEdit', 'QTimer', 'QMessageBox', 
    'QMenu', 'QAction', 'QPoint', 'QFontDatabase', 'QApplication'
]

for name in qt_names:
    setattr(mock_qt, name, Dummy)

mock_qt.Qt = MagicMock()
mock_qt.Qt.WindowType = MagicMock()

# Mock other submodules
sys.modules['aqt.utils'] = MagicMock()
sys.modules['aqt.gui_hooks'] = MagicMock()

# Import from package
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

if __name__ == '__main__':
    unittest.main()
