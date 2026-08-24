"""Regression tests: mobile script sync failure reporting.

sync_mobile_script() used to return bare False with no logging when the
collection was closed (e.g. Install clicked while the Remove-triggered
AnkiWeb sync had mw.col closed), surfacing only a generic
"Failed to sync script file to media folder." dialog. It must now return a
human-readable reason string for every failure path and None on success.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _load_sync_fn():
    """Import addon.mobile_sync with aqt mocked out."""
    mock_aqt = types.ModuleType("aqt")
    mock_mw = MagicMock()
    mock_aqt.mw = mock_mw
    saved_aqt = sys.modules.get("aqt")
    saved_mw_pkg = sys.modules.get("aqt.mw") if "aqt.mw" in sys.modules else None
    sys.modules["aqt"] = mock_aqt
    # addon package stub so relative imports resolve without executing __init__
    pkg = types.ModuleType("addon")
    pkg.__path__ = [os.path.join(PROJECT_ROOT, "addon")]
    pkg.__package__ = "addon"
    saved_addon = sys.modules.get("addon")
    sys.modules["addon"] = pkg
    try:
        import importlib
        mod = importlib.import_module("addon.mobile_sync")
        return mod, mod.sync_mobile_script, mock_mw
    finally:
        if saved_aqt is not None:
            sys.modules["aqt"] = saved_aqt
        else:
            sys.modules.pop("aqt", None)
        if saved_addon is not None:
            sys.modules["addon"] = saved_addon
        else:
            sys.modules.pop("addon", None)
        sys.modules.pop("addon.mobile_sync", None)
        sys.modules.pop("addon.config_ui", None)
        sys.modules.pop("addon.logger", None)


import types


class SyncMobileScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod, _sync, cls.mock_mw = _load_sync_fn()
        cls.sync = staticmethod(cls.mod.sync_mobile_script)

    def _col(self, tmp_media_dir):
        col = MagicMock()
        col.media.dir.return_value = tmp_media_dir

        def fake_write_data(name, data):
            with open(os.path.join(tmp_media_dir, name), "wb") as f:
                f.write(data.read())

        col.media.write_data.side_effect = fake_write_data
        return col

    def test_no_collection_returns_reason_not_false(self):
        self.mock_mw.col = None
        result = self.sync()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        self.assertIn("collection", result.lower())

    def test_success_returns_none(self, ):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.mock_mw.col = self._col(d)
            result = self.sync()
            self.assertIsNone(result)
            dest = os.path.join(d, "_ai_hints_template.js")
            self.assertTrue(os.path.exists(dest))
            src = os.path.join(PROJECT_ROOT, "addon", "web", "template.js")
            with open(src, "r", encoding="utf-8") as f:
                self.assertEqual(open(dest, "r", encoding="utf-8").read(), f.read())

    def test_exception_returns_error_string(self):
        col = MagicMock()
        col.media.dir.side_effect = RuntimeError("disk on fire")
        self.mock_mw.col = col
        result = self.sync()
        self.assertIsInstance(result, str)
        self.assertIn("disk on fire", result)

    def test_missing_source_returns_reason(self):
        self.mock_mw.col = MagicMock()
        with patch.object(self.mod.os.path, "exists", side_effect=[False]):
            result = self.sync()
        self.assertIsInstance(result, str)
        self.assertIn("not found", result.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
