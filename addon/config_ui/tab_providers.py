import os
from aqt.qt import *
from ..ai_client import DEFAULT_MODELS, MODEL_SUGGESTIONS
from .widgets import ProviderRowWidget

class FallbackOrderDialog(QDialog):
    def __init__(self, parent, provider, current_list, suggestions):
        super().__init__(parent)
        # parent is typically the main ConfigDialog (which contains on_fetch_models)
        self.main_dialog = parent
        self.provider = provider
        
        self.setWindowTitle(f"Fallback Priority: {provider.capitalize()}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Configure the list of models to try if the primary model fails.<br/>"
            "The add-on will attempt these models in order from top to bottom."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        self.list_widget = QListWidget()
        for m in current_list:
            self.list_widget.addItem(m)
        layout.addWidget(self.list_widget)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.up_btn = QPushButton("Move Up")
        self.up_btn.clicked.connect(lambda: self.move_item(-1))
        self.down_btn = QPushButton("Move Down")
        self.down_btn.clicked.connect(lambda: self.move_item(1))
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.remove_item)
        
        btn_layout.addWidget(self.up_btn)
        btn_layout.addWidget(self.down_btn)
        btn_layout.addWidget(self.remove_btn)
        layout.addLayout(btn_layout)
        
        # Add new model section
        add_layout = QHBoxLayout()
        self.add_edit = QComboBox()
        self.add_edit.setEditable(True)
        self.add_edit.addItems(suggestions)
        self.add_edit.setCurrentText("")
        
        self.add_btn = QPushButton("Add Model")
        self.add_btn.clicked.connect(self.add_item)
        
        self.fetch_btn = QPushButton("Fetch")
        self.fetch_btn.setFixedWidth(70)
        self.fetch_btn.setToolTip("Fetch latest available models from provider API.")
        self.fetch_btn.clicked.connect(self.on_fetch_clicked)
        
        add_layout.addWidget(self.add_edit, 1)
        add_layout.addWidget(self.fetch_btn)
        add_layout.addWidget(self.add_btn)
        layout.addLayout(add_layout)
        
        # OK / Cancel
        dlg_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dlg_btns.accepted.connect(self.accept)
        dlg_btns.rejected.connect(self.reject)
        layout.addWidget(dlg_btns)

    def on_fetch_clicked(self):
        # We temporarily bridge the dropdown to the main dialog's fetcher
        if hasattr(self.main_dialog, "on_fetch_models"):
            self.main_dialog.on_fetch_models(self.provider, self.add_edit)

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

    def add_item(self):
        text = self.add_edit.currentText().strip()
        if not text: return
        
        # Don't add duplicates
        existing = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if text in existing: return
        
        self.list_widget.addItem(text)
        self.add_edit.setCurrentText("")

    def get_ordered_list(self):
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]


class ProvidersTabMixin:
    def _create_providers_tab(self):
        """Constructs the Tab 2: AI Providers UI"""
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
        self.ag_model_fetch_btn.clicked.connect(lambda: self.on_fetch_models("antigravity", self.ag_model_edit))
        
        self.ag_model_test_btn = QPushButton("Test")
        self.ag_model_test_btn.setFixedWidth(75)
        self.ag_model_test_btn.setToolTip("Run a test generation via the local Antigravity Proxy.")
        self.ag_model_test_btn.clicked.connect(lambda: self.on_test_model("antigravity", self.ag_model_edit))

        self.ag_model_layout.addWidget(self.ag_model_edit)
        self.ag_model_layout.addWidget(self.ag_model_fetch_btn)
        self.ag_model_layout.addWidget(self.ag_model_test_btn)
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
        self.local_fetch_btn.clicked.connect(lambda: self.on_fetch_models("local", self.local_model_edit))
        
        self.local_test_btn = QPushButton("Test")
        self.local_test_btn.setFixedWidth(75)
        self.local_test_btn.setToolTip("Run a test generation against your local AI endpoint.")
        self.local_test_btn.clicked.connect(lambda: self.on_test_model("local", self.local_model_edit))

        self.local_model_layout.addWidget(self.local_model_edit)
        self.local_model_layout.addWidget(self.local_fetch_btn)
        self.local_model_layout.addWidget(self.local_test_btn)
        
        self.local_api_key_edit = QLineEdit()
        self.local_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.local_api_key_edit.setToolTip("Provide auth key if running a secured local relay (usually blank for localhost).")
        self.local_fallback_cb = QCheckBox("Use Local AI as fallback")
        self.local_fallback_cb.setToolTip("Automatically attempt connection to the local instance below if all cloud endpoints time out or report failures.")
        local_layout.addRow(self.local_fallback_cb)
        local_layout.addRow("Base URL:", self.local_url_edit)
        local_layout.addRow("Model Name:", self.local_model_layout)
        local_layout.addRow("API Key (optional):", self.local_api_key_edit)
        local_group.setLayout(local_layout)
        self.prov_layout.addRow(local_group)

        model_group = QGroupBox("Model Names & Fallback Priority")
        model_main_layout = QVBoxLayout()
        
        # Add Fetch All and Restore Default buttons
        model_btns_layout = QHBoxLayout()
        
        fetch_all_btn = QPushButton("Fetch All Available Models")
        fetch_all_btn.setToolTip("Attempts to fetch latest models for all providers that have API keys.")
        fetch_all_btn.clicked.connect(self.on_fetch_all_models)
        model_btns_layout.addWidget(fetch_all_btn)
        
        restore_models_btn = QPushButton("Restore Default Models")
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
