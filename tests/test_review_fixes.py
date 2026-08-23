# -*- coding: utf-8 -*-
"""Regression tests for the 2026-08 full-code-review fixes.

Each test maps to a finding ID from the review report.
"""
import html
import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)


def _install_aqt_mocks():
    """Minimal aqt mocks so addon modules import cleanly outside Anki."""
    if "aqt" in sys.modules and getattr(sys.modules["aqt"], "__aih_mocked__", False):
        return
    aqt = ModuleType("aqt")
    aqt.qt = MagicMock()
    aqt.utils = MagicMock()
    aqt.webview = MagicMock()
    aqt.theme = MagicMock()
    aqt.gui_hooks = MagicMock()
    aqt.operations = MagicMock()
    aqt.operations.deck = MagicMock()
    mw = MagicMock()
    mw.pm.profileFolder.return_value = ""  # keep data files in addon dir for tests
    mw.taskman.run_on_main.side_effect = lambda fn, *a, **k: fn(*a, **k)
    aqt.mw = mw
    sys.modules["aqt"] = aqt
    sys.modules["aqt.qt"] = aqt.qt
    sys.modules["aqt.utils"] = aqt.utils
    sys.modules["aqt.gui_hooks"] = aqt.gui_hooks
    sys.modules["aqt.operations"] = aqt.operations
    sys.modules["aqt.operations.deck"] = aqt.operations.deck
    sys.modules["anki"] = ModuleType("anki")
    sys.modules["anki.errors"] = ModuleType("anki.errors")
    class NotFoundError(Exception):
        pass
    sys.modules["anki.errors"].NotFoundError = NotFoundError
    aqt.__aih_mocked__ = True


_install_aqt_mocks()

from addon.card_parser import CardParser, _iter_hint_blocks          # noqa: E402
from addon.ai_client import AIClient, RATE_LIMIT_STREAK              # noqa: E402
from addon.config_io import resolve_data_file, atomic_write_json     # noqa: E402


class TestC1ErrorsSetterNoReset(unittest.TestCase):
    """C1: setting local_queue_errors must not reset runtime state or swap locks."""

    def test_setter_is_pure(self):
        from addon.batch_manager import BatchManager
        bm = BatchManager()
        bm.local_queue_jobs = [{
            "id": "j1", "queue": [1], "total": 1, "failed_cards": [],
            "config": {}, "provider": None, "pass": 1, "errors": 0,
        }]
        lock_before = bm._db_lock
        stats_before = object()
        bm.last_run_stats = stats_before
        threads_before = {"x": 1}
        bm.active_threads_status = threads_before

        bm.local_queue_errors = bm.local_queue_errors + 1  # what failure paths do

        self.assertEqual(bm.local_queue_errors, 1)
        self.assertIs(bm._db_lock, lock_before, "setter must not replace _db_lock")
        self.assertIs(bm.last_run_stats, stats_before)
        self.assertIs(bm.active_threads_status, threads_before)
        self.assertEqual(len(bm.local_queue_jobs), 1)
        self.assertEqual(bm.local_queue_jobs[0]["queue"], [1])


class TestH4RateLimitStreak(unittest.TestCase):
    """H4: a 429 must advance the streak exactly once per failure."""

    def setUp(self):
        RATE_LIMIT_STREAK.clear()
        self.client = AIClient({"model_cooldown_minutes": 10})

    def tearDown(self):
        RATE_LIMIT_STREAK.clear()

    def test_delay_then_mark_increments_once(self):
        err = urllib_error_429()
        delay1 = self.client._extract_retry_delay("gemini", "m", "k", err, "")
        self.assertEqual(RATE_LIMIT_STREAK.get(("gemini", "m", "k"), 0), 0,
                         "_extract_retry_delay must not store the streak")
        self.assertAlmostEqual(delay1, 600.0)
        self.client._mark_combo_failed("gemini", "m", "k", delay_seconds=delay1)
        self.assertEqual(RATE_LIMIT_STREAK[("gemini", "m", "k")], 1,
                         "streak must be exactly 1 after one 429")

        # second hit escalates to 2x cooldown, streak ends at 2
        delay2 = self.client._extract_retry_delay("gemini", "m", "k", err, "")
        self.assertAlmostEqual(delay2, 1200.0)
        self.client._mark_combo_failed("gemini", "m", "k", delay_seconds=delay2)
        self.assertEqual(RATE_LIMIT_STREAK[("gemini", "m", "k")], 2)


