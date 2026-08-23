import unittest
import sys
import os
import json
from types import ModuleType
from unittest.mock import MagicMock, patch

# ---- Mock the aqt / ankiqt namespaces BEFORE importing addon modules ----
aqt = ModuleType('aqt')
sys.modules['aqt'] = aqt
aqt.qt = MagicMock()
sys.modules['aqt.qt'] = aqt.qt
aqt.utils = MagicMock()
sys.modules['aqt.utils'] = aqt.utils
aqt.webview = MagicMock()
sys.modules['aqt.webview'] = aqt.webview
aqt.theme = MagicMock()
sys.modules['aqt.theme'] = aqt.theme
aqt.colors = MagicMock()
sys.modules['aqt.colors'] = aqt.colors
aqt.gui_hooks = MagicMock()
sys.modules['aqt.gui_hooks'] = aqt.gui_hooks
aqt.operations = MagicMock()
sys.modules['aqt.operations'] = aqt.operations
aqt.operations.deck = MagicMock()
sys.modules['aqt.operations.deck'] = aqt.operations.deck
aqt.mw = MagicMock()
sys.modules['aqt.mw'] = aqt.mw

classes = [
    'QDialog', 'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QLabel', 'QLineEdit',
    'QPushButton', 'QComboBox', 'QCheckBox', 'QTextEdit', 'QScrollArea',
    'QGroupBox', 'QFormLayout', 'QSpinBox', 'QDialogButtonBox', 'QPixmap',
    'Qt', 'QApplication', 'QSizePolicy', 'QTimer', 'QTabWidget', 'QListWidget',
    'QListWidgetItem', 'QDesktopServices', 'QUrl', 'QProgressBar',
    'QStyledItemDelegate', 'QEvent', 'QTextBrowser', 'QFontDatabase',
    'QCompleter', 'QButtonGroup', 'QRadioButton', 'QMessageBox', 'QProgressDialog',
]
for cls in classes:
    # Keep these as class objects so `class ConfigDialog(QDialog, ...)` subclasses work.
    setattr(aqt.qt, cls, MagicMock)

sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from addon.config_ui.tab_batch import BatchTabMixin
import addon.config_ui.main_dialog as main_dialog


class StopScan(Exception):
    """Raised inside askUser to halt batch flow right after the confirm call."""


class OneShotAskUser:
    def __init__(self):
        self.messages = []

    def __call__(self, msg, *args, **kwargs):
        self.messages.append(msg)
        raise StopScan()


def _make_dummy(batch_full_scan=False, selected_ids=None, cfg=None, deck_results=None, deck_name="DeckA"):
    obj = MagicMock()
    obj.selected_card_ids = selected_ids

    chooser = MagicMock()
    chooser.currentText.return_value = deck_name
    obj.batch_deck_chooser = chooser

    skip_cb = MagicMock()
    skip_cb.isChecked.return_value = False
    obj.batch_skip_existing_cb = skip_cb

    full_cb = MagicMock()
    full_cb.isChecked.return_value = batch_full_scan
    obj.batch_full_scan_cb = full_cb

    limit = MagicMock()
    limit.value.return_value = 1000000
    obj.batch_limit_spin = limit

    native = MagicMock()
    native.isChecked.return_value = False
    obj.rb_native_async = native
    rb_local = MagicMock()
    rb_local.isChecked.return_value = True
    obj.rb_local_queue = rb_local

    obj.rb_selected_deck = MagicMock()

    obj.batch_multithread_cb = MagicMock()
    obj.batch_multithread_cb.isChecked.return_value = False

    obj.batch_provider_cb = MagicMock()
    obj.batch_provider_cb.currentIndex.return_value = 0

    model_cb = MagicMock()
    model_cb.currentText.return_value = "⚡ System Default (Configured Primary Model)"
    obj.batch_model_cb = model_cb

    obj.save_config = MagicMock()

    obj.results = {}
    obj.calls = []

    col = MagicMock()
    col.decks = MagicMock()
    col.decks.all_names.return_value = ["DeckA", "DeckB"]

    def _find_cards(q, *args, **kwargs):
        obj.calls.append(q)
        return (deck_results or {}).get(q, [])

    col.find_cards.side_effect = _find_cards
    col.db = MagicMock()
    col.db.scalar.return_value = 999999
    obj._col = col

    if cfg is None:
        cfg = {"tag_hinted_notes": True, "deck_last_scan_nid": {"DeckA": 55555}}
    obj._cfg = cfg
    return obj


def _mock_mw(obj):
    mw = MagicMock()
    mw.col = obj._col
    addmgr = MagicMock()
    addmgr.getConfig.return_value = obj._cfg
    mw.addonManager = addmgr
    return mw


