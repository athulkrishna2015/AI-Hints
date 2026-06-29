# -*- coding: utf-8 -*-

import os
import re
from aqt import mw
from aqt.qt import *
from .widgets import ADDON_PACKAGE
from ..logger import logger

class MobileTabMixin:
    def _create_mobile_tab(self):
        self.mobile_tab = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        title = QLabel("<h2>Mobile & Cross-Platform Support</h2>")
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        intro = QLabel(
            "AI-Hints supports AnkiDroid and AnkiMobile by saving data directly into your cards. "
            "Use the <b>One-Click Install</b> below to automatically set up your templates "
            "for all note types."
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
        self.full_install_btn.setToolTip("Automatically installs the script and updates all templates.")
        self.full_install_btn.clicked.connect(self.on_full_install)
        setup_btn_layout.addWidget(self.full_install_btn)

        self.full_remove_btn = QPushButton("Remove from All Note Types")
        self.full_remove_btn.setToolTip("Removes AI-Hints tags from all your templates.")
        self.full_remove_btn.clicked.connect(self.on_full_remove)
        setup_btn_layout.addWidget(self.full_remove_btn)

        group_layout.addLayout(setup_btn_layout)

        # Status feedback label instead of annoying modal popups
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 11px; margin-top: 4px; padding: 4px;")
        group_layout.addWidget(self.status_label)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setLayout(layout)
        scroll.setWidget(scroll_content)
        
        main_layout = QVBoxLayout(self.mobile_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        return self.mobile_tab

    def update_mobile_script_view(self, _=None):
        self.script_edit.setPlainText(self._get_full_template_block())

    def _get_config_js(self):
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        shortcuts = config.get("shortcuts", {})
        import json
        shortcuts_json = json.dumps(shortcuts)
        use_emojis = self.mobile_emojis_cb.isChecked()
        show_extra = self.mobile_extra_cb.isChecked()
        do_not_collapse = config.get("do_not_auto_collapse", False)
        return (
            "window.aiHintsMobileConfig = { "
            f"useEmojis: {'true' if use_emojis else 'false'}, "
            f"showExtraButtons: {'true' if show_extra else 'false'}, "
            f"doNotAutoCollapse: {'true' if do_not_collapse else 'false'}, "
            f"shortcuts: {shortcuts_json} "
            "};"
        )

    def _get_full_template_block(self, field_name: str = None, template_html: str = "", is_cloze: bool = False, is_front: bool = False):
        config_js = self._get_config_js()
        
        should_inject = False
        if field_name:
            if is_cloze and is_front:
                # Always inject hidden cloze:field_name on the Front side of Cloze cards
                # to bypass AnkiDroid's raw field cloze leakage protection.
                should_inject = True
            elif template_html:
                has_field_tag = (
                    f"{{{{{field_name}}}}}" in template_html or
                    f":{field_name}}}" in template_html or
                    f"cloze:{field_name}" in template_html
                )
                if not has_field_tag:
                    should_inject = True
            else:
                should_inject = True
                    
        field_expr = f"cloze:{field_name}" if (is_cloze and is_front) else field_name
        field_tag = f'<div style="display:none;">{{{{{field_expr}}}}}</div>' if should_inject else ""
        return (
            "<!-- AI-HINTS-BEGIN -->\n"
            f"{field_tag}\n"
            "<ai-hints></ai-hints>\n"
            "<script>\n"
            f"{config_js}\n"
            "</script>\n"
            "<script src='_ai_hints_template.js'></script>\n"
            "<!-- AI-HINTS-END -->"
        )

    def on_copy_script(self):
        # Determine the likely target field for the manual script preview
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        # Determine default storage field (best guess: first field of first model)
        field_name = "AI Hints"
        if mw.col and mw.col.models.all():
            m = mw.col.models.all()[0]
            if m.get("flds"):
                field_name = m["flds"][0]["name"]
        
        QApplication.clipboard().setText(self._get_full_template_block(field_name))
        QMessageBox.information(self, "AI-Hints", "Template script copied to clipboard!")

    def on_full_install(self):
        # 1. Sync script file
        from ..mobile_sync import sync_mobile_script
        if not sync_mobile_script():
            QMessageBox.critical(self, "AI-Hints", "Failed to sync script file to media folder.")
            return

        # Update flag
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        config["mobile_setup_completed"] = True
        from ..config_io import write_pretty_config
        write_pretty_config(ADDON_PACKAGE, config)

        # 2. Inject into all templates
        count = 0
        templates_updated = 0
        
        try:
            for model in mw.col.models.all():
                model_changed = False
                
                # We now always use the first field to ensure it is rendered on front
                if not model['flds']:
                    continue
                field_name = model['flds'][0]['name']

                pattern = r"<!-- AI-HINTS-BEGIN -->.*?<!-- AI-HINTS-END -->"
                is_cloze = (model.get('type') == 1)
                for tmpl in model['tmpls']:
                    # Update Front and Back
                    for side in ['qfmt', 'afmt']:
                        old_html = tmpl[side]
                        clean_html = re.sub(pattern, "", old_html, flags=re.DOTALL)
                        new_block = self._get_full_template_block(
                            field_name, clean_html, is_cloze=is_cloze, is_front=(side == 'qfmt')
                        )
                        # Check if block exists
                        if "<!-- AI-HINTS-BEGIN -->" in old_html:
                            # Replace existing block
                            new_html = re.sub(pattern, new_block, old_html, flags=re.DOTALL)
                            if new_html != old_html:
                                tmpl[side] = new_html
                                model_changed = True
                                templates_updated += 1
                        else:
                            # Append to end
                            tmpl[side] = old_html.strip() + "\n\n" + new_block
                            model_changed = True
                            templates_updated += 1
                
                if model_changed:
                    if hasattr(mw.col.models, "update_dict"):
                        mw.col.models.update_dict(model)
                    else:
                        mw.col.models.save(model)
                    count += 1
            
            if count > 0:
                if hasattr(mw.col, "set_modified"):
                    mw.col.set_modified()
                elif hasattr(mw.col, "mark_dirty"):
                    mw.col.mark_dirty()
            
            self.status_label.setStyleSheet("color: #28a745; font-weight: bold; font-size: 11px;")
            self.status_label.setText(
                f"✅ Successfully updated {count} note types ({templates_updated} cards)!\n"
                "🔄 Triggering AnkiWeb Sync to apply changes to mobile..."
            )
            QTimer.singleShot(8000, lambda: self.status_label.setText(""))
            
            if count > 0 and hasattr(mw, "onSync"):
                mw.onSync()
        except Exception as e:
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 11px;")
            self.status_label.setText(f"❌ Error during template installation: {e}")

    def on_full_remove(self):
        # Update flag
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        config["mobile_setup_completed"] = False
        from ..config_io import write_pretty_config
        write_pretty_config(ADDON_PACKAGE, config)

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
                    if hasattr(mw.col.models, "update_dict"):
                        mw.col.models.update_dict(model)
                    else:
                        mw.col.models.save(model)
                    count += 1
            
            # Automatically delete the _ai_hints_template.js file from media directory
            script_deleted = False
            try:
                dest_name = "_ai_hints_template.js"
                dest_path = os.path.join(mw.col.media.dir(), dest_name)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                    script_deleted = True
            except Exception as e:
                logger.error(f"AI-Hints auto-delete script failed: {e}")

            if count > 0 or script_deleted:
                if hasattr(mw.col, "set_modified"):
                    mw.col.set_modified()
                elif hasattr(mw.col, "mark_dirty"):
                    mw.col.mark_dirty()
            
            self.status_label.setStyleSheet("color: #fd7e14; font-weight: bold; font-size: 11px;")
            status_text = f"🧹 Successfully removed AI-Hints from {count} note types"
            if script_deleted:
                status_text += " and deleted the template script"
            status_text += "!\n🔄 Triggering AnkiWeb Sync to apply changes to mobile..."
            
            self.status_label.setText(status_text)
            QTimer.singleShot(8000, lambda: self.status_label.setText(""))
            
            # Always sync on remove to push both template changes and script deletion
            if hasattr(mw, "onSync"):
                mw.onSync()
        except Exception as e:
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 11px;")
            self.status_label.setText(f"❌ Error during template removal: {e}")
