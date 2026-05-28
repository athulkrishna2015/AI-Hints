import unittest
import sys
import os
import json
from unittest.mock import MagicMock, patch
from types import ModuleType

# Mock aqt before importing batch_manager
mock_aqt = MagicMock()
sys.modules['aqt'] = mock_aqt
mock_qt = ModuleType('aqt.qt')
sys.modules['aqt.qt'] = mock_qt

class Dummy:
    def __init__(self, *args, **kwargs): pass
    def isActive(self): return False
    def start(self, *args): pass
    def stop(self): pass

setattr(mock_qt, 'QTimer', Dummy)

# Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from addon.batch_manager import BatchManager, initialize_batch_manager, STATE_FILE, batch_manager

class TestBatchManager(unittest.TestCase):

    def setUp(self):
        # Backup STATE_FILE if it exists
        self.state_file_backup = None
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    self.state_file_backup = f.read()
            except Exception:
                pass
            try:
                os.remove(STATE_FILE)
            except Exception:
                pass

    def tearDown(self):
        # Restore STATE_FILE
        if os.path.exists(STATE_FILE):
            try:
                os.remove(STATE_FILE)
            except Exception:
                pass
        if self.state_file_backup is not None:
            try:
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    f.write(self.state_file_backup)
            except Exception:
                pass

    def test_state_persistence_active_paused(self):
        """Test that active and paused states are correctly saved and loaded."""
        manager = BatchManager()
        manager.local_queue = [1, 2, 3]
        manager.local_queue_total = 3
        manager.local_queue_errors = 1
        manager.local_queue_active = True
        manager.local_queue_paused = True

        manager.save_state()

        # Check content of state file
        self.assertTrue(os.path.exists(STATE_FILE))
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cache = data.get("local_cache", {})
        self.assertEqual(cache.get("queue"), [1, 2, 3])
        self.assertEqual(cache.get("total"), 3)
        self.assertEqual(cache.get("errors"), 1)
        self.assertEqual(cache.get("active"), True)
        self.assertEqual(cache.get("paused"), True)

        # Load into a new manager to verify recovery
        new_manager = BatchManager()
        self.assertEqual(new_manager.local_queue, [1, 2, 3])
        self.assertEqual(new_manager.local_queue_total, 3)
        self.assertEqual(new_manager.local_queue_errors, 1)
        self.assertEqual(new_manager.local_queue_active, True)
        self.assertEqual(new_manager.local_queue_paused, True)

    def test_set_pause_local_queue_saves_immediately(self):
        """Test that calling set_pause_local_queue saves the state to disk immediately."""
        manager = BatchManager()
        manager.local_queue = [4, 5]
        manager.local_queue_active = True
        manager.local_queue_paused = False
        manager.save_state()

        # Change pause state using public method
        manager.set_pause_local_queue(True)

        # Verify it updated in file immediately
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertTrue(data.get("local_cache", {}).get("paused"))

    @patch('addon.batch_manager.BatchManager.start_local_sequential_queue')
    @patch('addon.batch_manager.BatchManager.start_timer_if_needed')
    def test_initialize_batch_manager_auto_resumes(self, mock_start_timer, mock_start_queue):
        """Test that initialize_batch_manager auto-resumes active unpaused sequential queues."""
        # 1. Active & unpaused -> should auto-resume
        batch_manager.local_queue = [100, 200]
        batch_manager.local_queue_active = True
        batch_manager.local_queue_paused = False

        initialize_batch_manager()
        mock_start_queue.assert_called_once_with(None)
        self.assertFalse(batch_manager.local_queue_active)  # Reset to False so start_local_sequential_queue can run

        # Reset mocks
        mock_start_queue.reset_mock()

        # 2. Active but paused -> should NOT auto-resume
        batch_manager.local_queue = [100, 200]
        batch_manager.local_queue_active = True
        batch_manager.local_queue_paused = True

        initialize_batch_manager()
        mock_start_queue.assert_not_called()

        # Reset mocks
        mock_start_queue.reset_mock()

        # 3. Not active -> should NOT auto-resume
        batch_manager.local_queue = [100, 200]
        batch_manager.local_queue_active = False
        batch_manager.local_queue_paused = False

        initialize_batch_manager()
        mock_start_queue.assert_not_called()

if __name__ == "__main__":
    unittest.main()
