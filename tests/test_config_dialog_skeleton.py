"""Static guards for the config dialog's load/save attribute contract.

Regression context (v8.6.4): a new method was accidentally inserted into the
middle of ``ConfigDialog.load_config_into_ui``.  The remainder of that method's
body (the block that assigns ``self.model_fallbacks_data`` and friends) became
the body of the new method, so none of those attributes existed at save time:

    Notification: Error saving configuration:
    'ConfigDialog' object has no attribute 'model_fallbacks_data'

These tests are pure AST checks (no Qt, no Anki) and run in milliseconds.
"""
import ast
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIALOG_PATH = os.path.join(PROJECT_ROOT, "addon", "config_ui", "main_dialog.py")

# Attributes that ``save_config`` reads unguarded and that must therefore be
# created by ``load_config_into_ui`` (or ``setup_ui``) before it can run.
LOAD_TARGETS = (
    "model_fallbacks_data",
    "disabled_fallback_models_data",
    "transient_skip_data",
    "global_model_priority_data",
    "disabled_global_model_priority_data",
)


class _ConfigDialogAst:
    def __init__(self, path=DIALOG_PATH):
        with open(path, "r", encoding="utf-8") as fh:
            self.source = fh.read()
        self.tree = ast.parse(self.source)
        self.cls = None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == "ConfigDialog":
                self.cls = node
                break
        if self.cls is None:
            raise AssertionError("ConfigDialog class not found in main_dialog.py")

    def method(self, name):
        for node in self.cls.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"ConfigDialog.{name} not found")

    def assigned_attrs(self, func):
        """``self.foo = ...`` attribute names assigned in a function."""
        out = set()
        for node in ast.walk(func):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            for tgt in targets:
                for sub in ast.walk(tgt):
                    if (isinstance(sub, ast.Attribute)
                            and isinstance(sub.value, ast.Name)
                            and sub.value.id == "self"):
                        out.add(sub.attr)
        return out

    def guarded_attrs(self, func):
        """Attributes referenced inside ``hasattr(self, "...")`` tests."""
        out = set()
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Name) and f.id == "hasattr"):
                continue
            if len(node.args) != 2:
                continue
            owner, attr = node.args
            if (isinstance(owner, ast.Name) and owner.id == "self"
                    and isinstance(attr, ast.Constant)
                    and isinstance(attr.value, str)):
                out.add(attr.value)
        return out

    def read_attrs(self, func):
        """``self.foo`` attribute names read in a function (excluding calls)."""
        assigned = self.assigned_attrs(func)
        called = set()
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Attribute)
                        and isinstance(f.value, ast.Name)
                        and f.value.id == "self"):
                    called.add(f.attr)
        out = set()
        for node in ast.walk(func):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"):
                out.add(node.attr)
        return out - assigned - called


