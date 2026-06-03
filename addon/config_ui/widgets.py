import os
import json
from aqt import mw
from aqt.qt import *
from ..logger import info, tooltip
from ..ai_client import DEFAULT_MODELS, MODEL_FALLBACKS, PROVIDER_ORDER, MODEL_SUGGESTIONS, AIClient

# Resolve the top-level addon package name (e.g. 'ai_hints_dev' or 'AI-Hints')
ADDON_PACKAGE = __name__.split(".")[0]

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
        self.model_edit = QLineEdit(data.get("model", "") if data else "")
        self.headers_edit = QTextEdit()
        self.headers_edit.setPlainText(json.dumps(data.get("headers", {}), indent=2) if data else "{}")
        
        layout.addRow("Provider Name (ID):", self.name_edit)
        layout.addRow("Endpoint URL:", self.url_edit)
        layout.addRow("API Key:", self.key_edit)
        
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
        self.key_edit.setPlaceholderText("Enter API Key...")
        
        # Load existing API key
        keys = parent_dialog.config.get("api_keys", {}) or {}
        self.key_edit.setText(keys.get(provider, ""))
        top_layout.addWidget(self.key_edit, 1)

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
        self.fetch_btn.clicked.connect(lambda: self.parent_dialog.on_fetch_models(self.provider, self.edit))
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

        self.test_btn.clicked.connect(lambda: self.parent_dialog.on_test_model(self.provider, self.edit, status_label=self.status_label))

        main_layout.addLayout(bottom_layout)
        
        self.enabled_cb.toggled.connect(self.on_enabled_toggled)
        self.on_enabled_toggled(self.enabled_cb.isChecked())

    def on_enabled_toggled(self, checked):
        self.key_edit.setEnabled(checked)
        self.eye_btn.setEnabled(checked)
        self.key_label.setEnabled(checked)
        self.model_label.setEnabled(checked)
        self.edit.setEnabled(checked)
        self.fetch_btn.setEnabled(checked)
        self.test_btn.setEnabled(checked)
        self.up_btn.setEnabled(checked)
        self.down_btn.setEnabled(checked)
        self.fallbacks_btn.setEnabled(checked)

    def on_fallbacks_clicked(self):
        from .tab_providers import FallbackOrderDialog
        
        # Get currently configured fallbacks for this provider
        # Note: We need to pull from the current live config in the parent dialog
        current_fallbacks = self.parent_dialog.model_fallbacks_data.get(self.provider, [])
        
        # We also want to provide some smart suggestions for adding new ones
        suggestions = MODEL_SUGGESTIONS.get(self.provider, [])
        
        dlg = FallbackOrderDialog(self.parent_dialog, self.provider, current_fallbacks, suggestions)
        if dlg.exec():
            new_fallbacks = dlg.get_ordered_list()
            self.parent_dialog.model_fallbacks_data[self.provider] = new_fallbacks
            
            # Save disabled fallback models
            new_disabled = dlg.get_disabled_list()
            self.parent_dialog.disabled_fallback_models_data[self.provider] = new_disabled
            
            tooltip(f"Updated fallback priority for {self.provider.capitalize()}")
