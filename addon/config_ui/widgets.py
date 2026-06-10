import os
import json
from aqt import mw
from aqt.qt import *
from ..logger import info, tooltip
from ..ai_client import DEFAULT_MODELS, MODEL_FALLBACKS, PROVIDER_ORDER, MODEL_SUGGESTIONS, AIClient

# Resolve the top-level addon package name (e.g. 'ai_hints_dev' or 'AI-Hints')
ADDON_PACKAGE = __name__.split(".")[0]

PERSISTENT_TEST_STATUSES = {}
FETCH_CANCELLATIONS = {}

class CustomProviderDialog(QDialog):
    def __init__(self, parent, name="", data=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        self.setWindowTitle("Custom Provider")
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit(name)
        if name:
            self.name_edit.setReadOnly(True)
            
        self.url_edit = QLineEdit(data.get("url", "") if data else "")
        self.key_edit = QLineEdit(data.get("api_key", "") if data else "")
        self.key_edit.setPlaceholderText("Enter API Key(s)...")
        self.key_edit.setToolTip(
            "Enter one or more API keys separated by commas, semicolons, or newlines.\n"
            "To name/label your keys, use formats:\n"
            "  - name:key (e.g. primary:sk-xxx)\n"
            "  - key (name) (e.g. sk-xxx (backup))"
        )
        
        self.manage_keys_btn = QPushButton("🔑")
        self.manage_keys_btn.setToolTip("Manage Multiple API Keys...")
        self.manage_keys_btn.setFixedWidth(30)
        self.manage_keys_btn.setStyleSheet("padding: 2px;")
        self.manage_keys_btn.clicked.connect(self.on_manage_keys)
        
        key_layout = QHBoxLayout()
        key_layout.addWidget(self.key_edit, 1)
        key_layout.addWidget(self.manage_keys_btn)

        self.model_edit = QLineEdit(data.get("model", "") if data else "")
        self.headers_edit = QTextEdit()
        self.headers_edit.setPlainText(json.dumps(data.get("headers", {}), indent=2) if data else "{}")
        
        layout.addRow("Provider Name (ID):", self.name_edit)
        layout.addRow("Endpoint URL:", self.url_edit)
        layout.addRow("API Key:", key_layout)
        
        model_row = QHBoxLayout()
        self.model_edit = QLineEdit(data.get("model", "") if data else "")
        model_row.addWidget(self.model_edit)
        self.fetch_btn = QPushButton("Fetch")
        self.fetch_btn.setFixedWidth(50)
        self.fetch_btn.clicked.connect(self.on_fetch)
        model_row.addWidget(self.fetch_btn)
        layout.addRow("Model Name:", model_row)
        
        layout.addRow("Headers (JSON):", self.headers_edit)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def on_manage_keys(self):
        provider = self.name_edit.text().strip() or "custom"
        dlg = ManageKeysDialog(provider, self, self.key_edit.text().strip())
        if dlg.exec():
            self.key_edit.setText(dlg.get_keys_string())

    def on_fetch(self):
        url = self.url_edit.text().strip()
        api_key = self.key_edit.text().strip()
        if not url:
            info("Please enter an endpoint URL first.")
            return
            
        try:
            headers = json.loads(self.headers_edit.toPlainText() or "{}")
        except:
            headers = {}

        # Create temp config for fetching
        temp_config = self.config.copy()
        temp_config["custom_providers"] = {
            "TEMP": {
                "url": url,
                "api_key": api_key,
                "headers": headers
            }
        }
        
        client = AIClient(temp_config)
        self.fetch_btn.setEnabled(False)
        tooltip("Fetching models...")
        try:
            models = client.fetch_models("TEMP")
            if models:
                # Use a menu for selection
                menu = QMenu(self)
                for m in sorted(models):
                    action = menu.addAction(m)
                    action.triggered.connect(lambda chk, val=m: self.model_edit.setText(val))
                menu.exec(self.fetch_btn.mapToGlobal(QPoint(0, self.fetch_btn.height())))
            else:
                info("No models found or endpoint does not support /models.")
        except Exception as e:
            info(f"Fetch failed: {e}")
        finally:
            self.fetch_btn.setEnabled(True)

    def validate_and_accept(self):
        if not self.name_edit.text().strip():
            info("Provider name cannot be empty.")
            return
        try:
            json.loads(self.headers_edit.toPlainText() or "{}")
        except Exception:
            info("Headers must be valid JSON.")
            return
        self.accept()

PROVIDER_URLS = {
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

class ProviderRowWidget(QWidget):
    def __init__(self, provider, parent_dialog):
        super().__init__()
        self.provider = provider
        self.parent_dialog = parent_dialog
        
        # Give the widget a styled frame/border to group the provider settings beautifully
        self.setStyleSheet("""
            ProviderRowWidget {
                background-color: rgba(0, 0, 0, 0.02);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 1. Top row: Checkbox, Name, API Key, Eye button, Up/Down reorder buttons
        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)

        # Checkbox
        self.enabled_cb = QCheckBox()
        disabled_list = parent_dialog.config.get("disabled_providers", [])
        self.enabled_cb.setChecked(provider not in disabled_list)
        self.enabled_cb.setToolTip(f"Enable or disable fallback to {provider.capitalize()}")
        top_layout.addWidget(self.enabled_cb)

        # Label/Title
        self.label = QLabel(f"<b>{provider.capitalize()}</b>")
        self.label.setMinimumWidth(80)
        top_layout.addWidget(self.label)
        
        # API Key Label (Clickable link if URL exists)
        url = PROVIDER_URLS.get(provider)
        if url:
            key_label_text = f"<a href='{url}' style='color: #008CBA; text-decoration: none;'>API Key:</a>"
        else:
            key_label_text = "API Key:"
        
        self.key_label = QLabel(key_label_text)
        self.key_label.setOpenExternalLinks(True)
        self.key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(self.key_label)

        # API Key Input field
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Enter API Key(s)...")
        self.key_edit.setToolTip(
            "Enter one or more API keys separated by commas, semicolons, or newlines.\n"
            "To name/label your keys, use formats:\n"
            "  - name:key (e.g. primary:sk-xxx)\n"
            "  - key (name) (e.g. sk-xxx (backup))"
        )
        
        # Load existing API key
        keys = parent_dialog.config.get("api_keys", {}) or {}
        self.key_edit.setText(keys.get(provider, ""))
        top_layout.addWidget(self.key_edit, 1)

        # Keys Management Button
        self.manage_keys_btn = QPushButton("🔑")
        self.manage_keys_btn.setToolTip("Manage Multiple API Keys...")
        self.manage_keys_btn.setFixedWidth(30)
        self.manage_keys_btn.setStyleSheet("padding: 2px;")
        self.manage_keys_btn.clicked.connect(self.on_manage_keys)
        top_layout.addWidget(self.manage_keys_btn)

        # Register key edit in parent_dialog dict for backwards compatibility/saving!
        if not hasattr(parent_dialog, "api_key_edits"):
            parent_dialog.api_key_edits = {}
        parent_dialog.api_key_edits[provider] = self.key_edit

        # Eye Button
        self.eye_btn = QPushButton("👁️")
        self.eye_btn.setToolTip("Toggle API Key visibility")
        self.eye_btn.setFixedWidth(30)
        self.eye_btn.setStyleSheet("padding: 2px;")
        self.eye_btn.clicked.connect(lambda checked=False, e=self.key_edit: e.setEchoMode(
            QLineEdit.EchoMode.Normal if e.echoMode() == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password
        ))
        top_layout.addWidget(self.eye_btn)

        # Up button
        self.up_btn = QPushButton("▲")
        self.up_btn.setFixedWidth(30)
        self.up_btn.setStyleSheet("padding: 2px;")
        self.up_btn.clicked.connect(lambda: self.parent_dialog.move_provider_row(self, -1))
        top_layout.addWidget(self.up_btn)

        # Down button
        self.down_btn = QPushButton("▼")
        self.down_btn.setFixedWidth(30)
        self.down_btn.setStyleSheet("padding: 2px;")
        self.down_btn.clicked.connect(lambda: self.parent_dialog.move_provider_row(self, 1))
        top_layout.addWidget(self.down_btn)

        main_layout.addLayout(top_layout)

        # 2. Bottom row: Active Model label, Model Selection combo box, Fetch, Test, Fallbacks
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(6)

        # Indent spacer to align with top inputs
        indent_spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        bottom_layout.addItem(indent_spacer)

        self.model_label = QLabel("Active Model:")
        self.model_label.setStyleSheet("font-weight: bold;")
        bottom_layout.addWidget(self.model_label)

        # Combobox
        self.edit = QComboBox()
        self.edit.setEditable(True)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Build priority-ordered suggestion list
        default = DEFAULT_MODELS.get(provider, "")
        fallbacks = MODEL_FALLBACKS.get(provider, [])
        suggestions = MODEL_SUGGESTIONS.get(provider, [])
        
        all_items = []
        seen = set()
        
        def _add_if_new(model_name):
            if not model_name or model_name in seen: return
            seen.add(model_name)
            all_items.append(model_name)
            
        _add_if_new(default)
        for m in fallbacks: _add_if_new(m)
        for m in suggestions: _add_if_new(m)
            
        self.edit.addItems(all_items)
        bottom_layout.addWidget(self.edit, 1)

        # Fetch button
        self.fetch_btn = QPushButton("Fetch")
        self.fetch_btn.setFixedWidth(75)
        self.fetch_btn.setStyleSheet("padding: 2px;")
        self.fetch_btn.setToolTip(f"Fetch latest models from {provider.capitalize()} API (requires API key)")
        self.fetch_btn.clicked.connect(lambda: self.parent_dialog.on_fetch_models(self.provider, self.edit, fetch_btn=self.fetch_btn))
        bottom_layout.addWidget(self.fetch_btn)

        # Test button
        self.test_btn = QPushButton("Test")
        self.test_btn.setFixedWidth(65)
        self.test_btn.setStyleSheet("padding: 2px;")
        self.test_btn.setToolTip(f"Run a test generation with the selected {provider.capitalize()} model")
        bottom_layout.addWidget(self.test_btn)

        # Fallbacks button
        self.fallbacks_btn = QPushButton("Fallbacks")
        self.fallbacks_btn.setFixedWidth(90)
        self.fallbacks_btn.setStyleSheet("padding: 2px;")
        self.fallbacks_btn.setToolTip(f"Configure and prioritize fallback models for {provider.capitalize()}")
        self.fallbacks_btn.clicked.connect(self.on_fallbacks_clicked)
        bottom_layout.addWidget(self.fallbacks_btn)

        # Status Label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-weight: bold; margin-left: 5px;")
        bottom_layout.addWidget(self.status_label)

        self.edit.currentTextChanged.connect(self.update_blacklist_status)
        self.update_blacklist_status()

        self.test_btn.clicked.connect(lambda: self.parent_dialog.on_test_model(self.provider, self.edit, status_label=self.status_label))

        main_layout.addLayout(bottom_layout)
        
        self.enabled_cb.toggled.connect(self.on_enabled_toggled)
        self.on_enabled_toggled(self.enabled_cb.isChecked())

    def on_enabled_toggled(self, checked):
        self.key_edit.setEnabled(checked)
        self.manage_keys_btn.setEnabled(checked)
        self.eye_btn.setEnabled(checked)
        self.model_label.setEnabled(checked)
        self.edit.setEnabled(checked)
        self.fetch_btn.setEnabled(checked)
        self.test_btn.setEnabled(checked)
        self.up_btn.setEnabled(checked)
        self.down_btn.setEnabled(checked)
        self.fallbacks_btn.setEnabled(checked)

    def on_manage_keys(self):
        dlg = ManageKeysDialog(self.provider, self, self.key_edit.text().strip())
        if dlg.exec():
            self.key_edit.setText(dlg.get_keys_string())

    def update_blacklist_status(self):
        model = self.edit.currentText().strip()
        status_info = PERSISTENT_TEST_STATUSES.get(self.provider)
        if status_info:
            status_text, tooltip_text, style_color, tested_model = status_info
            if tested_model == model:
                self.status_label.setText(status_text)
                self.status_label.setToolTip(tooltip_text)
                self.status_label.setStyleSheet(f"font-weight: bold; color: {style_color}; margin-left: 5px;")
                return
            elif not getattr(self.parent_dialog, "ui_initializing", False):
                # User changed the model, clear stale persistent status
                PERSISTENT_TEST_STATUSES.pop(self.provider, None)
                
        from ..ai_client import is_model_blacklisted
        if model and is_model_blacklisted(self.provider, model):
            self.status_label.setText("🚫 Blacklisted")
            self.status_label.setToolTip("This model is currently blacklisted on cooldown due to recent failures.")
            self.status_label.setStyleSheet("font-weight: bold; color: red; margin-left: 5px;")
        else:
            self.status_label.setText("")
            self.status_label.setToolTip("")

    def on_fallbacks_clicked(self):
        from .tab_providers import FallbackOrderDialog
        
        # Get currently configured fallbacks for this provider
        # Note: We need to pull from the current live config in the parent dialog
        current_fallbacks = self.parent_dialog.model_fallbacks_data.get(self.provider, [])
        
        # We also want to provide some smart suggestions for adding new ones
        suggestions = MODEL_SUGGESTIONS.get(self.provider, [])
        
        active_model = self.edit.currentText().strip()
        self.fallback_dialog = FallbackOrderDialog(self.parent_dialog, self.provider, active_model, current_fallbacks, suggestions)
        self.fallback_dialog.setWindowFlag(Qt.WindowType.Window, True)
        self.fallback_dialog.setWindowModality(Qt.WindowModality.NonModal)
        
        def _save_data():
            new_active = self.fallback_dialog.get_active_model()
            if new_active:
                self.edit.setCurrentText(new_active)
                
            new_fallbacks = self.fallback_dialog.get_ordered_list()
            self.parent_dialog.model_fallbacks_data[self.provider] = new_fallbacks
            
            # Save disabled fallback models
            new_disabled = self.fallback_dialog.get_disabled_list()
            self.parent_dialog.disabled_fallback_models_data[self.provider] = new_disabled
            tooltip(f"Updated fallback priority for {self.provider.capitalize()}")
            
        self.fallback_dialog.accepted.connect(_save_data)
        self.fallback_dialog.show()


class ManageKeysDialog(QDialog):
    def __init__(self, provider, parent_widget, raw_keys_str):
        super().__init__(parent_widget)
        self.setWindowTitle(f"Manage API Keys - {provider.capitalize()}")
        self.resize(550, 300)
        
        layout = QVBoxLayout(self)
        
        # Add instruction label
        label = QLabel("Manage multiple API keys for rotation. Order determines failover priority.")
        label.setStyleSheet("font-style: italic; color: gray;")
        layout.addWidget(label)
        
        # Table widget to show keys
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Enabled", "Name / Label (Optional)", "API Key"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)
        
        # Action Buttons Layout (Add, Remove, Move Up, Move Down)
        btn_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("＋ Add Row")
        self.add_btn.clicked.connect(self.on_add_row)
        btn_layout.addWidget(self.add_btn)
        
        self.remove_btn = QPushButton("－ Remove Row")
        self.remove_btn.clicked.connect(self.on_remove_row)
        btn_layout.addWidget(self.remove_btn)
        
        self.up_btn = QPushButton("▲ Move Up")
        self.up_btn.clicked.connect(self.on_move_up)
        btn_layout.addWidget(self.up_btn)
        
        self.down_btn = QPushButton("▼ Move Down")
        self.down_btn.clicked.connect(self.on_move_down)
        btn_layout.addWidget(self.down_btn)
        
        layout.addLayout(btn_layout)
        
        # Dialog buttons (OK, Cancel)
        dialog_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dialog_btns.accepted.connect(self.accept)
        dialog_btns.rejected.connect(self.reject)
        layout.addWidget(dialog_btns)
        
        # Parse and populate existing keys
        self.populate_keys(provider, raw_keys_str)

    def populate_keys(self, provider, raw_keys_str):
        client = AIClient({})
        parsed = client._parse_all_keys(provider, raw_keys_str)
        for item in parsed:
            self.add_key_row(item["name"], item["key"], item["enabled"])

    def add_key_row(self, name, key, enabled):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Checkbox item in column 0
        enabled_item = QTableWidgetItem()
        enabled_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        enabled_item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        
        name_item = QTableWidgetItem(name)
        key_item = QTableWidgetItem(key)
        
        self.table.setItem(row, 0, enabled_item)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, key_item)

    def on_add_row(self):
        self.add_key_row("", "", True)
        row = self.table.rowCount() - 1
        self.table.setCurrentCell(row, 2)
        self.table.editItem(self.table.item(row, 2))

    def on_remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def on_move_up(self):
        row = self.table.currentRow()
        if row > 0:
            enabled = self.table.item(row, 0).checkState() == Qt.CheckState.Checked if self.table.item(row, 0) else True
            name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            key = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            
            prev_enabled = self.table.item(row - 1, 0).checkState() == Qt.CheckState.Checked if self.table.item(row - 1, 0) else True
            prev_name = self.table.item(row - 1, 1).text() if self.table.item(row - 1, 1) else ""
            prev_key = self.table.item(row - 1, 2).text() if self.table.item(row - 1, 2) else ""
            
            for r in [row, row - 1]:
                for c in [0, 1, 2]:
                    if not self.table.item(r, c):
                        self.table.setItem(r, c, QTableWidgetItem())
            
            self.table.item(row - 1, 0).setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
            self.table.item(row - 1, 1).setText(name)
            self.table.item(row - 1, 2).setText(key)
            
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if prev_enabled else Qt.CheckState.Unchecked)
            self.table.item(row, 1).setText(prev_name)
            self.table.item(row, 2).setText(prev_key)
            
            self.table.setCurrentCell(row - 1, 0)

    def on_move_down(self):
        row = self.table.currentRow()
        if row >= 0 and row < self.table.rowCount() - 1:
            enabled = self.table.item(row, 0).checkState() == Qt.CheckState.Checked if self.table.item(row, 0) else True
            name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            key = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            
            next_enabled = self.table.item(row + 1, 0).checkState() == Qt.CheckState.Checked if self.table.item(row + 1, 0) else True
            next_name = self.table.item(row + 1, 1).text() if self.table.item(row + 1, 1) else ""
            next_key = self.table.item(row + 1, 2).text() if self.table.item(row + 1, 2) else ""
            
            for r in [row, row + 1]:
                for c in [0, 1, 2]:
                    if not self.table.item(r, c):
                        self.table.setItem(r, c, QTableWidgetItem())
            
            self.table.item(row + 1, 0).setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
            self.table.item(row + 1, 1).setText(name)
            self.table.item(row + 1, 2).setText(key)
            
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if next_enabled else Qt.CheckState.Unchecked)
            self.table.item(row, 1).setText(next_name)
            self.table.item(row, 2).setText(next_key)
            
            self.table.setCurrentCell(row + 1, 0)

    def get_keys_string(self) -> str:
        entries = []
        for row in range(self.table.rowCount()):
            enabled_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            key_item = self.table.item(row, 2)
            
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            name = name_item.text().strip() if name_item else ""
            key = key_item.text().strip() if key_item else ""
            
            if not key:
                continue
                
            prefix = "" if enabled else "disabled:"
            if name:
                entries.append(f"{prefix}{name}:{key}")
            else:
                entries.append(f"{prefix}{key}")
                
        return ", ".join(entries)
