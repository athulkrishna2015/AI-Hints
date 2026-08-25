"""Headless tests for the lazy/chunked Logs tab pipeline.

The old load_log() read the whole rotating log with readlines(), filtered it
several times, regex-linkified every line and rebuilt a giant QTextBrowser
HTML document ON the GUI thread every second — freezing Anki and ballooning
memory on large logs. process_log_file() now streams the file off-thread with
a render cap. These tests verify filter semantics, the truncation notice,
bounded rendering, and processing speed on a large synthetic log.
"""
import os
import sys
import time
import types
import unittest
from unittest.mock import MagicMock

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)


def _install_aqt_mocks():
    if "aqt" in sys.modules and getattr(sys.modules["aqt"], "__aih_mocked__", False):
        return
    from PyQt6 import QtCore, QtGui, QtWidgets

    aqt = types.ModuleType("aqt")
    qt_mod = types.ModuleType("aqt.qt")
    for mod in (QtCore, QtGui, QtWidgets):
        for name in dir(mod):
            if not name.startswith("_"):
                setattr(qt_mod, name, getattr(mod, name))
    aqt.mw = None  # skip hook wiring in addon/__init__
    aqt.utils = MagicMock()
    aqt.gui_hooks = MagicMock()
    sys.modules["aqt"] = aqt
    sys.modules["aqt.qt"] = qt_mod
    sys.modules["aqt.utils"] = aqt.utils
    sys.modules["aqt.gui_hooks"] = aqt.gui_hooks
    anki = types.ModuleType("anki")
    errors = types.ModuleType("anki.errors")

    class NotFoundError(Exception):
        pass

    errors.NotFoundError = NotFoundError
    sys.modules["anki"] = anki
    sys.modules["anki.errors"] = errors
    aqt.__aih_mocked__ = True


_install_aqt_mocks()

from addon.config_ui.tab_logs import LOG_RENDER_CAP, process_log_file  # noqa: E402


def _line(level="INFO", msg="hello"):
    return f"2026-08-25 12:00:00,000 - {level} - {msg}\n"


class ProcessLogFileTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "ai_hints.log")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, lines):
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def test_level_source_search_filters(self):
        self._write([
            _line("DEBUG", "verbose detail"),
            _line("INFO", "[Proxy] antigravity call done"),          # proxy source
            _line("INFO", "Batch queue advanced to card 1234567890123"),
            _line("WARNING", "pregen queue skipped a card"),
            _line("ERROR", "provider exploded"),
            _line("INFO", "[MODEL_TEST] test row ok"),
        ])
        res = process_log_file(self.path, "ALL", "ALL", "")
        self.assertEqual(res["total"], 6)
        self.assertEqual(res["matched_total"], 6)
        self.assertFalse(res["truncated"])

        err_only = process_log_file(self.path, "ERROR", "ALL", "")
        self.assertEqual(err_only["matched_total"], 1)
        self.assertIn("exploded", err_only["content_plain"])

        batch_only = process_log_file(self.path, "ALL", "Batch Processing", "")
        self.assertEqual(batch_only["matched_total"], 1)
        self.assertIn("Batch queue", batch_only["content_plain"])

        proxy_only = process_log_file(self.path, "ALL", "Antigravity Proxy", "")
        self.assertEqual(proxy_only["matched_total"], 1)

        pregen = process_log_file(self.path, "ALL", "Pre-generation", "")
        self.assertEqual(pregen["matched_total"], 1)

        model_test = process_log_file(self.path, "ALL", "Model Testing", "")
        self.assertEqual(model_test["matched_total"], 1)

        std = process_log_file(self.path, "ALL", "Standard Addon", "")
        self.assertEqual(std["matched_total"], 4)  # excludes Proxy + MODEL_TEST

        search = process_log_file(self.path, "ALL", "ALL", "EXPLODED")  # case-insensitive
        self.assertEqual(search["matched_total"], 1)

    def test_render_cap_keeps_newest_and_reports_truncation(self):
        self._write([_line("INFO", f"line-{i:06d}") for i in range(50)])
        cap = 10
        res = process_log_file(self.path, "ALL", "ALL", "", max_lines=cap)
        self.assertTrue(res["truncated"])
        self.assertEqual(res["matched_total"], 50)
        plain = res["content_plain"]
        # Newest kept, oldest hidden.
        self.assertIn("line-000049", plain)
        self.assertNotIn("line-000000", plain)
        # Notice goes into HTML only.
        self.assertIn("older matching lines hidden", res["content_html"])

    def test_no_matches_message(self):
        self._write([_line("INFO", "only this")])
        res = process_log_file(self.path, "ERROR", "ALL", "")
        self.assertEqual(res["matched_total"], 0)
        self.assertIn("No entries matching", res["content_html"])
        self.assertFalse(res["truncated"])

    def test_large_log_fast_and_capped(self):
        n = 150_000
        self._write([_line("INFO", f"row {i} card 1234567890{i % 10}") for i in range(n)])
        t0 = time.perf_counter()
        res = process_log_file(self.path, "ALL", "ALL", "", max_lines=LOG_RENDER_CAP)
        dt = time.perf_counter() - t0
        self.assertEqual(res["total"], n)
        self.assertEqual(res["matched_total"], n)
        self.assertTrue(res["truncated"])
        self.assertLessEqual(
            len(res["content_plain"].splitlines()), LOG_RENDER_CAP + 1,
            "render output must stay capped regardless of file size",
        )
        html_len = len(res["content_html"])
        self.assertLess(html_len, 2_000_000, "HTML payload must stay bounded")
        print(f"\nprocess {n:,} lines in {dt:.2f}s, html={html_len / 1024:.0f} KB")
        self.assertLess(dt, 30, f"log processing too slow: {dt:.1f}s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
