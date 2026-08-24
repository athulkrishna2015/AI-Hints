import json
import os
from aqt import mw
from aqt.qt import *
from ..logger import info, tooltip
from ..ai_client import DEFAULT_MODELS, MODEL_SUGGESTIONS, MODEL_FALLBACKS, PROVIDER_ORDER
from ..ai_client import is_model_blacklisted, is_model_deprecated
from .widgets import CustomProviderDialog, ProviderRowWidget, PERSISTENT_TEST_STATUSES, FETCH_CANCELLATIONS, NEWLY_ADDED_MODELS, MISSING_FROM_FETCH

DEFAULT_TEST_QUESTION = "Why does a rotating magnet fall slower through a copper tube than a non-magnetic mass of the same size?"
DEFAULT_TEST_ANSWER = "Due to Faraday's law of induction and Lenz's law, the falling magnet induces eddy currents in the copper tube, creating an opposing magnetic field that exerts an upward electromagnetic braking force."

TEST_CANCELLATIONS = {}

# Highlight colours for newly added vs missing vs deprecated models in fallback lists.
# Kept as hex strings and resolved lazily so imports stay safe in headless tests.
COL_NEW_BG = "#d9f2cd"
COL_NEW_FG = "#1e7e34"
COL_MISSING_BG = "#fff0c8"
COL_MISSING_FG = "#8a6d1a"
COL_DEP_BG = "#ffe1e1"
COL_DEP_FG = "#b71c1c"

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


