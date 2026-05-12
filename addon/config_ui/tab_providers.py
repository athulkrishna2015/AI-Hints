import os
from aqt.qt import *
from ..ai_client import DEFAULT_MODELS, MODEL_SUGGESTIONS
from .widgets import ProviderRowWidget

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
        self.ag_model_fetch_btn.setFixedWidth(70)
        self.ag_model_fetch_btn.setToolTip("Fetch currently available backend models directly from the local proxy server (Must be running).")
        self.ag_model_fetch_btn.clicked.connect(lambda: self.on_fetch_models("antigravity", self.ag_model_edit))
        
        self.ag_model_layout.addWidget(self.ag_model_edit)
        self.ag_model_layout.addWidget(self.ag_model_fetch_btn)
        ag_layout.addRow("Active Model:", self.ag_model_layout)
        
        ag_layout.addRow(self.ag_enable_cb)
        
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
        self.local_fetch_btn.setFixedWidth(70)
        self.local_fetch_btn.setToolTip("Fetch available models from the specified local Base URL")
        self.local_fetch_btn.clicked.connect(lambda: self.on_fetch_models("local", self.local_model_edit))
        
        self.local_model_layout.addWidget(self.local_model_edit)
        self.local_model_layout.addWidget(self.local_fetch_btn)
        
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
