"""Per-model request parameters shown as columns in the fallback model lists.

The six editable columns are plain table items (plus shared combo delegates
for the enumerated ones) so dialogs with thousands of rows stay fast. Values
are mirrored into a dict keyed by "provider|model"; the dict is authoritative
and is harvested back from the items before every structural operation.
"""
from aqt.qt import *

HEADERS = ["Temp", "Max tokens", "Reasoning effort", "Thinking budget", "Response format", "Cache"]
WIDTHS = [60, 90, 120, 120, 110, 60]
EFFORTS = ["auto", "none", "minimal", "low", "medium", "high", "xhigh", "max"]
FORMATS = ["auto", "json_object", "none"]
CACHE_OPTIONS = ["Yes", "No"]


def collect_variant_values(temp, max_tokens, effort, thinking_budget, fmt, cache):
    """Turn the six displayed cell values into a non-default override dict."""
    values = {}
    try:
        values["temperature"] = float(str(temp).strip())
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


class VariantComboDelegate(QStyledItemDelegate):
    """One reusable combo editor for an entire enumerated column."""

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


def install_variant_columns(table, start_col):
    """Attach combo delegates to the three enumerated variant columns."""
    for offset, options in ((2, EFFORTS), (4, FORMATS), (5, CACHE_OPTIONS)):
        table.setItemDelegateForColumn(start_col + offset, VariantComboDelegate(options, table))


def variant_display_values(values):
    """Six display strings for a (provider, model) override dict."""
    values = values if isinstance(values, dict) else {}
    return [
        "" if values.get("temperature") is None else str(values["temperature"]),
        "" if values.get("max_tokens") is None else str(values["max_tokens"]),
        str(values.get("reasoning_effort") or "auto"),
        "" if values.get("thinking_budget") is None else str(values["thinking_budget"]),
        str(values.get("response_format") or "auto"),
        "No" if values.get("prompt_caching") is False else "Yes",
    ]


def set_variant_cells(table, row, start_col, values):
    """Write the six variant cells for a row."""
    for offset, text in enumerate(variant_display_values(values)):
        item = QTableWidgetItem(text)
        item.setToolTip("Leave blank / auto for provider default.")
        table.setItem(row, start_col + offset, item)


def harvest_variant_cells(table, start_col, key_for_row, overrides):
    """Read variant cells back into the authoritative override dict."""
    for row in range(table.rowCount()):
        key = key_for_row(table, row)
        if not key:
            continue
        cells = []
        for col in range(start_col, start_col + len(HEADERS)):
            item = table.item(row, col)
            cells.append(item.text().strip() if item else "")
        values = collect_variant_values(*cells)
        if values:
            overrides[key] = values
        else:
            overrides.pop(key, None)
