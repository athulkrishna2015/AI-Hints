import threading
from aqt import mw
from aqt.utils import askUser
from aqt.qt import *
from ..logger import logger, info, tooltip

class BatchTabMixin:
    def _create_batch_tab(self):
        """Constructs the Tab 5: Batch Generation UI"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # -- 1. START GROUP --
        start_group = QGroupBox("Start New Batch Generation")
        s_layout = QFormLayout()

        # 🔄 Generation Method Toggle Group
        method_widget = QWidget()
        method_layout = QHBoxLayout(method_widget)
        method_layout.setContentsMargins(0,0,0,0)
        
        self.method_bg_grp = QButtonGroup(self)
        
        self.rb_local_queue = QRadioButton("Sequential Local Queue (Recommended)")
        self.rb_local_queue.setChecked(True)
        self.rb_local_queue.setToolTip("Processes cards one-by-one in the background. Supports ALL providers and honors full fallback settings. Free-tier friendly!")
        
        self.rb_native_async = QRadioButton("Native Async API (Cloud)")
        self.rb_native_async.setToolTip("Bundles requests to cloud provider. Faster, but requires paid tier/billing linked and excludes fallbacks.")
        
        self.method_bg_grp.addButton(self.rb_local_queue)
        self.method_bg_grp.addButton(self.rb_native_async)
        method_layout.addWidget(self.rb_local_queue)
        method_layout.addWidget(self.rb_native_async)
        
        s_layout.addRow("Method Type:", method_widget)
        
        # ℹ️ Info Warning label that flips based on choice
        self.batch_desc_label = QLabel("💡 Uses standard local background loop. Perfectly respects your fallback tree and works on all free keys.")
        self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        self.batch_desc_label.setWordWrap(True)
        s_layout.addRow("", self.batch_desc_label)

        # 🚀 Provider Override Selector
        self.batch_provider_cb = QComboBox()
        self.batch_provider_cb.addItem("⚡ Standard Config (Follows Fallback Matrix)")
        # Load list of active providers
        from ..ai_client import PROVIDER_ORDER
        for prov in PROVIDER_ORDER:
             self.batch_provider_cb.addItem(prov.capitalize(), prov)
        
        s_layout.addRow("Force Provider:", self.batch_provider_cb)

        # 🎯 Specific Model Override Selector
        self.batch_model_cb = QComboBox()
        self.batch_model_cb.setEditable(True)
        self.batch_model_cb.addItem("⚡ System Default (Configured Primary Model)")
        self.batch_model_cb.setToolTip("Choose a specific model to use for this batch. Leaves blank to use your configured default for the provider.")
        s_layout.addRow("Force Model:", self.batch_model_cb)
        
        # Dynamic Model Suggestions connector
        self.batch_provider_cb.currentIndexChanged.connect(self._update_batch_model_suggestions)

        # 📦 Searchable Embedded Deck Selector
        self.batch_deck_chooser = QComboBox()
        self.batch_deck_chooser.setEditable(True)
        self.batch_deck_chooser.setInsertPolicy(QComboBox.InsertPolicy.NoInsert) 
        
        # Load and Sort Deck Names
        try:
             all_decks = mw.col.decks.all_names()
             self.batch_deck_chooser.addItems(all_decks)
             # Pre-select current active deck in main window
             curr = mw.col.decks.current().get('name', '')
             if curr in all_decks:
                  self.batch_deck_chooser.setCurrentText(curr)
        except: pass

        # Enable Advanced Partial Searching (AutoComplete)
        completer = QCompleter(mw.col.decks.all_names(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains) 
        self.batch_deck_chooser.setCompleter(completer)
        
        s_layout.addRow("Source Deck:", self.batch_deck_chooser)
        
        self.batch_skip_existing_cb = QCheckBox("Skip cards that already have AI Hints generated")
        self.batch_skip_existing_cb.setChecked(True)
        s_layout.addRow(self.batch_skip_existing_cb)

        # Version-gated Batch Regeneration control
        self.batch_regen_version_cb = QCheckBox("└─ Except if Generated Version < ")
        self.batch_regen_version_cb.setStyleSheet("margin-left: 15px;")
        self.batch_regen_version_cb.setToolTip("If checked, cards with hints will still be queued for batching if their stored version is older than the target.")
        self.batch_regen_version_cb.setChecked(False)
        
        self.batch_regen_min_version_edit = QLineEdit()
        self.batch_regen_min_version_edit.setPlaceholderText("e.g. 1.4.2")
        self.batch_regen_min_version_edit.setFixedWidth(80)
        
        # Load initial default from current main config values
        self.batch_regen_min_version_edit.setText(self.config.get("auto_regenerate_min_version", ""))

        batch_version_row = QHBoxLayout()
        batch_version_row.setContentsMargins(15, 0, 0, 0)
        batch_version_row.addWidget(self.batch_regen_version_cb)
        batch_version_row.addWidget(self.batch_regen_min_version_edit)
        batch_version_row.addStretch()
        s_layout.addRow(batch_version_row)
        
        self.batch_regen_version_cb.toggled.connect(
            lambda enabled: self.batch_regen_min_version_edit.setEnabled(enabled)
        )
        self.batch_regen_min_version_edit.setEnabled(False)
        
        self.batch_skip_existing_cb.toggled.connect(
            lambda checked: self.batch_regen_version_cb.setEnabled(checked)
        )
        
        self.method_bg_grp.buttonClicked.connect(self._on_batch_method_changed)
        
        start_group.setLayout(s_layout)
        layout.addWidget(start_group)
        
        # -- 2. ACTIVE GROUP --
        active_group = QGroupBox("Running & Pending Batches")
        a_layout = QVBoxLayout()
        
        self.batch_list_view = QTextBrowser()
        self.batch_list_view.setReadOnly(True)
        self.batch_list_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.batch_list_view.setPlaceholderText("No active native batch tracking handles found.")
        self.batch_list_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.batch_list_view.setOpenExternalLinks(False)
        self.batch_list_view.anchorClicked.connect(self._on_log_link_clicked)
        a_layout.addWidget(self.batch_list_view)
        refresh_row = QHBoxLayout()
        
        # Primary Control Suite cluster
        self.batch_run_btn = QPushButton("🚀 Initiate Queue")
        self.batch_run_btn.setAutoDefault(False)
        self.batch_run_btn.setMinimumHeight(30)
        self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
        try: self.batch_run_btn.clicked.disconnect()
        except Exception: pass
        self.batch_run_btn.clicked.connect(self.on_batch_control_clicked)
        
        self.stop_local_btn = QPushButton("🛑 Stop Queue")
        self.stop_local_btn.setAutoDefault(False)
        self.stop_local_btn.setMinimumHeight(30)
        self.stop_local_btn.setStyleSheet("color: #dc3545; font-weight: bold;")
        try: self.stop_local_btn.clicked.disconnect()
        except Exception: pass
        self.stop_local_btn.clicked.connect(self.on_stop_local_queue)
 
        self.refresh_status_btn = QPushButton("🔄 Refresh Status")
        self.refresh_status_btn.setAutoDefault(False)
        self.refresh_status_btn.setMinimumHeight(30)
        try: self.refresh_status_btn.clicked.disconnect()
        except Exception: pass
        self.refresh_status_btn.clicked.connect(self.update_batch_status_tab)
        
        # Grouped Layout
        refresh_row.addWidget(self.batch_run_btn)
        refresh_row.addWidget(self.stop_local_btn)
        refresh_row.addStretch() 
        refresh_row.addWidget(self.refresh_status_btn)
        
        a_layout.addLayout(refresh_row)
        active_group.setLayout(a_layout)
        layout.addWidget(active_group)
        
        layout.addStretch()
        
        self._on_batch_method_changed()
        
        return tab

    def _update_batch_model_suggestions(self):
        """Pulls available pre-seeded list suggestions from shared constants file."""
        self.batch_model_cb.clear()
        self.batch_model_cb.addItem("⚡ System Default (Configured Primary Model)")
        
        combo_idx = self.batch_provider_cb.currentIndex()
        if combo_idx <= 0:
             return
             
        prov = self.batch_provider_cb.itemData(combo_idx)
        if prov:
             from ..ai_client import MODEL_SUGGESTIONS
             suggs = MODEL_SUGGESTIONS.get(prov, [])
             for s in suggs:
                  self.batch_model_cb.addItem(s)

    def _on_batch_method_changed(self):
        """Updates descriptions, buttons, and valid providers when toggle flips."""
        self._refresh_batch_controls()

    def _refresh_batch_controls(self):
        """Unified UI state manager for the main batch button and descriptions."""
        from ..batch_manager import batch_manager
        
        is_cloud = self.rb_native_async.isChecked()
        is_active = getattr(batch_manager, "local_queue_active", False)
        is_paused = getattr(batch_manager, "local_queue_paused", False)
        has_saved = bool(getattr(batch_manager, "local_queue", []))

        if is_cloud:
            self.batch_desc_label.setText("⚠️ Uses Cloud Native API. Requires **PAID ACCOUNT** / linked billing. Currently ONLY Gemini supports this schema. Closes fast.")
            self.batch_desc_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 11px; margin-bottom: 5px;")
            self.batch_run_btn.setText("🚀 Submit Cloud Batch")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #0d6efd; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            return

        # Local Queue Logic
        if is_active:
            if is_paused:
                self.batch_run_btn.setText("▶️ Resume Queue")
                self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #ffc107; color: black; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            else:
                self.batch_run_btn.setText("⏸️ Pause Queue")
                self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #e9ecef; color: black; border-radius: 4px; border: 1px solid #ced4da; padding-left: 10px; padding-right: 10px;")
            
            self.batch_desc_label.setText("💡 Uses standard local background loop. Perfectly respects your fallback tree, works on all free keys! (Anki must stay open)")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        
        elif has_saved:
            self.batch_run_btn.setText("⏯️ Resume Saved Queue")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #fd7e14; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            self.batch_desc_label.setText("💾 Found an unfinished offline batch from a previous session! Click below to Resume.")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        
        else:
            self.batch_run_btn.setText("🚀 Initiate Queue")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            self.batch_desc_label.setText("💡 Uses standard local background loop. Perfectly respects your fallback tree, works on all free keys! (Anki must stay open)")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")

    def update_batch_status_tab(self):
        try:
            from ..batch_manager import batch_manager
            
            # Sync Unified Button UI State
            self._refresh_batch_controls()

            summary = batch_manager.get_status_summary()
            
            # 🚦 Selection Safety: If user is currently selecting text, DO NOT update
            # as it will clear their selection and make navigation/copying impossible.
            if self.batch_list_view.textCursor().hasSelection():
                return

            if not summary:
                  self.batch_list_view.setHtml("<i>(Ready to initialize)</i>")
            else:
                  self.batch_list_view.setHtml(summary)
                  
        except Exception:
            pass

    def _on_log_link_clicked(self, qurl):
        """Intercepts clicks on anchor tags and routes to native Anki Browser actions."""
        url = qurl.toString().strip()
        if url.startswith("browse:"):
             query = url.split(":", 1)[1] 
             from aqt import dialogs
             browser = dialogs.open("Browser", mw)
             try:
                  browser.search_for(query)
             except AttributeError:
                  try:
                       browser.search(query)
                  except (AttributeError, TypeError):
                       try:
                            try: browser.form.searchEdit.lineEdit().setText(query)
                            except AttributeError: browser.form.searchEdit.setText(query)
                            try: browser.search() 
                            except (AttributeError, TypeError): browser.onSearchActivated()
                       except Exception: pass
             browser.setFocus()
             browser.activateWindow()
             browser.raise_()

    def on_batch_control_clicked(self):
        from ..batch_manager import batch_manager
        
        # 1. If active local queue, toggle pause
        if not self.rb_native_async.isChecked() and batch_manager.local_queue_active:
            new_pause = not batch_manager.local_queue_paused
            batch_manager.set_pause_local_queue(new_pause)
            tooltip("⏸️ Local Queue Paused" if new_pause else "▶️ Local Queue Resumed")
            self._refresh_batch_controls()
            return
            
        # 2. Otherwise, delegate to start logic
        self.on_start_config_batch()

    def on_stop_local_queue(self):
        from ..batch_manager import batch_manager
        if not batch_manager.local_queue_active and not batch_manager.local_queue:
             info("There is no local sequential queue currently running or saved.")
             return
        if askUser("Are you sure you want to STOP and CLEAR the local sequential queue?\n\nRemaining queued cards will be discarded."):
             batch_manager.stop_local_queue()
             self._refresh_batch_controls()
             self.update_batch_status_tab()

    def update_batch_ui_for_selection(self):
        """Called when external cards are passed into the dialog from browser."""
        if not hasattr(self, "selected_card_ids") or not self.selected_card_ids:
            return
            
        count = len(self.selected_card_ids)
        # Update Deck Chooser to reflect selection
        self.batch_deck_chooser.setEditable(True)
        self.batch_deck_chooser.lineEdit().setText(f"(Selected: {count} cards)")
        self.batch_deck_chooser.setEnabled(False)
        
        # Switch method to Local Queue by default for broad compatibility
        # unless user already specifically chose Cloud
        if not self.rb_native_async.isChecked():
            self.rb_local_queue.setChecked(True)
            self._on_batch_method_changed()

    def on_start_config_batch(self):
        from ..batch_manager import batch_manager
        
        # 1. Handle selection from browser if present
        if hasattr(self, "selected_card_ids") and self.selected_card_ids:
            source_cids = list(self.selected_card_ids)
            deck_name = "Selected Cards"
        else:
            # Traditional deck-based search
            if not self.rb_native_async.isChecked() and not batch_manager.local_queue_active and batch_manager.local_queue:
                 count = len(batch_manager.local_queue)
                 res = askUser(
                      f"💾 **UNFINISHED BATCH DETECTED**\n\n"
                      f"Found {count} cards waiting from your previous session.\n\n"
                      f"• Click 'Yes' to RESUME processing these cards.\n"
                      f"• Click 'No' to DISCARD the old queue and start a fresh batch."
                 )
                 if res:
                      started = batch_manager.start_local_sequential_queue(card_ids=None) 
                      if started:
                           self.update_batch_status_tab()
                           self._on_batch_method_changed() 
                      return
                 else:
                      batch_manager.stop_local_queue() 

            deck_name = self.batch_deck_chooser.currentText().strip()
            all_valid_decks = mw.col.decks.all_names()
            if deck_name not in all_valid_decks:
                 info(f"⚠️ Deck not found: '{deck_name}'\nPlease select a valid deck from the list.")
                 return

            if not deck_name:
                 info("Please select a deck first.")
                 return
                 
            try:
                source_cids = mw.col.find_cards(f"deck:\"{deck_name}\"")
            except Exception as e:
                logger.error(f"Deck search failed: {e}")
                source_cids = []

        try:
            if not source_cids:
                info(f"No cards found for processing ({deck_name}).")
                return
                
            if self.batch_skip_existing_cb.isChecked():
                from ..reviewer_hooks import card_has_hints, _get_card_from_collection, _card_saved_version, _version_less_than
                final_ids = []
                use_ver_gate = self.batch_regen_version_cb.isChecked()
                min_ver = self.batch_regen_min_version_edit.text().strip()
                
                skipped_count = 0
                for cid in source_cids:
                    c = _get_card_from_collection(cid)
                    if not c: continue
                    has_hints = card_has_hints(c)
                    should_process = not has_hints
                    if has_hints and use_ver_gate and min_ver:
                        saved_ver = _card_saved_version(c)
                        if _version_less_than(saved_ver, min_ver):
                            should_process = True
                    
                    if should_process:
                        final_ids.append(cid)
                    else:
                        skipped_count += 1
                        if skipped_count < 5:
                             logger.debug(f"AI-Hints Batch: Skipping card {cid} (already has hints).")
                
                logger.info(f"AI-Hints Batch Filtering: Filtered {len(source_cids)} cards -> {len(final_ids)} cards to process ({skipped_count} skipped).")
            else:
                final_ids = list(source_cids)
                
            if not final_ids:
                info("No cards need hint generation (all selected have hints already).")
                return
                
            chunked_ids = final_ids[:1000]
            excess = len(final_ids) - 1000
            
            is_native = self.rb_native_async.isChecked()
            mode_str = "Native Cloud Batch" if is_native else "Local Background Queue"
            
            confirm_msg = f"Ready to process {len(chunked_ids)} cards using **{mode_str}**."
            if excess > 0:
                confirm_msg += f"\n\n(Note: {excess} remaining skipped due to safety limits.)"
            
            if not askUser(confirm_msg + "\n\nProceed with execution?"):
                return
            
            combo_idx = self.batch_provider_cb.currentIndex()
            prov_override = None
            if combo_idx > 0:
                prov_override = self.batch_provider_cb.itemData(combo_idx)

            chosen_model = self.batch_model_cb.currentText().strip()
            model_override = None
            if chosen_model and "⚡" not in chosen_model:
                 model_override = chosen_model
            
            config = self.config.copy()
            target_prov = prov_override or config.get("ai_provider", "openai")
            
            if model_override:
                 current_models = config.get("models", {})
                 if not isinstance(current_models, dict): current_models = {}
                 else: current_models = current_models.copy() 
                 current_models[target_prov] = model_override
                 config["models"] = current_models
                 logger.info(f"Applying transient Batch Model Override: {target_prov} -> {model_override}")

            from ..ai_client import AIClient
            
            client = AIClient(config)
            if not client.has_any_ready_provider():
                 info("No configured API Keys found! Visit Provider settings first.")
                 return

            if not is_native:
                started = batch_manager.start_local_sequential_queue(
                    chunked_ids, 
                    config, 
                    provider_override=prov_override
                )
                if started:
                    QTimer.singleShot(1500, self.update_batch_status_tab)
                return

            else:
                target_prov = prov_override or "gemini"
                if target_prov != "gemini":
                    info(f"❌ Native Cloud Batch is currently NOT supported for provider '{target_prov.upper()}'.\n\nPlease either select 'Gemini' OR switch your Method back to 'Sequential Local Queue'.")
                    return
                
                from ..card_parser import CardParser
                from ..reviewer_hooks import _get_card_from_collection

                parser = CardParser(
                    config.get("storage_mode", "json")
                )
                
                items = []
                actual_cids = []
                
                for cid in chunked_ids:
                    try:
                        card = _get_card_from_collection(cid)
                        if not card: continue
                        f, b = parser.get_note_content(card.note(), card)
                        if not f and not b:
                            continue

                        items.append({
                            "key": str(cid),
                            "system_prompt": config.get("system_prompt", ""),
                            "user_prompt": f"FRONT:\n{f}\n\nBACK:\n{b}"
                        })
                        actual_cids.append(cid)
                    except: pass
                    
                if not items:
                    info("Failed to assemble content payload.")
                    return
                    
                def _bg_run():
                    try:
                        tooltip("Transmitting payload to Google...")
                        resp = client.submit_gemini_batch(items)
                        jname = resp.get("name")
                        if jname:
                            batch_manager.register_job(jname, actual_cids)
                            mw.taskman.run_on_main(lambda jn=jname: info(f"✅ Cloud Batch Initiated: {jn}\nMonitoring setup."))
                            mw.taskman.run_on_main(self.update_batch_status_tab)
                        else:
                            mw.taskman.run_on_main(lambda: info("Unknown transmission fault. No tracking ID returned."))
                    except Exception as e:
                        err_msg = str(e)
                        mw.taskman.run_on_main(lambda msg=err_msg: info(msg))
                        
                threading.Thread(target=_bg_run, daemon=True).start()
                
        except Exception as e:
            logger.error(f"Config UI Batch Start Master Error: {e}")
            info(f"Launch failed: {e}")