class ConfigDialogLoadSaveContractTests(unittest.TestCase):
    def setUp(self):
        self.ast = _ConfigDialogAst()

    def test_all_config_dialog_methods_present(self):
        """v8.6.4/8.6.5 shipped main_dialog.py missing 21 of 42 methods.

        The packaged artifact still had ``save_config`` but had lost
        ``refresh_custom_list`` and the whole custom-provider management
        surface, so the dialog could not be used. Fail loudly if the class
        shrinks again.
        """
        names = {f.name for f in self.ast.cls.body
                 if isinstance(f, ast.FunctionDef)}
        required = {
            "load_config_into_ui", "save_config", "setup_ui", "on_tab_changed",
            "_on_tab_changed_tracker", "copy_to_clipboard", "refresh_custom_list",
            "on_delete_binary", "on_fetch_all_models", "_local_test_endpoint",
            "on_test_model", "on_test_all_models", "on_fetch_models",
            "_rename_provider", "_save_custom_dialog", "on_add_custom",
            "on_edit_custom", "on_remove_custom", "on_restore_current_tab",
            "on_restore_models_only", "on_restore_general", "on_restore_providers",
            "on_restore_advanced", "stop_migration", "move_provider_row",
            "_update_models_now",
        }
        missing = sorted(required - names)
        self.assertEqual(missing, [], "ConfigDialog is missing method(s): %r" % (missing,))
        self.assertGreaterEqual(
            len(names), 40,
            "ConfigDialog defines only %d methods; the class was truncated." % len(names),
        )

    def test_model_variants_tab_is_wired(self):
        """The per-model settings tab must be built, loaded and saved."""
        with open(DIALOG_PATH, "r", encoding="utf-8") as fh:
            dialog = fh.read()
        mixin_path = os.path.join(PROJECT_ROOT, "addon", "config_ui",
                                  "tab_model_variants.py")
        with open(mixin_path, "r", encoding="utf-8") as fh:
            mixin = fh.read()

        self.assertIn("ModelVariantsTabMixin", dialog)
        self.assertIn('("Model Variants", self._create_model_variants_tab)', dialog)
        self.assertIn("self._collect_model_variants()", dialog)
        self.assertIn("self._load_model_variants_into_ui()", dialog)
        for method in ("_create_model_variants_tab", "_collect_model_variants",
                       "_load_model_variants_into_ui"):
            self.assertIn(f"def {method}(", mixin)
        # The table must be pre-filled from the saved model lists, not empty.
        self.assertIn("known_model_pairs(self.config)", mixin)
        self.assertIn("table.setRowCount(len(rows))", mixin)
        # The old "Add from priority/fallback lists" button hung for minutes
        # because it called insertRow + setCellWidget once per model (thousands
        # of rows). Refresh must bulk-fill plain items with a shared delegate.
        self.assertNotIn("setCellWidget", mixin)
        load = next(
            node for node in ast.walk(ast.parse(mixin))
            if isinstance(node, ast.FunctionDef)
            and node.name == "_load_model_variants_into_ui"
        )
        self.assertNotIn(
            "insertRow",
            {n.func.attr for n in ast.walk(load)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)},
        )

    def test_load_config_into_ui_contains_no_nested_methods(self):
        """A nested ``def`` here means a method was spliced into the body."""
        load = self.ast.method("load_config_into_ui")
        nested = [
            n.name for n in ast.walk(load)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not load
        ]
        self.assertEqual(
            nested, [],
            "load_config_into_ui contains nested function(s) %r. This is the "
            "v8.6.4 bug shape: a class method was pasted into the middle of "
            "the loader, swallowing the rest of its body." % (nested,),
        )

    def test_load_targets_are_assigned_by_loader(self):
        load_attrs = self.ast.assigned_attrs(self.ast.method("load_config_into_ui"))
        setup_attrs = self.ast.assigned_attrs(self.ast.method("setup_ui"))
        available = load_attrs | setup_attrs
        missing = [n for n in LOAD_TARGETS if n not in available]
        self.assertEqual(
            missing, [],
            "load_config_into_ui no longer assigns %r; save_config reads these "
            "unguarded and will raise AttributeError." % (missing,),
        )

    def test_save_config_reads_are_initialised_before_save(self):
        """Every unguarded ``self.X`` read in save_config must be created early."""
        save = self.ast.method("save_config")
        load_attrs = self.ast.assigned_attrs(self.ast.method("load_config_into_ui"))
        setup_attrs = self.ast.assigned_attrs(self.ast.method("setup_ui"))
        init_attrs = self.ast.assigned_attrs(self.ast.method("__init__"))
        guarded = self.ast.guarded_attrs(save)
        assigned_in_save = self.ast.assigned_attrs(save)
        # Attributes created by widget-construction helpers elsewhere in the
        # package (tab mixins assign self.X during setup_ui).
        pkg_dir = os.path.join(PROJECT_ROOT, "addon", "config_ui")
        mixin_attrs = set()
        for fname in os.listdir(pkg_dir):
            if not fname.endswith(".py") or fname == "main_dialog.py":
                continue
            try:
                with open(os.path.join(pkg_dir, fname), "r", encoding="utf-8") as fh:
                    mod_tree = ast.parse(fh.read())
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(mod_tree):
                if isinstance(node, ast.FunctionDef):
                    mixin_attrs |= self.ast.assigned_attrs(node)
        available = load_attrs | setup_attrs | init_attrs | mixin_attrs | assigned_in_save | guarded

        unsupported = sorted(
            a for a in self.ast.read_attrs(save)
            if a not in available and not a.startswith("__")
        )
        self.assertEqual(
            unsupported, [],
            "save_config reads attribute(s) %r that nothing creates before "
            "save time. Either initialise them in load_config_into_ui/setup_ui "
            "or guard the read with hasattr()." % (unsupported,),
        )


    def test_batch_settings_survive_save_and_reload(self):
        """Batch-tab toggles must be written by save and restored by load.

        Regression (v9.0.2): ``batch_prevent_sleep`` and ``batch_sync_after``
        were read from the checkboxes when a batch started, but ``save_config``
        never wrote them and ``load_config_into_ui`` never restored them.  The
        checkbox looked enabled until the dialog was reopened, then silently
        reverted to its default, so the setting could never be saved.
        """
        keys = (
            "batch_limit",
            "batch_full_scan",
            "batch_sync_after",
            "batch_prevent_sleep",
            "multithread_providers",
        )

        def string_constants(func):
            return {
                n.value for n in ast.walk(func)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }

        saved = string_constants(self.ast.method("save_config"))
        loaded = string_constants(self.ast.method("load_config_into_ui"))
        missing_save = [k for k in keys if k not in saved]
        missing_load = [k for k in keys if k not in loaded]
        self.assertEqual(
            missing_save, [],
            "save_config does not persist batch setting(s) %r; toggling them "
            "in the Batch tab is lost when the config dialog reloads." % (missing_save,),
        )
        self.assertEqual(
            missing_load, [],
            "load_config_into_ui does not restore batch setting(s) %r; the "
            "checkbox silently reverts to its default on reopen." % (missing_load,),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
