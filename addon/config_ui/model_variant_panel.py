"""Compact per-model parameter editor embedded in the fallback dialogs.

Shows the non-default overrides for the (provider, model) row currently
selected in the dialog's table. Values are stored in a plain dict keyed by
"provider|model", so changing the table order or fetching new models never
loses an override. Only values that differ from provider defaults are kept,
matching config["model_variants"] consumed by AIClient._model_variant().
"""
from aqt.qt import *

EFFORTS = ["auto", "none", "minimal", "low", "medium", "high", "xhigh", "max"]
FORMATS = ["auto", "json_object", "none"]
CACHE_OPTIONS = ["Yes", "No"]


def collect_variant_values(temp, max_tokens, effort, thinking_budget, fmt, cache):
    """Pure helper: turn the six displayed field values into override dict."""
    values = {}
    try:
        t = float(str(temp).strip())
        values["temperature"] = t
    except (TypeError, ValueError):
        pass
    try:
        mt = int(str(max_tokens).strip())
        if mt > 0:
            values["max_tokens"] = mt
    except (TypeError, ValueError):
        pass
    effort = str(effort or "auto").strip().lower()
    if effort in EFFORTS and effort != "auto":
        values["reasoning_effort"] = effort
    try:
        budget = int(str(thinking_budget).strip())
        if budget >= 0:  # 0 is meaningful: explicitly disable thinking
            values["thinking_budget"] = budget
    except (TypeError, ValueError):
        pass
    fmt = str(fmt or "auto").strip().lower()
    if fmt in FORMATS and fmt != "auto":
        values["response_format"] = fmt
    if str(cache or "Yes").strip().lower() in ("no", "false", "0", "off"):
        values["prompt_caching"] = False
    return values


class VariantPanel(QGroupBox):
    """Edit parameters for the selected model; writes into ``overrides``."""

    def __init__(self, overrides, parent=None):
        super().__init__("Model Parameters (selected model)", parent)
        self.overrides = overrides if isinstance(overrides, dict) else {}
        self._key = None
        self._loading = False

        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.temp_edit = QLineEdit()
        self.temp_edit.setPlaceholderText("provider default")
        self.max_tokens_edit = QLineEdit()
        self.max_tokens_edit.setPlaceholderText("provider default")
        self.effort_combo = QComboBox()
        self.effort_combo.addItems(EFFORTS)
        self.budget_edit = QLineEdit()
        self.budget_edit.setPlaceholderText("provider default (0 disables thinking)")
        self.format_combo = QComboBox()
        self.format_combo.addItems(FORMATS)
        self.cache_combo = QComboBox()
        self.cache_combo.addItems(CACHE_OPTIONS)

        form.addRow("Temperature:", self.temp_edit)
        form.addRow("Max tokens:", self.max_tokens_edit)
        form.addRow("Reasoning effort:", self.effort_combo)
        form.addRow("Thinking budget:", self.budget_edit)
        form.addRow("Response format:", self.format_combo)
        form.addRow("Prompt caching:", self.cache_combo)

        self.reset_btn = QPushButton("Reset selected model to defaults")
        self.reset_btn.setToolTip("Remove all overrides for this model (it keeps its list position).")
        form.addRow(self.reset_btn)

        for widget in (self.temp_edit, self.max_tokens_edit, self.budget_edit):
            widget.textChanged.connect(self._on_edit)
        for widget in (self.effort_combo, self.format_combo, self.cache_combo):
            widget.currentTextChanged.connect(self._on_edit)
        self.reset_btn.clicked.connect(self._reset_selected)

        self.setInfoLabel()
        self.setEnabled(False)

    def setInfoLabel(self):
        tip = (
            "Select a model in either list to edit its request parameters. "
            "Blank fields use the provider default; only changed values are saved."
        )
        self.setToolTip(tip)

    def load(self, provider, model):
        self._loading = True
        self._key = f"{provider}|{model}" if provider and model else None
        values = self.overrides.get(self._key, {}) if self._key else {}
        values = values if isinstance(values, dict) else {}
        self._set_text(self.temp_edit, values.get("temperature"))
        self._set_text(self.max_tokens_edit, values.get("max_tokens"))
        self._set_text(self.budget_edit, values.get("thinking_budget"))
        self._set_combo(self.effort_combo, values.get("reasoning_effort", "auto"))
        self._set_combo(self.format_combo, values.get("response_format", "auto"))
        self._set_combo(
            self.cache_combo,
            "No" if values.get("prompt_caching") is False else "Yes",
        )
        self.setEnabled(bool(self._key))
        self.setTitle(
            f"Model Parameters — {provider} / {model}" if self._key
            else "Model Parameters (select a model above)"
        )
        self._loading = False

    @staticmethod
    def _set_text(widget, value):
        widget.blockSignals(True)
        widget.setText("" if value is None or value == "" else str(value))
        widget.blockSignals(False)

    def _set_combo(self, widget, value):
        widget.blockSignals(True)
        idx = widget.findText(str(value or "auto"))
        widget.setCurrentIndex(idx if idx >= 0 else 0)
        widget.blockSignals(False)

    def _on_edit(self, *_args):
        if self._loading or not self._key:
            return
        values = collect_variant_values(
            self.temp_edit.text(), self.max_tokens_edit.text(),
            self.effort_combo.currentText(), self.budget_edit.text(),
            self.format_combo.currentText(), self.cache_combo.currentText(),
        )
        if values:
            self.overrides[self._key] = values
        else:
            self.overrides.pop(self._key, None)

    def _reset_selected(self):
        if not self._key:
            return
        self.overrides.pop(self._key, None)
        self.load(self._key.split("|", 1)[0], self._key.split("|", 1)[1])
