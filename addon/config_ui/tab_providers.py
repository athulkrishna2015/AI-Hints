import json
import os
import re
from aqt import mw
from aqt.qt import *
from ..logger import info, tooltip
from ..ai_client import DEFAULT_MODELS, MODEL_SUGGESTIONS, MODEL_FALLBACKS, PROVIDER_ORDER
from ..ai_client import is_model_blacklisted, is_model_deprecated
from .widgets import (CustomProviderDialog, ProviderRowWidget, PERSISTENT_TEST_STATUSES,
                      FETCH_CANCELLATIONS, NEWLY_ADDED_MODELS, MISSING_FROM_FETCH,
                      GLOBAL_NEWLY_ADDED_MODELS, GLOBAL_MISSING_FROM_FETCH,
                      _get_blacklist_remaining)

DEFAULT_TEST_QUESTION = "Why does a rotating magnet fall slower through a copper tube than a non-magnetic mass of the same size?"
DEFAULT_TEST_ANSWER = "Due to Faraday's law of induction and Lenz's law, the falling magnet induces eddy currents in the copper tube, creating an opposing magnetic field that exerts an upward electromagnetic braking force."

TEST_CANCELLATIONS = {}


def cancel_other_model_tests(keep_key):
    """Cancel every other in-flight model-test run so two tests from different
    dialogs (e.g. a per-provider fallback test and the global priority test)
    never run at the same time and interleave their log output."""
    for k in list(TEST_CANCELLATIONS.keys()):
        if k != keep_key:
            TEST_CANCELLATIONS[k] = True


# Highlight colours for newly added vs missing vs deprecated models in fallback lists.
# Kept as hex strings and resolved lazily so imports stay safe in headless tests.
COL_NEW_BG = "#d9f2cd"
COL_NEW_FG = "#1e7e34"
COL_MISSING_BG = "#fff0c8"
COL_MISSING_FG = "#8a6d1a"
COL_DEP_BG = "#ffe1e1"
COL_DEP_FG = "#b71c1c"

def _build_remove_menu(callback):
    menu = QMenu()
    menu.addAction("Remove Selected", lambda: callback("selected"))
    menu.addAction("Remove Deprecated", lambda: callback("deprecated"))
    menu.addAction("Remove No Longer Returned", lambda: callback("missing"))
    menu.addAction("Remove Deprecated & No Longer Returned", lambda: callback("flagged"))
    return menu


def _build_test_menu(callback):
    menu = QMenu()
    menu.addAction("Test Checked", lambda: callback("checked"))
    menu.addAction("Test Row", lambda: callback("row"))
    menu.addAction("Test All", lambda: callback("all"))
    return menu


def normalized_model_key(model):
    name = (model or "").strip().casefold()
    if name.endswith(":free"):
        name = name[: -len(":free")]
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", name)


def cluster_pairs_by_model(pairs):
    seen = {}
    for _, model in pairs:
        key = normalized_model_key(model)
        if key not in seen:
            seen[key] = len(seen)
    return [pairs[i] for i in sorted(range(len(pairs)), key=lambda i: (seen[normalized_model_key(pairs[i][1])], i))]


def sort_pairs_by(pairs, kind):
    if kind == "model":
        return sorted(pairs, key=lambda p: (normalized_model_key(p[1]), p[1].casefold(), p[0].casefold()))
    return sorted(pairs, key=lambda p: (p[0].casefold(), p[1].casefold()))


def prune_orphan_pairs(pairs, known_providers):
    current, orphaned = [], 0
    for item in pairs or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            if item[0] in known_providers:
                current.append((item[0], item[1]))
            else:
                orphaned += 1
    return current, orphaned


def provider_enabled_pairs(main_dialog):
    """Return provider/model pairs enabled in the per-provider fallback data."""
    result = []
    models = getattr(main_dialog, "config", {}).get("models", {}) or {}
    fallbacks = getattr(main_dialog, "model_fallbacks_data", {}) or {}
    disabled = getattr(main_dialog, "disabled_fallback_models_data", {}) or {}
    providers = set(fallbacks) | set(models)
    custom = getattr(main_dialog, "custom_providers_data", {}) or {}
    if isinstance(custom, dict):
        providers.update(custom)
        for provider, data in custom.items():
            if isinstance(data, dict) and data.get("model"):
                models = dict(models)
                models.setdefault(provider, data["model"])
    for provider in sorted(providers):
        blocked = set(disabled.get(provider, []) or [])
        candidates = list(fallbacks.get(provider, []) or [])
        active = models.get(provider, "") if isinstance(models, dict) else ""
        if active:
            candidates.insert(0, active)
        for model in candidates:
            pair = (provider, model)
            if model and model not in blocked and pair not in result:
                result.append(pair)
    return result


class _FallbackTable(QTableWidget):
    MIME_TYPE = "application/x-ai-hints-fallback-rows"

    def __init__(self, drop_handler, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drop_handler = drop_handler
        self._drop_pos = None
        self._scroll_direction = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(45)
        self._scroll_timer.timeout.connect(self._scroll_drag_position)

    def _scroll_drag_position(self):
        if not self._scroll_direction:
            return
        scrollbar = self.verticalScrollBar()
        value = scrollbar.value()
        next_value = value + self._scroll_direction
        if next_value == value:
            self._stop_drag_scroll()
            return
        scrollbar.setValue(next_value)
        self.update()

    def _stop_drag_scroll(self):
        self._scroll_direction = 0
        self._scroll_timer.stop()

    def startDrag(self, supported_actions):
        if not self.selectionModel().selectedRows():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, QByteArray(b"ai-hints-fallback-rows"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            super().dragEnterEvent(event)
            self._drop_pos = event.position().toPoint()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            # Let QTableWidget update its insertion-line painting state. The
            # drop event remains custom so Qt never moves or deletes cells.
            super().dragMoveEvent(event)
            margin = 48
            y = event.position().toPoint().y()
            height = self.viewport().height()
            if y < margin:
                self._scroll_direction = -1
            elif y > height - margin:
                self._scroll_direction = 1
            else:
                self._scroll_direction = 0
                self._scroll_timer.stop()
            if self._scroll_direction and not self._scroll_timer.isActive():
                self._scroll_timer.start()
            self._drop_pos = event.position().toPoint()
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        self._stop_drag_scroll()
        self._drop_pos = None
        self.update()
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            event.ignore()
            return
        self._drop_handler(self, event)

    def dragLeaveEvent(self, event):
        self._stop_drag_scroll()
        self._drop_pos = None
        self.update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_pos is None:
            return
        index = self.indexAt(self._drop_pos)
        if index.isValid():
            rect = self.visualRect(index)
            y = rect.top() if self._drop_pos.y() < rect.center().y() else rect.bottom() + 1
        else:
            y = self.viewport().height()
            if self.rowCount():
                last = self.visualRect(self.model().index(self.rowCount() - 1, 0))
                y = last.bottom() + 1 if last.isValid() else y
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor("#35bfff"), 3))
        painter.drawLine(0, y, self.viewport().width(), y)
        painter.setPen(QPen(QColor("#b9efff"), 1))
        painter.drawLine(0, y - 2, self.viewport().width(), y - 2)
        painter.drawLine(0, y + 2, self.viewport().width(), y + 2)
        painter.end()


