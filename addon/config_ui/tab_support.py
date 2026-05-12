import os
from aqt.qt import *

class SupportTabMixin:
    def _create_support_tab(self):
        """Constructs the Tab 6: Support UI"""
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
