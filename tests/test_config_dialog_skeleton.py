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


if __name__ == "__main__":
    unittest.main(verbosity=2)