class FallbackPriorityDialog(QDialog):
    def _make_fallback_table(self, headers, init_widths=None):
        table = _FallbackTable(self._handle_table_drop)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        for c in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            if init_widths and c in init_widths:
                table.setColumnWidth(c, init_widths[c])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setDragEnabled(True)
        table.setAcceptDrops(True)
        table.setDropIndicatorShown(True)
        table.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        table.setDefaultDropAction(Qt.DropAction.MoveAction)
        table.setStyleSheet("""
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background-color: rgba(0, 140, 186, 0.1); color: black; }
            QTableWidget::drop-indicator { background-color: #1687c7; height: 3px; }
        """)
        if not hasattr(self, "_sort_states"):
            self._sort_states = {}
        return table

    def _handle_table_drop(self, table, event):
        if event.source() is not table:
            event.ignore()
            return
        rows = self._selected_rows(table)
        if not rows:
            event.ignore()
            return
        pos = event.position().toPoint()
        index = table.indexAt(pos)
        boundary = table.rowCount() if not index.isValid() else index.row()
        if index.isValid() and pos.y() >= table.visualRect(index).center().y():
            boundary += 1
        selected = set(rows)
        keys = []
        for row in range(table.rowCount()):
            try:
                key = self._row_key(table, row)
            except (TypeError, IndexError):
                event.ignore()
                return
            if not key or (isinstance(key, (tuple, list)) and len(key) != 2):
                event.ignore()
                return
            keys.append(key)
        moving = [keys[row] for row in rows]
        rest = [key for row, key in enumerate(keys) if row not in selected]
        insert_at = sum(1 for row in range(boundary) if row not in selected)
        wanted = rest[:insert_at] + moving + rest[insert_at:]
        self._reorder_dragged_rows(table, wanted, moving)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def _reorder_dragged_rows(self, table, wanted, selected_keys):
        self._reorder_to_keys(table, wanted)
        table.clearSelection()
        selection_model = table.selectionModel()
        selected_rows = [
            row for row in range(table.rowCount())
            if self._row_key(table, row) in set(selected_keys)
        ]
        if selected_rows:
            table.setCurrentCell(selected_rows[0], 0)
        for row in selected_rows:
            selection_model.select(
                table.model().index(row, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        self._clear_sort_indicator(table)

    def _init_fallback_table(self, headers, init_widths=None):
        self.table = self._make_fallback_table(headers, init_widths)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    def _tbl(self, table):
        return table if table is not None else self.table

    def _row_key(self, table, row):
        raise NotImplementedError

    def _row_checked(self, table, row):
        item = table.item(row, 0)
        return bool(item and item.checkState() == Qt.CheckState.Checked)

    def _row_search_text(self, table, row):
        raise NotImplementedError

    def _sort_entry_key(self, table, col):
        return None

    def _reorder_to_keys(self, table, wanted):
        raise NotImplementedError

    def _after_filter(self):
        pass

    def _ensure_visible_widgets(self, table=None):
        pass

    def eventFilter(self, obj, event):
        tables = [t for t in (getattr(self, "table", None), getattr(self, "enabled_table", None), getattr(self, "disabled_table", None)) if t is not None]
        if obj in [t.viewport() for t in tables] and event.type() in (
            QEvent.Type.Show,
            QEvent.Type.Resize,
        ):
            self._ensure_visible_widgets()
        return super().eventFilter(obj, event)

    def _selected_rows(self, table=None):
        t = self._tbl(table)
        selected = {index.row() for index in t.selectionModel().selectedRows()}
        if not selected and t.currentRow() != -1:
            selected = {t.currentRow()}
        return sorted(selected)

    def _split_tables(self):
        return tuple(t for t in (getattr(self, "enabled_table", None), getattr(self, "disabled_table", None)) if t is not None)

    def _tables(self):
        return self._split_tables()

    def _focused_table(self):
        for table in self._split_tables() or (self._tbl(None),):
            if table.selectedItems():
                return table
        for table in self._split_tables() or (self._tbl(None),):
            if table.hasFocus() and table.currentRow() >= 0:
                return table
        for table in self._split_tables() or (self._tbl(None),):
            if table.currentRow() >= 0:
                return table
        return self._split_tables()[0] if self._split_tables() else self._tbl(None)

    def _sort_state(self, table):
        key = id(table)
        if key not in self._sort_states:
            self._sort_states[key] = [-1, False]
        return self._sort_states[key]

    def _clear_sort_indicator(self, table=None):
        t = self._tbl(table)
        st = self._sort_state(t)
        st[0], st[1] = -1, False
        t.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)

    def _on_header_clicked(self, col, table=None):
        t = self._tbl(table)
        if t.rowCount() == 0:
            return
        st = self._sort_state(t)
        if col == st[0]:
            st[1] = not st[1]
        else:
            st[0], st[1] = col, False
        keyfn = self._sort_entry_key(t, col)
        if keyfn is None:
            self._clear_sort_indicator(t)
            return
        order = Qt.SortOrder.DescendingOrder if st[1] else Qt.SortOrder.AscendingOrder
        t.horizontalHeader().setSortIndicator(col, order)
        keys = [self._row_key(t, r) for r in range(t.rowCount())]
        self._reorder_to_keys(t, [k for _, k in sorted(enumerate(keys), key=lambda e: keyfn(e[1], e[0]), reverse=st[1])])

    def move_item_to_edge(self, table, to_bottom=False):
        rows = self._selected_rows(table)
        if not rows:
            return
        keys = [self._row_key(table, row) for row in range(table.rowCount())]
        selected = set(rows)
        moving = [keys[row] for row in rows]
        rest = [key for row, key in enumerate(keys) if row not in selected]
        wanted = rest + moving if to_bottom else moving + rest
        self._reorder_to_keys(table, wanted)
        selected_keys = set(moving)
        table.clearSelection()
        selection_model = table.selectionModel()
        selected_rows = [
            row for row in range(table.rowCount())
            if self._row_key(table, row) in selected_keys
        ]
        if selected_rows:
            table.setCurrentCell(selected_rows[0], 0)
        for row in selected_rows:
            selection_model.select(
                table.model().index(row, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        self._clear_sort_indicator(table)

    def filter_models(self, text, table=None):
        t = self._tbl(table)
        query = text.strip().casefold()
        for r in range(t.rowCount()):
            t.setRowHidden(r, bool(query and query not in self._row_search_text(t, r).casefold()))
        self._after_filter()

class ToolTipDelegate(QStyledItemDelegate):
    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            if not index.isValid():
                return False
            tooltip = index.data(Qt.ItemDataRole.ToolTipRole)
            if not tooltip:
                return False
            
            # Show tooltip to the right of the current mouse pointer position
            # We add a small offset (15px) to ensure it doesn't overlap the cursor
            pos = event.globalPos()
            pos.setX(pos.x() + 15)
            
            QToolTip.showText(pos, tooltip, view)
            return True
        return super().helpEvent(event, view, option, index)


class FallbackOrderDialog(FallbackPriorityDialog):
    def __init__(self, parent, provider, active_model, current_list, suggestions):
        super().__init__(parent)
        self.main_dialog = parent
        self.provider = provider
        self.active_model = active_model
        
        self.setWindowTitle(f"Fallback Priority: {provider.capitalize()}")
        self.setMinimumWidth(900)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Configure the list of models to try if the primary model fails.<br/>"
            "The first model in <b>Enabled</b> is the Active Model. Uncheck a row to move it to "
            "<b>Disabled</b> (or check one there to enable it) — each list keeps its own order.<br/>"
            "Click a column header to sort that list, or use the buttons below to reorder."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search models...")
        self.search_edit.textChanged.connect(self.filter_models)
        layout.addWidget(self.search_edit)

        # Columns: [Model Name] [Thinking Level] [Timeout]
        headers = ["Model Name", "Thinking Level", "Timeout (s)"]
        self.enabled_table = self._make_fallback_table(headers, {0: 320, 1: 120, 2: 100})
        self.disabled_table = self._make_fallback_table(headers, {0: 320, 1: 120, 2: 100})
        self.table = self.enabled_table
        for table in (self.enabled_table, self.disabled_table):
            table.horizontalHeader().sectionClicked.connect(lambda col, t=table: self._on_header_clicked(col, t))
            table.itemChanged.connect(self._on_item_changed)
            table.verticalScrollBar().valueChanged.connect(self._ensure_visible_widgets)
            table.viewport().installEventFilter(self)
        self._moving_rows = False

        disabled_models = getattr(parent, "disabled_fallback_models_data", {}).get(provider, [])
        fallback_statuses = PERSISTENT_TEST_STATUSES.get(f"{provider}_fallback_statuses", {})
        thinking_levels = getattr(parent, "thinking_levels_data", {}).get(provider, {})
        model_timeouts = getattr(parent, "model_timeouts_data", {}).get(provider, {})

        # Authoritative per-model values. The combo/spin cell widgets are
        # created lazily for visible rows only (providers like OpenRouter ship
        # 400+ models), so these dicts — not the widgets — are the source of
        # truth and are harvested back before every structural/read operation.
        self._thinking_levels = dict(thinking_levels or {})
        self._model_timeouts = dict(model_timeouts or {})

        # Build the initial lists: active model first in Enabled, then the
        # remaining checked fallbacks; unchecked models go to Disabled.
        enabled_list = []
        disabled_list = []
        if active_model:
            enabled_list.append(active_model)
        for m in current_list:
            if m != active_model:
                (disabled_list if m in disabled_models else enabled_list).append(m)

        # Batch-populate large lists (e.g. 400+ OpenRouter models): plain items
        # are cheap; per-row widgets are materialized on demand.
        for table in (self.enabled_table, self.disabled_table):
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
        try:
            self.enabled_table.setRowCount(len(enabled_list))
            for i, m in enumerate(enabled_list):
                self._add_model_row(self.enabled_table, m, True, row=i)
            self.disabled_table.setRowCount(len(disabled_list))
            for i, m in enumerate(disabled_list):
                self._add_model_row(self.disabled_table, m, False, row=i)
        finally:
            for table in (self.enabled_table, self.disabled_table):
                table.blockSignals(False)
                table.setUpdatesEnabled(True)

        # Materialize the first screenful immediately so the dialog never opens
        # with empty cells; further rows load as the user scrolls.
        self._ensure_visible_widgets()

        self.enabled_label = QLabel("Enabled priority (first row is Active):")
        self.enabled_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        self.disabled_label = QLabel("Disabled / available:")
        self.disabled_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        self.enabled_up_btn = QPushButton("▲ Up")
        self.enabled_up_btn.clicked.connect(lambda: self.move_item_in(self.enabled_table, -1))
        self.enabled_down_btn = QPushButton("▼ Down")
        self.enabled_down_btn.clicked.connect(lambda: self.move_item_in(self.enabled_table, 1))
        self.enabled_top_btn = QPushButton("⇈ Top")
        self.enabled_top_btn.clicked.connect(lambda: self.move_item_to_edge(self.enabled_table))
        self.enabled_bottom_btn = QPushButton("⇊ Bottom")
        self.enabled_bottom_btn.clicked.connect(lambda: self.move_item_to_edge(self.enabled_table, True))
        self.disabled_up_btn = QPushButton("▲ Up")
        self.disabled_up_btn.clicked.connect(lambda: self.move_item_in(self.disabled_table, -1))
        self.disabled_down_btn = QPushButton("▼ Down")
        self.disabled_down_btn.clicked.connect(lambda: self.move_item_in(self.disabled_table, 1))
        self.disabled_top_btn = QPushButton("⇈ Top")
        self.disabled_top_btn.clicked.connect(lambda: self.move_item_to_edge(self.disabled_table))
        self.disabled_bottom_btn = QPushButton("⇊ Bottom")
        self.disabled_bottom_btn.clicked.connect(lambda: self.move_item_to_edge(self.disabled_table, True))

        lists_splitter = QSplitter(Qt.Orientation.Horizontal)
        lists_splitter.setChildrenCollapsible(False)
        enabled_wrap = QWidget()
        enabled_panel = QVBoxLayout(enabled_wrap)
        enabled_panel.setContentsMargins(0, 0, 0, 0)
        enabled_panel.addWidget(self.enabled_label)
        enabled_panel.addWidget(self.enabled_table, 1)
        enabled_move = QHBoxLayout()
        enabled_move.addWidget(self.enabled_up_btn)
        enabled_move.addWidget(self.enabled_down_btn)
        enabled_move.addWidget(self.enabled_top_btn)
        enabled_move.addWidget(self.enabled_bottom_btn)
        enabled_move.addStretch()
        enabled_panel.addLayout(enabled_move)
        lists_splitter.addWidget(enabled_wrap)
        disabled_wrap = QWidget()
        disabled_panel = QVBoxLayout(disabled_wrap)
        disabled_panel.setContentsMargins(0, 0, 0, 0)
        disabled_panel.addWidget(self.disabled_label)
        disabled_panel.addWidget(self.disabled_table, 1)
        disabled_move = QHBoxLayout()
        disabled_move.addWidget(self.disabled_up_btn)
        disabled_move.addWidget(self.disabled_down_btn)
        disabled_move.addWidget(self.disabled_top_btn)
        disabled_move.addWidget(self.disabled_bottom_btn)
        disabled_move.addStretch()
        disabled_panel.addLayout(disabled_move)
        lists_splitter.addWidget(disabled_wrap)
        lists_splitter.setStretchFactor(0, 1)
        lists_splitter.setStretchFactor(1, 1)
        layout.addWidget(lists_splitter, 1)
        self._update_counts()

        # Action buttons (stacked in 2 rows to prevent overflow)
        btn_layout = QVBoxLayout()

        row1_layout = QHBoxLayout()
        self.set_active_btn = QPushButton("Set Active")
        self.set_active_btn.setToolTip("Set the selected model as the primary active model (moves it to the top).")
        self.set_active_btn.clicked.connect(self.set_selected_as_active)
        self.add_btn = QPushButton("Add Model...")
        self.add_btn.setToolTip("Add a custom model name to this provider's fallback list.")
        self.add_btn.clicked.connect(self._add_custom_model)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Remove models from the list. Choose which type to remove from the dropdown.")
        self.remove_btn.setMenu(_build_remove_menu(self.remove_models))

        row1_layout.addWidget(self.set_active_btn)
        row1_layout.addWidget(self.add_btn)
        row1_layout.addWidget(self.remove_btn)
        
        row2_layout = QHBoxLayout()
        self.list_test_btn = QPushButton("Test")
        self.list_test_btn.setToolTip("Test models from the list. Choose which mode from the dropdown.")
        self.list_test_btn.setMenu(_build_test_menu(self.on_test_from_list))
        self.match_global_btn = QPushButton("Match Global Enabled")
        self.match_global_btn.setToolTip("Enable the models currently enabled in Advanced Global Fallback Priority. This keeps the current per-provider order and does not change the global order.")
        self.match_global_btn.clicked.connect(self.match_global_enabled)

        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setToolTip("Fetch available models from this provider's API.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_from_list)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset the list back to code defaults.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        row2_layout.addWidget(self.list_test_btn)
        row2_layout.addWidget(self.match_global_btn)
        row2_layout.addWidget(self.list_fetch_btn)
        row2_layout.addWidget(self.restore_btn)
        
        btn_layout.addLayout(row1_layout)
        btn_layout.addLayout(row2_layout)
        layout.addLayout(btn_layout)
        
        # OK / Cancel
        dlg_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dlg_btns.accepted.connect(self.accept)
        dlg_btns.rejected.connect(self.reject)
        layout.addWidget(dlg_btns)
        
        self.update_item_labels()

    def _model_flags(self, model_name):
        """Return (is_newly_added, is_deprecated, is_missing_after_fetch) for a model."""
        is_new = model_name in NEWLY_ADDED_MODELS.get(self.provider, ())
        is_dep = is_model_deprecated(self.provider, model_name)
        is_missing = model_name in MISSING_FROM_FETCH.get(self.provider, ())
        return is_new, is_dep, is_missing

    def _cancel_own_test(self):
        """Stop this dialog's model-test loop if it is still running in the
        background. Called when the dialog is closed so a test never keeps
        running (and logging) after its window disappears."""
        test_key = f"{self.provider}_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True

    def closeEvent(self, event):
        self._cancel_own_test()
        super().closeEvent(event)

    def _apply_model_highlight(self, item, model_name):
        """Colour a fallback table row based on new/missing/deprecated status."""
        # Rows are swapped in place, so clear the previous model's brushes
        # before applying the current model's status.
        item.setBackground(QBrush())
        item.setForeground(QBrush())
        is_new, is_dep, is_missing = self._model_flags(model_name)
        if is_dep:
            item.setBackground(QBrush(QColor(COL_DEP_BG)))
            item.setForeground(QBrush(QColor(COL_DEP_FG)))
        elif is_missing:
            item.setBackground(QBrush(QColor(COL_MISSING_BG)))
            item.setForeground(QBrush(QColor(COL_MISSING_FG)))
        elif is_new:
            item.setBackground(QBrush(QColor(COL_NEW_BG)))
            item.setForeground(QBrush(QColor(COL_NEW_FG)))

    def _add_model_row(self, table, model_name, checked, row=None):
        if row is None:
            row = table.rowCount()
            table.insertRow(row)
        # Seed authoritative values; cell widgets are created lazily.
        self._thinking_levels.setdefault(model_name, "off")
        self._model_timeouts.setdefault(model_name, 0)

        # Column 0: Model name with checkbox
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, model_name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        is_new, is_dep, is_missing = self._model_flags(model_name)
        new_mark = "🆕 " if is_new else ""
        dep_mark = " | ⚠️ Deprecated" if is_dep else ""
        missing_mark = " | ⚠️ No Longer Returned" if (is_missing and not is_dep) else ""
        item.setText(f"{new_mark}{model_name}{dep_mark}{missing_mark}")
        self._apply_model_highlight(item, model_name)
        if is_dep:
            item.setToolTip("⚠️ This model appears to be deprecated/retired. Consider removing it from the fallback list.")
        elif is_missing:
            item.setToolTip("⚠️ The provider no longer returned this model in the latest fetch. It may be retired — consider removing it from the fallback list.")
        table.setItem(row, 0, item)

    # ---- Lazy cell-widget materialization ----------------------------------
    # Creating a QComboBox + QSpinBox for every row made dialogs with hundreds
    # of models (OpenRouter) take seconds to open. Widgets are now created only
    # for rows near the visible viewport; the name-keyed dicts hold the
    # authoritative values and are harvested back before any structural or
    # read operation.

    def _materialize_row_widgets(self, table, row):
        if table.cellWidget(row, 1) is not None:
            return
        item = table.item(row, 0)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)

        combo = QComboBox()
        combo.addItems(["off", "low", "medium", "high"])
        combo.setCurrentText(self._thinking_levels.get(name, "off"))
        table.setCellWidget(row, 1, combo)

        spin = QSpinBox()
        spin.setRange(0, 300)
        spin.setSuffix(" s")
        spin.setToolTip("Request timeout in seconds. 0 = use provider/global timeout.")
        spin.setValue(self._model_timeouts.get(name, 0))
        table.setCellWidget(row, 2, spin)

    def _visible_row_range(self, table):
        count = table.rowCount()
        if count == 0:
            return 0, -1
        first = table.rowAt(0)
        if first < 0:
            first = 0
        viewport_h = max(1, table.viewport().height())
        last = table.rowAt(viewport_h - 2)
        if last < first:
            row_h = max(1, table.rowHeight(first))
            last = min(count - 1, first + (viewport_h // row_h))
        return first, min(count - 1, last)

    def _ensure_table_widgets(self, table):
        first, last = self._visible_row_range(table)
        if last < first:
            return
        margin = 15  # pre-build a few screens' worth while scrolling
        lo = max(0, first - margin)
        hi = min(table.rowCount() - 1, last + margin)
        updates = table.updatesEnabled()
        if updates:
            table.setUpdatesEnabled(False)
        try:
            for i in range(lo, hi + 1):
                if not table.isRowHidden(i):
                    self._materialize_row_widgets(table, i)
        finally:
            if updates:
                table.setUpdatesEnabled(True)

    def _ensure_visible_widgets(self):
        for table in (self.enabled_table, self.disabled_table):
            self._ensure_table_widgets(table)

    def _harvest_widgets(self):
        """Copy current combo/spin values back into the authoritative dicts."""
        for table in (self.enabled_table, self.disabled_table):
            for i in range(table.rowCount()):
                item = table.item(i, 0)
                if not item:
                    continue
                name = item.data(Qt.ItemDataRole.UserRole)
                if not name:
                    continue
                combo = table.cellWidget(i, 1)
                if combo is not None:
                    self._thinking_levels[name] = combo.currentText()
                spin = table.cellWidget(i, 2)
                if spin is not None:
                    self._model_timeouts[name] = spin.value()

    def _refresh_row_widgets(self, table, row):
        """Re-sync an existing row's widgets with its (possibly swapped) model."""
        item = table.item(row, 0)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        combo = table.cellWidget(row, 1)
        if combo is not None:
            combo.setCurrentText(self._thinking_levels.get(name, "off"))
        spin = table.cellWidget(row, 2)
        if spin is not None:
            spin.setValue(self._model_timeouts.get(name, 0))

    def _refresh_visible_widgets(self):
        for table in (self.enabled_table, self.disabled_table):
            for r in range(table.rowCount()):
                if table.cellWidget(r, 1) is not None:
                    self._refresh_row_widgets(table, r)

    def on_fetch_from_list(self):
        fetch_key = f"{self.provider}_fallback"
        if fetch_key in FETCH_CANCELLATIONS:
            # User clicked again to Stop/Cancel
            FETCH_CANCELLATIONS[fetch_key] = True
            self.list_fetch_btn.setText("Fetch All")
            return

        FETCH_CANCELLATIONS[fetch_key] = False
        self.list_fetch_btn.setText("Stop Fetch All")
        self.list_test_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        
        api_key = self.main_dialog.api_key_edits[self.provider].text().strip() if self.provider in self.main_dialog.api_key_edits else ""
        local_providers = self.main_dialog.local_providers_data or {}
        if not api_key and self.provider not in ["local"] and self.provider not in self.main_dialog.custom_providers_data and self.provider not in local_providers:
            info(f"Please enter an API key for {self.provider.capitalize()} first.")
            self.list_fetch_btn.setText("Fetch All")
            self.list_test_btn.setEnabled(True)
            self.restore_btn.setEnabled(True)
            del FETCH_CANCELLATIONS[fetch_key]
            return
            
        temp_config = self.main_dialog.config.copy()
        # Only override the key when the edit field actually has a value; otherwise
        # keep the saved (correct) key from the config copy.
        if api_key:
            if "api_keys" not in temp_config: temp_config["api_keys"] = {}
            temp_config["api_keys"][self.provider] = api_key
        # Include in-memory (unsaved) local & custom providers so a freshly added
        # provider's fallback models can be fetched before the user clicks Save.
        if hasattr(self.main_dialog, "local_providers_data"):
            temp_config["local_providers"] = self.main_dialog.local_providers_data
        if hasattr(self.main_dialog, "custom_providers_data"):
            temp_config["custom_providers"] = self.main_dialog.custom_providers_data
            
        import threading
        from ..ai_client import AIClient
        
        tooltip(f"Fetching models for {self.provider.capitalize()}...")
        
        def _runner():
            try:
                if FETCH_CANCELLATIONS.get(fetch_key):
                    return
                client = AIClient(temp_config)
                models = client.fetch_models(self.provider)
                if FETCH_CANCELLATIONS.get(fetch_key):
                    return
                    
                def _update_ui():
                    if models:
                        models_clean = sorted(list(set(models)))
                        existing = [t.item(j, 0).data(Qt.ItemDataRole.UserRole)
                                    for t in (self.enabled_table, self.disabled_table)
                                    for j in range(t.rowCount()) if t.item(j, 0)]
                        existing_set = set(existing)

                        fetched_set = set(models_clean)
                        missing_set = {m for m in existing_set if m and m not in fetched_set}
                        if missing_set:
                            MISSING_FROM_FETCH[self.provider] = missing_set

                        added_count = 0
                        newly = NEWLY_ADDED_MODELS.setdefault(self.provider, set())
                        for m in models_clean:
                            if m and m not in existing_set:
                                newly.add(m)
                                self._add_model_row(self.disabled_table, m, False)
                                added_count += 1

                        self.update_item_labels()
                        self._update_counts()
                        self._ensure_visible_widgets()
                        tooltip(f"Fetched {len(models_clean)} models ({added_count} new, {len(missing_set)} missing).")
                    else:
                        info(f"Could not fetch models for {self.provider.capitalize()}. Check connection.")
                mw.taskman.run_on_main(_update_ui)
            except Exception as e:
                err_msg = str(e)
                def _fail_err():
                    info(f"Error fetching models: {err_msg}")
                mw.taskman.run_on_main(_fail_err)
            finally:
                if fetch_key in FETCH_CANCELLATIONS:
                    del FETCH_CANCELLATIONS[fetch_key]
                def _enable():
                    self.list_fetch_btn.setText("Fetch All")
                    self.list_test_btn.setEnabled(True)
                    self.restore_btn.setEnabled(True)
                mw.taskman.run_on_main(_enable)
                
        threading.Thread(target=_runner, daemon=True).start()

    def _row_key(self, table, row):
        item = table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _row_search_text(self, table, row):
        return self._row_key(table, row) or ""

    def _after_filter(self):
        self._ensure_visible_widgets()

    def _sort_entry_key(self, table, col):
        ranks = {"off": 0, "low": 1, "medium": 2, "high": 3}
        if col == 1:
            return lambda name, row: ranks.get(self._thinking_levels.get(name, "off"), 0)
        if col == 2:
            return lambda name, row: self._model_timeouts.get(name, 0)
        return lambda name, row: (normalized_model_key(name), (name or "").casefold())

    def _reorder_to_keys(self, table, wanted):
        self._harvest_widgets()
        by_name = {}
        for i in range(table.rowCount()):
            d = self._row_data(table, i)
            item = table.item(i, 0)
            d["hidden"] = table.isRowHidden(i)
            d["selected"] = bool(item and item.isSelected())
            by_name.setdefault(d["name"], []).append(d)
        ordered = []
        for name in wanted:
            if by_name.get(name):
                ordered.append(by_name[name].pop(0))
        self._rebuild_rows(ordered, table)
        for i, d in enumerate(ordered):
            table.setRowHidden(i, d["hidden"])
            if d["selected"]:
                it = table.item(i, 0)
                if it:
                    it.setSelected(True)

    def _rebuild_rows(self, model_data, table=None):
        """Replace the whole table contents from a list of _row_data dicts."""
        table = table if table is not None else self.table
        self._harvest_widgets()
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            table.setRowCount(0)
            table.setRowCount(len(model_data))
            for i, d in enumerate(model_data):
                self._add_model_row(table, d["name"], d["checked"], row=i)
        finally:
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
        self.update_item_labels()
        self._ensure_visible_widgets()

    def on_test_from_list(self, mode="all"):
        test_key = f"{self.provider}_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True
            self.list_test_btn.setText("Test")
            tooltip("Testing cancelled.")
            return

        cancel_other_model_tests(test_key)
        TEST_CANCELLATIONS[test_key] = False
        self.list_test_btn.setText("Stop Test")
        self.restore_btn.setEnabled(False)
        self.enabled_up_btn.setEnabled(False)
        self.enabled_down_btn.setEnabled(False)
        self.disabled_up_btn.setEnabled(False)
        self.disabled_down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)

        # Collect models based on mode
        if mode == "checked":
            tables = [self.enabled_table]
        else:
            tables = [self.enabled_table, self.disabled_table]
        models = []
        model_tables = []
        seen_models = set()
        for table in tables:
            for i in range(table.rowCount()):
                item = table.item(i, 0)
                if not item:
                    continue
                model_name = item.data(Qt.ItemDataRole.UserRole)
                if model_name in seen_models:
                    continue
                if mode == "all":
                    models.append(model_name)
                    model_tables.append(table)
                    seen_models.add(model_name)
                elif mode == "checked" and item.checkState() == Qt.CheckState.Checked:
                    models.append(model_name)
                    model_tables.append(table)
                    seen_models.add(model_name)
                elif mode == "row" and table.item(i, 0) and table.item(i, 0).isSelected():
                    models.append(model_name)
                    model_tables.append(table)
                    seen_models.add(model_name)

        if not models:
            tooltip("No models match the selected test mode.")
            self._test_done(test_key)
            return
        
        import threading
        from ..ai_client import AIClient
        
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            for idx, (model, table) in enumerate(zip(models, model_tables)):
                if TEST_CANCELLATIONS.get(test_key):
                    break
                # Update item state to Testing
                def _update_testing(t=table, name=model):
                    row = self._find_row_in(t, name)
                    item = t.item(row, 0) if row >= 0 else None
                    if item:
                        item.setText(f"{name} (⏳ Testing...)")
                mw.taskman.run_on_main(_update_testing)
                
                status = "✅ Working"
                try:
                    # Prepare temporary config for this model
                    temp_config = self.main_dialog.config.copy()
                    api_key = self.main_dialog.api_key_edits[self.provider].text().strip() if self.provider in self.main_dialog.api_key_edits else ""
                    # Only override the key when the edit field actually has a value;
                    # otherwise keep the saved (correct) key from the config copy.
                    if api_key:
                        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                        temp_config["api_keys"][self.provider] = api_key
                    # Include in-memory (unsaved) custom/local providers so a freshly
                    # added provider tests with the current URL/key before Save.
                    if hasattr(self.main_dialog, "local_providers_data"):
                        temp_config["local_providers"] = self.main_dialog.local_providers_data
                    if hasattr(self.main_dialog, "custom_providers_data"):
                        temp_config["custom_providers"] = self.main_dialog.custom_providers_data
                    if "models" not in temp_config: temp_config["models"] = {}
                    temp_config["models"][self.provider] = model
                    
                    if self.provider == "local":
                        temp_config["local_endpoint"] = self.main_dialog._local_endpoint_for(model)
                    client = AIClient(temp_config)
                    test_front = self.main_dialog.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION
                    test_back = self.main_dialog.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER
                    if TEST_CANCELLATIONS.get(test_key):
                        break
                    res = client.generate_options(test_front, test_back, override_provider=self.provider, only_this_provider=True, override_model=model)
                    if TEST_CANCELLATIONS.get(test_key):
                        break
                    error_msg = None
                    if not (res and (res.get("hints") or res.get("options"))):
                        status = "❌ Empty"
                        error_msg = "Empty response"
                        tooltip_text = (
                            f"<div style='width: 350px;'>"
                            f"<b>Question:</b> {test_front}<br/>"
                            f"<b>Answer:</b> {test_back}<br/><br/>"
                            f"<b>Status:</b> Provider returned empty response or no usable hints/options.<br/>"
                            f"<i>Tip: Check model name, API key, quota, or response format.</i>"
                            f"</div>"
                        )
                    else:
                        formatted_res = json.dumps(res, indent=2, ensure_ascii=False)
                        tooltip_text = (
                            f"<div style='width: 450px;'>"
                            f"<b>Question:</b> {test_front}<br/>"
                            f"<b>Answer:</b> {test_back}<br/><br/>"
                            f"<b>Model Response:</b><br/>"
                            f"<pre style='font-family: monospace; font-size: 11px; white-space: pre-wrap; word-wrap: break-word;'>{formatted_res}</pre>"
                            f"</div>"
                        )
                except Exception as e:
                    error_msg = str(e)
                    if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                        status = "⏳ Timeout"
                    else:
                        status = "❌ Error"
                    tooltip_text = (
                        f"<div style='width: 350px;'>"
                        f"<b>Question:</b> {test_front}<br/>"
                        f"<b>Answer:</b> {test_back}<br/><br/>"
                        f"<b>Error:</b> {error_msg}<br/>"
                        f"{'<i>Tip: Endpoint took longer to respond than the request timeout limit.</i>' if 'Timeout' in status else ''}"
                        f"</div>"
                    )
                
                if TEST_CANCELLATIONS.get(test_key):
                    break

                # Update item state to result
                def _update_result(t=table, name=model, st=status, tt=tooltip_text):
                    fallback_statuses = PERSISTENT_TEST_STATUSES.setdefault(f"{self.provider}_fallback_statuses", {})
                    fallback_statuses[name] = st
                    fallback_tooltips = PERSISTENT_TEST_STATUSES.setdefault(f"{self.provider}_fallback_tooltips", {})
                    fallback_tooltips[name] = tt
                    row = self._find_row_in(t, name)
                    item = t.item(row, 0) if row >= 0 else None
                    if item:
                        item.setText(f"{name} ({st})")
                        item.setToolTip(tt)
                mw.taskman.run_on_main(_update_result)
                
            self._test_done(test_key)
            
        threading.Thread(target=_runner, daemon=True).start()

    def _test_done(self, test_key):
        def _done():
            self.list_test_btn.setText("Test")
            self.restore_btn.setEnabled(True)
            self.enabled_up_btn.setEnabled(True)
            self.enabled_down_btn.setEnabled(True)
            self.disabled_up_btn.setEnabled(True)
            self.disabled_down_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
            if test_key in TEST_CANCELLATIONS:
                del TEST_CANCELLATIONS[test_key]
            self.update_item_labels()
        mw.taskman.run_on_main(_done)

    def _find_row_in(self, table, name):
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == name:
                return r
        return -1

    def _update_counts(self):
        self.enabled_label.setText(f"Enabled priority (first row is Active, {self.enabled_table.rowCount()}):")
        self.disabled_label.setText(f"Disabled / available ({self.disabled_table.rowCount()}):")

    def match_global_enabled(self):
        """Make per-provider membership match the global enabled set."""
        wanted = {
            model for provider, model in (
                getattr(self.main_dialog, "global_model_priority_data", []) or []
            ) if provider == self.provider
        }
        self._harvest_widgets()
        rows = []
        for table in self._split_tables():
            for row in range(table.rowCount()):
                data = self._row_data(table, row)
                data["checked"] = data["name"] in wanted
                rows.append(data)
        present = {data["name"] for data in rows}
        for model in wanted - present:
            rows.append({"name": model, "checked": True,
                         "think": "off", "timeout": 0})
        self._moving_rows = True
        try:
            enabled = [data for data in rows if data["checked"]]
            disabled = [data for data in rows if not data["checked"]]
            self._rebuild_rows(enabled, self.enabled_table)
            self._rebuild_rows(disabled, self.disabled_table)
        finally:
            self._moving_rows = False
        self._update_counts()
        self.update_item_labels()

    def _move_row_to_other_table(self, table, row, checked):
        item = table.item(row, 0)
        name = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if not name:
            return
        self._moving_rows = True
        try:
            self._harvest_widgets()
            table.removeRow(row)
            target = self.enabled_table if checked else self.disabled_table
            self._add_model_row(target, name, checked)
            target.setCurrentCell(target.rowCount() - 1, 0)
            self._clear_sort_indicator(table)
            self._clear_sort_indicator(target)
            self.update_item_labels()
            self._update_counts()
        finally:
            self._moving_rows = False

    def _on_item_changed(self, item):
        if self._moving_rows:
            return
        table = item.tableWidget()
        if table not in (self.enabled_table, self.disabled_table) or item.column() != 0:
            return
        row = table.row(item)
        if row < 0 or row >= table.rowCount():
            return
        checked = item.checkState() == Qt.CheckState.Checked
        if (table is self.enabled_table) == checked:
            return
        if table is self.enabled_table and self.enabled_table.rowCount() == 1:
            table.blockSignals(True)
            try:
                item.setCheckState(Qt.CheckState.Checked)
            finally:
                table.blockSignals(False)
            tooltip("Cannot disable the last enabled model.")
            return
        self._move_row_to_other_table(table, row, checked)

    def _swap_rows_in(self, table, a, b):
        """Swap two rows in the given table; widgets follow their new model."""
        self._harvest_widgets()
        for column in range(table.columnCount()):
            if table.cellWidget(a, column) is not None or table.cellWidget(b, column) is not None:
                continue
            item_a = table.takeItem(a, column)
            item_b = table.takeItem(b, column)
            table.setItem(a, column, item_b)
            table.setItem(b, column, item_a)
        self._refresh_row_widgets(table, a)
        self._refresh_row_widgets(table, b)

    def _swap_rows(self, a, b):
        self._swap_rows_in(self.enabled_table, a, b)

    def _row_data(self, table, row):
        item = table.item(row, 0)
        name = item.data(Qt.ItemDataRole.UserRole) if item else ""
        return {
            "name": name,
            "checked": item.checkState() == Qt.CheckState.Checked if item else True,
            "think": self._thinking_levels.get(name, "off"),
            "timeout": self._model_timeouts.get(name, 0),
        }

    def update_item_labels(self, *args):
        for table in (self.enabled_table, self.disabled_table):
            table.blockSignals(True)
            table.setUpdatesEnabled(False)
        try:
            fallback_statuses = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_statuses", {})
            fallback_tooltips = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_tooltips", {})
            for table in (self.enabled_table, self.disabled_table):
                active_table = table is self.enabled_table
                for i in range(table.rowCount()):
                    item = table.item(i, 0)
                    if not item: continue
                    m = item.data(Qt.ItemDataRole.UserRole)
                    status = fallback_statuses.get(m)
                    bl = is_model_blacklisted(self.provider, m, getattr(self.main_dialog, "config", None))
                    bl_text = ""
                    remaining = None
                    if bl:
                        bl_text = " | 🚫 Blacklisted"
                        remaining = _get_blacklist_remaining(self.provider, m, getattr(self.main_dialog, "config", None))
                        if remaining:
                            bl_text += f" ({remaining})"
                    status_suffix = f" ({status}{bl_text})" if status else (f" ({bl_text.strip()})" if bl_text else "")

                    tt = fallback_tooltips.get(m) if fallback_tooltips else None
                    is_new, is_dep, is_missing = self._model_flags(m)
                    dep_note = "⚠️ This model appears to be deprecated/retired. Consider removing it from the fallback list." if is_dep else ""
                    missing_note = "⚠️ The provider no longer returned this model in the latest fetch. It may be retired — consider removing it from the fallback list." if (is_missing and not is_dep) else ""
                    if tt:
                        item.setToolTip(tt)
                    elif dep_note:
                        item.setToolTip(dep_note)
                    elif missing_note:
                        item.setToolTip(missing_note)
                    elif bl:
                        bl_tooltip = "This model is currently on cooldown due to recent failures."
                        if remaining:
                            bl_tooltip += f"<br/><i>{remaining} left</i>"
                        item.setToolTip(bl_tooltip)
                    else:
                        item.setToolTip("")

                    new_mark = "🆕 " if is_new else ""
                    dep_mark = " | ⚠️ Deprecated" if is_dep else ""
                    missing_mark = " | ⚠️ No Longer Returned" if (is_missing and not is_dep) else ""
                    if active_table and i == 0:
                        item.setCheckState(Qt.CheckState.Checked)
                        item.setText(f"⭐ {new_mark}{m} (Active){status_suffix}{dep_mark}{missing_mark}")
                    else:
                        if not active_table:
                            item.setCheckState(Qt.CheckState.Unchecked)
                        item.setText(f"{new_mark}{m}{status_suffix}{dep_mark}{missing_mark}")
                    self._apply_model_highlight(item, m)
        finally:
            for table in (self.enabled_table, self.disabled_table):
                table.setUpdatesEnabled(True)
                table.blockSignals(False)

    def set_selected_as_active(self):
        table = self._focused_table()
        row = table.currentRow()
        if table is self.disabled_table:
            if row < 0:
                tooltip("Select a model first.")
                return
            name = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self._move_row_to_other_table(table, row, True)
            row = self._find_row_in(self.enabled_table, name)
            table = self.enabled_table
        if row > 0:
            self._swap_rows_in(table, row, 0)
            table.setCurrentCell(0, 0)
            self.update_item_labels()
            self._clear_sort_indicator(table)

    def _add_custom_model(self):
        existing = {
            table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            for table in (self.enabled_table, self.disabled_table)
            for i in range(table.rowCount())
            if table.item(i, 0)
        }
        name, ok = QInputDialog.getText(
            self, "Add Custom Model",
            f"Model name for {self.provider.capitalize()}:",
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            tooltip("Model name cannot be empty.")
            return
        if name in existing:
            tooltip(f"Model '{name}' is already in the list.")
            return
        self.enabled_table.blockSignals(True)
        try:
            self._add_model_row(self.enabled_table, name, checked=True)
        finally:
            self.enabled_table.blockSignals(False)
        self.update_item_labels()
        self._update_counts()
        tooltip(f"Added '{name}' to the list.")

    def _move_row_to_other_table(self, table, row, checked):
        item = table.item(row, 0)
        name = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if not name:
            return
        self._moving_rows = True
        try:
            self._harvest_widgets()
            table.removeRow(row)
            target = self.enabled_table if checked else self.disabled_table
            self._add_model_row(target, name, checked)
            target.setCurrentCell(target.rowCount() - 1, 0)
            self._clear_sort_indicator(table)
            self._clear_sort_indicator(target)
            self.update_item_labels()
            self._update_counts()
        finally:
            self._moving_rows = False

    def move_item(self, delta):
        self.move_item_in(self._focused_table(), delta)

    def move_item_in(self, table, delta):
        rows = self._selected_rows(table)
        if not rows:
            return
        selected = set(rows)
        selected_keys = {
            table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in rows
            if table.item(row, 0) is not None
        }

        # Swap with the adjacent row instead of removing/recreating selected
        # rows. This handles non-contiguous selections and keeps every row's
        # lazily-created controls attached to its model.
        if delta < 0:
            candidates = rows
        else:
            candidates = reversed(rows)
        for row in candidates:
            neighbor = row + delta
            if neighbor < 0 or neighbor >= table.rowCount() or neighbor in selected:
                continue
            self._swap_rows_in(table, row, neighbor)
            selected.remove(row)
            selected.add(neighbor)

        table.clearSelection()
        selection_model = table.selectionModel()
        new_rows = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) in selected_keys:
                new_rows.append(row)
        if new_rows:
            table.setCurrentCell(new_rows[0], 0)
        for row in new_rows:
            index = table.model().index(row, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        self.update_item_labels()
        self._clear_sort_indicator(table)

    def filter_models(self, text):
        for table in (self.enabled_table, self.disabled_table):
            super().filter_models(text, table)

    def _rows_matching(self, table, pred):
        rows = []
        for i in range(table.rowCount()):
            item = table.item(i, 0)
            if item and pred(item.data(Qt.ItemDataRole.UserRole)):
                rows.append(i)
        return rows

    def remove_models(self, kind):
        """Remove rows based on the requested removal type.

        kind in {"selected", "deprecated", "missing", "flagged"}.
        """
        tables = (self.enabled_table, self.disabled_table)
        if kind == "selected":
            targets = [(t, i) for t in tables for i in self._selected_rows(t)]
            label = "selected"
        elif kind == "deprecated":
            targets = [(t, i) for t in tables for i in self._rows_matching(t, lambda m: is_model_deprecated(self.provider, m))]
            label = "deprecated"
        elif kind == "missing":
            missing = MISSING_FROM_FETCH.get(self.provider, set())
            targets = [(t, i) for t in tables for i in self._rows_matching(t, lambda m: m in missing)]
            label = "no-longer-returned"
        else:
            missing = MISSING_FROM_FETCH.get(self.provider, set())
            targets = [(t, i) for t in tables for i in self._rows_matching(
                t, lambda m: is_model_deprecated(self.provider, m) or m in missing)]
            label = "deprecated/no-longer-returned"

        if not targets:
            tooltip(f"No {label} models found in the list.")
            return
        total = self.enabled_table.rowCount() + self.disabled_table.rowCount()
        if len(targets) >= total:
            tooltip("Cannot remove all models; at least one must remain in the list.")
            return
        enabled_victims = {i for t, i in targets if t is self.enabled_table}
        if len(enabled_victims) >= self.enabled_table.rowCount():
            tooltip("Cannot remove every enabled model; at least one must stay enabled.")
            return
        self._harvest_widgets()
        by_table = {}
        for table, i in targets:
            by_table.setdefault(table, []).append(i)
        removed = 0
        for table, rows in by_table.items():
            for i in sorted(set(rows), reverse=True):
                name = table.item(i, 0).data(Qt.ItemDataRole.UserRole)
                self._thinking_levels.pop(name, None)
                self._model_timeouts.pop(name, None)
                table.removeRow(i)
                removed += 1
        self.update_item_labels()
        self._update_counts()
        tooltip(f"Removed {removed} model(s).")

    def restore_defaults(self):
        self._thinking_levels = {}
        self._model_timeouts = {}
        defaults = MODEL_FALLBACKS.get(self.provider, [])
        full_list = []
        if self.active_model:
            full_list.append(self.active_model)
        for m in defaults:
            if m != self.active_model:
                full_list.append(m)
        for table in (self.enabled_table, self.disabled_table):
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
        try:
            self.enabled_table.setRowCount(0)
            self.enabled_table.setRowCount(len(full_list))
            for i, m in enumerate(full_list):
                self._add_model_row(self.enabled_table, m, True, row=i)
            self.disabled_table.setRowCount(0)
        finally:
            for table in (self.enabled_table, self.disabled_table):
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
        self.update_item_labels()
        self._update_counts()
        self._ensure_visible_widgets()

    def get_active_model(self):
        if self.enabled_table.rowCount() > 0:
            item = self.enabled_table.item(0, 0)
            if item:
                return item.data(Qt.ItemDataRole.UserRole)
        return ""

    def get_ordered_list(self):
        result = []
        for i in range(1, self.enabled_table.rowCount()):
            item = self.enabled_table.item(i, 0)
            if item:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def get_disabled_list(self):
        return [self.disabled_table.item(i, 0).data(Qt.ItemDataRole.UserRole)
                for i in range(self.disabled_table.rowCount())
                if self.disabled_table.item(i, 0)]

    def _current_model_names(self):
        return {
            table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            for table in (self.enabled_table, self.disabled_table)
            for i in range(table.rowCount())
            if table.item(i, 0)
        }

    def get_thinking_levels(self):
        self._harvest_widgets()
        names = self._current_model_names()
        return {k: v for k, v in self._thinking_levels.items() if k in names}

    def get_model_timeouts(self):
        self._harvest_widgets()
        names = self._current_model_names()
        return {k: v for k, v in self._model_timeouts.items() if k in names}


class AddModelDialog(QDialog):
    def __init__(self, parent, providers, default_models, suggestions, fallbacks):
        super().__init__(parent)
        self.main_dialog = parent.main_dialog
        self.setWindowTitle("Add Model to Global Priority")
        layout = QFormLayout(self)
        
        self.provider_cb = QComboBox()
        self.provider_cb.addItems(providers)
        
        self.model_cb = QComboBox()
        self.model_cb.setEditable(True)
        
        self.providers_data = {}
        for p in providers:
            models_set = set()
            if default_models.get(p):
                models_set.add(default_models[p])
            for m in suggestions.get(p, []):
                models_set.add(m)
            for m in fallbacks.get(p, []):
                models_set.add(m)

            # For custom providers, read model + model_fallbacks from custom_providers_data
            # (same priority chain as _models_for_provider uses)
            if hasattr(self.main_dialog, "custom_providers_data") and p in self.main_dialog.custom_providers_data:
                cp_cfg = self.main_dialog.custom_providers_data.get(p) or {}
                if isinstance(cp_cfg, dict):
                    primary = str(cp_cfg.get("model", "") or "").strip()
                    if primary:
                        models_set.add(primary)
                    fb = cp_cfg.get("model_fallbacks", []) or []
                    if isinstance(fb, str):
                        fb = [fb]
                    for m in fb:
                        if m and str(m).strip():
                            models_set.add(str(m).strip())

            # Read from main dialog's comboboxes if they exist
            if p == "local" and hasattr(self.main_dialog, "local_model_edit"):
                cb = self.main_dialog.local_model_edit
                for i in range(cb.count()):
                    models_set.add(cb.itemText(i))
            elif hasattr(self.main_dialog, "model_edits") and p in self.main_dialog.model_edits:
                cb = self.main_dialog.model_edits[p]
                for i in range(cb.count()):
                    models_set.add(cb.itemText(i))

            self.providers_data[p] = sorted(list(models_set))
        
        def update_models():
            p = self.provider_cb.currentText()
            self.model_cb.clear()
            self.model_cb.addItems([m for m in self.providers_data.get(p, []) if m])
            
        self.provider_cb.currentTextChanged.connect(update_models)
        update_models()
        
        layout.addRow("Provider:", self.provider_cb)
        layout.addRow("Model Name:", self.model_cb)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow("", buttons)
        
    def get_selection(self):
        return self.provider_cb.currentText(), self.model_cb.currentText().strip()


class GlobalFallbackOrderDialog(FallbackPriorityDialog):
    def __init__(self, parent, current_global_list):
        super().__init__(parent)
        self.main_dialog = parent
        
        self.setWindowTitle("Advanced Global Fallback Priority")
        self.setMinimumWidth(1050)
        self.setMinimumHeight(600)

        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Configure a global fallback sequence across all models and providers.<br/>"
            "Only the <b>Enabled</b> list is tried, top to bottom. Uncheck a row to move it to "
            "<b>Disabled</b> (or check one there to enable it) — each list keeps its own order.<br/>"
            "Click a column header to sort that list by the column (click again to reverse)."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers/models...")
        self.search_edit.textChanged.connect(self.filter_models)
        layout.addWidget(self.search_edit)

        self._g_thinking = {p: dict(m) for p, m in (getattr(parent, "global_thinking_levels_data", {}) or {}).items() if isinstance(m, dict)}
        self._g_timeouts = {p: dict(m) for p, m in (getattr(parent, "global_model_timeouts_data", {}) or {}).items() if isinstance(m, dict)}
        self._per_thinking = getattr(parent, "thinking_levels_data", {}) or {}
        self._per_timeouts = getattr(parent, "model_timeouts_data", {}) or {}
        self._moving_rows = False

        headers = ["Provider", "Model", "Thinking Level", "Timeout (s)", "Status"]
        self.enabled_table = self._make_fallback_table(headers, {0: 150, 1: 280, 2: 110, 3: 90, 4: 160})
        self.disabled_table = self._make_fallback_table(headers, {0: 150, 1: 280, 2: 110, 3: 90, 4: 160})
        for table in (self.enabled_table, self.disabled_table):
            table.horizontalHeader().sectionClicked.connect(
                lambda col, t=table: self._on_header_clicked(col, t))
            table.itemChanged.connect(self._on_item_changed)
            table.verticalScrollBar().valueChanged.connect(self._ensure_visible_widgets)
            table.viewport().installEventFilter(self)

        self.enabled_label = QLabel("Enabled priority order:")
        self.enabled_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        self.disabled_label = QLabel("Disabled / available:")
        self.disabled_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        self.enabled_up_btn = QPushButton("▲ Up")
        self.enabled_up_btn.clicked.connect(lambda: self.move_item_in(self.enabled_table, -1))
        self.enabled_down_btn = QPushButton("▼ Down")
        self.enabled_down_btn.clicked.connect(lambda: self.move_item_in(self.enabled_table, 1))
        self.enabled_top_btn = QPushButton("⇈ Top")
        self.enabled_top_btn.clicked.connect(lambda: self.move_item_to_edge(self.enabled_table))
        self.enabled_bottom_btn = QPushButton("⇊ Bottom")
        self.enabled_bottom_btn.clicked.connect(lambda: self.move_item_to_edge(self.enabled_table, True))
        self.disabled_up_btn = QPushButton("▲ Up")
        self.disabled_up_btn.clicked.connect(lambda: self.move_item_in(self.disabled_table, -1))
        self.disabled_down_btn = QPushButton("▼ Down")
        self.disabled_down_btn.clicked.connect(lambda: self.move_item_in(self.disabled_table, 1))
        self.disabled_top_btn = QPushButton("⇈ Top")
        self.disabled_top_btn.clicked.connect(lambda: self.move_item_to_edge(self.disabled_table))
        self.disabled_bottom_btn = QPushButton("⇊ Bottom")
        self.disabled_bottom_btn.clicked.connect(lambda: self.move_item_to_edge(self.disabled_table, True))

        lists_splitter = QSplitter(Qt.Orientation.Horizontal)
        lists_splitter.setChildrenCollapsible(False)
        enabled_wrap = QWidget()
        enabled_panel = QVBoxLayout(enabled_wrap)
        enabled_panel.setContentsMargins(0, 0, 0, 0)
        enabled_panel.addWidget(self.enabled_label)
        enabled_panel.addWidget(self.enabled_table, 1)
        enabled_move = QHBoxLayout()
        enabled_move.addWidget(self.enabled_up_btn)
        enabled_move.addWidget(self.enabled_down_btn)
        enabled_move.addWidget(self.enabled_top_btn)
        enabled_move.addWidget(self.enabled_bottom_btn)
        enabled_move.addStretch()
        enabled_panel.addLayout(enabled_move)
        lists_splitter.addWidget(enabled_wrap)
        disabled_wrap = QWidget()
        disabled_panel = QVBoxLayout(disabled_wrap)
        disabled_panel.setContentsMargins(0, 0, 0, 0)
        disabled_panel.addWidget(self.disabled_label)
        disabled_panel.addWidget(self.disabled_table, 1)
        disabled_move = QHBoxLayout()
        disabled_move.addWidget(self.disabled_up_btn)
        disabled_move.addWidget(self.disabled_down_btn)
        disabled_move.addWidget(self.disabled_top_btn)
        disabled_move.addWidget(self.disabled_bottom_btn)
        disabled_move.addStretch()
        disabled_panel.addLayout(disabled_move)
        lists_splitter.addWidget(disabled_wrap)
        lists_splitter.setStretchFactor(0, 1)
        lists_splitter.setStretchFactor(1, 1)
        layout.addWidget(lists_splitter, 1)

        # Populate current list
        self.populate_list(current_global_list)
        self._ensure_visible_widgets()

        # Action buttons (stacked in 2 rows to prevent overflow)
        btn_layout = QVBoxLayout()

        row1_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Model...")
        self.add_btn.clicked.connect(self.add_model_prompt)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Remove models from the list. Choose which type to remove from the dropdown.")
        self.remove_btn.setMenu(_build_remove_menu(self.remove_models))

        row1_layout.addWidget(self.add_btn)
        row1_layout.addWidget(self.remove_btn)
        
        row2_layout = QHBoxLayout()
        self.list_test_btn = QPushButton("Test")
        self.list_test_btn.setToolTip("Test models from the list. Choose which mode from the dropdown.")
        self.list_test_btn.setMenu(_build_test_menu(self.on_test_all))
        self.group_same_btn = QPushButton("Group Same Models")
        self.group_same_btn.setToolTip("Cluster rows for the same model together across providers within each list so you can order each model once, then pick which provider entry has priority. Ignores vendor prefixes (openai/gpt-4o matches gpt-4o), :free suffixes, case, and punctuation (claude-haiku-4.5 matches claude-haiku-4-5); fallback still tries enabled rows top to bottom.")
        self.group_same_btn.clicked.connect(self.group_same_models)
        self.match_provider_btn = QPushButton("Match Per-Provider Enabled")
        self.match_provider_btn.setToolTip("Match Enabled/Disabled membership to the built-in and custom provider fallback lists. The global row order is preserved.")
        self.match_provider_btn.clicked.connect(self.match_provider_enabled)

        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setToolTip("Fetch available models for all providers.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_all)
        
        self.edit_provider_btn = QPushButton("✏️")
        self.edit_provider_btn.setToolTip("Edit the selected provider's endpoint, key, model, headers, and body params.")
        self.edit_provider_btn.clicked.connect(self.on_edit_selected_provider)
        
        self.remove_provider_btn = QPushButton("🗑️")
        self.remove_provider_btn.setToolTip("Remove all models belonging to the selected provider from this list.")
        self.remove_provider_btn.clicked.connect(self.on_remove_selected_provider)
        
        self.add_custom_provider_btn = QPushButton("+ Custom Provider")
        self.add_custom_provider_btn.setToolTip("Add a new custom provider by opening the Custom Provider dialog.")
        self.add_custom_provider_btn.clicked.connect(self.on_add_custom_provider)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset global fallback priority to default provider-based models.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        row2_layout.addWidget(self.list_test_btn)
        row2_layout.addWidget(self.group_same_btn)
        row2_layout.addWidget(self.match_provider_btn)
        row2_layout.addWidget(self.list_fetch_btn)
        row2_layout.addWidget(self.edit_provider_btn)
        row2_layout.addWidget(self.remove_provider_btn)
        row2_layout.addWidget(self.add_custom_provider_btn)
        row2_layout.addWidget(self.restore_btn)
        
        btn_layout.addLayout(row1_layout)
        btn_layout.addLayout(row2_layout)
        layout.addLayout(btn_layout)
        
        # OK / Cancel
        dlg_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dlg_btns.accepted.connect(self.accept)
        dlg_btns.rejected.connect(self.reject)
        layout.addWidget(dlg_btns)

    def _cancel_own_test(self):
        """Stop this dialog's model-test loop if it is still running in the
        background. Called when the dialog is closed so a test never keeps
        running (and logging) after its window disappears."""
        test_key = "global_fallback_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True

    def closeEvent(self, event):
        self._cancel_own_test()
        super().closeEvent(event)

    def _provider_display(self, provider):
        if hasattr(self.main_dialog, "custom_providers_data") and provider in self.main_dialog.custom_providers_data:
            return provider
        return provider.capitalize()

    def _tables(self):
        return (self.enabled_table, self.disabled_table)

    def _row_pair(self, table, row):
        item = table.item(row, 0)
        pair = item.data(Qt.ItemDataRole.UserRole) if item else None
        return (pair[0], pair[1])

    def _row_key(self, table, row):
        return self._row_pair(table, row)

    def _row_search_text(self, table, row):
        provider, model = self._row_pair(table, row)
        return f"{provider} {model}"

    def _sort_entry_key(self, table, col):
        if col == 0:
            return lambda pair, row: pair[0].casefold()
        if col == 1:
            return lambda pair, row: (normalized_model_key(pair[1]), pair[1].casefold())
        if col == 2:
            ranks = {"off": 0, "low": 1, "medium": 2, "high": 3}
            return lambda pair, row: ranks.get(str(self._g_thinking.get(pair[0], {}).get(pair[1], "off")), 0)
        if col == 3:
            return lambda pair, row: int(self._g_timeouts.get(pair[0], {}).get(pair[1], 0) or 0)
        return lambda pair, row: table.item(row, 4).text().casefold()

    def _capture_rows(self, table):
        data = []
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            pair = item.data(Qt.ItemDataRole.UserRole)
            data.append({
                "pair": (pair[0], pair[1]),
                "checked": item.checkState() == Qt.CheckState.Checked,
                "hidden": table.isRowHidden(r),
                "selected": item.isSelected(),
                "texts": {c: table.item(r, c).text() for c in (0, 1, 4)},
                "tips": {c: table.item(r, c).toolTip() for c in (0, 1, 4)},
                "bg": {c: table.item(r, c).background() for c in (0, 1, 4)},
                "fg": {c: table.item(r, c).foreground() for c in (0, 1, 4)},
            })
        return data

    def _restore_captured_row(self, table, d):
        p, m = d["pair"]
        row = table.rowCount()
        table.insertRow(row)
        for col in (0, 1, 4):
            item = QTableWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, (p, m))
            if col == 0:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            table.setItem(row, col, item)
        table.item(row, 0).setCheckState(Qt.CheckState.Checked if d["checked"] else Qt.CheckState.Unchecked)
        for col in (0, 1, 4):
            item = table.item(row, col)
            item.setText(d["texts"][col])
            item.setToolTip(d["tips"][col])
            item.setBackground(d["bg"][col])
            item.setForeground(d["fg"][col])
        table.setRowHidden(row, d["hidden"])
        table.item(row, 0).setSelected(d["selected"])
        return row

    def _reorder_to_keys(self, table, wanted, label=None):
        self._harvest_widgets()
        data = self._capture_rows(table)
        buckets = {}
        for d in data:
            buckets.setdefault(d["pair"], []).append(d)
        order_index = {pair: 0 for pair in buckets}
        ordered = []
        for pair in wanted:
            queue = buckets[pair]
            i = order_index[pair]
            order_index[pair] = i + 1
            ordered.append(queue[i])
        for d in ordered:
            d["added"] = False
        show_progress = label is not None and len(ordered) > self._reorder_progress_after
        prog = None
        if show_progress:
            from PyQt6.QtWidgets import QProgressDialog, QApplication
            prog = QProgressDialog(label, "Cancel", 0, len(ordered), self)
            prog.setWindowModality(Qt.WindowModality.WindowModal)
            prog.setMinimumDuration(400)
            prog.setValue(0)
        self._moving_rows = True
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        table.setVisible(False)
        try:
            table.setRowCount(0)
            cancelled = False
            for n, d in enumerate(ordered):
                self._restore_captured_row(table, d)
                d["added"] = True
                if prog is not None and n % 100 == 0:
                    prog.setValue(n)
                    QApplication.processEvents()
                    if prog.wasCanceled():
                        cancelled = True
                        break
            if cancelled:
                for d in data:
                    if not d["added"]:
                        self._restore_captured_row(table, d)
                        d["added"] = True
        finally:
            table.setVisible(True)
            table.setUpdatesEnabled(True)
            table.blockSignals(False)
            self._moving_rows = False
            if prog is not None:
                prog.close()
        self._ensure_table_widgets(table)
        self._update_counts()

    def _find_row(self, provider, model):
        for table in self._tables():
            for r in range(table.rowCount()):
                if self._row_pair(table, r) == (provider, model):
                    return table, r
        return None, -1

    def _update_counts(self):
        self.enabled_label.setText(f"Enabled priority order ({self.enabled_table.rowCount()}):")
        self.disabled_label.setText(f"Disabled / available ({self.disabled_table.rowCount()}):")

    def _on_item_changed(self, item):
        if self._moving_rows:
            return
        table = item.tableWidget()
        if table not in self._tables() or item.column() != 0:
            return
        row = table.row(item)
        if row < 0 or row >= table.rowCount():
            return
        pair = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            return
        provider, model = pair
        checked = item.checkState() == Qt.CheckState.Checked
        if (table is self.enabled_table) == checked:
            return
        self._move_row_to_other_table(table, row, checked)

    def _move_row_to_other_table(self, table, row, checked):
        pair = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            return
        provider, model = pair
        self._moving_rows = True
        try:
            self._harvest_widgets()
            table.removeRow(row)
            target = self.disabled_table if checked is False else self.enabled_table
            new_row = self._add_table_row(target, provider, model, checked=checked)
            target.setCurrentCell(new_row, 0)
            self._clear_sort_indicator(table)
            self._clear_sort_indicator(target)
            self._update_counts()
        finally:
            self._moving_rows = False

    def _seed_row_values(self, provider, model):
        think = self._g_thinking.setdefault(provider, {})
        if model not in think:
            per = self._per_thinking.get(provider, {}) or {}
            think[model] = per.get(model, "off") if isinstance(per, dict) else "off"
        timeouts = self._g_timeouts.setdefault(provider, {})
        if model not in timeouts:
            per = self._per_timeouts.get(provider, {}) or {}
            timeouts[model] = per.get(model, 0) if isinstance(per, dict) else 0

    def _render_row(self, table, row, provider, model):
        global_statuses = PERSISTENT_TEST_STATUSES.get("global_fallback_statuses", {})
        global_tooltips = PERSISTENT_TEST_STATUSES.get("global_fallback_tooltips", {})
        status = global_statuses.get((provider, model))
        bl = is_model_blacklisted(provider, model, getattr(self.main_dialog, "config", None))
        remaining = _get_blacklist_remaining(provider, model, getattr(self.main_dialog, "config", None))
        bl_text = " | 🚫 Blacklisted"
        if remaining:
            bl_text += f" ({remaining})"
        core = status or ""
        if bl:
            core = f"{core}{bl_text}" if core else bl_text.strip()
        new_mark, dep_mark, missing_mark, is_new, is_dep, is_missing = self._global_marks(provider, model)
        texts = {
            0: self._provider_display(provider),
            1: f"{new_mark}{model}",
            4: f"({core}){dep_mark}{missing_mark}" if (core or dep_mark or missing_mark) else "",
        }
        if bl:
            tt = "This model is currently on cooldown due to recent failures."
            if remaining:
                tt += f"<br/><i>{remaining} left</i>"
        elif is_dep:
            tt = "⚠️ This model appears to be deprecated/retired. Consider removing it from the global list."
        elif is_missing:
            tt = "⚠️ The provider no longer returned this model in the latest fetch. It may be retired — consider removing it from the global list."
        else:
            tt = global_tooltips.get((provider, model), "")
        for col, text in texts.items():
            item = table.item(row, col)
            item.setText(text)
            item.setToolTip(tt)
            self._apply_global_highlight(item, provider, model)
        self._refresh_row_widgets(table, row)

    def _add_table_row(self, table, provider, model, checked=True):
        self._seed_row_values(provider, model)
        table.blockSignals(True)
        try:
            row = table.rowCount()
            table.insertRow(row)
            for col in (0, 1, 4):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, (provider, model))
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                table.setItem(row, col, item)
            table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            table.blockSignals(False)
        self._render_row(table, row, provider, model)
        return row

    def _materialize_row_widgets(self, table, row):
        if table.cellWidget(row, 2) is not None:
            return
        provider, model = self._row_pair(table, row)
        combo = QComboBox()
        combo.addItems(["off", "low", "medium", "high"])
        combo.setCurrentText(str(self._g_thinking.get(provider, {}).get(model, "off")))
        table.setCellWidget(row, 2, combo)
        spin = QSpinBox()
        spin.setRange(0, 300)
        spin.setSuffix(" s")
        spin.setToolTip("Request timeout in seconds. 0 = inherit the per-provider / global timeout.")
        try:
            spin.setValue(int(self._g_timeouts.get(provider, {}).get(model, 0) or 0))
        except (TypeError, ValueError):
            spin.setValue(0)
        table.setCellWidget(row, 3, spin)

    def _ensure_table_widgets(self, table):
        count = table.rowCount()
        if count == 0:
            return
        first = table.rowAt(0)
        if first < 0:
            first = 0
        viewport_h = max(1, table.viewport().height())
        last = table.rowAt(viewport_h - 2)
        if last < first:
            row_h = max(1, table.rowHeight(first))
            last = min(count - 1, first + (viewport_h // row_h))
        lo = max(0, first - 15)
        hi = min(count - 1, last + 15)
        updates = table.updatesEnabled()
        if updates:
            table.setUpdatesEnabled(False)
        try:
            for i in range(lo, hi + 1):
                if not table.isRowHidden(i):
                    self._materialize_row_widgets(table, i)
        finally:
            if updates:
                table.setUpdatesEnabled(True)

    def _ensure_visible_widgets(self):
        for table in self._tables():
            self._ensure_table_widgets(table)

    def _harvest_widgets(self):
        for table in self._tables():
            for r in range(table.rowCount()):
                combo = table.cellWidget(r, 2)
                spin = table.cellWidget(r, 3)
                if combo is None and spin is None:
                    continue
                provider, model = self._row_pair(table, r)
                if combo is not None:
                    self._g_thinking.setdefault(provider, {})[model] = combo.currentText()
                if spin is not None:
                    self._g_timeouts.setdefault(provider, {})[model] = spin.value()

    def _refresh_row_widgets(self, table, row):
        if row < 0 or row >= table.rowCount():
            return
        provider, model = self._row_pair(table, row)
        combo = table.cellWidget(row, 2)
        if combo is not None:
            combo.setCurrentText(str(self._g_thinking.get(provider, {}).get(model, "off")))
        spin = table.cellWidget(row, 3)
        if spin is not None:
            try:
                spin.setValue(int(self._g_timeouts.get(provider, {}).get(model, 0) or 0))
            except (TypeError, ValueError):
                spin.setValue(0)

    def _refresh_visible_widgets(self):
        for table in self._tables():
            for r in range(table.rowCount()):
                if table.cellWidget(r, 2) is not None:
                    self._refresh_row_widgets(table, r)

    def _all_pairs(self):
        return {self._row_pair(t, r) for t in self._tables() for r in range(t.rowCount())}

    def get_global_thinking_levels(self):
        self._harvest_widgets()
        pairs = self._all_pairs()
        return {p: {m: v for m, v in models.items() if (p, m) in pairs}
                for p, models in self._g_thinking.items() if isinstance(models, dict)}

    def get_global_model_timeouts(self):
        self._harvest_widgets()
        pairs = self._all_pairs()
        return {p: {m: v for m, v in models.items() if (p, m) in pairs}
                for p, models in self._g_timeouts.items() if isinstance(models, dict)}

    def match_provider_enabled(self):
        """Match global membership to provider fallback enabled states only."""
        enabled_pairs = set(provider_enabled_pairs(self.main_dialog))
        self._moving_rows = True
        try:
            ordered = [self._row_key(table, r) for table in self._tables() for r in range(table.rowCount())]
            enabled = [pair for pair in ordered if pair in enabled_pairs]
            disabled = [pair for pair in ordered if pair not in enabled_pairs]
            self._rebuild_global_membership(enabled, self.enabled_table)
            self._rebuild_global_membership(disabled, self.disabled_table)
        finally:
            self._moving_rows = False
        self._update_counts()

    def _rebuild_global_membership(self, pairs, table):
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(0)
            for provider, model in pairs:
                self._add_table_row(table, provider, model, checked=(table is self.enabled_table))
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)
        self._ensure_table_widgets(table)

    def populate_list(self, model_pairs):
        for table in self._tables():
            table.blockSignals(True)
            table.setRowCount(0)
            self._clear_sort_indicator(table)

        # Global checkbox state is independent from per-provider fallback state.
        disabled_map = getattr(self.main_dialog, "disabled_global_model_priority_data", [])
        disabled_map = set(tuple(item) for item in disabled_map if isinstance(item, (list, tuple)) and len(item) == 2)

        for table in self._tables():
            table.setUpdatesEnabled(False)
        try:
            for provider, model in model_pairs:
                if (provider, model) in disabled_map:
                    self._add_table_row(self.disabled_table, provider, model, checked=False)
                else:
                    self._add_table_row(self.enabled_table, provider, model, checked=True)
        finally:
            for table in self._tables():
                table.setUpdatesEnabled(True)
                table.blockSignals(False)
        self._update_counts()

    def _global_marks(self, provider, model):
        """Returns (new_mark, dep_mark, missing_mark, is_new, is_deprecated, is_missing)."""
        is_new = model in GLOBAL_NEWLY_ADDED_MODELS.get(provider, ())
        is_dep = is_model_deprecated(provider, model)
        is_missing = model in GLOBAL_MISSING_FROM_FETCH.get(provider, ())
        return ("🆕 " if is_new else "",
                " | ⚠️ Deprecated" if is_dep else "",
                " | ⚠️ No Longer Returned" if (is_missing and not is_dep) else "",
                is_new, is_dep, is_missing)

    def _apply_global_highlight(self, item, provider, model):
        _n, _d, _m, is_new, is_dep, is_missing = self._global_marks(provider, model)
        item.setBackground(QBrush())
        item.setForeground(QBrush())
        if is_dep:
            item.setBackground(QBrush(QColor(COL_DEP_BG)))
            item.setForeground(QBrush(QColor(COL_DEP_FG)))
        elif is_missing:
            item.setBackground(QBrush(QColor(COL_MISSING_BG)))
            item.setForeground(QBrush(QColor(COL_MISSING_FG)))
        elif is_new:
            item.setBackground(QBrush(QColor(COL_NEW_BG)))
            item.setForeground(QBrush(QColor(COL_NEW_FG)))

    _reorder_progress_after = 800

    def _apply_pair_order(self, table, wanted, label=None):
        self._reorder_to_keys(table, wanted, label)
        self._clear_sort_indicator(table)

    def group_same_models(self):
        for table in self._tables():
            pairs = [self._row_key(table, r) for r in range(table.rowCount())]
            self._apply_pair_order(table, cluster_pairs_by_model(pairs), "Grouping same models...")

    def filter_models(self, text):
        for table in self._tables():
            query = text.strip().casefold()
            for r in range(table.rowCount()):
                table.setRowHidden(r, bool(query and query not in self._row_search_text(table, r).casefold()))

    def refresh_statuses(self):
        for table in self._tables():
            for r in range(table.rowCount()):
                self._render_row(table, r, *self._row_key(table, r))

    def add_model_prompt(self):
        providers = list(PROVIDER_ORDER) + list(self.main_dialog.custom_providers_data.keys())
        dlg = AddModelDialog(self, providers, DEFAULT_MODELS, MODEL_SUGGESTIONS, MODEL_FALLBACKS)
        if dlg.exec():
            provider, model = dlg.get_selection()
            if provider and model:
                self._add_table_row(self.enabled_table, provider, model, checked=True)
                self._update_counts()

    def move_item(self, delta):
        self.move_item_in(self._focused_table(), delta)

    def move_item_in(self, table, delta):
        rows = self._selected_rows(table)
        if not rows:
            return
        selected_pairs = {self._row_key(table, row) for row in rows}
        pairs = [self._row_key(table, r) for r in range(table.rowCount())]
        selected = set(rows)
        candidates = rows if delta < 0 else reversed(rows)
        for row in candidates:
            neighbor = row + delta
            if neighbor < 0 or neighbor >= len(pairs) or neighbor in selected:
                continue
            pairs[row], pairs[neighbor] = pairs[neighbor], pairs[row]
            selected.remove(row)
            selected.add(neighbor)
        wanted = pairs
        self._reorder_to_keys(table, wanted, "Moving rows...")
        table.clearSelection()
        selection_model = table.selectionModel()
        selected_rows = []
        for row in range(table.rowCount()):
            if self._row_key(table, row) in selected_pairs:
                selected_rows.append(row)
        if selected_rows:
            table.setCurrentCell(selected_rows[0], 0)
        for row in selected_rows:
            selection_model.select(
                table.model().index(row, 0),
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        self._clear_sort_indicator(table)

    def on_edit_selected_provider(self):
        table = self._focused_table()
        row = table.currentRow()
        if row < 0:
            tooltip("Select a provider/model row first.")
            return
        provider, model = self._row_pair(table, row)
        custom_providers = getattr(self.main_dialog, "custom_providers_data", {}) or {}
        cp_data = custom_providers.get(provider)
        if not cp_data:
            cp_data = {
                "url": "",
                "models_url": "",
                "api_key": self.main_dialog.config.get("api_keys", {}).get(provider, ""),
                "model": model,
                "headers": {},
                "body_params": {},
            }
        dlg = CustomProviderDialog(self, name=provider, data=cp_data, config=self.main_dialog.config)
        if dlg.exec():
            new_data = dlg.get_data()
            new_name = dlg.name_edit.text().strip()
            if not new_name:
                return
            if new_name != provider:
                self._harvest_widgets()
                if provider in self._g_thinking:
                    self._g_thinking.setdefault(new_name, {}).update(self._g_thinking.pop(provider))
                if provider in self._g_timeouts:
                    self._g_timeouts.setdefault(new_name, {}).update(self._g_timeouts.pop(provider))
                for table in self._tables():
                    for i in range(table.rowCount()):
                        p, m = self._row_pair(table, i)
                        if p == provider:
                            for col in (0, 1, 4):
                                table.item(i, col).setData(Qt.ItemDataRole.UserRole, (new_name, m))
                            self._render_row(table, i, new_name, m)
                cp_data = custom_providers.get(provider, {})
                if cp_data and provider in custom_providers:
                    del custom_providers[provider]
                custom_providers[new_name] = new_data
                if not hasattr(self.main_dialog, "custom_providers_data"):
                    self.main_dialog.custom_providers_data = {}
                self.main_dialog.custom_providers_data.update(custom_providers)
            else:
                custom_providers[provider] = new_data
                if not hasattr(self.main_dialog, "custom_providers_data"):
                    self.main_dialog.custom_providers_data = {}
                self.main_dialog.custom_providers_data[provider] = new_data
            if new_data.get("api_key") and "api_keys" in self.main_dialog.config:
                self.main_dialog.config["api_keys"][new_name] = new_data["api_key"]
            tooltip(f"Updated provider: {new_name}")

    def on_remove_selected_provider(self):
        table = self._focused_table()
        row = table.currentRow()
        if row < 0:
            tooltip("Select a provider/model row first.")
            return
        provider, _ = self._row_pair(table, row)
        self._harvest_widgets()
        removed = 0
        for t in self._tables():
            for i in reversed([j for j in range(t.rowCount()) if self._row_pair(t, j)[0] == provider]):
                t.removeRow(i)
                removed += 1
        self._g_thinking.pop(provider, None)
        self._g_timeouts.pop(provider, None)
        self._update_counts()
        tooltip(f"Removed {removed} model(s) for {provider}.")

    def on_add_custom_provider(self):
        dlg = CustomProviderDialog(self, config=self.main_dialog.config)
        if dlg.exec():
            data = dlg.get_data()
            name = dlg.name_edit.text().strip()
            if not name:
                return
            if not hasattr(self.main_dialog, "custom_providers_data"):
                self.main_dialog.custom_providers_data = {}
            self.main_dialog.custom_providers_data[name] = data
            if data.get("api_key"):
                if "api_keys" not in self.main_dialog.config:
                    self.main_dialog.config["api_keys"] = {}
                self.main_dialog.config["api_keys"][name] = data["api_key"]
            models = []
            try:
                temp_config = self.main_dialog.config.copy()
                temp_config["custom_providers"] = self.main_dialog.custom_providers_data
                client = AIClient(temp_config)
                models = client.fetch_models(name)
            except Exception:
                pass
            if not models and data.get("model"):
                models = [data["model"]]
            for m in models:
                self._add_table_row(self.enabled_table, name, m, checked=True)
            self._update_counts()
            tooltip(f"Added custom provider: {name}")

    def _rows_matching(self, table, pred):
        rows = []
        for i in range(table.rowCount()):
            if pred(*self._row_pair(table, i)):
                rows.append(i)
        return rows

    def remove_models(self, kind):
        """Remove rows based on the requested removal type.

        kind in {"selected", "deprecated", "missing", "flagged"}.
        """
        targets = []
        if kind == "selected":
            for table in self._tables():
                targets.extend((table, i) for i in self._selected_rows(table))
            label = "selected"
        elif kind == "deprecated":
            for table in self._tables():
                targets.extend((table, i) for i in self._rows_matching(table, lambda p, m: is_model_deprecated(p, m)))
            label = "deprecated"
        elif kind == "missing":
            for table in self._tables():
                targets.extend((table, i) for i in self._rows_matching(
                    table, lambda p, m: m in GLOBAL_MISSING_FROM_FETCH.get(p, set())))
            label = "no-longer-returned"
        else:
            for table in self._tables():
                targets.extend((table, i) for i in self._rows_matching(
                    table, lambda p, m: is_model_deprecated(p, m) or m in GLOBAL_MISSING_FROM_FETCH.get(p, set())))
            label = "deprecated/no-longer-returned"

        if not targets:
            tooltip(f"No {label} models found in the list.")
            return
        self._harvest_widgets()
        by_table = {}
        for table, i in targets:
            by_table.setdefault(table, []).append(i)
        removed = 0
        for table, rows in by_table.items():
            for i in sorted(set(rows), reverse=True):
                provider, model = self._row_pair(table, i)
                table.removeRow(i)
                if provider in self._g_thinking and model in self._g_thinking[provider]:
                    del self._g_thinking[provider][model]
                if provider in self._g_timeouts and model in self._g_timeouts[provider]:
                    del self._g_timeouts[provider][model]
                removed += 1
        self._update_counts()
        tooltip(f"Removed {removed} model(s).")
            
    def restore_defaults(self):
        defaults = []
        priority = self.main_dialog.config.get("provider_priority", PROVIDER_ORDER)
        for p in priority:
            active_m = self.main_dialog.config.get("models", {}).get(p, DEFAULT_MODELS.get(p, ""))
            if active_m:
                defaults.append((p, active_m))
            fallbacks = self.main_dialog.config.get("model_fallbacks", {}).get(p, MODEL_FALLBACKS.get(p, []))
            for f in fallbacks:
                if f != active_m:
                    defaults.append((p, f))
        self._g_thinking = {}
        self._g_timeouts = {}
        self.populate_list(defaults)
        self._ensure_visible_widgets()
        
    def get_ordered_list(self):
        return [self._row_pair(self.enabled_table, r) for r in range(self.enabled_table.rowCount())]

    def get_disabled_list(self):
        return [self._row_pair(self.disabled_table, r) for r in range(self.disabled_table.rowCount())]
        
    def on_fetch_all(self):
        fetch_key = "global_fallback_fetch"
        if fetch_key in FETCH_CANCELLATIONS:
            FETCH_CANCELLATIONS[fetch_key] = True
            self.list_fetch_btn.setText("Fetch All")
            return
            
        FETCH_CANCELLATIONS[fetch_key] = False
        self.list_fetch_btn.setText("Stop Fetch All")
        self.list_test_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        
        # Determine which providers we will fetch for
        providers_to_fetch = []
        for provider, combobox in self.main_dialog.model_edits.items():
            api_key = self.main_dialog.api_key_edits[provider].text().strip() if provider in self.main_dialog.api_key_edits else ""
            if api_key or provider == "local":
                providers_to_fetch.append(provider)
        
        if "local" not in providers_to_fetch and hasattr(self.main_dialog, 'local_model_edit'):
            providers_to_fetch.append("local")

        # Also fetch for custom named local providers
        if hasattr(self.main_dialog, "local_providers_data"):
            for lp, lp_data in (self.main_dialog.local_providers_data or {}).items():
                if lp_data and lp_data.get("enabled", True):
                    if lp not in providers_to_fetch:
                        providers_to_fetch.append(lp)

        # Also fetch for custom API providers (OpenAI-compatible custom providers)
        if hasattr(self.main_dialog, "custom_providers_data"):
            for cp, cp_data in (self.main_dialog.custom_providers_data or {}).items():
                if cp_data and isinstance(cp_data, dict) and str(cp_data.get("url", "") or "").strip():
                    if cp not in providers_to_fetch:
                        providers_to_fetch.append(cp)
        
        if not providers_to_fetch:
            tooltip("No providers configured to fetch.")
            self.list_fetch_btn.setText("Fetch All")
            self.list_test_btn.setEnabled(True)
            self.restore_btn.setEnabled(True)
            return
            
        import threading
        from ..ai_client import AIClient
        
        tooltip("Fetching models from all configured providers...")
        
        def _runner():
            try:
                for provider in providers_to_fetch:
                    if FETCH_CANCELLATIONS.get(fetch_key):
                        break
                    
                    try:
                        api_key = self.main_dialog.api_key_edits[provider].text().strip() if provider in self.main_dialog.api_key_edits else ""
                        temp_config = self.main_dialog.config.copy()
                        temp_config["local_providers"] = self.main_dialog.local_providers_data
                        # Always include current custom_providers so fetch_models has URLs/keys
                        if hasattr(self.main_dialog, "custom_providers_data"):
                            temp_config["custom_providers"] = self.main_dialog.custom_providers_data
                        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                        temp_config["api_keys"][provider] = api_key
                        if provider == "local":
                            temp_config["local_endpoint"] = self.main_dialog._local_endpoint_for()
                        
                        client = AIClient(temp_config)
                        models = client.fetch_models(provider)
                    except Exception as e:
                        logger.debug(f"AI-Hints: global fetch failed for {provider}: {e}")
                        continue
                    
                    if FETCH_CANCELLATIONS.get(fetch_key):
                        break
                        
                    if models:
                        def _update_ui(p=provider, ms=models):
                            existing = [self._row_pair(t, j) for t in self._tables() for j in range(t.rowCount())]
                            existing_set = set(existing)

                            added_count = 0
                            newly = GLOBAL_NEWLY_ADDED_MODELS.setdefault(p, set())
                            for m in sorted(list(set(ms))):
                                if m and (p, m) not in existing_set:
                                    newly.add(m)
                                    self._add_table_row(self.disabled_table, p, m, checked=False)
                                    added_count += 1
                            self._update_counts()
                            
                            fetched_set = set(ms)
                            missed = {m for (pr, m) in existing if pr == p and m not in fetched_set}
                            if missed:
                                GLOBAL_MISSING_FROM_FETCH[p] = missed
                            
                            self.refresh_statuses()
                            if added_count > 0:
                                tooltip(f"Added {added_count} new models for {self._provider_display(p)}.")
                        mw.taskman.run_on_main(_update_ui)
            except Exception as e:
                err_msg = str(e)
                def _fail():
                    info(f"Error during global fetch: {err_msg}")
                mw.taskman.run_on_main(_fail)
            finally:
                if fetch_key in FETCH_CANCELLATIONS:
                    del FETCH_CANCELLATIONS[fetch_key]
                def _enable():
                    self.list_fetch_btn.setText("Fetch All")
                    self.list_test_btn.setEnabled(True)
                    self.restore_btn.setEnabled(True)
                mw.taskman.run_on_main(_enable)
                
        threading.Thread(target=_runner, daemon=True).start()
        
    def on_test_all(self, mode="checked"):
        test_key = "global_fallback_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True
            self.list_test_btn.setText("Test")
            tooltip("Testing cancelled.")
            return

        cancel_other_model_tests(test_key)
        TEST_CANCELLATIONS[test_key] = False
        self.list_test_btn.setText("Stop Test")
        self.restore_btn.setEnabled(False)
        self.enabled_up_btn.setEnabled(False)
        self.enabled_down_btn.setEnabled(False)
        self.disabled_up_btn.setEnabled(False)
        self.disabled_down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        
        if mode == "checked":
            tables = [self.enabled_table]
        else:
            tables = list(self._tables())

        def _test_includes(table, i):
            item = table.item(i, 0)
            if mode == "row":
                return item.isSelected()
            if mode == "checked":
                return item.checkState() == Qt.CheckState.Checked
            return True

        items_data = []
        seen_items = set()
        for table in tables:
            for i in range(table.rowCount()):
                if not _test_includes(table, i):
                    continue
                data = self._row_pair(table, i)
                if data in seen_items:
                    continue
                seen_items.add(data)
                items_data.append(data)

        import threading
        from ..ai_client import AIClient
        
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            
            for i, (provider, model) in enumerate(items_data):
                if TEST_CANCELLATIONS.get(test_key):
                    break
                def _update_testing(prov=provider, name=model):
                    table, row = self._find_row(prov, name)
                    if row >= 0:
                        table.item(row, 4).setText(f"(⏳ Testing...)")
                mw.taskman.run_on_main(_update_testing)
                
                status = "✅ Working"
                tooltip_text = ""
                try:
                    temp_config = self.main_dialog.config.copy()
                    temp_config["local_providers"] = self.main_dialog.local_providers_data
                    api_key = self.main_dialog.api_key_edits[provider].text().strip() if provider in self.main_dialog.api_key_edits else ""
                    # Only override the key when the edit field actually has a value;
                    # otherwise keep the saved (correct) key from the config copy.
                    if api_key:
                        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                        temp_config["api_keys"][provider] = api_key
                    # Include in-memory (unsaved) custom providers so a freshly added
                    # provider tests with the current URL/key before Save.
                    if hasattr(self.main_dialog, "custom_providers_data"):
                        temp_config["custom_providers"] = self.main_dialog.custom_providers_data
                    if "models" not in temp_config: temp_config["models"] = {}
                    temp_config["models"][provider] = model
                    
                    if provider == "local":
                        temp_config["local_endpoint"] = self.main_dialog._local_endpoint_for(model)
                    client = AIClient(temp_config)
                    test_front = self.main_dialog.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION
                    test_back = self.main_dialog.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER
                    if TEST_CANCELLATIONS.get(test_key):
                        break
                    res = client.generate_options(test_front, test_back, override_provider=provider, only_this_provider=True, override_model=model)
                    if TEST_CANCELLATIONS.get(test_key):
                        break
                    if not (res and (res.get("hints") or res.get("options"))):
                        status = "❌ Empty"
                        tooltip_text = (
                            f"<div style='width: 350px;'>"
                            f"<b>Question:</b> {test_front}<br/>"
                            f"<b>Answer:</b> {test_back}<br/><br/>"
                            f"<b>Status:</b> Provider returned empty response or no usable hints/options.<br/>"
                            f"<i>Tip: Check model name, API key, quota, or response format.</i>"
                            f"</div>"
                        )
                    else:
                        formatted_res = json.dumps(res, indent=2, ensure_ascii=False)
                        # Use pre-wrap and fixed width to ensure tooltip stays compact and to the right
                        tooltip_text = (
                            f"<div style='width: 450px;'>"
                            f"<b>Question:</b> {test_front}<br/>"
                            f"<b>Answer:</b> {test_back}<br/><br/>"
                            f"<b>Model Response:</b><br/>"
                            f"<pre style='font-family: monospace; font-size: 11px; white-space: pre-wrap; word-wrap: break-word;'>{formatted_res}</pre>"
                            f"</div>"
                        )
                except Exception as e:
                    err_str = str(e)
                    if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                        status = "⏳ Timeout"
                    else:
                        status = "❌ Error"
                    tooltip_text = (
                        f"<div style='width: 350px;'>"
                        f"<b>Question:</b> {test_front}<br/>"
                        f"<b>Answer:</b> {test_back}<br/><br/>"
                        f"<b>Error:</b> {err_str}<br/>"
                        f"{'<i>Tip: Endpoint took longer to respond than the request timeout limit. Increase timeout in Advanced tab.</i>' if 'Timeout' in status else ''}"
                        f"</div>"
                    )
                    
                if TEST_CANCELLATIONS.get(test_key):
                    break

                def _update_result(prov=provider, name=model, st=status, tt=tooltip_text):
                    global_statuses = PERSISTENT_TEST_STATUSES.setdefault("global_fallback_statuses", {})
                    global_statuses[(prov, name)] = st
                    global_tooltips = PERSISTENT_TEST_STATUSES.setdefault("global_fallback_tooltips", {})
                    global_tooltips[(prov, name)] = tt
                    table, row = self._find_row(prov, name)
                    if row >= 0:
                        self._render_row(table, row, prov, name)
                mw.taskman.run_on_main(_update_result)
                
            def _done():
                self.list_test_btn.setText("Test")
                self.restore_btn.setEnabled(True)
                self.enabled_up_btn.setEnabled(True)
                self.enabled_down_btn.setEnabled(True)
                self.disabled_up_btn.setEnabled(True)
                self.disabled_down_btn.setEnabled(True)
                self.remove_btn.setEnabled(True)
                self.add_btn.setEnabled(True)
                if test_key in TEST_CANCELLATIONS:
                    del TEST_CANCELLATIONS[test_key]
            mw.taskman.run_on_main(_done)
            
        threading.Thread(target=_runner, daemon=True).start()


class ProvidersTabMixin:
    def _local_endpoint_for(self, model=""):
        """Build a local_endpoint dict from in-memory local_providers_data."""
        endpoint = dict(self.config.get("local_endpoint", {}) or {})
        providers = getattr(self, "local_providers_data", {}) or {}
        provider_data = providers.get("local")
        if not provider_data:
            provider_data = next(iter(providers.values()), {}) if providers else {}
        provider_data = provider_data or {}
        endpoint["base_url"] = (
            provider_data.get("url")
            or provider_data.get("base_url")
            or endpoint.get("base_url")
            or "http://localhost:11434/v1"
        )
        endpoint["api_key"] = provider_data.get("api_key", endpoint.get("api_key", ""))
        if model:
            endpoint["model"] = model
        return endpoint

    def update_fallback_ui_states(self):
        if not hasattr(self, "advanced_fallback_cb"):
            return
        use_global = self.advanced_fallback_cb.isChecked()
        self.advanced_fallback_btn.setEnabled(use_global)

        # Visually dim the per-provider rows while the advanced global fallback
        # list is active, so it's obvious the global list governs fallback order —
        # but keep the controls fully interactive (grayed out, not disabled).
        # Per-provider settings (keys, active model, enable toggle, per-provider
        # fallbacks/timeouts) are still read at runtime, so the user can reach
        # them without unchecking the global list. When unchecked, restore full
        # opacity.
        if hasattr(self, 'models_layout') and self.models_layout is not None:
            from .widgets import ProviderRowWidget
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget):
                    if use_global:
                        effect = QGraphicsOpacityEffect(w)
                        effect.setOpacity(0.45)
                        w.setGraphicsEffect(effect)
                    else:
                        w.setGraphicsEffect(None)

        # Update the visible mode indicator (text + colour) and highlight the
        # Advanced Fallback button whenever the global list is active, so the user
        # always knows which fallback mode is in play.
        if hasattr(self, "fallback_mode_label"):
            if use_global:
                self.fallback_mode_label.setText(
                    "🖥️ <b>Mode: Advanced Global Fallback active</b> — the global "
                    "priority list controls cross-provider fallback order. Provider "
                    "rows are dimmed for clarity but stay fully interactive (keys, "
                    "models, toggles, and per-provider fallbacks are still read at "
                    "runtime)."
                )
                self.fallback_mode_label.setStyleSheet(
                    "color: #1e7e34; font-weight: normal; padding: 5px; "
                    "background-color: rgba(30,126,52,0.12); border-radius: 4px;"
                )
            else:
                self.fallback_mode_label.setText(
                    "⚙️ <b>Mode: Standard per-provider fallbacks</b> — each provider "
                    "uses its own nested fallback list in priority order. The "
                    "advanced global list is not applied."
                )
                self.fallback_mode_label.setStyleSheet(
                    "color: #5a6268; font-weight: normal; padding: 5px;"
                )

        if hasattr(self, "advanced_fallback_btn"):
            if use_global:
                self.advanced_fallback_btn.setStyleSheet(
                    "QPushButton { background-color: #1e7e34; color: white; "
                    "font-weight: bold; border-radius: 4px; padding: 3px 8px; }"
                )
            else:
                self.advanced_fallback_btn.setStyleSheet("")
                    
    def rank_checked_providers_first(self):
        """Reorder provider rows so all checked/enabled providers float to the top,
        preserving their relative order."""
        if not hasattr(self, "models_layout") or self.models_layout is None:
            return
        from .widgets import ProviderRowWidget
        checked = []
        unchecked = []
        for i in range(self.models_layout.count()):
            item = self.models_layout.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if isinstance(w, ProviderRowWidget):
                (checked if w.enabled_cb.isChecked() else unchecked).append(w)
        for w in unchecked:
            self.models_layout.removeWidget(w)
        for w in checked:
            self.models_layout.removeWidget(w)
        for w in checked:
            self.models_layout.addWidget(w)
        for w in unchecked:
            self.models_layout.addWidget(w)
        tooltip("Ranked checked providers first.")
    
    def on_add_custom_provider(self):
        from .widgets import CustomProviderDialog
        dlg = CustomProviderDialog(self, config=self.config)
        if dlg.exec():
            data = dlg.get_data()
            name = dlg.name_edit.text().strip()
            if not name:
                return
            if not hasattr(self, "custom_providers_data"):
                self.custom_providers_data = {}
            self.custom_providers_data[name] = data
            if data.get("api_key"):
                if "api_keys" not in self.config:
                    self.config["api_keys"] = {}
                self.config["api_keys"][name] = data["api_key"]
            self.refresh_custom_list()
            tooltip(f"Added custom provider: {name}")
                    
    def update_special_blacklist_status(self, provider, combobox, status_label):
        model = combobox.currentText().strip()
        status_info = PERSISTENT_TEST_STATUSES.get(provider)
        if status_info:
            status_text, tooltip_text, style_color, tested_model = status_info
            if tested_model == model:
                status_label.setText(status_text)
                status_label.setToolTip(tooltip_text)
                status_label.setStyleSheet(f"font-weight: bold; color: {style_color}; margin-left: 5px;")
                return
            else:
                PERSISTENT_TEST_STATUSES.pop(provider, None)
                
        from ..ai_client import is_model_blacklisted
        if model and is_model_blacklisted(provider, model, getattr(self.main_dialog, "config", None)):
            status_label.setText("🚫 Blacklisted")
            status_label.setToolTip("This model is currently blacklisted on cooldown due to recent failures.")
            status_label.setStyleSheet("font-weight: bold; color: red; margin-left: 5px;")
        else:
            status_label.setText("")
            status_label.setToolTip("")

    def on_reset_test_prompt(self):
        self.test_question_edit.setText(DEFAULT_TEST_QUESTION)
        self.test_answer_edit.setText(DEFAULT_TEST_ANSWER)
        tooltip("Reset test prompt to default.")

    def _known_global_providers(self):
        known = set(PROVIDER_ORDER)
        known.update((self.config.get("provider_priority", None) or []))
        for attr in ("custom_providers_data", "local_providers_data"):
            data = getattr(self, attr, {}) or {}
            if isinstance(data, dict):
                known.update(data.keys())
        known.add("local")
        return known

    def on_advanced_fallback_clicked(self):
        if not hasattr(self, "global_model_priority_data"):
            self.global_model_priority_data = self.config.get("global_model_priority", [])

        current_list, orphaned = prune_orphan_pairs(self.global_model_priority_data, self._known_global_providers())
        if orphaned:
            tooltip(f"Ignoring {orphaned} row(s) for deleted providers (dropped on OK).")

        dlg = GlobalFallbackOrderDialog(self, current_list)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        self.global_fallback_dlg = dlg
        def save_global_fallback():
            # The full list must keep disabled rows too (they live in the
            # Disabled table now); the separate disabled map marks which
            # are off, and never touches per-provider fallback state.
            self.disabled_global_model_priority_data = dlg.get_disabled_list()
            self.global_model_priority_data = dlg.get_ordered_list() + self.disabled_global_model_priority_data

            # This row's own thinking/timeout values live in the global
            # scope and override the per-provider ones at runtime.
            self.global_thinking_levels_data = dlg.get_global_thinking_levels()
            self.global_model_timeouts_data = dlg.get_global_model_timeouts()
            tooltip("Advanced fallback priority and disabled states updated. Click Save to apply.")

        def clear_global_fallback(*args):
            self.global_fallback_dlg = None

        dlg.accepted.connect(save_global_fallback)
        dlg.finished.connect(clear_global_fallback)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _create_providers_tab(self):
        """Constructs the Tab 2: AI Providers UI"""
        self.providers_tab = QWidget()
        prov_main_layout = QVBoxLayout()
        
        prov_scroll = QScrollArea()
        prov_scroll.setWidgetResizable(True)
        prov_content = QWidget()
        self.prov_layout = QFormLayout(prov_content)
        
        self.api_key_edits = {}
        self.model_edits = {}

        model_group = QGroupBox("Model Names & Fallback Priority")
        model_main_layout = QVBoxLayout()
        
        # Add Fetch All, Test All, and Restore Default buttons
        model_btns_layout = QHBoxLayout()
        
        self.fetch_all_btn = QPushButton("Fetch All")
        self.fetch_all_btn.setToolTip("Attempts to fetch latest models for all providers that have API keys.")
        self.fetch_all_btn.clicked.connect(self.on_fetch_all_models)
        model_btns_layout.addWidget(self.fetch_all_btn)
        
        test_all_btn = QPushButton("Test All")
        test_all_btn.setToolTip("Runs sequential test checks for all configured/enabled providers.")
        test_all_btn.clicked.connect(self.on_test_all_models)
        model_btns_layout.addWidget(test_all_btn)
        
        restore_models_btn = QPushButton("Restore Defaults")
        restore_models_btn.setToolTip("Restores model names to factory defaults.")
        restore_models_btn.clicked.connect(self.on_restore_models_only)
        model_btns_layout.addWidget(restore_models_btn)
        
        self.advanced_fallback_cb = QCheckBox("Enable Advanced Fallback Priority (Global List)")
        self.advanced_fallback_cb.setToolTip("If checked, the system uses the global priority list rather than the standard nested model fallback rules.")
        self.advanced_fallback_cb.stateChanged.connect(self.update_fallback_ui_states)
        model_main_layout.addWidget(self.advanced_fallback_cb)

        # Visible mode indicator so it's always clear which fallback mode is active
        # (advanced global list vs standard per-provider nested fallbacks). Text,
        # color, and highlight all update in update_fallback_ui_states().
        self.fallback_mode_label = QLabel()
        self.fallback_mode_label.setWordWrap(True)
        self.fallback_mode_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        model_main_layout.addWidget(self.fallback_mode_label)

        self.advanced_fallback_btn = QPushButton("Advanced Fallback Priority...")
        self.advanced_fallback_btn.setToolTip("Configure a global priority list to mix-and-match model fallbacks across different providers.")
        self.advanced_fallback_btn.clicked.connect(self.on_advanced_fallback_clicked)
        model_btns_layout.addWidget(self.advanced_fallback_btn)
        
        self.rank_checked_first_btn = QPushButton("Rank Checked First")
        self.rank_checked_first_btn.setToolTip("Move all checked/enabled providers to the top of the list, preserving their relative order.")
        self.rank_checked_first_btn.clicked.connect(self.rank_checked_providers_first)
        model_btns_layout.addWidget(self.rank_checked_first_btn)
        
        model_main_layout.addLayout(model_btns_layout)
        
        self.models_layout = QVBoxLayout()
        model_main_layout.addLayout(self.models_layout)
        
        # Add Custom Provider button
        add_layout = QHBoxLayout()
        add_layout.addStretch()
        self.add_custom_provider_btn = QPushButton("+ Custom Provider")
        self.add_custom_provider_btn.setToolTip("Add a new custom provider.")
        self.add_custom_provider_btn.clicked.connect(self.on_add_custom_provider)
        add_layout.addWidget(self.add_custom_provider_btn)
        model_main_layout.addLayout(add_layout)

        model_group.setLayout(model_main_layout)
        self.prov_layout.addRow(model_group)
        
        # Model Testing Prompt Settings Group
        testing_group = QGroupBox("Model Testing Prompt Settings")
        testing_layout = QFormLayout()
        
        self.test_question_edit = QLineEdit()
        self.test_question_edit.setToolTip("Customize the question (Front) used when running tests on models.")
        
        self.test_answer_edit = QLineEdit()
        self.test_answer_edit.setToolTip("Customize the expected answer (Back) used when running tests on models.")
        
        reset_test_prompt_btn = QPushButton("Reset to Default")
        reset_test_prompt_btn.setToolTip("Reset the test question and answer to default challenging values.")
        reset_test_prompt_btn.clicked.connect(self.on_reset_test_prompt)
        
        testing_layout.addRow("Test Question (Front):", self.test_question_edit)
        testing_layout.addRow("Test Answer (Back):", self.test_answer_edit)
        testing_layout.addRow("", reset_test_prompt_btn)
        
        testing_group.setLayout(testing_layout)
        self.prov_layout.addRow(testing_group)
        
        prov_scroll.setWidget(prov_content)
        prov_main_layout.addWidget(prov_scroll)
        
        self.providers_tab.setLayout(prov_main_layout)
        return self.providers_tab