def urllib_error_429():
    import io
    import urllib.error
    return urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, io.BytesIO(b""))


class TestH7CooldownTypes(unittest.TestCase):
    """H7: string/None cooldown config values must not crash."""

    def test_string_value(self):
        c = AIClient({"model_cooldown_minutes": "15"})
        self.assertEqual(c._cooldown_seconds(), 900.0)

    def test_none_value(self):
        c = AIClient({"model_cooldown_minutes": None})
        self.assertEqual(c._cooldown_seconds(), 600.0)

    def test_garbage_value(self):
        c = AIClient({"model_cooldown_minutes": "abc"})
        self.assertEqual(c._cooldown_seconds(), 600.0)


class TestM17DepthAwareScanner(unittest.TestCase):
    """M17: blocks containing raw nested HTML must survive read-modify-write."""

    def setUp(self):
        self.parser = CardParser()

    RAW_BLOCK = (
        '<div class="ai-hints-json" style="display:none">'
        'STALE <div class="legacy">old</div> '
        '{"c1": {"hints": ["h"], "options": ["o"]}}'
        "</div>"
    )

    def test_raw_html_payload_fully_matched(self):
        matches = list(_iter_hint_blocks(self.RAW_BLOCK))
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].group(0), self.RAW_BLOCK)

    def test_update_replaces_whole_legacy_block_not_splice(self):
        out = self.parser._update_json_block_in_field(
            "Q " + self.RAW_BLOCK, {"hints": ["new"], "options": []}, "c1", None
        )
        # Exactly ONE block remains and it parses cleanly
        blocks = list(_iter_hint_blocks(out))
        self.assertEqual(len(blocks), 1)
        parsed = json.loads(html.unescape(blocks[0].group(1)))
        self.assertEqual(parsed["c1"]["hints"], ["new"])
        self.assertNotIn("STALE", out)
        self.assertNotIn('class="legacy"', out)

    def test_unterminated_block_skipped(self):
        text = '<div class="ai-hints-json">never closed <span>hi</span>'
        self.assertEqual(list(_iter_hint_blocks(text)), [])

    def test_sibling_blocks_not_merged(self):
        two = ('<div class="ai-hints-json">{"a":1}</div>'
               '<div class="ai-hints-json">{"b":2}</div>')
        self.assertEqual(len(list(_iter_hint_blocks(two))), 2)

    def test_clear_removes_block_and_noise(self):
        field = 'before<br><br>\n' + \
                '<div class="ai-hints-json">{&quot;c1&quot;:{&quot;hints&quot;:[&quot;x&quot;],&quot;options&quot;:[]}}</div>' + \
                '\n<after>'
        field = field.replace("<after>", "<p>after</p>")
        note = FakeNoteSingle({"F": field})
        self.assertTrue(self.parser.clear_hints_from_note(note))
        self.assertNotIn("ai-hints-json", note["F"])
        self.assertIn("before", note["F"])
        self.assertIn("after", note["F"])

    def test_remove_all_strips_everything(self):
        field = ('x<br><div class="ai-hints-json">{}</div>y'
                 '<div class="ai-hints-container">html</div>z')
        note = FakeNoteSingle({"F": field})
        self.assertTrue(self.parser._remove_all_hints_from_fields(note))
        self.assertNotIn("ai-hints", note["F"])
        self.assertIn("x", note["F"]) and self.assertIn("y", note["F"]) and self.assertIn("z", note["F"])


class FakeNoteSingle(dict):
    """Note-like mapping whose .keys() lists field names."""
    def keys(self):
        return list(dict.keys(self))


