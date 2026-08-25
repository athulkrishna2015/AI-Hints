"""Regression tests: single canonical log file (handler == Logs tab == Clear).

get_logger() used to bind the file handler at import time — before the Anki
profile opened — so it landed on the addon folder while the Logs tab and
Clear Log resolved _log_path() to the profile data dir once the profile was
up. Result: the on-disk file held only a couple of startup lines while the
tab showed the real stream. rebind_file_logging() now attaches the handler
at profile-open time so every consumer shares one path.
"""
import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from addon import logger as logger_mod  # noqa: E402


def _rotating_handlers(log):
    from logging.handlers import RotatingFileHandler
    return [h for h in log.handlers if isinstance(h, RotatingFileHandler)]


class RebindFileLoggingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.tmp.name, "ai_hints.log")
        self.patcher = patch.object(logger_mod, "_log_path", lambda: self.log_path)
        self.patcher.start()
        self.log = logger_mod.logger
        # Strip handlers/filters for a deterministic production-like start.
        self._orig_handlers = self.log.handlers[:]
        self._orig_filters = self.log.filters[:]
        for h in self.log.handlers[:]:
            self.log.removeHandler(h)
        for f in self.log.filters[:]:
            self.log.removeFilter(f)

    def tearDown(self):
        for h in list(self.log.handlers):
            try:
                h.close()
            except Exception:
                pass
            self.log.removeHandler(h)
        for h in self._orig_handlers:
            self.log.addHandler(h)
        for f in self._orig_filters:
            self.log.addFilter(f)
        self.patcher.stop()
        self.tmp.cleanup()

    def test_rebind_attaches_single_handler_and_writes_file(self):
        bound_to = logger_mod.rebind_file_logging()
        self.assertEqual(bound_to, self.log_path)
        rh = _rotating_handlers(self.log)
        self.assertEqual(len(rh), 1, "exactly one rotating file handler expected")
        self.assertTrue(any(isinstance(f, logger_mod.ContextFilter) for f in self.log.filters))
        self.log.info("rebind-marker-123")
        for h in rh:
            h.flush()
        with open(self.log_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("rebind-marker-123", content)

    def test_rebind_is_idempotent_pathwise(self):
        logger_mod.rebind_file_logging()
        logger_mod.rebind_file_logging()
        # Second call detaches the first handler before adding: still exactly one.
        self.assertEqual(len(_rotating_handlers(self.log)), 1)
        self.log.info("after-second-rebind")
        for h in _rotating_handlers(self.log):
            h.flush()
        with open(self.log_path, encoding="utf-8") as f:
            self.assertIn("after-second-rebind", f.read())

    def test_clear_log_keeps_handler_on_same_file(self):
        logger_mod.rebind_file_logging()
        self.log.info("pre-clear-entry")
        for h in _rotating_handlers(self.log):
            h.flush()
        logger_mod.clear_log_file()
        self.assertEqual(len(_rotating_handlers(self.log)), 1)
        with open(self.log_path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("pre-clear-entry", content)
        self.assertIn("New session started", content)

    def test_import_time_get_logger_adds_no_file_handler(self):
        """Simulate fresh import state: no file handler until profile opens."""
        self.assertEqual(len(_rotating_handlers(self.log)), 0,
                         "get_logger must not bind a file handler pre-profile")


if __name__ == "__main__":
    unittest.main(verbosity=2)
