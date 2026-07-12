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
        
        # Option Selection Keys Section
        short_layout.addRow(QLabel("--- MCQ Option Selection Keys ---"))
        
        self.select_options_modifier_cb = QComboBox()
        self.select_options_modifier_cb.addItems(["ctrl", "alt", "shift", "meta", "none"])
        self.select_options_modifier_cb.setToolTip("Modifier key to select MCQ options on the question/front side.")
        short_layout.addRow("Select Options Modifier:", self.select_options_modifier_cb)
        
        self.select_options_keys_edit = QLineEdit()
        self.select_options_keys_edit.setPlaceholderText("e.g. 1-9")
        self.select_options_keys_edit.setFixedWidth(50)
        self.select_options_keys_edit.setToolTip("Keys to select corresponding options in order (1 for 1st, 2 for 2nd, etc.). Defaults to 1-9.")
        short_layout.addRow("Select Options Keys:", self.select_options_keys_edit)

        # Collision Info Label
        collision_label = QLabel(
            "<b>Shortcut Collision Recommendations:</b><br/>"
            "• <b>ctrl:</b> Recommended / safest. Zero conflicts with Anki or standard Linux window managers.<br/>"
            "• <b>alt:</b> Highly conflicted. Matches default AI-Hints system triggers (Alt + 1-6).<br/>"
            "• <b>meta:</b> Highly conflicted. Super/Windows key triggers dock window launches on Linux.<br/>"
            "• <b>none / shift:</b> Conflicts with raw keyboard entry, space ratings, or key symbols."
        )
        collision_label.setWordWrap(True)
        collision_label.setStyleSheet("color: #555; font-size: 11px; margin-top: 8px;")
        short_layout.addRow(collision_label)

        self.shortcuts_tab.setLayout(short_layout)
        return self.shortcuts_tab
