"""Per-model variant settings: one row per (provider, model) pair.

Stored in config["model_variants"] as {"provider|model": {...}}. Only values
that differ from the defaults are saved; the AI client applies them to each
request for that exact model.
"""

from aqt.qt import *

from .widgets import NoWheelComboBox


class ModelVariantsTabMixin:
    _VARIANT_COLUMNS = [
        "Provider", "Model", "Temp", "Max tokens", "Reasoning effort",
        "Thinking budget", "Response format", "Cache",
    ]

    def _create_model_variants_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Per-model overrides. Each row applies only to that provider/model pair. "
            "Leave a field empty (or 'auto' / 'Yes') to use the add-on default. "
            "Thinking budget is used by Gemini and Anthropic (Anthropic also requires "
            "Max tokens above the budget and a budget of at least 1024)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        self.model_variants_table = QTableWidget(0, len(self._VARIANT_COLUMNS))
        self.model_variants_table.setHorizontalHeaderLabels(self._VARIANT_COLUMNS)
        header = self.model_variants_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.model_variants_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.model_variants_table.setToolTip(
            "Temp: sampling temperature. Max tokens: output cap. Reasoning effort: "
            "OpenAI-compatible reasoning models. Thinking budget: extra reasoning "
            "tokens. Response format: json_object / none overrides JSON mode. "
            "Cache: set to No to disable prompt caching for this model."
        )
        layout.addWidget(self.model_variants_table)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Add variant")
        add_btn.clicked.connect(lambda: self._add_model_variant_row())
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected_model_variant)
        fill_btn = QPushButton("Add from priority / fallback lists")
        fill_btn.setToolTip(
            "Create rows for models already configured in the global priority "
            "list and per-provider fallback lists."
        )
        fill_btn.clicked.connect(self._add_variants_from_lists)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addWidget(fill_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.model_variants_table.itemChanged.connect(self._mark_model_variants_dirty)
        self._load_model_variants_into_ui()
        return tab

    def _mark_model_variants_dirty(self, *_args):
        self._dirty = True

    def _add_model_variant_row(self, provider="", model="", values=None):
        values = values or {}
        table = self.model_variants_table
        row = table.rowCount()
        table.insertRow(row)

        def _set(col, text):
            item = QTableWidgetItem(str(text if text is not None else ""))
            table.setItem(row, col, item)
            return item

        _set(0, provider)
        _set(1, model)
        _set(2, values.get("temperature", ""))
        _set(3, values.get("max_tokens", ""))
        _set(4, values.get("reasoning_effort", ""))
        _set(5, values.get("thinking_budget", ""))

        effort = NoWheelComboBox()
        effort.addItems(["auto", "none", "minimal", "low", "medium", "high", "xhigh", "max"])
        effort.setCurrentText(str(values.get("reasoning_effort") or "auto"))
        fmt = NoWheelComboBox()
        fmt.addItems(["auto", "json_object", "none"])
        fmt.setCurrentText(str(values.get("response_format") or "auto"))
        cache = NoWheelComboBox()
        cache.addItems(["Yes", "No"])
        cache.setCurrentText("No" if values.get("prompt_caching") is False else "Yes")
        for widget in (effort, fmt, cache):
            widget.currentIndexChanged.connect(self._mark_model_variants_dirty)
        table.setCellWidget(row, 4, effort)
        table.setCellWidget(row, 6, fmt)
        table.setCellWidget(row, 7, cache)
        return row

    def _remove_selected_model_variant(self):
        table = self.model_variants_table
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)
        if rows:
            self._dirty = True

    def _add_variants_from_lists(self):
        existing = set()
        table = self.model_variants_table
        for row in range(table.rowCount()):
            p = table.item(row, 0)
            m = table.item(row, 1)
            if p and m:
                existing.add((p.text().strip(), m.text().strip()))

        pairs = []
        for entry in (self.config.get("global_model_priority") or []):
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                pairs.append((str(entry[0]), str(entry[1])))
        for provider, models in (self.config.get("model_fallbacks") or {}).items():
            if isinstance(models, (list, tuple)):
                pairs.extend((str(provider), str(model)) for model in models)

        added = 0
        for provider, model in pairs:
            if not provider or not model or (provider, model) in existing:
                continue
            existing.add((provider, model))
            self._add_model_variant_row(provider, model)
            added += 1
        if added:
            self._dirty = True

    def _load_model_variants_into_ui(self):
        table = self.model_variants_table
        table.blockSignals(True)
        table.setRowCount(0)
        variants = self.config.get("model_variants") or {}
        if isinstance(variants, dict):
            for key, values in variants.items():
                if not isinstance(key, str) or not isinstance(values, dict):
                    continue
                provider, sep, model = key.partition("|")
                if not sep or not provider or not model:
                    continue
                self._add_model_variant_row(provider, model, values)
        table.blockSignals(False)

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

            effort = table.cellWidget(row, 4)
            if effort is not None and effort.currentText() != "auto":
                values["reasoning_effort"] = effort.currentText()
            fmt = table.cellWidget(row, 6)
            if fmt is not None and fmt.currentText() != "auto":
                values["response_format"] = fmt.currentText()
            cache = table.cellWidget(row, 7)
            if cache is not None and cache.currentText() == "No":
                values["prompt_caching"] = False

            if values:
                variants[f"{provider}|{model}"] = values
        return variants
