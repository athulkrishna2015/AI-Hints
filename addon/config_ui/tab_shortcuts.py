from aqt.qt import *

class ShortcutsTabMixin:
    def _create_shortcuts_tab(self):
        """Constructs the Tab 4: Shortcuts UI"""
        self.shortcuts_tab = QWidget()
        short_layout = QFormLayout()
        
        self.modifier_cb = QComboBox()
        self.modifier_cb.addItems(["alt", "ctrl", "shift", "meta", "none"])
        self.modifier_cb.setToolTip("The modifier key to use with shortcuts. 'meta' is the Command key on Mac or Windows key on Windows. 'none' means no modifier.")
        short_layout.addRow("Shortcut Modifier:", self.modifier_cb)
        
        self.shortcut_edits = {}
        shortcut_labels = {
            "generate": "Generate / Regenerate:",
            "toggle-options": "Toggle Options:",
            "toggle-hints": "Toggle Hints:",
            "clear": "Clear:",
            "refresh": "Refresh:",
            "show-json": "Show JSON:"
        }
        shortcut_tooltips = {
            "generate": "Triggers automatic generation or regeneration of hints for the current card.",
            "toggle-options": "Collapses or expands the multiple-choice options field.",
            "toggle-hints": "Collapses or expands the written hints hint field.",
            "clear": "Wipes the stored hints payload from the card metadata irrevocably.",
            "refresh": "Forces the UI renderer to re-parse the current card data from scratch.",
            "show-json": "Reveals debugging panel showing internal JSON storage data for the note."
        }
        for key, label in shortcut_labels.items():
            edit = QLineEdit()
            edit.setPlaceholderText("e.g. 1")
            edit.setFixedWidth(50)
            edit.setToolTip(shortcut_tooltips.get(key, ""))
            self.shortcut_edits[key] = edit
            short_layout.addRow(label, edit)
        
        self.shortcuts_tab.setLayout(short_layout)
        return self.shortcuts_tab
