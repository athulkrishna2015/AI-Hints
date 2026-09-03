"""Offscreen smoke + perf test: FallbackOrderDialog lazy widget materialization.

FallbackOrderDialog used to create a QComboBox + QSpinBox cell widget for every
row up front, making the dialog take seconds to open for providers with 400+
models (OpenRouter). Rows are now item-only; widgets materialize for visible
rows on demand. This test verifies:
  1. Construction with 400 models is fast and creates only a few widgets.
  2. Scrolling materializes widgets for newly visible rows.
  3. Values round-trip through the name-keyed dicts even for rows whose
     widgets were never created (thinking level / per-model timeout).
  4. Row swaps keep widget contents in sync with their model.
"""
import os
import sys
import time
import types
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Redirect every mutable state file (blacklist, caches) to a dedicated test
# folder so the live addon/profile data dir is never touched by the suite.
os.environ.setdefault(
    "AIHINTS_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".aihints_data"),
)

# ---- Stub `aqt` while keeping real PyQt6 for aqt.qt -----------------------
from PyQt6 import QtCore, QtGui, QtWidgets

aqt_mod = types.ModuleType("aqt")
aqt_mod.mw = MagicMock()
qt_mod = types.ModuleType("aqt.qt")
utils_mod = types.ModuleType("aqt.utils")
utils_mod.tooltip = lambda *args, **kwargs: None
for mod in (QtCore, QtGui, QtWidgets):
    for name in dir(mod):
        if not name.startswith("_"):
            setattr(qt_mod, name, getattr(mod, name))
sys.modules["aqt"] = aqt_mod
sys.modules["aqt.qt"] = qt_mod
sys.modules["aqt.utils"] = utils_mod

pkg = types.ModuleType("addon")
pkg.__path__ = [os.path.join(PROJECT_ROOT, "addon")]
pkg.__package__ = "addon"
saved = {k: sys.modules.get(k) for k in list(sys.modules) if k == "addon" or k.startswith("addon.")}
for k in list(sys.modules):
    if k.startswith("addon."):
        del sys.modules[k]
sys.modules["addon"] = pkg

from addon.config_ui.tab_providers import FallbackOrderDialog  # noqa: E402
from addon.config_ui.widgets import CustomProviderDialog  # noqa: E402

import addon.ai_client as _ai_client
import shutil as _shutil
import tempfile as _tempfile
_ai_client._bl_tmpdir = _tempfile.mkdtemp(prefix="aihints-bl-")
_ai_client.BLACKLIST_FILE = os.path.join(_ai_client._bl_tmpdir, "blacklist.json")
_ai_client._blacklist_path_resolved = True
_ai_client._BLACKLIST_LOADED = False

Qt = qt_mod.Qt  # noqa: E402


def make_dialog(n_models=400):
    # Real QWidget parent: QDialog needs one, and the dialog reads its
    # *_data attributes off the parent (the settings dialog in production).
    class FakeSettingsDialog(QtWidgets.QWidget):
        disabled_fallback_models_data = {}
        thinking_levels_data = {"openrouter": {"model-005": "high"}}
        model_timeouts_data = {"openrouter": {"model-007": 42}}

    parent = FakeSettingsDialog()
    models = [f"model-{i:03d}" for i in range(n_models)]
    t0 = time.perf_counter()
    dlg = FallbackOrderDialog(parent, "openrouter", "model-000", models, [])
    dt = time.perf_counter() - t0
    return dlg, dt


def count_widgets(dlg):
    return sum(
        1 for i in range(dlg.table.rowCount()) if dlg.table.cellWidget(i, 1) is not None
    )


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

# Built-in provider editing must restore shipped defaults, not the values from
# the currently edited custom override.
restore_parent = QtWidgets.QWidget()
restore_dlg = CustomProviderDialog(
    restore_parent,
    name="openai",
    data={
        "url": "https://example.invalid/chat",
        "api_key": "old-key",
        "model": "old-model",
        "headers": {"X-Old": "1"},
        "body_params": {"old": True},
    },
)
restore_dlg.on_restore_default()
restored = restore_dlg.get_data()
assert restored["url"] == "https://api.openai.com/v1/chat/completions"
assert restored["model"] == "gpt-4o"
assert restored["api_key"] == ""
assert restored["headers"] == {} and restored["body_params"] == {}