class FallbackOrderDialog(QDialog):
    def __init__(self, parent, provider, active_model, current_list, suggestions):
        super().__init__(parent)
        self.main_dialog = parent
        self.provider = provider
        self.active_model = active_model
        
        self.setWindowTitle(f"Fallback Priority: {provider.capitalize()}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Configure the list of models to try if the primary model fails.<br/>"
            "The first model in the list is the Active Model. Use the buttons below to reorder."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search models...")
        self.search_edit.textChanged.connect(self.filter_models)
        layout.addWidget(self.search_edit)

        # Use QTableWidget: [Model Name] [Thinking Level] [Timeout]
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Model Name", "Thinking Level", "Timeout (s)"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 100)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setStyleSheet("""
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background-color: rgba(0, 140, 186, 0.1); color: black; }
        """)

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
        
        # Build the initial list: active model first, then the remaining fallbacks
        full_list = []
        if active_model:
            full_list.append(active_model)
        for m in current_list:
            if m != active_model:
                full_list.append(m)
        
        # Batch-populate large lists (e.g. 400+ OpenRouter models): plain items
        # are cheap; per-row widgets are materialized on demand.
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(full_list))
            for i, m in enumerate(full_list):
                self._add_model_row(m, m not in disabled_models, row=i)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

        # Materialize the first screenful immediately so the dialog never opens
        # with empty cells; further rows load as the user scrolls.
        self._ensure_visible_widgets()
        self.table.verticalScrollBar().valueChanged.connect(self._ensure_visible_widgets)
        self.table.viewport().installEventFilter(self)
            
        layout.addWidget(self.table)
        
        # Action buttons (stacked in 2 rows to prevent overflow)
        btn_layout = QVBoxLayout()
        
        row1_layout = QHBoxLayout()
        self.up_btn = QPushButton("Move Up")
        self.up_btn.clicked.connect(lambda: self.move_item(-1))
        self.down_btn = QPushButton("Move Down")
        self.down_btn.clicked.connect(lambda: self.move_item(1))
        self.set_active_btn = QPushButton("Set Active")
        self.set_active_btn.setToolTip("Set the selected model as the primary active model (moves it to the top).")
        self.set_active_btn.clicked.connect(self.set_selected_as_active)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Remove models from the list. Choose which type to remove from the dropdown.")
        self.remove_btn.setMenu(self._build_remove_menu(self.remove_models))
        
        row1_layout.addWidget(self.up_btn)
        row1_layout.addWidget(self.down_btn)
        row1_layout.addWidget(self.set_active_btn)
        row1_layout.addWidget(self.remove_btn)
        
        row2_layout = QHBoxLayout()
        self.list_test_btn = QPushButton("Test")
        self.list_test_btn.setToolTip("Test models from the list. Choose which mode from the dropdown.")
        self.list_test_btn.setMenu(self._build_test_menu(self.on_test_from_list))
        self.sort_selected_btn = QPushButton("Rank Checked First")
        self.sort_selected_btn.clicked.connect(self.rank_selected_first)
        
        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setToolTip("Fetch available models from this provider's API.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_from_list)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset the list back to code defaults.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        row2_layout.addWidget(self.list_test_btn)
        row2_layout.addWidget(self.sort_selected_btn)
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

    def _add_model_row(self, model_name, checked, row=None):
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
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
        self.table.setItem(row, 0, item)

    # ---- Lazy cell-widget materialization ----------------------------------
    # Creating a QComboBox + QSpinBox for every row made dialogs with hundreds
    # of models (OpenRouter) take seconds to open. Widgets are now created only
    # for rows near the visible viewport; the name-keyed dicts hold the
    # authoritative values and are harvested back before any structural or
    # read operation.

    def _materialize_row_widgets(self, row):
        if self.table.cellWidget(row, 1) is not None:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)

        combo = QComboBox()
        combo.addItems(["off", "low", "medium", "high"])
        combo.setCurrentText(self._thinking_levels.get(name, "off"))
        self.table.setCellWidget(row, 1, combo)

        spin = QSpinBox()
        spin.setRange(0, 300)
        spin.setSuffix(" s")
        spin.setToolTip("Request timeout in seconds. 0 = use provider/global timeout.")
        spin.setValue(self._model_timeouts.get(name, 0))
        self.table.setCellWidget(row, 2, spin)

    def _visible_row_range(self):
        count = self.table.rowCount()
        if count == 0:
            return 0, -1
        first = self.table.rowAt(0)
        if first < 0:
            first = 0
        viewport_h = max(1, self.table.viewport().height())
        last = self.table.rowAt(viewport_h - 2)
        if last < first:
            row_h = max(1, self.table.rowHeight(first))
            last = min(count - 1, first + (viewport_h // row_h))
        return first, min(count - 1, last)

    def _ensure_visible_widgets(self):
        first, last = self._visible_row_range()
        if last < first:
            return
        margin = 15  # pre-build a few screens' worth while scrolling
        lo = max(0, first - margin)
        hi = min(self.table.rowCount() - 1, last + margin)
        updates = self.table.updatesEnabled()
        if updates:
            self.table.setUpdatesEnabled(False)
        try:
            for i in range(lo, hi + 1):
                if not self.table.isRowHidden(i):
                    self._materialize_row_widgets(i)
        finally:
            if updates:
                self.table.setUpdatesEnabled(True)

    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() in (
            QEvent.Type.Show,
            QEvent.Type.Resize,
        ):
            self._ensure_visible_widgets()
        return super().eventFilter(obj, event)

    def _harvest_widgets(self):
        """Copy current combo/spin values back into the authoritative dicts."""
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if not item:
                continue
            name = item.data(Qt.ItemDataRole.UserRole)
            if not name:
                continue
            combo = self.table.cellWidget(i, 1)
            if combo is not None:
                self._thinking_levels[name] = combo.currentText()
            spin = self.table.cellWidget(i, 2)
            if spin is not None:
                self._model_timeouts[name] = spin.value()

    def _refresh_row_widgets(self, row):
        """Re-sync an existing row's widgets with its (possibly swapped) model."""
        item = self.table.item(row, 0)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        combo = self.table.cellWidget(row, 1)
        if combo is not None:
            combo.setCurrentText(self._thinking_levels.get(name, "off"))
        spin = self.table.cellWidget(row, 2)
        if spin is not None:
            spin.setValue(self._model_timeouts.get(name, 0))

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
                        existing = [self.table.item(j, 0).data(Qt.ItemDataRole.UserRole) for j in range(self.table.rowCount()) if self.table.item(j, 0)]
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
                                self._add_model_row(m, False)
                                added_count += 1
                        
                        self.update_item_labels()
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

    def filter_models(self, text):
        query = text.strip().casefold()
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                model = item.data(Qt.ItemDataRole.UserRole) or ""
                self.table.setRowHidden(i, bool(query and query not in model.casefold()))
        self._ensure_visible_widgets()

    def _rebuild_rows(self, model_data):
        """Replace the whole table contents from a list of _row_data dicts."""
        self._harvest_widgets()
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(model_data))
            for i, d in enumerate(model_data):
                self._add_model_row(d["name"], d["checked"], row=i)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        self.update_item_labels()
        self._ensure_visible_widgets()

    def rank_selected_first(self):
        rows = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                rows.append((i, item.checkState() == Qt.CheckState.Checked))
        rows.sort(key=lambda x: not x[1])
        # Rebuild table in sorted order
        self._rebuild_rows([self._row_data(old_row) for old_row, _ in rows])

    def on_test_from_list(self, mode="all"):
        test_key = f"{self.provider}_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True
            self.list_test_btn.setText("Test")
            tooltip("Testing cancelled.")
            return

        TEST_CANCELLATIONS[test_key] = False
        self.list_test_btn.setText("Stop Test")
        self.restore_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        
        # Collect models based on mode
        models = []
        model_indices = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if not item:
                continue
            model_name = item.data(Qt.ItemDataRole.UserRole)
            if mode == "all":
                models.append(model_name)
                model_indices.append(i)
            elif mode == "checked" and item.checkState() == Qt.CheckState.Checked:
                models.append(model_name)
                model_indices.append(i)
            elif mode == "row" and self.table.item(i, 0) and self.table.item(i, 0).isSelected():
                models.append(model_name)
                model_indices.append(i)
        
        if not models:
            tooltip("No models match the selected test mode.")
            self._test_done(test_key)
            return
        
        import threading
        from ..ai_client import AIClient
        
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            for idx, (model, row_idx) in enumerate(zip(models, model_indices)):
                if TEST_CANCELLATIONS.get(test_key):
                    break
                # Update item state to Testing
                def _update_testing(r=row_idx, name=model):
                    item = self.table.item(r, 0)
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
                        temp_config["local_endpoint"] = {
                            "base_url": self.main_dialog.local_url_edit.text().strip() or "http://localhost:11434/v1",
                            "api_key": self.main_dialog.local_api_key_edit.text().strip(),
                            "model": model
                        }
                    client = AIClient(temp_config)
                    test_front = self.main_dialog.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION
                    test_back = self.main_dialog.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER
                    if TEST_CANCELLATIONS.get(test_key):
                        break
                    res = client.generate_options(test_front, test_back, override_provider=self.provider, only_this_provider=True)
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
                def _update_result(r=row_idx, name=model, st=status, tt=tooltip_text):
                    item = self.table.item(r, 0)
                    if item:
                        item.setText(f"{name} ({st})")
                        item.setToolTip(tt)
                        fallback_statuses = PERSISTENT_TEST_STATUSES.setdefault(f"{self.provider}_fallback_statuses", {})
                        fallback_statuses[name] = st
                        fallback_tooltips = PERSISTENT_TEST_STATUSES.setdefault(f"{self.provider}_fallback_tooltips", {})
                        fallback_tooltips[name] = tt
                mw.taskman.run_on_main(_update_result)
                
            self._test_done(test_key)
            
        threading.Thread(target=_runner, daemon=True).start()

    def _test_done(self, test_key):
        def _done():
            self.list_test_btn.setText("Test")
            self.restore_btn.setEnabled(True)
            self.up_btn.setEnabled(True)
            self.down_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
            if test_key in TEST_CANCELLATIONS:
                del TEST_CANCELLATIONS[test_key]
        mw.taskman.run_on_main(_done)

    def on_item_changed(self, item):
        if self.table.row(item) == 0 and item.checkState() == Qt.CheckState.Unchecked:
            next_checked_idx = -1
            for idx in range(1, self.table.rowCount()):
                other = self.table.item(idx, 0)
                if other and other.checkState() == Qt.CheckState.Checked:
                    next_checked_idx = idx
                    break
            
            self.table.blockSignals(True)
            try:
                if next_checked_idx != -1:
                    self._swap_rows(next_checked_idx, 0)
                    self.table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
                    tooltip("Promoted next checked model to Active.")
                else:
                    item.setCheckState(Qt.CheckState.Checked)
                    tooltip("Cannot uncheck the active model when no other checked models are available.")
            finally:
                self.table.blockSignals(False)
            self.update_item_labels()

    def _swap_rows(self, a, b):
        """Swap two rows in the table; widgets (if any) follow their new model."""
        self._harvest_widgets()
        item_a = self.table.takeItem(a, 0)
        item_b = self.table.takeItem(b, 0)
        self.table.setItem(a, 0, item_b)
        self.table.setItem(b, 0, item_a)
        self._refresh_row_widgets(a)
        self._refresh_row_widgets(b)

    def _row_data(self, row):
        item = self.table.item(row, 0)
        name = item.data(Qt.ItemDataRole.UserRole) if item else ""
        return {
            "name": name,
            "checked": item.checkState() == Qt.CheckState.Checked if item else True,
            "think": self._thinking_levels.get(name, "off"),
            "timeout": self._model_timeouts.get(name, 0),
        }

    def update_item_labels(self, *args):
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            fallback_statuses = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_statuses", {})
            fallback_tooltips = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_tooltips", {})
            for i in range(self.table.rowCount()):
                item = self.table.item(i, 0)
                if not item: continue
                m = item.data(Qt.ItemDataRole.UserRole)
                status = fallback_statuses.get(m)
                bl = " | 🚫 Blacklisted" if is_model_blacklisted(self.provider, m, getattr(self.main_dialog, "config", None)) else ""
                status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
                
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
                else:
                    item.setToolTip("" if not bl else "This model is currently on cooldown due to recent failures.")
                
                new_mark = "🆕 " if is_new else ""
                dep_mark = " | ⚠️ Deprecated" if is_dep else ""
                missing_mark = " | ⚠️ No Longer Returned" if (is_missing and not is_dep) else ""
                if i == 0:
                    item.setCheckState(Qt.CheckState.Checked)
                    item.setText(f"⭐ {new_mark}{m} (Active){status_suffix}{dep_mark}{missing_mark}")
                else:
                    item.setText(f"{new_mark}{m}{status_suffix}{dep_mark}{missing_mark}")
                self._apply_model_highlight(item, m)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)

    def set_selected_as_active(self):
        row = self.table.currentRow()
        if row > 0:
            self._swap_rows(row, 0)
            self.table.setCurrentCell(0, 0)
            self.update_item_labels()

    def move_item(self, delta):
        curr_row = self.table.currentRow()
        if curr_row == -1: return
        target_row = curr_row + delta
        if 0 <= target_row < self.table.rowCount():
            self._swap_rows(curr_row, target_row)
            self.table.setCurrentCell(target_row, 0)
            self.update_item_labels()

    @staticmethod
    def _build_remove_menu(callback):
        menu = QMenu()
        menu.addAction("Remove Selected", lambda: callback("selected"))
        menu.addAction("Remove Deprecated", lambda: callback("deprecated"))
        menu.addAction("Remove No Longer Returned", lambda: callback("missing"))
        menu.addAction("Remove Deprecated & No Longer Returned", lambda: callback("flagged"))
        return menu

    @staticmethod
    def _build_test_menu(callback):
        menu = QMenu()
        menu.addAction("Test Checked", lambda: callback("checked"))
        menu.addAction("Test Row", lambda: callback("row"))
        menu.addAction("Test All", lambda: callback("all"))
        return menu

    def _selected_rows(self):
        selected = {index.row() for index in self.table.selectionModel().selectedRows()}
        if not selected and self.table.currentRow() != -1:
            selected = {self.table.currentRow()}
        return sorted(selected)

    def _rows_matching(self, pred):
        rows = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and pred(item.data(Qt.ItemDataRole.UserRole)):
                rows.append(i)
        return rows

    def remove_models(self, kind):
        """Remove rows based on the requested removal type.

        kind in {"selected", "deprecated", "missing", "flagged"}.
        """
        if kind == "selected":
            to_remove = self._selected_rows()
            label = "selected"
        elif kind == "deprecated":
            to_remove = self._rows_matching(lambda m: is_model_deprecated(self.provider, m))
            label = "deprecated"
        elif kind == "missing":
            missing = MISSING_FROM_FETCH.get(self.provider, set())
            to_remove = self._rows_matching(lambda m: m in missing)
            label = "no-longer-returned"
        else:
            missing = MISSING_FROM_FETCH.get(self.provider, set())
            to_remove = self._rows_matching(
                lambda m: is_model_deprecated(self.provider, m) or m in missing)
            label = "deprecated/no-longer-returned"

        if not to_remove:
            tooltip(f"No {label} models found in the list.")
            return
        if len(to_remove) >= self.table.rowCount():
            tooltip("Cannot remove all models; at least one must remain in the list.")
            return
        removed = 0
        for i in reversed(to_remove):
            name = self.table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            self._thinking_levels.pop(name, None)
            self._model_timeouts.pop(name, None)
            self.table.removeRow(i)
            removed += 1
        self.update_item_labels()
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
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(full_list))
            for i, m in enumerate(full_list):
                self._add_model_row(m, True, row=i)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        self.update_item_labels()
        self._ensure_visible_widgets()

    def get_active_model(self):
        if self.table.rowCount() > 0:
            item = self.table.item(0, 0)
            if item:
                return item.data(Qt.ItemDataRole.UserRole)
        return ""

    def get_ordered_list(self):
        result = []
        for i in range(1, self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def get_disabled_list(self):
        disabled = []
        for i in range(1, self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.checkState() == Qt.CheckState.Unchecked:
                disabled.append(item.data(Qt.ItemDataRole.UserRole))
        return disabled

    def _current_model_names(self):
        return {
            self.table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            for i in range(self.table.rowCount())
            if self.table.item(i, 0)
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


class GlobalFallbackOrderDialog(QDialog):
    def __init__(self, parent, current_global_list):
        super().__init__(parent)
        self.main_dialog = parent
        
        self.setWindowTitle("Advanced Global Fallback Priority")
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Configure a global fallback sequence across all models and providers.<br/>"
            "If the primary active model fails, the system tries models sequentially from top to bottom.<br/>"
            "Drag & Drop to reorder, or use action buttons below."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search providers/models...")
        self.search_edit.textChanged.connect(self.filter_models)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDropIndicatorShown(True)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        self.tooltip_delegate = ToolTipDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self.tooltip_delegate)
        
        # Populate current list
        self.populate_list(current_global_list)
        layout.addWidget(self.list_widget)
        
        # Action buttons (stacked in 2 rows to prevent overflow)
        btn_layout = QVBoxLayout()
        
        row1_layout = QHBoxLayout()
        self.up_btn = QPushButton("Move Up")
        self.up_btn.clicked.connect(lambda: self.move_item(-1))
        self.down_btn = QPushButton("Move Down")
        self.down_btn.clicked.connect(lambda: self.move_item(1))
        self.add_btn = QPushButton("Add Model...")
        self.add_btn.clicked.connect(self.add_model_prompt)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Remove models from the list. Choose which type to remove from the dropdown.")
        self.remove_btn.setMenu(self._build_remove_menu(self.remove_models))
        
        row1_layout.addWidget(self.up_btn)
        row1_layout.addWidget(self.down_btn)
        row1_layout.addWidget(self.add_btn)
        row1_layout.addWidget(self.remove_btn)
        
        row2_layout = QHBoxLayout()
        self.list_test_btn = QPushButton("Test")
        self.list_test_btn.setToolTip("Test models from the list. Choose which mode from the dropdown.")
        self.list_test_btn.setMenu(self._build_test_menu(self.on_test_all))
        self.sort_selected_btn = QPushButton("Rank Selected First")
        self.sort_selected_btn.clicked.connect(self.rank_selected_first)
        
        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setToolTip("Fetch available models for all providers.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_all)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset global fallback priority to default provider-based models.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        row2_layout.addWidget(self.list_test_btn)
        row2_layout.addWidget(self.sort_selected_btn)
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

    def _provider_display(self, provider):
        if hasattr(self.main_dialog, "custom_providers_data") and provider in self.main_dialog.custom_providers_data:
            return provider
        return provider.capitalize()

    def populate_list(self, model_pairs):
        self.list_widget.clear()
        global_statuses = PERSISTENT_TEST_STATUSES.get("global_fallback_statuses", {})
        global_tooltips = PERSISTENT_TEST_STATUSES.get("global_fallback_tooltips", {})
        
        # Get currently disabled models map
        disabled_map = self.main_dialog.disabled_fallback_models_data if hasattr(self.main_dialog, "disabled_fallback_models_data") else {}

        self.list_widget.setUpdatesEnabled(False)
        try:
            for provider, model in model_pairs:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, (provider, model))
                status = global_statuses.get((provider, model))
                bl = " | 🚫 Blacklisted" if is_model_blacklisted(provider, model, getattr(self.main_dialog, "config", None)) else ""
                status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
                new_mark, dep_mark, missing_mark, is_new, is_dep, is_missing = self._global_marks(provider, model)
                item.setText(f"[{self._provider_display(provider)}] {new_mark}{model}{status_suffix}{dep_mark}{missing_mark}")
                self._apply_global_highlight(item, provider, model)
            
                # Make item checkable and ensure standard flags are set
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            
                # Set check state based on global disabled map
                provider_disabled = disabled_map.get(provider, [])
                item.setCheckState(Qt.CheckState.Unchecked if model in provider_disabled else Qt.CheckState.Checked)

                tt = global_tooltips.get((provider, model))
                if tt:
                    item.setToolTip(tt)
                elif is_dep:
                    item.setToolTip("⚠️ This model appears to be deprecated/retired. Consider removing it from the global list.")
                elif is_missing:
                    item.setToolTip("⚠️ The provider no longer returned this model in the latest fetch. It may be retired — consider removing it from the global list.")
                elif bl:
                    item.setToolTip("This model is currently on cooldown due to recent failures.")
                self.list_widget.addItem(item)
        finally:
            self.list_widget.setUpdatesEnabled(True)

    def _global_marks(self, provider, model):
        """Returns (new_mark, dep_mark, missing_mark, is_new, is_deprecated, is_missing)."""
        is_new = model in NEWLY_ADDED_MODELS.get(provider, ())
        is_dep = is_model_deprecated(provider, model)
        is_missing = model in MISSING_FROM_FETCH.get(provider, ())
        return ("🆕 " if is_new else "",
                " | ⚠️ Deprecated" if is_dep else "",
                " | ⚠️ No Longer Returned" if (is_missing and not is_dep) else "",
                is_new, is_dep, is_missing)

    def _apply_global_highlight(self, item, provider, model):
        _n, _d, _m, is_new, is_dep, is_missing = self._global_marks(provider, model)
        if is_dep:
            item.setBackground(QBrush(QColor(COL_DEP_BG)))
            item.setForeground(QBrush(QColor(COL_DEP_FG)))
        elif is_missing:
            item.setBackground(QBrush(QColor(COL_MISSING_BG)))
            item.setForeground(QBrush(QColor(COL_MISSING_FG)))
        elif is_new:
            item.setBackground(QBrush(QColor(COL_NEW_BG)))
            item.setForeground(QBrush(QColor(COL_NEW_FG)))

    def filter_models(self, text):
        query = text.strip().casefold()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            provider, model = item.data(Qt.ItemDataRole.UserRole)
            item.setHidden(bool(query and query not in f"{provider} {model}".casefold()))

    def rank_selected_first(self):
        items = [self.list_widget.takeItem(0) for _ in range(self.list_widget.count())]
        items.sort(key=lambda item: item.checkState() != Qt.CheckState.Checked)
        for item in items:
            self.list_widget.addItem(item)
            
    def refresh_statuses(self):
        """Updates the status suffixes (e.g. 'Working', 'Error') and tooltips without clearing the whole list."""
        global_statuses = PERSISTENT_TEST_STATUSES.get("global_fallback_statuses", {})
        global_tooltips = PERSISTENT_TEST_STATUSES.get("global_fallback_tooltips", {})
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            provider, model = item.data(Qt.ItemDataRole.UserRole)
            status = global_statuses.get((provider, model))
            bl = " | 🚫 Blacklisted" if is_model_blacklisted(provider, model, getattr(self.main_dialog, "config", None)) else ""
            status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
            new_mark, dep_mark, missing_mark, is_new, is_dep, is_missing = self._global_marks(provider, model)
            item.setText(f"[{self._provider_display(provider)}] {new_mark}{model}{status_suffix}{dep_mark}{missing_mark}")
            self._apply_global_highlight(item, provider, model)
            tt = global_tooltips.get((provider, model))
            if tt:
                item.setToolTip(tt)
            elif is_dep:
                item.setToolTip("⚠️ This model appears to be deprecated/retired. Consider removing it from the global list.")
            elif is_missing:
                item.setToolTip("⚠️ The provider no longer returned this model in the latest fetch. It may be retired — consider removing it from the global list.")
            elif bl:
                item.setToolTip("This model is currently on cooldown due to recent failures.")

    def add_model_prompt(self):
        providers = list(PROVIDER_ORDER) + list(self.main_dialog.custom_providers_data.keys())
        dlg = AddModelDialog(self, providers, DEFAULT_MODELS, MODEL_SUGGESTIONS, MODEL_FALLBACKS)
        if dlg.exec():
            provider, model = dlg.get_selection()
            if provider and model:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, (provider, model))
                item.setText(f"[{self._provider_display(provider)}] {model}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.list_widget.addItem(item)
                
    def move_item(self, delta):
        curr_row = self.list_widget.currentRow()
        if curr_row == -1: return
        target_row = curr_row + delta
        if 0 <= target_row < self.list_widget.count():
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(target_row, item)
            self.list_widget.setCurrentRow(target_row)
            
    def remove_models(self, kind):
        """Remove list rows based on the requested removal type.

        kind in {"selected", "deprecated", "missing", "flagged"}.
        """
        if kind == "selected":
            to_remove = [i for i in range(self.list_widget.count()) if self.list_widget.item(i).isSelected()]
            label = "selected"
        elif kind == "deprecated":
            to_remove = [
                i for i in range(self.list_widget.count())
                if is_model_deprecated(*self.list_widget.item(i).data(Qt.ItemDataRole.UserRole))
            ]
            label = "deprecated"
        elif kind == "missing":
            to_remove = [
                i for i in range(self.list_widget.count())
                if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)[1]
                in MISSING_FROM_FETCH.get(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)[0], set())
            ]
            label = "no-longer-returned"
        else:
            to_remove = []
            for i in range(self.list_widget.count()):
                provider, model = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                if is_model_deprecated(provider, model) or model in MISSING_FROM_FETCH.get(provider, set()):
                    to_remove.append(i)
            label = "deprecated/no-longer-returned"

        to_remove = sorted(set(to_remove), reverse=True)
        if not to_remove:
            tooltip(f"No {label} models found in the list.")
            return
        removed = 0
        for i in to_remove:
            self.list_widget.takeItem(i)
            removed += 1
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
        self.populate_list(defaults)
        
    def get_ordered_list(self):
        result = []
        for i in range(self.list_widget.count()):
            result.append(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole))
        return result

    def get_disabled_list(self):
        disabled = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Unchecked:
                disabled.append(item.data(Qt.ItemDataRole.UserRole))
        return disabled
        
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
                    
                    api_key = self.main_dialog.api_key_edits[provider].text().strip() if provider in self.main_dialog.api_key_edits else ""
                    temp_config = self.main_dialog.config.copy()
                    temp_config["local_providers"] = self.main_dialog.local_providers_data
                    # Always include current custom_providers so fetch_models has URLs/keys
                    if hasattr(self.main_dialog, "custom_providers_data"):
                        temp_config["custom_providers"] = self.main_dialog.custom_providers_data
                    if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                    temp_config["api_keys"][provider] = api_key
                    if provider == "local":
                        temp_config["local_endpoint"] = {
                            "base_url": self.main_dialog.local_url_edit.text().strip() or "http://localhost:11434/v1",
                            "api_key": self.main_dialog.local_api_key_edit.text().strip()
                        }

                    client = AIClient(temp_config)
                    models = client.fetch_models(provider)
                    
                    if FETCH_CANCELLATIONS.get(fetch_key):
                        break
                        
                    if models:
                        def _update_ui(p=provider, ms=models):
                            existing = [self.list_widget.item(j).data(Qt.ItemDataRole.UserRole) for j in range(self.list_widget.count())]
                            existing_set = set(existing)
                            
                            added_count = 0
                            newly = NEWLY_ADDED_MODELS.setdefault(p, set())
                            for m in sorted(list(set(ms))):
                                if m and (p, m) not in existing_set:
                                    newly.add(m)
                                    item = QListWidgetItem()
                                    item.setData(Qt.ItemDataRole.UserRole, (p, m))
                                    item.setText(f"[{self._provider_display(p)}] {m}")
                                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                                    item.setCheckState(Qt.CheckState.Unchecked)
                                    self.list_widget.addItem(item)
                                    added_count += 1
                            
                            fetched_set = set(ms)
                            missed = {m for (pr, m) in existing if pr == p and m not in fetched_set}
                            if missed:
                                MISSING_FROM_FETCH[p] = missed
                            
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

        TEST_CANCELLATIONS[test_key] = False
        self.list_test_btn.setText("Stop Test")
        self.restore_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        
        def _test_includes(i):
            item = self.list_widget.item(i)
            if mode == "row":
                return item.isSelected()
            if mode == "checked":
                return item.checkState() == Qt.CheckState.Checked
            return True

        items_data = [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
            if _test_includes(i)
        ]
        
        import threading
        from ..ai_client import AIClient
        
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            
            for i, (provider, model) in enumerate(items_data):
                if TEST_CANCELLATIONS.get(test_key):
                    break
                def _update_testing(idx=i, prov=provider, name=model):
                    item = self.list_widget.item(idx)
                    if item:
                        item.setText(f"[{self._provider_display(prov)}] {name} (⏳ Testing...)")
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
                        temp_config["local_endpoint"] = {
                            "base_url": self.main_dialog.local_url_edit.text().strip() or "http://localhost:11434/v1",
                            "api_key": self.main_dialog.local_api_key_edit.text().strip(),
                            "model": model
                        }
                    client = AIClient(temp_config)
                    test_front = self.main_dialog.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION
                    test_back = self.main_dialog.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER
                    if TEST_CANCELLATIONS.get(test_key):
                        break
                    res = client.generate_options(test_front, test_back, override_provider=provider, only_this_provider=True)
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

                def _update_result(idx=i, prov=provider, name=model, st=status, tt=tooltip_text):
                    item = self.list_widget.item(idx)
                    if item:
                        item.setText(f"[{self._provider_display(prov)}] {name} ({st})")
                        item.setToolTip(tt)
                        global_statuses = PERSISTENT_TEST_STATUSES.setdefault("global_fallback_statuses", {})
                        global_statuses[(prov, name)] = st
                        global_tooltips = PERSISTENT_TEST_STATUSES.setdefault("global_fallback_tooltips", {})
                        global_tooltips[(prov, name)] = tt
                mw.taskman.run_on_main(_update_result)
                
            def _done():
                self.list_test_btn.setText("Test")
                self.restore_btn.setEnabled(True)
                self.up_btn.setEnabled(True)
                self.down_btn.setEnabled(True)
                self.remove_btn.setEnabled(True)
                self.add_btn.setEnabled(True)
                if test_key in TEST_CANCELLATIONS:
                    del TEST_CANCELLATIONS[test_key]
            mw.taskman.run_on_main(_done)
            
        threading.Thread(target=_runner, daemon=True).start()


