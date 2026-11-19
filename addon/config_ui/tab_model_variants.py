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
    _COLUMN_WIDTHS = [150, 340, 70, 90, 130, 120, 130, 70]

    def _create_model_variants_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Per-model overrides. Every fetched model is pre-filled; each row "
            "applies only to that provider/model pair. Leave a field empty (or "
            "'auto' / 'Yes') to use the add-on default. Thinking budget is used "
            "by Gemini and Anthropic (Anthropic also requires Max tokens above "
            "the budget and a budget of at least 1024)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        table = QTableWidget(0, len(self._VARIANT_COLUMNS))
        self.model_variants_table = table
        table.setHorizontalHeaderLabels(self._VARIANT_COLUMNS)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(self._COLUMN_WIDTHS):
            table.setColumnWidth(col, width)
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
        layout.addWidget(table)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Add variant")
        add_btn.clicked.connect(lambda: self._add_model_variant_row())
        remove_btn = QPushButton("Remove selected")
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
        self._load_model_variants_into_ui()
        return tab

    def _mark_model_variants_dirty(self, *_args):
        self._dirty = True

    def _add_model_variant_row(self, provider="", model="", values=None):
        table = self.model_variants_table
        row = table.rowCount()
        table.insertRow(row)
        self._set_variant_row(row, provider, model, values)
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
        # Preserve anything typed but not yet saved.
        current = self._collect_model_variants() if table.rowCount() else {}
        variants = self.config.get("model_variants") or {}
        saved = variants if isinstance(variants, dict) else {}
        merged = dict(current)
        merged.update(saved)

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

    def _remove_selected_model_variant(self):
        table = self.model_variants_table
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)
        if rows:
            self._dirty = True

    def _collect_model_variants(self):
        table = getattr(self, "model_variants_table", None)
        if table is None:
            return self.config.get("model_variants") or {}
        variants = {}
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

            if values:
                variants[f"{provider}|{model}"] = values
        return variants
