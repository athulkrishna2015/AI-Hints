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

from addon.config_ui.tab_logs import LOG_RENDER_CAP, LogTabMixin, process_log_file  # noqa: E402


# ---- Minimal fake widget surface so LogTabMixin methods run headless --------

class _FakeBar:
    def value(self):
        return 0

    def maximum(self):
        return 100

    def setValue(self, v):
        pass


class _FakeCursor:
    def hasSelection(self):
        return False


class _FakeView:
    def __init__(self):
        self.text = ""
        self.html = ""
        self.extra = None

    def setPlainText(self, t):
        self.text, self.html = t, t

    def toPlainText(self):
        # First apply differs from "" so rendering proceeds; afterwards the
        # equality shortcut mirrors real QTextBrowser behavior closely enough.
        import re as _re
        if self.html:
            return _re.sub(r"<[^>]+>", " ", self.html)
        return self.text

    def textCursor(self):
        return _FakeCursor()

    def setHtml(self, h):
        self.html = h

    def verticalScrollBar(self):
        return _FakeBar()

    def setExtraSelections(self, s):
        self.extra = s


class _Stub:
    def __init__(self, value):
        self._v = value

    def currentText(self):
        return self._v

    def text(self):
        return self._v


class _FutureLike:
    """Mimics concurrent.futures.Future as Anki's taskman delivers it."""

    def __init__(self, value):
        self._value = value

    def result(self, timeout=None):
        return self._value


def _make_tab(path):
    tab = MagicMock()
    tab.log_level_cb = _Stub("ALL")
    tab.log_source_cb = _Stub("ALL")
    tab.log_search_edit = _Stub("")
    tab.addon_dir = os.path.dirname(path)
    tab.log_view = _FakeView()
    tab.match_count_label = MagicMock()
    tab._apply_search_highlighting = lambda pattern: None
    # Bind the real unbound methods.
    tab.load_log = lambda: LogTabMixin.load_log(tab)
    tab._apply_log_result = lambda r, s: LogTabMixin._apply_log_result(tab, r, s)
    return tab


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
            _line("INFO", "Batch queue advanced to card 1234567890123"),
            _line("WARNING", "pregen queue skipped a card"),
            _line("ERROR", "provider exploded"),
            _line("INFO", "[MODEL_TEST] test row ok"),
            _line("INFO", "AI-Hints Linger: late result arrived from gemini/gemini-3.6-flash (candidate #2)."),
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

        pregen = process_log_file(self.path, "ALL", "Pre-generation", "")
        self.assertEqual(pregen["matched_total"], 1)

        model_test = process_log_file(self.path, "ALL", "Model Testing", "")
        self.assertEqual(model_test["matched_total"], 1)

        linger = process_log_file(self.path, "ALL", "Lingering", "")
        self.assertEqual(linger["matched_total"], 1)
        self.assertIn("AI-Hints Linger", linger["content_plain"])

        std = process_log_file(self.path, "ALL", "Standard Addon", "")
        self.assertEqual(std["matched_total"], 5)  # excludes MODEL_TEST

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


class LoadLogDeliveryTests(unittest.TestCase):
    """Anki's taskman.run_in_background(on_done=...) delivers a Future, not the
    value; the callback must unwrap both shapes (regression: 'Future' object is
    not subscriptable shown in the log view)."""

    def setUp(self):
        import tempfile
        from unittest.mock import patch
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "ai_hints.log")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(_line("INFO", "marker-line-xyz"))
        from addon import logger as logger_mod
        patcher = patch.object(logger_mod, "_log_path", lambda: self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_fallback_renders(self):
        tab = _make_tab(self.path)
        tab.load_log()
        self.assertIn("marker-line-xyz", tab.log_view.html)

    def test_future_delivery_renders(self):
        import addon.config_ui.tab_logs as tl

        tab = _make_tab(self.path)
        captured = {}

        def fake_run_in_background(func, on_done=None, **kw):
            captured["func"] = func
            captured["on_done"] = on_done
            return MagicMock()

        mw_mock = MagicMock()
        mw_mock.taskman.run_in_background.side_effect = fake_run_in_background
        aqt_mod = sys.modules["aqt"]
        aqt_mod.mw = mw_mock
        try:
            tab.load_log()
            self.assertIn("func", captured)
            fut = _FutureLike(captured["func"]())
            captured["on_done"](fut)  # must unwrap, not crash on subscript
        finally:
            aqt_mod.mw = None
        self.assertIn("marker-line-xyz", tab.log_view.html)
        self.assertNotIn("Error", tab.log_view.text or tab.log_view.html[:200])

    def test_stale_generation_discarded(self):
        import addon.config_ui.tab_logs as tl

        tab = _make_tab(self.path)
        pending = []

        def fake_run_in_background(func, on_done=None, **kw):
            pending.append((func, on_done))
            return MagicMock()

        mw_mock = MagicMock()
        mw_mock.taskman.run_in_background.side_effect = fake_run_in_background
        aqt_mod = sys.modules["aqt"]
        aqt_mod.mw = mw_mock
        try:
            tab.load_log()          # gen 1 scheduled
            func1, done1 = pending.pop(0)
            # File changed -> next tick schedules gen 2 and applies it first.
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(_line("INFO", "newer-entry"))
            tab.load_log()
            func2, done2 = pending.pop(0)
            done2(_FutureLike(func2()))
            latest_html = tab.log_view.html
            # Late-arriving gen-1 result must be ignored.
            done1(_FutureLike(func1()))
        finally:
            aqt_mod.mw = None
        self.assertEqual(tab.log_view.html, latest_html)
        self.assertIn("newer-entry", tab.log_view.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
