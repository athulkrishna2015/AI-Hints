import os
from aqt import mw
from aqt.qt import *
from ..logger import info, tooltip
from ..ai_client import DEFAULT_MODELS, MODEL_SUGGESTIONS, MODEL_FALLBACKS
from .widgets import ProviderRowWidget, PERSISTENT_TEST_STATUSES, FETCH_CANCELLATIONS

class FallbackOrderDialog(QDialog):
    def __init__(self, parent, provider, current_list, suggestions):
        super().__init__(parent)
        self.main_dialog = parent
        self.provider = provider
        
        self.setWindowTitle(f"Fallback Priority: {provider.capitalize()}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Configure the list of models to try if the primary model fails.<br/>"
            "Drag & Drop to reorder, or uncheck to temporarily disable fallback to it."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        self.list_widget = QListWidget()
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDropIndicatorShown(True)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        disabled_models = getattr(parent, "disabled_fallback_models_data", {}).get(provider, [])
        for m in current_list:
            item = QListWidgetItem(m)
            item.setData(Qt.ItemDataRole.UserRole, m)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if m in disabled_models else Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.up_btn = QPushButton("Move Up")
        self.up_btn.clicked.connect(lambda: self.move_item(-1))
        self.down_btn = QPushButton("Move Down")
        self.down_btn.clicked.connect(lambda: self.move_item(1))
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.remove_item)
        
        self.list_test_btn = QPushButton("Test All")
        self.list_test_btn.setFixedWidth(70)
        self.list_test_btn.setToolTip("Test all models in the list sequentially.")
        self.list_test_btn.clicked.connect(self.on_test_from_list)
        
        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setFixedWidth(80)
        self.list_fetch_btn.setToolTip("Fetch available models from this provider's API.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_from_list)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset the list back to code defaults.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        btn_layout.addWidget(self.up_btn)
        btn_layout.addWidget(self.down_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.list_test_btn)
        btn_layout.addWidget(self.list_fetch_btn)
        btn_layout.addWidget(self.restore_btn)
        layout.addLayout(btn_layout)
        
        # OK / Cancel
        dlg_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dlg_btns.accepted.connect(self.accept)
        dlg_btns.rejected.connect(self.reject)
        layout.addWidget(dlg_btns)

    def on_fetch_from_list(self):
        fetch_key = f"{self.provider}_fallback"
        if fetch_key in FETCH_CANCELLATIONS:
            # User clicked again to Stop/Cancel
            FETCH_CANCELLATIONS[fetch_key] = True
            self.list_fetch_btn.setText("Fetch All")
            return

        FETCH_CANCELLATIONS[fetch_key] = False
        self.list_fetch_btn.setText("Stop Fetch")
        self.list_test_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        
        api_key = self.main_dialog.api_key_edits[self.provider].text().strip() if self.provider in self.main_dialog.api_key_edits else ""
        if not api_key and self.provider not in ["local", "antigravity"]:
            info(f"Please enter an API key for {self.provider.capitalize()} first.")
            self.list_fetch_btn.setText("Fetch All")
            self.list_test_btn.setEnabled(True)
            self.restore_btn.setEnabled(True)
            del FETCH_CANCELLATIONS[fetch_key]
            return
            
        temp_config = self.main_dialog.config.copy()
        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
        temp_config["api_keys"][self.provider] = api_key
        if self.provider == "local":
            temp_config["local_endpoint"] = {
                "base_url": self.main_dialog.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "api_key": self.main_dialog.local_api_key_edit.text().strip()
            }
            
        import threading
        from ..ai_client import AIClient
        
        tooltip(f"Fetching models for {self.provider.capitalize()}...")
        
        def _runner():
            try:
                if FETCH_CANCELLATIONS.get(fetch_key):
                    return
                client = AIClient(temp_config)
                models = client.fetch_models(self.provider)
                if FETCH_CANCELLATIONS.get(fetch_key):
                    return
                    
                def _update_ui():
                    if models:
                        models_clean = sorted(list(set(models)))
                        # Get existing model names in the list widget
                        existing = [self.list_widget.item(j).data(Qt.ItemDataRole.UserRole) for j in range(self.list_widget.count())]
                        existing_set = set(existing)
                        
                        added_count = 0
                        for m in models_clean:
                            if m and m not in existing_set:
                                item = QListWidgetItem(m)
                                item.setData(Qt.ItemDataRole.UserRole, m)
                                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                                # Unchecked by default
                                item.setCheckState(Qt.CheckState.Unchecked)
                                self.list_widget.addItem(item)
                                added_count += 1
                                
                        tooltip(f"Fetched {len(models_clean)} models ({added_count} new added).")
                    else:
                        info(f"Could not fetch models for {self.provider.capitalize()}. Check connection.")
                mw.taskman.run_on_main(_update_ui)
            except Exception as e:
                def _fail_err():
                    info(f"Error fetching models: {e}")
                mw.taskman.run_on_main(_fail_err)
            finally:
                if fetch_key in FETCH_CANCELLATIONS:
                    del FETCH_CANCELLATIONS[fetch_key]
                def _enable():
                    self.list_fetch_btn.setText("Fetch All")
                    self.list_test_btn.setEnabled(True)
                    self.restore_btn.setEnabled(True)
                mw.taskman.run_on_main(_enable)
                
        threading.Thread(target=_runner, daemon=True).start()
 
    def on_test_from_list(self):
        self.list_test_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        
        # Collect all models from items
        models = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_widget.count())]
        
        import threading
        from ..ai_client import AIClient
        
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            for i, model in enumerate(models):
                # Update item state to Testing
                def _update_testing(idx=i, name=model):
                    item = self.list_widget.item(idx)
                    item.setText(f"{name} (⏳ Testing...)")
                mw.taskman.run_on_main(_update_testing)
                
                status = "✅ Working"
                try:
                    # Prepare temporary config for this model
                    temp_config = self.main_dialog.config.copy()
                    api_key = self.main_dialog.api_key_edits[self.provider].text().strip() if self.provider in self.main_dialog.api_key_edits else ""
                    if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                    temp_config["api_keys"][self.provider] = api_key
                    if "models" not in temp_config: temp_config["models"] = {}
                    temp_config["models"][self.provider] = model
                    
                    if self.provider == "local":
                        temp_config["local_endpoint"] = {
                            "base_url": self.main_dialog.local_url_edit.text().strip() or "http://localhost:11434/v1",
                            "api_key": self.main_dialog.local_api_key_edit.text().strip(),
                            "model": model
                        }
                    if self.provider == "antigravity":
                        temp_config["antigravity_proxy"] = {"enabled": True, "port": 3000}
                        
                    client = AIClient(temp_config)
                    test_front = "What is the capital of France?"
                    test_back = "Paris"
                    res = client.generate_options(test_front, test_back, override_provider=self.provider)
                    if not (res and (res.get("hints") or res.get("options"))):
                        status = "❌ Empty"
                except Exception as e:
                    err_msg = str(e).split("\n")[0]
                    status = f"❌ Error: {err_msg}"
                
                # Update item state to result
                def _update_result(idx=i, name=model, st=status):
                    item = self.list_widget.item(idx)
                    item.setText(f"{name} ({st})")
                mw.taskman.run_on_main(_update_result)
                
            def _done():
                self.list_test_btn.setEnabled(True)
                self.restore_btn.setEnabled(True)
                self.up_btn.setEnabled(True)
                self.down_btn.setEnabled(True)
                self.remove_btn.setEnabled(True)
            mw.taskman.run_on_main(_done)
            
        threading.Thread(target=_runner, daemon=True).start()

    def move_item(self, delta):
        curr_row = self.list_widget.currentRow()
        if curr_row == -1: return
        target_row = curr_row + delta
        if 0 <= target_row < self.list_widget.count():
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(target_row, item)
            self.list_widget.setCurrentRow(target_row)

    def remove_item(self):
        curr_row = self.list_widget.currentRow()
        if curr_row != -1:
            self.list_widget.takeItem(curr_row)

    def restore_defaults(self):
        self.list_widget.clear()
        defaults = MODEL_FALLBACKS.get(self.provider, [])
        for m in defaults:
            item = QListWidgetItem(m)
            item.setData(Qt.ItemDataRole.UserRole, m)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)



    def get_ordered_list(self):
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_widget.count())]

    def get_disabled_list(self):
        disabled = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Unchecked:
                disabled.append(item.data(Qt.ItemDataRole.UserRole))
        return disabled


