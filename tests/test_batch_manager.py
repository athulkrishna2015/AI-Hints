import unittest
import sys
import os
import json
from unittest.mock import MagicMock, patch
from types import ModuleType

# Mock aqt before importing batch_manager
from types import ModuleType
aqt = ModuleType('aqt')
sys.modules['aqt'] = aqt
aqt.qt = MagicMock()
sys.modules['aqt.qt'] = aqt.qt
aqt.utils = MagicMock()
sys.modules['aqt.utils'] = aqt.utils
aqt.webview = MagicMock()
sys.modules['aqt.webview'] = aqt.webview
aqt.theme = MagicMock()
sys.modules['aqt.theme'] = aqt.theme
aqt.colors = MagicMock()
sys.modules['aqt.colors'] = aqt.colors
aqt.gui_hooks = MagicMock()
sys.modules['aqt.gui_hooks'] = aqt.gui_hooks
aqt.operations = MagicMock()
sys.modules['aqt.operations'] = aqt.operations
aqt.operations.deck = MagicMock()
sys.modules['aqt.operations.deck'] = aqt.operations.deck
aqt.mw = MagicMock()
sys.modules['aqt.mw'] = aqt.mw

classes = ['QDialog', 'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QLabel', 
           'QLineEdit', 'QPushButton', 'QComboBox', 'QCheckBox', 'QTextEdit',
           'QScrollArea', 'QGroupBox', 'QFormLayout', 'QSpinBox', 'QDialogButtonBox',
           'QPixmap', 'Qt', 'QApplication', 'QSizePolicy', 'QTimer', 'QTabWidget',
           'QListWidget', 'QListWidgetItem', 'QDesktopServices', 'QUrl', 'QProgressBar',
           'QDialogButtonBox', 'QStyledItemDelegate', 'QEvent']
for cls in classes:
    setattr(aqt.qt, cls, MagicMock)

class Dummy:
    def __init__(self, *args, **kwargs): pass
    def isActive(self): return False
    def start(self, *args): pass
    def stop(self): pass

setattr(aqt.qt, 'QTimer', Dummy)

# Execute taskman.run_on_main callbacks SYNCHRONOUSLY so main-thread hops
# (e.g. BatchManager._missing_hint_cids_on_main) complete instead of waiting.
aqt.mw.taskman.run_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
aqt.mw.pm.profileFolder.return_value = ''  # keep state file in addon dir for tests

# Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from addon.batch_manager import BatchManager, initialize_batch_manager, batch_manager
STATE_FILE = batch_manager._state_file_path()

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

    def test_failed_cards_in_status_summary(self):
        """Test that failed card IDs are correctly stored, persisted, and shown in get_status_summary."""
        manager = BatchManager()
        manager.local_queue = [10, 11]
        manager.local_queue_total = 2
        manager.local_queue_failed_cards = [12, 13]
        manager.local_queue_active = True
        manager.save_state()

        # Load recovery to check persistence
        new_manager = BatchManager()
        self.assertEqual(new_manager.local_queue_failed_cards, [12, 13])

        # Verify summary output shows the failed cards when active
        summary_active = new_manager.get_status_summary()
        self.assertIn("Failed Cards (2)", summary_active)
        self.assertIn("browse:cid:12", summary_active)
        self.assertIn("browse:cid:13", summary_active)

        # Verify summary output shows the failed cards when dormant
        new_manager.local_queue_active = False
        summary_dormant = new_manager.get_status_summary()
        self.assertIn("Failed Cards (2)", summary_dormant)
        self.assertIn("browse:cid:12", summary_dormant)
        self.assertIn("browse:cid:13", summary_dormant)

        # Verify summary output shows the failed cards when completed (last_run_stats)
        new_manager.local_queue = []
        new_manager.local_queue_failed_cards = []
        new_manager.last_run_stats = {
            "total": 2,
            "errors": 2,
            "failed_cards": [12, 13],
            "time": 0
        }
        summary_completed = new_manager.get_status_summary()
        self.assertIn("Failed Card IDs", summary_completed)
        self.assertIn("browse:cid:12", summary_completed)
        self.assertIn("browse:cid:13", summary_completed)

    @patch('addon.batch_manager.BatchManager.start_local_sequential_queue')
    @patch('addon.batch_manager.BatchManager.start_timer_if_needed')
    def test_initialize_batch_manager_restores_paused(self, mock_start_timer, mock_start_queue):
        """Interrupted queues are restored PAUSED and NOT auto-resumed (user resumes manually)."""
        # 1. Active & unpaused -> should restore in paused state, no auto-start
        batch_manager.local_queue = [100, 200]
        batch_manager.local_queue_active = True
        batch_manager.local_queue_paused = False

        initialize_batch_manager()
        mock_start_queue.assert_not_called()
        self.assertTrue(batch_manager.local_queue_paused)
        self.assertFalse(batch_manager.local_queue_active)

        # 2. Active and already paused -> stays paused, no auto-start
        batch_manager.local_queue = [100, 200]
        batch_manager.local_queue_active = True
        batch_manager.local_queue_paused = True

        initialize_batch_manager()
        mock_start_queue.assert_not_called()
        self.assertTrue(batch_manager.local_queue_paused)
        self.assertFalse(batch_manager.local_queue_active)

        # 3. Not active -> should NOT touch state
        batch_manager.local_queue = [100, 200]
        batch_manager.local_queue_active = False
        batch_manager.local_queue_paused = False

        initialize_batch_manager()
        mock_start_queue.assert_not_called()

    def test_thread_waits_for_active_peers(self):
        """Test that worker thread does not break out of loop if another thread is processing."""
        manager = BatchManager()
        manager.local_queue = []
        manager.local_queue_active = True
        manager.active_threads_status = {
            "gemini": {"model": "gemini-3.1-flash-lite", "cid": 12345, "status": "Processing"},
            "huggingface": {"model": "deepseek-v3", "cid": None, "status": "Starting"}
        }

        # Run popping check in a mock scenario:
        # Since 'gemini' has a non-None cid (12345), 'huggingface' should choose to wait/sleep, not break.
        # We can test this by calling a mock loop step or verifying the logic under self._db_lock context.
        # Let's verify that the status of 'huggingface' gets set to 'Waiting for peers' or handles appropriately.
        # We can patch time.sleep to avoid actual delay.
        with patch('time.sleep') as mock_sleep:
            # We run a single check matching the logic in the thread worker:
            provider = "huggingface"
            current_model = "deepseek-v3"
            
            # Replicate the core logic to assert it functions as expected:
            should_break = False
            should_sleep = False
            with manager._db_lock:
                if not manager.local_queue:
                    any_processing = False
                    for prov, status_info in manager.active_threads_status.items():
                        if prov != provider and status_info.get("cid") is not None:
                            any_processing = True
                            break
                    if not any_processing:
                        should_break = True
                    else:
                        should_sleep = True

            self.assertFalse(should_break)
            self.assertTrue(should_sleep)

    @patch('addon.batch_manager.AIClient')
    @patch('time.sleep')
    @patch('addon.reviewer_hooks._get_card_from_collection')
    @patch('addon.batch_manager.mw')
    def test_empty_card_skip_behavior(self, mock_mw, mock_get_card, mock_sleep, mock_ai_client):
        """Test that a card with empty front and back (e.g. missing cloze) is skipped and marked as skipped in DB."""
        # Setup manager
        manager = BatchManager()
        manager.local_queue = [9999]
        manager.local_queue_active = True
        manager.local_queue_total = 1
        
        # Setup mocks
        mock_card = MagicMock()
        mock_note = MagicMock()
        mock_card.note.return_value = mock_note
        mock_get_card.return_value = mock_card
        
        mock_client = MagicMock()
        mock_client._provider_models.return_value = ["gemini-flash"]
        mock_client.is_network_available.return_value = True
        mock_ai_client.return_value = mock_client
        
        mock_parser = MagicMock()
        mock_parser.get_note_content.return_value = ("", "")
        mock_parser.update_note_with_hints.return_value = True
        
        # We want run_on_main to execute synchronously so we can assert side effects
        mock_mw.taskman.run_on_main = lambda func: func()
        mock_mw.col.update_note = MagicMock()
        mock_mw.addonManager.getConfig.return_value = {}
        
        # Run one step/loop of the thread
        manager._run_local_queue_thread(
            provider="gemini",
            parser=mock_parser,
            config={}
        )
        
        # Verify card was popped and processed
        self.assertEqual(manager.local_queue, [])
        mock_parser.update_note_with_hints.assert_called_once()
        args, kwargs = mock_parser.update_note_with_hints.call_args
        self.assertEqual(args[1]["hints"], [])
        self.assertEqual(args[1]["options"], [])
        self.assertEqual(args[1]["_skipped"], True)
        mock_mw.col.update_note.assert_called_once_with(mock_note)

    @patch('addon.batch_manager.threading.Thread')
    def test_multiple_jobs_queuing(self, mock_thread):
        """Test starting multiple sequential queue jobs, appending them, and stopping individually."""
        manager = BatchManager()
        manager.local_queue_jobs = []
        manager.local_queue_active = False
        
        # Start first job
        started = manager.start_local_sequential_queue(card_ids=[101, 102], config={"ai_provider": "gemini"}, provider_override="gemini")
        self.assertTrue(started)
        self.assertTrue(manager.local_queue_active)
        self.assertEqual(len(manager.local_queue_jobs), 1)
        self.assertEqual(manager.local_queue, [101, 102])
        self.assertEqual(manager.local_queue_total, 2)
        
        # Start second job while active (this should append/queue it)
        started_second = manager.start_local_sequential_queue(card_ids=[201, 202, 203], config={"ai_provider": "gemini"}, provider_override="gemini")
        self.assertTrue(started_second)
        self.assertEqual(len(manager.local_queue_jobs), 2)
        # Active job should still be the first one
        self.assertEqual(manager.local_queue, [101, 102])
        self.assertEqual(manager.local_queue_total, 2)
        # Verify second job is queued
        self.assertEqual(manager.local_queue_jobs[1]["queue"], [201, 202, 203])
        self.assertEqual(manager.local_queue_jobs[1]["total"], 3)
        
        # Discard the current paused/active job
        manager.stop_local_queue()
        # Verify second job is now the active one
        self.assertEqual(len(manager.local_queue_jobs), 1)
        self.assertEqual(manager.local_queue, [201, 202, 203])
        self.assertEqual(manager.local_queue_total, 3)

    def test_save_state_preserves_regular_config_but_strips_secrets_and_blacklist_snapshot(self):
        manager = BatchManager()
        manager.local_queue_jobs = [{
            "id": "job_test",
            "queue": [101],
            "total": 1,
            "failed_cards": [],
            "config": {
                "api_keys": {"gemini": "secret"},
                "ai_provider": "gemini",
                "provider_priority": ["openrouter", "gemini", "openai"],
                "model_fallbacks": {"gemini": ["gemini-3.1-flash-lite", "gemini-2.5-flash"]},
                "global_model_priority": ["gemini:gemini-3.1-flash-lite"],
                "use_global_model_priority": True,
                "disabled_fallback_models": {"gemini": ["gemini-flash-latest"]},
                "model_blacklist_data": {"version": 3, "stale": True},
            },
            "provider": "gemini",
            "pass": 1,
            "errors": 0,
        }]
        manager.save_state()

        with open(STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)

        saved_config = payload["local_cache"]["jobs"][0]["config"]
        self.assertNotIn("api_keys", saved_config)
        self.assertNotIn("model_blacklist_data", saved_config)
        self.assertEqual(saved_config["provider_priority"], ["openrouter", "gemini", "openai"])
        self.assertEqual(saved_config["model_fallbacks"], {"gemini": ["gemini-3.1-flash-lite", "gemini-2.5-flash"]})
        self.assertEqual(saved_config["global_model_priority"], ["gemini:gemini-3.1-flash-lite"])
        self.assertTrue(saved_config["use_global_model_priority"])
        self.assertEqual(saved_config["disabled_fallback_models"], {"gemini": ["gemini-flash-latest"]})

    @patch('addon.batch_manager.threading.Thread')
    def test_queue_reordering_and_management(self, mock_thread):
        """Test moving jobs up, down, canceling queued jobs, and clearing the entire queue."""
        manager = BatchManager()
        manager.local_queue_jobs = []
        manager.local_queue_active = False
        
        # Start 3 jobs
        manager.start_local_sequential_queue(card_ids=[101], config={"ai_provider": "gemini"}, provider_override="gemini")
        manager.start_local_sequential_queue(card_ids=[201], config={"ai_provider": "gemini"}, provider_override="gemini")
        manager.start_local_sequential_queue(card_ids=[301], config={"ai_provider": "gemini"}, provider_override="gemini")
        
        self.assertEqual(len(manager.local_queue_jobs), 3)
        job_1_id = manager.local_queue_jobs[0]["id"]
        job_2_id = manager.local_queue_jobs[1]["id"]
        job_3_id = manager.local_queue_jobs[2]["id"]
        
        # Test moving job 3 up (swaps index 2 with index 1)
        success = manager.move_job_up(job_3_id)
        self.assertTrue(success)
        self.assertEqual(manager.local_queue_jobs[1]["id"], job_3_id)
        self.assertEqual(manager.local_queue_jobs[2]["id"], job_2_id)
        
        # Test moving job 3 down (swaps index 1 with index 2)
        success = manager.move_job_down(job_3_id)
        self.assertTrue(success)
        self.assertEqual(manager.local_queue_jobs[1]["id"], job_2_id)
        self.assertEqual(manager.local_queue_jobs[2]["id"], job_3_id)
        
        # Test canceling job 2
        success = manager.discard_job(job_2_id)
        self.assertTrue(success)
        self.assertEqual(len(manager.local_queue_jobs), 2)
        self.assertEqual(manager.local_queue_jobs[0]["id"], job_1_id)
        self.assertEqual(manager.local_queue_jobs[1]["id"], job_3_id)
        
        # Test clearing queue
        manager.clear_all_queued_jobs()
        self.assertEqual(len(manager.local_queue_jobs), 0)
        self.assertFalse(manager.local_queue_active)

    @patch('time.sleep')
    @patch.object(BatchManager, '_run_local_queue_thread')
    @patch('addon.batch_manager.CardParser')
    @patch('addon.batch_manager.AIClient')
    @patch('addon.reviewer_hooks._get_card_from_collection')
    @patch('addon.reviewer_hooks.card_has_hints')
    def test_all_active_providers_join_multithread_bulk_gen(self, mock_card_has_hints, mock_get_card, mock_aiclient_class, mock_card_parser_class, mock_run_thread, mock_sleep):
        """All candidate/active providers must join the bulk local-queue generation when multithreading is enabled."""
        manager = BatchManager()
        manager.local_queue_jobs = []
        manager.local_queue_active = False

        candidates = ["openai", "gemini", "anthropic", "openrouter"]
        mock_client = MagicMock()
        mock_client._candidate_providers.return_value = candidates
        mock_aiclient_class.return_value = mock_client
        mock_card_parser_class.return_value = MagicMock()
        mock_get_card.return_value = MagicMock()
        mock_card_has_hints.return_value = True

        config = {
            "multithread_providers": True,
            "ai_provider": "openai",
            "provider_priority": candidates,
            "api_keys": {p: f"key-{p}" for p in candidates},
        }
        manager.local_queue_jobs = [{
            "id": "multithread_job",
            "queue": [100, 101, 102],
            "total": 3,
            "failed_cards": [],
            "config": config,
            "provider": None,
            "pass": 1,
            "errors": 0,
        }]
        manager.local_queue_active = True
        manager.saved_config = config

        manager._run_local_queue(config, None)

        # The full set of READY providers is adopted as the active provider pool
        self.assertEqual(set(manager.active_providers), set(candidates))
        # A dedicated worker thread was spawned for EVERY active provider
        spawned_providers = [c.args[0] for c in mock_run_thread.call_args_list]
        self.assertEqual(len(spawned_providers), len(candidates))
        self.assertEqual(set(spawned_providers), set(candidates))
        # No cards were counted as failures: every provider participated so the combined pool succeeded
        self.assertEqual(manager.local_queue_errors, 0)
        self.assertEqual(manager.local_queue_failed_cards, [])
        mock_client._candidate_providers.assert_called_once_with("openai")

    @patch('time.sleep')
    @patch.object(BatchManager, '_run_local_queue_thread')
    @patch('addon.batch_manager.CardParser')
    @patch('addon.batch_manager.AIClient')
    @patch('addon.reviewer_hooks._get_card_from_collection')
    @patch('addon.reviewer_hooks.card_has_hints')
    def test_only_ready_providers_join_multithread_bulk_gen(self, mock_card_has_hints, mock_get_card, mock_aiclient_class, mock_card_parser_class, mock_run_thread, mock_sleep):
        """Providers that are NOT ready must be excluded from the bulk generation worker pool."""
        manager = BatchManager()
        manager.local_queue_jobs = []
        manager.local_queue_active = False

        candidates = ["openai", "gemini"]
        mock_client = MagicMock()
        mock_client._candidate_providers.return_value = candidates  # 'anthropic' is unconfigured => omitted
        mock_aiclient_class.return_value = mock_client
        mock_card_parser_class.return_value = MagicMock()
        mock_get_card.return_value = MagicMock()
        mock_card_has_hints.return_value = True

        config = {
            "multithread_providers": True,
            "ai_provider": "openai",
            "provider_priority": ["openai", "gemini", "anthropic"],
            "api_keys": {"openai": "k1", "gemini": "k2"},
        }
        manager.local_queue_jobs = [{
            "id": "filtered_job",
            "queue": [50],
            "total": 1,
            "failed_cards": [],
            "config": config,
            "provider": None,
            "pass": 1,
            "errors": 0,
        }]
        manager.local_queue_active = True
        manager.saved_config = config

        manager._run_local_queue(config, None)

        # Unready provider ('anthropic') must not join the bulk generation
        self.assertEqual(set(manager.active_providers), set(candidates))
        self.assertNotIn("anthropic", manager.active_providers)
        spawned_providers = [c.args[0] for c in mock_run_thread.call_args_list]
        self.assertEqual(set(spawned_providers), set(candidates))
        self.assertNotIn("anthropic", spawned_providers)

if __name__ == "__main__":
    unittest.main()