def _mock_batch_manager():
    bm = MagicMock()
    bm.local_queue_active = False
    bm.local_queue = []
    bm.start_local_sequential_queue.return_value = True
    return bm


class TestBatchFastScan(unittest.TestCase):
    def setUp(self):
        self._prev_states = {}
        # Isolate the cursor sidecar so tests never read the developer's real file
        import tempfile
        self._cursor_tmpdir = tempfile.mkdtemp()
        self._cursor_file = os.path.join(self._cursor_tmpdir, "batch_scan_cursors.json")
        self._path_patch = patch(
            "addon.config_ui.tab_batch._scan_cursors_path",
            return_value=self._cursor_file,
        )
        self._path_patch.start()
        self.addCleanup(self._path_patch.stop)
        self.addCleanup(lambda: __import__("shutil", fromlist=["rmtree"]).rmtree(self._cursor_tmpdir, ignore_errors=True))

    def _run(self, **kwargs):
        obj = _make_dummy(**kwargs)
        ask = OneShotAskUser()
        deck_results = kwargs.get("deck_results") or {
            'deck:"DeckA"': [1, 2, 3, 4, 5],
            'deck:"DeckA" nid:55560,55570': [5],
            'deck:"DeckB"': [100, 101],
        }
        obj._col.find_cards.side_effect = lambda q, *a, **k: obj.calls.append(q) or deck_results.get(q, [])

        def _find_notes(q, *a, **k):
            return [55550, 55560, 55570]
        obj._col.find_notes.side_effect = _find_notes
        with patch("addon.config_ui.tab_batch.mw", new=_mock_mw(obj)), \
             patch("addon.config_ui.tab_batch.askUser", new=ask), \
             patch("addon.batch_manager.batch_manager", _mock_batch_manager()):
            try:
                BatchTabMixin.on_start_config_batch(obj)
            except StopScan:
                pass
        self.calls = obj.calls
        self.asks = ask.messages
        return obj

    def test_fast_scans_notes_since_last_cursor(self):
        # Seed a cursor for DeckA between 55550 and 55560 so only those two
        # notes are "new" (matches the deck_results mapping in _run()).
        from addon.config_ui.tab_batch import _save_scan_cursors
        _save_scan_cursors({"DeckA": 55559})
        self._run()
        self.assertIn('deck:"DeckA"', self.calls)
        self.assertIn('deck:"DeckA" nid:55560,55570', self.calls)
        self.assertNotIn('nid:>', " ".join(self.calls))
        self.assertEqual(len(self.asks), 1)
        self.assertIn("fast scan", self.asks[0])

    def test_subdeck_without_cursor_gets_full_scan(self):
        # DeckB has no saved cursor -> its older un-hinted cards must never be skipped.
        obj = self._run(deck_name="DeckB")
        self.assertIn('deck:"DeckB"', self.calls)
        self.assertNotIn('deck:"DeckB" nid:', self.calls)
        self.assertEqual(len(self.asks), 1)

    def test_full_scan_checkbox_ignores_cursor(self):
        self._run(batch_full_scan=True)
        self.assertEqual(self.calls, ['deck:"DeckA"'])
        self.assertEqual(len(self.asks), 1)
        self.assertNotIn("fast scan", self.asks[0])

    def test_selected_cards_never_use_deck_search(self):
        self._run(selected_ids=[7, 8])
        # Explicit selections bypass the deck search AND the cursor filter.
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.asks), 1)
        self.assertIn("Ready to process 2 cards", self.asks[0])

    def test_shipped_config_json_defaults(self):
        with open(os.path.join(PROJECT_ROOT, "addon", "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertTrue(cfg["tag_hinted_notes"])
        self.assertEqual(cfg["hint_tag"], "ai-hints")
        self.assertTrue(cfg["tag_skipped_notes"])
        self.assertFalse(cfg["batch_full_scan"])
        self.assertIn("deck_last_scan_nid", cfg)


class DummyTagNote:
    def __init__(self, tags=None, values=None):
        self.tags = list(tags or [])
        self._values = values or {}

    def values(self):
        return list(self._values.values())


class TestBatchCursorRecording(unittest.TestCase):
    def test_records_cursor_for_deck_and_subdecks(self):
        import json as _json
        import tempfile
        obj = MagicMock()
        obj.selected_card_ids = None

        col = MagicMock()
        col.db = MagicMock()
        col.db.scalar.return_value = 900000
        col.decks = MagicMock()
        col.decks.all_names.return_value = ["DeckA", "DeckA::Sub", "DeckB"]

        mw = MagicMock()
        mw.col = col
        addmgr = MagicMock()
        addmgr.getConfig.return_value = {"deck_last_scan_nid": {}}
        mw.addonManager = addmgr

        # Cursors persist to a dedicated sidecar file (NOT meta.json)
        tmpdir = tempfile.mkdtemp()
        cursor_file = os.path.join(tmpdir, "batch_scan_cursors.json")

        with patch("addon.config_ui.tab_batch.mw", new=mw), \
             patch("addon.config_ui.tab_batch._scan_cursors_path", return_value=cursor_file):
            BatchTabMixin._record_batch_scan_cursor(obj, "DeckA")

        addmgr.writeConfig.assert_not_called()  # meta.json untouched
        with open(cursor_file, "r", encoding="utf-8") as f:
            cursors = _json.load(f)
        self.assertEqual(cursors["DeckA"], 900000)
        self.assertEqual(cursors["DeckA::Sub"], 900000)
        self.assertNotIn("DeckB", cursors)

    def test_selected_cards_never_record_cursor(self):
        obj = MagicMock()
        mw = MagicMock()
        addmgr = MagicMock()
        mw.addonManager = addmgr
        with patch("addon.config_ui.tab_batch.mw", new=mw):
            BatchTabMixin._record_batch_scan_cursor(obj, "Selected Cards")
        addmgr.writeConfig.assert_not_called()


class TestTagAllExisting(unittest.TestCase):
    def test_only_notes_with_hint_data_are_tagged(self):
        already = DummyTagNote(tags=["ai-hints"], values={"f1": "x"})
        with_data = DummyTagNote(tags=[], values={"f1": '<div class="ai-hints-json">{}</div>'})
        without_data = DummyTagNote(tags=[], values={"f1": "plain"})

        col = MagicMock()
        col.find_notes.return_value = [1, 2, 3]
        col.get_note.side_effect = lambda nid: {1: already, 2: with_data, 3: without_data}[nid]

        dialog = MagicMock()
        dialog.hint_tag_edit = MagicMock()
        dialog.hint_tag_edit.text.return_value = "ai-hints"
        dialog._get_maint_search_query = MagicMock(return_value="")

        handler = None
        for klass in [main_dialog.ConfigDialog] + list(main_dialog.ConfigDialog.__mro__):
            if hasattr(klass, "on_tag_all_hinted"):
                handler = getattr(klass, "on_tag_all_hinted")
                break

        mw = MagicMock()
        mw.col = col

        # The handler imports Qt/QApplication/... from `aqt.qt` at call time, which in a
        fake_qt = MagicMock()
        fake_qapp = MagicMock()
        fake_qmsg = MagicMock()
        fake_progress = MagicMock()
        fake_progress.return_value.wasCanceled.return_value = False

        cur_aqt = sys.modules.get("aqt")
        qt_slots = []
        if sys.modules.get("aqt.qt") is not None:
            qt_slots.append(sys.modules["aqt.qt"])
        if cur_aqt is not None and getattr(cur_aqt, "qt", None) is not None:
            qt_slots.append(cur_aqt.qt)
        if not qt_slots:
            qt_slots.append(aqt.qt)

        saved = {}
        for name, val in (("Qt", fake_qt), ("QApplication", fake_qapp),
                          ("QMessageBox", fake_qmsg), ("QProgressDialog", fake_progress)):
            for qt in qt_slots:
                prev = getattr(qt, name, None)
                saved.setdefault(name, []).append((qt, prev))
                setattr(qt, name, val)

        try:
            with patch.object(main_dialog, "mw", mw), \
                 patch.object(main_dialog, "askUser", return_value=True), \
                 patch("addon.reviewer_hooks._note_set_tag", side_effect=_real_set_tag):
                handler(dialog)
        finally:
            for name, entries in saved.items():
                for qt, prev in entries:
                    if prev is None:
                        delattr(qt, name)
                    else:
                        setattr(qt, name, prev)

        self.assertIn("ai-hints", already.tags)
        self.assertIn("ai-hints", with_data.tags)
        self.assertNotIn("ai-hints", without_data.tags)
        self.assertEqual(col.update_note.call_count, 1)


def _real_set_tag(note, tag, add):
    """Mirrors reviewer_hooks._note_set_tag with a plain python note."""
    has = any(t == tag or t.lower() == tag.lower() for t in note.tags)
    if add and not has:
        note.tags.append(tag)
        return True
    elif not add and has:
        note.tags = [t for t in note.tags if t.lower() != tag.lower()]
        return True
    return False


if __name__ == "__main__":
    unittest.main(verbosity=2)