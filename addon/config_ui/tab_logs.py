import os
import re
from collections import deque
from aqt.qt import *
from aqt.utils import askUser
from ..logger import logger, info, tooltip
from ..batch_manager import batch_manager

# Render cap: at most this many *matching* lines are turned into HTML per
# refresh (newest ones), keeping setHtml() cheap even on multi-MB logs.
LOG_RENDER_CAP = 4000


def _linkify_line(stripped: str) -> str:
    """Escape + hyperlink URLs / 13-digit Anki IDs for one log line."""
    escaped = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 1. Hyperlink URLs
    escaped = re.sub(
        r'(https?://[^\s<>"]+)',
        r'<a href="\1" style="color: #0d6efd; text-decoration: underline;">\1</a>',
        escaped,
    )

    # 2. Hyperlink 13-digit Anki IDs (but not inside the a-tags we just made)
    def _link_anki_ids(m):
        return re.sub(r'\b(\d{13})\b', r'<a href="browse:cid:\1" title="Open in Browser" style="color: #0d6efd; text-decoration: underline;">\1</a>', m.group(0))

    escaped = re.sub(r'(<a[^>]*>.*?</a>)|(.*?)(?=<a|$)', lambda m: m.group(1) or _link_anki_ids(m), escaped)
    return escaped


def _line_to_html(line: str) -> str:
    stripped = line.rstrip("\r\n")
    escaped = _linkify_line(stripped)

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
        return f"<span style='{style}'>{escaped}</span>"
    return escaped


def _line_matches(line: str, level_filter: str, source_filter: str, search_lower: str) -> bool:
    if level_filter != "ALL" and f" - {level_filter} - " not in line:
        return False
    if source_filter == "Antigravity Proxy":
        if "[Proxy]" not in line:
            return False
    elif source_filter == "Batch Processing":
        if "Batch" not in line and "Queue" not in line:
            return False
    elif source_filter == "Pre-generation":
        low = line.lower()
        if "pre-generation" not in low and "pregen" not in low:
            return False
    elif source_filter == "Model Testing":
        if "[MODEL_TEST]" not in line:
            return False
    elif source_filter == "Standard Addon":
        if "[Proxy]" in line or "[MODEL_TEST]" in line:
            return False
    if search_lower and search_lower not in line.lower():
        return False
    return True


def process_log_file(path: str, level_filter: str, source_filter: str, search_filter: str,
                     max_lines: int = LOG_RENDER_CAP) -> dict:
    """Streams the log file and builds the render payload. Runs OFF the GUI thread.

    Only the newest `max_lines` matching lines are HTML-rendered (older matches
    collapse into a truncation notice), so huge rotating logs stay responsive.
    """
    search_lower = (search_filter or "").strip().lower()
    total = 0
    matched_total = 0
    kept = deque(maxlen=max(1, int(max_lines)))

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            total += 1
            if not _line_matches(line, level_filter, source_filter, search_lower):
                continue
            matched_total += 1
            kept.append(line)

    truncated = matched_total > len(kept)
    lines = list(kept)

    if not lines:
        content_html = "<i>No entries matching the selected filters.</i>"
        content_plain = "No entries matching the selected filters."
    else:
        html_lines = [_line_to_html(l) for l in lines]
        if truncated:
            skipped = matched_total - len(lines)
            html_lines.insert(0, (
                f"<span style='color:#6c757d;'>&#9888; {skipped:,} older matching lines hidden "
                f"(render cap {max_lines:,}). Narrow with Level/Source/Search or raise "
                f"AI-Hints' log render cap.</span>"
            ))
        content_html = "<pre style='margin:0; font-family:monospace; white-space:pre-wrap;'>" + "<br/>".join(html_lines) + "</pre>"
        content_plain = "".join(lines)

    return {
        "total": total,
        "matched_total": matched_total,
        "truncated": truncated,
        "content_html": content_html,
        "content_plain": content_plain,
    }


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

        self.debug_logging_cb = QCheckBox("Debug logging")
        self.debug_logging_cb.setToolTip("Enable verbose DEBUG-level log entries (off by default). Useful for diagnosing issues such as the TTS addon interaction.")
        filter_layout.addWidget(self.debug_logging_cb)

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
        try:
            from ..logger import _log_path
            log_file = _log_path()
        except Exception:
            log_file = os.path.join(self.addon_dir, "ai_hints.log")
        if not os.path.exists(log_file):
            self._log_fingerprint = None
            self.log_view.setPlainText("No log file found yet. Errors will appear here after using the add-on.")
            return

        level_filter = self.log_level_cb.currentText()
        source_filter = self.log_source_cb.currentText()
        search_filter = self.log_search_edit.text().strip()

        # Cheap change-detection: the live timer fires every second, so skip
        # all work (even spawning a thread) until the file or filters change.
        fingerprint = None
        try:
            st = os.stat(log_file)
            fingerprint = (st.st_mtime_ns, st.st_size, level_filter, source_filter, search_filter.lower())
        except OSError:
            pass
        if fingerprint is not None and fingerprint == getattr(self, "_log_fingerprint", None):
            return
        self._log_fingerprint = fingerprint

        self._log_gen = getattr(self, "_log_gen", 0) + 1
        gen = self._log_gen

        def _worker():
            # Heavy part (streaming read, filtering, HTML build) runs off the
            # GUI thread with bounded memory (streamed + render-capped).
            return process_log_file(log_file, level_filter, source_filter, search_filter)

        def _apply(fut_or_result):
            if gen != getattr(self, "_log_gen", 0):
                return  # stale result; filters or file changed meanwhile
            try:
                # Anki's taskman hands the callback a concurrent.futures.Future;
                # older paths / headless fallback deliver the raw value.
                result = fut_or_result.result() if hasattr(fut_or_result, "result") else fut_or_result
            except Exception as e:
                if not self.log_view.textCursor().hasSelection():
                    self.log_view.setPlainText(f"Error reading log: {e}")
                return
            try:
                self._apply_log_result(result, search_filter)
            except Exception as e:
                if not self.log_view.textCursor().hasSelection():
                    self.log_view.setPlainText(f"Error rendering log: {e}")

        try:
            from aqt import mw
            mw.taskman.run_in_background(_worker, on_done=_apply)
        except Exception:
            # Headless/test fallback: no taskman available.
            _apply(_worker())

    def _apply_log_result(self, result, search_filter: str):
        label_parts = []
        if result["total"]:
            label_parts.append(f"{result['matched_total']:,} / {result['total']:,} lines match")
        if result["truncated"]:
            label_parts.append(f"showing newest {LOG_RENDER_CAP:,} (memory-safe cap)")
        self.match_count_label.setText("  ·  ".join(label_parts))

        content_plain = result["content_plain"]
        if self.log_view.toPlainText() == content_plain:
            return

        # 🚦 Selection Safety: If user is currently selecting text, DO NOT update
        # as it will clear their selection and make copying impossible.
        if self.log_view.textCursor().hasSelection():
            return

        vbar = self.log_view.verticalScrollBar()
        prev_value = vbar.value()
        was_at_bottom = prev_value >= vbar.maximum() - 10

        self.log_view.setHtml(result["content_html"])

        if was_at_bottom:
            vbar.setValue(vbar.maximum())
        else:
            vbar.setValue(prev_value)

        # 🖍️ Apply Search Highlighting
        self._apply_search_highlighting(search_filter)

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
        try:
            from ..logger import _log_path
            log_file = _log_path()
        except Exception:
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