dlg, dt = make_dialog()
print(f"construct(400 rows): {dt * 1000:.0f} ms, initial widgets: {count_widgets(dlg)}")
assert dlg.table.rowCount() == 400
assert dt < 1.0, f"dialog construction still slow: {dt:.2f}s"
assert count_widgets(dlg) <= 60, f"too many eager widgets: {count_widgets(dlg)}"

dlg.show()
app.processEvents()
visible_after_show = count_widgets(dlg)
print(f"after show: {visible_after_show} widgets (viewport rows)")
assert 5 <= visible_after_show <= 80

# Scroll to the bottom; last row must get its widgets.
sb = dlg.table.verticalScrollBar()
sb.setValue(sb.maximum())
app.processEvents()
assert dlg.table.cellWidget(399, 1) is not None, "bottom row not materialized on scroll"
print(f"after scroll-to-bottom: {count_widgets(dlg)} widgets")

# Edit a materialized combo, then read back values for BOTH edited and
# never-materialized rows.
dlg.table.cellWidget(399, 1).setCurrentText("medium")
levels = dlg.get_thinking_levels()
timeouts = dlg.get_model_timeouts()
assert levels["model-399"] == "medium", levels.get("model-399")
assert levels["model-005"] == "high", levels.get("model-005")  # dict-backed row
assert timeouts["model-007"] == 42, timeouts.get("model-007")  # dict-backed row
assert len(levels) == 400 and len(timeouts) == 400

# Swap top two rows; item order changes, dict values stay keyed by model.
dlg._swap_rows(0, 1)
assert dlg.table.item(0, 0).data(Qt.ItemDataRole.UserRole) == "model-001"
assert dlg.table.item(1, 0).data(Qt.ItemDataRole.UserRole) == "model-000"
levels2 = dlg.get_thinking_levels()
assert levels2["model-001"] == "off" or levels2["model-001"] == levels["model-001"]
assert levels2["model-005"] == "high"

# Moving multiple selected rows must move them as a group. In particular,
# selectRow() is not additive, so verify the selection survives the move too.
selection_model = dlg.table.selectionModel()
selection_model.clearSelection()
for row in (1, 2):
    index = dlg.table.model().index(row, 0)
    selection_model.select(
        index,
        QtCore.QItemSelectionModel.SelectionFlag.Select
        | QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )
names_before = [dlg.table.item(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(4)]
dlg.move_item(-1)
names_after = [dlg.table.item(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(4)]
assert names_after[:4] == [names_before[1], names_before[2], names_before[0], names_before[3]]
assert sorted(index.row() for index in dlg.table.selectionModel().selectedRows()) == [0, 1]
assert dlg.get_thinking_levels()["model-005"] == "high"
assert dlg.get_model_timeouts()["model-007"] == 42

# Search filter hides rows; ensure does not choke.
dlg.filter_models("model-39")
hidden = sum(1 for i in range(400) if dlg.table.isRowHidden(i))
assert hidden == 400 - 10, hidden  # model-390..399

# Unchecking moves the row to Disabled; header-click sorting rebuilds the
# table without losing data.
dlg.table.item(50, 0).setCheckState(Qt.CheckState.Unchecked)
assert dlg.disabled_table.rowCount() == 1
dlg._on_header_clicked(0)
assert dlg.table.item(0, 0).data(Qt.ItemDataRole.UserRole) != ""
assert dlg.get_thinking_levels()["model-005"] == "high"

print("ALL LAZY-FALLBACK CHECKS PASSED")

for k in list(sys.modules):
    if k == "addon" or k.startswith("addon."):
        del sys.modules[k]
for k, v in saved.items():
    if v is not None:
        sys.modules[k] = v
if hasattr(_ai_client, "_bl_tmpdir"):
    _shutil.rmtree(_ai_client._bl_tmpdir, ignore_errors=True)