class TestH5AtomicPregenSave(unittest.TestCase):
    """H5: PregenCache.save is atomic (temp+replace), never truncating."""

    def test_save_atomic_and_roundtrip(self):
        from addon.reviewer_hooks import PregenCache
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "pregen.json")
        cache = PregenCache(path)
        cache[123] = {"hints": ["h"], "options": []}
        cache.save()
        self.assertFalse(os.path.exists(path + ".tmp"))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["123"]["hints"], ["h"])
        # reload
        cache2 = PregenCache(path)
        self.assertEqual(cache2[123]["hints"], ["h"])

    def test_batch_save_state_atomic(self):
        from addon.batch_manager import BatchManager
        tmpdir = tempfile.mkdtemp()
        bm = BatchManager()
        path = os.path.join(tmpdir, "state.json")
        with patch.object(bm, "_state_file_path", return_value=path):
            bm.jobs = {}
            bm.local_queue_jobs = []
            bm.save_state()
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            self.assertIn("native_jobs", payload)
            self.assertIn("local_cache", payload)


class TestM11ProfileDataMigration(unittest.TestCase):
    """M11: resolve_data_file migrates legacy addon-dir copies."""

    def test_migration_moves_legacy_file(self):
        import shutil
        from addon import config_io
        tmp_profile = tempfile.mkdtemp()
        fname = f"mig_test_{int(time.time()*1000)}_{os.getpid()}.json"
        # Legacy copies live in the ADDON dir (where old versions wrote them)
        legacy_path = os.path.join(config_io._ADDON_DIR, fname)
        with open(legacy_path, "w") as f:
            json.dump({"v": 1}, f)

        # A real (non-"Mock"-named) class so config_io's Mock check passes
        class FakeAnkiMW:
            def __init__(self):
                self.pm = MagicMock()
                self.pm.profileFolder.return_value = tmp_profile

        try:
            with patch.dict(sys.modules, {"aqt": MagicMock(mw=FakeAnkiMW())}):
                new_path = config_io.resolve_data_file(fname)
            self.assertEqual(os.path.basename(os.path.dirname(new_path)), "ai_hints_bin")
            self.assertEqual(os.path.dirname(os.path.dirname(new_path)), tmp_profile)
            self.assertTrue(os.path.exists(new_path))
            self.assertFalse(os.path.exists(legacy_path), "legacy copy must be moved")
            with open(new_path) as f:
                self.assertEqual(json.load(f)["v"], 1)
        finally:
            shutil.rmtree(tmp_profile, ignore_errors=True)
            if os.path.exists(legacy_path):
                os.remove(legacy_path)


class TestLowUserAgent(unittest.TestCase):
    def test_user_agent_has_version(self):
        from addon import ai_client
        version_file = os.path.join(ai_client.ADDON_PATH, "VERSION")
        expected = "Anki-AI-Hints/0"
        if os.path.exists(version_file):
            with open(version_file) as f:
                expected = f"Anki-AI-Hints/{f.read().strip()}"
        self.assertEqual(ai_client.USER_AGENT, expected)


class TestLowJsEscaping(unittest.TestCase):
    def test_trigger_js_click_escapes_needles(self):
        from addon import reviewer_hooks
        captured = {}
        web = MagicMock()
        web.eval.side_effect = lambda s: captured.setdefault("js", s)
        mw_mock = MagicMock()
        mw_mock.reviewer.web = web
        # _safe_web_eval consults sip.isdeleted; force "not deleted"
        sys.modules["aqt"].qt.sip.isdeleted.return_value = False
        with patch.object(reviewer_hooks, "mw", mw_mock):
            reviewer_hooks.trigger_js_click('Op"); alert(1); //', "🎯")
        js = captured["js"]
        self.assertIn('\\");', js, "needle must be json.dumps-escaped into the script")
        self.assertIn('"Op\\"); alert(1); //"', js)
        # emoji is escaped as surrogate pair by json.dumps (ensure_ascii) — valid JS
        self.assertIn("\\ud83c\\udfaf", js)


