"""Per-model variant settings: one row per (provider, model) pair.

Stored in config["model_variants"] as {"provider|model": {...}}. Only values
that differ from the defaults are saved; the AI client applies them to each
request for that exact model.

The table is pre-filled with every model known from the priority/fallback
lists (thousands of rows for OpenRouter-class providers), so cell values are
plain text items with one shared combo delegate per column — creating a
widget per row would make the dialog unusably slow.
"""

from aqt.qt import *

from ..model_variants import known_model_pairs


class _VariantComboDelegate(QStyledItemDelegate):
    """A single reusable combo editor for a whole column."""

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self._options = list(options)

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self._options)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        i = editor.findText(str(value or ""))
        editor.setCurrentIndex(i if i >= 0 else 0)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class ModelVariantsTabMixin:
    _VARIANT_COLUMNS = [
        "Provider", "Model", "Temp", "Max tokens", "Reasoning effort",
        "Thinking budget", "Response format", "Cache",
    ]
    _EFFORTS = ["auto", "none", "minimal", "low", "medium", "high", "xhigh", "max"]
    _FORMATS = ["auto", "json_object", "none"]
    _CACHE = ["Yes", "No"]
    _COLUMN_WIDTHS = [130, 300, 60, 80, 110, 100, 110, 60]

    def _create_model_variants_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Per-model overrides. Every fetched model is pre-filled; each row "
            "applies only to that provider/model pair. Leave a field empty (or "
            "'auto' / 'Yes') to use the add-on default. Click a column header "
            "to sort. Thinking budget is used by Gemini and Anthropic "
            "(Anthropic also requires Max tokens above the budget and a budget "
            "of at least 1024)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        search_layout = QHBoxLayout()
        self.model_variant_search = QLineEdit()
        self.model_variant_search.setPlaceholderText(
            "Filter models by provider or name...")
        self.model_variant_search.textChanged.connect(
            self._apply_model_variant_filter)
        self.model_variant_count = QLabel()
        search_layout.addWidget(self.model_variant_search)
        search_layout.addWidget(self.model_variant_count)
        layout.addLayout(search_layout)

        table = QTableWidget(0, len(self._VARIANT_COLUMNS))
        self.model_variants_table = table
        table.setHorizontalHeaderLabels(self._VARIANT_COLUMNS)
        header = table.horizontalHeader()
        for col, width in enumerate(self._COLUMN_WIDTHS):
            table.setColumnWidth(col, width)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setToolTip(
            "Temp: sampling temperature. Max tokens: output cap. Reasoning effort: "
            "OpenAI-compatible reasoning models. Thinking budget: extra reasoning "
            "tokens. Response format: json_object / none overrides JSON mode. "
            "Cache: set to No to disable prompt caching for this model."
        )
        table.setItemDelegateForColumn(4, _VariantComboDelegate(self._EFFORTS, table))
        table.setItemDelegateForColumn(6, _VariantComboDelegate(self._FORMATS, table))
        table.setItemDelegateForColumn(7, _VariantComboDelegate(self._CACHE, table))
        table.setSortingEnabled(True)
        header.sortIndicatorChanged.connect(
            lambda *_: QTimer.singleShot(0, self._apply_model_variant_filter))
        layout.addWidget(table)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Add variant")
        add_btn.setToolTip(
            "Add a blank row for a provider/model that is not in the fetched "
            "lists (for example a model you type manually). Fill in the "
            "provider and model, then set the overrides you want."
        )
        add_btn.clicked.connect(lambda: self._add_model_variant_row())
        remove_btn = QPushButton("Remove selected")
        remove_btn.setToolTip(
            "Remove the selected rows from this table. On Save their overrides "
            "are deleted; the model stays in the provider's own priority and "
            "fallback lists."
        )
        remove_btn.clicked.connect(self._remove_selected_model_variant)
        refresh_btn = QPushButton("Refresh models from lists")
        refresh_btn.setToolTip(
            "Re-read the global priority list and per-provider fallback lists "
            "and add any models missing from this table."
        )
        refresh_btn.clicked.connect(self._load_model_variants_into_ui)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addWidget(refresh_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        table.itemChanged.connect(self._mark_model_variants_dirty)
        # load_config_into_ui() is the single init point when tabs are built
        # eagerly. For tabs built lazily later, load on first construction.
        if getattr(self, "_model_variants_loaded", False):
            self._load_model_variants_into_ui()
        return tab

    def _mark_model_variants_dirty(self, *_args):
        self._dirty = True

    def _apply_model_variant_filter(self):
        """Hide non-matching rows; hidden rows still keep their values."""
        table = getattr(self, "model_variants_table", None)
        if table is None:
            return
        search = getattr(self, "model_variant_search", None)
        term = search.text().strip().lower() if search is not None else ""
        visible = 0
        for row in range(table.rowCount()):
            provider = table.item(row, 0)
            model = table.item(row, 1)
            text = f"{provider.text() if provider else ''} {model.text() if model else ''}".lower()
            match = not term or term in text
            table.setRowHidden(row, not match)
            if match:
                visible += 1
        count = getattr(self, "model_variant_count", None)
        if count is not None:
            count.setText(f"{visible} of {table.rowCount()} shown")

    def _add_model_variant_row(self, provider="", model="", values=None):
        table = self.model_variants_table
        # With sorting enabled, insertRow() can immediately move the new row,
        # so writing to the original index lands on a different model.
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        row = table.rowCount()
        table.insertRow(row)
        self._set_variant_row(row, provider, model, values)
        table.setSortingEnabled(was_sorting)
        if was_sorting:
            header = table.horizontalHeader()
            table.sortItems(header.sortIndicatorSection(), header.sortIndicatorOrder())
        if provider and model and hasattr(self, "_removed_model_variant_keys"):
            self._removed_model_variant_keys.discard(f"{provider}|{model}")
        self._apply_model_variant_filter()
        return row

    def _set_variant_row(self, row, provider="", model="", values=None):
        values = values or {}
        table = self.model_variants_table

        def _set(col, text):
            table.setItem(row, col, QTableWidgetItem(str(text if text is not None else "")))

        effort = str(values.get("reasoning_effort") or "auto")
        fmt = str(values.get("response_format") or "auto")
        cache = "No" if values.get("prompt_caching") is False else "Yes"
        _set(0, provider)
        _set(1, model)
        _set(2, values.get("temperature", ""))
        _set(3, values.get("max_tokens", ""))
        _set(4, effort)
        _set(5, values.get("thinking_budget", ""))
        _set(6, fmt)
        _set(7, cache)

    def _known_model_pairs(self):
        return known_model_pairs(self.config)

    def _load_model_variants_into_ui(self):
        table = self.model_variants_table
        # The table is authoritative: a value cleared in the UI must not be
        # resurrected from the stale on-disk snapshot on the next refresh.
        current = self._collect_model_variant_rows() if table.rowCount() else {}
        variants = self.config.get("model_variants") or {}
        saved = variants if isinstance(variants, dict) else {}
        merged = dict(saved)
        for key, values in current.items():
            if values:
                merged[key] = values
            else:
                merged.pop(key, None)
        for key in getattr(self, "_removed_model_variant_keys", set()):
            merged.pop(key, None)

        rows = []
        seen = set()
        for key, values in merged.items():
            provider, sep, model = str(key).partition("|")
            if not sep or not provider or not model or not isinstance(values, dict):
                continue
            rows.append((provider, model, values))
            seen.add((provider, model))
        for provider, model in self._known_model_pairs():
            if (provider, model) in seen:
                continue
            seen.add((provider, model))
            rows.append((provider, model, {}))
        # Keep rows the user added or reset to defaults, even when they are
        # not part of any fetched model list.
        for key in current:
            provider, sep, model = str(key).partition("|")
            if not sep or not provider or not model or (provider, model) in seen:
                continue
            seen.add((provider, model))
            rows.append((provider, model, {}))

        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.blockSignals(True)
        was_updating = table.updatesEnabled()
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(rows))
            for i, (provider, model, values) in enumerate(rows):
                self._set_variant_row(i, provider, model, values)
        finally:
            table.setUpdatesEnabled(was_updating)
            table.blockSignals(False)
            table.setSortingEnabled(was_sorting)
            self._apply_model_variant_filter()

    def _remove_selected_model_variant(self):
        table = self.model_variants_table
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        removed = set()
        for row in rows:
            p, m = table.item(row, 0), table.item(row, 1)
            if p and m and p.text().strip() and m.text().strip():
                removed.add(f"{p.text().strip()}|{m.text().strip()}")
            table.removeRow(row)
        if rows:
            if not hasattr(self, "_removed_model_variant_keys"):
                self._removed_model_variant_keys = set()
            self._removed_model_variant_keys.update(removed)
            saved = self.config.get("model_variants")
            if isinstance(saved, dict):
                for key in removed:
                    saved.pop(key, None)
            self._dirty = True
            self._apply_model_variant_filter()

    def _collect_model_variant_rows(self):
        """Lossless snapshot of the table: every row, even all-default ones."""
        table = getattr(self, "model_variants_table", None)
        if table is None:
            return {}
        rows = {}
        for row in range(table.rowCount()):
            p = table.item(row, 0)
            m = table.item(row, 1)
            if not p or not m:
                continue
            provider, model = p.text().strip(), m.text().strip()
            if not provider or not model:
                continue

            values = {}

            def _number(col, cast):
                item = table.item(row, col)
                text = item.text().strip() if item else ""
                if not text:
                    return None
                try:
                    return cast(text)
                except ValueError:
                    return None

            temperature = _number(2, float)
            if temperature is not None:
                values["temperature"] = temperature
            max_tokens = _number(3, int)
            if max_tokens is not None and max_tokens > 0:
                values["max_tokens"] = max_tokens
            budget = _number(5, int)
            if budget is not None and budget >= 0:
                values["thinking_budget"] = budget

            def _text(col):
                item = table.item(row, col)
                return item.text().strip().lower() if item else ""

            effort = _text(4)
            if effort in self._EFFORTS and effort != "auto":
                values["reasoning_effort"] = effort
            fmt = _text(6)
            if fmt in self._FORMATS and fmt != "auto":
                values["response_format"] = fmt
            if _text(7) in ("no", "false", "0", "off"):
                values["prompt_caching"] = False

            rows[f"{provider}|{model}"] = values
        return rows

    def _collect_model_variants(self):
        """Only non-default values are persisted in config."""
        table = getattr(self, "model_variants_table", None)
        if table is None:
            return self.config.get("model_variants") or {}
        return {k: v for k, v in self._collect_model_variant_rows().items() if v}
