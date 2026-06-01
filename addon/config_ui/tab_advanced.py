from aqt import mw
from aqt.qt import *

class AdvancedTabMixin:
    def _create_advanced_tab(self):
        """Constructs the Tab 3: Advanced UI"""
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()

        # System Prompt (at top)
        adv_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setToolTip("Customize the core AI persona instructions defining generation constraints, math syntaxes, and output layout.")
        adv_layout.addWidget(self.system_prompt_edit)

        # Migration Section
        mig_group = QGroupBox("Migration Tools")
        mig_layout = QVBoxLayout()
        mig_layout.addWidget(QLabel("AI-Hints now saves data exclusively to the <b>first field</b> of every card to ensure visibility on the front side."))
        
        self.migrate_btn = QPushButton("🚀 Move all AI data to the first field")
        self.migrate_btn.setToolTip("Searches all fields in your entire collection and moves any AI-Hints data blocks to the first field of the note.")
        self.migrate_btn.setStyleSheet("padding: 4px 10px;")
        self.migrate_btn.clicked.connect(self.on_migrate_data)
        
        mig_btn_layout = QHBoxLayout()
        mig_btn_layout.addStretch()
        mig_btn_layout.addWidget(self.migrate_btn)
        mig_layout.addLayout(mig_btn_layout)
        
        mig_group.setLayout(mig_layout)
        adv_layout.addWidget(mig_group)

        # Maintenance Section
        maint_group = QGroupBox("Maintenance Tools")
        maint_layout = QVBoxLayout()
        maint_layout.addWidget(QLabel("Scan for and clean up orphaned/empty hints that no longer correspond to any cards (e.g. if you removed a cloze deletion)."))
        
        self.clean_orphans_btn = QPushButton("🧹 Scan & Clean Orphaned Hints")
        self.clean_orphans_btn.setToolTip("Scans all cards to detect AI hints that do not correspond to any active cards and list them to remove that data.")
        self.clean_orphans_btn.setStyleSheet("padding: 4px 10px;")
        self.clean_orphans_btn.clicked.connect(self.on_scan_orphans)
        
        clean_btn_layout = QHBoxLayout()
        clean_btn_layout.addStretch()
        clean_btn_layout.addWidget(self.clean_orphans_btn)
        maint_layout.addLayout(clean_btn_layout)

        maint_layout.addWidget(QLabel("Convert all legacy unicode escape codes (like \\u0d38) into readable characters and pretty-print existing card JSON blocks."))
        
        self.format_unicode_btn = QPushButton("📝 Convert Unicode Escapes to Normal Text")
        self.format_unicode_btn.setToolTip("Scan your entire collection and convert legacy JSON blocks with hex escapes (e.g. \\uXXXX) into clean, pretty-printed readable text.")
        self.format_unicode_btn.setStyleSheet("padding: 4px 10px;")
        self.format_unicode_btn.clicked.connect(self.on_convert_unicode_escapes)
        
        unicode_btn_layout = QHBoxLayout()
        unicode_btn_layout.addStretch()
        unicode_btn_layout.addWidget(self.format_unicode_btn)
        maint_layout.addLayout(unicode_btn_layout)
        
        maint_group.setLayout(maint_layout)
        adv_layout.addWidget(maint_group)

        # Model Blacklist Management Group
        blacklist_group = QGroupBox("Model Cooldowns & Blacklist")
        blacklist_layout = QVBoxLayout()
        blacklist_layout.addWidget(QLabel("When an AI model fails or hits a rate limit, it is temporarily blacklisted to avoid repeated failures. You can view and clear them here."))
        
        # Cooldown duration setting
        cooldown_setting_layout = QHBoxLayout()
        cooldown_setting_layout.addWidget(QLabel("Default Failure Cooldown (Minutes):"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 1440)  # 1 minute to 24 hours
        self.cooldown_spin.setToolTip("Set the standard duration a model is disabled for after experiencing a failure or rate limit.")
        cooldown_setting_layout.addWidget(self.cooldown_spin)
        cooldown_setting_layout.addStretch()
        blacklist_layout.addLayout(cooldown_setting_layout)

        self.blacklist_list = QListWidget()
        self.blacklist_list.setMinimumHeight(120)
        blacklist_layout.addWidget(self.blacklist_list)
        
        bl_btn_layout = QHBoxLayout()
        self.remove_bl_btn = QPushButton("Remove Selected")
        self.remove_bl_btn.setToolTip("Immediately clears the cooldown for the selected model so it can be attempted again.")
        self.remove_bl_btn.clicked.connect(self.on_remove_selected_blacklist)
        
        self.clear_bl_btn = QPushButton("Clear All Cooldowns")
        self.clear_bl_btn.setToolTip("Clears cooldowns/blacklist for all models.")
        self.clear_bl_btn.clicked.connect(self.on_clear_all_blacklist)
        
        bl_btn_layout.addWidget(self.remove_bl_btn)
        bl_btn_layout.addWidget(self.clear_bl_btn)
        bl_btn_layout.addStretch()
        blacklist_layout.addLayout(bl_btn_layout)
        
        blacklist_group.setLayout(blacklist_layout)
        adv_layout.addWidget(blacklist_group)

        # Raw Editor Toggle
        self.raw_toggle = QPushButton("Show Raw JSON Editor")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setToolTip("Directly inspect and write the raw serialization JSON for fine-grained control.")
        self.raw_toggle.setStyleSheet("padding: 4px 10px;")
        
        raw_btn_layout = QHBoxLayout()
        raw_btn_layout.addStretch()
        raw_btn_layout.addWidget(self.raw_toggle)
        adv_layout.addLayout(raw_btn_layout)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)
        
        adv_layout.addStretch()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setLayout(adv_layout)
        scroll.setWidget(scroll_content)
        
        main_layout = QVBoxLayout(self.advanced_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
        
        return self.advanced_tab

    def refresh_blacklist_list(self):
        if not hasattr(self, "blacklist_list"):
            return
        self.blacklist_list.clear()
        import time
        from ..ai_client import FAILED_MODELS_CACHE
        now = time.time()
        
        expired_keys = []
        for (provider, model), expiry in list(FAILED_MODELS_CACHE.items()):
            remaining = expiry - now
            if remaining <= 0:
                expired_keys.append((provider, model))
                continue
            
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            if mins > 60:
                hours = mins // 60
                mins = mins % 60
                time_str = f"{hours}h {mins}m remaining"
            else:
                time_str = f"{mins}m {secs}s remaining"
                
            item_text = f"{provider.capitalize()} - {model} ({time_str})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemData.UserRole, (provider, model))
            self.blacklist_list.addItem(item)
            
        if expired_keys:
            for k in expired_keys:
                if k in FAILED_MODELS_CACHE:
                    del FAILED_MODELS_CACHE[k]
            self._save_blacklist_locally()

    def _save_blacklist_locally(self):
        try:
            from ..ai_client import BLACKLIST_FILE, FAILED_MODELS_CACHE
            import json
            serializable = {f"{p}|{m}": e for (p, m), e in FAILED_MODELS_CACHE.items()}
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable, f)
        except Exception:
            pass

    def on_remove_selected_blacklist(self):
        curr_item = self.blacklist_list.currentItem()
        if not curr_item:
            return
            
        data = curr_item.data(Qt.ItemData.UserRole)
        if data:
            provider, model = data
            from ..ai_client import FAILED_MODELS_CACHE
            from ..logger import tooltip
            if (provider, model) in FAILED_MODELS_CACHE:
                del FAILED_MODELS_CACHE[(provider, model)]
                self._save_blacklist_locally()
                tooltip(f"Cleared cooldown for {provider.capitalize()} - {model}")
                self.refresh_blacklist_list()
                
    def on_clear_all_blacklist(self):
        from ..ai_client import FAILED_MODELS_CACHE
        from ..logger import tooltip
        if FAILED_MODELS_CACHE:
            FAILED_MODELS_CACHE.clear()
            self._save_blacklist_locally()
            tooltip("Cleared all model cooldowns/blacklist")
            self.refresh_blacklist_list()
