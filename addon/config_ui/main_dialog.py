import os
import json
import time
from aqt import mw
from aqt.utils import askUser
from aqt.qt import *
from ..logger import logger, info, tooltip
from ..ai_client import (
    DEFAULT_MODELS, 
    LEGACY_MODEL_REPLACEMENTS, 
    MODEL_FALLBACKS, 
    PROVIDER_ORDER, 
    AIClient,
    derive_active_provider,
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
from .widgets import (CustomProviderDialog, ProviderRowWidget, ADDON_PACKAGE,
                      PERSISTENT_TEST_STATUSES, FETCH_CANCELLATIONS,
                      NEWLY_ADDED_MODELS, MISSING_FROM_FETCH,
                      GLOBAL_NEWLY_ADDED_MODELS, GLOBAL_MISSING_FROM_FETCH)
from .tab_providers import cancel_other_model_tests, TEST_CANCELLATIONS
from ..config_io import write_pretty_config_preserve_keys

LAST_ACTIVE_TAB_INDEX = 7  # Fallback static state

def _set_test_status(status_label, provider, st, tt, col, model_name):
    PERSISTENT_TEST_STATUSES[provider] = (st, tt, col, model_name)
    status_label.setText(st)
    status_label.setToolTip(tt)
    status_label.setStyleSheet(f"font-weight: bold; color: {col}; margin-left: 5px;")

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
        # Prefer the on-disk meta.json: addonManager.getConfig() falls back to
        # config.json defaults when the addon package name does not resolve to
        # this addon's folder, and a defaults-based snapshot would then destroy
        # the user's real config on the next save.
        from ..config_io import read_meta_config
        disk_config = read_meta_config()
        if isinstance(disk_config, dict) and disk_config:
            self.config = self._normalize_config(disk_config)
        else:
            self.config = self._normalize_config(mw.addonManager.getConfig(ADDON_PACKAGE) or {})
        
        # Load default config for restoration
        try:
            with open(os.path.join(self.addon_dir, "config.json"), "r", encoding="utf-8") as f:
                self.default_config = json.load(f)
        except Exception as e:
            logger.error(f"Could not load default config: {e}")
            self.default_config = {}

        self.custom_providers_data = (self.config.get("custom_providers", {}) or {}).copy()
        self.local_providers_data = (self.config.get("local_providers", {}) or {}).copy()
        
        NEWLY_ADDED_MODELS.clear()
        MISSING_FROM_FETCH.clear()
        GLOBAL_NEWLY_ADDED_MODELS.clear()
        GLOBAL_MISSING_FROM_FETCH.clear()
        
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

        # Wire the "Update Now" button for model lists (if present).
        if hasattr(self, "update_models_now_btn"):
            self.update_models_now_btn.clicked.connect(self._update_models_now)

        # Unsaved-changes tracking for the close warning.
        self._dirty = False
        self._connect_dirty_tracking()

        # Defer initial tab handler so it runs AFTER the dialog is displayed.
        # Running it synchronously here would call load_log() (file I/O) on the
        # main thread during construction, causing Anki to freeze.
        QTimer.singleShot(0, lambda: self.on_tab_changed(self.tabs.currentIndex()))

    def _mark_dirty(self, *args):
        self._dirty = True

    def _connect_dirty_tracking(self):
        """Mark the dialog as dirty when the user edits any config control."""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab is None:
                continue
            # The live Logs tab updates its text constantly; ignore it.
            if self.tabs.tabText(i) == "Logs":
                continue
            for w in tab.findChildren(QWidget):
                try:
                    if isinstance(w, QCheckBox):
                        w.toggled.connect(self._mark_dirty)
                    elif isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QKeySequenceEdit)):
                        if hasattr(w, "isReadOnly") and w.isReadOnly():
                            continue
                        w.textChanged.connect(self._mark_dirty)
                    elif isinstance(w, QComboBox):
                        w.currentIndexChanged.connect(self._mark_dirty)
                        w.currentTextChanged.connect(self._mark_dirty)
                    elif isinstance(w, (QSpinBox, QDoubleSpinBox, QDateTimeEdit)):
                        w.valueChanged.connect(self._mark_dirty)
                except Exception:
                    pass

    def reject(self):
        super().reject()

    def closeEvent(self, event):
        event.accept()

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
        """Proxy integration removed; keep this as a no-op for compatibility."""
        return

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
        save_only_btn.setToolTip("Saves configuration and syncs mobile without closing the window.")
        save_only_btn.clicked.connect(lambda: self.save_config(close=False))
        save_only_btn.setDefault(True)
        btn_layout.addWidget(save_only_btn)

        save_close_btn = QPushButton("Save && Close")
        save_close_btn.setToolTip("Saves configuration and syncs mobile, then closes the window.")
        save_close_btn.clicked.connect(lambda: self.save_config(close=True))
        btn_layout.addWidget(save_close_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without saving.")
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
        """Load configuration values into UI elements."""
        c = self.config
        # Provider rows read these during construction — assign before
        self.model_fallbacks_data = (c.get("model_fallbacks", {}) or {}).copy()
        disabled_models = c.get("disabled_fallback_models", {}) or {}
        if not isinstance(disabled_models, dict):
            disabled_models = {}
        self.disabled_fallback_models_data = disabled_models.copy()
        transient_skip = c.get("transient_skip_providers", {}) or {}
        if not isinstance(transient_skip, dict):
            transient_skip = {}
        self.transient_skip_data = {p: list(v or []) for p, v in transient_skip.items()}
        self.refresh_custom_list()
        self.options_count_sb.setValue(c.get("options_count", 4))
        self.fix_latex_cb.setChecked(c.get("fix_latex", False))
        self.answer_display_position_cb.setCurrentText(c.get("answer_display_position", "between"))
        self.show_hints_cb.setChecked(c.get("show_hints_button", True))
        self.show_options_cb.setChecked(c.get("show_options_button", True))
        self.show_on_card_cb.setChecked(c.get("show_on_card", True))
        if hasattr(self, "show_in_bottom_bar_cb"):
            self.show_in_bottom_bar_cb.setChecked(c.get("show_in_bottom_bar", False))
        if hasattr(self, "show_in_popup_cb"):
            self.show_in_popup_cb.setChecked(c.get("show_in_popup", False))

        if hasattr(self, 'auto_clear_cb'):
            self.auto_clear_cb.setChecked(c.get("auto_clear_logs", True))
        if hasattr(self, 'debug_logging_cb'):
            self.debug_logging_cb.setChecked(c.get("debug_logging", False))

        self.auto_generate_new_cb.setChecked(c.get("auto_generate_new", False))
        self.auto_regenerate_if_modified_cb.setChecked(c.get("auto_regenerate_if_modified", False))
        self.auto_regenerate_if_modified_cb.setEnabled(self.auto_generate_new_cb.isChecked())
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
        if hasattr(self, "auto_update_models_cb"):
            self.auto_update_models_cb.setChecked(c.get("auto_update_models", True))

    def _update_models_now(self):
        try:
            from ..model_updater import run_auto_update
            import threading
            def _run():
                summary = run_auto_update()
                removed = summary.get("removed", 0)
                errors = summary.get("errors", [])
                msg = f"Model lists updated. Pruned {removed} deprecated/removed entr{'y' if removed == 1 else 'ies'}."
                if errors:
                    msg += " Errors: " + "; ".join(errors[:3])
                try:
                    from aqt.utils import tooltip
                    tooltip(msg)
                except Exception:
                    pass
            threading.Thread(target=_run, daemon=True, name="ai-hints-model-update-now").start()
            try:
                from aqt.utils import tooltip
                tooltip("Updating model lists in the background...")
            except Exception:
                pass
        except Exception as e:
            try:
                from aqt.utils import tooltip
                tooltip(f"Model update failed: {e}")
            except Exception:
                pass

    def save_config(self, close=True):
        try:
            if hasattr(self, 'raw_toggle') and self.raw_toggle.isChecked():
                raw_config = json.loads(self.raw_editor.toPlainText() or "{}")
                from ..config_io import write_pretty_config
                write_pretty_config(ADDON_PACKAGE, self._normalize_config(raw_config))
                NEWLY_ADDED_MODELS.clear()
                MISSING_FROM_FETCH.clear()
                GLOBAL_NEWLY_ADDED_MODELS.clear()
                GLOBAL_MISSING_FROM_FETCH.clear()
                self._dirty = False
                if close: self.accept()
                else: tooltip("Configuration saved.")
                return True
            new_config = self.config.copy()
            new_config["options_count"] = self.options_count_sb.value()
            new_config["fix_latex"] = self.fix_latex_cb.isChecked()
            new_config["answer_display_position"] = self.answer_display_position_cb.currentText()
            new_config["show_hints_button"] = self.show_hints_cb.isChecked()
            new_config["show_options_button"] = self.show_options_cb.isChecked()
            new_config["show_on_card"] = self.show_on_card_cb.isChecked()
            if hasattr(self, "show_in_bottom_bar_cb"):
                new_config["show_in_bottom_bar"] = self.show_in_bottom_bar_cb.isChecked()
            else:
                new_config["show_in_bottom_bar"] = False
            if hasattr(self, "show_in_popup_cb"):
                new_config["show_in_popup"] = self.show_in_popup_cb.isChecked()
            else:
                new_config["show_in_popup"] = False
            if hasattr(self, 'auto_clear_cb'):
                new_config["auto_clear_logs"] = self.auto_clear_cb.isChecked()
            if hasattr(self, 'debug_logging_cb'):
                new_config["debug_logging"] = self.debug_logging_cb.isChecked()
            new_config["auto_generate_new"] = self.auto_generate_new_cb.isChecked()
            new_config["auto_regenerate_if_modified"] = self.auto_regenerate_if_modified_cb.isChecked()
            new_config["auto_regenerate_all"] = self.auto_regenerate_all_cb.isChecked()
            new_config["auto_regenerate_if_old_version"] = self.auto_regenerate_old_version_cb.isChecked()
            new_config["auto_regenerate_min_version"] = self.auto_regenerate_min_version_edit.text().strip()
            new_config["auto_regenerate_if_old_time"] = self.auto_regenerate_old_time_cb.isChecked()
            new_config["auto_regenerate_min_time"] = self.auto_regenerate_min_time_edit.text().strip()
            new_config["pre_generate_next"] = self.pre_generate_next_cb.isChecked()
            new_config["pre_generate_count"] = self.pre_generate_count_spin.value()
            new_config["pregen_direct_save"] = self.pregen_direct_save_cb.isChecked()
            new_config["generate_hints_enabled"] = self.generate_hints_enabled_cb.isChecked()
            new_config["generate_options_enabled"] = self.generate_options_enabled_cb.isChecked()
            new_config["auto_show_hints"] = self.auto_show_hints_cb.isChecked()
            new_config["auto_show_options"] = self.auto_show_options_cb.isChecked()
            new_config["auto_show_hints_answer"] = self.auto_show_hints_answer_cb.isChecked()
            new_config["auto_show_options_answer"] = self.auto_show_options_answer_cb.isChecked()
            if hasattr(self, "options_before_hints_cb"):
                new_config["options_before_hints"] = self.options_before_hints_cb.isChecked()
            if hasattr(self, "rate_good_on_correct_cb"):
                new_config["rate_good_on_correct"] = self.rate_good_on_correct_cb.isChecked()
                new_config["rate_good_delay_ms"] = int(self.rate_good_delay_spin.value() * 1000)
            if hasattr(self, "rate_again_on_wrong_cb"):
                new_config["rate_again_on_wrong"] = self.rate_again_on_wrong_cb.isChecked()
                new_config["rate_again_delay_ms"] = int(self.rate_again_delay_spin.value() * 1000)
            if hasattr(self, "tag_hinted_notes_cb"):
                new_config["tag_hinted_notes"] = self.tag_hinted_notes_cb.isChecked()
                new_config["hint_tag"] = self.hint_tag_edit.text().strip() or "ai-hints"
            if hasattr(self, "auto_update_models_cb"):
                new_config["auto_update_models"] = self.auto_update_models_cb.isChecked()
            if hasattr(self, "tag_skipped_notes_cb"):
                new_config["tag_skipped_notes"] = self.tag_skipped_notes_cb.isChecked()
                new_config["skip_tag"] = self.skip_tag_edit.text().strip() or "ai-hints::skipped"
            new_config["manual_show_hints"] = self.manual_show_hints_cb.isChecked()
            new_config["manual_show_options"] = self.manual_show_options_cb.isChecked()
            if hasattr(self, "maint_only_modified_cb"):
                new_config["maint_only_modified"] = self.maint_only_modified_cb.isChecked()
            new_config["shortcuts"] = {key: edit.text().strip() for key, edit in self.shortcut_edits.items()}
            
            # Save primary shortcut modifiers
            prim_list = []
            if self.mod_ctrl.isChecked(): prim_list.append("ctrl")
            if self.mod_alt.isChecked(): prim_list.append("alt")
            if self.mod_shift.isChecked(): prim_list.append("shift")
            if self.mod_meta.isChecked(): prim_list.append("meta")
            new_config["shortcuts"]["modifier"] = "+".join(prim_list) if prim_list else "none"

            # Save select options modifier
            opt_list = []
            if self.opt_ctrl.isChecked(): opt_list.append("ctrl")
            if self.opt_alt.isChecked(): opt_list.append("alt")
            if self.opt_shift.isChecked(): opt_list.append("shift")
            if self.opt_meta.isChecked(): opt_list.append("meta")
            new_config["shortcuts"]["select-options-modifier"] = "+".join(opt_list) if opt_list else "none"
            new_config["shortcuts"]["select-options-keys"] = self.select_options_keys_edit.text().strip()
            def _safe_key(p, edit):
                try:
                    return edit.text().strip()
                except RuntimeError:
                    return self.config.get("api_keys", {}).get(p, "")
            def _safe_model(p, edit):
                try:
                    return edit.currentText().strip() or DEFAULT_MODELS.get(p, "")
                except RuntimeError:
                    return self.config.get("models", {}).get(p, DEFAULT_MODELS.get(p, ""))
            _existing_keys = self.config.get("api_keys", {}) or {}
            if not isinstance(_existing_keys, dict):
                _existing_keys = {}
            _edited_keys = {p: _safe_key(p, edit) for p, edit in self.api_key_edits.items()}
            for _p, _e in _edited_keys.items():
                if not _e and _existing_keys.get(_p):
                    _edited_keys[_p] = _existing_keys.get(_p)
            # Preserve any stored keys whose provider is not shown as an edit row.
            for _p, _e in _existing_keys.items():
                _edited_keys.setdefault(_p, _e)
            new_config["api_keys"] = _edited_keys
            new_config["models"] = {p: _safe_model(p, edit) for p, edit in self.model_edits.items()}
            new_config["local_providers"] = self.local_providers_data
            new_config["system_prompt"] = self.default_config.get("system_prompt", "")
            new_config["additional_system_instructions"] = self.system_prompt_edit.toPlainText()
            new_config["custom_providers"] = self.custom_providers_data
            new_config["model_fallbacks"] = self.model_fallbacks_data
            new_config["disabled_fallback_models"] = self.disabled_fallback_models_data
            new_config["transient_skip_providers"] = getattr(self, "transient_skip_data", {})
            new_config["thinking_levels"] = self.thinking_levels_data
            new_config["model_timeouts"] = self.model_timeouts_data
            new_config["global_model_priority"] = self.global_model_priority_data
            new_config["disabled_global_model_priority"] = self.disabled_global_model_priority_data
            new_config["global_thinking_levels"] = self.global_thinking_levels_data
            new_config["global_model_timeouts"] = self.global_model_timeouts_data
            new_config["use_global_model_priority"] = self.advanced_fallback_cb.isChecked()
            new_config["test_question_front"] = self.test_question_edit.text().strip()
            new_config["test_question_back"] = self.test_answer_edit.text().strip()
            if hasattr(self, "cooldown_spin"):
                new_config["model_cooldown_minutes"] = self.cooldown_spin.value()
                
            if hasattr(self, "backoff_spin"):
                new_config["rate_limit_backoff_seconds"] = self.backoff_spin.value()

            if hasattr(self, "ignore_net_cb"):
                new_config["ignore_network_checks"] = self.ignore_net_cb.isChecked()
                
            if hasattr(self, "timeout_spin"):
                new_config["request_timeout"] = self.timeout_spin.value()
                
            if hasattr(self, "pregen_timeout_spin"):
                new_config["pregen_request_timeout"] = self.pregen_timeout_spin.value()
            if hasattr(self, "batch_timeout_spin"):
                new_config["batch_request_timeout"] = self.batch_timeout_spin.value()
            if hasattr(self, "batch_linger_cb"):
                new_config["batch_linger_on_timeout"] = self.batch_linger_cb.isChecked()
            if hasattr(self, "provider_timeout_spins"):
                new_config["provider_timeouts"] = {
                    provider: spin.value()
                    for provider, spin in self.provider_timeout_spins.items()
                    if spin.value() > 0
                }
                
            if hasattr(self, "font_size_combo"):
                font_size = self.font_size_combo.currentText().strip()
                if font_size == "inherit":
                    font_size = ""
                new_config["hints_font_size"] = font_size

            if hasattr(self, "batch_limit_spin"):
                new_config["batch_limit"] = self.batch_limit_spin.value()
                
            if hasattr(self, "batch_multithread_cb"):
                new_config["multithread_providers"] = self.batch_multithread_cb.isChecked()
            if hasattr(self, "batch_full_scan_cb"):
                new_config["batch_full_scan"] = self.batch_full_scan_cb.isChecked()

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
            from ..config_io import write_pretty_config_preserve_keys
            write_pretty_config_preserve_keys(ADDON_PACKAGE, self._normalize_config(new_config))
            NEWLY_ADDED_MODELS.clear()
            MISSING_FROM_FETCH.clear()
            GLOBAL_NEWLY_ADDED_MODELS.clear()
            GLOBAL_MISSING_FROM_FETCH.clear()
            try:
                from ..mobile_sync import auto_update_mobile_setup
                auto_update_mobile_setup() # Silently update if setup was already completed
            except Exception: pass
            # Apply debug_logging level change immediately (no restart needed)
            try:
                import logging
                from ..logger import logger as _aih_logger
                _aih_logger.setLevel(logging.DEBUG if new_config.get("debug_logging", False) else logging.INFO)
            except Exception: pass
            self.config = new_config
            self._dirty = False
            if close: self.accept()
            else: tooltip("Configuration saved.")
            return True
        except Exception as e:
            info(f"Error saving configuration: {e}")
            return False

    def refresh_local_providers_list(self):
        if hasattr(ProvidersTabMixin, "refresh_local_providers_list"):
            return ProvidersTabMixin.refresh_local_providers_list(self)

    def update_local_provider_labels(self):
        if hasattr(ProvidersTabMixin, "update_local_provider_labels"):
            return ProvidersTabMixin.update_local_provider_labels(self)

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
        config.setdefault("disabled_providers", [])
        derived = derive_active_provider(config)
        if derived:
            config["ai_provider"] = derived
        local = {"enabled": False, "base_url": "http://localhost:11434/v1", "model": DEFAULT_MODELS.get("local", ""), "api_key": ""}
        raw_local = config.get("local_endpoint", {}) or {}
        if isinstance(raw_local, dict): local.update(raw_local)
        config["local_endpoint"] = local
        local_providers = config.get("local_providers", {}) or {}
        if not isinstance(local_providers, dict):
            local_providers = {}
        if not local_providers and local.get("base_url"):
            local_providers = {
                "local": {
                    "url": local.get("base_url", "http://localhost:11434/v1"),
                    "base_url": local.get("base_url", "http://localhost:11434/v1"),
                    "api_key": local.get("api_key", ""),
                    "model": local.get("model", DEFAULT_MODELS.get("local", "")),
                    "headers": {},
                    "enabled": local.get("enabled", False),
                }
            }
        config["local_providers"] = local_providers
        config.setdefault("ai_provider", "openai")
        config.setdefault("mathjax_format", "delimiters")
        config.setdefault("fix_latex", False)
        config.setdefault("answer_display_position", "between")
        config.setdefault("system_prompt", "")
        config.setdefault("additional_system_instructions", "")
        config.setdefault("show_hints_button", True)
        config.setdefault("show_options_button", True)
        if not isinstance(config.get("custom_providers", {}), dict): config["custom_providers"] = {}
        else: config.setdefault("custom_providers", {})
        if not isinstance(config.get("local_providers", {}), dict): config["local_providers"] = {}
        else: config.setdefault("local_providers", {})
        try: config["options_count"] = max(1, min(int(config.get("options_count", 4)), 10))
        except: config["options_count"] = 4
        config.setdefault("show_on_card", True)
        config.setdefault("show_in_bottom_bar", False)
        config.setdefault("show_in_popup", False)
        config.setdefault("auto_clear_logs", True)
        config.setdefault("debug_logging", False)
        config.setdefault("request_timeout", 60)
        config.setdefault("pregen_request_timeout", 60)
        config.setdefault("batch_request_timeout", 120)
        config.setdefault("provider_timeouts", {})
        config.setdefault("auto_generate_new", False)
        config.setdefault("auto_regenerate_if_modified", False)
        config.setdefault("auto_regenerate_all", False)
        config.setdefault("auto_regenerate_if_old_version", False)
        config.setdefault("auto_regenerate_min_version", "")
        config.setdefault("auto_regenerate_if_old_time", False)
        config.setdefault("auto_regenerate_min_time", "")
        config.setdefault("config_version", 3)
        config.setdefault("auto_show_hints", True)
        config.setdefault("auto_show_options", True)
        config.setdefault("auto_show_hints_answer", True)
        config.setdefault("auto_show_options_answer", True)
        config.setdefault("options_before_hints", True)
        config.setdefault("generate_hints_enabled", True)
        config.setdefault("generate_options_enabled", True)
        config.setdefault("manual_show_hints", True)
        config.setdefault("manual_show_options", False)
        config.setdefault("maint_only_modified", True)
        config.setdefault("batch_full_scan", False)
        config.setdefault("tag_hinted_notes", True)
        config.setdefault("tag_skipped_notes", True)
        config.setdefault("auto_update_models", True)
        
        # Mobile Support Defaults
        config.setdefault("mobile_use_emojis", False)
        config.setdefault("mobile_show_extra_buttons", False)
        config.setdefault("mobile_setup_completed", False)

        default_shortcuts = {
            "modifier": "alt", 
            "generate": "1", 
            "toggle-options": "3", 
            "toggle-hints": "2", 
            "clear": "4", 
            "refresh": "5", 
            "show-json": "6",
            "select-options-modifier": "none",
            "select-options-keys": "1-9"
        }
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

        from ..config_io import get_orphans_check_time, set_orphans_check_time
        last_check = get_orphans_check_time()
        
        # Only check modified notes if checkbox is checked and we have a previous clean timestamp
        only_modified = hasattr(self, "maint_only_modified_cb") and self.maint_only_modified_cb.isChecked()
        
        time_filter_msg = ""
        if only_modified and last_check > 0:
            elapsed_seconds = max(0.0, time.time() - last_check)
            elapsed_days = int(elapsed_seconds / 86400) + 1
            if query:
                query = f"({query}) edited:{elapsed_days}"
            else:
                query = f"edited:{elapsed_days}"
            time_filter_msg = f" (modified in the last {elapsed_days} day(s))"

        parser = CardParser()

        nids = mw.col.find_notes(query)
        total = len(nids)
        if total == 0:
            if only_modified and last_check > 0:
                set_orphans_check_time(int(time.time()))
            QMessageBox.information(self, "AI-Hints", f"No notes found in the selected scope ({scope_str}){time_filter_msg}!")
            return

        # Show a progress dialog
        progress = QProgressDialog(f"Scanning {scope_str}{time_filter_msg} for orphaned hints...", "Cancel", 0, total, self)
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
                note_orphans = parser.get_orphaned_hints(note)

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
        _log_orphaned_results(orphaned_hints, is_standalone=False)

        if not orphaned_hints:
            set_orphans_check_time(int(time.time()))
            QMessageBox.information(self, "Scan Complete", "🎉 No orphaned hints found! Your collection is perfectly clean.")
            return

        self._show_orphans_cleanup_dialog(orphaned_hints, parser)

    def _show_orphans_cleanup_dialog(self, orphaned_hints, parser):
        """Displays a dialog showing all orphaned hints found and allows safe cleanup."""
        _build_orphans_cleanup_dialog(self, orphaned_hints, parser)

    def on_tag_all_hinted(self):
        """Tags every note that already contains AI-Hints data with the configured hint tag,
        so the fast batch-scan mode can skip them. Skips and cleared cards aren't tagged."""
        from aqt.qt import Qt, QProgressDialog, QApplication, QMessageBox
        from aqt.utils import askUser
        from ..reviewer_hooks import _note_set_tag

        hint_tag = self.hint_tag_edit.text().strip() or "ai-hints"
        query = self._get_maint_search_query()
        scope_str = "your entire collection" if not query else f"the deck '{self.maint_deck_cb.currentText()}'"

        if not askUser(
            f"This will scan {scope_str} and tag every note that already contains saved AI-Hints "
            f"data with the tag '{hint_tag}'. Skipped and cleared notes are NOT tagged.\n\n"
            f"Run this once to enable fast batch scanning on cards created before tagging was on.\n\nContinue?"
        ):
            return

        nids = mw.col.find_notes(query)
        total = len(nids)
        if total == 0:
            QMessageBox.information(self, "Tag All", "No notes found in the selected scope!")
            return

        progress = QProgressDialog(f"Scanning {scope_str} for existing AI-Hints data...", "Cancel", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(200)

        tagged_count = 0
        for i, nid in enumerate(nids):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Scanning note {i + 1} of {total}...")
            QApplication.processEvents()
            try:
                note = mw.col.get_note(nid)
                if hint_tag in note.tags:
                    continue
                has_hint_data = any(
                    "ai-hints-json" in value or "ai-hints-container" in value
                    for value in note.values()
                )
                if not has_hint_data:
                    continue
                if _note_set_tag(note, hint_tag, True):
                    mw.col.update_note(note)
                    tagged_count += 1
            except Exception as e:
                logger.error(f"AI-Hints: Error tagging note {nid}: {e}")
        progress.setValue(total)

        mw.reset()
        if tagged_count:
            logger.info(f"AI-Hints: Tagged {tagged_count} notes with '{hint_tag}'.")
            QMessageBox.information(
                self,
                "Tagging Complete",
                f"🏷️ Tagged {tagged_count} existing notes with '{hint_tag}'."
                "\n\nFast batch scanning can now skip these cards.",
            )
        else:
            QMessageBox.information(
                self,
                "Tagging Complete",
                "No notes with existing AI-Hints data needed tagging.",
            )

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

        from ..card_parser import find_json_candidates

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

    def on_clear_pregen_cache(self):
        """Clears the transient pre-generation disk cache."""
        try:
            from ..reviewer_hooks import _pregenerated_data
            count = len(_pregenerated_data)
            if count == 0:
                tooltip("Pregen cache is already empty.")
                return
            
            if not askUser(f"Are you sure you want to clear {count} pre-generated hints from the disk cache?"):
                return
                
            _pregenerated_data.clear()
            tooltip(f"Successfully cleared {count} items from pregen cache.")
        except Exception as e:
            logger.error(f"Failed to clear pregen cache: {e}")
            info(f"Failed to clear pregen cache: {e}")

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

def _build_orphans_cleanup_dialog(parent, orphaned_hints, parser):
    """Shared orphaned-hints cleanup dialog behind the config tab and the Tools-menu entry."""
    from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QMessageBox
    from ..config_io import set_orphans_check_time
    import re

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
    btn_layout.addWidget(show_btn)
    btn_layout.addStretch()
    btn_layout.addWidget(clean_btn)
    layout.addLayout(btn_layout)

    def on_show_card():
        selected_row = list_widget.currentRow()
        if selected_row < 0 or selected_row >= len(orphaned_hints):
            return
        query_str = f"nid:{orphaned_hints[selected_row]['note_id']}"
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
                                    new_val = new_val[:match.start(1)] + new_payload + new_val[match.end(1):]
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
        set_orphans_check_time(int(time.time()))
        logger.info(f"AI-Hints: Orphaned hints cleanup COMPLETED. Cleaned data in {cleaned_count} notes.")
        QMessageBox.information(
            parent, "Cleanup Complete",
            f"🎉 Successfully cleaned up orphaned AI hints from {cleaned_count} notes!"
        )

    clean_btn.clicked.connect(do_clean)
    dialog.setModal(False)
    dialog.show()
    mw._orphaned_hints_dialog = dialog
    return dialog


def on_clean_orphaned_hints(query="", scope_str="entire collection"):
    """Run the orphaned-hints scan and show the cleanup dialog without opening the config window."""
    if not isinstance(query, str):
        query = ""
    if not isinstance(scope_str, str):
        scope_str = "entire collection"
    _show_orphans_cleanup_dialog_standalone(mw, query, scope_str)


def _show_orphans_cleanup_dialog_standalone(parent, query="", scope_str="entire collection"):
    """Standalone version of the orphan scan + cleanup dialog that does not require ConfigDialog."""
    if not isinstance(query, str):
        query = ""
    if not isinstance(scope_str, str):
        scope_str = "entire collection"
    from aqt.qt import Qt, QProgressDialog, QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
    from ..card_parser import CardParser
    import json, html, re

    from .widgets import ADDON_PACKAGE
    from ..config_io import get_orphans_check_time, set_orphans_check_time
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    last_check = get_orphans_check_time()
    
    # Check config settings first to respect user checkbox preference at all times
    only_modified = config.get("maint_only_modified", True)
    from .main_dialog import _config_dialog_instance
    if _config_dialog_instance and hasattr(_config_dialog_instance, "maint_only_modified_cb"):
        only_modified = _config_dialog_instance.maint_only_modified_cb.isChecked()
    
    time_filter_msg = ""
    if only_modified and last_check > 0:
        elapsed_seconds = max(0.0, time.time() - last_check)
        elapsed_days = int(elapsed_seconds / 86400) + 1
        if query:
            query = f"({query}) edited:{elapsed_days}"
        else:
            query = f"edited:{elapsed_days}"
        time_filter_msg = f" (modified in the last {elapsed_days} day(s))"

    parser = CardParser()

    nids = mw.col.find_notes(query)
    total = len(nids)
    if total == 0:
        if only_modified and last_check > 0:
            set_orphans_check_time(int(time.time()))
        QMessageBox.information(parent, "AI-Hints", f"No notes found in {scope_str}{time_filter_msg}!")
        return

    progress = QProgressDialog(f"Scanning {scope_str}{time_filter_msg} for orphaned hints...", "Cancel", 0, total, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(200)

    orphaned_hints = []
    logger.info(f"AI-Hints: Starting standalone scan for orphaned AI hints in {scope_str}{time_filter_msg}.")

    for i, nid in enumerate(nids):
        if progress.wasCanceled():
            logger.info(f"AI-Hints: Orphaned hints scan CANCELLED by user. Processed {i} notes.")
            return
        progress.setValue(i)
        progress.setLabelText(f"Scanning note {i+1} of {total}...")
        QApplication.processEvents()

        try:
            note = mw.col.get_note(nid)
            note_orphans = parser.get_orphaned_hints(note)

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
    _log_orphaned_results(orphaned_hints, is_standalone=True)

    if not orphaned_hints:
        set_orphans_check_time(int(time.time()))
        QMessageBox.information(parent, "Scan Complete", "🎉 No orphaned hints found! Your collection is perfectly clean.")
        return

    _build_orphans_cleanup_dialog(parent, orphaned_hints, parser)

def _log_orphaned_results(orphaned_hints, is_standalone=False):
    prefix = "Standalone orphan scan" if is_standalone else "Orphaned hints scan"
    if not orphaned_hints:
        logger.info(f"AI-Hints: {prefix} COMPLETED. Found orphans in 0 notes.")
        return

    orphaned_details = []
    for item in orphaned_hints:
        nid = item["note_id"]
        note_obj = item["note"]
        card_info = []
        for block, key, val in item["orphans"]:
            try:
                ord_idx = int(key[1:]) - 1
                cid = None
                if hasattr(note_obj, "cards") and callable(note_obj.cards):
                    for c in note_obj.cards():
                        if c.ord == ord_idx:
                            cid = c.id
                            break
                if cid is not None:
                    card_info.append(f"{key} (Card ID: {cid})")
                else:
                    card_info.append(f"{key} (No Card ID)")
            except Exception:
                card_info.append(key)
        orphaned_details.append(f"Note ID: {nid} -> {', '.join(card_info)}")

    details_str = "\n  - " + "\n  - ".join(orphaned_details)
    logger.info(f"AI-Hints: {prefix} COMPLETED. Found orphans in {len(orphaned_hints)} notes.{details_str}")

def init_config_ui():
    from aqt import gui_hooks
    gui_hooks.profile_will_close.append(_close_config_dialog_on_shutdown)
    gui_hooks.profile_did_open.append(check_support_on_update)
    
    mw.addonManager.setConfigAction(ADDON_PACKAGE, on_config_dialog)

    from aqt.qt import QAction
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
