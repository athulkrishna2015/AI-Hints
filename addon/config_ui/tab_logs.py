import os
import re
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
        self.log_level_cb.setCurrentText("INFO")
        self.log_level_cb.currentIndexChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_level_cb)
        
        filter_layout.addWidget(QLabel(" Source:"))
        self.log_source_cb = QComboBox()
        self.log_source_cb.addItems(["ALL", "Antigravity Proxy", "Batch Processing", "Pre-generation", "Model Testing", "Standard Addon"])
        self.log_source_cb.currentIndexChanged.connect(self.load_log)
        filter_layout.addWidget(self.log_source_cb)
        
        filter_layout.addWidget(QLabel(" Search:"))
        self.log_search_edit = QLineEdit()
        self.log_search_edit.setPlaceholderText("Filter text...")
        self.log_search_edit.setClearButtonEnabled(True)
        self.log_search_edit.setMinimumWidth(180)
        
        # Debounced search timer
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self.load_log)
        self.log_search_edit.textChanged.connect(lambda: self._search_timer.start(300))
        
        filter_layout.addWidget(self.log_search_edit)

        self.match_count_label = QLabel("")
        self.match_count_label.setStyleSheet("color: #6c757d; font-size: 11px; font-weight: bold;")
        filter_layout.addWidget(self.match_count_label)
        
        filter_layout.addStretch()
        
        self.auto_clear_cb = QCheckBox("Clear on startup")
        self.auto_clear_cb.setToolTip("Automatically clear the log file every time Anki starts.")
        filter_layout.addWidget(self.auto_clear_cb)

        self.live_label = QLabel("● Live")
        self.live_label.setStyleSheet("color: green; font-weight: bold;")
        self.live_label.setVisible(False)
        filter_layout.addWidget(self.live_label)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Manually refresh the log view")
        refresh_btn.clicked.connect(self.load_log)
        filter_layout.addWidget(refresh_btn)
        
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
        
        self.log_view = QTextBrowser()
        self.log_view.setReadOnly(True)
        self.log_view.setOpenExternalLinks(False)
        self.log_view.anchorClicked.connect(self._on_log_anchor_clicked)
        self.log_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard |
            Qt.TextInteractionFlag.LinksAccessibleByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
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
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            if level_filter != "ALL":
                lines = [l for l in lines if f" - {level_filter} - " in l]
            
            source_filter = self.log_source_cb.currentText()
            if source_filter == "Antigravity Proxy":
                lines = [l for l in lines if "[Proxy]" in l]
            elif source_filter == "Batch Processing":
                lines = [l for l in lines if "Batch" in l or "Queue" in l]
            elif source_filter == "Pre-generation":
                lines = [l for l in lines if "pre-generation" in l.lower() or "pregen" in l.lower()]
            elif source_filter == "Model Testing":
                lines = [l for l in lines if "[MODEL_TEST]" in l]
            elif source_filter == "Standard Addon":
                lines = [l for l in lines if "[Proxy]" not in l and "[MODEL_TEST]" not in l]
            
            if search_filter:
                lines = [l for l in lines if search_filter in l.lower()]
            
            if not lines:
                content = "No entries matching the selected filters."
                content_html = "<i>No entries matching the selected filters.</i>"
            else:
                content = "".join(lines)
                html_lines = []
                for line in lines:
                    stripped = line.rstrip("\r\n")
                    escaped = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    
                    # 1. Hyperlink URLs
                    escaped = re.sub(
                        r'(https?://[^\s<>"]+)',
                        r'<a href="\1" style="color: #0d6efd; text-decoration: underline;">\1</a>',
                        escaped
                    )
                    
                    # 2. Hyperlink 13-digit Anki IDs (but not inside the a-tags we just made)
                    # We use a custom replace function to avoid matching within href attributes or text content of existing tags
                    def _link_anki_ids(m):
                        return re.sub(r'\b(\d{13})\b', r'<a href="browse:cid:\1" title="Open in Browser" style="color: #0d6efd; text-decoration: underline;">\1</a>', m.group(0))
                    
                    escaped = re.sub(r'(<a[^>]*>.*?</a>)|(.*?)(?=<a|$)', lambda m: m.group(1) or _link_anki_ids(m), escaped)
                    
                    color = None
                    font_weight = "normal"
                    
                    if " - DEBUG - " in escaped:
                        color = "#8a8a8a"  # gray
                    elif " - WARNING - " in escaped:
                        color = "#fd7e14"  # orange
                        font_weight = "bold"
                    elif " - ERROR - " in escaped or " - CRITICAL - " in escaped:
                        color = "#d9534f"  # red
                        font_weight = "bold"
                    elif " - INFO - " in escaped:
                        if "success" in escaped.lower():
                            color = "#198754"  # green
                            font_weight = "bold"
                        elif "abort" in escaped.lower() or "stop" in escaped.lower() or "aborted" in escaped.lower():
                            color = "#f0ad4e"  # orange-yellow
                            font_weight = "bold"
                    
                    style = ""
                    if color:
                        style += f"color: {color};"
                    if font_weight != "normal":
                        style += f"font-weight: {font_weight};"
                    
                    if style:
                        html_lines.append(f"<span style='{style}'>{escaped}</span>")
                    else:
                        html_lines.append(escaped)
                
                content_html = "<pre style='margin:0; font-family:monospace; white-space:pre-wrap;'>" + "<br/>".join(html_lines) + "</pre>"

            if self.log_view.toPlainText() == content:
                return
            
            # 🚦 Selection Safety: If user is currently selecting text, DO NOT update
            # as it will clear their selection and make copying impossible.
            if self.log_view.textCursor().hasSelection():
                return

            vbar = self.log_view.verticalScrollBar()
            prev_value = vbar.value()
            was_at_bottom = prev_value >= vbar.maximum() - 10
            
            self.log_view.setHtml(content_html)
            
            if was_at_bottom:
                vbar.setValue(vbar.maximum())
            else:
                vbar.setValue(prev_value)

            # 🖍️ Apply Search Highlighting
            self._apply_search_highlighting(search_filter)

        except Exception as e:
            if not self.log_view.textCursor().hasSelection():
                self.log_view.setPlainText(f"Error reading log: {e}")

    def _apply_search_highlighting(self, pattern: str):
        """Highlights all occurrences of the search pattern in the log view."""
        extra_selections = []
        
        if not pattern or len(pattern) < 2:
            self.log_view.setExtraSelections(extra_selections)
            return

        # Case-insensitive search to match the filter logic
        cursor = self.log_view.document().find(pattern, 0) 
        
        # Color palette for highlighting (Warm Yellow)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff3cd"))
        fmt.setForeground(QColor("#856404"))
        fmt.setFontWeight(QFont.Weight.Bold)

        # Loop through all matches
        count = 0
        while not cursor.isNull():
            count += 1
            if count > 2000: break # Higher safety limit for log files
            
            selection = QTextEdit.ExtraSelection()
            selection.format = fmt
            selection.cursor = cursor
            extra_selections.append(selection)
            
            cursor = self.log_view.document().find(pattern, cursor)

        self.log_view.setExtraSelections(extra_selections)
        
        # Update match count label
        if not pattern:
            self.match_count_label.setText("")
        else:
            limit_hit = " (limit hit)" if count > 2000 else ""
            self.match_count_label.setText(f"{count} matches{limit_hit}")

    def clear_log(self):
        log_file = os.path.join(self.addon_dir, "ai_hints.log")
        try:
            open(log_file, "w", encoding="utf-8").close()
            self.log_view.setPlainText("Log cleared.")
            logger.info("Log cleared by user.")
        except Exception as e:
            info(f"Could not clear log: {e}")

    def _on_log_anchor_clicked(self, qurl):
        """Intercepts clicks on anchor tags to either open Anki Browser or an external URL."""
        url = qurl.toString().strip()
        if url.startswith("browse:"):
             query = url.split(":", 1)[1] 
             from aqt import dialogs, mw
             browser = dialogs.open("Browser", mw)
             try:
                  browser.search_for(query)
             except AttributeError:
                  try:
                       browser.search(query)
                  except (AttributeError, TypeError):
                       try:
                            try: browser.form.searchEdit.lineEdit().setText(query)
                            except AttributeError: browser.form.searchEdit.setText(query)
                            try: browser.search() 
                            except (AttributeError, TypeError): browser.onSearchActivated()
                       except Exception: pass
             browser.setFocus()
             browser.activateWindow()
             browser.raise_()
        else:
             QDesktopServices.openUrl(qurl)