class ProvidersTabMixin:
    def update_fallback_ui_states(self):
        if not hasattr(self, "advanced_fallback_cb"):
            return
        use_global = self.advanced_fallback_cb.isChecked()
        self.advanced_fallback_btn.setEnabled(use_global)
        
        # 1. Disable reordering and fallback configurations on standard provider rows
        if hasattr(self, 'models_layout') and self.models_layout is not None:
            from .widgets import ProviderRowWidget
            for i in range(self.models_layout.count()):
                item = self.models_layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if isinstance(w, ProviderRowWidget):
                    w.up_btn.setEnabled(not use_global)
                    w.down_btn.setEnabled(not use_global)
                    w.enabled_cb.setEnabled(not use_global)
                    w.fallbacks_btn.setEnabled(not use_global)
                    
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

    def on_advanced_fallback_clicked(self):
        if not hasattr(self, "global_model_priority_data"):
            self.global_model_priority_data = self.config.get("global_model_priority", [])
        
        current_list = []
        for item in self.global_model_priority_data:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                current_list.append((item[0], item[1]))

        dlg = GlobalFallbackOrderDialog(self, current_list)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.global_fallback_dlg = dlg
        try:
            if dlg.exec():
                self.global_model_priority_data = dlg.get_ordered_list()
                
                # Sync disabled fallback models based on checkbox states in the dialog
                if not hasattr(self, "disabled_fallback_models_data"):
                    self.disabled_fallback_models_data = self.config.get("disabled_fallback_models", {})

                for i in range(dlg.list_widget.count()):
                    item = dlg.list_widget.item(i)
                    provider, model = item.data(Qt.ItemDataRole.UserRole)
                    is_disabled = (item.checkState() == Qt.CheckState.Unchecked)
                    
                    if provider not in self.disabled_fallback_models_data:
                        self.disabled_fallback_models_data[provider] = []
                    
                    current_disabled = self.disabled_fallback_models_data[provider]
                    if is_disabled:
                        if model not in current_disabled:
                            current_disabled.append(model)
                    else:
                        if model in current_disabled:
                            while model in current_disabled:
                                current_disabled.remove(model)
                
                tooltip("Advanced fallback priority and disabled states updated. Click Save to apply.")
        finally:
            self.global_fallback_dlg = None

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
        self.ag_model_edit = QComboBox()
        self.ag_enable_cb = QCheckBox()
        self.ag_status_label = QLabel()
        self.ag_path_label = QLabel()
        self.ag_fetch_btn = QPushButton()
        self.ag_dashboard_btn = QPushButton()
        self.ag_delete_btn = QPushButton()
        self.ag_dl_progress = QProgressBar()
        self.ag_dl_status = QLabel()

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

        self.advanced_fallback_btn = QPushButton("Advanced Fallback Priority...")
        self.advanced_fallback_btn.setToolTip("Configure a global priority list to mix-and-match model fallbacks across different providers.")
        self.advanced_fallback_btn.clicked.connect(self.on_advanced_fallback_clicked)
        model_btns_layout.addWidget(self.advanced_fallback_btn)
        
        model_main_layout.addLayout(model_btns_layout)
        
        self.models_layout = QVBoxLayout()
        model_main_layout.addLayout(self.models_layout)

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
