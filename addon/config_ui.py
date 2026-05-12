import os
import json
from aqt import mw
from aqt.utils import askUser
from aqt.deckchooser import DeckChooser
from aqt.qt import *
from .logger import logger, get_logger, info, tooltip
from .ai_client import DEFAULT_MODELS, LEGACY_MODEL_REPLACEMENTS, MODEL_FALLBACKS, PROVIDER_ORDER, MODEL_SUGGESTIONS, AIClient
import logging

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
        suggestions = MODEL_SUGGESTIONS.get(provider, [])
        default = DEFAULT_MODELS.get(provider, "")
        all_suggestions = suggestions[:]
        if default and default not in all_suggestions:
            all_suggestions.insert(0, default)
        self.edit.addItems(all_suggestions)
        layout.addWidget(self.edit)
        
        # Fetch button
        self.fetch_btn = QPushButton("Fetch")
        self.fetch_btn.setFixedWidth(70)
        self.fetch_btn.setToolTip(f"Fetch latest models from {provider.capitalize()} API (requires API key)")
        self.fetch_btn.clicked.connect(lambda: self.parent_dialog.on_fetch_models(self.provider, self.edit))
        layout.addWidget(self.fetch_btn)
        
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

class ConfigDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("AI-Hints Configuration")
        self.setModal(False)
        self.setMinimumSize(600, 700)
        self.addon_dir = os.path.dirname(__file__)
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
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.on_tab_changed(self.tabs.currentIndex())

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

    def setup_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        # --- Tab 1: General Settings ---
        self.general_tab = QWidget()
        gen_layout = QFormLayout()
        
        self.ai_provider_cb = QComboBox()
        self.ai_provider_cb.setToolTip("Select the main AI model provider for generating hints.")
        gen_layout.addRow("Active AI Provider:", self.ai_provider_cb)
        
        self.options_count_sb = QSpinBox()
        self.options_count_sb.setRange(1, 10)
        self.options_count_sb.setToolTip("Set how many multiple-choice options (answers) the AI should generate per card.")
        gen_layout.addRow("Number of Options:", self.options_count_sb)
        
        self.storage_mode_cb = QComboBox()
        self.storage_mode_cb.addItems(["json", "html"])
        self.storage_mode_cb.setToolTip("JSON: Invisible (cleaner). HTML: Visible on all devices.")
        gen_layout.addRow("Storage Mode:", self.storage_mode_cb)
        
        self.mathjax_format_cb = QComboBox()
        self.mathjax_format_cb.addItems(["delimiters", "inline"])
        self.mathjax_format_cb.setToolTip(r"delimiters: \( ... \), \[ ... \]. inline: $ ... $, $$ ... $")
        gen_layout.addRow("MathJax Format:", self.mathjax_format_cb)
        
        self.fix_latex_cb = QCheckBox("Repair AI LaTeX Errors")
        self.fix_latex_cb.setToolTip("Automatically fix common AI math errors like missing backslashes or missing delimiters.")
        gen_layout.addRow(self.fix_latex_cb)

        # --- Button Visibility Group ---
        button_group = QGroupBox("Button Visibility")
        button_layout = QFormLayout()
        
        self.show_hints_cb = QCheckBox("Show Hints Button")
        self.show_hints_cb.setToolTip("Render the foldable 'Hints' section container on the review screen.")
        button_layout.addRow(self.show_hints_cb)
        
        self.show_options_cb = QCheckBox("Show Options Button (Sequential)")
        self.show_options_cb.setToolTip("Render the clickable 'Options' section container on the review screen.")
        button_layout.addRow(self.show_options_cb)
        
        self.show_on_card_cb = QCheckBox("Show Generate Button on Review Card")
        self.show_on_card_cb.setToolTip("Embed generation controls (Generate, Regenerate, Clear) inline inside the card itself.")
        button_layout.addRow(self.show_on_card_cb)
        
        self.show_in_bottom_bar_cb = QCheckBox("Show Generate Button in Review Bar")
        self.show_in_bottom_bar_cb.setToolTip("Place generation controls at the very bottom of the reviewer, next to answer buttons.")
        button_layout.addRow(self.show_in_bottom_bar_cb)

        self.show_in_popup_cb = QCheckBox("Show Results in Popup Window")
        self.show_in_popup_cb.setToolTip("Open successful generations in a non-blocking popup window for review before storing.")
        button_layout.addRow(self.show_in_popup_cb)
        
        button_group.setLayout(button_layout)
        gen_layout.addRow(button_group)

        # --- Auto-Show & Generation Group ---
        show_group = QGroupBox("Auto-Show & Generation")
        show_layout = QFormLayout()

        self.auto_generate_new_cb = QCheckBox("Auto Generate for New Cards")
        self.auto_generate_new_cb.setToolTip("Automatically run AI generation for new/empty cards that do not have hints/options yet.")
        show_layout.addRow(self.auto_generate_new_cb)

        self.auto_regenerate_all_cb = QCheckBox("└─ Force Regenerate Even if Data Exists")
        self.auto_regenerate_all_cb.setToolTip("Always overwrite hints, even for cards that already have data. Requires primary Auto-Generate to be active.")
        self.auto_regenerate_all_cb.setStyleSheet("margin-left: 15px;")
        show_layout.addRow(self.auto_regenerate_all_cb)

        self.auto_regenerate_old_version_cb = QCheckBox("└─ Regenerate if Generated Version < ")
        self.auto_regenerate_old_version_cb.setToolTip(
            "Automatically regenerate hints for cards whose stored version is older than the version number you specify. "
            "Requires Auto Generate to be active. Leave the version field empty to disable."
        )
        self.auto_regenerate_old_version_cb.setStyleSheet("margin-left: 15px;")
        self.auto_regenerate_min_version_edit = QLineEdit()
        self.auto_regenerate_min_version_edit.setPlaceholderText("e.g. 1.4.2")
        self.auto_regenerate_min_version_edit.setFixedWidth(80)
        self.auto_regenerate_min_version_edit.setToolTip(
            "Cards generated by an addon version older than this will be regenerated automatically."
        )
        version_row = QHBoxLayout()
        version_row.setContentsMargins(15, 0, 0, 0)
        version_row.addWidget(self.auto_regenerate_old_version_cb)
        version_row.addWidget(self.auto_regenerate_min_version_edit)
        version_row.addStretch()
        show_layout.addRow(version_row)

        # Couple all sub-checkboxes to the primary Auto-Generate checkbox
        def _update_regen_controls(enabled):
            self.auto_regenerate_all_cb.setEnabled(enabled)
            self.auto_regenerate_old_version_cb.setEnabled(enabled)
            self.auto_regenerate_min_version_edit.setEnabled(
                enabled and self.auto_regenerate_old_version_cb.isChecked()
            )
        self.auto_generate_new_cb.toggled.connect(_update_regen_controls)
        self.auto_regenerate_old_version_cb.toggled.connect(
            lambda checked: self.auto_regenerate_min_version_edit.setEnabled(
                checked and self.auto_generate_new_cb.isChecked()
            )
        )

        show_layout.addRow(QLabel("<b>On Card Load:</b>"))
        self.auto_show_hints_cb = QCheckBox("Auto Show Hints")
        self.auto_show_hints_cb.setToolTip("Automatically expand and show hints when a card is loaded.")
        show_layout.addRow(self.auto_show_hints_cb)

        self.auto_show_options_cb = QCheckBox("Auto Show Options")
        self.auto_show_options_cb.setToolTip("Automatically expand and show options when a card is loaded.")
        show_layout.addRow(self.auto_show_options_cb)

        show_layout.addRow(QLabel("<b>After Manual Generation:</b>"))
        self.manual_show_hints_cb = QCheckBox("Auto Show Hints")
        self.manual_show_hints_cb.setToolTip("Automatically expand and show hints after clicking Generate/Regenerate.")
        show_layout.addRow(self.manual_show_hints_cb)

        self.manual_show_options_cb = QCheckBox("Auto Show Options")
        self.manual_show_options_cb.setToolTip("Automatically expand and show options after clicking Generate/Regenerate.")
        show_layout.addRow(self.manual_show_options_cb)
        
        show_group.setLayout(show_layout)
        gen_layout.addRow(show_group)
        
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
        self.local_url_edit.setToolTip("Point to an OpenAI-compatible backend or Ollama instance (e.g., http://localhost:11434/v1).")
        self.local_model_edit = QLineEdit()
        self.local_model_edit.setToolTip("Define the specific locally installed model tag to run inference with.")
        self.local_api_key_edit = QLineEdit()
        self.local_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.local_api_key_edit.setToolTip("Provide auth key if running a secured local relay (usually blank for localhost).")
        self.local_fallback_cb = QCheckBox("Use Local AI as fallback")
        self.local_fallback_cb.setToolTip("Automatically attempt connection to the local instance below if all cloud endpoints time out or report failures.")
        local_layout.addRow(self.local_fallback_cb)
        local_layout.addRow("Base URL:", self.local_url_edit)
        local_layout.addRow("Model Name:", self.local_model_edit)
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
        self.tabs.addTab(self.providers_tab, "AI Providers")
        
        # --- Tab 3: Advanced ---
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()
        
        adv_layout.addWidget(QLabel("Target Fields (Where hints are saved, comma-separated):"))
        self.target_fields_edit = QLineEdit()
        self.target_fields_edit.setToolTip("Example: Extras, Back, Text")
        adv_layout.addWidget(self.target_fields_edit)
        
        adv_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setToolTip("Customize the core AI persona instructions defining generation constraints, math syntaxes, and output layout.")
        adv_layout.addWidget(self.system_prompt_edit)
        
        adv_layout.addWidget(QLabel("Note Type Fields:"))
        
        if mw.col is not None:
            self.nt_selector_layout = QVBoxLayout()
            self.nt_cb = QComboBox()
            self.nt_cb.setToolTip("Switch active Note Type to edit allowed field scans.")
            self.nt_cb.currentIndexChanged.connect(self.on_nt_changed)
            self.nt_selector_layout.addWidget(self.nt_cb)
            
            self.fld_list = QListWidget()
            self.fld_list.setToolTip("Check off specifically which fields in this note type contain textual question context the AI should ingest.")
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
        self.raw_toggle.setToolTip("Directly inspect and write the raw serialization JSON for fine-grained control.")
        adv_layout.addWidget(self.raw_toggle)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)
        
        self.advanced_tab.setLayout(adv_layout)
        self.tabs.addTab(self.advanced_tab, "Advanced")

        # --- Tab 4: Shortcuts ---
        self.shortcuts_tab = QWidget()
        short_layout = QFormLayout()
        
        self.modifier_cb = QComboBox()
        self.modifier_cb.addItems(["alt", "ctrl", "shift", "meta", "none"])
        self.modifier_cb.setToolTip("The modifier key to use with shortcuts. 'meta' is the Command key on Mac or Windows key on Windows. 'none' means no modifier.")
        short_layout.addRow("Shortcut Modifier:", self.modifier_cb)
        
        self.shortcut_edits = {}
        shortcut_labels = {
            "generate": "Generate / Regenerate:",
            "toggle-options": "Toggle Options:",
            "toggle-hints": "Toggle Hints:",
            "clear": "Clear:",
            "refresh": "Refresh:",
            "show-json": "Show JSON:"
        }
        shortcut_tooltips = {
            "generate": "Triggers automatic generation or regeneration of hints for the current card.",
            "toggle-options": "Collapses or expands the multiple-choice options field.",
            "toggle-hints": "Collapses or expands the written hints hint field.",
            "clear": "Wipes the stored hints payload from the card metadata irrevocably.",
            "refresh": "Forces the UI renderer to re-parse the current card data from scratch.",
            "show-json": "Reveals debugging panel showing internal JSON storage data for the note."
        }
        for key, label in shortcut_labels.items():
            edit = QLineEdit()
            edit.setPlaceholderText("e.g. 1")
            edit.setFixedWidth(50)
            edit.setToolTip(shortcut_tooltips.get(key, ""))
            self.shortcut_edits[key] = edit
            short_layout.addRow(label, edit)
        
        self.shortcuts_tab.setLayout(short_layout)
        self.tabs.addTab(self.shortcuts_tab, "Shortcuts")
        
        # --- Tab 5: Batch ---
        self.batch_tab = self._create_batch_tab()
        self.tabs.addTab(self.batch_tab, "Batch Generation")
        
        # --- Tab 6: Support ---
        self.support_tab = self._create_support_tab()
        self.tabs.addTab(self.support_tab, "Support")
        
        # --- Tab 7: Logs ---
        self.log_tab = self._create_log_tab()
        self.tabs.addTab(self.log_tab, "Logs")
        
        layout.addWidget(self.tabs)
        
        # Set Logs tab as default
        self.tabs.setCurrentIndex(6)
        
        # --- Bottom Buttons ---
        btn_layout = QHBoxLayout()
        
        self.restore_btn = QPushButton("Restore Tab Defaults")
        self.restore_btn.clicked.connect(self.on_restore_current_tab)
        btn_layout.addWidget(self.restore_btn)
        
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(lambda: self.save_config(close=False))
        btn_layout.addWidget(self.save_btn)
        
        self.save_exit_btn = QPushButton("Save and Exit")
        self.save_exit_btn.clicked.connect(lambda: self.save_config(close=True))
        btn_layout.addWidget(self.save_exit_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def _create_log_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Level filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Level:"))
        self.log_level_cb = QComboBox()
        self.log_level_cb.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_cb.currentIndexChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_level_cb)
        
        filter_layout.addWidget(QLabel(" Search:"))
        self.log_search_edit = QLineEdit()
        self.log_search_edit.setPlaceholderText("Filter text...")
        self.log_search_edit.textChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_search_edit)
        
        filter_layout.addStretch()
        
        self.auto_clear_cb = QCheckBox("Clear on startup")
        self.auto_clear_cb.setToolTip("Automatically clear the log file every time Anki starts.")
        filter_layout.addWidget(self.auto_clear_cb)

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
        search_filter = self.log_search_edit.text().strip().lower()
        
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            if level_filter != "ALL":
                lines = [l for l in lines if f" - {level_filter} - " in l]
            
            if search_filter:
                lines = [l for l in lines if search_filter in l.lower()]
            
            content = "".join(lines) if lines else "No entries matching the selected filters."
            if self.log_view.toPlainText() == content:
                return

            vbar = self.log_view.verticalScrollBar()
            was_at_bottom = vbar.value() >= vbar.maximum() - 10
            
            self.log_view.setPlainText(content)
            
            if was_at_bottom:
                vbar.setValue(vbar.maximum())
        except Exception as e:
            self.log_view.setPlainText(f"Error reading log: {e}")

    def clear_log(self):
        log_file = os.path.join(self.addon_dir, "ai_hints.log")
        try:
            open(log_file, "w", encoding="utf-8").close()
            self.log_view.setPlainText("Log cleared.")
            logger.info("Log cleared by user.")
        except Exception as e:
            info(f"Could not clear log: {e}")

    def _create_batch_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # -- 1. START GROUP --
        start_group = QGroupBox("Start New Batch Generation")
        s_layout = QFormLayout()

        # 🔄 Generation Method Toggle Group
        method_widget = QWidget()
        method_layout = QHBoxLayout(method_widget)
        method_layout.setContentsMargins(0,0,0,0)
        
        self.method_bg_grp = QButtonGroup(self)
        
        self.rb_local_queue = QRadioButton("Sequential Local Queue (Recommended)")
        self.rb_local_queue.setChecked(True)
        self.rb_local_queue.setToolTip("Processes cards one-by-one in the background. Supports ALL providers and honors full fallback settings. Free-tier friendly!")
        
        self.rb_native_async = QRadioButton("Native Async API (Cloud)")
        self.rb_native_async.setToolTip("Bundles requests to cloud provider. Faster, but requires paid tier/billing linked and excludes fallbacks.")
        
        self.method_bg_grp.addButton(self.rb_local_queue)
        self.method_bg_grp.addButton(self.rb_native_async)
        method_layout.addWidget(self.rb_local_queue)
        method_layout.addWidget(self.rb_native_async)
        
        s_layout.addRow("Method Type:", method_widget)
        
        # ℹ️ Info Warning label that flips based on choice
        self.batch_desc_label = QLabel("💡 Uses standard local background loop. Perfectly respects your fallback tree and works on all free keys.")
        self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        self.batch_desc_label.setWordWrap(True)
        s_layout.addRow("", self.batch_desc_label)

        # 🚀 Provider Override Selector
        self.batch_provider_cb = QComboBox()
        self.batch_provider_cb.addItem("⚡ Standard Config (Follows Fallback Matrix)")
        # Load list of active providers including any defined in PROVIDER_ORDER
        from .ai_client import PROVIDER_ORDER
        for prov in PROVIDER_ORDER:
             self.batch_provider_cb.addItem(prov.capitalize(), prov)
        
        s_layout.addRow("Force Provider:", self.batch_provider_cb)

        # 🎯 Specific Model Override Selector
        self.batch_model_cb = QComboBox()
        self.batch_model_cb.setEditable(True)
        self.batch_model_cb.addItem("⚡ System Default (Configured Primary Model)")
        self.batch_model_cb.setToolTip("Choose a specific model to use for this batch. Leaves blank to use your configured default for the provider.")
        s_layout.addRow("Force Model:", self.batch_model_cb)
        
        # Dynamic Model Suggestions connector
        self.batch_provider_cb.currentIndexChanged.connect(self._update_batch_model_suggestions)

        # 📦 Searchable Embedded Deck Selector
        self.batch_deck_chooser = QComboBox()
        self.batch_deck_chooser.setEditable(True)
        self.batch_deck_chooser.setInsertPolicy(QComboBox.InsertPolicy.NoInsert) # No adding temp fake decks
        
        # Load and Sort Deck Names
        try:
             all_decks = mw.col.decks.all_names()
             self.batch_deck_chooser.addItems(all_decks)
             # Pre-select current active deck in main window
             curr = mw.col.decks.current().get('name', '')
             if curr in all_decks:
                  self.batch_deck_chooser.setCurrentText(curr)
        except: pass

        # Enable Advanced Partial Searching (AutoComplete)
        completer = QCompleter(mw.col.decks.all_names(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains) # This enables "partial search"!
        self.batch_deck_chooser.setCompleter(completer)
        
        s_layout.addRow("Source Deck:", self.batch_deck_chooser)
        
        self.batch_skip_existing_cb = QCheckBox("Skip cards that already have AI Hints generated")
        self.batch_skip_existing_cb.setChecked(True)
        s_layout.addRow(self.batch_skip_existing_cb)

        # Version-gated Batch Regeneration control
        self.batch_regen_version_cb = QCheckBox("└─ Except if Generated Version < ")
        self.batch_regen_version_cb.setStyleSheet("margin-left: 15px;")
        self.batch_regen_version_cb.setToolTip("If checked, cards with hints will still be queued for batching if their stored version is older than the target.")
        self.batch_regen_version_cb.setChecked(False)
        
        self.batch_regen_min_version_edit = QLineEdit()
        self.batch_regen_min_version_edit.setPlaceholderText("e.g. 1.4.2")
        self.batch_regen_min_version_edit.setFixedWidth(80)
        
        # Load initial default from current main config values
        self.batch_regen_min_version_edit.setText(self.config.get("auto_regenerate_min_version", ""))

        batch_version_row = QHBoxLayout()
        batch_version_row.setContentsMargins(15, 0, 0, 0)
        batch_version_row.addWidget(self.batch_regen_version_cb)
        batch_version_row.addWidget(self.batch_regen_min_version_edit)
        batch_version_row.addStretch()
        s_layout.addRow(batch_version_row)
        
        # Enable/disable version edit based on checkbox
        self.batch_regen_version_cb.toggled.connect(
            lambda enabled: self.batch_regen_min_version_edit.setEnabled(enabled)
        )
        self.batch_regen_min_version_edit.setEnabled(False)
        
        # Only enable version logic if 'Skip Existing' is ON
        self.batch_skip_existing_cb.toggled.connect(
            lambda checked: self.batch_regen_version_cb.setEnabled(checked)
        )
        
        # Connect toggle group to UI update handler
        self.method_bg_grp.buttonClicked.connect(self._on_batch_method_changed)
        
        start_group.setLayout(s_layout)
        layout.addWidget(start_group)
        
        # -- 2. ACTIVE GROUP --
        active_group = QGroupBox("Running & Pending Batches")
        a_layout = QVBoxLayout()
        
        self.batch_list_view = QTextBrowser()
        self.batch_list_view.setReadOnly(True)
        self.batch_list_view.setPlaceholderText("No active native batch tracking handles found.")
        self.batch_list_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.batch_list_view.setOpenExternalLinks(False)
        self.batch_list_view.anchorClicked.connect(self._on_log_link_clicked)
        a_layout.addWidget(self.batch_list_view)
        refresh_row = QHBoxLayout()
        
        # Primary Control Suite cluster
        self.batch_run_btn = QPushButton("🚀 Initiate Queue")
        self.batch_run_btn.setAutoDefault(False)
        self.batch_run_btn.setMinimumHeight(30)
        self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
        try: self.batch_run_btn.clicked.disconnect()
        except Exception: pass
        self.batch_run_btn.clicked.connect(self.on_start_config_batch)
        
        self.pause_local_btn = QPushButton("⏸️ Pause Queue")
        self.pause_local_btn.setAutoDefault(False)
        self.pause_local_btn.setCheckable(True)
        self.pause_local_btn.setMinimumHeight(30)
        try: self.pause_local_btn.clicked.disconnect()
        except Exception: pass
        self.pause_local_btn.clicked.connect(self.on_pause_toggled)
        
        self.stop_local_btn = QPushButton("🛑 Stop Queue")
        self.stop_local_btn.setAutoDefault(False)
        self.stop_local_btn.setMinimumHeight(30)
        self.stop_local_btn.setStyleSheet("color: #dc3545; font-weight: bold;")
        try: self.stop_local_btn.clicked.disconnect()
        except Exception: pass
        self.stop_local_btn.clicked.connect(self.on_stop_local_queue)
 
        self.refresh_status_btn = QPushButton("🔄 Refresh Status")
        self.refresh_status_btn.setAutoDefault(False)
        self.refresh_status_btn.setMinimumHeight(30)
        try: self.refresh_status_btn.clicked.disconnect()
        except Exception: pass
        self.refresh_status_btn.clicked.connect(self.update_batch_status_tab)
        
        # Grouped Layout
        refresh_row.addWidget(self.batch_run_btn)
        refresh_row.addWidget(self.pause_local_btn)
        refresh_row.addWidget(self.stop_local_btn)
        refresh_row.addStretch() # Separator spacer
        refresh_row.addWidget(self.refresh_status_btn)
        
        a_layout.addLayout(refresh_row)
        
        active_group.setLayout(a_layout)
        layout.addWidget(active_group)
        
        layout.addStretch()
        
        # Initial UI state update
        self._on_batch_method_changed()
        
        return tab

    def _update_batch_model_suggestions(self):
        """Pulls available pre-seeded list suggestions from shared constants file."""
        self.batch_model_cb.clear()
        self.batch_model_cb.addItem("⚡ System Default (Configured Primary Model)")
        
        combo_idx = self.batch_provider_cb.currentIndex()
        if combo_idx <= 0:
             return
             
        prov = self.batch_provider_cb.itemData(combo_idx)
        if prov:
             from .ai_client import MODEL_SUGGESTIONS
             suggs = MODEL_SUGGESTIONS.get(prov, [])
             for s in suggs:
                  self.batch_model_cb.addItem(s)

    def _on_batch_method_changed(self):
        """Updates descriptions, buttons, and valid providers when toggle flips."""
        if self.rb_native_async.isChecked():
            # Cloud Native Async selected
            self.batch_desc_label.setText("⚠️ Uses Cloud Native API. Requires **PAID ACCOUNT** / linked billing. Currently ONLY Gemini supports this schema. Closes fast.")
            self.batch_desc_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 11px; margin-bottom: 5px;")
            
            self.batch_run_btn.setText("🚀 Submit Cloud Batch")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #0d6efd; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
        else:
            # Local Sequential Queue selected
            self.batch_desc_label.setText("💡 Uses standard local background loop. Perfectly respects your fallback tree, works on all free keys! (Anki must stay open)")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
            
            from .batch_manager import batch_manager
            if not getattr(batch_manager, "local_queue_active", False) and getattr(batch_manager, "local_queue", []):
                 self.batch_run_btn.setText("⏯️ Resume Saved Queue")
                 self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #fd7e14; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
                 self.batch_desc_label.setText("💾 Found an unfinished offline batch from a previous session! Click below to Resume.")
            else:
                 self.batch_run_btn.setText("🚀 Initiate Queue")
                 self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")

    def update_batch_status_tab(self):
        try:
            from .batch_manager import batch_manager
            
            # Sync Pause Button UI State based on engine state
            is_paused = getattr(batch_manager, "local_queue_paused", False)
            self.pause_local_btn.setChecked(is_paused)
            if is_paused:
                 self.pause_local_btn.setText("▶️ Resume Queue")
                 self.pause_local_btn.setStyleSheet("background-color: #ffc107; font-weight: bold;")
            else:
                 self.pause_local_btn.setText("⏸️ Pause Queue")
                 self.pause_local_btn.setStyleSheet("")

            summary = batch_manager.get_status_summary()
            
            # Render the generated HTML directly for rich functionality
            if not summary:
                  self.batch_list_view.setHtml("<i>(Ready to initialize)</i>")
            else:
                  self.batch_list_view.setHtml(summary)
                  
        except Exception:
            pass

    def _on_log_link_clicked(self, qurl):
        """Intercepts clicks on anchor tags and routes to native Anki Browser actions."""
        url = qurl.toString().strip()
        if url.startswith("browse:"):
             # Expected format 'browse:cid:12345'
             query = url.split(":", 1)[1] # Extract 'cid:12345'
             from aqt import dialogs
             # Open browser globally and drive search automatically
             browser = dialogs.open("Browser", mw)
             try:
                  # Standard API in recent Anki builds
                  browser.search(query)
             except AttributeError:
                  # Stable Legacy API fallback
                  browser.form.searchEdit.lineEdit().setText(query)
                  browser.onSearchActivated()
             
             # Force window prominence
             browser.setFocus()
             browser.activateWindow()
             browser.raise_()

    def on_pause_toggled(self, checked):
        from .batch_manager import batch_manager
        batch_manager.set_pause_local_queue(checked)
        tooltip("⏸️ Local Queue Paused" if checked else "▶️ Local Queue Resumed")
        self.update_batch_status_tab()

    def on_stop_local_queue(self):
        """Triggers safe termination of active serial background loop."""
        from .batch_manager import batch_manager
        if not batch_manager.local_queue_active:
             info("There is no local sequential queue currently running.")
             return
             
        if askUser("Are you sure you want to HALT the local background queue?\n\nCompleted cards are already saved. Remaining queued cards will be discarded."):
             batch_manager.stop_local_queue()
             # Reset pause button state
             self.pause_local_btn.setChecked(False)
             self.update_batch_status_tab()

    def on_start_config_batch(self):
        from .batch_manager import batch_manager
        
        # 🚀 RESUME INTERCEPTOR
        # If an inactive local queue exists, ask user whether to restore or flush it!
        if not self.rb_native_async.isChecked() and not batch_manager.local_queue_active and batch_manager.local_queue:
             count = len(batch_manager.local_queue)
             res = askUser(
                  f"💾 **UNFINISHED BATCH DETECTED**\n\n"
                  f"Found {count} cards waiting from your previous session.\n\n"
                  f"• Click 'Yes' to RESUME processing these cards.\n"
                  f"• Click 'No' to DISCARD the old queue and start a fresh batch."
             )
             if res:
                  # User wishes to resume the background daemon
                  started = batch_manager.start_local_sequential_queue(card_ids=None) # Uses persistence
                  if started:
                       self.update_batch_status_tab()
                       self._on_batch_method_changed() # Redraw visual states
                  return
             else:
                  # User decided to wipe the stored queue and start fresh
                  batch_manager.stop_local_queue() # Explicitly clear from disk
                  # Continue falling through to allow fresh generation flow

        # Standard Fresh Generation Flow follows
        # Extract string directly from our searchable combobox
        deck_name = self.batch_deck_chooser.currentText().strip()
        
        # Verify the deck actually exists in the collection to prevent typos
        all_valid_decks = mw.col.decks.all_names()
        if deck_name not in all_valid_decks:
             info(f"⚠️ Deck not found: '{deck_name}'\nPlease select a valid deck from the list.")
             return

        if not deck_name:
             info("Please select a deck first.")
             return
             
             
        # Collect potential cards
        try:
            cids = mw.col.find_cards(f"deck:\"{deck_name}\"")
            if not cids:
                info(f"No cards found in deck '{deck_name}'.")
                return
                
            # Filter existing
            if self.batch_skip_existing_cb.isChecked():
                from .reviewer_hooks import card_has_hints, _get_card_from_collection, _card_saved_version, _version_less_than
                final_ids = []
                
                use_ver_gate = self.batch_regen_version_cb.isChecked()
                min_ver = self.batch_regen_min_version_edit.text().strip()
                
                for cid in cids:
                    c = _get_card_from_collection(cid)
                    if not c:
                        continue
                        
                    has_hints = card_has_hints(c)
                    
                    if not has_hints:
                        # Absolutely no hints yet, keep it
                        final_ids.append(cid)
                    elif use_ver_gate and min_ver:
                        # Has hints, but check if they are outdated
                        saved_ver = _card_saved_version(c)
                        if _version_less_than(saved_ver, min_ver):
                            final_ids.append(cid)
            else:
                final_ids = list(cids)
                
            if not final_ids:
                info("No cards need hint generation (all selected have hints already).")
                return
                
            # Chunk limit to 1000 for inline batch safety
            chunked_ids = final_ids[:1000]
            excess = len(final_ids) - 1000
            
            # 1. Confirm execution intent
            is_native = self.rb_native_async.isChecked()
            mode_str = "Native Cloud Batch" if is_native else "Local Background Queue"
            
            confirm_msg = f"Ready to process {len(chunked_ids)} cards using **{mode_str}**."
            if excess > 0:
                confirm_msg += f"\n\n(Note: {excess} remaining skipped due to safety limits.)"
            
            if not askUser(confirm_msg + "\n\nProceed with execution?"):
                return
            
            # 2. Identify selected stack override
            selected_prov = self.batch_provider_cb.currentData() # Can be 'gemini', 'groq', etc.
            # currentData returns None for top option if we used addItem(text) instead of addItem(text, data)
            # Wait, above I used addItem("Standard...", None)? No, I need to check how it was set.
            
            combo_idx = self.batch_provider_cb.currentIndex()
            prov_override = None
            if combo_idx > 0:
                # Actually fetched data
                prov_override = self.batch_provider_cb.itemData(combo_idx)

            # Check specific Model Override
            chosen_model = self.batch_model_cb.currentText().strip()
            model_override = None
            if chosen_model and "⚡" not in chosen_model:
                 model_override = chosen_model

            # 3. Branch Logic 🌳
            
            # Prepare fresh runtime config clone
            config = self.config.copy()
            
            # Effectively route target provider identification for the model override injector
            target_prov = prov_override or config.get("ai_provider", "openai")
            
            # 💉 Inject Dynamic Model Override directly into the clone config dictionary!
            if model_override:
                 # Ensure 'models' dictionary exists correctly in config
                 current_models = config.get("models", {})
                 if not isinstance(current_models, dict): current_models = {}
                 else: current_models = current_models.copy() # Clone internal map
                 
                 current_models[target_prov] = model_override
                 config["models"] = current_models
                 logger.info(f"Applying transient Batch Model Override: {target_prov} -> {model_override}")

            from .ai_client import AIClient
            from .batch_manager import batch_manager
            
            client = AIClient(config)
            if not client.has_any_ready_provider():
                 info("No configured API Keys found! Visit Provider settings first.")
                 return

            if not is_native:
                # --- PATH A: LOCAL SEQUENTIAL LOOP ---
                started = batch_manager.start_local_sequential_queue(
                    chunked_ids, 
                    config, 
                    provider_override=prov_override
                )
                if started:
                    # Auto-update view shortly after start
                    QTimer.singleShot(1500, self.update_batch_status_tab)
                return

            else:
                # --- PATH B: NATIVE ASYNC CLOUD BATCH ---
                # Safety: Only gemini supports native right now
                target_prov = prov_override or "gemini"
                if target_prov != "gemini":
                    info(f"❌ Native Cloud Batch is currently NOT supported for provider '{target_prov.upper()}'.\n\nPlease either select 'Gemini' OR switch your Method back to 'Sequential Local Queue'.")
                    return
                
                # Prepare items for Gemini bulk payload
                from .card_parser import CardParser
                from .reviewer_hooks import _get_card_from_collection

                parser = CardParser(
                    config.get("target_fields", []),
                    config.get("note_type_fields", {}),
                    config.get("storage_mode", "json")
                )
                
                items = []
                actual_cids = []
                
                for cid in chunked_ids:
                    try:
                        card = _get_card_from_collection(cid)
                        if not card: continue
                        f, b = parser.get_note_content(card.note(), card)
                        items.append({
                            "key": str(cid),
                            "system_prompt": config.get("system_prompt", ""),
                            "user_prompt": f"FRONT:\n{f}\n\nBACK:\n{b}"
                        })
                        actual_cids.append(cid)
                    except: pass
                    
                if not items:
                    info("Failed to assemble content payload.")
                    return
                    
                def _bg_run():
                    try:
                        tooltip("Transmitting payload to Google...")
                        resp = client.submit_gemini_batch(items)
                        jname = resp.get("name")
                        if jname:
                            batch_manager.register_job(jname, actual_cids)
                            mw.taskman.run_on_main(lambda jn=jname: info(f"✅ Cloud Batch Initiated: {jn}\nMonitoring setup."))
                            mw.taskman.run_on_main(self.update_batch_status_tab)
                        else:
                            mw.taskman.run_on_main(lambda: info("Unknown transmission fault. No tracking ID returned."))
                    except Exception as e:
                        # Graceful bubble for our newly trapped "FREE TIER" exception
                        err_msg = str(e)
                        mw.taskman.run_on_main(lambda msg=err_msg: info(msg))
                        
                import threading
                threading.Thread(target=_bg_run, daemon=True).start()
                
        except Exception as e:
            logger.error(f"Config UI Batch Start Master Error: {e}")
            info(f"Error attempting start: {e}")
            info(f"Launch failed: {e}")

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
        self.mathjax_format_cb.setCurrentText(c.get("mathjax_format", "delimiters"))
        self.fix_latex_cb.setChecked(c.get("fix_latex", False))
        self.show_hints_cb.setChecked(c.get("show_hints_button", True))
        self.show_options_cb.setChecked(c.get("show_options_button", True))
        self.show_on_card_cb.setChecked(c.get("show_on_card", True))
        self.show_in_bottom_bar_cb.setChecked(c.get("show_in_bottom_bar", True))
        self.show_in_popup_cb.setChecked(c.get("show_in_popup", False))
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
            # Add to combobox if not present (e.g. custom user model)
            if edit.findText(model_name) == -1:
                edit.addItem(model_name)
            edit.setCurrentText(model_name)
            
        local = c.get("local_endpoint", {}) or {}
        self.local_url_edit.setText(local.get("base_url", ""))
        self.local_model_edit.setText(local.get("model", ""))
        self.local_api_key_edit.setText(local.get("api_key", ""))
        self.local_fallback_cb.setChecked(local.get("enabled", False))
        
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        
        self.target_fields_edit.setText(", ".join(c.get("target_fields", [])))
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
        custom_names = list(self.custom_providers_data.keys())
        self.ai_provider_cb.addItems(providers + custom_names)
        if current_selection:
            self.ai_provider_cb.setCurrentText(current_selection)

        # Get current order from layout
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
                
        # Rebuild models layout
        if hasattr(self, 'models_layout') and self.models_layout is not None:
            while self.models_layout.count():
                item = self.models_layout.takeAt(0)
                if item:
                    w = item.widget()
                    if w: w.deleteLater()
            
            self.model_edits = {}
            for p in new_priority:
                if p == "local":
                    continue
                w = ProviderRowWidget(p, self)
                if p in current_models_state:
                    w.edit.setCurrentText(current_models_state[p])
                elif p in self.config.get("models", {}):
                    w.edit.setCurrentText(self.config["models"][p])
                self.model_edits[p] = w.edit
                self.models_layout.addWidget(w)

    def on_fetch_all_models(self):
        tooltip("Starting batch model fetch...")
        for provider, combobox in self.model_edits.items():
            # We reuse on_fetch_models but without individual tooltips to avoid spam
            self.on_fetch_models(provider, combobox, silent=True)
        tooltip("Finished fetching models for all configured providers.")

    def on_fetch_models(self, provider, combobox, silent=False):
        api_key = self.api_key_edits[provider].text().strip() if provider in self.api_key_edits else ""
        if not api_key and provider != "local":
            if not silent:
                info(f"Please enter an API key for {provider.capitalize()} first.")
            return

        # Create a temporary config to use the API key from the UI
        temp_config = self.config.copy()
        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
        temp_config["api_keys"][provider] = api_key
        
        client = AIClient(temp_config)
        combobox.setEnabled(False)
        if not silent:
            tooltip(f"Fetching models for {provider.capitalize()}...")
        
        # In a real app we'd use a thread, but for simple GETs we'll do it inline for now
        # to keep the code simpler. urllib will block briefly.
        try:
            models = client.fetch_models(provider)
            if models:
                current_text = combobox.currentText()
                combobox.clear()
                # Sort models and ensure current one is at top
                models = sorted(list(set(models)))
                if current_text and current_text not in models:
                    models.insert(0, current_text)
                combobox.addItems(models)
                if current_text:
                    combobox.setCurrentText(current_text)
                if not silent:
                    tooltip(f"Found {len(models)} models for {provider.capitalize()}")
            else:
                if not silent:
                    info(f"Could not fetch models for {provider.capitalize()}. Check your API key and connection.")
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            if not silent:
                info(f"Error fetching models: {e}")
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
            if askUser(f"⚠️ WARNING: This will immediately restore all settings in the 'General' tab to their default values.\n\nAny custom changes in this tab will be lost. Continue?"):
                self.on_restore_general()
                tooltip("General defaults restored.")
        elif tab_text == "AI Providers":
            if askUser(f"⚠️ WARNING: This will immediately restore all model names and fallback priorities in the 'AI Providers' tab to their default values (your API keys will be preserved).\n\nContinue?"):
                self.on_restore_providers()
                tooltip("Provider defaults restored.")
        elif tab_text == "Advanced":
            if askUser(f"⚠️ WARNING: This will immediately restore the System Prompt and Note Type settings in the 'Advanced' tab to their default values.\n\nYour custom prompt and field mappings will be lost. Continue?"):
                self.on_restore_advanced()
                tooltip("Advanced defaults restored.")
        else:
            tooltip("No defaults to restore for this tab.")

    def on_restore_models_only(self):
        if not self.default_config: return
        if not askUser("⚠️ WARNING: This will immediately restore all selected Model Names to their factory default values.\n\nContinue?"):
            return
            
        c = self.default_config
        models = c.get("models", {}) or {}
        for p, edit in self.model_edits.items():
            model_name = models.get(p, DEFAULT_MODELS.get(p, ""))
            if edit.findText(model_name) == -1:
                edit.addItem(model_name)
            edit.setCurrentText(model_name)
            
        logger.info("Restored default model selections.")
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
        logger.info("Restored General defaults.")
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
            if p == "local":
                continue
            w = ProviderRowWidget(p, self)
            model_name = models.get(p, DEFAULT_MODELS.get(p, ""))
            if w.edit.findText(model_name) == -1:
                w.edit.addItem(model_name)
            w.edit.setCurrentText(model_name)
            self.model_edits[p] = w.edit
            self.models_layout.addWidget(w)
            
        local = c.get("local_endpoint", {}) or {}
        self.local_url_edit.setText(local.get("base_url", ""))
        self.local_model_edit.setText(local.get("model", ""))
        self.local_fallback_cb.setChecked(local.get("enabled", False))
        
        logger.info("Restored Provider defaults (models, priority; API keys preserved).")
        tooltip("Provider defaults restored.")

    def on_restore_advanced(self):
        if not self.default_config: return
        c = self.default_config
        self.target_fields_edit.setText(", ".join(c.get("target_fields", [])))
        self.system_prompt_edit.setPlainText(c.get("system_prompt", ""))
        self.note_type_fields_data = c.get("note_type_fields", {}).copy()
        self.on_nt_changed()
        
        self.note_fields_edit.setPlainText(json.dumps(self.note_type_fields_data, indent=4))
        # Don't reset Raw Editor completely unless user specifically wants to
        logger.info("Restored Advanced defaults (System prompt, note fields).")
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
            if self.raw_toggle.isChecked():
                raw_config = json.loads(self.raw_editor.toPlainText() or "{}")
                mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(raw_config))
                logger.info("Configuration saved via Raw JSON Editor.")
                if close:
                    self.accept()
                else:
                    tooltip("Configuration saved.")
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
            new_config["models"] = {
                p: (edit.currentText().strip() or DEFAULT_MODELS.get(p, ""))
                for p, edit in self.model_edits.items()
            }
            new_config["local_endpoint"] = {
                "enabled": self.local_fallback_cb.isChecked(),
                "base_url": self.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "model": self.local_model_edit.text().strip() or DEFAULT_MODELS["local"],
                "api_key": self.local_api_key_edit.text().strip()
            }
            new_config["system_prompt"] = self.system_prompt_edit.toPlainText()
            new_config["target_fields"] = [f.strip() for f in self.target_fields_edit.text().split(",") if f.strip()]
            
            if hasattr(self, 'nt_cb'):
                new_config["note_type_fields"] = self.note_type_fields_data
            else:
                new_config["note_type_fields"] = json.loads(self.note_fields_edit.toPlainText())
            
            new_config["custom_providers"] = self.custom_providers_data
            
            # Save provider priority
            priority = []
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget):
                    priority.append(w.provider)
            new_config["provider_priority"] = priority
            
            # Log changes
            changed = []
            old_config = self.config
            for k, v in new_config.items():
                if k not in old_config or old_config[k] != v:
                    changed.append(k)
            
            if changed:
                logger.info(f"Configuration saved. Changes in: {', '.join(changed)}")
            else:
                logger.info("Configuration saved. No changes detected.")

            mw.addonManager.writeConfig(ADDON_PACKAGE, self._normalize_config(new_config))
            # Update current config to detect future changes
            self.config = new_config
            if close:
                self.accept()
            else:
                tooltip("Configuration saved.")
        except Exception as e:
            info(f"Error saving configuration: {e}")

    def _normalize_config(self, config):
        config = dict(config or {})

        raw_api_keys = config.get("api_keys", {}) or {}
        api_keys = dict(raw_api_keys) if isinstance(raw_api_keys, dict) else {}
        for provider in PROVIDER_ORDER:
            if provider != "local":
                api_keys.setdefault(provider, "")
        config["api_keys"] = api_keys

        models = dict(DEFAULT_MODELS)
        raw_models = config.get("models", {}) or {}
        if isinstance(raw_models, dict):
            models.update(raw_models)
        for provider, model in list(models.items()):
            models[provider] = LEGACY_MODEL_REPLACEMENTS.get((provider, model), model)
        config["models"] = models

        model_fallbacks = {
            provider: list(fallbacks)
            for provider, fallbacks in MODEL_FALLBACKS.items()
        }
        raw_model_fallbacks = config.get("model_fallbacks", {}) or {}
        if isinstance(raw_model_fallbacks, dict):
            model_fallbacks.update(raw_model_fallbacks)
        config["model_fallbacks"] = model_fallbacks

        # Normalize provider priority
        custom_providers = config.get("custom_providers", {})
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        
        custom_names = list(custom_providers.keys())
        priority = config.get("provider_priority", [])
        old_default = [
            "gemini",
            "groq",
            "openrouter",
            "sambanova",
            "cerebras",
            "huggingface",
            "openai",
            "anthropic",
            "deepseek",
            "mistral",
            "together",
            "nvidia",
            "grok",
            "local"
        ]
        if not isinstance(priority, list) or priority == old_default:
            priority = PROVIDER_ORDER + custom_names
        
        available = set(PROVIDER_ORDER + custom_names)
        priority = [p for p in priority if p in available]
        for p in PROVIDER_ORDER + custom_names:
            if p not in priority:
                priority.append(p)
        config["provider_priority"] = priority

        local = {
            "enabled": False,
            "base_url": "http://localhost:11434/v1",
            "model": DEFAULT_MODELS["local"],
            "api_key": "",
        }
        raw_local = config.get("local_endpoint", {}) or {}
        if isinstance(raw_local, dict):
            local.update(raw_local)
        config["local_endpoint"] = local

        config.setdefault("ai_provider", "openai")
        config.setdefault("storage_mode", "json")
        config.setdefault("mathjax_format", "delimiters")
        config.setdefault("fix_latex", False)
        config.setdefault("target_fields", [])
        config.setdefault("system_prompt", "")
        config.setdefault("show_hints_button", True)
        config.setdefault("show_options_button", True)
        if not isinstance(config.get("custom_providers", {}), dict):
            config["custom_providers"] = {}
        else:
            config.setdefault("custom_providers", {})
        if not isinstance(config.get("note_type_fields", {}), dict):
            config["note_type_fields"] = {}
        else:
            config.setdefault("note_type_fields", {})
        try:
            config["options_count"] = max(1, min(int(config.get("options_count", 4)), 10))
        except (TypeError, ValueError):
            config["options_count"] = 4
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

        # Normalize shortcuts
        default_shortcuts = {
            "modifier": "alt",
            "generate": "1",
            "toggle-options": "2",
            "toggle-hints": "3",
            "clear": "4",
            "refresh": "5",
            "show-json": "6"
        }
        shortcuts = dict(default_shortcuts)
        raw_shortcuts = config.get("shortcuts", {}) or {}
        if isinstance(raw_shortcuts, dict):
            shortcuts.update(raw_shortcuts)
        config["shortcuts"] = shortcuts

        return config