class TestBatchSummaryEscaping(unittest.TestCase):
    def test_description_html_escaped(self):
        from addon.batch_manager import BatchManager
        bm = BatchManager()
        bm.local_queue_active = True
        bm.local_queue_paused = False
        bm.local_queue_jobs = [{
            "id": "j", "queue": [1, 2], "total": 2, "failed_cards": [],
            "config": {}, "provider": None, "pass": 1, "errors": 0,
            "description": 'Deck <script>alert("x")</script>',
        }]
        summary = bm.get_status_summary()
        self.assertNotIn("<script>", summary)
        self.assertIn("&lt;script&gt;", summary)


class TestC3VerificationMainThread(unittest.TestCase):
    """C3: verification runs through taskman.run_on_main."""

    def test_missing_hint_cids_via_main(self):
        import addon.batch_manager as bmod
        calls = []
        mw_mock = MagicMock()
        def fake_run_on_main(fn):
            calls.append(fn)
            fn()
        mw_mock.taskman.run_on_main.side_effect = fake_run_on_main

        with patch.object(bmod, "mw", mw_mock), \
             patch("addon.reviewer_hooks.card_has_hints", return_value=False), \
             patch("addon.reviewer_hooks._get_card_from_collection",
                   side_effect=lambda cid: MagicMock(id=cid)):
            missing = bmod.BatchManager._missing_hint_cids_on_main([1, 2, 3])

        self.assertEqual(len(calls), 1, "collection access must be marshalled to main")
        self.assertEqual(missing, [1, 2, 3])


class TestC2TerminatorGating(unittest.TestCase):
    """C2: Note.fields proxy installs ONLY when Terminator webview detected."""

    def _fresh_modules(self):
        anki_mod = ModuleType("anki")
        notes_mod = ModuleType("anki.notes")
        class Note:
            def __init__(self): pass
        notes_mod.Note = Note
        anki_mod.notes = notes_mod
        return anki_mod, notes_mod

    def test_no_patch_without_terminator(self):
        from addon import anki_terminator_patch as atp
        anki_mod, notes_mod = self._fresh_modules()
        mods = {"anki": anki_mod, "anki.notes": notes_mod}
        # Ensure no dock_web_view modules exist
        saved = {k: v for k, v in sys.modules.items() if "dock_web_view" in k}
        for k in saved:
            del sys.modules[k]
        try:
            with patch.dict(sys.modules, mods):
                atp.setup_anki_terminator_patch()
                self.assertFalse(hasattr(notes_mod.Note, "_ai_hints_fields_patched"),
                                 "Note patch must NOT install without Terminator")
        finally:
            sys.modules.update(saved)

    def test_patch_with_terminator(self):
        from addon import anki_terminator_patch as atp
        anki_mod, notes_mod = self._fresh_modules()

        dwv = ModuleType("1234567.dock_web_view")
        class ResizableWebView:
            def get_field_text(self, card=None): pass
            def load_and_interact(self, card=None, *a, **k): pass
        dwv.ResizableWebView = ResizableWebView

        with patch.dict(sys.modules, {
            "anki": anki_mod, "anki.notes": notes_mod,
            "1234567.dock_web_view": dwv,
        }):
            ok = atp.patch_anki_terminator()
            self.assertTrue(ok)
            atp.patch_anki_note_fields()
            self.assertTrue(hasattr(notes_mod.Note, "_ai_hints_fields_patched"))
            self.assertTrue(hasattr(ResizableWebView, "_ai_hints_patched"))


