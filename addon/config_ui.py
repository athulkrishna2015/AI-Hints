import os
import json
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, tooltip

class ConfigDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("AI-Hints Configuration")
        self.setMinimumSize(600, 700)
        self.addon_dir = os.path.dirname(__file__)
        self.config = mw.addonManager.getConfig(__name__)
        
        self.setup_ui()
        self.load_config_into_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        # --- Tab 1: General Settings ---
        self.general_tab = QWidget()
        gen_layout = QFormLayout()
        
        self.ai_provider_cb = QComboBox()
        providers = ["openai", "anthropic", "gemini", "deepseek", "groq", "grok", "mistral", "openrouter", "nvidia", "local"]
        custom_providers = list(self.config.get("custom_providers", {}).keys())
        self.ai_provider_cb.addItems(providers + custom_providers)
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
            "grok": "https://console.x.ai/",
            "nvidia": "https://build.nvidia.com/explore/discover"
        }
        
        self.api_key_edits = {}
        for p in providers:
            if p == "local": continue
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_edits[p] = edit
            
            url = provider_urls.get(p)
            label_text = f"<a href='{url}' style='color: #008CBA; text-decoration: none;'>{p.capitalize()} API Key:</a>" if url else f"{p.capitalize()} API Key:"
            label = QLabel(label_text)
            label.setOpenExternalLinks(True)
            self.prov_layout.addRow(label, edit)
            
        # Local Endpoint Group
        local_group = QGroupBox("Local AI / Ollama Settings")
        local_layout = QFormLayout()
        self.local_url_edit = QLineEdit()
        self.local_model_edit = QLineEdit()
        local_layout.addRow("Base URL:", self.local_url_edit)
        local_layout.addRow("Model Name:", self.local_model_edit)
        local_group.setLayout(local_layout)
        self.prov_layout.addRow(local_group)
        
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
            self.note_type_tree = QTreeWidget()
            self.note_type_tree.setHeaderHidden(True)
            adv_layout.addWidget(self.note_type_tree)
            
            self.note_fields_edit = QTextEdit()
            self.note_fields_edit.setVisible(False)
        else:
            self.note_type_tree = None
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
        
        layout.addWidget(self.tabs)
        
        # --- Bottom Buttons ---
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.save_config)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.setLayout(layout)

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
        self.ai_provider_cb.setCurrentText(c.get("ai_provider", "openai"))
        self.options_count_sb.setValue(c.get("options_count", 4))
        self.storage_mode_cb.setCurrentText(c.get("storage_mode", "json"))
        self.show_hints_cb.setChecked(c.get("show_hints_button", True))
        self.show_options_cb.setChecked(c.get("show_options_button", True))
        
        keys = c.get("api_keys", {})
        for p, edit in self.api_key_edits.items():
            edit.setText(keys.get(p, ""))
            
        local = c.get("local_endpoint", {})
        self.local_url_edit.setText(local.get("base_url", ""))
        self.local_model_edit.setText(local.get("model", ""))
        
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        
        nt_fields = c.get("note_type_fields", {})
        if self.note_type_tree:
            self.note_type_tree.clear()
            for model in mw.col.models.all():
                m_item = QTreeWidgetItem(self.note_type_tree, [model["name"]])
                m_item.setExpanded(False)
                active_fields = nt_fields.get(model["name"], [])
                has_checked = False
                for fld in model["flds"]:
                    f_item = QTreeWidgetItem(m_item, [fld["name"]])
                    f_item.setFlags(f_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    if fld["name"] in active_fields:
                        f_item.setCheckState(0, Qt.CheckState.Checked)
                        has_checked = True
                    else:
                        f_item.setCheckState(0, Qt.CheckState.Unchecked)
                if has_checked:
                    m_item.setExpanded(True)
        
        self.note_fields_edit.setPlainText(json.dumps(nt_fields, indent=4))
        self.raw_editor.setPlainText(json.dumps(c, indent=4))

    def copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        tooltip("Copied to clipboard")

    def save_config(self):
        try:
            # If raw editor was used and is visible, prioritize it? 
            # Or just sync everything. Let's sync from GUI.
            new_config = self.config.copy()
            new_config["ai_provider"] = self.ai_provider_cb.currentText()
            new_config["options_count"] = self.options_count_sb.value()
            new_config["storage_mode"] = self.storage_mode_cb.currentText()
            new_config["show_hints_button"] = self.show_hints_cb.isChecked()
            new_config["show_options_button"] = self.show_options_cb.isChecked()
            
            new_config["api_keys"] = {p: edit.text() for p, edit in self.api_key_edits.items()}
            new_config["local_endpoint"] = {
                "base_url": self.local_url_edit.text(),
                "model": self.local_model_edit.text()
            }
            new_config["system_prompt"] = self.system_prompt_edit.toPlainText()
            
            if hasattr(self, 'note_type_tree') and self.note_type_tree:
                nt_fields = {}
                for i in range(self.note_type_tree.topLevelItemCount()):
                    m_item = self.note_type_tree.topLevelItem(i)
                    m_name = m_item.text(0)
                    checked_fields = []
                    for j in range(m_item.childCount()):
                        f_item = m_item.child(j)
                        if f_item.checkState(0) == Qt.CheckState.Checked:
                            checked_fields.append(f_item.text(0))
                    if checked_fields:
                        nt_fields[m_name] = checked_fields
                new_config["note_type_fields"] = nt_fields
            else:
                new_config["note_type_fields"] = json.loads(self.note_fields_edit.toPlainText())
            
            mw.addonManager.writeConfig(__name__, new_config)
            self.accept()
        except Exception as e:
            showInfo(f"Error saving configuration: {e}")

def on_config_dialog(parent=None):
    if parent is None: parent = mw
    ConfigDialog(parent).exec()

def init_config_ui():
    mw.addonManager.setConfigAction(__name__, on_config_dialog)
