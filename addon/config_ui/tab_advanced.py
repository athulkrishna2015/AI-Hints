from aqt import mw
from aqt.qt import *

class AdvancedTabMixin:
    def _create_advanced_tab(self):
        """Constructs the Tab 3: Advanced UI"""
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()
        
        # 0. System Prompt (at top)
        adv_layout.addWidget(QLabel("Additional System Instructions (Appended to Default Prompt):"))
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setToolTip("Enter custom instructions, formatting rules, or prompt adjustments to append to the default system prompt.")
        adv_layout.addWidget(self.system_prompt_edit)

        # 2. Model failure/blacklist management
        blacklist_group = QGroupBox("Model Cooldowns & Blacklist")
        blacklist_layout = QVBoxLayout()
        
        bl_info = QLabel("Models that fail repeatedly are temporarily blacklisted to prevent lag.")
        bl_info.setWordWrap(True)
        bl_info.setStyleSheet("color: #666; font-size: 11px;")
        blacklist_layout.addWidget(bl_info)
        
        # Sort options row
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort By:"))
        self.blacklist_sort_cb = QComboBox()
        self.blacklist_sort_cb.addItems(["Name", "Time Remaining (Descending)", "Time Remaining (Ascending)", "Failure Streak"])
        self.blacklist_sort_cb.currentTextChanged.connect(self.refresh_blacklist_list)
        sort_layout.addWidget(self.blacklist_sort_cb)
        sort_layout.addStretch()
        blacklist_layout.addLayout(sort_layout)

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
        self.cooldown_spin.setValue(10)
        cooldown_row.addWidget(self.cooldown_spin)
        cooldown_row.addStretch()
        blacklist_layout.addLayout(cooldown_row)
        
        # Request Timeout setting
        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel("API Request Timeout (seconds):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 300)
        self.timeout_spin.setToolTip("Set the timeout limit (in seconds) for API requests to the AI providers during active review or manual generation.")
        timeout_row.addWidget(self.timeout_spin)
        
        timeout_row.addWidget(QLabel("Pregen Timeout (seconds):"))
        self.pregen_timeout_spin = QSpinBox()
        self.pregen_timeout_spin.setRange(1, 300)
        self.pregen_timeout_spin.setToolTip("Set the timeout limit (in seconds) for background pre-generation requests.")
        timeout_row.addWidget(self.pregen_timeout_spin)
        
        timeout_row.addStretch()
        blacklist_layout.addLayout(timeout_row)
        
        blacklist_group.setLayout(blacklist_layout)
        adv_layout.addWidget(blacklist_group)

        # 3. Visual Styling Group
        style_group = QGroupBox("Visual Styling")
        style_layout = QFormLayout()
        
        self.font_size_combo = QComboBox()
        self.font_size_combo.setEditable(True)
        self.font_size_combo.addItems([
            "inherit",
            "0.75em", "0.8em", "0.85em", "0.9em", "0.95em", "1.0em", "1.1em", "1.2em",
            "12px", "13px", "14px", "15px", "16px", "18px"
        ])
        self.font_size_combo.setToolTip("Set the font size for AI hints and options.")
        style_layout.addRow("Hints Font Size:", self.font_size_combo)
        style_group.setLayout(style_layout)
        adv_layout.addWidget(style_group)
        
        # 4. Unicode and Maintenance Tools
        maint_group = QGroupBox("Maintenance Tools")
        maint_layout = QVBoxLayout()
        
        # --- Deck Scoping Row ---
        scope_layout = QHBoxLayout()
        scope_layout.addWidget(QLabel("Scope Task To:"))
        
        self.maint_deck_cb = QComboBox()
        self.maint_deck_cb.setEditable(True)
        self.maint_deck_cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.maint_deck_cb.setToolTip("Choose whether to run maintenance on a specific deck or your entire collection.")
        
        # Populate decks
        self._refresh_maint_deck_list()
        
        scope_layout.addWidget(self.maint_deck_cb, 1)
        
        self.maint_deck_refresh_btn = QPushButton("🔄")
        self.maint_deck_refresh_btn.setFixedWidth(30)
        self.maint_deck_refresh_btn.setToolTip("Refresh deck list")
        self.maint_deck_refresh_btn.clicked.connect(self._refresh_maint_deck_list)
        scope_layout.addWidget(self.maint_deck_refresh_btn)
        
        maint_layout.addLayout(scope_layout)
        maint_layout.addWidget(QLabel("<hr/>"))
        # ------------------------

        self.migrate_btn = QPushButton("📦 Migrate AI Data to First Fields")
        self.migrate_btn.setToolTip("Moves AI hints from various fields into the first field (JSON format) for all notes.")
        self.migrate_btn.clicked.connect(self.on_migrate_data)
        maint_layout.addWidget(self.migrate_btn)

        self.html_to_json_btn = QPushButton("👻 Convert HTML to Hidden JSON")
        self.html_to_json_btn.setToolTip("Finds visible HTML hint blocks and converts them into optimized, invisible JSON data to clean up your editor.")
        self.html_to_json_btn.clicked.connect(self.on_convert_html_to_json)
        maint_layout.addWidget(self.html_to_json_btn)

        self.unicode_btn = QPushButton("🔣 Convert Unicode Escapes")
        self.unicode_btn.setToolTip("Finds JSON blocks with escaped characters (e.g. \\u00e9) and converts them to readable text.")
        self.unicode_btn.clicked.connect(self.on_convert_unicode_escapes)
        maint_layout.addWidget(self.unicode_btn)

        self.maint_only_modified_cb = QCheckBox("Only scan notes modified since last clean scan")
        self.maint_only_modified_cb.setToolTip("Speeds up scanning by only checking notes edited since the last successful clean scan.")
        self.maint_only_modified_cb.setChecked(True)
        maint_layout.addWidget(self.maint_only_modified_cb)

        self.orphan_btn = QPushButton("🧹 Clean Orphaned Hints")
        self.orphan_btn.setToolTip("Finds and removes AI hint data for clozes that no longer exist on the note.")
        self.orphan_btn.clicked.connect(self.on_scan_orphans)
        maint_layout.addWidget(self.orphan_btn)
        
        self.purge_json_btn = QPushButton("🗑️ Purge Naked JSON Blocks")
        self.purge_json_btn.setToolTip("Removes raw AI JSON that was accidentally pasted into fields without the div wrapper.")
        self.purge_json_btn.clicked.connect(self.on_clean_naked_json)
        maint_layout.addWidget(self.purge_json_btn)
        
        self.clear_pregen_btn = QPushButton("🧹 Clear Pregen Cache")
        self.clear_pregen_btn.setToolTip("Removes all pre-generated hints from the disk cache. Useful if you want to start fresh or clear space.")
        self.clear_pregen_btn.clicked.connect(self.on_clear_pregen_cache)
        maint_layout.addWidget(self.clear_pregen_btn)
        
        maint_group.setLayout(maint_layout)
        adv_layout.addWidget(maint_group)

        # 5. Raw Editor Toggle
        self.raw_toggle = QPushButton("Show Raw JSON Editor")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setToolTip("Directly inspect and write the raw serialization JSON for fine-grained control.")
        
        raw_btn_layout = QHBoxLayout()
        raw_btn_layout.addStretch()
        raw_btn_layout.addWidget(self.raw_toggle)
        adv_layout.addLayout(raw_btn_layout)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)

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

    def _refresh_maint_deck_list(self):
        """Populates the maintenance deck combo box with Entire Collection + current decks."""
        try:
            current_text = self.maint_deck_cb.currentText()
            self.maint_deck_cb.clear()
            self.maint_deck_cb.addItem("🌍 Entire Collection")
            
            all_decks = sorted(mw.col.decks.all_names())
            self.maint_deck_cb.addItems(all_decks)
            
            if current_text in all_decks or current_text == "🌍 Entire Collection":
                self.maint_deck_cb.setCurrentText(current_text)
            
            # Setup completer
            completer = QCompleter(["🌍 Entire Collection"] + all_decks, self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self.maint_deck_cb.setCompleter(completer)
        except: pass

    def _get_maint_search_query(self):
        """Returns the search query based on selected deck scope."""
        selected = self.maint_deck_cb.currentText().strip()
        if not selected or "Entire Collection" in selected:
            return ""
        return f'deck:"{selected}"'

    def refresh_blacklist_list(self):
        if not hasattr(self, "blacklist_list"):
            return
        self.blacklist_list.clear()
        import time
        from ..ai_client import FAILED_COMBOS_CACHE, RATE_LIMIT_STREAK, load_blacklist

        # Always reload from disk to stay in sync with background failures
        load_blacklist()

        now = time.time()
        
        expired_combos = [
            key for key, expiry in FAILED_COMBOS_CACHE.items()
            if expiry <= now
        ]
        for key in expired_combos:
            del FAILED_COMBOS_CACHE[key]

        # Fetch current sorting preference from UI
        sort_mode = "Name"
        if hasattr(self, "blacklist_sort_cb"):
            sort_mode = self.blacklist_sort_cb.currentText()

        combos_list = list(set(FAILED_COMBOS_CACHE) | set(RATE_LIMIT_STREAK))

        if sort_mode == "Time Remaining (Descending)":
            # Expiry descending. Put items without cooldown (None) at the bottom.
            def get_descending_key(key):
                exp = FAILED_COMBOS_CACHE.get(key)
                return (exp if exp is not None else 0.0, key[0].casefold(), key[1].casefold(), key[2].casefold())
            all_combos = sorted(combos_list, key=get_descending_key, reverse=True)
        elif sort_mode == "Time Remaining (Ascending)":
            # Expiry ascending. Put items without cooldown (None) at the bottom.
            def get_ascending_key(key):
                exp = FAILED_COMBOS_CACHE.get(key)
                return (exp if exp is not None else float('inf'), key[0].casefold(), key[1].casefold(), key[2].casefold())
            all_combos = sorted(combos_list, key=get_ascending_key)
        elif sort_mode == "Failure Streak":
            # Sort by streak descending, then alphabetically
            def get_streak_key(key):
                streak = RATE_LIMIT_STREAK.get(key, 0)
                return (-streak, key[0].casefold(), key[1].casefold(), key[2].casefold())
            all_combos = sorted(combos_list, key=get_streak_key)
        else:
            # Default sorting: Name/Alphabetical
            all_combos = sorted(
                combos_list,
                key=lambda key: (key[0].casefold(), key[1].casefold(), key[2].casefold()),
            )
        for provider, model, api_key in all_combos:
            expiry = FAILED_COMBOS_CACHE.get((provider, model, api_key))
            streak = RATE_LIMIT_STREAK.get((provider, model, api_key), 0)

            if expiry is not None:
                remaining = max(0, expiry - now)
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                if mins >= 60:
                    hours = mins // 60
                    mins = mins % 60
                    status = f"{hours}h {mins}m remaining"
                else:
                    status = f"{mins}m {secs}s remaining"
            else:
                status = "not on cooldown"

            preview = api_key[-6:] if len(api_key) > 6 else api_key
            if not preview:
                preview = "empty key"
            streak_text = f", failure streak {streak}" if streak else ""
            item_text = f"Combo: {provider.capitalize()} - {model} (Key: ...{preview}) ({status}{streak_text})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, ("combo", provider, model, api_key))
            self.blacklist_list.addItem(item)
            
        if expired_combos:
            self._save_blacklist_locally()

    def _save_blacklist_locally(self):
        try:
            from ..ai_client import save_blacklist
            save_blacklist()
        except Exception:
            pass

    def on_remove_selected_blacklist(self):
        curr_item = self.blacklist_list.currentItem()
        if not curr_item:
            return
            
        data = curr_item.data(Qt.ItemDataRole.UserRole)
        if data and isinstance(data, tuple) and len(data) == 4:
            type_tag, provider, model, api_key = data
            if type_tag == "combo":
                from ..ai_client import FAILED_COMBOS_CACHE, RATE_LIMIT_STREAK
                from ..logger import tooltip
                
                key = (provider, model, api_key)
                if key in FAILED_COMBOS_CACHE:
                    del FAILED_COMBOS_CACHE[key]
                if key in RATE_LIMIT_STREAK:
                    del RATE_LIMIT_STREAK[key]
                
                preview = api_key[-6:] if len(api_key) > 6 else api_key
                if not preview:
                    preview = "empty key"
                tooltip(f"Cleared cooldown and streak for {provider.capitalize()} - {model} (Key: ...{preview})")
                
                self._save_blacklist_locally()
                self.refresh_blacklist_list()
                
    def on_clear_all_blacklist(self):
        from ..ai_client import FAILED_COMBOS_CACHE, RATE_LIMIT_STREAK
        from ..logger import tooltip
        if FAILED_COMBOS_CACHE or RATE_LIMIT_STREAK:
            FAILED_COMBOS_CACHE.clear()
            RATE_LIMIT_STREAK.clear()
            self._save_blacklist_locally()
            tooltip("Cleared all model combos, cooldowns, and streaks")
            self.refresh_blacklist_list()
