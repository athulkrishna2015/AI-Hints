"""Cross-window fallback sync helpers + embedded model-parameter panel."""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AIHINTS_DATA_DIR", os.path.join(os.path.dirname(__file__), ".aihints_data"))

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402

aqt_mod = types.ModuleType("aqt")
aqt_mod.mw = MagicMock()
qt_mod = types.ModuleType("aqt.qt")
utils_mod = types.ModuleType("aqt.utils")
utils_mod.tooltip = lambda *args, **kwargs: None
for _mod in (QtCore, QtGui, QtWidgets):
    for _name in dir(_mod):
        if not _name.startswith("_"):
            setattr(qt_mod, _name, getattr(_mod, _name))
sys.modules["aqt"] = aqt_mod
sys.modules["aqt.qt"] = qt_mod
sys.modules["aqt.utils"] = utils_mod

pkg = types.ModuleType("addon")
pkg.__path__ = [os.path.join(PROJECT_ROOT, "addon")]
pkg.__package__ = "addon"
sys.modules["addon"] = pkg

from addon.config_ui.tab_providers import (  # noqa: E402
    merge_provider_into_global, merge_global_into_provider, remove_pair_from_lists,
)
from addon.config_ui.variant_columns import (  # noqa: E402
    collect_variant_values,
)
from addon.config_ui.tab_providers import (  # noqa: E402
    FallbackOrderDialog, GlobalFallbackOrderDialog, ProvidersTabMixin,
)


class ColumnReorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _parent(self):
        parent = QtWidgets.QWidget()
        parent.config = {}
        parent.model_variants_data = {"p|m1": {"temperature": 0.3}}
        parent.model_fallbacks_data = {}
        parent.disabled_fallback_models_data = {}
        parent.fallback_column_order = []
        parent.global_fallback_column_order = []
        return parent

    def test_drag_updates_saved_order_and_other_list(self):
        parent = self._parent()
        dlg = FallbackOrderDialog(parent, "p", "m1", ["m1", "m2"], [])
        header = dlg.enabled_table.horizontalHeader()
        header.moveSection(2, 0)  # Temp column to the front
        order = [header.logicalIndex(v) for v in range(header.count())]
        self.assertEqual(order[0], 2)
        self.assertEqual(parent.fallback_column_order, order)
        other = [dlg.disabled_table.horizontalHeader().logicalIndex(v)
                 for v in range(header.count())]
        self.assertEqual(other, order)

    def test_reorder_in_disabled_list_syncs_enabled_and_persists(self):
        parent = self._parent()
        dlg = FallbackOrderDialog(parent, "p", "m1", ["m1", "m2"], [])
        header = dlg.disabled_table.horizontalHeader()
        header.moveSection(3, 0)  # Max tokens to the front in Disabled
        order = [header.logicalIndex(v) for v in range(header.count())]
        self.assertEqual(order[0], 3)
        self.assertEqual(parent.fallback_column_order, order)
        enabled_order = [dlg.enabled_table.horizontalHeader().logicalIndex(v)
                         for v in range(header.count())]
        self.assertEqual(enabled_order, order)

    def test_saved_order_restored_in_new_dialog(self):
        parent = self._parent()
        parent.fallback_column_order = [2, 0, 1, 3, 4, 5, 6, 7]
        dlg = FallbackOrderDialog(parent, "p", "m1", ["m1"], [])
        header = dlg.enabled_table.horizontalHeader()
        self.assertEqual([header.logicalIndex(v) for v in range(header.count())],
                         parent.fallback_column_order)
        # Moving columns does not move the underlying row data.
        self.assertEqual(dlg.get_ordered_list(), [])
        self.assertAlmostEqual(dlg.get_variant_overrides()["p|m1"]["temperature"], 0.3)

    def test_global_column_order(self):
        parent = self._parent()
        gdlg = GlobalFallbackOrderDialog(parent, [["p", "m1"]])
        header = gdlg.enabled_table.horizontalHeader()
        header.moveSection(4, 0)
        order = [header.logicalIndex(v) for v in range(header.count())]
        self.assertEqual(order[0], 4)
        self.assertEqual(parent.global_fallback_column_order, order)


class CrossWindowSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _parent(self):
        parent = QtWidgets.QWidget()
        parent.model_fallbacks_data = {"p": ["m1", "m2"]}
        parent.disabled_fallback_models_data = {"p": []}
        parent.global_model_priority_data = []
        parent.disabled_global_model_priority_data = []
        parent.model_timeouts_data = {}
        parent.global_model_timeouts_data = {}
        parent.provider_widgets = {}
        parent.global_fallback_dlg = None
        parent.model_variants_data = {}
        return parent

    @staticmethod
    def _pairs(dlg, table):
        return [dlg._row_pair_opt(table, r) for r in range(table.rowCount())]

    def test_provider_fetch_syncs_open_global_dialog(self):
        parent = self._parent()
        gdlg = GlobalFallbackOrderDialog(parent, [["p", "m1"], ["p", "m2"]])
        parent.global_fallback_dlg = gdlg
        ProvidersTabMixin.sync_from_provider(parent, "p", ["m1"], ["m1", "m2", "m3"])
        self.assertEqual(parent.global_model_priority_data, [["p", "m1"]])
        self.assertIn(("p", "m1"), self._pairs(gdlg, gdlg.enabled_table))
        self.assertIn(("p", "m2"), self._pairs(gdlg, gdlg.disabled_table))
        self.assertIn(("p", "m3"), self._pairs(gdlg, gdlg.disabled_table))

    def test_global_fetch_syncs_open_provider_dialog(self):
        parent = self._parent()
        pdlg = FallbackOrderDialog(parent, "p", "m1", ["m1", "m2"], [])
        parent.provider_widgets = {"p": types.SimpleNamespace(fallback_dialog=pdlg)}
        ProvidersTabMixin.sync_from_global(
            parent, {("p", "m1"): True, ("p", "m2"): False, ("p", "m3"): True}
        )
        enabled = [pdlg._row_data(pdlg.enabled_table, r)["name"]
                   for r in range(pdlg.enabled_table.rowCount())]
        disabled = [pdlg._row_data(pdlg.disabled_table, r)["name"]
                    for r in range(pdlg.disabled_table.rowCount())]
        self.assertIn("m1", enabled)
        self.assertIn("m3", enabled)
        self.assertIn("m2", disabled)
        self.assertEqual(parent.model_fallbacks_data["p"], ["m1", "m3", "m2"])

    def test_provider_toggle_auto_syncs_global(self):
        parent = self._parent()
        gdlg = GlobalFallbackOrderDialog(parent, [["p", "m1"], ["p", "m2"]])
        parent.global_fallback_dlg = gdlg
        parent.disabled_fallback_models_data = {"p": ["m2"]}
        pdlg = FallbackOrderDialog(parent, "p", "m1", ["m1", "m2"], [])
        parent.provider_widgets = {
            "p": types.SimpleNamespace(fallback_dialog=pdlg, provider="p")
        }
        # Toggle m2 from Disabled to Enabled in the per-provider dialog.
        row = next(r for r in range(pdlg.disabled_table.rowCount())
                   if pdlg._row_data(pdlg.disabled_table, r).get("name") == "m2")
        pdlg._move_row_to_other_table(pdlg.disabled_table, row, True)
        enabled = self._pairs(gdlg, gdlg.enabled_table)
        self.assertIn(("p", "m2"), enabled)
        self.assertNotIn(("p", "m2"), self._pairs(gdlg, gdlg.disabled_table))

    def test_remove_propagates_to_both_open_dialogs(self):
        parent = self._parent()
        gdlg = GlobalFallbackOrderDialog(parent, [["p", "m1"], ["p", "m2"]])
        parent.global_fallback_dlg = gdlg
        pdlg = FallbackOrderDialog(parent, "p", "m1", ["m1", "m2"], [])
        parent.provider_widgets = {"p": types.SimpleNamespace(fallback_dialog=pdlg)}
        ProvidersTabMixin.remove_pair_everywhere(parent, "p", "m2")
        self.assertNotIn(("p", "m2"), self._pairs(gdlg, gdlg.enabled_table))
        self.assertNotIn(("p", "m2"), self._pairs(gdlg, gdlg.disabled_table))
        remaining = [pdlg._row_data(t, r)["name"]
                     for t in pdlg._tables() for r in range(t.rowCount())]
        self.assertNotIn("m2", remaining)
        self.assertNotIn("m2", parent.model_fallbacks_data["p"])


