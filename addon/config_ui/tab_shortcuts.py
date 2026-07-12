from aqt.qt import *

class ShortcutsTabMixin:
    def _create_shortcuts_tab(self):
        """Constructs the Tab 4: Shortcuts UI"""
        self.shortcuts_tab = QWidget()
        short_layout = QFormLayout()
        
        # Helper to construct multiple checkbox modifiers row
        def create_modifiers_row():
            container = QWidget()
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            
            ctrl_cb = QCheckBox("Ctrl")
            alt_cb = QCheckBox("Alt")
            shift_cb = QCheckBox("Shift")
            meta_cb = QCheckBox("Meta")
            
            layout.addWidget(ctrl_cb)
            layout.addWidget(alt_cb)
            layout.addWidget(shift_cb)
            layout.addWidget(meta_cb)
            layout.addStretch()
            container.setLayout(layout)
            return container, (ctrl_cb, alt_cb, shift_cb, meta_cb)

        # 1. Primary Shortcuts Modifiers
        self.modifier_container, (self.mod_ctrl, self.mod_alt, self.mod_shift, self.mod_meta) = create_modifiers_row()
        short_layout.addRow("Shortcut Modifier(s):", self.modifier_container)
        
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
        
        # 2. Options Selection Modifiers
        self.opt_modifier_container, (self.opt_ctrl, self.opt_alt, self.opt_shift, self.opt_meta) = create_modifiers_row()
        short_layout.addRow("Select Options Modifier(s):", self.opt_modifier_container)
        
        self.select_options_keys_edit = QLineEdit()
        self.select_options_keys_edit.setPlaceholderText("e.g. 1-9")
        self.select_options_keys_edit.setFixedWidth(50)
        self.select_options_keys_edit.setToolTip("Keys to select corresponding options in order (1 for 1st, 2 for 2nd, etc.). Defaults to 1-9.")
        short_layout.addRow("Select Options Keys:", self.select_options_keys_edit)

        # Collision Info Label
        collision_label = QLabel(
            "<b>Shortcut Collision Recommendations:</b><br/>"
            "• <b>ctrl+shift:</b> Recommended / safest combination for option selection. Zero conflicts with Anki or standard Linux window managers.<br/>"
            "• <b>ctrl:</b> Conflicted. Ctrl+1-4 conflicts with card flag sets in Anki.<br/>"
            "• <b>alt:</b> Conflicted. Matches default system triggers (Alt + 1-6).<br/>"
            "• <b>meta:</b> Conflicted. Super/Windows key triggers dock window launches on Linux.<br/>"
            "• <b>none / shift:</b> Conflicts with raw keyboard entry, space ratings, or key symbols."
        )
        collision_label.setWordWrap(True)
        collision_label.setStyleSheet("color: #555; font-size: 11px; margin-top: 8px;")
        short_layout.addRow(collision_label)

        self.shortcuts_tab.setLayout(short_layout)
        return self.shortcuts_tab
