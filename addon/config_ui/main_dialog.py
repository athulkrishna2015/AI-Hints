import os
import json
from aqt import mw
from aqt.utils import askUser
from aqt.qt import *
from ..logger import logger, info, tooltip
from ..ai_client import (
    DEFAULT_MODELS, 
    LEGACY_MODEL_REPLACEMENTS, 
    MODEL_FALLBACKS, 
    PROVIDER_ORDER, 
    AIClient
)

# Import Tab Mixins
from .tab_general import GeneralTabMixin
from .tab_providers import ProvidersTabMixin
from .tab_advanced import AdvancedTabMixin
from .tab_shortcuts import ShortcutsTabMixin
from .tab_batch import BatchTabMixin
from .tab_support import SupportTabMixin
from .tab_logs import LogTabMixin
from .tab_mobile import MobileTabMixin

# Import Support Widgets
from .widgets import CustomProviderDialog, ProviderRowWidget, ADDON_PACKAGE, PERSISTENT_TEST_STATUSES, FETCH_CANCELLATIONS

LAST_ACTIVE_TAB_INDEX = 7  # Fallback static state

class ConfigDialog(QDialog, GeneralTabMixin, ProvidersTabMixin, AdvancedTabMixin, 
                   ShortcutsTabMixin, BatchTabMixin, SupportTabMixin, LogTabMixin, MobileTabMixin):
    
    def __init__(self, parent, card_ids=None, deck_name=None):
        super().__init__(parent)
        self.ui_initializing = True
        self.setWindowTitle("AI-Hints Configuration")
        self.setModal(False)
        self.setMinimumSize(600, 700)
        self.addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.selected_card_ids = card_ids
        self.selected_deck_name = deck_name
        self.config = self._normalize_config(mw.addonManager.getConfig(ADDON_PACKAGE) or {})
        
        # Load default config for restoration
        try:
            with open(os.path.join(self.addon_dir, "config.json"), "r", encoding="utf-8") as f:
                self.default_config = json.load(f)
        except Exception as e:
            logger.error(f"Could not load default config: {e}")
            self.default_config = {}

        self.custom_providers_data = self.config.get("custom_providers", {}) or {}
        
        self.setup_ui()
        self.load_config_into_ui()

        self._migration_running = False
        self._migration_stop_requested = False

        # Live Log Timer
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.load_log)
        
        # Batch Status Timer
        self.batch_timer = QTimer(self)
        self.batch_timer.timeout.connect(self.update_batch_status_tab)
        
        # Provider Status Timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_provider_status)
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.ui_initializing = False
        # Defer initial tab handler so it runs AFTER the dialog is displayed.
        # Running it synchronously here would call load_log() (file I/O) on the
        # main thread during construction, causing Anki to freeze.
        QTimer.singleShot(0, lambda: self.on_tab_changed(self.tabs.currentIndex()))

    def set_selected_cards(self, card_ids):
        """External hook to pass cards from browser into the Batch tab."""
        self.selected_card_ids = card_ids
        if hasattr(self, "update_batch_ui_for_selection"):
            self.update_batch_ui_for_selection()

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        
        # Handle Log timer
        if tab_name == "Logs":
            self.load_log()
            self.log_timer.start(1000)
            if hasattr(self, "live_label"):
                self.live_label.setVisible(True)
        else:
            self.log_timer.stop()
            if hasattr(self, "live_label"):
                self.live_label.setVisible(False)
                
        # Handle Batch timer
        if tab_name == "Batch Generation":
            self.update_batch_status_tab()
            self.batch_timer.start(5000) # Update batch list every 5 seconds when viewing
        else:
            self.batch_timer.stop()

        # Handle Provider Status timer
        if tab_name == "AI Providers":
            self.update_provider_status()
            self.status_timer.start(3000) # Update status every 3 seconds
        else:
            self.status_timer.stop()

    def update_provider_status(self):
        """Refreshes the live status indicators for background daemons."""
        if not hasattr(self, "ag_status_label"):
            return

        from ..proxy_manager import proxy_manager
        if proxy_manager.is_running():
            self.ag_status_label.setText("Status: <span style='color: #28a745; font-weight: bold;'>● Running</span>")
        else:
            self.ag_status_label.setText("Status: <span style='color: #dc3545; font-weight: bold;'>○ Stopped</span>")

    def setup_ui(self):

        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        # Build Tabs using inherited Mixin methods
        general = self._create_general_tab()
        providers = self._create_providers_tab()
        advanced = self._create_advanced_tab()
        shortcuts = self._create_shortcuts_tab()
        batch = self._create_batch_tab()
        mobile = self._create_mobile_tab()
        support = self._create_support_tab()
        logs = self._create_log_tab()
        
        # Assemble Tabs in desired visual order
        self.tabs.addTab(general, "General")
        self.tabs.addTab(providers, "AI Providers")
        self.tabs.addTab(advanced, "Advanced")
        self.tabs.addTab(shortcuts, "Shortcuts")
        self.tabs.addTab(batch, "Batch Generation")
        self.tabs.addTab(mobile, "Mobile Support")
        self.tabs.addTab(support, "Support Authors")
        self.tabs.addTab(logs, "Logs")
        
        # Restore previously selected tab preference
        saved_index = self.config.get("last_active_tab", 0)
        if 0 <= saved_index < self.tabs.count():
             self.tabs.setCurrentIndex(saved_index)
        
        # Set tracking connector
        self.tabs.currentChanged.connect(self._on_tab_changed_tracker)

        layout.addWidget(self.tabs)
        
        # Bottom Action Bar
        btn_layout = QHBoxLayout()
        
        restore_btn = QPushButton("Restore Defaults")
        restore_btn.setToolTip("Restores default values ONLY for the currently selected tab.")
        restore_btn.clicked.connect(self.on_restore_current_tab)
        btn_layout.addWidget(restore_btn)

        stop_all_btn = QPushButton("🛑 Stop All")
        stop_all_btn.setToolTip("Emergency stop for all background tasks and batch generations.")
        stop_all_btn.setStyleSheet("color: white; background-color: #d9534f; font-weight: bold; padding: 3px 10px;")
        stop_all_btn.clicked.connect(self.emergency_stop)
        btn_layout.addWidget(stop_all_btn)

        btn_layout.addStretch()
        
        save_only_btn = QPushButton("Save")
        save_only_btn.setToolTip("Saves configuration without closing the window.")
        save_only_btn.clicked.connect(lambda: self.save_config(close=False))
        btn_layout.addWidget(save_only_btn)

        save_close_btn = QPushButton("Save && Close")
        save_close_btn.clicked.connect(lambda: self.save_config(close=True))
        save_close_btn.setDefault(True)
        btn_layout.addWidget(save_close_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

        # Migration Progress Section (Hidden by default)
        self.mig_progress_box = QGroupBox("Collection Migration Progress")
        self.mig_progress_box.setVisible(False)
        mig_prog_layout = QVBoxLayout()
        
        self.mig_progress_bar = QProgressBar()
        self.mig_progress_bar.setRange(0, 100)
        mig_prog_layout.addWidget(self.mig_progress_bar)
        
        mig_status_layout = QHBoxLayout()
        self.mig_status_label = QLabel("Scanning collection...")
        mig_status_layout.addWidget(self.mig_status_label)
        
        mig_status_layout.addStretch()
        
        self.mig_stop_btn = QPushButton("🛑 Stop Migration")
        self.mig_stop_btn.clicked.connect(self.stop_migration)
        mig_status_layout.addWidget(self.mig_stop_btn)
        
        mig_prog_layout.addLayout(mig_status_layout)
        self.mig_progress_box.setLayout(mig_prog_layout)
        layout.addWidget(self.mig_progress_box)

        self.setLayout(layout)

        # Apply initial selection if any
        if self.selected_card_ids:
            QTimer.singleShot(100, self.update_batch_ui_for_selection)

    def load_config_into_ui(self):
        c = self.config
        self.refresh_custom_list()
        self.ai_provider_cb.setCurrentText(c.get("ai_provider", "openai"))
        self.options_count_sb.setValue(c.get("options_count", 4))
        self.mathjax_format_cb.setCurrentText(c.get("mathjax_format", "delimiters"))
        self.fix_latex_cb.setChecked(c.get("fix_latex", False))
        self.answer_display_position_cb.setCurrentText(c.get("answer_display_position", "between"))
        self.show_hints_cb.setChecked(c.get("show_hints_button", True))
        self.show_options_cb.setChecked(c.get("show_options_button", True))
        self.show_on_card_cb.setChecked(c.get("show_on_card", True))
        self.show_in_bottom_bar_cb.setChecked(c.get("show_in_bottom_bar", True))
        self.show_in_popup_cb.setChecked(c.get("show_in_popup", False))
        
        if hasattr(self, 'auto_clear_cb'):
            self.auto_clear_cb.setChecked(c.get("auto_clear_logs", True))
            
        self.auto_generate_new_cb.setChecked(c.get("auto_generate_new", False))
        self.auto_regenerate_all_cb.setChecked(c.get("auto_regenerate_all", False))
        self.auto_regenerate_all_cb.setEnabled(self.auto_generate_new_cb.isChecked())
        auto_gen_on = self.auto_generate_new_cb.isChecked()
        self.auto_regenerate_old_version_cb.setChecked(c.get("auto_regenerate_if_old_version", False))
        self.auto_regenerate_old_version_cb.setEnabled(auto_gen_on)
        self.auto_regenerate_min_version_edit.setText(c.get("auto_regenerate_min_version", ""))
        self.auto_regenerate_min_version_edit.setEnabled(
            auto_gen_on and self.auto_regenerate_old_version_cb.isChecked()
        )
        self.auto_regenerate_old_time_cb.setChecked(c.get("auto_regenerate_if_old_time", False))
        self.auto_regenerate_old_time_cb.setEnabled(auto_gen_on)
        self.auto_regenerate_min_time_edit.setText(c.get("auto_regenerate_min_time", ""))
        self.auto_regenerate_min_time_edit.setEnabled(
            auto_gen_on and self.auto_regenerate_old_time_cb.isChecked()
        )
        self.pre_generate_next_cb.setChecked(c.get("pre_generate_next", True))
        self.pre_generate_next_cb.setEnabled(auto_gen_on)
        self.pre_generate_count_spin.setValue(c.get("pre_generate_count", 3))
        self.pre_generate_count_spin.setEnabled(auto_gen_on and self.pre_generate_next_cb.isChecked())
        
        self.auto_show_hints_cb.setChecked(c.get("auto_show_hints", True))
        self.auto_show_options_cb.setChecked(c.get("auto_show_options", False))
        self.do_not_auto_collapse_cb.setChecked(c.get("do_not_auto_collapse", False))
        self.manual_show_hints_cb.setChecked(c.get("manual_show_hints", True))
        self.manual_show_options_cb.setChecked(c.get("manual_show_options", False))
        
        shortcuts = c.get("shortcuts", {}) or {}
        self.modifier_cb.setCurrentText(shortcuts.get("modifier", "alt"))
        for key, edit in self.shortcut_edits.items():
            edit.setText(shortcuts.get(key, ""))

        keys = c.get("api_keys", {}) or {}
        for p, edit in self.api_key_edits.items():
            edit.setText(keys.get(p, ""))
        models = c.get("models", {}) or {}
        for p, edit in self.model_edits.items():
            model_name = models.get(p, DEFAULT_MODELS.get(p, ""))
            if edit.findText(model_name) == -1:
                edit.addItem(model_name)
            edit.setCurrentText(model_name)

        # Mobile Support Tab
        self.mobile_emojis_cb.setChecked(c.get("mobile_use_emojis", False))
        self.mobile_extra_cb.setChecked(c.get("mobile_show_extra_buttons", False))
        self.update_mobile_script_view()

        # AI Provider Logic

        ag_model = models.get("antigravity", DEFAULT_MODELS.get("antigravity", ""))
        if self.ag_model_edit.findText(ag_model) == -1:
            self.ag_model_edit.addItem(ag_model)
        self.ag_model_edit.setCurrentText(ag_model)
            
        ag_cfg = c.get("antigravity_proxy", {}) or {}
        self.ag_enable_cb.setChecked(ag_cfg.get("enabled", False))
            
        self.model_fallbacks_data = c.get("model_fallbacks", {}).copy()
        disabled_models = c.get("disabled_fallback_models", {}) or {}
        if not isinstance(disabled_models, dict):
            disabled_models = {}
        self.disabled_fallback_models_data = disabled_models.copy()
        self.global_model_priority_data = list(c.get("global_model_priority", []))
        self.advanced_fallback_cb.setChecked(c.get("use_global_model_priority", False))
        self.update_fallback_ui_states()
            
        local = c.get("local_endpoint", {}) or {}
        self.local_url_edit.setText(local.get("base_url", ""))
        model_name = local.get("model", "")
        if self.local_model_edit.findText(model_name) == -1:
            self.local_model_edit.addItem(model_name)
        self.local_model_edit.setCurrentText(model_name)
        self.local_api_key_edit.setText(local.get("api_key", ""))
        self.local_fallback_cb.setChecked(local.get("enabled", False))
        
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        
        from .tab_providers import DEFAULT_TEST_QUESTION, DEFAULT_TEST_ANSWER
        self.test_question_edit.setText(c.get("test_question_front", DEFAULT_TEST_QUESTION))
        self.test_answer_edit.setText(c.get("test_question_back", DEFAULT_TEST_ANSWER))
        
        self.raw_editor.setPlainText(json.dumps(c, indent=4))
        
        if hasattr(self, "cooldown_spin"):
            self.cooldown_spin.setValue(c.get("model_cooldown_minutes", 10))
            
        if hasattr(self, "font_size_combo"):
            font_size = c.get("hints_font_size", "")
            if not font_size:
                font_size = "inherit"
            self.font_size_combo.setCurrentText(font_size)
        
        if hasattr(self, "refresh_blacklist_list"):
            self.refresh_blacklist_list()
            
        if hasattr(self, "batch_limit_spin"):
            self.batch_limit_spin.setValue(c.get("batch_limit", 1000))
        if hasattr(self, "batch_multithread_cb"):
            self.batch_multithread_cb.setChecked(c.get("multithread_providers", False))

    def copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        tooltip("Copied to clipboard")

    def refresh_custom_list(self):
        self.custom_list.clear()
        self.custom_list.addItems(self.custom_providers_data.keys())

        # 1. Determine priority order first
        custom_names = list(self.custom_providers_data.keys())
        current_priority = []
        current_models_state = {}

        if hasattr(self, 'models_layout') and self.models_layout is not None:
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget):
                    current_priority.append(w.provider)
                    current_models_state[w.provider] = w.edit.currentText()

        if not current_priority:
            current_priority = self.config.get("provider_priority", [])
            if not current_priority:
                current_priority = PROVIDER_ORDER + custom_names

        available = set(PROVIDER_ORDER + custom_names)
        new_priority = [p for p in current_priority if p in available]
        for p in PROVIDER_ORDER + custom_names:
            if p not in new_priority:
                new_priority.append(p)

        # 2. Populate Active Provider Dropdown using the calculated priority
        current_selection = self.ai_provider_cb.currentText()
        self.ai_provider_cb.clear()
        self.ai_provider_cb.addItems(new_priority)
        if current_selection:
            try: self.ai_provider_cb.setCurrentText(current_selection)
            except: pass

        # 3. Rebuild Providers Tab layout
        if hasattr(self, 'models_layout') and self.models_layout is not None:
            while self.models_layout.count():
                item = self.models_layout.takeAt(0)
                if item:
                    w = item.widget()
                    if w: w.deleteLater()

            self.model_edits = {}
            self.provider_widgets = {}
            for p in new_priority:
                w = ProviderRowWidget(p, self)
                if p in current_models_state:
                    w.edit.setCurrentText(current_models_state[p])
                elif p in self.config.get("models", {}):
                    w.edit.setCurrentText(self.config["models"][p])
                self.model_edits[p] = w.edit
                self.provider_widgets[p] = w
                self.models_layout.addWidget(w)
            
            # Link self.ag_model_edit to the newly created antigravity edit combobox
            if "antigravity" in self.model_edits:
                self.ag_model_edit = self.model_edits["antigravity"]
    def on_fetch_binary(self):
        try:
            from ..proxy_manager import proxy_manager
            self.ag_dl_progress.setRange(0, 100)
            self.ag_dl_progress.setValue(0)
            self.ag_dl_progress.setVisible(True)
            self.ag_dl_status.setText("Connecting to GitHub...")
            self.ag_dl_status.setVisible(True)
            self.ag_fetch_btn.setEnabled(False) 
            
            def _progress_hook(downloaded, total, elapsed):
                def _update_ui():
                    total_mb = total / (1024*1024)
                    done_mb = downloaded / (1024*1024)
                    rate_mb_s = (done_mb / elapsed) if elapsed > 0 else 0
                    remaining_mb = max(0, total_mb - done_mb)
                    eta_s = (remaining_mb / rate_mb_s) if rate_mb_s > 0 else 0
                    pct = int((downloaded / total) * 100) if total > 0 else 0
                    status_txt = f"{done_mb:.1f}MB / {total_mb:.1f}MB ({pct}%) @ {rate_mb_s:.1f} MB/s - ETA: {int(eta_s)}s"
                    self.ag_dl_status.setText(status_txt)
                    self.ag_dl_progress.setValue(pct)
                mw.taskman.run_on_main(_update_ui)

            def _task():
                success = False
                err_msg = ""
                try:
                    success = proxy_manager.download_binary(progress_callback=_progress_hook)
                except Exception as e:
                    err_msg = str(e)
                
                def _done():
                    if success:
                        self.ag_dl_progress.setVisible(False)
                        self.ag_dl_status.setText("✅ Antigravity Proxy is fully updated & active.")
                        self.ag_dashboard_btn.setEnabled(True)
                        self.ag_enable_cb.setEnabled(True)
                        self.ag_enable_cb.setChecked(True)
                        self.ag_fetch_btn.setEnabled(False)
                        self.ag_delete_btn.setEnabled(True)
                        if "antigravity_proxy" not in self.config or not isinstance(self.config["antigravity_proxy"], dict):
                            self.config["antigravity_proxy"] = {}
                        self.config["antigravity_proxy"]["enabled"] = True
                        proxy_manager.start(self.config)
                    else:
                        self.ag_dl_progress.setVisible(False)
                        self.ag_dl_status.setText(f"❌ Failed: {err_msg}")
                        self.ag_fetch_btn.setEnabled(True) 
                mw.taskman.run_on_main(_done)
            
            import threading
            threading.Thread(target=_task, daemon=True).start()
        except Exception as e:
            from aqt.utils import showWarning
            showWarning(f"Setup failed: {e}")

    def _on_tab_changed_tracker(self, index):
        global LAST_ACTIVE_TAB_INDEX
        LAST_ACTIVE_TAB_INDEX = index
        if index == 2 and hasattr(self, "refresh_blacklist_list"):
            self.refresh_blacklist_list()
        if hasattr(self, 'config'):
             self.config["last_active_tab"] = index
             try: mw.addonManager.writeConfig(ADDON_PACKAGE, self.config)
             except Exception: pass

    def on_delete_binary(self):
        if not askUser("Are you sure you want to delete the Antigravity Proxy binary from your drive?\n\nThis will not delete your saved configuration, but disables the proxy until re-downloaded."):
            return
        try:
            from ..proxy_manager import proxy_manager
            proxy_manager.stop()
            if os.path.exists(proxy_manager.executable):
                os.remove(proxy_manager.executable)
            self.ag_fetch_btn.setEnabled(True)
            self.ag_dashboard_btn.setEnabled(False)
            self.ag_enable_cb.setEnabled(False)
            self.ag_enable_cb.setChecked(False)
            self.ag_delete_btn.setEnabled(False)
            self.ag_dl_status.setVisible(True)
            self.ag_dl_status.setText("🗑️ Native binary successfully removed from disk.")
            self.ag_dl_progress.setVisible(False)
        except Exception as e:
            from aqt.utils import showWarning
            showWarning(f"Deletion failed: {e}")

    def on_fetch_all_models(self):
        if getattr(self, "batch_fetch_active", False):
            # Cancel all active fetches
            for provider in list(self.active_batch_providers):
                FETCH_CANCELLATIONS[f"{provider}_main"] = True
            if hasattr(self, "fetch_all_btn"):
                self.fetch_all_btn.setText("Fetch All")
            if hasattr(self, "global_fallback_dlg") and self.global_fallback_dlg:
                self.global_fallback_dlg.list_fetch_btn.setText("Fetch All")
            self.batch_fetch_active = False
            self.active_batch_providers.clear()
            tooltip("Batch model fetch cancelled.")
            return

        # Determine which providers we will fetch for
        providers_to_fetch = []
        for provider, combobox in self.model_edits.items():
            api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
            if api_key or provider in ["local", "antigravity"]:
                providers_to_fetch.append((provider, combobox))
        
        # Also local and antigravity
        if hasattr(self, 'local_model_edit'):
            providers_to_fetch.append(("local", self.local_model_edit))
        if hasattr(self, 'ag_model_edit'):
            providers_to_fetch.append(("antigravity", self.ag_model_edit))
        
        if not providers_to_fetch:
            tooltip("No providers configured to fetch.")
            return
            
        self.batch_fetch_active = True
        self.active_batch_providers = {provider for provider, _ in providers_to_fetch}
        if hasattr(self, "fetch_all_btn"):
            self.fetch_all_btn.setText("Stop Fetch All")
        if hasattr(self, "global_fallback_dlg") and self.global_fallback_dlg:
            self.global_fallback_dlg.list_fetch_btn.setText("Stop Fetch All")
        tooltip("Starting batch model fetch...")
        
        def _check_batch_done(provider_done):
            if not getattr(self, "batch_fetch_active", False):
                return
            self.active_batch_providers.discard(provider_done)
            if not self.active_batch_providers:
                self.batch_fetch_active = False
                if hasattr(self, "fetch_all_btn"):
                    self.fetch_all_btn.setText("Fetch All")
                if hasattr(self, "global_fallback_dlg") and self.global_fallback_dlg:
                    self.global_fallback_dlg.list_fetch_btn.setText("Fetch All")
                tooltip("Finished fetching models for all configured providers.")
                
        for provider, combobox in providers_to_fetch:
            # Clear cancel flag for this provider
            FETCH_CANCELLATIONS[f"{provider}_main"] = False
            
            # Find the corresponding fetch button if it exists
            fetch_btn = None
            if provider == "local" and hasattr(self, "local_fetch_btn"):
                fetch_btn = self.local_fetch_btn
            elif provider == "antigravity" and hasattr(self, "ag_model_fetch_btn"):
                fetch_btn = self.ag_model_fetch_btn
            elif hasattr(self, "provider_widgets") and provider in self.provider_widgets:
                fetch_btn = self.provider_widgets[provider].fetch_btn
                
            self.on_fetch_models(provider, combobox, silent=True, fetch_btn=fetch_btn, on_done_callback=_check_batch_done)

    def on_test_model(self, provider, combobox, status_label=None):
        """Runs a real-world test generation using the currently selected model."""
        model_name = combobox.currentText().strip()
        if not model_name:
            if status_label:
                st, tt, col = "❌ No Model", "Please select or enter a model name first.", "red"
                PERSISTENT_TEST_STATUSES[provider] = (st, tt, col, "")
                status_label.setText(st)
                status_label.setToolTip(tt)
                status_label.setStyleSheet(f"font-weight: bold; color: {col}; margin-left: 5px;")
            else:
                info(f"Please select or enter a model name for {provider.capitalize()} first.")
            return

        api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
        if not api_key and provider not in ["local", "antigravity"]:
            if status_label:
                st, tt, col = "❌ No API Key", "Please enter an API key first.", "red"
                PERSISTENT_TEST_STATUSES[provider] = (st, tt, col, model_name)
                status_label.setText(st)
                status_label.setToolTip(tt)
                status_label.setStyleSheet(f"font-weight: bold; color: {col}; margin-left: 5px;")
            else:
                info(f"Please enter an API key for {provider.capitalize()} first.")
            return

        # Prepare temporary config for the test
        temp_config = self.config.copy()
        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
        temp_config["api_keys"][provider] = api_key
        
        if "models" not in temp_config: temp_config["models"] = {}
        temp_config["models"][provider] = model_name

        if provider == "local":
            temp_config["local_endpoint"] = {
                "base_url": self.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "api_key": self.local_api_key_edit.text().strip(),
                "model": model_name
            }
        
        if provider == "antigravity":
            temp_config["antigravity_proxy"] = {"enabled": True, "port": 3000}

        client = AIClient(temp_config)
        combobox.setEnabled(False)
        if status_label:
            status_label.setText("⏳ Testing...")
            status_label.setToolTip(f"Testing model: {model_name}")
            status_label.setStyleSheet("font-weight: bold; color: orange; margin-left: 5px;")
        else:
            tooltip(f"Testing {provider.capitalize()} model: {model_name}...")

        def _run_test():
            from ..logger import log_context
            log_context.source = "model_test"
            try:
                # Use the configured custom test prompt
                from .tab_providers import DEFAULT_TEST_QUESTION, DEFAULT_TEST_ANSWER
                test_front = self.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION
                test_back = self.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER
                
                # We use generate_options directly to test the full pipeline
                res = client.generate_options(test_front, test_back, override_provider=provider, only_this_provider=True)
                
                def _done():
                    combobox.setEnabled(True)
                    if res and (res.get("hints") or res.get("options")):
                        import json
                        formatted_res = json.dumps(res, indent=2, ensure_ascii=False)
                        if status_label:
                            st, tt, col = "✅ Success", (
                                f"<div style='width: 450px;'>"
                                f"<b>Question:</b> {test_front}<br/>"
                                f"<b>Answer:</b> {test_back}<br/><br/>"
                                f"<b>Model Response:</b><br/>"
                                f"<pre style='font-family: monospace; font-size: 11px; white-space: pre-wrap; word-wrap: break-word;'>{formatted_res}</pre>"
                                f"</div>"
                            ), "green"
                            PERSISTENT_TEST_STATUSES[provider] = (st, tt, col, model_name)
                            status_label.setText(st)
                            status_label.setToolTip(tt)
                            status_label.setStyleSheet(f"font-weight: bold; color: {col}; margin-left: 5px;")
                        else:
                            info(f"✅ Success! {provider.capitalize()} is working.\n\n"
                                 f"Model: {model_name}\n"
                                 f"Result: Generated {len(res.get('hints', []))} hints and {len(res.get('options', []))} options.")
                    else:
                        if status_label:
                            st, tt, col = "❌ Failed", f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/>The provider returned an empty response. Check API key, model name, balance.</div>", "red"
                            PERSISTENT_TEST_STATUSES[provider] = (st, tt, col, model_name)
                            status_label.setText(st)
                            status_label.setToolTip(tt)
                            status_label.setStyleSheet(f"font-weight: bold; color: {col}; margin-left: 5px;")
                        else:
                            info(f"❌ Test Failed for {provider.capitalize()}.\n\n"
                                 f"The provider returned an empty response. Check your API key, "
                                 f"model name, and account balance.")
                mw.taskman.run_on_main(_done)
                
            except Exception as e:
                def _fail():
                    combobox.setEnabled(True)
                    if status_label:
                        st, tt, col = "❌ Failed", f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/><b>Error:</b> {str(e)}</div>", "red"
                        PERSISTENT_TEST_STATUSES[provider] = (st, tt, col, model_name)
                        status_label.setText(st)
                        status_label.setToolTip(tt)
                        status_label.setStyleSheet(f"font-weight: bold; color: {col}; margin-left: 5px;")
                    else:
                        info(f"❌ Test Error ({provider.capitalize()}):\n\n{str(e)}")
                mw.taskman.run_on_main(_fail)

        import threading
        threading.Thread(target=_run_test, daemon=True).start()

    def on_test_all_models(self):
        """Runs test checks sequentially for all provider rows that are configured or enabled."""
        tooltip("Starting batch model testing...")
        
        # Collect all rows (providers) and their associated widgets
        targets = []
        
        # 1. Standard provider widgets
        if hasattr(self, 'models_layout') and self.models_layout is not None:
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget):
                    targets.append((w.provider, w.edit, w.status_label))
                    
        # 2. Local AI widget
        if hasattr(self, 'local_model_edit') and hasattr(self, 'local_test_status_label'):
            targets.append(("local", self.local_model_edit, self.local_test_status_label))
        
        # Antigravity is handled under step 1 (Standard provider priority list row)
        
        # Run tests sequentially in a background thread
        import threading
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            for provider, combobox, status_label in targets:
                # Only test if configured/enabled
                api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
                if not api_key and provider not in ["local", "antigravity"]:
                    continue
                
                # Update UI to Testing...
                def _start(c=combobox, s=status_label):
                    c.setEnabled(False)
                    if s:
                        s.setText("⏳ Testing...")
                        s.setToolTip(f"Testing model: {c.currentText()}")
                        s.setStyleSheet("font-weight: bold; color: orange; margin-left: 5px;")
                mw.taskman.run_on_main(_start)
                
                model_name = combobox.currentText().strip()
                status = "✅ Success"
                detail = ""
                
                try:
                    temp_config = self.config.copy()
                    if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                    temp_config["api_keys"][provider] = api_key
                    if "models" not in temp_config: temp_config["models"] = {}
                    temp_config["models"][provider] = model_name

                    if provider == "local":
                        temp_config["local_endpoint"] = {
                            "base_url": self.local_url_edit.text().strip() or "http://localhost:11434/v1",
                            "api_key": self.local_api_key_edit.text().strip(),
                            "model": model_name
                        }
                    
                    if provider == "antigravity":
                        temp_config["antigravity_proxy"] = {"enabled": True, "port": 3000}
                        
                    client = AIClient(temp_config)
                    from .tab_providers import DEFAULT_TEST_QUESTION, DEFAULT_TEST_ANSWER
                    test_front = self.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION
                    test_back = self.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER
                    res = client.generate_options(test_front, test_back, override_provider=provider, only_this_provider=True)
                    if not (res and (res.get("hints") or res.get("options"))):
                        status = "❌ Failed"
                        detail = f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/>Returned empty response.</div>"
                    else:
                        import json
                        formatted_res = json.dumps(res, indent=2, ensure_ascii=False)
                        detail = (
                            f"<div style='width: 450px;'>"
                            f"<b>Question:</b> {test_front}<br/>"
                            f"<b>Answer:</b> {test_back}<br/><br/>"
                            f"<b>Model Response:</b><br/>"
                            f"<pre style='font-family: monospace; font-size: 11px; white-space: pre-wrap; word-wrap: break-word;'>{formatted_res}</pre>"
                            f"</div>"
                        )
                except Exception as e:
                    status = "❌ Failed"
                    detail = f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/><b>Error:</b> {str(e)}</div>"
                    
                # Update UI to result
                def _end(c=combobox, s=status_label, st=status, d=detail, m=model_name):
                    c.setEnabled(True)
                    if s:
                        color = "green" if "Success" in st else "red"
                        PERSISTENT_TEST_STATUSES[provider] = (st, d, color, m)
                        s.setText(st)
                        s.setToolTip(d)
                        s.setStyleSheet(f"font-weight: bold; color: {color}; margin-left: 5px;")
                mw.taskman.run_on_main(_end)
                
            def _done_all():
                tooltip("Finished batch model testing.")
            mw.taskman.run_on_main(_done_all)
            
        threading.Thread(target=_runner, daemon=True).start()

    def on_fetch_models(self, provider, combobox, silent=False, fetch_btn=None, on_done_callback=None):
        fetch_key = f"{provider}_main"
        if fetch_key in FETCH_CANCELLATIONS:
            # User clicked again to Stop/Cancel
            FETCH_CANCELLATIONS[fetch_key] = True
            if fetch_btn:
                fetch_btn.setText("Fetch")
            return
            
        FETCH_CANCELLATIONS[fetch_key] = False
        if fetch_btn:
            fetch_btn.setText("Stop Fetch")
            
        api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
        if not api_key and provider not in ["local", "antigravity"]:
            if not silent:
                info(f"Please enter an API key for {provider.capitalize()} first.")
            if fetch_btn:
                fetch_btn.setText("Fetch")
            del FETCH_CANCELLATIONS[fetch_key]
            if on_done_callback:
                on_done_callback(provider)
            return
            
        temp_config = self.config.copy()
        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
        temp_config["api_keys"][provider] = api_key
        if provider == "local":
            temp_config["local_endpoint"] = {
                "base_url": self.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "api_key": self.local_api_key_edit.text().strip()
            }
            
        client = AIClient(temp_config)
        combobox.setEnabled(False)
        if not silent: tooltip(f"Fetching models for {provider.capitalize()}...")
        
        import threading
        def _runner():
            try:
                if FETCH_CANCELLATIONS.get(fetch_key):
                    return
                models = client.fetch_models(provider)
                if FETCH_CANCELLATIONS.get(fetch_key):
                    return
                    
                def _done():
                    if models:
                        current_text = combobox.currentText()
                        combobox.clear()
                        clean_models = sorted(list(set(models)))
                        if current_text and current_text not in clean_models: clean_models.insert(0, current_text)
                        combobox.addItems(clean_models)
                        if current_text: combobox.setCurrentText(current_text)
                        
                        # Update fallback list data
                        if hasattr(self, 'model_fallbacks_data') and hasattr(self, 'disabled_fallback_models_data'):
                            current_fallbacks = self.model_fallbacks_data.get(provider, [])
                            if not isinstance(current_fallbacks, list):
                                current_fallbacks = list(current_fallbacks)
                            
                            disabled_models = self.disabled_fallback_models_data.get(provider, [])
                            if not isinstance(disabled_models, list):
                                disabled_models = list(disabled_models)
                                
                            current_set = set(current_fallbacks)
                            for m in clean_models:
                                if m and m not in current_set:
                                    current_fallbacks.append(m)
                                    disabled_models.append(m)
                                    
                            self.model_fallbacks_data[provider] = current_fallbacks
                            self.disabled_fallback_models_data[provider] = disabled_models
                        
                        # Refresh global fallback dialog if active
                        if hasattr(self, "global_fallback_dlg") and self.global_fallback_dlg:
                            try:
                                self.global_fallback_dlg.refresh_statuses()
                            except: pass

                        if not silent: tooltip(f"Found {len(clean_models)} models for {provider.capitalize()}")
                    else:
                        if not silent: info(f"Could not fetch models for {provider.capitalize()}. Check connection.")
                mw.taskman.run_on_main(_done)
            except Exception as e:
                logger.error(f"Fetch error: {e}")
                def _fail():
                    if not silent: info(f"Error fetching models: {e}")
                mw.taskman.run_on_main(_fail)
            finally:
                if fetch_key in FETCH_CANCELLATIONS:
                    del FETCH_CANCELLATIONS[fetch_key]
                def _enable():
                    combobox.setEnabled(True)
                    if fetch_btn:
                        fetch_btn.setText("Fetch")
                    if on_done_callback:
                        on_done_callback(provider)
                mw.taskman.run_on_main(_enable)
                
        threading.Thread(target=_runner, daemon=True).start()

    def on_add_custom(self):
        dlg = CustomProviderDialog(self)
        if dlg.exec():
            name = dlg.name_edit.text().strip()
            self.custom_providers_data[name] = {
                "url": dlg.url_edit.text().strip(),
                "api_key": dlg.key_edit.text().strip(),
                "model": dlg.model_edit.text().strip(),
                "headers": json.loads(dlg.headers_edit.toPlainText() or "{}")
            }
            self.refresh_custom_list()
            
    def on_edit_custom(self):
        item = self.custom_list.currentItem()
        if not item: return
        name = item.text()
        data = self.custom_providers_data.get(name, {})
        dlg = CustomProviderDialog(self, name=name, data=data)
        if dlg.exec():
            new_name = dlg.name_edit.text().strip()
            if new_name != name:
                del self.custom_providers_data[name]
            self.custom_providers_data[new_name] = {
                "url": dlg.url_edit.text().strip(),
                "api_key": dlg.key_edit.text().strip(),
                "model": dlg.model_edit.text().strip(),
                "headers": json.loads(dlg.headers_edit.toPlainText() or "{}")
            }
            self.refresh_custom_list()

    def on_remove_custom(self):
        item = self.custom_list.currentItem()
        if not item: return
        name = item.text()
        del self.custom_providers_data[name]
        self.refresh_custom_list()
        
    def on_restore_current_tab(self):
        if not self.default_config: return
        tab_text = self.tabs.tabText(self.tabs.currentIndex())
        if tab_text == "General":
            if askUser("⚠️ WARNING: This will immediately restore all General settings. Continue?"):
                self.on_restore_general()
        elif tab_text == "AI Providers":
            if askUser("⚠️ WARNING: This will immediately restore all model names and priorities. Continue?"):
                self.on_restore_providers()
        elif tab_text == "Advanced":
            if askUser("⚠️ WARNING: This will immediately restore system prompt and field settings. Continue?"):
                self.on_restore_advanced()
        else:
            tooltip("No defaults to restore for this tab.")

    def on_restore_models_only(self):
        if not self.default_config: return
        if not askUser("⚠️ WARNING: This will restore model selections. Continue?"): return
        c = self.default_config
        models = c.get("models", {}) or {}
        for p, edit in self.model_edits.items():
            model_name = models.get(p, DEFAULT_MODELS.get(p, ""))
            if edit.findText(model_name) == -1: edit.addItem(model_name)
            edit.setCurrentText(model_name)
        ag_model = models.get("antigravity", DEFAULT_MODELS.get("antigravity", ""))
        if self.ag_model_edit.findText(ag_model) == -1: self.ag_model_edit.addItem(ag_model)
        self.ag_model_edit.setCurrentText(ag_model)
        local_model = c.get("local_endpoint", {}).get("model", "")
        if self.local_model_edit.findText(local_model) == -1: self.local_model_edit.addItem(local_model)
        self.local_model_edit.setCurrentText(local_model)
        tooltip("Default models restored.")

    def on_restore_general(self):
        if not self.default_config: return
        c = self.default_config
        self.ai_provider_cb.setCurrentText(c.get("ai_provider", "openai"))
        self.options_count_sb.setValue(c.get("options_count", 4))
        self.mathjax_format_cb.setCurrentText(c.get("mathjax_format", "delimiters"))
        self.fix_latex_cb.setChecked(c.get("fix_latex", False))
        self.answer_display_position_cb.setCurrentText(c.get("answer_display_position", "between"))
        self.show_hints_cb.setChecked(c.get("show_hints_button", True))
        self.show_options_cb.setChecked(c.get("show_options_button", True))
        self.show_on_card_cb.setChecked(c.get("show_on_card", True))
        self.show_in_bottom_bar_cb.setChecked(c.get("show_in_bottom_bar", True))
        self.show_in_popup_cb.setChecked(c.get("show_in_popup", False))
        if hasattr(self, 'auto_clear_cb'): self.auto_clear_cb.setChecked(c.get("auto_clear_logs", True))
        self.auto_generate_new_cb.setChecked(c.get("auto_generate_new", False))
        self.auto_regenerate_all_cb.setChecked(c.get("auto_regenerate_all", False))
        self.auto_regenerate_all_cb.setEnabled(self.auto_generate_new_cb.isChecked())
        auto_gen_on = self.auto_generate_new_cb.isChecked()
        self.auto_regenerate_old_version_cb.setChecked(c.get("auto_regenerate_if_old_version", False))
        self.auto_regenerate_old_version_cb.setEnabled(auto_gen_on)
        self.auto_regenerate_min_version_edit.setText(c.get("auto_regenerate_min_version", ""))
        self.auto_regenerate_min_version_edit.setEnabled(auto_gen_on and self.auto_regenerate_old_version_cb.isChecked())
        self.auto_regenerate_old_time_cb.setChecked(c.get("auto_regenerate_if_old_time", False))
        self.auto_regenerate_old_time_cb.setEnabled(auto_gen_on)
        self.auto_regenerate_min_time_edit.setText(c.get("auto_regenerate_min_time", ""))
        self.auto_regenerate_min_time_edit.setEnabled(auto_gen_on and self.auto_regenerate_old_time_cb.isChecked())
        self.auto_show_hints_cb.setChecked(c.get("auto_show_hints", True))
        self.auto_show_options_cb.setChecked(c.get("auto_show_options", False))
        self.do_not_auto_collapse_cb.setChecked(c.get("do_not_auto_collapse", False))
        self.manual_show_hints_cb.setChecked(c.get("manual_show_hints", True))
        self.manual_show_options_cb.setChecked(c.get("manual_show_options", False))
        tooltip("General defaults restored.")

    def on_restore_providers(self):
        if not self.default_config: return
        c = self.default_config
        models = c.get("models", {}) or {}
        default_priority = c.get("provider_priority", PROVIDER_ORDER)
        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            if item:
                w = item.widget()
                if w: w.deleteLater()
        self.model_edits = {}
        for p in default_priority:
            w = ProviderRowWidget(p, self)
            model_name = models.get(p, DEFAULT_MODELS.get(p, ""))
            if w.edit.findText(model_name) == -1: w.edit.addItem(model_name)
            w.edit.setCurrentText(model_name)
            self.model_edits[p] = w.edit
            self.models_layout.addWidget(w)
        local = c.get("local_endpoint", {}) or {}
        self.local_url_edit.setText(local.get("base_url", ""))
        model_name = local.get("model", "")
        if self.local_model_edit.findText(model_name) == -1: self.local_model_edit.addItem(model_name)
        self.local_model_edit.setCurrentText(model_name)
        self.local_fallback_cb.setChecked(local.get("enabled", False))
        ag_model = models.get("antigravity", DEFAULT_MODELS.get("antigravity", ""))
        if self.ag_model_edit.findText(ag_model) == -1: self.ag_model_edit.addItem(ag_model)
        self.ag_model_edit.setCurrentText(ag_model)
        tooltip("Provider defaults restored.")

    def on_restore_advanced(self):
        if not self.default_config: return
        c = self.default_config
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        tooltip("Advanced defaults restored.")

    def stop_migration(self):
        if self._migration_running:
            self._migration_stop_requested = True
            self.mig_status_label.setText("Stopping... finishing current note")
            self.mig_stop_btn.setEnabled(False)

    def on_migrate_data(self):
        """Finds all AI hints in non-first fields and moves them to the first field."""
        if self._migration_running:
            return

        query = self._get_maint_search_query()
        scope_str = "your entire collection" if not query else f"the deck '{self.maint_deck_cb.currentText()}'"

        if not askUser(f"This will scan {scope_str} and move any AI data blocks from secondary fields to the <b>first field</b> of each note to ensure they render correctly during review.\n\nContinue?"):
            return

        mw.checkpoint("Migrate AI Data")

        from ..card_parser import CardParser
        parser = CardParser(storage_mode=self.config.get("storage_mode", "json"))
        
        self._migration_running = True
        self._migration_stop_requested = False
        
        self.migrate_btn.setEnabled(False)
        self.migrate_btn.setText("🔄 Migration in progress...")
        
        self.mig_progress_box.setVisible(True)
        self.mig_progress_bar.setValue(0)
        self.mig_status_label.setText("Initializing migration...")
        self.mig_stop_btn.setEnabled(True)
        
        logger.info(f"AI-Hints: Starting migration for {scope_str} to move AI data to first fields.")
        
        def _task():
            moved = 0
            # Get all note IDs
            nids = mw.col.find_notes(query)
            total = len(nids)
            
            for i, nid in enumerate(nids):
                if self._migration_stop_requested:
                    logger.info(f"AI-Hints: Migration STOPPED by user. Processed {i} notes, moved {moved}.")
                    break
                    
                try:
                    note = mw.col.get_note(nid)
                    fields = list(note.keys())
                    if len(fields) < 2:
                        # Even if only one field, check if it needs consolidation/conversion
                        first_field = fields[0]
                        other_fields = []
                    else:
                        first_field = fields[0]
                        other_fields = fields[1:]
                    
                    # 1. Extract all blocks from all fields
                    all_blocks = parser._extract_all_hints_from_fields(note)
                    if not all_blocks:
                        continue
                        
                    # 2. Check if migration/consolidation is needed
                    # - Are there blocks in secondary fields?
                    # - Are there multiple blocks in total?
                    blocks_in_others = []
                    for f in other_fields:
                        blocks = parser._extract_hints_from_field(note[f], None)
                        if blocks:
                            blocks_in_others.extend(blocks)
                    
                    # Consolidation triggers:
                    # - Data in other fields
                    # - Multiple blocks total (even if all in first field)
                    if not blocks_in_others and len(all_blocks) <= 1:
                        # Check format: if single block is HTML, convert anyway
                        first_field_val = note[first_field]
                        if "ai-hints-container" in first_field_val:
                            pass # proceed to migrate/convert
                        else:
                            continue
                    
                    if blocks_in_others:
                        logger.debug(f"Migrating note {nid}: found {len(blocks_in_others)} blocks in secondary fields.")
                    elif len(all_blocks) > 1:
                        logger.debug(f"Consolidating note {nid}: found {len(all_blocks)} blocks in first field.")
                    else:
                        logger.debug(f"Converting note {nid}: converting HTML block to JSON.")
                        
                    # 3. If found, we clear ALL fields and re-inject into the first field
                    parser._remove_all_hints_from_fields(note)
                    
                    # Sort blocks by card index (c1, c2...)
                    all_blocks.sort(key=lambda x: x.get("card_key", "") if x.get("card_key") else "")
                    
                    # Re-inject into first field
                    current_val = note[first_field]
                    for block in all_blocks:
                        data = block["data"]
                        card_key = block.get("card_key")
                        toggles = block.get("toggles", {})
                        
                        current_val = parser._update_json_block_in_field(current_val, data, card_key, toggles)
                            
                    note[first_field] = current_val
                    mw.col.update_note(note)
                    moved += 1
                    
                    if i % 10 == 0 or i == total - 1:
                        def _prog(v=i, t=total, m=moved):
                            pct = int((v + 1) / t * 100) if t > 0 else 0
                            self.mig_progress_bar.setValue(pct)
                            self.mig_status_label.setText(f"Scanning: {v+1}/{t} notes (Moved: {m})")
                        mw.taskman.run_on_main(_prog)
                        
                except Exception as e:
                    logger.error(f"Migration error on note {nid}: {e}")
                    
            def _done(m=moved, stopped=self._migration_stop_requested):
                self._migration_running = False
                self.migrate_btn.setEnabled(True)
                self.migrate_btn.setText("🚀 Move all AI data to the first field")
                
                mw.reset()
                
                if stopped:
                    self.mig_status_label.setText(f"🛑 Stopped. Moved {m} notes.")
                    info(f"Migration stopped.\n\nProcessed until stop, moved AI data in {m} notes.")
                else:
                    logger.info(f"AI-Hints: Migration COMPLETED. Successfully moved AI data in {m} notes.")
                    self.mig_progress_bar.setValue(100)
                    self.mig_status_label.setText(f"✅ Complete! Moved {m} notes.")
                    info(f"✅ Migration Complete!\n\nMoved AI data in {m} notes to their first fields.")
                
                # Keep progress box visible for a few seconds then hide if complete
                if not stopped:
                    QTimer.singleShot(5000, lambda: self.mig_progress_box.setVisible(False))
                
            mw.taskman.run_on_main(_done)

        import threading
        threading.Thread(target=_task, daemon=True).start()

    def on_convert_html_to_json(self):
        """Specific maintenance task to convert all visible HTML hint blocks to hidden JSON."""
        if self._migration_running:
            return

        query = self._get_maint_search_query()
        scope_str = "your entire collection" if not query else f"the deck '{self.maint_deck_cb.currentText()}'"

        if not askUser(f"This will scan {scope_str} and find any visible HTML AI hint blocks and convert them into invisible JSON data to clean up your editor.\n\nContinue?"):
            return

        mw.checkpoint("Convert HTML to JSON")

        from ..card_parser import CardParser
        # Force JSON mode for this task
        parser = CardParser(storage_mode="json")
        
        self._migration_running = True
        self._migration_stop_requested = False
        
        self.html_to_json_btn.setEnabled(False)
        self.html_to_json_btn.setText("🔄 Converting...")
        
        self.mig_progress_box.setVisible(True)
        self.mig_progress_bar.setValue(0)
        self.mig_status_label.setText("Starting conversion...")
        self.mig_stop_btn.setEnabled(True)
        
        logger.info(f"AI-Hints: Starting HTML to JSON conversion for {scope_str}.")
        
        def _task():
            converted = 0
            nids = mw.col.find_notes(query)
            total = len(nids)
            
            for i, nid in enumerate(nids):
                if self._migration_stop_requested: break
                try:
                    note = mw.col.get_note(nid)
                    first_field = list(note.keys())[0]
                    
                    # Look specifically for HTML blocks
                    first_field_val = note[first_field]
                    if "ai-hints-container" not in first_field_val:
                        # Check other fields too
                        other_has = False
                        for f in list(note.keys())[1:]:
                            if "ai-hints-container" in note[f]:
                                other_has = True
                                break
                        if not other_has: continue

                    # 1. Extract all blocks (parser now supports HTML extraction)
                    all_blocks = parser._extract_all_hints_from_fields(note)
                    if not all_blocks: continue
                    
                    # 2. Clear and Re-inject as JSON into first field
                    parser._remove_all_hints_from_fields(note)
                    all_blocks.sort(key=lambda x: x.get("card_key", "") if x.get("card_key") else "")
                    
                    current_val = note[first_field]
                    for block in all_blocks:
                        data = block["data"]
                        card_key = block.get("card_key")
                        toggles = block.get("toggles", {})
                        current_val = parser._update_json_block_in_field(current_val, data, card_key, toggles)
                            
                    note[first_field] = current_val
                    mw.col.update_note(note)
                    converted += 1
                    
                    if i % 10 == 0 or i == total - 1:
                        def _prog(v=i, t=total, c=converted):
                            pct = int((v + 1) / t * 100) if t > 0 else 0
                            self.mig_progress_bar.setValue(pct)
                            self.mig_status_label.setText(f"Converting: {v+1}/{t} (Fixed: {c})")
                        mw.taskman.run_on_main(_prog)
                except Exception as e:
                    logger.error(f"HTML-to-JSON error on note {nid}: {e}")
                    
            def _done(c=converted, stopped=self._migration_stop_requested):
                self._migration_running = False
                self.html_to_json_btn.setEnabled(True)
                self.html_to_json_btn.setText("👻 Convert HTML to Hidden JSON")
                mw.reset()
                self.mig_progress_bar.setValue(100)
                self.mig_status_label.setText(f"✅ Fixed {c} notes.")
                info(f"Conversion Complete!\n\nSuccessfully hid hint blocks in {c} notes.")
                if not stopped:
                    QTimer.singleShot(5000, lambda: self.mig_progress_box.setVisible(False))
            mw.taskman.run_on_main(_done)

        import threading
        threading.Thread(target=_task, daemon=True).start()


    def move_provider_row(self, row_widget, delta):
        curr_index = self.models_layout.indexOf(row_widget)
        if curr_index == -1: return
        target_index = curr_index + delta
        if 0 <= target_index < self.models_layout.count():
            self.models_layout.removeWidget(row_widget)
            self.models_layout.insertWidget(target_index, row_widget)

    def save_config(self, close=True):
        try:
            if hasattr(self, 'raw_toggle') and self.raw_toggle.isChecked():
                raw_config = json.loads(self.raw_editor.toPlainText() or "{}")
                mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(raw_config))
                if close: self.accept()
                else: tooltip("Configuration saved.")
                return
            new_config = self.config.copy()
            new_config["ai_provider"] = self.ai_provider_cb.currentText()
            new_config["options_count"] = self.options_count_sb.value()
            new_config["mathjax_format"] = self.mathjax_format_cb.currentText()
            new_config["fix_latex"] = self.fix_latex_cb.isChecked()
            new_config["answer_display_position"] = self.answer_display_position_cb.currentText()
            new_config["show_hints_button"] = self.show_hints_cb.isChecked()
            new_config["show_options_button"] = self.show_options_cb.isChecked()
            new_config["show_on_card"] = self.show_on_card_cb.isChecked()
            new_config["show_in_bottom_bar"] = self.show_in_bottom_bar_cb.isChecked()
            new_config["show_in_popup"] = self.show_in_popup_cb.isChecked()
            if hasattr(self, 'auto_clear_cb'):
                new_config["auto_clear_logs"] = self.auto_clear_cb.isChecked()
            new_config["auto_generate_new"] = self.auto_generate_new_cb.isChecked()
            new_config["auto_regenerate_all"] = self.auto_regenerate_all_cb.isChecked()
            new_config["auto_regenerate_if_old_version"] = self.auto_regenerate_old_version_cb.isChecked()
            new_config["auto_regenerate_min_version"] = self.auto_regenerate_min_version_edit.text().strip()
            new_config["auto_regenerate_if_old_time"] = self.auto_regenerate_old_time_cb.isChecked()
            new_config["auto_regenerate_min_time"] = self.auto_regenerate_min_time_edit.text().strip()
            new_config["pre_generate_next"] = self.pre_generate_next_cb.isChecked()
            new_config["pre_generate_count"] = self.pre_generate_count_spin.value()
            new_config["auto_show_hints"] = self.auto_show_hints_cb.isChecked()
            new_config["auto_show_options"] = self.auto_show_options_cb.isChecked()
            new_config["do_not_auto_collapse"] = self.do_not_auto_collapse_cb.isChecked()
            new_config["manual_show_hints"] = self.manual_show_hints_cb.isChecked()
            new_config["manual_show_options"] = self.manual_show_options_cb.isChecked()
            new_config["shortcuts"] = {key: edit.text().strip() for key, edit in self.shortcut_edits.items()}
            new_config["shortcuts"]["modifier"] = self.modifier_cb.currentText()
            new_config["api_keys"] = {p: edit.text().strip() for p, edit in self.api_key_edits.items()}
            new_config["models"] = {p: (edit.currentText().strip() or DEFAULT_MODELS.get(p, "")) for p, edit in self.model_edits.items()}
            new_config["models"]["antigravity"] = self.ag_model_edit.currentText().strip() or DEFAULT_MODELS.get("antigravity", "")
            new_config["antigravity_proxy"] = {"enabled": self.ag_enable_cb.isChecked(), "port": 3000}
            new_config["local_endpoint"] = {
                "enabled": self.local_fallback_cb.isChecked(),
                "base_url": self.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "model": self.local_model_edit.currentText().strip() or DEFAULT_MODELS["local"],
                "api_key": self.local_api_key_edit.text().strip()
            }
            new_config["system_prompt"] = self.system_prompt_edit.toPlainText()
            new_config["custom_providers"] = self.custom_providers_data
            new_config["model_fallbacks"] = self.model_fallbacks_data
            new_config["disabled_fallback_models"] = self.disabled_fallback_models_data
            new_config["global_model_priority"] = self.global_model_priority_data
            new_config["use_global_model_priority"] = self.advanced_fallback_cb.isChecked()
            new_config["test_question_front"] = self.test_question_edit.text().strip()
            new_config["test_question_back"] = self.test_answer_edit.text().strip()
            if hasattr(self, "cooldown_spin"):
                new_config["model_cooldown_minutes"] = self.cooldown_spin.value()
                
            if hasattr(self, "font_size_combo"):
                font_size = self.font_size_combo.currentText().strip()
                if font_size == "inherit":
                    font_size = ""
                new_config["hints_font_size"] = font_size

            if hasattr(self, "batch_limit_spin"):
                new_config["batch_limit"] = self.batch_limit_spin.value()
                
            if hasattr(self, "batch_multithread_cb"):
                new_config["multithread_providers"] = self.batch_multithread_cb.isChecked()

            # Mobile Config
            new_config["mobile_use_emojis"] = self.mobile_emojis_cb.isChecked()
            new_config["mobile_show_extra_buttons"] = self.mobile_extra_cb.isChecked()
            new_config["mobile_setup_completed"] = self.config.get("mobile_setup_completed", False)

            priority = []
            disabled = []
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget):
                    priority.append(w.provider)
                    if hasattr(w, "enabled_cb") and not w.enabled_cb.isChecked():
                        disabled.append(w.provider)
            new_config["provider_priority"] = priority
            new_config["disabled_providers"] = disabled
            mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(new_config))
            try:
                from ..proxy_manager import proxy_manager
                from ..mobile_sync import auto_update_mobile_setup
                proxy_manager.start(new_config)
                auto_update_mobile_setup() # Silently update if setup was already completed
            except Exception: pass
            self.config = new_config
            if close: self.accept()
            else: tooltip("Configuration saved.")
        except Exception as e:
            info(f"Error saving configuration: {e}")

    def _normalize_config(self, config):
        config = dict(config or {})
        raw_api_keys = config.get("api_keys", {}) or {}
        api_keys = dict(raw_api_keys) if isinstance(raw_api_keys, dict) else {}
        for provider in PROVIDER_ORDER:
            if provider != "local": api_keys.setdefault(provider, "")
        config["api_keys"] = api_keys
        models = dict(DEFAULT_MODELS)
        raw_models = config.get("models", {}) or {}
        if isinstance(raw_models, dict): models.update(raw_models)
        for provider, model in list(models.items()):
            models[provider] = LEGACY_MODEL_REPLACEMENTS.get((provider, model), model)
        config["models"] = models
        model_fallbacks = {p: list(f) for p, f in MODEL_FALLBACKS.items()}
        raw_model_fallbacks = config.get("model_fallbacks", {}) or {}
        if isinstance(raw_model_fallbacks, dict): model_fallbacks.update(raw_model_fallbacks)
        config["model_fallbacks"] = model_fallbacks
        custom_providers = config.get("custom_providers", {})
        if not isinstance(custom_providers, dict): custom_providers = {}
        custom_names = list(custom_providers.keys())
        priority = config.get("provider_priority", [])
        if not isinstance(priority, list): priority = PROVIDER_ORDER + custom_names
        available = set(PROVIDER_ORDER + custom_names)
        priority = [p for p in priority if p in available]
        for p in PROVIDER_ORDER + custom_names:
            if p not in priority: priority.append(p)
        config["provider_priority"] = priority
        local = {"enabled": False, "base_url": "http://localhost:11434/v1", "model": DEFAULT_MODELS["local"], "api_key": ""}
        raw_local = config.get("local_endpoint", {}) or {}
        if isinstance(raw_local, dict): local.update(raw_local)
        config["local_endpoint"] = local
        config.setdefault("ai_provider", "openai")
        config.setdefault("storage_mode", "json")
        config.setdefault("mathjax_format", "delimiters")
        config.setdefault("fix_latex", False)
        config.setdefault("answer_display_position", "between")
        config.setdefault("system_prompt", "")
        config.setdefault("show_hints_button", True)
        config.setdefault("show_options_button", True)
        if not isinstance(config.get("custom_providers", {}), dict): config["custom_providers"] = {}
        else: config.setdefault("custom_providers", {})
        try: config["options_count"] = max(1, min(int(config.get("options_count", 4)), 10))
        except: config["options_count"] = 4
        config.setdefault("show_on_card", True)
        config.setdefault("show_in_bottom_bar", True)
        config.setdefault("show_in_popup", False)
        config.setdefault("auto_clear_logs", True)
        config.setdefault("auto_generate_new", False)
        config.setdefault("auto_regenerate_all", False)
        config.setdefault("auto_regenerate_if_old_version", False)
        config.setdefault("auto_regenerate_min_version", "")
        config.setdefault("auto_regenerate_if_old_time", False)
        config.setdefault("auto_regenerate_min_time", "")
        config.setdefault("auto_show_hints", True)
        config.setdefault("auto_show_options", False)
        config.setdefault("do_not_auto_collapse", False)
        config.setdefault("manual_show_hints", True)
        config.setdefault("manual_show_options", False)
        
        # Mobile Support Defaults
        config.setdefault("mobile_use_emojis", False)
        config.setdefault("mobile_show_extra_buttons", False)
        config.setdefault("mobile_setup_completed", False)

        default_shortcuts = {"modifier": "alt", "generate": "1", "toggle-options": "3", "toggle-hints": "2", "clear": "4", "refresh": "5", "show-json": "6"}
        shortcuts = dict(default_shortcuts)
        raw_shortcuts = config.get("shortcuts", {}) or {}
        if isinstance(raw_shortcuts, dict): shortcuts.update(raw_shortcuts)
        config["shortcuts"] = shortcuts
        return config

    def on_convert_unicode_escapes(self):
        """Scans all notes and converts legacy compact/escaped JSON blocks to pretty raw Unicode."""
        from aqt.qt import Qt, QProgressDialog, QApplication
        from aqt.utils import askUser, showInfo
        from ..card_parser import CardParser

        query = self._get_maint_search_query()
        scope_str = "your entire collection" if not query else f"the deck '{self.maint_deck_cb.currentText()}'"

        if not askUser(f"This will scan {scope_str} and convert any legacy AI hints JSON data with hex escape codes (like \\uXXXX) into readable text and apply pretty formatting.\n\nContinue?"):
            return

        mw.checkpoint("Convert Unicode Escapes")

        parser = CardParser(
            storage_mode=self.config.get("storage_mode", "json"),
            mathjax_format=self.config.get("mathjax_format", "delimiters"),
            fix_latex=self.config.get("fix_latex", False)
        )

        nids = mw.col.find_notes(query)
        total = len(nids)
        if total == 0:
            showInfo(f"No notes found in the selected scope ({scope_str})!")
            return

        # Show a progress dialog
        progress = QProgressDialog(f"Converting Unicode escapes in {scope_str}...", "Cancel", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(200)

        changed_count = 0
        logger.info(f"AI-Hints: Starting Unicode conversion for {scope_str}.")

        for i, nid in enumerate(nids):
            if progress.wasCanceled():
                logger.info(f"AI-Hints: Unicode conversion CANCELLED by user. Processed {i} notes, updated {changed_count}.")
                break
            progress.setValue(i)
            progress.setLabelText(f"Converting note {i+1} of {total}...")
            QApplication.processEvents()

            try:
                note = mw.col.get_note(nid)
                if parser.format_unformatted_blocks_in_note(note):
                    mw.col.update_note(note)
                    changed_count += 1
            except Exception as note_err:
                logger.error(f"Error converting note {nid} Unicode escapes: {note_err}")

        progress.setValue(total)
        mw.reset()
        logger.info(f"AI-Hints: Unicode conversion COMPLETED. Successfully updated and pretty-printed AI hints in {changed_count} notes.")
        showInfo(
            f"🎉 Conversion Complete!\n\n"
            f"Successfully updated and pretty-printed AI hints in {changed_count} notes."
        )

    def on_scan_orphans(self):
        """Scans the entire collection to find and list orphaned AI hints in JSON blocks."""
        from aqt.qt import Qt, QProgressDialog, QApplication, QMessageBox
        from ..card_parser import CardParser
        import json, html, re

        query = self._get_maint_search_query()
        scope_str = "entire collection" if not query else f"deck '{self.maint_deck_cb.currentText()}'"

        parser = CardParser()

        nids = mw.col.find_notes(query)
        total = len(nids)
        if total == 0:
            QMessageBox.information(self, "AI-Hints", f"No notes found in the selected scope ({scope_str})!")
            return

        # Show a progress dialog
        progress = QProgressDialog(f"Scanning {scope_str} for orphaned hints...", "Cancel", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(200)

        orphaned_hints = []
        logger.info(f"AI-Hints: Starting scan for orphaned AI hints in {scope_str}.")

        for i, nid in enumerate(nids):
            if progress.wasCanceled():
                logger.info(f"AI-Hints: Orphaned hints scan CANCELLED by user. Processed {i} notes.")
                return
            progress.setValue(i)
            progress.setLabelText(f"Scanning note {i+1} of {total}...")
            QApplication.processEvents()

            try:
                note = mw.col.get_note(nid)
                raw_blocks = parser.find_all_hints_blocks(note)
                if not raw_blocks:
                    continue

                # Get active cards and their keys
                active_ords = {c.ord for c in note.cards()}
                valid_keys = {f"c{ord + 1}" for ord in active_ords}

                note_orphans = []
                
                for block in raw_blocks:
                    if parser.json_class in block:
                        m = re.search(
                            r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
                            block, re.DOTALL | re.IGNORECASE
                        )
                        if m:
                            raw = html.unescape(m.group(1) or "")
                            try:
                                parsed = json.loads(raw)
                            except Exception:
                                continue
                            
                            if isinstance(parsed, dict) and parser._is_keyed_payload(parsed):
                                # Find keys that are c\d+ but not in valid_keys
                                for key in list(parsed.keys()):
                                    if re.fullmatch(r"c\d+", str(key)) and key not in valid_keys:
                                        note_orphans.append((block, key, parsed[key]))

                if note_orphans:
                    # Get preview (first field content, stripped of HTML)
                    first_field_val = list(note.values())[0] if note.values() else ""
                    preview = parser._clean_html(first_field_val)[:60]
                    if len(first_field_val) > 60:
                        preview += "..."
                    
                    orphaned_hints.append({
                        "note_id": nid,
                        "preview": preview or f"Note ID {nid}",
                        "orphans": note_orphans,
                        "note": note
                    })
            except Exception as e:
                logger.error(f"Error scanning note {nid} for orphans: {e}")

        progress.setValue(total)
        logger.info(f"AI-Hints: Orphaned hints scan COMPLETED. Found orphans in {len(orphaned_hints)} notes.")

        if not orphaned_hints:
            QMessageBox.information(self, "Scan Complete", "🎉 No orphaned hints found! Your collection is perfectly clean.")
            return

        self._show_orphans_cleanup_dialog(orphaned_hints, parser)

    def _show_orphans_cleanup_dialog(self, orphaned_hints, parser):
        """Displays a dialog showing all orphaned hints found and allows safe cleanup."""
        from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QMessageBox
        import json, html, re
        
        dialog = QDialog(self)
        dialog.setWindowTitle("🧹 Orphaned Hints Cleanup")
        dialog.resize(600, 450)
        layout = QVBoxLayout(dialog)

        desc = QLabel(
            "The following orphaned AI hints were detected. These exist in your cards' "
            "JSON data but do not correspond to any active cards (likely because "
            "cloze deletions were removed or note types were changed)."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        list_widget = QListWidget()
        layout.addWidget(list_widget)

        for item in orphaned_hints:
            keys_str = ", ".join([opt[1] for opt in item["orphans"]])
            preview_text = f"📝 {item['preview']}\n   ❌ Orphaned Card Keys: {keys_str}"
            
            list_item = QListWidgetItem(preview_text)
            list_widget.addItem(list_item)

        tip_label = QLabel("💡 <i>Double-click an item or click 'Show in Browser' to view the note in Anki's Browser.</i>")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 2px; margin-bottom: 2px;")
        layout.addWidget(tip_label)

        btn_layout = QHBoxLayout()
        
        show_btn = QPushButton("🔍 Show in Browser")
        show_btn.setStyleSheet("padding: 6px; border-radius: 4px;")
        show_btn.setEnabled(False)
        
        clean_btn = QPushButton(f"🔥 Remove {len(orphaned_hints)} Orphaned Hints")
        clean_btn.setStyleSheet("font-weight: bold; background-color: #dc3545; color: white; padding: 6px; border-radius: 4px;")
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 6px;")
        
        btn_layout.addWidget(show_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(clean_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_show_card():
            selected_row = list_widget.currentRow()
            if selected_row < 0 or selected_row >= len(orphaned_hints):
                return
            item_data = orphaned_hints[selected_row]
            note_id = item_data["note_id"]
            query = f"nid:{note_id}"
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

        def on_selection_changed():
            show_btn.setEnabled(list_widget.currentRow() >= 0)

        list_widget.currentRowChanged.connect(on_selection_changed)
        list_widget.itemDoubleClicked.connect(on_show_card)
        show_btn.clicked.connect(on_show_card)


        def do_clean():
            mw.checkpoint("Clean Orphaned Hints")
            cleaned_count = 0
            logger.info(f"AI-Hints: Starting cleanup of orphaned hints in {len(orphaned_hints)} notes.")
            
            for item in orphaned_hints:
                note = item["note"]
                fields = list(note.keys())
                if not fields:
                    continue
                
                note_changed = False
                
                for f_name in fields:
                    val = note[f_name]
                    if not isinstance(val, str) or parser.json_class not in val:
                        continue
                    
                    pattern = re.compile(
                        rf'<div\b[^>]*class=["\'][^"\']*{parser.json_class}[^"\']*["\'][^>]*>(.*?)</div>',
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    
                    new_val = val
                    matches = list(pattern.finditer(val))
                    for match in reversed(matches):
                        block_html = match.group(0)
                        raw_payload = match.group(1)
                        try:
                            parsed = parser._parse_json_payload(raw_payload)
                            if isinstance(parsed, dict) and parser._is_keyed_payload(parsed):
                                keys_removed = 0
                                for opt in item["orphans"]:
                                    orphan_block = opt[0]
                                    orphan_key = opt[1]
                                    if block_html == orphan_block and orphan_key in parsed:
                                        del parsed[orphan_key]
                                        keys_removed += 1
                                
                                if keys_removed > 0:
                                    if parsed:
                                        new_payload = parser.serialize_json_payload(parsed)
                                        inner_match = re.search(r'>(.*?)</div>', block_html, re.DOTALL)
                                        if inner_match:
                                            new_block = block_html.replace(inner_match.group(1), new_payload)
                                            new_val = new_val[:match.start()] + new_block + new_val[match.end():]
                                            note_changed = True
                                    else:
                                        new_val = new_val[:match.start()] + new_val[match.end():]
                                        note_changed = True
                        except Exception as e:
                            logger.error(f"Error cleaning orphaned hint block in note {note.id}: {e}")
                
                if note_changed:
                    new_val = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', new_val, flags=re.IGNORECASE)
                    note[fields[0]] = new_val.strip()
                    mw.col.update_note(note)
                    cleaned_count += 1

            dialog.accept()
            mw.reset()
            logger.info(f"AI-Hints: Orphaned hints cleanup COMPLETED. Cleaned data in {cleaned_count} notes.")
            QMessageBox.information(
                self, "Cleanup Complete",
                f"🎉 Successfully cleaned up orphaned AI hints from {cleaned_count} notes!"
            )

        clean_btn.clicked.connect(do_clean)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def on_clean_naked_json(self):
        """Scans all notes and safely removes raw, naked JSON blocks not wrapped in AI div containers."""
        from aqt.qt import Qt, QProgressDialog, QApplication, QMessageBox
        from aqt.utils import askUser, showInfo
        import json
        import html
        import re

        query = self._get_maint_search_query()
        scope_str = "your entire collection" if not query else f"the deck '{self.maint_deck_cb.currentText()}'"

        if not askUser(f"This will scan {scope_str} and safely remove only legacy, un-wrapped ('naked/raw') JSON text blocks, while keeping the proper wrapped AI data completely untouched.\n\nContinue?"):
            return

        mw.checkpoint("Purge Naked JSON Blocks")

        nids = mw.col.find_notes(query)
        total = len(nids)
        if total == 0:
            showInfo(f"No notes found in the selected scope ({scope_str})!")
            return

        progress = QProgressDialog(f"Scanning and purging naked JSON in {scope_str}...", "Cancel", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(200)

        changed_count = 0
        logger.info(f"AI-Hints: Starting purge of naked JSON blocks in {scope_str}.")
        div_pattern = re.compile(
            r'<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )

        def find_json_candidates(text):
            candidates = []
            start = -1
            depth = 0
            for i, char in enumerate(text):
                if char == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif char == '}':
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start != -1:
                            candidates.append((start, i + 1, text[start:i+1]))
            return candidates

        for i, nid in enumerate(nids):
            if progress.wasCanceled():
                logger.info(f"AI-Hints: Naked JSON purge CANCELLED by user. Processed {i} notes, cleaned {changed_count}.")
                break
            progress.setValue(i)
            progress.setLabelText(f"Scanning note {i+1} of {total}...")
            QApplication.processEvents()

            try:
                note = mw.col.get_note(nid)
                note_changed = False

                for f_name in note.keys():
                    field_val = note[f_name]
                    if not isinstance(field_val, str) or '{' not in field_val:
                        continue

                    wrapped_ranges = [(m.start(), m.end()) for m in div_pattern.finditer(field_val)]
                    candidates = find_json_candidates(field_val)
                    if not candidates:
                        continue

                    field_changed = False
                    for start_idx, end_idx, candidate in reversed(candidates):
                        # Verify if this candidate is wrapped inside any ai-hints divs
                        is_wrapped = any(w_start <= start_idx and end_idx <= w_end for w_start, w_end in wrapped_ranges)
                        if is_wrapped:
                            continue

                        # Clean candidate of HTML tags and unescape for validation
                        clean_candidate = re.sub(r'<[^>]+>', '', candidate)
                        clean_candidate = html.unescape(clean_candidate).strip()

                        try:
                            parsed = json.loads(clean_candidate)
                            if isinstance(parsed, dict):
                                is_ai_hints = False
                                if "hints" in parsed or "options" in parsed or "correct_answer" in parsed:
                                    is_ai_hints = True
                                elif any(isinstance(val, dict) and ("hints" in val or "options" in val) for val in parsed.values()):
                                    is_ai_hints = True

                                if is_ai_hints:
                                    # Purge the naked JSON block and its surrounding whitespace/BR tags
                                    left_str = field_val[:start_idx]
                                    right_str = field_val[end_idx:]

                                    left_str = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', left_str, flags=re.IGNORECASE)
                                    right_str = re.sub(r'^(?:<br\s*/?>|\s|&nbsp;)+', '', right_str, flags=re.IGNORECASE)

                                    field_val = left_str + right_str
                                    field_changed = True
                        except Exception:
                            pass

                    if field_changed:
                        field_val = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', field_val, flags=re.IGNORECASE)
                        note[f_name] = field_val.strip()
                        note_changed = True

                if note_changed:
                    mw.col.update_note(note)
                    changed_count += 1

            except Exception as note_err:
                logger.error(f"Error purging naked JSON from note {nid}: {note_err}")

        progress.setValue(total)
        mw.reset()
        logger.info(f"AI-Hints: Naked JSON purge COMPLETED. Successfully cleaned naked JSON blocks from {changed_count} notes.")
        showInfo(
            f"🎉 Purge Complete!\n\n"
            f"Successfully scanned your collection and cleaned naked JSON blocks from {changed_count} notes."
        )

# --- Module Global Lifecycle functions ---
_config_dialog_instance = None

def on_config_dialog(parent=None, tab_index=None, card_ids=None, deck_name=None):
    global _config_dialog_instance
    dialog_parent = parent or mw
    if _config_dialog_instance is not None:
        try:
            if _config_dialog_instance.isVisible():
                 if tab_index is not None:
                     _config_dialog_instance.tabs.setCurrentIndex(tab_index)
                 if card_ids is not None:
                     _config_dialog_instance.set_selected_cards(card_ids)
                 if deck_name is not None:
                     _config_dialog_instance.set_selected_deck(deck_name)
                 _config_dialog_instance.raise_()
                 _config_dialog_instance.activateWindow()
                 return
        except (RuntimeError, AttributeError): 
            _config_dialog_instance = None

    _config_dialog_instance = ConfigDialog(dialog_parent, card_ids=card_ids, deck_name=deck_name)
    _config_dialog_instance.setWindowFlag(Qt.WindowType.Window, True)
    _config_dialog_instance.setWindowModality(Qt.WindowModality.NonModal)
    
    if tab_index is not None:
        _config_dialog_instance.tabs.setCurrentIndex(tab_index)
        
    QTimer.singleShot(50, _config_dialog_instance.show)

def _close_config_dialog_on_shutdown():
    global _config_dialog_instance
    if _config_dialog_instance:
        try:
            _config_dialog_instance.close()
        except Exception:
            pass
        _config_dialog_instance = None

def check_support_on_update():
    """Automatically opens the Support tab once after an update, unless opted out."""
    try:
        # 1. Get current version from VERSION file
        addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version_path = os.path.join(addon_dir, "VERSION")
        if not os.path.exists(version_path):
            return
        with open(version_path, "r", encoding="utf-8") as f:
            current_version = f.read().strip()

        # 2. Get meta state
        meta = mw.addonManager.addonMeta(ADDON_PACKAGE)
        last_version = meta.get("last_seen_version", "")
        opt_out = meta.get("supporter_opt_out", False)

        # 3. Trigger if version changed
        if current_version != last_version:
            meta["last_seen_version"] = current_version
            mw.addonManager.writeAddonMeta(ADDON_PACKAGE, meta)
            
            if not opt_out:
                # Delay the automatic window opening to ensure Anki is stable
                def _open_support():
                    if not mw or not mw.col:
                        return
                    # Open dialog and switch to Support tab (Index 6)
                    on_config_dialog(mw)
                    def _switch_tab():
                        if _config_dialog_instance:
                            _config_dialog_instance.tabs.setCurrentIndex(6)
                    QTimer.singleShot(1000, _switch_tab) # Wait for UI to stabilize
                
                QTimer.singleShot(5000, _open_support)
    except Exception as e:
        logger.error(f"AI-Hints: Update check failed: {e}")

def on_clean_orphaned_hints():
    """Run the orphaned-hints scan and show the cleanup dialog without opening the config window."""
    from aqt.qt import Qt, QProgressDialog, QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
    from .main_dialog import _show_orphans_cleanup_dialog_standalone
    _show_orphans_cleanup_dialog_standalone(mw)


def _show_orphans_cleanup_dialog_standalone(parent):
    """Standalone version of the orphan scan + cleanup dialog that does not require ConfigDialog."""
    from aqt.qt import Qt, QProgressDialog, QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
    from ..card_parser import CardParser
    import json, html, re

    parser = CardParser()

    # Always scan the full collection when launched from the Tools menu
    query = ""
    scope_str = "entire collection"

    nids = mw.col.find_notes(query)
    total = len(nids)
    if total == 0:
        QMessageBox.information(parent, "AI-Hints", "No notes found in your collection!")
        return

    progress = QProgressDialog(f"Scanning {scope_str} for orphaned hints...", "Cancel", 0, total, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(200)

    orphaned_hints = []
    logger.info(f"AI-Hints: Starting standalone scan for orphaned AI hints in {scope_str}.")

    for i, nid in enumerate(nids):
        if progress.wasCanceled():
            logger.info(f"AI-Hints: Orphaned hints scan CANCELLED by user. Processed {i} notes.")
            return
        progress.setValue(i)
        progress.setLabelText(f"Scanning note {i+1} of {total}...")
        QApplication.processEvents()

        try:
            note = mw.col.get_note(nid)
            raw_blocks = parser.find_all_hints_blocks(note)
            if not raw_blocks:
                continue

            active_ords = {c.ord for c in note.cards()}
            valid_keys = {f"c{ord + 1}" for ord in active_ords}

            note_orphans = []
            for block in raw_blocks:
                if parser.json_class in block:
                    m = re.search(
                        r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
                        block, re.DOTALL | re.IGNORECASE
                    )
                    if m:
                        raw = html.unescape(m.group(1) or "")
                        try:
                            parsed = json.loads(raw)
                        except Exception:
                            continue
                        if isinstance(parsed, dict) and parser._is_keyed_payload(parsed):
                            for key in list(parsed.keys()):
                                if re.fullmatch(r"c\d+", str(key)) and key not in valid_keys:
                                    note_orphans.append((block, key, parsed[key]))

            if note_orphans:
                first_field_val = list(note.values())[0] if note.values() else ""
                preview = parser._clean_html(first_field_val)[:60]
                if len(first_field_val) > 60:
                    preview += "..."
                orphaned_hints.append({
                    "note_id": nid,
                    "preview": preview or f"Note ID {nid}",
                    "orphans": note_orphans,
                    "note": note,
                })
        except Exception as e:
            logger.error(f"Error scanning note {nid} for orphans: {e}")

    progress.setValue(total)
    logger.info(f"AI-Hints: Standalone orphan scan COMPLETED. Found orphans in {len(orphaned_hints)} notes.")

    if not orphaned_hints:
        QMessageBox.information(parent, "Scan Complete", "🎉 No orphaned hints found! Your collection is perfectly clean.")
        return

    # --- Cleanup dialog ---
    dialog = QDialog(parent)
    dialog.setWindowTitle("🧹 Orphaned Hints Cleanup")
    dialog.resize(600, 450)
    layout = QVBoxLayout(dialog)

    desc = QLabel(
        "The following orphaned AI hints were detected. These exist in your cards' "
        "JSON data but do not correspond to any active cards (likely because "
        "cloze deletions were removed or note types were changed)."
    )
    desc.setWordWrap(True)
    layout.addWidget(desc)

    list_widget = QListWidget()
    layout.addWidget(list_widget)

    for item in orphaned_hints:
        keys_str = ", ".join([opt[1] for opt in item["orphans"]])
        preview_text = f"📝 {item['preview']}\n   ❌ Orphaned Card Keys: {keys_str}"
        list_widget.addItem(QListWidgetItem(preview_text))

    tip_label = QLabel("💡 <i>Double-click an item or click 'Show in Browser' to view the note in Anki's Browser.</i>")
    tip_label.setWordWrap(True)
    tip_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 2px; margin-bottom: 2px;")
    layout.addWidget(tip_label)

    btn_layout = QHBoxLayout()
    show_btn = QPushButton("🔍 Show in Browser")
    show_btn.setStyleSheet("padding: 6px; border-radius: 4px;")
    show_btn.setEnabled(False)
    clean_btn = QPushButton(f"🔥 Remove {len(orphaned_hints)} Orphaned Hints")
    clean_btn.setStyleSheet("font-weight: bold; background-color: #dc3545; color: white; padding: 6px; border-radius: 4px;")
    cancel_btn = QPushButton("Cancel")
    cancel_btn.setStyleSheet("padding: 6px;")
    btn_layout.addWidget(show_btn)
    btn_layout.addStretch()
    btn_layout.addWidget(clean_btn)
    btn_layout.addWidget(cancel_btn)
    layout.addLayout(btn_layout)

    def on_show_card():
        selected_row = list_widget.currentRow()
        if selected_row < 0 or selected_row >= len(orphaned_hints):
            return
        note_id = orphaned_hints[selected_row]["note_id"]
        query_str = f"nid:{note_id}"
        from aqt import dialogs
        browser = dialogs.open("Browser", mw)
        try:
            browser.search_for(query_str)
        except AttributeError:
            try:
                browser.search(query_str)
            except (AttributeError, TypeError):
                try:
                    try: browser.form.searchEdit.lineEdit().setText(query_str)
                    except AttributeError: browser.form.searchEdit.setText(query_str)
                    try: browser.search()
                    except (AttributeError, TypeError): browser.onSearchActivated()
                except Exception: pass
        browser.setFocus()
        browser.activateWindow()
        browser.raise_()

    def on_selection_changed():
        show_btn.setEnabled(list_widget.currentRow() >= 0)

    list_widget.currentRowChanged.connect(on_selection_changed)
    list_widget.itemDoubleClicked.connect(on_show_card)
    show_btn.clicked.connect(on_show_card)

    def do_clean():
        mw.checkpoint("Clean Orphaned Hints")
        cleaned_count = 0
        logger.info(f"AI-Hints: Starting cleanup of orphaned hints in {len(orphaned_hints)} notes.")
        for item in orphaned_hints:
            note = item["note"]
            fields = list(note.keys())
            if not fields:
                continue
            note_changed = False
            for f_name in fields:
                val = note[f_name]
                if not isinstance(val, str) or parser.json_class not in val:
                    continue
                pattern = re.compile(
                    rf'<div\b[^>]*class=["\'][^"\']*{parser.json_class}[^"\']*["\'][^>]*>(.*?)</div>',
                    flags=re.DOTALL | re.IGNORECASE,
                )
                new_val = val
                matches = list(pattern.finditer(val))
                for match in reversed(matches):
                    block_html = match.group(0)
                    raw_payload = match.group(1)
                    try:
                        parsed_block = parser._parse_json_payload(raw_payload)
                        if isinstance(parsed_block, dict) and parser._is_keyed_payload(parsed_block):
                            keys_removed = 0
                            for opt in item["orphans"]:
                                orphan_block = opt[0]
                                orphan_key = opt[1]
                                if block_html == orphan_block and orphan_key in parsed_block:
                                    del parsed_block[orphan_key]
                                    keys_removed += 1
                            if keys_removed > 0:
                                if parsed_block:
                                    new_payload = parser.serialize_json_payload(parsed_block)
                                    inner_match = re.search(r'>(.*?)</div>', block_html, re.DOTALL)
                                    if inner_match:
                                        new_block = block_html.replace(inner_match.group(1), new_payload)
                                        new_val = new_val[:match.start()] + new_block + new_val[match.end():]
                                        note_changed = True
                                else:
                                    new_val = new_val[:match.start()] + new_val[match.end():]
                                    note_changed = True
                    except Exception as e:
                        logger.error(f"Error cleaning orphaned hint block in note {note.id}: {e}")
            if note_changed:
                new_val = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', new_val, flags=re.IGNORECASE)
                note[fields[0]] = new_val.strip()
                mw.col.update_note(note)
                cleaned_count += 1

        dialog.accept()
        mw.reset()
        logger.info(f"AI-Hints: Orphaned hints cleanup COMPLETED. Cleaned data in {cleaned_count} notes.")
        QMessageBox.information(
            parent, "Cleanup Complete",
            f"🎉 Successfully cleaned up orphaned AI hints from {cleaned_count} notes!"
        )

    clean_btn.clicked.connect(do_clean)
    cancel_btn.clicked.connect(dialog.reject)
    dialog.exec()

def init_config_ui():
    from aqt import gui_hooks
    gui_hooks.profile_will_close.append(_close_config_dialog_on_shutdown)
    gui_hooks.profile_did_open.append(check_support_on_update)
    
    mw.addonManager.setConfigAction(ADDON_PACKAGE, on_config_dialog)

    # 1. Add "Clean Orphaned Hints" right below "Empty Cards..."
    orphan_action = QAction("Clean Orphaned Hints", mw)
    orphan_action.triggered.connect(on_clean_orphaned_hints)
    
    # Try to find actionEmpty_Cards or search text
    inserted = False
    try:
        tools_menu = mw.form.menuTools
        for action in tools_menu.actions():
            # Check for standard "Empty Cards..." text
            if action.text().replace("&", "") == "Empty Cards...":
                # Find the action AFTER it
                actions = tools_menu.actions()
                idx = actions.index(action)
                if idx + 1 < len(actions):
                    tools_menu.insertAction(actions[idx+1], orphan_action)
                else:
                    tools_menu.addAction(orphan_action)
                inserted = True
                break
    except Exception as e:
        logger.error(f"AI-Hints: Failed to insert menu item at specific location: {e}")

    if not inserted:
        # Fallback to appending if search fails
        mw.form.menuTools.addAction(orphan_action)

    # 2. Add Tools menu entry so the window can be opened any time
    action = mw.form.menuTools.addAction("AI-Hints Config")
    action.triggered.connect(lambda: on_config_dialog(mw))