class MergeHelperTests(unittest.TestCase):
    def test_provider_fetch_wins_for_that_provider(self):
        on, off = merge_provider_into_global(
            [["gemini", "g1"], ["openai", "o1"]], [["gemini", "g2"]],
            "gemini", {"g1"}, ["g1", "g2", "g3"],
        )
        self.assertEqual(on, [["gemini", "g1"], ["openai", "o1"]])  # original order preserved
        self.assertEqual(off, [["gemini", "g2"], ["gemini", "g3"]])

    def test_global_fetch_wins_for_affected_providers(self):
        fb, dis = merge_global_into_provider(
            {"gemini": ["old"]}, {"gemini": []},
            {("gemini", "g1"): True, ("gemini", "g2"): False, ("openai", "o1"): True},
        )
        self.assertEqual(fb["gemini"], ["g1", "g2"])
        self.assertEqual(dis["gemini"], ["g2"])
        self.assertEqual(fb["openai"], ["o1"])
        self.assertEqual(dis["openai"], [])

    def test_remove_pair_touches_all_four_lists(self):
        fb, dis, on, off = remove_pair_from_lists(
            {"p": ["m", "x"]}, {"p": ["m"]}, [["p", "m"]], [["q", "m"], ["p", "m"]], "p", "m"
        )
        self.assertEqual(fb, {"p": ["x"]})
        self.assertEqual(dis, {"p": []})
        self.assertEqual(on, [])
        self.assertEqual(off, [["q", "m"]])


class VariantValueTests(unittest.TestCase):
    def test_defaults_are_not_persisted(self):
        self.assertEqual(
            collect_variant_values("", "", "auto", "", "auto", "Yes"), {}
        )

    def test_non_defaults_and_zero_budget(self):
        self.assertEqual(
            collect_variant_values("0.7", "4096", "high", "0", "json_object", "No"),
            {"temperature": 0.7, "max_tokens": 4096, "reasoning_effort": "high",
             "thinking_budget": 0, "response_format": "json_object",
             "prompt_caching": False},
        )

    def test_invalid_numbers_are_dropped(self):
        self.assertEqual(collect_variant_values("abc", "-5", "x", "-1", "bad", "Yes"), {})


class DialogVariantColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _parent(self):
        parent = QtWidgets.QWidget()
        parent.config = {"model_variants": {"p|m1": {"temperature": 0.3}}}
        parent.model_variants_data = dict(parent.config["model_variants"])
        parent.model_fallbacks_data = {}
        parent.disabled_fallback_models_data = {}
        return parent

    def test_per_provider_columns_are_per_row_and_loaded(self):
        parent = self._parent()
        dlg = FallbackOrderDialog(parent, "p", "m1", ["m1", "m2"], [])
        self.assertEqual(dlg.enabled_table.columnCount(), 8)
        # Saved override shows in m1's row, not in m2's row.
        self.assertAlmostEqual(float(dlg.enabled_table.item(0, 2).text()), 0.3)
        self.assertEqual(dlg.enabled_table.item(1, 2).text(), "")
        # Edit m2's cells; each row is independent.
        dlg.enabled_table.item(1, 2).setText("0.9")
        dlg.enabled_table.item(1, 4).setData(Qt.ItemDataRole.EditRole, "high")
        dlg.enabled_table.item(1, 7).setData(Qt.ItemDataRole.EditRole, "No")
        out = dlg.get_variant_overrides()
        self.assertAlmostEqual(out["p|m1"]["temperature"], 0.3)
        self.assertEqual(out["p|m2"], {
            "temperature": 0.9, "reasoning_effort": "high", "prompt_caching": False,
        })
        # Parent snapshot is untouched until OK.
        self.assertAlmostEqual(parent.model_variants_data["p|m1"]["temperature"], 0.3)

    def test_global_columns_loaded_and_editable(self):
        parent = self._parent()
        dlg = GlobalFallbackOrderDialog(parent, [["p", "m1"], ["p", "m2"]])
        self.assertEqual(dlg.enabled_table.columnCount(), 10)
        self.assertAlmostEqual(float(dlg.enabled_table.item(0, 4).text()), 0.3)
        self.assertEqual(dlg.enabled_table.item(1, 4).text(), "")
        dlg.enabled_table.item(1, 4).setText("1.2")
        out = dlg.get_variant_overrides()
        self.assertAlmostEqual(out["p|m1"]["temperature"], 0.3)
        self.assertAlmostEqual(out["p|m2"]["temperature"], 1.2)

    def test_clearing_all_cells_removes_override(self):
        parent = self._parent()
        dlg = FallbackOrderDialog(parent, "p", "m1", ["m1"], [])
        for col in range(2, 8):
            dlg.enabled_table.item(0, col).setText("")
        dlg.enabled_table.item(0, 4).setData(Qt.ItemDataRole.EditRole, "auto")
        dlg.enabled_table.item(0, 6).setData(Qt.ItemDataRole.EditRole, "auto")
        dlg.enabled_table.item(0, 7).setData(Qt.ItemDataRole.EditRole, "Yes")
        self.assertNotIn("p|m1", dlg.get_variant_overrides())


if __name__ == "__main__":
    unittest.main()
