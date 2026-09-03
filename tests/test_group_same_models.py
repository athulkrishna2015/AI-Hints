"""Order-helper tests: clustering identical model names in the Advanced Global Fallback dialog."""
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

os.environ.setdefault(
    "AIHINTS_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".aihints_data"),
)

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

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
for k in ("addon.config_ui.tab_providers", "addon.config_ui.widgets", "addon.config_ui"):
    sys.modules.pop(k, None)
sys.modules["addon"] = pkg

from addon.config_ui.tab_providers import (  # noqa: E402
    FallbackOrderDialog,
    GlobalFallbackOrderDialog,
    cluster_pairs_by_model,
    normalized_model_key,
    sort_pairs_by,
)

for k in list(sys.modules):
    if k == "addon" or k.startswith("addon."):
        del sys.modules[k]
for k, v in saved.items():
    if v is not None:
        sys.modules[k] = v


class ClusterPairsByModelTests(unittest.TestCase):
    def test_groups_identical_models_by_first_seen_order(self):
        pairs = [("openai", "gpt-4o"), ("gemini", "gemini-flash"), ("openrouter", "gpt-4o")]
        self.assertEqual(
            cluster_pairs_by_model(pairs),
            [("openai", "gpt-4o"), ("openrouter", "gpt-4o"), ("gemini", "gemini-flash")],
        )

    def test_within_group_provider_order_preserved(self):
        pairs = [("c", "m"), ("a", "m"), ("b", "m")]
        self.assertEqual(cluster_pairs_by_model(pairs), pairs)

    def test_no_duplicates_unchanged(self):
        pairs = [("a", "m1"), ("b", "m2"), ("c", "m3")]
        self.assertEqual(cluster_pairs_by_model(pairs), pairs)

    def test_empty(self):
        self.assertEqual(cluster_pairs_by_model([]), [])

    def test_matching_ignores_case(self):
        pairs = [("a", "DeepSeek-V3"), ("b", "deepseek-v3"), ("c", "Other")]
        self.assertEqual(
            cluster_pairs_by_model(pairs),
            [("a", "DeepSeek-V3"), ("b", "deepseek-v3"), ("c", "Other")],
        )

    def test_vendor_prefix_matches_native_name(self):
        pairs = [("openai", "gpt-4o"), ("gemini", "gemini-flash"), ("openrouter", "openai/gpt-4o")]
        self.assertEqual(
            cluster_pairs_by_model(pairs),
            [("openai", "gpt-4o"), ("openrouter", "openai/gpt-4o"), ("gemini", "gemini-flash")],
        )

    def test_free_suffix_matches_base_model(self):
        pairs = [
            ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
            ("groq", "other"),
            ("openrouter", "meta-llama/llama-3.1-8b-instruct"),
        ]
        self.assertEqual(
            cluster_pairs_by_model(pairs),
            [
                ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
                ("openrouter", "meta-llama/llama-3.1-8b-instruct"),
                ("groq", "other"),
            ],
        )

    def test_similar_but_different_models_stay_separate(self):
        pairs = [("a", "gpt-4o"), ("b", "gpt-4o-mini"), ("c", "openai/gpt-4o")]
        self.assertEqual(cluster_pairs_by_model(pairs), [("a", "gpt-4o"), ("c", "openai/gpt-4o"), ("b", "gpt-4o-mini")])

    def test_ollama_style_tags_preserved(self):
        pairs = [("ollama", "llama3.1:8b"), ("other", "llama3.1:70b")]
        self.assertEqual(cluster_pairs_by_model(pairs), pairs)

    def test_duplicate_pairs_stay_stable(self):
        pairs = [("a", "m"), ("b", "n"), ("a", "m")]
        self.assertEqual(cluster_pairs_by_model(pairs), [("a", "m"), ("a", "m"), ("b", "n")])

    def test_normalized_model_key(self):
        self.assertEqual(normalized_model_key("openai/gpt-4o"), "gpt4o")
        self.assertEqual(normalized_model_key("meta-llama/llama-3.1-8b-instruct:free"), "llama318binstruct")
        self.assertEqual(normalized_model_key("  DeepSeek-V3 "), "deepseekv3")
        self.assertEqual(normalized_model_key("llama3.1:8b"), "llama318b")

    def test_separator_variants_cluster(self):
        pairs = [("a", "claude-haiku-4.5"), ("b", "zzz"), ("c", "claude-haiku-4-5")]
        self.assertEqual(
            cluster_pairs_by_model(pairs),
            [("a", "claude-haiku-4.5"), ("c", "claude-haiku-4-5"), ("b", "zzz")],
        )

    def test_missing_dash_clusters(self):
        pairs = [("a", "qwen3-32b"), ("b", "qwen-3-32b")]
        self.assertEqual(cluster_pairs_by_model(pairs), pairs)

    def test_at_separator_clusters(self):
        pairs = [("a", "claude-3-haiku@20240307"), ("b", "claude-3-haiku-20240307")]
        self.assertEqual(cluster_pairs_by_model(pairs), pairs)


