# -*- coding: utf-8 -*-

import os
import re
from aqt import mw
from aqt.utils import askUser
from aqt.qt import *
from .widgets import ADDON_PACKAGE

class MobileTabMixin:
    def _create_mobile_tab(self):
        self.mobile_tab = QWidget()
        layout = QVBoxLayout(self.mobile_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        title = QLabel("<h2>Mobile & Cross-Platform Support</h2>")
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        intro = QLabel(
            "AI-Hints saves generated hints directly into card fields. "
            "To view them on mobile, you need to add a script to your card templates."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Options Group
        opt_group = QGroupBox("Mobile Display Options")
        opt_layout = QVBoxLayout(opt_group)
        
        self.mobile_emojis_cb = QCheckBox("Use Emojis instead of text labels (saves space)")
        self.mobile_emojis_cb.setToolTip("Uses 💡 and 🎯 instead of 'Show Hints' and 'Show Options'.")
        self.mobile_emojis_cb.stateChanged.connect(self.update_mobile_script_view)
        opt_layout.addWidget(self.mobile_emojis_cb)

        self.mobile_extra_cb = QCheckBox("Show extra buttons (Refresh, Show JSON)")
        self.mobile_extra_cb.setToolTip("Adds 🔄 and 📝 buttons for debugging on mobile.")
        self.mobile_extra_cb.stateChanged.connect(self.update_mobile_script_view)
        opt_layout.addWidget(self.mobile_extra_cb)

        layout.addWidget(opt_group)

        # Instructions Group
        group = QGroupBox("Template Setup")
        group_layout = QVBoxLayout(group)

        # Installation/Removal Buttons
        setup_btn_layout = QHBoxLayout()
        
        self.full_install_btn = QPushButton("One-Click Install: Setup All Note Types")
        self.full_install_btn.setToolTip("Automatically installs the script and updates all templates.\n\nNOTE: This will require a FULL SYNC (one-way) to AnkiWeb.")
        self.full_install_btn.clicked.connect(self.on_full_install)
        setup_btn_layout.addWidget(self.full_install_btn)

        self.full_remove_btn = QPushButton("Remove from All Note Types")
        self.full_remove_btn.setToolTip("Removes AI-Hints tags from all your templates.\n\nNOTE: This will require a FULL SYNC (one-way) to AnkiWeb.")
        self.full_remove_btn.clicked.connect(self.on_full_remove)
        setup_btn_layout.addWidget(self.full_remove_btn)

        group_layout.addLayout(setup_btn_layout)

        group_layout.addSpacing(10)
        
        step_label = QLabel("<b>Manual Installation (Alternative):</b>")
        group_layout.addWidget(step_label)

        self.script_edit = QTextEdit()
        self.script_edit.setReadOnly(True)
        self.script_edit.setAcceptRichText(False)
        self.script_edit.setMinimumHeight(150)
        group_layout.addWidget(self.script_edit)

        copy_btn = QPushButton("Copy Manual Script to Clipboard")
        copy_btn.clicked.connect(self.on_copy_script)
        group_layout.addWidget(copy_btn)

        layout.addWidget(group)
        layout.addStretch()

        return self.mobile_tab

    def update_mobile_script_view(self, _=None):
        self.script_edit.setPlainText(self._get_full_template_block())

    def _get_config_js(self):
        use_emojis = self.mobile_emojis_cb.isChecked()
        show_extra = self.mobile_extra_cb.isChecked()
        return (
            "window.aiHintsMobileConfig = { "
            f"useEmojis: {'true' if use_emojis else 'false'}, "
            f"showExtraButtons: {'true' if show_extra else 'false'} "
            "};"
        )

    def _get_full_template_block(self):
        config_js = self._get_config_js()
        return (
            "<!-- AI-HINTS-BEGIN -->\n"
            "<ai-hints></ai-hints>\n"
            "<script>\n"
            f"{config_js}\n"
            "</script>\n"
            "<script src='_ai_hints_template.js'></script>\n"
            "<!-- AI-HINTS-END -->"
        )

    def on_copy_script(self):
        QApplication.clipboard().setText(self.script_edit.toPlainText())
        QMessageBox.information(self, "AI-Hints", "Template script copied to clipboard!")

    def on_full_install(self):
        msg = (
            "This will modify the templates of ALL your Note Types to include the AI-Hints UI. "
            "Because this changes your database structure, Anki will require a **FULL SYNC (One-Way)** "
            "to AnkiWeb the next time you sync.\n\n"
            "Do you want to continue?"
        )
        if not askUser(msg):
            return

        # 1. Sync script file
        from ..mobile_sync import sync_mobile_script
        if not sync_mobile_script():
            QMessageBox.critical(self, "AI-Hints", "Failed to sync script file to media folder.")
            return

        # 2. Inject into all templates
        new_block = self._get_full_template_block()
        count = 0
        templates_updated = 0
        
        try:
            for model in mw.col.models.all():
                model_changed = False
                for tmpl in model['tmpls']:
                    # Update Front and Back
                    for side in ['qfmt', 'afmt']:
                        old_html = tmpl[side]
                        # Check if block exists
                        if "<!-- AI-HINTS-BEGIN -->" in old_html:
                            # Replace existing block
                            pattern = r"<!-- AI-HINTS-BEGIN -->.*?<!-- AI-HINTS-END -->"
                            new_html = re.sub(pattern, new_block, old_html, flags=re.DOTALL)
                            if new_html != old_html:
                                tmpl[side] = new_html
                                model_changed = True
                                templates_updated += 1
                        else:
                            # Append to end
                            tmpl[side] = old_html + "\n\n" + new_block
                            model_changed = True
                            templates_updated += 1
                
                if model_changed:
                    mw.col.models.save(model)
                    count += 1
            
            if count > 0:
                # Force Anki to recognize structural changes for sync
                mw.col.set_mod()
                if hasattr(mw, "requireReset"):
                    mw.requireReset()
            
            QMessageBox.information(
                self, 
                "AI-Hints", 
                f"Successfully updated {count} note types ({templates_updated} cards)!\n\n"
                "IMPORTANT: You must now SYNC and choose 'Upload to AnkiWeb' when prompted."
            )
        except Exception as e:
            QMessageBox.critical(self, "AI-Hints", f"Error during template installation: {e}")

    def on_full_remove(self):
        msg = (
            "This will REMOVE the AI-Hints UI tags from ALL your Note Types. "
            "Because this changes your database structure, Anki will require a **FULL SYNC (One-Way)** "
            "to AnkiWeb the next time you sync.\n\n"
            "Do you want to continue?"
        )
        if not askUser(msg):
            return

        count = 0
        pattern = r"(\n\n)?<!-- AI-HINTS-BEGIN -->.*?<!-- AI-HINTS-END -->"
        
        try:
            for model in mw.col.models.all():
                model_changed = False
                for tmpl in model['tmpls']:
                    for side in ['qfmt', 'afmt']:
                        old_html = tmpl[side]
                        if "<!-- AI-HINTS-BEGIN -->" in old_html:
                            new_html = re.sub(pattern, "", old_html, flags=re.DOTALL)
                            if new_html != old_html:
                                tmpl[side] = new_html.strip()
                                model_changed = True
                
                if model_changed:
                    mw.col.models.save(model)
                    count += 1
            
            if count > 0:
                mw.col.set_mod()
                if hasattr(mw, "requireReset"):
                    mw.requireReset()

            QMessageBox.information(
                self, 
                "AI-Hints", 
                f"Successfully removed AI-Hints from {count} note types!\n\n"
                "IMPORTANT: You must now SYNC and choose 'Upload to AnkiWeb' when prompted."
            )
        except Exception as e:
            QMessageBox.critical(self, "AI-Hints", f"Error during template removal: {e}")