class TestM13GeminiHeaderAuth(unittest.TestCase):
    def test_fetch_models_gemini_uses_header(self):
        client = AIClient({"api_keys": {"gemini": "SECRET"}})
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return json.dumps({"models": [
                    {"name": "models/gem-x", "supportedGenerationMethods": ["generateContent"]}
                ]}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            return FakeResp()

        import urllib.request
        with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            models = client.fetch_models("gemini")

        self.assertEqual(models, ["gem-x"])
        self.assertNotIn("SECRET", captured["url"])
        flat = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(flat.get("x-goog-api-key"), "SECRET")


class TestKeyParsingBrackets(unittest.TestCase):
    def test_mismatched_bracket_not_treated_as_name(self):
        c = AIClient({})
        parsed = c._parse_all_keys("openai", "sk-key(name]")
        self.assertEqual(parsed[0]["name"], "", "mismatched bracket must not become a name")
        self.assertEqual(parsed[0]["key"], "sk-key(name]")

    def test_matching_bracket_name(self):
        c = AIClient({})
        parsed = c._parse_all_keys("openai", "sk-key (main)")
        self.assertEqual(parsed[0]["name"], "main")
        self.assertEqual(parsed[0]["key"], "sk-key")

    def test_named_colon_short_key(self):
        c = AIClient({})
        parsed = c._parse_all_keys("openai", "primary:key1")
        self.assertEqual(parsed[0]["name"], "primary")
        self.assertEqual(parsed[0]["key"], "key1")


class TestM10ClearLogFile(unittest.TestCase):
    def test_clear_removes_and_restores_handler(self):
        import logging
        from logging.handlers import RotatingFileHandler
        from addon import logger as logmod

        tmpdir = tempfile.mkdtemp()
        base = os.path.join(tmpdir, "ai_hints.log")

        h = RotatingFileHandler(base, maxBytes=1024, backupCount=2)
        logger = logmod.logger
        original_handlers = list(logger.handlers)
        logger.handlers = []
        logger.addHandler(h)

        with open(base, "w") as f:
            f.write("old content")
        with open(base + ".1", "w") as f:
            f.write("rotated")

        with patch.object(logmod, "_log_path", return_value=base):
            logmod.clear_log_file()

        self.assertFalse(os.path.exists(base + ".1"), "rotation must be removed")
        # handler re-installed and usable
        file_handlers = [x for x in logger.handlers if isinstance(x, RotatingFileHandler)]
        self.assertEqual(len(file_handlers), 1)
        logger.removeHandler(file_handlers[0])
        file_handlers[0].close()
        logger.handlers = original_handlers


class TestM14ProxyAccountsNonString(unittest.TestCase):
    def test_sync_handles_nonstring_config(self):
        from addon.proxy_manager import ProxyManager
        pm = ProxyManager()
        fake_mw = MagicMock()
        fake_mw.addonManager.getConfig.return_value = {"antigravity_accounts": None}
        with tempfile.TemporaryDirectory() as td:
            with patch.object(ProxyManager, "bin_dir", property(lambda self: td)):
                with patch.dict(sys.modules, {"aqt": MagicMock(mw=fake_mw)}):
                    pm._sync_accounts_file({"antigravity_accounts": None})  # must not raise


class TestM18RestorePaused(unittest.TestCase):
    def test_initialize_marks_interrupted_queue_paused_without_starting(self):
        from addon import batch_manager as bmod
        bm = bmod.batch_manager
        old_jobs, old_active, old_paused = bm.local_queue_jobs, bm.local_queue_active, bm.local_queue_paused
        try:
            bm.local_queue_jobs = [{"id": "x", "queue": [9], "total": 1, "failed_cards": [],
                                    "config": {}, "provider": None, "pass": 1, "errors": 0}]
            bm.local_queue_active = True
            bm.local_queue_paused = False
            with patch.object(bmod.batch_manager, "start_local_sequential_queue") as sq, \
                 patch.object(bmod.batch_manager, "start_timer_if_needed"):
                bmod.initialize_batch_manager()
            sq.assert_not_called()
            self.assertTrue(bm.local_queue_paused)
            self.assertFalse(bm.local_queue_active)
        finally:
            bm.local_queue_jobs, bm.local_queue_active, bm.local_queue_paused = old_jobs, old_active, old_paused


if __name__ == "__main__":
    unittest.main(verbosity=2)