class SortPairsByTests(unittest.TestCase):
    def test_sort_by_provider(self):
        pairs = [("openrouter", "z"), ("gemini", "b"), ("anthropic", "a")]
        self.assertEqual(
            sort_pairs_by(pairs, "provider"),
            [("anthropic", "a"), ("gemini", "b"), ("openrouter", "z")],
        )

    def test_sort_by_model(self):
        pairs = [("openai", "gpt-4o"), ("gemini", "abc"), ("openrouter", "gpt-4o")]
        self.assertEqual(
            sort_pairs_by(pairs, "model"),
            [("gemini", "abc"), ("openai", "gpt-4o"), ("openrouter", "gpt-4o")],
        )

    def test_sort_by_model_uses_normalized_key(self):
        pairs = [("openrouter", "openai/gpt-4o"), ("gemini", "aaa"), ("openai", "gpt-4o")]
        self.assertEqual(
            sort_pairs_by(pairs, "model"),
            [("gemini", "aaa"), ("openai", "gpt-4o"), ("openrouter", "openai/gpt-4o")],
        )

    def test_sort_is_case_insensitive(self):
        pairs = [("b", "Zebra"), ("a", "apple")]
        self.assertEqual(sort_pairs_by(pairs, "model"), [("a", "apple"), ("b", "Zebra")])

    def test_sort_empty(self):
        self.assertEqual(sort_pairs_by([], "provider"), [])


class GlobalDialogTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _make_dialog(self, rows, disabled=()):
        parent = QtWidgets.QWidget()
        parent.config = {}
        parent.custom_providers_data = {}
        parent.disabled_global_model_priority_data = [list(d) for d in disabled]
        return GlobalFallbackOrderDialog(parent, rows)

    def _order(self, dlg):
        return [dlg._row_pair(dlg.enabled_table, r) for r in range(dlg.enabled_table.rowCount())]

    def _disabled_order(self, dlg):
        return [dlg._row_pair(dlg.disabled_table, r) for r in range(dlg.disabled_table.rowCount())]

    def test_table_columns_and_rows(self):
        dlg = self._make_dialog([("openai", "gpt-4o"), ("gemini", "alpha")])
        self.assertEqual(dlg.enabled_table.columnCount(), 5)
        self.assertEqual(dlg.enabled_table.rowCount(), 2)
        self.assertEqual(dlg.disabled_table.rowCount(), 0)
        self.assertEqual(dlg.enabled_table.item(0, 0).text(), "Openai")
        self.assertEqual(dlg.enabled_table.item(0, 1).text(), "gpt-4o")
        self.assertEqual(dlg.get_ordered_list(), [("openai", "gpt-4o"), ("gemini", "alpha")])
        self.assertEqual(dlg.get_disabled_list(), [])

    def test_populate_splits_disabled(self):
        dlg = self._make_dialog([("a", "m1"), ("b", "m2"), ("c", "m3")], disabled=[("b", "m2")])
        self.assertEqual(self._order(dlg), [("a", "m1"), ("c", "m3")])
        self.assertEqual(self._disabled_order(dlg), [("b", "m2")])
        self.assertEqual(dlg.get_disabled_list(), [("b", "m2")])

    def test_uncheck_moves_to_disabled(self):
        from PyQt6.QtCore import Qt

        dlg = self._make_dialog([("a", "m1"), ("b", "m2")])
        dlg.enabled_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(self._order(dlg), [("b", "m2")])
        self.assertEqual(self._disabled_order(dlg), [("a", "m1")])
        self.assertEqual(dlg.get_disabled_list(), [("a", "m1")])

    def test_check_in_disabled_moves_to_enabled(self):
        from PyQt6.QtCore import Qt

        dlg = self._make_dialog([("a", "m1"), ("b", "m2")], disabled=[("a", "m1")])
        dlg.disabled_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(self._disabled_order(dlg), [])
        self.assertEqual(self._order(dlg), [("b", "m2"), ("a", "m1")])
        self.assertEqual(dlg.get_ordered_list(), [("b", "m2"), ("a", "m1")])

    def _make_dialog_with_values(self, rows, thinking=None, timeouts=None, per_thinking=None, per_timeouts=None):
        parent = QtWidgets.QWidget()
        parent.config = {}
        parent.custom_providers_data = {}
        parent.disabled_global_model_priority_data = []
        parent.global_thinking_levels_data = thinking or {}
        parent.global_model_timeouts_data = timeouts or {}
        parent.thinking_levels_data = per_thinking or {}
        parent.model_timeouts_data = per_timeouts or {}
        return GlobalFallbackOrderDialog(parent, rows)

    def test_thinking_timeout_seeded_from_per_provider(self):
        dlg = self._make_dialog_with_values(
            [("openai", "gpt-4o")],
            per_thinking={"openai": {"gpt-4o": "high"}},
            per_timeouts={"openai": {"gpt-4o": 45}},
        )
        levels = dlg.get_global_thinking_levels()
        timeouts = dlg.get_global_model_timeouts()
        self.assertEqual(levels["openai"]["gpt-4o"], "high")
        self.assertEqual(timeouts["openai"]["gpt-4o"], 45)

    def test_saved_global_values_win_over_per_provider(self):
        dlg = self._make_dialog_with_values(
            [("openai", "gpt-4o")],
            thinking={"openai": {"gpt-4o": "low"}},
            per_thinking={"openai": {"gpt-4o": "high"}},
        )
        self.assertEqual(dlg.get_global_thinking_levels()["openai"]["gpt-4o"], "low")

    def test_edited_widgets_saved(self):
        dlg = self._make_dialog([("openai", "gpt-4o")])
        dlg._ensure_visible_widgets()
        combo = dlg.enabled_table.cellWidget(0, 2)
        spin = dlg.enabled_table.cellWidget(0, 3)
        self.assertIsNotNone(combo)
        self.assertIsNotNone(spin)
        combo.setCurrentText("medium")
        spin.setValue(90)
        self.assertEqual(dlg.get_global_thinking_levels()["openai"]["gpt-4o"], "medium")
        self.assertEqual(dlg.get_global_model_timeouts()["openai"]["gpt-4o"], 90)

    def test_header_click_sorts_provider_asc_then_desc(self):
        rows = [("openrouter", "z"), ("gemini", "b"), ("anthropic", "a")]
        dlg = self._make_dialog(rows)
        dlg._on_header_clicked(0, dlg.enabled_table)
        self.assertEqual(self._order(dlg), [("anthropic", "a"), ("gemini", "b"), ("openrouter", "z")])
        dlg._on_header_clicked(0, dlg.enabled_table)
        self.assertEqual(self._order(dlg), [("openrouter", "z"), ("gemini", "b"), ("anthropic", "a")])
        self.assertEqual(dlg.get_ordered_list(), self._order(dlg))

    def test_header_click_sorts_model_normalized(self):
        rows = [("openrouter", "openai/gpt-4o"), ("gemini", "aaa"), ("openai", "gpt-4o")]
        dlg = self._make_dialog(rows)
        dlg._on_header_clicked(1, dlg.enabled_table)
        self.assertEqual(self._order(dlg), [("gemini", "aaa"), ("openai", "gpt-4o"), ("openrouter", "openai/gpt-4o")])

    def test_header_sort_keeps_lists_separate(self):
        dlg = self._make_dialog(
            [("openrouter", "z"), ("gemini", "b"), ("anthropic", "a")], disabled=[("anthropic", "a")]
        )
        dlg._on_header_clicked(0, dlg.enabled_table)
        self.assertEqual(self._order(dlg), [("gemini", "b"), ("openrouter", "z")])
        self.assertEqual(self._disabled_order(dlg), [("anthropic", "a")])

    def test_group_keeps_lists_separate(self):
        dlg = self._make_dialog(
            [("openai", "gpt-4o"), ("gemini", "x"), ("openrouter", "openai/gpt-4o"), ("z", "gpt-4o")],
            disabled=[("z", "gpt-4o")],
        )
        dlg.group_same_models()
        self.assertEqual(
            self._order(dlg),
            [("openai", "gpt-4o"), ("openrouter", "openai/gpt-4o"), ("gemini", "x")],
        )
        self.assertEqual(self._disabled_order(dlg), [("z", "gpt-4o")])

    def test_move_and_remove_rows(self):
        dlg = self._make_dialog([("a", "m1"), ("b", "m2"), ("c", "m3")])
        dlg.enabled_table.item(2, 0).setSelected(True)
        dlg.enabled_table.setCurrentCell(2, 0)
        dlg.move_item(-1)
        self.assertEqual(self._order(dlg), [("a", "m1"), ("c", "m3"), ("b", "m2")])
        dlg.remove_models("selected")
        self.assertEqual(self._order(dlg), [("a", "m1"), ("b", "m2")])

    def test_group_large_list_completes(self):
        import time as _time

        rows = [(f"p{i % 50}", f"model-{i % 200}") for i in range(1500)]
        dlg = self._make_dialog(rows)
        t0 = _time.perf_counter()
        dlg.group_same_models()
        dt = _time.perf_counter() - t0
        self.assertLess(dt, 10, f"group_same_models took {dt:.1f}s")
        self.assertEqual(dlg.enabled_table.rowCount(), 1500)

    def test_reorder_progress_completes(self):
        from unittest.mock import patch

        rows = [(f"p{i % 5}", f"model-{i % 4}") for i in range(20)]
        dlg = self._make_dialog(rows)
        dlg._reorder_progress_after = 5
        seen = {}

        class FakeProgress:
            def __init__(self, *args):
                seen["shown"] = True
                seen["closed"] = False

            def setWindowModality(self, *args):
                pass

            def setMinimumDuration(self, *args):
                pass

            def setValue(self, *args):
                pass

            def wasCanceled(self):
                return False

            def close(self):
                seen["closed"] = True

        with patch("PyQt6.QtWidgets.QProgressDialog", FakeProgress):
            dlg.group_same_models()
        self.assertTrue(seen.get("shown"))
        self.assertTrue(seen.get("closed"))
        self.assertEqual(dlg.enabled_table.rowCount(), 20)
        got = [dlg._row_pair(dlg.enabled_table, r) for r in range(20)]
        self.assertEqual(got, cluster_pairs_by_model(rows))

    def test_reorder_cancel_keeps_table_complete(self):
        from unittest.mock import patch

        rows = [(f"p{i % 5}", f"model-{i % 4}") for i in range(20)]
        dlg = self._make_dialog(rows)
        dlg._reorder_progress_after = 5
        seen = {}

        class FakeProgress:
            def __init__(self, *args):
                seen["closed"] = False

            def setWindowModality(self, *args):
                pass

            def setMinimumDuration(self, *args):
                pass

            def setValue(self, *args):
                pass

            def wasCanceled(self):
                return True

            def close(self):
                seen["closed"] = True

        with patch("PyQt6.QtWidgets.QProgressDialog", FakeProgress):
            dlg.group_same_models()
        self.assertTrue(seen.get("closed"))
        got = [dlg._row_pair(dlg.enabled_table, r) for r in range(dlg.enabled_table.rowCount())]
        self.assertEqual(dlg.enabled_table.rowCount(), 20)
        self.assertEqual(sorted(got), sorted(rows))


class ProviderDialogHeaderSortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _make_dialog(self):
        class FakeSettingsDialog(QtWidgets.QWidget):
            disabled_fallback_models_data = {}
            thinking_levels_data = {"p": {"m-high": "high", "m-low": "low"}}
            model_timeouts_data = {"p": {"m-slow": 42}}

        parent = FakeSettingsDialog()
        return FallbackOrderDialog(parent, "p", "m-zed", ["m-zed", "m-high", "m-low", "m-slow"], [])

    def _names(self, dlg):
        return [dlg.table.item(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(dlg.table.rowCount())]

    def test_header_click_sorts_model_and_keeps_values(self):
        from PyQt6.QtCore import Qt

        dlg = self._make_dialog()
        dlg._on_header_clicked(0)
        names = self._names(dlg)
        self.assertEqual(names, sorted(names, key=lambda n: (normalized_model_key(n), n.casefold())))
        self.assertEqual(dlg.get_thinking_levels()["m-high"], "high")
        self.assertEqual(dlg.get_thinking_levels()["m-low"], "low")
        self.assertEqual(dlg.get_model_timeouts()["m-slow"], 42)
        dlg._on_header_clicked(0)
        self.assertEqual(self._names(dlg), list(reversed(names)))

    def test_header_click_sorts_thinking_then_timeout(self):
        dlg = self._make_dialog()
        dlg._on_header_clicked(1)
        self.assertEqual(
            self._names(dlg),
            ["m-zed", "m-slow", "m-low", "m-high"],
            self._names(dlg),
        )
        dlg._on_header_clicked(2)
        self.assertEqual(self._names(dlg)[-1], "m-slow")

    def _names_in(self, dlg, table):
        return [table.item(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(table.rowCount())]

    def test_uncheck_moves_to_disabled(self):
        from PyQt6.QtCore import Qt

        dlg = self._make_dialog()
        dlg.enabled_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(self._names_in(dlg, dlg.enabled_table), ["m-zed", "m-low", "m-slow"])
        self.assertEqual(self._names_in(dlg, dlg.disabled_table), ["m-high"])
        self.assertEqual(dlg.get_disabled_list(), ["m-high"])
        self.assertEqual(dlg.get_active_model(), "m-zed")

    def test_uncheck_active_promotes_next(self):
        from PyQt6.QtCore import Qt

        dlg = self._make_dialog()
        dlg.enabled_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dlg.get_active_model(), "m-high")
        self.assertEqual(self._names_in(dlg, dlg.disabled_table), ["m-zed"])

    def test_cannot_disable_last_enabled(self):
        from PyQt6.QtCore import Qt

        dlg = self._make_dialog()
        for _ in range(3):
            dlg.enabled_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dlg.enabled_table.rowCount(), 1)
        dlg.enabled_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dlg.enabled_table.rowCount(), 1)
        self.assertEqual(dlg.get_active_model(), "m-zed")

    def test_check_in_disabled_moves_to_enabled(self):
        from PyQt6.QtCore import Qt

        class FakeSettingsDialog(QtWidgets.QWidget):
            disabled_fallback_models_data = {"p": ["m-low"]}
            thinking_levels_data = {}
            model_timeouts_data = {}

        parent = FakeSettingsDialog()
        dlg = FallbackOrderDialog(parent, "p", "m-zed", ["m-zed", "m-high", "m-low", "m-slow"], [])
        self.assertEqual(self._names_in(dlg, dlg.disabled_table), ["m-low"])
        dlg.disabled_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dlg.disabled_table.rowCount(), 0)
        self.assertIn("m-low", self._names_in(dlg, dlg.enabled_table))
        self.assertEqual(dlg.get_disabled_list(), [])