class ProvidersTabMixin:
    def update_special_blacklist_status(self, provider, combobox, status_label):
        model = combobox.currentText().strip()
        status_info = PERSISTENT_TEST_STATUSES.get(provider)
        if status_info:
            status_text, tooltip_text, style_color, tested_model = status_info
            if tested_model == model:
                status_label.setText(status_text)
                status_label.setToolTip(tooltip_text)
                status_label.setStyleSheet(f"font-weight: bold; color: {style_color}; margin-left: 5px;")
                return
            else:
                PERSISTENT_TEST_STATUSES.pop(provider, None)
                
        from ..ai_client import is_model_blacklisted
        if model and is_model_blacklisted(provider, model):
            status_label.setText("🚫 Blacklisted")
            status_label.setToolTip("This model is currently blacklisted on cooldown due to recent failures.")
            status_label.setStyleSheet("font-weight: bold; color: red; margin-left: 5px;")
        else:
            status_label.setText("")
            status_label.setToolTip("")

    def _create_providers_tab(self):
        """Constructs the Tab 2: AI Providers UI"""
        self.providers_tab = QWidget()
        prov_main_layout = QVBoxLayout()
        
        prov_scroll = QScrollArea()
        prov_scroll.setWidgetResizable(True)
        prov_content = QWidget()
        self.prov_layout = QFormLayout(prov_content)
        
        self.api_key_edits = {}
        self.model_edits = {}

        # Antigravity Proxy Group
        ag_group = QGroupBox("Antigravity Cloud Proxy (Native Daemon)")
        ag_layout = QFormLayout()
        
        self.ag_enable_cb = QCheckBox("Enable Background Proxy Daemon")
        self.ag_enable_cb.setToolTip("Automatically run the bundled proxy in the background when Anki starts.")
        
        self.ag_dashboard_btn = QPushButton("🚀 Open Setup Dashboard")
        self.ag_dashboard_btn.setToolTip("Open the local web interface to configure Google accounts.")
        self.ag_dashboard_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("http://localhost:3000/frontend/index.html")))
        
        self.ag_fetch_btn = QPushButton("📥 Fetch Native Binary")
        self.ag_fetch_btn.setToolTip("Manually download the latest executable from GitHub if missing.")
        self.ag_fetch_btn.clicked.connect(self.on_fetch_binary)
        
        self.ag_test_btn = QPushButton("🧪 Test Model")
        self.ag_test_btn.setToolTip("Run a test generation via the local Antigravity Proxy.")
        self.ag_test_btn.clicked.connect(lambda: self.on_test_model("antigravity", self.ag_model_edit))

        self.ag_delete_btn = QPushButton("🗑️ Delete Binary")
        self.ag_delete_btn.setToolTip("Removes the proxy and credential files from disk to free space.")
        self.ag_delete_btn.clicked.connect(self.on_delete_binary)
        
        # Button state logic
        from ..proxy_manager import proxy_manager
        has_bin = os.path.exists(proxy_manager.executable)
        self.ag_dashboard_btn.setEnabled(has_bin)
        self.ag_enable_cb.setEnabled(has_bin)
        self.ag_fetch_btn.setEnabled(not has_bin)
        self.ag_delete_btn.setEnabled(has_bin)
        
        if not has_bin:
             self.ag_dashboard_btn.setToolTip("Download the binary first to enable dashboard access.")
             self.ag_enable_cb.setToolTip("Download the binary first to enable this feature.")
        else:
             self.ag_fetch_btn.setToolTip("Binary is already downloaded locally.")
        
        self.ag_model_layout = QHBoxLayout()
        self.ag_model_edit = QComboBox()
        self.ag_model_edit.setEditable(True)
        self.ag_model_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.ag_model_edit.setToolTip("Select/Enter specific model desired via Proxy.")
        
        # Prepopulate standard defaults
        suggestions = MODEL_SUGGESTIONS.get("antigravity", [])
        default_mod = DEFAULT_MODELS.get("antigravity", "")
        all_suggestions = list(suggestions)
        if default_mod and default_mod not in all_suggestions:
            all_suggestions.insert(0, default_mod)
        self.ag_model_edit.addItems(all_suggestions)
        
        self.ag_model_fetch_btn = QPushButton("Fetch")
        self.ag_model_fetch_btn.setFixedWidth(85)
        self.ag_model_fetch_btn.setToolTip("Fetch currently available backend models directly from the local proxy server (Must be running).")
        self.ag_model_fetch_btn.clicked.connect(lambda: self.on_fetch_models("antigravity", self.ag_model_edit, fetch_btn=self.ag_model_fetch_btn))
        
        self.ag_model_test_btn = QPushButton("Test")
        self.ag_model_test_btn.setFixedWidth(75)
        self.ag_model_test_btn.setToolTip("Run a test generation via the local Antigravity Proxy.")
        
        self.ag_test_status_label = QLabel("")
        self.ag_test_status_label.setStyleSheet("font-weight: bold; margin-left: 5px;")
        
        self.ag_model_edit.currentTextChanged.connect(lambda: self.update_special_blacklist_status("antigravity", self.ag_model_edit, self.ag_test_status_label))
        self.update_special_blacklist_status("antigravity", self.ag_model_edit, self.ag_test_status_label)
            
        self.ag_model_test_btn.clicked.connect(lambda: self.on_test_model("antigravity", self.ag_model_edit, status_label=self.ag_test_status_label))

        self.ag_model_layout.addWidget(self.ag_model_edit)
        self.ag_model_layout.addWidget(self.ag_model_fetch_btn)
        self.ag_model_layout.addWidget(self.ag_model_test_btn)
        self.ag_model_layout.addWidget(self.ag_test_status_label)
        ag_layout.addRow("Active Model:", self.ag_model_layout)
        
        ag_layout.addRow(self.ag_enable_cb)
        
        self.ag_status_label = QLabel("Status: <span style='color: grey;'>Checking...</span>")
        ag_layout.addRow(self.ag_status_label)
        
        btn_hbox = QHBoxLayout()
        btn_hbox.addWidget(self.ag_fetch_btn)
        btn_hbox.addWidget(self.ag_dashboard_btn)
        btn_hbox.addWidget(self.ag_delete_btn)
        ag_layout.addRow("", btn_hbox)
        
        self.ag_dl_progress = QProgressBar()
        self.ag_dl_progress.setVisible(False)
        self.ag_dl_status = QLabel("")
        self.ag_dl_status.setVisible(False)
        ag_layout.addRow(self.ag_dl_progress)
        ag_layout.addRow(self.ag_dl_status)

        ag_group.setLayout(ag_layout)
        self.prov_layout.addRow(ag_group)
            
        # Local Endpoint Group
        local_group = QGroupBox("Local AI / Ollama Settings")
        local_layout = QFormLayout()
        self.local_url_edit = QLineEdit()
        self.local_url_edit.setToolTip("Point to an OpenAI-compatible backend or Ollama instance (e.g., http://localhost:11434/v1).")
        
        self.local_model_layout = QHBoxLayout()
        self.local_model_edit = QComboBox()
        self.local_model_edit.setEditable(True)
        self.local_model_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.local_model_edit.setToolTip("Define the specific locally installed model tag to run inference with.")
        
        self.local_fetch_btn = QPushButton("Fetch")
        self.local_fetch_btn.setFixedWidth(85)
        self.local_fetch_btn.setToolTip("Fetch available models from the specified local Base URL")
        self.local_fetch_btn.clicked.connect(lambda: self.on_fetch_models("local", self.local_model_edit, fetch_btn=self.local_fetch_btn))
        
        self.local_test_btn = QPushButton("Test")
        self.local_test_btn.setFixedWidth(75)
        self.local_test_btn.setToolTip("Run a test generation against your local AI endpoint.")
        
        self.local_test_status_label = QLabel("")
        self.local_test_status_label.setStyleSheet("font-weight: bold; margin-left: 5px;")
        
        self.local_model_edit.currentTextChanged.connect(lambda: self.update_special_blacklist_status("local", self.local_model_edit, self.local_test_status_label))
        self.update_special_blacklist_status("local", self.local_model_edit, self.local_test_status_label)
            
        self.local_test_btn.clicked.connect(lambda: self.on_test_model("local", self.local_model_edit, status_label=self.local_test_status_label))

        self.local_model_layout.addWidget(self.local_model_edit)
        self.local_model_layout.addWidget(self.local_fetch_btn)
        self.local_model_layout.addWidget(self.local_test_btn)
        self.local_model_layout.addWidget(self.local_test_status_label)
        
        self.local_api_key_edit = QLineEdit()
        self.local_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.local_api_key_edit.setToolTip("Provide auth key if running a secured local relay (usually blank for localhost).")
        
        local_key_btn = QPushButton("👁️")
        local_key_btn.setToolTip("Toggle API Key visibility")
        local_key_btn.setFixedWidth(30)
        local_key_btn.setStyleSheet("padding: 2px;")
        local_key_btn.clicked.connect(lambda checked=False, e=self.local_api_key_edit: e.setEchoMode(
            QLineEdit.EchoMode.Normal if e.echoMode() == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password
        ))
        
        local_key_layout = QHBoxLayout()
        local_key_layout.addWidget(self.local_api_key_edit, 1)
        local_key_layout.addWidget(local_key_btn)

        self.local_fallback_cb = QCheckBox("Use Local AI as fallback")
        self.local_fallback_cb.setToolTip("Automatically attempt connection to the local instance below if all cloud endpoints time out or report failures.")
        local_layout.addRow(self.local_fallback_cb)
        local_layout.addRow("Base URL:", self.local_url_edit)
        local_layout.addRow("Model Name:", self.local_model_layout)
        local_layout.addRow("API Key (optional):", local_key_layout)
        local_group.setLayout(local_layout)
        self.prov_layout.addRow(local_group)

        model_group = QGroupBox("Model Names & Fallback Priority")
        model_main_layout = QVBoxLayout()
        
        # Add Fetch All, Test All, and Restore Default buttons
        model_btns_layout = QHBoxLayout()
        
        self.fetch_all_btn = QPushButton("Fetch All")
        self.fetch_all_btn.setToolTip("Attempts to fetch latest models for all providers that have API keys.")
        self.fetch_all_btn.clicked.connect(self.on_fetch_all_models)
        model_btns_layout.addWidget(self.fetch_all_btn)
        
        test_all_btn = QPushButton("Test All")
        test_all_btn.setToolTip("Runs sequential test checks for all configured/enabled providers.")
        test_all_btn.clicked.connect(self.on_test_all_models)
        model_btns_layout.addWidget(test_all_btn)
        
        restore_models_btn = QPushButton("Restore Defaults")
        restore_models_btn.setToolTip("Restores model names to factory defaults.")
        restore_models_btn.clicked.connect(self.on_restore_models_only)
        model_btns_layout.addWidget(restore_models_btn)
        
        model_main_layout.addLayout(model_btns_layout)
        
        self.models_layout = QVBoxLayout()
        model_main_layout.addLayout(self.models_layout)
        
        model_group.setLayout(model_main_layout)
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
        return self.providers_tab