_config_dialog_instance = None

def on_config_dialog(parent=None):
    global _config_dialog_instance
    
    # Detach completely to ensure users can minimize/use Main Anki freely
    dialog_parent = None
    
    if _config_dialog_instance is not None:
        try:
            if _config_dialog_instance.isVisible():
                 _config_dialog_instance.raise_()
                 _config_dialog_instance.activateWindow()
                 return
        except RuntimeError:
            _config_dialog_instance = None # Instance was deleted
            
    _config_dialog_instance = ConfigDialog(dialog_parent)
    
    # Modeless configuration ensuring total UI independence
    _config_dialog_instance.setWindowFlag(Qt.WindowType.Window, True)
    _config_dialog_instance.setWindowModality(Qt.WindowModality.NonModal)
    
    # Defer show call to next event loop cycle.
    # This crucial break prevents the calling modal Addon Manager 
    # from locking out the newly spawned config widget.
    QTimer.singleShot(50, _config_dialog_instance.show)

def init_config_ui():
    mw.addonManager.setConfigAction(ADDON_PACKAGE, on_config_dialog)
    
    # Add Tools menu entry so the window can be opened any time
    action = mw.form.menuTools.addAction("AI-Hints Config")
    action.triggered.connect(lambda: on_config_dialog(mw))
