"""Local integration test: AI-Hints picker suspends Review Hotmouse.

Loads the REAL HotmouseManager from the sibling addon repo
(Review-Hotmouse-plus-overview) with mocked aqt, registers it in sys.modules
the way Anki would, then drives addon.hotmouse_patch:

  1. suspend_hotmouse() disables the manager (wheel events pass through).
  2. handle_scroll() consumes nothing while suspended.
  3. resume_hotmouse() restores the previous enabled state.
  4. Suspension is refcounted by reason: double suspend needs double resume.
  5. Without Hotmouse installed the bridge is a silent no-op.
"""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.dont_write_bytecode = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOTMOUSE_ADDON = os.path.join(os.path.dirname(ROOT_DIR), "Review-Hotmouse-plus-overview", "addon")
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
    # mw=None keeps addon/__init__ from wiring hooks/config UI (not needed
    # here) while hotmouse_patch itself stays fully functional.
    aqt.mw = None
    aqt.utils = MagicMock()
    # tooltip() is called directly by actions.py; keep it harmless.
    aqt.utils.tooltip = MagicMock()
    aqt.gui_hooks = MagicMock()
    aqt.operations = MagicMock()
    aqt.operations.deck = MagicMock()
    sys.modules["aqt"] = aqt
    sys.modules["aqt.qt"] = qt_mod
    sys.modules["aqt.utils"] = aqt.utils
    sys.modules["aqt.gui_hooks"] = aqt.gui_hooks
    sys.modules["aqt.operations"] = aqt.operations
    sys.modules["aqt.operations.deck"] = aqt.operations.deck
    anki = types.ModuleType("anki")
    errors = types.ModuleType("anki.errors")

    class NotFoundError(Exception):
        pass

    errors.NotFoundError = NotFoundError
    sys.modules["anki"] = anki
    sys.modules["anki.errors"] = errors
    aqt.__aih_mocked__ = True


def _load_real_hotmouse_manager():
    """Import the real actions.py + manager.py as package 'aih_hm_test'."""
    pkg_name = "aih_hm_test"
    pkg_dir = os.path.join(HOTMOUSE_ADDON, "hotmouse")
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [pkg_dir]
    sys.modules[pkg_name] = pkg
    for sub in ("actions", "manager"):
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.{sub}", os.path.join(pkg_dir, f"{sub}.py")
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.{sub}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules[f"{pkg_name}.manager"]


_install_aqt_mocks()

if not os.path.isdir(HOTMOUSE_ADDON):
    raise unittest.SkipTest("Review-Hotmouse-plus-overview not found next to AI-Hints")

from addon import hotmouse_patch  # noqa: E402

# Real hotmouse code reads mw.state / mw.web at call time; give it a live
# mock BEFORE loading it, now that addon/__init__ has been skipped
# (imported with mw=None).
sys.modules["aqt"].mw = MagicMock()
sys.modules["aqt"].mw.state = "review"

hm_manager = _load_real_hotmouse_manager()

# Register the manager under a hotmouse-ish module name like Anki would.
fake_event = types.ModuleType("Review-Hotmouse-plus-overview.event")


class HotmouseBridgeTests(unittest.TestCase):
    def setUp(self):
        hm_manager.set_config({"default_enabled": True, "shortcuts": {"wheel": {}}})
        self.manager = hm_manager.HotmouseManager()
        fake_event.manager = self.manager
        sys.modules[fake_event.__name__] = fake_event

    def tearDown(self):
        sys.modules.pop(fake_event.__name__, None)

    def test_suspend_disables_and_resume_restores(self):
        self.assertTrue(self.manager.enabled)
        hotmouse_patch.suspend_hotmouse()
        self.assertFalse(self.manager.enabled)
        hotmouse_patch.resume_hotmouse()
        self.assertTrue(self.manager.enabled)

    def test_suspended_scroll_consumes_nothing(self):
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QWheelEvent
        from PyQt6.QtCore import QPointF, Qt

        hotmouse_patch.suspend_hotmouse()
        try:
            event = QWheelEvent(QPointF(10, 10), QPointF(10, 10),
                                QPoint(0, 0), QPoint(0, 120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            consumed = self.manager.on_mouse_scroll(event)
            self.assertFalse(consumed, "suspended hotmouse must not consume wheel events")
        finally:
            hotmouse_patch.resume_hotmouse()

    def test_cooperates_with_other_suspend_reasons(self):
        # Same-reason suspend is a no-op by design; a second addon suspending
        # under its own reason must keep hotmouse off until it also resumes.
        hotmouse_patch.suspend_hotmouse()
        self.manager.suspend("other-addon")
        hotmouse_patch.resume_hotmouse()
        self.assertFalse(self.manager.enabled, "another reason still holds it suspended")
        self.manager.resume("other-addon")
        self.assertTrue(self.manager.enabled)

    def test_noop_without_hotmouse_installed(self):
        sys.modules.pop(fake_event.__name__, None)
        hotmouse_patch.suspend_hotmouse()  # must not raise
        hotmouse_patch.resume_hotmouse()


if __name__ == "__main__":
    unittest.main(verbosity=2)
