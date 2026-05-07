import os
import json
from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import showInfo, tooltip

class ConfigDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("AI-Hints Configuration")
        self.setMinimumSize(500, 600)
        self.addon_dir = os.path.dirname(__file__)
        self.config = mw.addonManager.getConfig(__name__)
        
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        # --- Tab 1: Settings ---
        self.settings_tab = QWidget()
        settings_layout = QVBoxLayout()
        
        self.config_editor = QTextEdit()
        self.config_editor.setPlainText(json.dumps(self.config, indent=4))
        self.config_editor.setAcceptRichText(False)
        settings_layout.addWidget(QLabel("Edit Configuration (JSON):"))
        settings_layout.addWidget(self.config_editor)
        
        self.settings_tab.setLayout(settings_layout)
        self.tabs.addTab(self.settings_tab, "Settings")
        
        # --- Tab 2: Support ---
        self.support_tab = QWidget()
        support_main_layout = QVBoxLayout()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        support_data = [
            {
                "name": "Ko-fi",
                "id": "https://ko-fi.com/D1D01W6NQT",
                "qr": None,
                "is_link": True
            },
            {
                "name": "UPI",
                "id": "athulkrishnasv2015-2@okhdfcbank",
                "qr": "UPI.jpg"
            },
            {
                "name": "Bitcoin (BTC)",
                "id": "bc1qrrek3m7sr33qujjrktj949wav6mehdsk057cfx",
                "qr": "BTC.jpg"
            },
            {
                "name": "Ethereum (ETH)",
                "id": "0xce6899e4903EcB08bE5Be65E44549fadC3F45D27",
                "qr": "ETH.jpg"
            }
        ]
        
        for item in support_data:
            group = QGroupBox(item["name"])
            group_layout = QVBoxLayout()
            
            # QR Code Image
            if item.get("qr"):
                qr_label = QLabel()
                qr_path = os.path.join(self.addon_dir, "Support", item["qr"])
                if os.path.exists(qr_path):
                    pixmap = QPixmap(qr_path)
                    qr_label.setPixmap(pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    group_layout.addWidget(qr_label)
            
            # ID and Buttons
            id_layout = QHBoxLayout()
            id_text = QLineEdit(item["id"])
            id_text.setReadOnly(True)
            id_layout.addWidget(id_text)

            if item.get("is_link"):
                open_btn = QPushButton("Open in Browser")
                open_btn.clicked.connect(lambda checked, url=item["id"]: QDesktopServices.openUrl(QUrl(url)))
                id_layout.addWidget(open_btn)
            else:
                copy_btn = QPushButton("Copy")
                copy_btn.clicked.connect(lambda checked, text=item["id"]: self.copy_to_clipboard(text))
                id_layout.addWidget(copy_btn)
            
            group_layout.addLayout(id_layout)
            group.setLayout(group_layout)
            scroll_layout.addWidget(group)
            
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        support_main_layout.addWidget(scroll)
        
        self.support_tab.setLayout(support_main_layout)
        self.tabs.addTab(self.support_tab, "Support")
        
        layout.addWidget(self.tabs)
        
        # --- Bottom Buttons ---
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.save_config)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.setLayout(layout)

    def copy_to_clipboard(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        tooltip("Copied to clipboard")

    def save_config(self):
        try:
            new_config = json.loads(self.config_editor.toPlainText())
            mw.addonManager.writeConfig(__name__, new_config)
            self.accept()
        except Exception as e:
            showInfo(f"Invalid JSON configuration: {e}")

def on_config_dialog(parent=None):
    if parent is None:
        parent = mw
    ConfigDialog(parent).exec()

def init_config_ui():
    mw.addonManager.setConfigAction(__name__, on_config_dialog)
