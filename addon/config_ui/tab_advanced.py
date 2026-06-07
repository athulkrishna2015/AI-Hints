from aqt import mw
from aqt.qt import *

class AdvancedTabMixin:
    def _create_advanced_tab(self):
        """Constructs the Tab 3: Advanced UI"""
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()
        
        # 1. AI Content Storage Options
        storage_group = QGroupBox("AI Data Storage")
        storage_layout = QFormLayout()
        
        self.storage_mode_cb = QComboBox()
        self.storage_mode_cb.addItems(["JSON (Recommended)", "HTML (Legacy)"])
        self.storage_mode_cb.setToolTip("How AI hints are stored in your cards. JSON is more robust.")
        storage_layout.addRow("Storage Format:", self.storage_mode_cb)
        
        storage_group.setLayout(storage_layout)
        adv_layout.addWidget(storage_group)

        # 2. Model failure/blacklist management
        blacklist_group = QGroupBox("Model Cooldowns & Blacklist")
        blacklist_layout = QVBoxLayout()
        
        bl_info = QLabel("Models that fail repeatedly are temporarily blacklisted to prevent lag.")
        bl_info.setWordWrap(True)
        bl_info.setStyleSheet("color: #666; font-size: 11px;")
        blacklist_layout.addWidget(bl_info)
        
        self.blacklist_list = QListWidget()
        self.blacklist_list.setMinimumHeight(150)
        blacklist_layout.addWidget(self.blacklist_list)
        
        bl_btns = QHBoxLayout()
        self.clear_sel_bl_btn = QPushButton("Remove Selected")
        self.clear_sel_bl_btn.clicked.connect(self.on_remove_selected_blacklist)
        
        self.clear_all_bl_btn = QPushButton("Clear All Cooldowns")
        self.clear_all_bl_btn.clicked.connect(self.on_clear_all_blacklist)
        
        bl_btns.addWidget(self.clear_sel_bl_btn)
        bl_btns.addWidget(self.clear_all_bl_btn)
        blacklist_layout.addLayout(bl_btns)
        
        # Cooldown setting
        cooldown_row = QHBoxLayout()
        cooldown_row.addWidget(QLabel("Default Failure Lockout (mins):"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 1440)
        self.cooldown_spin.setValue(60)
        cooldown_row.addWidget(self.cooldown_spin)
        cooldown_row.addStretch()
        blacklist_layout.addLayout(cooldown_row)
        
        blacklist_group.setLayout(blacklist_layout)
        adv_layout.addWidget(blacklist_group)
        
        # 3. Unicode and Maintenance Tools
        maint_group = QGroupBox("Maintenance Tools")
        maint_layout = QVBoxLayout()
        
        self.migrate_btn = QPushButton("📦 Migrate AI Data to First Fields")
        self.migrate_btn.setToolTip("Moves AI hints from various fields into the first field (JSON format) for all notes.")
        self.migrate_btn.clicked.connect(self.on_migrate_data)
        maint_layout.addWidget(self.migrate_btn)

        self.unicode_btn = QPushButton("🔣 Convert Unicode Escapes")
        self.unicode_btn.setToolTip("Finds JSON blocks with escaped characters (e.g. \\u00e9) and converts them to readable text.")
        self.unicode_btn.clicked.connect(self.on_convert_unicode_escapes)
        maint_layout.addWidget(self.unicode_btn)

        self.orphan_btn = QPushButton("🧹 Clean Orphaned Hints")
        self.orphan_btn.setToolTip("Finds and removes AI hint data for clozes that no longer exist on the note.")
        self.orphan_btn.clicked.connect(self.on_scan_orphans)
        maint_layout.addWidget(self.orphan_btn)
        
        self.purge_json_btn = QPushButton("🗑️ Purge Naked JSON Blocks")
        self.purge_json_btn.setToolTip("Removes raw AI JSON that was accidentally pasted into fields without the div wrapper.")
        self.purge_json_btn.clicked.connect(self.on_clean_naked_json)
        maint_layout.addWidget(self.purge_json_btn)
        
        maint_group.setLayout(maint_layout)
        adv_layout.addWidget(maint_group)

        # Migration progress (hidden by default)
        self.mig_progress_box = QGroupBox("Migration Progress")
        self.mig_progress_box.setVisible(False)
        mig_p_layout = QVBoxLayout()
        self.mig_progress_bar = QProgressBar()
        mig_p_layout.addWidget(self.mig_progress_bar)
        self.mig_status_label = QLabel("Scanning collection...")
        mig_p_layout.addWidget(self.mig_status_label)
        
        self.mig_stop_btn = QPushButton("Stop Migration")
        self.mig_stop_btn.clicked.connect(self.on_stop_migration)
        mig_p_layout.addWidget(self.mig_stop_btn)
        
        self.mig_progress_box.setLayout(mig_p_layout)
        adv_layout.addWidget(self.mig_progress_box)

        adv_layout.addStretch()
        
        # Wrap in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setLayout(adv_layout)
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout(self.advanced_tab)
        main_layout.addWidget(scroll)
        
        return self.advanced_tab

    def refresh_blacklist_list(self):
        if not hasattr(self, "blacklist_list"):
            return
        self.blacklist_list.clear()
        import time
        from ..ai_client import FAILED_MODELS_CACHE, RATE_LIMIT_STREAK
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
            item.setData(Qt.ItemDataRole.UserRole, (provider, model))
            self.blacklist_list.addItem(item)
            
        if expired_keys:
            for k in expired_keys:
                if k in FAILED_MODELS_CACHE:
                    del FAILED_MODELS_CACHE[k]
                if k in RATE_LIMIT_STREAK:
                    del RATE_LIMIT_STREAK[k]
            self._save_blacklist_locally()

    def _save_blacklist_locally(self):
        try:
            from ..ai_client import BLACKLIST_FILE, FAILED_MODELS_CACHE, RATE_LIMIT_STREAK
            import json
            expiries = {f"{p}|{m}": e for (p, m), e in FAILED_MODELS_CACHE.items()}
            streaks = {f"{p}|{m}": s for (p, m), s in RATE_LIMIT_STREAK.items()}
            
            data = {
                "expiries": expiries,
                "streaks": streaks,
                "version": 2
            }
            
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    def on_remove_selected_blacklist(self):
        curr_item = self.blacklist_list.currentItem()
        if not curr_item:
            return
            
        data = curr_item.data(Qt.ItemDataRole.UserRole)
        if data:
            provider, model = data
            from ..ai_client import FAILED_MODELS_CACHE, RATE_LIMIT_STREAK
            from ..logger import tooltip
            key = (provider, model)
            if key in FAILED_MODELS_CACHE:
                del FAILED_MODELS_CACHE[key]
            if key in RATE_LIMIT_STREAK:
                del RATE_LIMIT_STREAK[key]
            
            self._save_blacklist_locally()
            tooltip(f"Cleared cooldown and streak for {provider.capitalize()} - {model}")
            self.refresh_blacklist_list()
                
    def on_clear_all_blacklist(self):
        from ..ai_client import FAILED_MODELS_CACHE, RATE_LIMIT_STREAK
        from ..logger import tooltip
        if FAILED_MODELS_CACHE or RATE_LIMIT_STREAK:
            FAILED_MODELS_CACHE.clear()
            RATE_LIMIT_STREAK.clear()
            self._save_blacklist_locally()
            tooltip("Cleared all model cooldowns and streaks")
            self.refresh_blacklist_list()
