import os
from aqt.qt import *
from aqt.utils import askUser
from ..logger import logger, info, tooltip
from ..batch_manager import batch_manager

class LogTabMixin:
    def _create_log_tab(self):
        """Constructs the Tab 7: Logs UI"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Level filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Level:"))
        self.log_level_cb = QComboBox()
        self.log_level_cb.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_cb.currentIndexChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_level_cb)
        
        filter_layout.addWidget(QLabel(" Source:"))
        self.log_source_cb = QComboBox()
        self.log_source_cb.addItems(["ALL", "Antigravity Proxy", "Batch Processing", "Standard Addon"])
        self.log_source_cb.currentIndexChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_source_cb)
        
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

        stop_btn = QPushButton("🛑 Stop All")
        stop_btn.setToolTip("Emergency stop for all background tasks and batch generations.")
        stop_btn.setStyleSheet("color: white; background-color: #d9534f; font-weight: bold; padding: 3px 8px;")
        stop_btn.clicked.connect(self.emergency_stop)
        filter_layout.addWidget(stop_btn)
        
        layout.addLayout(filter_layout)
        
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.log_view)
        
        # NOTE: Do NOT call self.load_log() here. It is called by on_tab_changed()
        # when the user switches to this tab. Calling it during construction
        # blocks the main thread before the dialog is shown, freezing Anki.
        return tab

    def emergency_stop(self):
        if askUser("Are you sure you want to stop all active generations? This will clear the current queue."):
            batch_manager.stop_all()
            self.load_log()

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
            
            source_filter = self.log_source_cb.currentText()
            if source_filter == "Antigravity Proxy":
                lines = [l for l in lines if "[Proxy]" in l]
            elif source_filter == "Batch Processing":
                lines = [l for l in lines if "Batch" in l or "Queue" in l]
            elif source_filter == "Standard Addon":
                lines = [l for l in lines if "[Proxy]" not in l]
            
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
