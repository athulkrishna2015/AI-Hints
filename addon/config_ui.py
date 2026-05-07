import os
import json
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, tooltip
from .logger import logger, get_logger
from .ai_client import DEFAULT_MODELS, LEGACY_MODEL_REPLACEMENTS, MODEL_FALLBACKS, PROVIDER_ORDER
import logging

# Resolve the top-level addon package name (e.g. 'ai_hints_dev' or 'AI-Hints')
ADDON_PACKAGE = __name__.split(".")[0]

class CustomProviderDialog(QDialog):
    def __init__(self, parent, name="", data=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Provider")
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit(name)
        if name:
            self.name_edit.setReadOnly(True)
            
        self.url_edit = QLineEdit(data.get("url", "") if data else "")
        self.key_edit = QLineEdit(data.get("api_key", "") if data else "")
        self.model_edit = QLineEdit(data.get("model", "") if data else "")
        self.headers_edit = QTextEdit()
        self.headers_edit.setPlainText(json.dumps(data.get("headers", {}), indent=2) if data else "{}")
        
        layout.addRow("Provider Name (ID):", self.name_edit)
        layout.addRow("Endpoint URL:", self.url_edit)
        layout.addRow("API Key:", self.key_edit)
        layout.addRow("Model Name:", self.model_edit)
        layout.addRow("Headers (JSON):", self.headers_edit)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def validate_and_accept(self):
        if not self.name_edit.text().strip():
            showInfo("Provider name cannot be empty.")
            return
        try:
            json.loads(self.headers_edit.toPlainText() or "{}")
        except Exception:
            showInfo("Headers must be valid JSON.")
            return
        self.accept()

class ConfigDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("AI-Hints Configuration")
        self.setMinimumSize(600, 700)
        self.addon_dir = os.path.dirname(__file__)
        self.config = self._normalize_config(mw.addonManager.getConfig(ADDON_PACKAGE) or {})
        self.custom_providers_data = self.config.get("custom_providers", {}) or {}
        
        self.setup_ui()
        self.load_config_into_ui()

        # Live Log Timer
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.load_log)
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index):
        if self.tabs.tabText(index) == "Logs":
            self.load_log()
            self.log_timer.start(2000)  # Refresh every 2 seconds
            if hasattr(self, "live_label"):
                self.live_label.setVisible(True)
        else:
            self.log_timer.stop()
            if hasattr(self, "live_label"):
                self.live_label.setVisible(False)

    def setup_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        # --- Tab 1: General Settings ---
        self.general_tab = QWidget()
        gen_layout = QFormLayout()
        
        self.ai_provider_cb = QComboBox()
        gen_layout.addRow("Active AI Provider:", self.ai_provider_cb)
        
        self.options_count_sb = QSpinBox()
        self.options_count_sb.setRange(1, 10)
        gen_layout.addRow("Number of Options:", self.options_count_sb)
        
        self.storage_mode_cb = QComboBox()
        self.storage_mode_cb.addItems(["json", "html"])
        self.storage_mode_cb.setToolTip("JSON: Invisible (cleaner). HTML: Visible on all devices.")
        gen_layout.addRow("Storage Mode:", self.storage_mode_cb)
        
        self.show_hints_cb = QCheckBox("Show Hints Button")
        gen_layout.addRow(self.show_hints_cb)
        
        self.show_options_cb = QCheckBox("Show Options Button (Sequential)")
        gen_layout.addRow(self.show_options_cb)
        
        self.general_tab.setLayout(gen_layout)
        self.tabs.addTab(self.general_tab, "General")
        
        # --- Tab 2: AI Providers (API Keys) ---
        self.providers_tab = QWidget()
        prov_main_layout = QVBoxLayout()
        
        prov_scroll = QScrollArea()
        prov_scroll.setWidgetResizable(True)
        prov_content = QWidget()
        self.prov_layout = QFormLayout(prov_content)
        
        provider_urls = {
            "openai": "https://platform.openai.com/api-keys",
            "anthropic": "https://console.anthropic.com/",
            "gemini": "https://aistudio.google.com/app/apikey",
            "groq": "https://console.groq.com/keys",
            "deepseek": "https://platform.deepseek.com/api_keys",
            "openrouter": "https://openrouter.ai/keys",
            "mistral": "https://console.mistral.ai/api-keys/",
            "together": "https://api.together.xyz/settings/api-keys",
            "huggingface": "https://huggingface.co/settings/tokens",
            "sambanova": "https://cloud.sambanova.ai/apis",
            "cerebras": "https://cloud.cerebras.ai/",
            "grok": "https://console.x.ai/",
            "nvidia": "https://build.nvidia.com/explore/discover"
        }
        
        self.api_key_edits = {}
        self.model_edits = {}
        
        free_providers = ["gemini", "groq", "openrouter", "huggingface", "sambanova", "cerebras"]
        free_group = QGroupBox("Free / Freemium Providers")
        free_layout = QFormLayout()
        for p in free_providers:
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_edits[p] = edit
            
            url = provider_urls.get(p)
            label_text = f"<a href='{url}' style='color: #008CBA; text-decoration: none;'>{p.capitalize()} API Key:</a>" if url else f"{p.capitalize()} API Key:"
            label = QLabel(label_text)
            label.setOpenExternalLinks(True)
            free_layout.addRow(label, edit)
        free_group.setLayout(free_layout)
        self.prov_layout.addRow(free_group)
        
        paid_providers = ["openai", "anthropic", "deepseek", "mistral", "together", "nvidia", "grok"]
        paid_group = QGroupBox("Paid Providers")
        paid_layout = QFormLayout()
        for p in paid_providers:
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_edits[p] = edit
            
            url = provider_urls.get(p)
            label_text = f"<a href='{url}' style='color: #008CBA; text-decoration: none;'>{p.capitalize()} API Key:</a>" if url else f"{p.capitalize()} API Key:"
            label = QLabel(label_text)
            label.setOpenExternalLinks(True)
            paid_layout.addRow(label, edit)
        paid_group.setLayout(paid_layout)
        self.prov_layout.addRow(paid_group)
            
        # Local Endpoint Group
        local_group = QGroupBox("Local AI / Ollama Settings")
        local_layout = QFormLayout()
        self.local_url_edit = QLineEdit()
        self.local_model_edit = QLineEdit()
        self.local_api_key_edit = QLineEdit()
        self.local_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.local_fallback_cb = QCheckBox("Use Local AI as fallback")
        local_layout.addRow(self.local_fallback_cb)
        local_layout.addRow("Base URL:", self.local_url_edit)
        local_layout.addRow("Model Name:", self.local_model_edit)
        local_layout.addRow("API Key (optional):", self.local_api_key_edit)
        local_group.setLayout(local_layout)
        self.prov_layout.addRow(local_group)

        model_group = QGroupBox("Model Names")
        model_layout = QFormLayout()
        for p in PROVIDER_ORDER:
            if p == "local":
                continue
            edit = QLineEdit()
            edit.setPlaceholderText(DEFAULT_MODELS.get(p, ""))
            self.model_edits[p] = edit
            model_layout.addRow(f"{p.capitalize()} model:", edit)
        model_group.setLayout(model_layout)
        self.prov_layout.addRow(model_group)
        
        # Custom Providers Group
        custom_group = QGroupBox("Custom Providers")
        custom_layout = QVBoxLayout()
        
        self.custom_list = QListWidget()
        custom_layout.addWidget(self.custom_list)
        
        cbtn_layout = QHBoxLayout()
        self.add_custom_btn = QPushButton("Add")
        self.add_custom_btn.clicked.connect(self.on_add_custom)
        self.edit_custom_btn = QPushButton("Edit")
        self.edit_custom_btn.clicked.connect(self.on_edit_custom)
        self.remove_custom_btn = QPushButton("Remove")
        self.remove_custom_btn.clicked.connect(self.on_remove_custom)
        
        cbtn_layout.addWidget(self.add_custom_btn)
        cbtn_layout.addWidget(self.edit_custom_btn)
        cbtn_layout.addWidget(self.remove_custom_btn)
        custom_layout.addLayout(cbtn_layout)
        
        custom_group.setLayout(custom_layout)
        self.prov_layout.addRow(custom_group)
        
        prov_scroll.setWidget(prov_content)
        prov_main_layout.addWidget(prov_scroll)
        self.providers_tab.setLayout(prov_main_layout)
        self.tabs.addTab(self.providers_tab, "AI Providers")
        
        # --- Tab 3: Advanced ---
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()
        
        adv_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_edit = QTextEdit()
        adv_layout.addWidget(self.system_prompt_edit)
        
        adv_layout.addWidget(QLabel("Note Type Fields:"))
        
        if mw.col is not None:
            self.nt_selector_layout = QVBoxLayout()
            self.nt_cb = QComboBox()
            self.nt_cb.currentIndexChanged.connect(self.on_nt_changed)
            self.nt_selector_layout.addWidget(self.nt_cb)
            
            self.fld_list = QListWidget()
            self.fld_list.itemChanged.connect(self.on_fld_changed)
            self.nt_selector_layout.addWidget(self.fld_list)
            
            adv_layout.addLayout(self.nt_selector_layout)
            
            self.note_fields_edit = QTextEdit()
            self.note_fields_edit.setVisible(False)
        else:
            adv_layout.addWidget(QLabel("(Raw JSON editor since collection is closed)"))
            self.note_fields_edit = QTextEdit()
            self.note_fields_edit.setMaximumHeight(150)
            adv_layout.addWidget(self.note_fields_edit)
        
        # Raw Editor Toggle
        self.raw_toggle = QPushButton("Show Raw JSON Editor")
        self.raw_toggle.setCheckable(True)
        adv_layout.addWidget(self.raw_toggle)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)
        
        self.advanced_tab.setLayout(adv_layout)
        self.tabs.addTab(self.advanced_tab, "Advanced")
        
        # --- Tab 4: Support ---
        self.support_tab = self._create_support_tab()
        self.tabs.addTab(self.support_tab, "Support")
        
        # --- Tab 5: Logs ---
        self.log_tab = self._create_log_tab()
        self.tabs.addTab(self.log_tab, "Logs")
        
        layout.addWidget(self.tabs)
        
        # --- Bottom Buttons ---
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.save_config)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.setLayout(layout)

    def _create_log_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Level filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.log_level_cb = QComboBox()
        self.log_level_cb.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_cb.currentIndexChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_level_cb)
        filter_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_log)
        filter_layout.addWidget(refresh_btn)

        self.live_label = QLabel("● Live")
        self.live_label.setStyleSheet("color: green; font-weight: bold;")
        self.live_label.setVisible(False)
        filter_layout.addWidget(self.live_label)
        
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(lambda: (
            QApplication.clipboard().setText(self.log_view.toPlainText()),
            tooltip("Log copied to clipboard")
        ))
        filter_layout.addWidget(copy_btn)
        
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clear_log)
        filter_layout.addWidget(clear_btn)
        
        layout.addLayout(filter_layout)
        
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.log_view)
        
        self.load_log()
        return tab

    def load_log(self):
        log_file = os.path.join(self.addon_dir, "ai_hints.log")
        if not os.path.exists(log_file):
            self.log_view.setPlainText("No log file found yet. Errors will appear here after using the add-on.")
            return
        
        level_filter = self.log_level_cb.currentText()
        
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            if level_filter != "ALL":
                lines = [l for l in lines if f" - {level_filter} - " in l]
            
            self.log_view.setPlainText("".join(lines) if lines else "No entries matching the selected level.")
            # Scroll to bottom
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        except Exception as e:
            self.log_view.setPlainText(f"Error reading log: {e}")

    def clear_log(self):
        log_file = os.path.join(self.addon_dir, "ai_hints.log")
        try:
            open(log_file, "w", encoding="utf-8").close()
            self.log_view.setPlainText("Log cleared.")
            logger.info("Log cleared by user.")
        except Exception as e:
            showInfo(f"Could not clear log: {e}")

    def _create_support_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        s_layout = QVBoxLayout(content)
        
        support_data = [
            {"name": "Ko-fi", "id": "https://ko-fi.com/D1D01W6NQT", "qr": None, "is_link": True},
            {"name": "UPI", "id": "athulkrishnasv2015-2@okhdfcbank", "qr": "UPI.jpg"},
            {"name": "Bitcoin (BTC)", "id": "bc1qrrek3m7sr33qujjrktj949wav6mehdsk057cfx", "qr": "BTC.jpg"},
            {"name": "Ethereum (ETH)", "id": "0xce6899e4903EcB08bE5Be65E44549fadC3F45D27", "qr": "ETH.jpg"}
        ]
        
        for item in support_data:
            group = QGroupBox(item["name"])
            gl = QVBoxLayout()
            if item.get("qr"):
                qr_label = QLabel()
                qr_path = os.path.join(self.addon_dir, "Support", item["qr"])
                if os.path.exists(qr_path):
                    pixmap = QPixmap(qr_path)
                    qr_label.setPixmap(pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    gl.addWidget(qr_label)
            
            id_layout = QHBoxLayout()
            id_text = QLineEdit(item["id"])
            id_text.setReadOnly(True)
            id_layout.addWidget(id_text)
            if item.get("is_link"):
                btn = QPushButton("Open")
                btn.clicked.connect(lambda chk, u=item["id"]: QDesktopServices.openUrl(QUrl(u)))
                id_layout.addWidget(btn)
            else:
                btn = QPushButton("Copy")
                btn.clicked.connect(lambda chk, t=item["id"]: self.copy_to_clipboard(t))
                id_layout.addWidget(btn)
            gl.addLayout(id_layout)
            group.setLayout(gl)
            s_layout.addWidget(group)
            
        s_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        tab.setLayout(layout)
        return tab

    def load_config_into_ui(self):
        c = self.config
        self.refresh_custom_list()
        self.ai_provider_cb.setCurrentText(c.get("ai_provider", "openai"))
        self.options_count_sb.setValue(c.get("options_count", 4))
        self.storage_mode_cb.setCurrentText(c.get("storage_mode", "json"))
        self.show_hints_cb.setChecked(c.get("show_hints_button", True))
        self.show_options_cb.setChecked(c.get("show_options_button", True))
        
        keys = c.get("api_keys", {}) or {}
        for p, edit in self.api_key_edits.items():
            edit.setText(keys.get(p, ""))

        models = c.get("models", {}) or {}
        for p, edit in self.model_edits.items():
            edit.setText(models.get(p, DEFAULT_MODELS.get(p, "")))
            
        local = c.get("local_endpoint", {}) or {}
        self.local_url_edit.setText(local.get("base_url", ""))
        self.local_model_edit.setText(local.get("model", ""))
        self.local_api_key_edit.setText(local.get("api_key", ""))
        self.local_fallback_cb.setChecked(local.get("enabled", False))
        
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        
        self.note_type_fields_data = c.get("note_type_fields", {})
        if hasattr(self, 'nt_cb'):
            self.nt_cb.blockSignals(True)
            self.nt_cb.clear()
            self.models_cache = {m['name']: m['flds'] for m in mw.col.models.all()}
            self.nt_cb.addItems(list(self.models_cache.keys()))
            self.nt_cb.blockSignals(False)
            if self.nt_cb.count() > 0:
                self.nt_cb.setCurrentIndex(0)
                self.on_nt_changed()
        
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
        
        current_selection = self.ai_provider_cb.currentText()
        self.ai_provider_cb.clear()
        providers = PROVIDER_ORDER
        self.ai_provider_cb.addItems(providers + list(self.custom_providers_data.keys()))
        if current_selection:
            self.ai_provider_cb.setCurrentText(current_selection)

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

    def save_config(self):
        try:
            if self.raw_toggle.isChecked():
                raw_config = json.loads(self.raw_editor.toPlainText() or "{}")
                mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(raw_config))
                self.accept()
                return

            new_config = self.config.copy()
            new_config["ai_provider"] = self.ai_provider_cb.currentText()
            new_config["options_count"] = self.options_count_sb.value()
            new_config["storage_mode"] = self.storage_mode_cb.currentText()
            new_config["show_hints_button"] = self.show_hints_cb.isChecked()
            new_config["show_options_button"] = self.show_options_cb.isChecked()
            
            new_config["api_keys"] = {p: edit.text().strip() for p, edit in self.api_key_edits.items()}
            new_config["models"] = {
                p: (edit.text().strip() or DEFAULT_MODELS.get(p, ""))
                for p, edit in self.model_edits.items()
            }
            new_config["local_endpoint"] = {
                "enabled": self.local_fallback_cb.isChecked(),
                "base_url": self.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "model": self.local_model_edit.text().strip() or DEFAULT_MODELS["local"],
                "api_key": self.local_api_key_edit.text().strip()
            }
            new_config["system_prompt"] = self.system_prompt_edit.toPlainText()
            
            if hasattr(self, 'nt_cb'):
                new_config["note_type_fields"] = self.note_type_fields_data
            else:
                new_config["note_type_fields"] = json.loads(self.note_fields_edit.toPlainText())
            
            new_config["custom_providers"] = self.custom_providers_data
            mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(new_config))
            self.accept()
        except Exception as e:
            showInfo(f"Error saving configuration: {e}")

    def _normalize_config(self, config):
        config = dict(config or {})

        api_keys = dict(config.get("api_keys", {}) or {})
        for provider in PROVIDER_ORDER:
            if provider != "local":
                api_keys.setdefault(provider, "")
        config["api_keys"] = api_keys

        models = dict(DEFAULT_MODELS)
        models.update(config.get("models", {}) or {})
        for provider, model in list(models.items()):
            models[provider] = LEGACY_MODEL_REPLACEMENTS.get((provider, model), model)
        config["models"] = models

        model_fallbacks = {
            provider: list(fallbacks)
            for provider, fallbacks in MODEL_FALLBACKS.items()
        }
        model_fallbacks.update(config.get("model_fallbacks", {}) or {})
        config["model_fallbacks"] = model_fallbacks

        local = {
            "enabled": False,
            "base_url": "http://localhost:11434/v1",
            "model": DEFAULT_MODELS["local"],
            "api_key": "",
        }
        local.update(config.get("local_endpoint", {}) or {})
        config["local_endpoint"] = local

        config.setdefault("custom_providers", {})
        config.setdefault("note_type_fields", {})
        return config

_config_dialog_instance = None

def on_config_dialog(parent=None):
    global _config_dialog_instance
    if parent is None: parent = mw
    # Reuse existing window if already open
    if _config_dialog_instance is not None and _config_dialog_instance.isVisible():
        _config_dialog_instance.raise_()
        _config_dialog_instance.activateWindow()
        return
    _config_dialog_instance = ConfigDialog(parent)
    _config_dialog_instance.setWindowFlag(Qt.WindowType.Window, True)
    _config_dialog_instance.show()

def init_config_ui():
    mw.addonManager.setConfigAction(ADDON_PACKAGE, on_config_dialog)
    
    # Add Tools menu entry so the window can be opened any time
    action = mw.form.menuTools.addAction("AI-Hints Config")
    action.triggered.connect(lambda: on_config_dialog(mw))
