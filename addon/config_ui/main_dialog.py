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

# Import Support Widgets
from .widgets import CustomProviderDialog, ProviderRowWidget, ADDON_PACKAGE

LAST_ACTIVE_TAB_INDEX = 6  # Fallback static state

class ConfigDialog(QDialog, GeneralTabMixin, ProvidersTabMixin, AdvancedTabMixin, 
                   ShortcutsTabMixin, BatchTabMixin, SupportTabMixin, LogTabMixin):
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("AI-Hints Configuration")
        self.setModal(False)
        self.setMinimumSize(600, 700)
        self.addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
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
        # Defer initial tab handler so it runs AFTER the dialog is displayed.
        # Running it synchronously here would call load_log() (file I/O) on the
        # main thread during construction, causing Anki to freeze.
        QTimer.singleShot(0, lambda: self.on_tab_changed(self.tabs.currentIndex()))

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        
        # Handle Note Type Loading
        if tab_name == "Advanced":
            self._load_note_types_if_needed()

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

    def _load_note_types_if_needed(self):
        """Heavy operation: only call when Advanced tab is actually viewed."""
        if not hasattr(self, 'nt_cb') or self.nt_cb.count() > 0:
            return
            
        logger.debug("AI-Hints: Lazy-loading note types for Advanced tab.")
        self.nt_cb.blockSignals(True)
        self.nt_cb.clear()
        
        # This is the heavy collection scan
        self.models_cache = {m['name']: m['flds'] for m in mw.col.models.all()}
        self.nt_cb.addItems(list(self.models_cache.keys()))
        
        self.nt_cb.blockSignals(False)
        if self.nt_cb.count() > 0:
            self.nt_cb.setCurrentIndex(0)
            self.on_nt_changed()

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
        support = self._create_support_tab()
        logs = self._create_log_tab()
        
        # Assemble Tabs in desired visual order
        self.tabs.addTab(general, "General")
        self.tabs.addTab(providers, "AI Providers")
        self.tabs.addTab(advanced, "Advanced")
        self.tabs.addTab(shortcuts, "Shortcuts")
        self.tabs.addTab(batch, "Batch Generation")
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
        
        btn_layout.addStretch()
        
        save_btn = QPushButton("Save && Close")
        save_btn.clicked.connect(self.save_config)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def load_config_into_ui(self):
        c = self.config
        self.refresh_custom_list()
        self.ai_provider_cb.setCurrentText(c.get("ai_provider", "openai"))
        self.options_count_sb.setValue(c.get("options_count", 4))
        self.storage_mode_cb.setCurrentText(c.get("storage_mode", "json"))
        self.mathjax_format_cb.setCurrentText(c.get("mathjax_format", "delimiters"))
        self.fix_latex_cb.setChecked(c.get("fix_latex", False))
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
        self.auto_show_hints_cb.setChecked(c.get("auto_show_hints", False))
        self.auto_show_options_cb.setChecked(c.get("auto_show_options", False))
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
            
        ag_model = models.get("antigravity", DEFAULT_MODELS.get("antigravity", ""))
        if self.ag_model_edit.findText(ag_model) == -1:
            self.ag_model_edit.addItem(ag_model)
        self.ag_model_edit.setCurrentText(ag_model)
            
        ag_cfg = c.get("antigravity_proxy", {}) or {}
        self.ag_enable_cb.setChecked(ag_cfg.get("enabled", False))
            
        local = c.get("local_endpoint", {}) or {}
        self.local_url_edit.setText(local.get("base_url", ""))
        model_name = local.get("model", "")
        if self.local_model_edit.findText(model_name) == -1:
            self.local_model_edit.addItem(model_name)
        self.local_model_edit.setCurrentText(model_name)
        self.local_api_key_edit.setText(local.get("api_key", ""))
        self.local_fallback_cb.setChecked(local.get("enabled", False))
        
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        
        self.target_fields_edit.setText(", ".join(c.get("target_fields", [])))
        self.note_type_fields_data = c.get("note_type_fields", {})
        
        if hasattr(self, 'note_fields_edit'):
             self.note_fields_edit.setPlainText(json.dumps(self.note_type_fields_data, indent=4))
        self.raw_editor.setPlainText(json.dumps(c, indent=4))

    def copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        tooltip("Copied to clipboard")

    def on_nt_changed(self):
        self.fld_list.blockSignals(True)
        self.fld_list.clear()
        nt_name = self.nt_cb.currentText()
        if not nt_name:
            self.fld_list.blockSignals(False)
            return
            
        flds = self.models_cache.get(nt_name, [])
        active_flds = self.note_type_fields_data.get(nt_name, [])
        
        for fld in flds:
            item = QListWidgetItem(fld["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if fld["name"] in active_flds:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.fld_list.addItem(item)
            
        self.fld_list.blockSignals(False)

    def on_fld_changed(self, item):
        nt_name = self.nt_cb.currentText()
        if not nt_name: return
        
        fld_name = item.text()
        active_flds = self.note_type_fields_data.get(nt_name, [])
        
        if item.checkState() == Qt.CheckState.Checked:
            if fld_name not in active_flds:
                active_flds.append(fld_name)
        else:
            if fld_name in active_flds:
                active_flds.remove(fld_name)
                
        if active_flds:
            self.note_type_fields_data[nt_name] = active_flds
        elif nt_name in self.note_type_fields_data:
            del self.note_type_fields_data[nt_name]

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
            for p in new_priority:
                w = ProviderRowWidget(p, self)
                if p in current_models_state:
                    w.edit.setCurrentText(current_models_state[p])
                elif p in self.config.get("models", {}):
                    w.edit.setCurrentText(self.config["models"][p])
                self.model_edits[p] = w.edit
                self.models_layout.addWidget(w)
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
        tooltip("Starting batch model fetch...")
        for provider, combobox in self.model_edits.items():
            self.on_fetch_models(provider, combobox, silent=True)
        self.on_fetch_models("antigravity", self.ag_model_edit, silent=True)
        self.on_fetch_models("local", self.local_model_edit, silent=True)
        tooltip("Finished fetching models for all configured providers.")

    def on_test_model(self, provider, combobox):
        """Runs a real-world test generation using the currently selected model."""
        model_name = combobox.currentText().strip()
        if not model_name:
            info(f"Please select or enter a model name for {provider.capitalize()} first.")
            return

        api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
        if not api_key and provider not in ["local", "antigravity"]:
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
            # Note: We assume proxy is running for the test. 
            # If not, the request will fail naturally.

        client = AIClient(temp_config)
        combobox.setEnabled(False)
        tooltip(f"Testing {provider.capitalize()} model: {model_name}...")

        def _run_test():
            try:
                # Use a simple test prompt
                test_front = "What is the capital of France?"
                test_back = "Paris"
                
                # We use generate_options directly to test the full pipeline
                res = client.generate_options(test_front, test_back, override_provider=provider)
                
                def _done():
                    combobox.setEnabled(True)
                    if res and (res.get("hints") or res.get("options")):
                        hints_count = len(res.get("hints", []))
                        opts_count = len(res.get("options", []))
                        info(f"✅ Success! {provider.capitalize()} is working.\n\n"
                             f"Model: {model_name}\n"
                             f"Result: Generated {hints_count} hints and {opts_count} options.")
                    else:
                        info(f"❌ Test Failed for {provider.capitalize()}.\n\n"
                             f"The provider returned an empty response. Check your API key, "
                             f"model name, and account balance.")
                mw.taskman.run_on_main(_done)
                
            except Exception as e:
                def _fail():
                    combobox.setEnabled(True)
                    info(f"❌ Test Error ({provider.capitalize()}):\n\n{str(e)}")
                mw.taskman.run_on_main(_fail)

        import threading
        threading.Thread(target=_run_test, daemon=True).start()

    def on_fetch_models(self, provider, combobox, silent=False):
        api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
        if not api_key and provider not in ["local", "antigravity"]:
            if not silent:
                info(f"Please enter an API key for {provider.capitalize()} first.")
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
        try:
            models = client.fetch_models(provider)
            if models:
                current_text = combobox.currentText()
                combobox.clear()
                models = sorted(list(set(models)))
                if current_text and current_text not in models: models.insert(0, current_text)
                combobox.addItems(models)
                if current_text: combobox.setCurrentText(current_text)
                if not silent: tooltip(f"Found {len(models)} models for {provider.capitalize()}")
            else:
                if not silent: info(f"Could not fetch models for {provider.capitalize()}. Check connection.")
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            if not silent: info(f"Error fetching models: {e}")
        finally:
            combobox.setEnabled(True)

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
        self.storage_mode_cb.setCurrentText(c.get("storage_mode", "json"))
        self.mathjax_format_cb.setCurrentText(c.get("mathjax_format", "delimiters"))
        self.fix_latex_cb.setChecked(c.get("fix_latex", False))
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
        self.auto_show_hints_cb.setChecked(c.get("auto_show_hints", False))
        self.auto_show_options_cb.setChecked(c.get("auto_show_options", False))
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
        self.target_fields_edit.setText(", ".join(c.get("target_fields", [])))
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        self.note_type_fields_data = c.get("note_type_fields", {}).copy()
        self.on_nt_changed()
        if hasattr(self, 'note_fields_edit'): self.note_fields_edit.setPlainText(json.dumps(self.note_type_fields_data, indent=4))
        tooltip("Advanced defaults restored.")

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
            new_config["storage_mode"] = self.storage_mode_cb.currentText()
            new_config["mathjax_format"] = self.mathjax_format_cb.currentText()
            new_config["fix_latex"] = self.fix_latex_cb.isChecked()
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
            new_config["auto_show_hints"] = self.auto_show_hints_cb.isChecked()
            new_config["auto_show_options"] = self.auto_show_options_cb.isChecked()
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
            new_config["target_fields"] = [f.strip() for f in self.target_fields_edit.text().split(",") if f.strip()]
            if hasattr(self, 'nt_cb'): new_config["note_type_fields"] = self.note_type_fields_data
            else: new_config["note_type_fields"] = json.loads(self.note_fields_edit.toPlainText())
            new_config["custom_providers"] = self.custom_providers_data
            priority = []
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget): priority.append(w.provider)
            new_config["provider_priority"] = priority
            mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(new_config))
            try:
                from ..proxy_manager import proxy_manager
                proxy_manager.start(new_config)
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
        config.setdefault("target_fields", [])
        config.setdefault("system_prompt", "")
        config.setdefault("show_hints_button", True)
        config.setdefault("show_options_button", True)
        if not isinstance(config.get("custom_providers", {}), dict): config["custom_providers"] = {}
        else: config.setdefault("custom_providers", {})
        if not isinstance(config.get("note_type_fields", {}), dict): config["note_type_fields"] = {}
        else: config.setdefault("note_type_fields", {})
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
        config.setdefault("auto_show_hints", False)
        config.setdefault("auto_show_options", False)
        config.setdefault("manual_show_hints", True)
        config.setdefault("manual_show_options", False)
        default_shortcuts = {"modifier": "alt", "generate": "1", "toggle-options": "2", "toggle-hints": "3", "clear": "4", "refresh": "5", "show-json": "6"}
        shortcuts = dict(default_shortcuts)
        raw_shortcuts = config.get("shortcuts", {}) or {}
        if isinstance(raw_shortcuts, dict): shortcuts.update(raw_shortcuts)
        config["shortcuts"] = shortcuts
        return config

# --- Module Global Lifecycle functions ---
_config_dialog_instance = None

def on_config_dialog(parent=None):
    global _config_dialog_instance
    dialog_parent = None
    if _config_dialog_instance is not None:
        try:
            if _config_dialog_instance.isVisible():
                 _config_dialog_instance.raise_()
                 _config_dialog_instance.activateWindow()
                 return
        except RuntimeError: _config_dialog_instance = None
    _config_dialog_instance = ConfigDialog(dialog_parent)
    _config_dialog_instance.setWindowFlag(Qt.WindowType.Window, True)
    _config_dialog_instance.setWindowModality(Qt.WindowModality.NonModal)
    QTimer.singleShot(50, _config_dialog_instance.show)

def init_config_ui():
    mw.addonManager.setConfigAction(ADDON_PACKAGE, on_config_dialog)
    # Add Tools menu entry so the window can be opened any time
    action = mw.form.menuTools.addAction("AI-Hints Config")
    action.triggered.connect(lambda: on_config_dialog(mw))
