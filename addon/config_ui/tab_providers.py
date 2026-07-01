import os
from aqt import mw
from aqt.qt import *
from ..logger import info, tooltip
from ..ai_client import DEFAULT_MODELS, MODEL_SUGGESTIONS, MODEL_FALLBACKS, PROVIDER_ORDER
from ..ai_client import is_model_blacklisted
from .widgets import ProviderRowWidget, PERSISTENT_TEST_STATUSES, FETCH_CANCELLATIONS

DEFAULT_TEST_QUESTION = "Why does a rotating magnet fall slower through a copper tube than a non-magnetic mass of the same size?"
DEFAULT_TEST_ANSWER = "Due to Faraday's law of induction and Lenz's law, the falling magnet induces eddy currents in the copper tube, creating an opposing magnetic field that exerts an upward electromagnetic braking force."

TEST_CANCELLATIONS = {}

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
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Configure the list of models to try if the primary model fails.<br/>"
            "The first model in the list is the Active Model. Drag & Drop to reorder, or uncheck to temporarily disable a fallback model."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        self.list_widget = QListWidget()
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDropIndicatorShown(True)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        # Add a styled item delegate for better spacing and to prevent tooltip overlap
        self.list_widget.setStyleSheet("""
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            }
            QListWidget::item:selected {
                background-color: rgba(0, 140, 186, 0.1);
                color: black;
            }
        """)

        self.tooltip_delegate = ToolTipDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self.tooltip_delegate)
        
        # Connect internal drag/drop layout changes and checkState changes to label/active state updaters
        self.list_widget.model().layoutChanged.connect(self.update_item_labels)
        self.list_widget.model().rowsMoved.connect(self.update_item_labels)
        self.list_widget.itemChanged.connect(self.on_item_changed)
        
        disabled_models = getattr(parent, "disabled_fallback_models_data", {}).get(provider, [])
        fallback_statuses = PERSISTENT_TEST_STATUSES.get(f"{provider}_fallback_statuses", {})
        
        # Build the initial list: active model first, then the remaining fallbacks
        full_list = []
        if active_model:
            full_list.append(active_model)
        for m in current_list:
            if m != active_model:
                full_list.append(m)
                
        for m in full_list:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, m)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if m in disabled_models else Qt.CheckState.Checked)
            # Show blacklist badge immediately on open
            bl = " | 🚫 Blacklisted" if is_model_blacklisted(provider, m) else ""
            status = fallback_statuses.get(m)
            status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
            item.setText(m + status_suffix)
            self.list_widget.addItem(item)
            
        layout.addWidget(self.list_widget)
        
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
        self.remove_btn.clicked.connect(self.remove_item)
        
        row1_layout.addWidget(self.up_btn)
        row1_layout.addWidget(self.down_btn)
        row1_layout.addWidget(self.set_active_btn)
        row1_layout.addWidget(self.remove_btn)
        
        row2_layout = QHBoxLayout()
        self.list_test_btn = QPushButton("Test All")
        self.list_test_btn.setToolTip("Test all models in the list sequentially.")
        self.list_test_btn.clicked.connect(self.on_test_from_list)
        
        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setToolTip("Fetch available models from this provider's API.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_from_list)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset the list back to code defaults.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        row2_layout.addWidget(self.list_test_btn)
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
        if not api_key and self.provider not in ["local"]:
            info(f"Please enter an API key for {self.provider.capitalize()} first.")
            self.list_fetch_btn.setText("Fetch All")
            self.list_test_btn.setEnabled(True)
            self.restore_btn.setEnabled(True)
            del FETCH_CANCELLATIONS[fetch_key]
            return
            
        temp_config = self.main_dialog.config.copy()
        if "api_keys" not in temp_config: temp_config["api_keys"] = {}
        temp_config["api_keys"][self.provider] = api_key
        if self.provider == "local":
            temp_config["local_endpoint"] = {
                "base_url": self.main_dialog.local_url_edit.text().strip() or "http://localhost:11434/v1",
                "api_key": self.main_dialog.local_api_key_edit.text().strip()
            }
            
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
                        # Get existing model names in the list widget
                        existing = [self.list_widget.item(j).data(Qt.ItemDataRole.UserRole) for j in range(self.list_widget.count())]
                        existing_set = set(existing)
                        
                        added_count = 0
                        fallback_statuses = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_statuses", {})
                        for m in models_clean:
                            if m and m not in existing_set:
                                item = QListWidgetItem()
                                item.setData(Qt.ItemDataRole.UserRole, m)
                                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                                # Unchecked by default
                                item.setCheckState(Qt.CheckState.Unchecked)
                                status = fallback_statuses.get(m)
                                if status:
                                    item.setText(f"{m} ({status})")
                                else:
                                    item.setText(m)
                                self.list_widget.addItem(item)
                                added_count += 1
                                
                        tooltip(f"Fetched {len(models_clean)} models ({added_count} new added).")
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

    def on_test_from_list(self):
        test_key = f"{self.provider}_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True
            self.list_test_btn.setText("Test All")
            tooltip("Testing cancelled.")
            return

        TEST_CANCELLATIONS[test_key] = False
        self.list_test_btn.setText("Stop Test All")
        self.restore_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        
        # Collect all models from items
        models = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_widget.count())]
        
        import threading
        from ..ai_client import AIClient
        
        def _runner():
            from ..logger import log_context
            log_context.source = "model_test"
            for i, model in enumerate(models):
                if TEST_CANCELLATIONS.get(test_key):
                    break
                # Update item state to Testing
                def _update_testing(idx=i, name=model):
                    item = self.list_widget.item(idx)
                    if item:
                        item.setText(f"{name} (⏳ Testing...)")
                mw.taskman.run_on_main(_update_testing)
                
                status = "✅ Working"
                try:
                    # Prepare temporary config for this model
                    temp_config = self.main_dialog.config.copy()
                    api_key = self.main_dialog.api_key_edits[self.provider].text().strip() if self.provider in self.main_dialog.api_key_edits else ""
                    if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                    temp_config["api_keys"][self.provider] = api_key
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
                        tooltip_text = f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/>The provider returned an empty response.</div>"
                    else:
                        import json
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
                    status = "❌ Error"
                    error_msg = str(e)
                    tooltip_text = f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/><b>Error:</b> {error_msg}</div>"
                
                if TEST_CANCELLATIONS.get(test_key):
                    break

                # Update item state to result
                def _update_result(idx=i, name=model, st=status, tt=tooltip_text):
                    item = self.list_widget.item(idx)
                    if item:
                        item.setText(f"{name} ({st})")
                        item.setToolTip(tt)
                        # Save to persistent statuses
                        fallback_statuses = PERSISTENT_TEST_STATUSES.setdefault(f"{self.provider}_fallback_statuses", {})
                        fallback_statuses[name] = st
                        fallback_tooltips = PERSISTENT_TEST_STATUSES.setdefault(f"{self.provider}_fallback_tooltips", {})
                        fallback_tooltips[name] = tt
                mw.taskman.run_on_main(_update_result)
                
            def _done():
                self.list_test_btn.setText("Test All")
                self.restore_btn.setEnabled(True)
                self.up_btn.setEnabled(True)
                self.down_btn.setEnabled(True)
                self.remove_btn.setEnabled(True)
                if test_key in TEST_CANCELLATIONS:
                    del TEST_CANCELLATIONS[test_key]
            mw.taskman.run_on_main(_done)
            
        threading.Thread(target=_runner, daemon=True).start()

    def on_item_changed(self, item):
        if self.list_widget.row(item) == 0 and item.checkState() == Qt.CheckState.Unchecked:
            # Find the next checked model in the list
            next_checked_idx = -1
            for idx in range(1, self.list_widget.count()):
                if self.list_widget.item(idx).checkState() == Qt.CheckState.Checked:
                    next_checked_idx = idx
                    break
            
            self.list_widget.blockSignals(True)
            self.list_widget.model().blockSignals(True)
            try:
                if next_checked_idx != -1:
                    # Take the newly promoted model
                    promoted_item = self.list_widget.takeItem(next_checked_idx)
                    # Insert it at index 0 (shifts old active model to index 1)
                    self.list_widget.insertItem(0, promoted_item)
                    # Uncheck the old active model (now at index 1)
                    self.list_widget.item(1).setCheckState(Qt.CheckState.Unchecked)
                    tooltip("Promoted next checked model to Active.")
                else:
                    # Force it back to checked
                    item.setCheckState(Qt.CheckState.Checked)
                    tooltip("Cannot uncheck the active model when no other checked models are available.")
            finally:
                self.list_widget.model().blockSignals(False)
                self.list_widget.blockSignals(False)
            self.update_item_labels()

    def update_item_labels(self, *args):
        self.list_widget.blockSignals(True)
        self.list_widget.model().blockSignals(True)
        try:
            fallback_statuses = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_statuses", {})
            fallback_tooltips = PERSISTENT_TEST_STATUSES.get(f"{self.provider}_fallback_tooltips", {})
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                m = item.data(Qt.ItemDataRole.UserRole)
                status = fallback_statuses.get(m)
                bl = " | 🚫 Blacklisted" if is_model_blacklisted(self.provider, m) else ""
                status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
                
                # Update tooltip if we have a saved response
                tt = fallback_tooltips.get(m) if fallback_tooltips else None
                if tt:
                    item.setToolTip(tt)
                else:
                    item.setToolTip("" if not bl else "This model is currently on cooldown due to recent failures.")
                
                if i == 0:
                    item.setCheckState(Qt.CheckState.Checked)
                    item.setText(f"⭐ {m} (Active){status_suffix}")
                else:
                    item.setText(f"{m}{status_suffix}")
        finally:
            self.list_widget.model().blockSignals(False)
            self.list_widget.blockSignals(False)

    def set_selected_as_active(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(0, item)
            self.list_widget.setCurrentRow(0)
            self.update_item_labels()

    def move_item(self, delta):
        curr_row = self.list_widget.currentRow()
        if curr_row == -1: return
        target_row = curr_row + delta
        if 0 <= target_row < self.list_widget.count():
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(target_row, item)
            self.list_widget.setCurrentRow(target_row)
            self.update_item_labels()

    def remove_item(self):
        curr_row = self.list_widget.currentRow()
        if curr_row != -1:
            if self.list_widget.count() <= 1:
                tooltip("Cannot remove the only model.")
                return
            self.list_widget.takeItem(curr_row)
            self.update_item_labels()

    def restore_defaults(self):
        self.list_widget.clear()
        defaults = MODEL_FALLBACKS.get(self.provider, [])
        full_list = []
        if self.active_model:
            full_list.append(self.active_model)
        for m in defaults:
            if m != self.active_model:
                full_list.append(m)
        for m in full_list:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, m)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        self.update_item_labels()

    def get_active_model(self):
        if self.list_widget.count() > 0:
            return self.list_widget.item(0).data(Qt.ItemDataRole.UserRole)
        return ""

    def get_ordered_list(self):
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(1, self.list_widget.count())]

    def get_disabled_list(self):
        disabled = []
        for i in range(1, self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Unchecked:
                disabled.append(item.data(Qt.ItemDataRole.UserRole))
        return disabled


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
        self.remove_btn.clicked.connect(self.remove_item)
        
        row1_layout.addWidget(self.up_btn)
        row1_layout.addWidget(self.down_btn)
        row1_layout.addWidget(self.add_btn)
        row1_layout.addWidget(self.remove_btn)
        
        row2_layout = QHBoxLayout()
        self.list_test_btn = QPushButton("Test All")
        self.list_test_btn.setToolTip("Test all global models sequentially.")
        self.list_test_btn.clicked.connect(self.on_test_all)
        
        self.list_fetch_btn = QPushButton("Fetch All")
        self.list_fetch_btn.setToolTip("Fetch available models for all providers.")
        self.list_fetch_btn.clicked.connect(self.on_fetch_all)
        
        self.restore_btn = QPushButton("Restore Defaults")
        self.restore_btn.setToolTip("Reset global fallback priority to default provider-based models.")
        self.restore_btn.clicked.connect(self.restore_defaults)
        
        row2_layout.addWidget(self.list_test_btn)
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

    def populate_list(self, model_pairs):
        self.list_widget.clear()
        global_statuses = PERSISTENT_TEST_STATUSES.get("global_fallback_statuses", {})
        global_tooltips = PERSISTENT_TEST_STATUSES.get("global_fallback_tooltips", {})
        
        # Get currently disabled models map
        disabled_map = self.main_dialog.disabled_fallback_models_data if hasattr(self.main_dialog, "disabled_fallback_models_data") else {}

        for provider, model in model_pairs:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, (provider, model))
            status = global_statuses.get((provider, model))
            bl = " | 🚫 Blacklisted" if is_model_blacklisted(provider, model) else ""
            status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
            item.setText(f"[{provider.capitalize()}] {model}{status_suffix}")
            
            # Make item checkable and ensure standard flags are set
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Set check state based on global disabled map
            provider_disabled = disabled_map.get(provider, [])
            item.setCheckState(Qt.CheckState.Unchecked if model in provider_disabled else Qt.CheckState.Checked)

            tt = global_tooltips.get((provider, model))
            if tt:
                item.setToolTip(tt)
            elif bl:
                item.setToolTip("This model is currently on cooldown due to recent failures.")
            self.list_widget.addItem(item)
            
    def refresh_statuses(self):
        """Updates the status suffixes (e.g. 'Working', 'Error') and tooltips without clearing the whole list."""
        global_statuses = PERSISTENT_TEST_STATUSES.get("global_fallback_statuses", {})
        global_tooltips = PERSISTENT_TEST_STATUSES.get("global_fallback_tooltips", {})
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            provider, model = item.data(Qt.ItemDataRole.UserRole)
            status = global_statuses.get((provider, model))
            bl = " | 🚫 Blacklisted" if is_model_blacklisted(provider, model) else ""
            status_suffix = f" ({status}{bl})" if status else (f" ({bl.strip()})" if bl else "")
            item.setText(f"[{provider.capitalize()}] {model}{status_suffix}")
            tt = global_tooltips.get((provider, model))
            if tt:
                item.setToolTip(tt)
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
                item.setText(f"[{provider.capitalize()}] {model}")
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
            
    def remove_item(self):
        curr_row = self.list_widget.currentRow()
        if curr_row != -1:
            self.list_widget.takeItem(curr_row)
            
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
                            for m in sorted(list(set(ms))):
                                if m and (p, m) not in existing_set:
                                    item = QListWidgetItem()
                                    item.setData(Qt.ItemDataRole.UserRole, (p, m))
                                    item.setText(f"[{p.capitalize()}] {m}")
                                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                                    item.setCheckState(Qt.CheckState.Unchecked)
                                    self.list_widget.addItem(item)
                                    added_count += 1
                            if added_count > 0:
                                tooltip(f"Added {added_count} new models for {p.capitalize()}.")
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
        
    def on_test_all(self):
        test_key = "global_fallback_test"
        if test_key in TEST_CANCELLATIONS:
            TEST_CANCELLATIONS[test_key] = True
            self.list_test_btn.setText("Test All")
            tooltip("Testing cancelled.")
            return

        TEST_CANCELLATIONS[test_key] = False
        self.list_test_btn.setText("Stop Test All")
        self.restore_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        
        items_data = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_widget.count())]
        
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
                        item.setText(f"[{prov.capitalize()}] {name} (⏳ Testing...)")
                mw.taskman.run_on_main(_update_testing)
                
                status = "✅ Working"
                tooltip_text = ""
                try:
                    temp_config = self.main_dialog.config.copy()
                    api_key = self.main_dialog.api_key_edits[provider].text().strip() if provider in self.main_dialog.api_key_edits else ""
                    if "api_keys" not in temp_config: temp_config["api_keys"] = {}
                    temp_config["api_keys"][provider] = api_key
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
                        tooltip_text = f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/>The provider returned an empty response.</div>"
                    else:
                        import json
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
                    status = "❌ Error"
                    tooltip_text = f"<div style='width: 350px;'><b>Question:</b> {test_front}<br/><b>Answer:</b> {test_back}<br/><br/><b>Error:</b> {str(e)}</div>"
                    
                if TEST_CANCELLATIONS.get(test_key):
                    break

                def _update_result(idx=i, prov=provider, name=model, st=status, tt=tooltip_text):
                    item = self.list_widget.item(idx)
                    if item:
                        item.setText(f"[{prov.capitalize()}] {name} ({st})")
                        item.setToolTip(tt)
                        global_statuses = PERSISTENT_TEST_STATUSES.setdefault("global_fallback_statuses", {})
                        global_statuses[(prov, name)] = st
                        global_tooltips = PERSISTENT_TEST_STATUSES.setdefault("global_fallback_tooltips", {})
                        global_tooltips[(prov, name)] = tt
                mw.taskman.run_on_main(_update_result)
                
            def _done():
                self.list_test_btn.setText("Test All")
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
        if model and is_model_blacklisted(provider, model):
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

        # Local Providers Group
        local_group = QGroupBox("Local Providers")
        local_layout = QVBoxLayout()
        self.local_providers_list = QListWidget()
        self.local_providers_list.setDragEnabled(True)
        self.local_providers_list.setAcceptDrops(True)
        self.local_providers_list.setDropIndicatorShown(True)
        self.local_providers_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.local_providers_list.model().rowsMoved.connect(self._sync_local_provider_order_from_ui)
        self.local_providers_list.itemChanged.connect(self.on_local_provider_item_changed)
        local_layout.addWidget(QLabel("Manage multiple local endpoints. Drag to reorder and uncheck to disable."))
        local_layout.addWidget(self.local_providers_list)

        local_btn_layout = QHBoxLayout()
        self.add_local_provider_btn = QPushButton("Add")
        self.add_local_provider_btn.clicked.connect(self.on_add_local_provider)
        self.edit_local_provider_btn = QPushButton("Edit")
        self.edit_local_provider_btn.clicked.connect(self.on_edit_local_provider)
        self.fetch_local_provider_btn = QPushButton("Fetch")
        self.fetch_local_provider_btn.clicked.connect(self.on_fetch_local_provider)
        self.test_local_provider_btn = QPushButton("Test")
        self.test_local_provider_btn.clicked.connect(self.on_test_local_provider)
        self.remove_local_provider_btn = QPushButton("Remove")
        self.remove_local_provider_btn.clicked.connect(self.on_remove_local_provider)
        for btn in [self.add_local_provider_btn, self.edit_local_provider_btn, self.fetch_local_provider_btn, self.test_local_provider_btn, self.remove_local_provider_btn]:
            local_btn_layout.addWidget(btn)
        local_layout.addLayout(local_btn_layout)
        local_group.setLayout(local_layout)
        self.prov_layout.addRow(local_group)

        prov_scroll.setWidget(prov_content)
        prov_main_layout.addWidget(prov_scroll)
        
        self.providers_tab.setLayout(prov_main_layout)
        return self.providers_tab

    def refresh_local_providers_list(self):
        if not hasattr(self, "local_providers_list"):
            return
        self.local_providers_list.blockSignals(True)
        self.local_providers_list.clear()
        for name, data in (self.local_providers_data or {}).items():
            data = data or {}
            url = data.get("url") or data.get("base_url", "")
            model = data.get("model", "")
            item = QListWidgetItem(f"{name} - {url} - {model}" if model else f"{name} - {url}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            item.setCheckState(Qt.CheckState.Checked if data.get("enabled", True) else Qt.CheckState.Unchecked)
            self.local_providers_list.addItem(item)
        self.local_providers_list.blockSignals(False)
        self.update_local_provider_labels()

    def update_local_provider_labels(self):
        if not hasattr(self, "local_providers_list"):
            return
        for i in range(self.local_providers_list.count()):
            item = self.local_providers_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            data = self.local_providers_data.get(name, {}) or {}
            url = data.get("url") or data.get("base_url", "")
            model = data.get("model", "")
            label = f"{name} - {url} - {model}" if model else f"{name} - {url}"
            if item.checkState() == Qt.CheckState.Unchecked:
                label += " (disabled)"
            item.setText(label)

    def on_local_provider_item_changed(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        if name in self.local_providers_data:
            self.local_providers_data[name]["enabled"] = item.checkState() == Qt.CheckState.Checked
        self.update_local_provider_labels()

    def _sync_local_provider_order_from_ui(self):
        ordered = {}
        for i in range(self.local_providers_list.count()):
            item = self.local_providers_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name in self.local_providers_data:
                ordered[name] = self.local_providers_data[name]
        self.local_providers_data = ordered

    def _selected_local_provider_name(self):
        item = self.local_providers_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "").strip() if item else ""

    def _local_provider_temp_config(self, name):
        temp_config = self.config.copy()
        local_providers = temp_config.get("local_providers", {}) or {}
        if not isinstance(local_providers, dict):
            local_providers = {}
        temp_config["local_providers"] = local_providers
        temp_config["local_provider_override"] = name
        return temp_config

    def on_add_local_provider(self):
        dlg = CustomProviderDialog(self, config=self.config)
        if dlg.exec():
            name = dlg.name_edit.text().strip()
            self.local_providers_data[name] = {
                "url": dlg.url_edit.text().strip(),
                "base_url": dlg.url_edit.text().strip(),
                "api_key": dlg.key_edit.text().strip(),
                "model": dlg.model_edit.text().strip(),
                "headers": json.loads(dlg.headers_edit.toPlainText() or "{}"),
                "enabled": True,
            }
            self.refresh_local_providers_list()

    def on_edit_local_provider(self):
        name = self._selected_local_provider_name()
        if not name:
            return
        data = self.local_providers_data.get(name, {})
        dlg = CustomProviderDialog(self, name=name, data=data, config=self.config)
        if dlg.exec():
            new_name = dlg.name_edit.text().strip()
            if new_name != name:
                del self.local_providers_data[name]
            self.local_providers_data[new_name] = {
                "url": dlg.url_edit.text().strip(),
                "base_url": dlg.url_edit.text().strip(),
                "api_key": dlg.key_edit.text().strip(),
                "model": dlg.model_edit.text().strip(),
                "headers": json.loads(dlg.headers_edit.toPlainText() or "{}"),
                "enabled": data.get("enabled", True),
            }
            self.refresh_local_providers_list()

    def on_remove_local_provider(self):
        name = self._selected_local_provider_name()
        if name in self.local_providers_data:
            del self.local_providers_data[name]
        self.refresh_local_providers_list()

    def on_fetch_local_provider(self):
        name = self._selected_local_provider_name()
        if not name:
            info("Select a local provider first.")
            return
        from ..ai_client import AIClient
        client = AIClient(self._local_provider_temp_config(name))
        try:
            models = client.fetch_models("local")
            if models:
                menu = QMenu(self)
                for m in sorted(set(models)):
                    action = menu.addAction(m)
                    action.triggered.connect(lambda chk, val=m: self._set_local_provider_model(name, val))
                menu.exec(self.fetch_local_provider_btn.mapToGlobal(QPoint(0, self.fetch_local_provider_btn.height())))
            else:
                info(f"No models found for {name}.")
        except Exception as e:
            info(f"Fetch failed for {name}: {e}")

    def _set_local_provider_model(self, name, model):
        if name in self.local_providers_data:
            self.local_providers_data[name]["model"] = model
            self.refresh_local_providers_list()

    def on_test_local_provider(self):
        name = self._selected_local_provider_name()
        if not name:
            info("Select a local provider first.")
            return
        from ..ai_client import AIClient
        temp_config = self._local_provider_temp_config(name)
        provider_cfg = self.local_providers_data.get(name, {}) or {}
        temp_config.setdefault("models", {})
        temp_config["models"]["local"] = provider_cfg.get("model", DEFAULT_MODELS["local"])
        client = AIClient(temp_config)
        try:
            res = client.generate_options(
                self.test_question_edit.text().strip() or DEFAULT_TEST_QUESTION,
                self.test_answer_edit.text().strip() or DEFAULT_TEST_ANSWER,
                override_provider="local",
                only_this_provider=True,
            )
            if res and (res.get("hints") or res.get("options")):
                tooltip(f"{name} responded successfully.")
            else:
                info(f"{name} returned no usable data.")
        except Exception as e:
            info(f"Test failed for {name}: {e}")
