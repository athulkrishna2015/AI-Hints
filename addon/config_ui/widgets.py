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

class ProviderRowWidget(QWidget):
    def __init__(self, provider, parent_dialog):
        super().__init__()
        self.provider = provider
        self.parent_dialog = parent_dialog
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        
        # Label
        self.label = QLabel(f"{provider.capitalize()} model:")
        self.label.setMinimumWidth(150)
        layout.addWidget(self.label)
        
        # Combobox
        self.edit = QComboBox()
        self.edit.setEditable(True)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Build priority-ordered suggestion list
        # 1. Start with the default recommended model
        default = DEFAULT_MODELS.get(provider, "")
        
        # 2. Add fallback models (these are explicitly ordered by quality in ai_client.py)
        # We import them locally to avoid circular dependencies if any
        from ..ai_client import MODEL_FALLBACKS, MODEL_SUGGESTIONS
        fallbacks = MODEL_FALLBACKS.get(provider, [])
        
        # 3. Add other general suggestions
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
        layout.addWidget(self.edit)
        
        # Fetch button
        self.fetch_btn = QPushButton("Fetch")
        self.fetch_btn.setFixedWidth(60)
        self.fetch_btn.setToolTip(f"Fetch latest models from {provider.capitalize()} API (requires API key)")
        self.fetch_btn.clicked.connect(lambda: self.parent_dialog.on_fetch_models(self.provider, self.edit))
        layout.addWidget(self.fetch_btn)
        
        # Test button
        self.test_btn = QPushButton("Test")
        self.test_btn.setFixedWidth(50)
        self.test_btn.setToolTip(f"Run a test generation with the selected {provider.capitalize()} model")
        self.test_btn.clicked.connect(lambda: self.parent_dialog.on_test_model(self.provider, self.edit))
        layout.addWidget(self.test_btn)
        
        # Up button
        self.up_btn = QPushButton("▲")
        self.up_btn.setFixedWidth(45)
        self.up_btn.clicked.connect(lambda: self.parent_dialog.move_provider_row(self, -1))
        layout.addWidget(self.up_btn)
        
        # Down button
        self.down_btn = QPushButton("▼")
        self.down_btn.setFixedWidth(45)
        self.down_btn.clicked.connect(lambda: self.parent_dialog.move_provider_row(self, 1))
        layout.addWidget(self.down_btn)
