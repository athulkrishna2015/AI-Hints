import os
import threading
import time
from aqt import mw
from aqt.utils import askUser
from aqt.qt import *
from ..logger import logger, info, tooltip
from .widgets import ADDON_PACKAGE

from ..config_io import atomic_write_json, read_json_file, _ADDON_DIR

ENTIRE_COLLECTION = "🗂️ Entire Collection"

# Per-deck incremental-scan cursors used to be stored inside meta.json. They are
# written on every batch run, so they now live in their own sidecar file to keep
# that high-frequency write off meta.json (which holds api_keys/providers).
SCAN_CURSORS_FILENAME = "batch_scan_cursors.json"


def _scan_cursors_path():
    """Cursor sidecar lives in the profile data dir so it survives updates."""
    try:
        from ..config_io import resolve_data_file

        return resolve_data_file(SCAN_CURSORS_FILENAME)
    except Exception:
        return os.path.join(_ADDON_DIR, SCAN_CURSORS_FILENAME)


def _load_scan_cursors():
    """Load per-deck scan cursors from the sidecar file, migrating from meta.json
    on first run so existing cursors are preserved."""
    data = read_json_file(_scan_cursors_path())
    if isinstance(data, dict):
        return data
    try:
        from ..config_io import read_meta_config
        legacy = (read_meta_config() or {}).get("deck_last_scan_nid")
        if isinstance(legacy, dict):
            atomic_write_json(_scan_cursors_path(), legacy)
            return legacy
    except Exception:
        pass
    return {}


def _save_scan_cursors(cursors):
    atomic_write_json(_scan_cursors_path(), cursors)


def _subtree_deck_names(deck_name):
    """Return deck_name plus every deck directly or indirectly beneath it."""
    try:
        names = mw.col.decks.all_names()
    except Exception:
        return [deck_name]
    prefix = deck_name + "::"
    return [deck_name] + [d for d in names if d.startswith(prefix)]

class BatchTabMixin:
    def _create_batch_tab(self):
        """Constructs the Tab 5: Batch Generation UI"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(6, 6, 6, 6)

        # -- 1. START GROUP --
        start_group = QGroupBox("Start New Batch Generation")
        s_layout = QFormLayout()

        # 🔄 Generation Method Toggle Group
        method_widget = QWidget()
        method_layout = QHBoxLayout(method_widget)
        method_layout.setContentsMargins(0,0,0,0)
        
        self.method_bg_grp = QButtonGroup(self)
        
        self.rb_local_queue = QRadioButton("Sequential Local Queue (Recommended)")
        self.rb_local_queue.setChecked(True)
        self.rb_local_queue.setToolTip("Processes cards one-by-one in the background. Supports ALL providers and honors full fallback settings. Free-tier friendly!")
        
        self.rb_native_async = QRadioButton("Native Async API (Cloud)")
        self.rb_native_async.setToolTip("Bundles requests to cloud provider. Faster, but requires paid tier/billing linked and excludes fallbacks.")
        
        self.method_bg_grp.addButton(self.rb_local_queue)
        self.method_bg_grp.addButton(self.rb_native_async)
        method_layout.addWidget(self.rb_local_queue)
        method_layout.addWidget(self.rb_native_async)
        
        s_layout.addRow("Method Type:", method_widget)
        
        # ℹ️ Info Warning label that flips based on choice
        self.batch_desc_label = QLabel("💡 Uses standard local background loop. Perfectly respects your fallback tree and works on all free keys.")
        self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        self.batch_desc_label.setWordWrap(True)
        s_layout.addRow("", self.batch_desc_label)

        # 🚀 Provider Override Selector
        self.batch_provider_cb = QComboBox()
        self.batch_provider_cb.addItem("⚡ Standard Config (Follows Fallback Matrix)")
        # Load list of active providers
        from ..ai_client import PROVIDER_ORDER
        seen = set()
        for prov in PROVIDER_ORDER:
             if prov in seen:
                  continue
             seen.add(prov)
             self.batch_provider_cb.addItem(prov.capitalize(), prov)
        if "local" not in seen:
             self.batch_provider_cb.addItem("Local", "local")
        
        s_layout.addRow("Force Provider:", self.batch_provider_cb)

        # 🎯 Specific Model Override Selector
        self.batch_model_cb = QComboBox()
        self.batch_model_cb.setEditable(True)
        self.batch_model_cb.addItem("⚡ System Default (Configured Primary Model)")
        self.batch_model_cb.setToolTip("Choose a specific model to use for this batch. Leaves blank to use your configured default for the provider.")
        s_layout.addRow("Force Model:", self.batch_model_cb)
        
        # Dynamic Model Suggestions connector
        self.batch_provider_cb.currentIndexChanged.connect(self._update_batch_model_suggestions)

        # 📦 Searchable Embedded Deck Selector
        self.batch_deck_chooser = QComboBox()
        self.batch_deck_chooser.setEditable(True)
        self.batch_deck_chooser.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # Cap the popup so a large deck list never spans the whole screen; typing
        # still searches via the completer below.
        self.batch_deck_chooser.setMaxVisibleItems(16)
        self.batch_deck_chooser.setToolTip(
            "Type to search decks (substring, case-insensitive) or pick from the "
            "list. A deck includes all of its sub-decks for batching."
        )
        try:
            self.batch_deck_chooser.lineEdit().setPlaceholderText("Search decks…")
        except Exception:
            pass

        # Load decks once, then populate both the chooser and its completer with
        # the same list so the special "Entire Collection" entry is searchable too.
        try:
            all_decks = list(mw.col.decks.all_names())
        except Exception:
            all_decks = []

        self.batch_deck_chooser.addItem(ENTIRE_COLLECTION)
        self.batch_deck_chooser.addItems(all_decks)
        # Pre-select current active deck in main window
        if curr := getattr(self, "selected_deck_name", None) or self._current_deck_name():
            if curr in all_decks or curr == ENTIRE_COLLECTION:
                self.batch_deck_chooser.setCurrentText(curr)

        # Searchable autocomplete: filters the deck list by substring as you type.
        # Uses a dedicated model (Entire Collection + all decks) with an explicit
        # Popup completion mode so typed substrings reliably narrow the list.
        completer = QCompleter([ENTIRE_COLLECTION] + all_decks, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(16)
        try:
            completer.popup().setMaximumHeight(320)
        except Exception:
            pass
        self.batch_deck_chooser.setCompleter(completer)
        self.batch_deck_chooser.currentTextChanged.connect(self._on_deck_chooser_changed)

        s_layout.addRow("Source Deck:", self.batch_deck_chooser)
        
        self.batch_skip_existing_cb = QCheckBox("Skip cards that already have AI Hints generated")
        self.batch_skip_existing_cb.setChecked(True)
        s_layout.addRow(self.batch_skip_existing_cb)

        # ⏱ Incremental scan: by default only cards created since this deck's last FULL batch
        # scan are processed (per-deck cursor, so sub-decks each get a fresh start). The optional
        # FULL scan checkbox ignores the cursor and re-checks every card in the deck.
        self.batch_full_scan_cb = QCheckBox("🧹 Force FULL scan (ignore last-scan cursor)")
        self.batch_full_scan_cb.setToolTip(
            "Fast mode (default) skips cards that were created before this deck's most recent "
            "FULL batch scan, making batch scanning nearly instant.\n\n"
            "The last-scan cursor is tracked PER-DECK, so each sub-deck is scanned independently "
            "and older notes moved into a sub-deck are never wrongly skipped by another deck's "
            "scan time.\n\n"
            "Use this checkbox to force a FULL scan that ignores the cursor and re-checks every "
            "card in the selected deck."
        )
        self.batch_full_scan_cb.setChecked(self.config.get("batch_full_scan", False))
        s_layout.addRow(self.batch_full_scan_cb)

        # Version-gated Batch Regeneration control
        self.batch_regen_version_cb = QCheckBox("└─ Except if Generated Version < ")
        self.batch_regen_version_cb.setStyleSheet("margin-left: 15px;")
        self.batch_regen_version_cb.setToolTip("If checked, cards with hints will still be queued for batching if their stored version is older than the target.")
        self.batch_regen_version_cb.setChecked(False)
        
        self.batch_regen_min_version_edit = QLineEdit()
        self.batch_regen_min_version_edit.setPlaceholderText("e.g. 1.4.2")
        self.batch_regen_min_version_edit.setFixedWidth(80)
        
        # Load initial default from current main config values
        self.batch_regen_min_version_edit.setText(self.config.get("auto_regenerate_min_version", ""))

        batch_version_row = QHBoxLayout()
        batch_version_row.setContentsMargins(15, 0, 0, 0)
        batch_version_row.addWidget(self.batch_regen_version_cb)
        batch_version_row.addWidget(self.batch_regen_min_version_edit)
        batch_version_row.addStretch()
        s_layout.addRow(batch_version_row)
        
        # 🔢 Batch Limit
        self.batch_limit_spin = QSpinBox()
        self.batch_limit_spin.setRange(1, 1000000)
        self.batch_limit_spin.setValue(self.config.get("batch_limit", 1000))
        self.batch_limit_spin.setSuffix(" cards")
        s_layout.addRow("Batch Limit:", self.batch_limit_spin)
        
        # 🧵 Multithreading
        self.batch_multithread_cb = QCheckBox("Concurrent Multi-Provider Generation (Multithreaded)")
        self.batch_multithread_cb.setToolTip("Generates cards in parallel using all of your ready and enabled providers. Bypasses provider overrides.")
        self.batch_multithread_cb.setChecked(self.config.get("multithread_providers", False))
        s_layout.addRow(self.batch_multithread_cb)
        
        self.batch_regen_version_cb.toggled.connect(
            lambda enabled: self.batch_regen_min_version_edit.setEnabled(enabled)
        )
        self.batch_regen_min_version_edit.setEnabled(False)
        
        self.batch_skip_existing_cb.toggled.connect(
            lambda checked: self.batch_regen_version_cb.setEnabled(checked)
        )
        
        self.method_bg_grp.buttonClicked.connect(self._on_batch_method_changed)
        
        start_group.setLayout(s_layout)
        layout.addWidget(start_group)
        
        # -- 1.5 REGENERATE BY MODEL GROUP --
        regen_group = QGroupBox("🎯 Regenerate Cards by Stored Model")
        regen_group.setStyleSheet("QGroupBox { margin-bottom: 0px; padding-bottom: 0px; }")
        rg_layout = QFormLayout()
        rg_layout.setContentsMargins(6, 0, 6, 0)
        rg_layout.setVerticalSpacing(2)

        self.regen_model_edit = QLineEdit()
        self.regen_model_edit.setPlaceholderText("e.g. gpt-oss-120b")
        self.regen_model_edit.setToolTip(
            "Model name that was used to generate hints on the cards you want to regenerate. "
            "The collection is only scanned when you click 'Scan & Queue Regeneration', so "
            "there is no up-front full-collection scan when opening this window."
        )
        rg_layout.addRow("Stored Model:", self.regen_model_edit)

        self.regen_force_model_edit = QLineEdit()
        self.regen_force_model_edit.setPlaceholderText("(blank = use Force Model above)")
        self.regen_force_model_edit.setToolTip(
            "Optional. If set, regenerated cards force this exact model (it is fused into the "
            "Force Model / provider override above). Leave blank to use the batch Force Model settings."
        )
        rg_layout.addRow("Regenerate with:", self.regen_force_model_edit)

        self.regen_scan_btn = QPushButton("🔁 Scan & Queue Regeneration")
        self.regen_scan_btn.setAutoDefault(False)
        self.regen_scan_btn.setStyleSheet("font-weight: bold;")
        self.regen_scan_btn.clicked.connect(self.on_regen_by_model_clicked)
        rg_layout.addRow(self.regen_scan_btn)

        self.regen_progress_bar = QProgressBar()
        self.regen_progress_bar.setRange(0, 0)  # indeterminate busy animation
        self.regen_progress_bar.setFormat("Scanning… (%v of %m)")
        self.regen_progress_bar.setVisible(False)
        rg_layout.addRow("", self.regen_progress_bar)

        self.regen_status_label = QLabel("")
        self.regen_status_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        self.regen_status_label.setWordWrap(True)
        rg_layout.addRow("", self.regen_status_label)

        regen_group.setLayout(rg_layout)
        layout.addWidget(regen_group)
        
        # NOTE: no auto-scan of the collection at dialog open — a synchronous
        # full-collection scan on the GUI thread freezes the config window.
        # The collection is only scanned on demand when the user clicks the
        # "Scan & Queue Regeneration" button.
        
        # -- 2. ACTIVE GROUP --
        active_group = QGroupBox("Running & Pending Batches")
        a_layout = QVBoxLayout()
        a_layout.setContentsMargins(4, 0, 4, 4)
        a_layout.setSpacing(2)

        # Batch queue control buttons sit on top of the batch job logs, above the
        # status list. Created here (not the footer) so the batch tab's state logic
        # (_refresh_batch_controls) can reference them during construction.
        batch_btn_row = QHBoxLayout()
        batch_btn_row.setSpacing(4)
        self.batch_run_btn = QPushButton("🚀 Initiate Queue")
        self.batch_run_btn.setAutoDefault(False)
        self.batch_run_btn.setMinimumHeight(30)
        self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
        self.batch_run_btn.clicked.connect(self.on_batch_control_clicked)
        batch_btn_row.addWidget(self.batch_run_btn)

        self.pause_local_btn = QPushButton("⏸️ Pause Queue")
        self.pause_local_btn.setAutoDefault(False)
        self.pause_local_btn.setMinimumHeight(30)
        self.pause_local_btn.setVisible(False)
        self.pause_local_btn.clicked.connect(self.on_toggle_pause_local_queue)
        batch_btn_row.addWidget(self.pause_local_btn)

        self.stop_local_btn = QPushButton("🛑 Stop & Discard Queue")
        self.stop_local_btn.setAutoDefault(False)
        self.stop_local_btn.setMinimumHeight(30)
        self.stop_local_btn.setStyleSheet("color: #dc3545; font-weight: bold;")
        self.stop_local_btn.clicked.connect(self.on_stop_local_queue)
        batch_btn_row.addWidget(self.stop_local_btn)

        self.refresh_status_btn = QPushButton("🔄 Refresh Status")
        self.refresh_status_btn.setAutoDefault(False)
        self.refresh_status_btn.setMinimumHeight(30)
        self.refresh_status_btn.clicked.connect(self.update_batch_status_tab)
        batch_btn_row.addWidget(self.refresh_status_btn)

        batch_btn_row.addStretch()
        a_layout.addLayout(batch_btn_row)

        self.batch_list_view = QTextBrowser()
        self.batch_list_view.setReadOnly(True)
        self.batch_list_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.batch_list_view.setPlaceholderText("No active native batch tracking handles found.")
        self.batch_list_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.batch_list_view.setOpenExternalLinks(False)
        self.batch_list_view.anchorClicked.connect(self._on_log_link_clicked)
        a_layout.addWidget(self.batch_list_view)
        active_group.setLayout(a_layout)
        layout.addWidget(active_group)
        
        layout.addStretch()
        
        self._on_batch_method_changed()
        
        self._batch_scroll = QScrollArea()
        self._batch_scroll.setWidgetResizable(True)
        self._batch_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_content = QWidget()
        scroll_content.setLayout(layout)
        self._batch_scroll.setWidget(scroll_content)
        
        main_layout = QVBoxLayout(tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._batch_scroll)
        
        return tab

    def _update_batch_model_suggestions(self):
        """Pulls available pre-seeded list suggestions from shared constants file."""
        self.batch_model_cb.clear()
        self.batch_model_cb.addItem("⚡ System Default (Configured Primary Model)")
        
        combo_idx = self.batch_provider_cb.currentIndex()
        if combo_idx <= 0:
             return
             
        prov = self.batch_provider_cb.itemData(combo_idx)
        if prov:
             from ..ai_client import MODEL_SUGGESTIONS
             suggs = MODEL_SUGGESTIONS.get(prov, [])
             for s in suggs:
                  self.batch_model_cb.addItem(s)

    def _on_batch_method_changed(self):
        """Updates descriptions, buttons, and valid providers when toggle flips."""
        self._refresh_batch_controls()

    def _refresh_batch_controls(self):
        """Unified UI state manager for the main batch button and descriptions."""
        from ..batch_manager import batch_manager
        
        is_cloud = self.rb_native_async.isChecked()
        is_active = getattr(batch_manager, "local_queue_active", False)
        is_paused = getattr(batch_manager, "local_queue_paused", False)
        has_saved = bool(getattr(batch_manager, "local_queue", []))

        if is_cloud:
            self.batch_desc_label.setText("⚠️ Uses Cloud Native API. Requires **PAID ACCOUNT** / linked billing. Currently ONLY Gemini supports this schema. Closes fast.")
            self.batch_desc_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 11px; margin-bottom: 5px;")
            self.pause_local_btn.setVisible(False)
            self.batch_run_btn.setEnabled(True)
            self.batch_run_btn.setText("🚀 Submit Cloud Batch")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #0d6efd; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            return

        # Local Queue Logic: the Initiate/Resume button and the Pause button are
        # separate controls. Initiating is always allowed — while a queue is running
        # or paused it adds another batch to the job list (processed in order), and
        # the Pause button is the only pause/resume toggle.
        if is_active:
            self.batch_run_btn.setEnabled(True)
            self.batch_run_btn.setText("🚀 Initiate Queue")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            self.batch_run_btn.setToolTip("Starts another batch and appends it to the running queue; it is processed after the current work finishes.")
            self.pause_local_btn.setVisible(True)
            if is_paused:
                self.pause_local_btn.setText("▶️ Resume Queue")
                self.pause_local_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            else:
                self.pause_local_btn.setText("⏸️ Pause Queue")
                self.pause_local_btn.setStyleSheet("font-weight: bold; background-color: #ffc107; color: black; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            
            self.batch_desc_label.setText("💡 Uses standard local background loop. Perfectly respects your fallback tree, works on all free keys! (Anki must stay open)")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        
        elif has_saved:
            self.batch_run_btn.setEnabled(True)
            self.batch_run_btn.setText("⏯️ Resume Saved Queue")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #fd7e14; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            self.pause_local_btn.setVisible(False)
            self.batch_desc_label.setText("💾 Found an unfinished offline batch from a previous session! Click below to Resume.")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")
        
        else:
            self.batch_run_btn.setEnabled(True)
            self.batch_run_btn.setText("🚀 Initiate Queue")
            self.batch_run_btn.setStyleSheet("font-weight: bold; background-color: #198754; color: white; border-radius: 4px; padding-left: 10px; padding-right: 10px;")
            self.pause_local_btn.setVisible(False)
            self.batch_desc_label.setText("💡 Uses standard local background loop. Perfectly respects your fallback tree, works on all free keys! (Anki must stay open)")
            self.batch_desc_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11px; margin-bottom: 5px;")

    def update_batch_status_tab(self):
        try:
            from ..batch_manager import batch_manager
            
            # Sync Unified Button UI State
            self._refresh_batch_controls()

            summary = batch_manager.get_status_summary()
            
            # 🚦 Selection Safety: If user is currently selecting text, DO NOT update
            # as it will clear their selection and make navigation/copying impossible.
            if self.batch_list_view.textCursor().hasSelection():
                return

            if hasattr(self, "selected_card_ids") and self.selected_card_ids and not batch_manager.local_queue_active:
                count = len(self.selected_card_ids)
                selection_html = (
                    f"<div style='font-size:12px; padding-bottom:4px;'>"
                    f"<span style='color:#0d6efd;'><b>📋 PENDING SELECTION</b></span>"
                    f"</div>"
                    f"Ready to process <b>{count}</b> selected cards from browser.<br/>"
                    f"<i>Click 'Initiate Queue' or 'Start' to begin.</i><br/>"
                    f"<hr style='border:0; border-top:1px solid #ccc; margin:8px 0;'/>"
                )
                if summary and "No active batch jobs" not in summary:
                    summary = selection_html + summary
                else:
                    summary = selection_html

            if not summary:
                  summary = "<i>(Ready to initialize)</i>"
                  
            self._set_batch_log_preserving_scroll(summary)
                  
        except Exception:
            pass

    def _set_batch_log_preserving_scroll(self, summary):
        """Render the batch log without snapping the view to the top.

        If the user had already scrolled to the bottom we keep them pinned to the
        bottom (so newly appended lines stay visible); otherwise we keep their
        current scrolled position untouched.
        """
        try:
            sb = self.batch_list_view.verticalScrollBar()
            was_at_bottom = sb.maximum() <= 0 or sb.value() >= sb.maximum() - 2
            self.batch_list_view.setHtml(summary)
            if was_at_bottom:
                sb.setValue(sb.maximum())
            else:
                current = sb.value()
                QTimer.singleShot(0, lambda v=current: self.batch_list_view.verticalScrollBar().setValue(v))
        except Exception:
            try:
                self.batch_list_view.setHtml(summary)
            except Exception:
                pass

    def _on_log_link_clicked(self, qurl):
        """Intercepts clicks on anchor tags and routes to native Anki Browser actions."""
        url = qurl.toString().strip()
        if url.startswith("browse:"):
             query = url.split(":", 1)[1] 
             from aqt import dialogs
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
        
        elif url.startswith("discard:"):
             try:
                  cid = int(url.split(":")[2])
                  from ..batch_manager import batch_manager
                  if batch_manager.discard_from_queue(cid):
                       tooltip(f"🗑️ Card {cid} discarded from queue.")
                       self.update_batch_status_tab()
             except Exception as e:
                  logger.error(f"Failed to discard card from batch UI: {e}")

        elif url.startswith("job_cancel:"):
             try:
                  job_id = url.split(":", 1)[1]
                  from ..batch_manager import batch_manager
                  if batch_manager.discard_job(job_id):
                       tooltip("🗑️ Queued job canceled.")
                       self.update_batch_status_tab()
             except Exception as e:
                  logger.error(f"Failed to cancel job from batch UI: {e}")
                  
        elif url.startswith("job_up:"):
             try:
                  job_id = url.split(":", 1)[1]
                  from ..batch_manager import batch_manager
                  if batch_manager.move_job_up(job_id):
                       self.update_batch_status_tab()
             except Exception as e:
                  logger.error(f"Failed to move job up: {e}")
                  
        elif url.startswith("job_down:"):
             try:
                  job_id = url.split(":", 1)[1]
                  from ..batch_manager import batch_manager
                  if batch_manager.move_job_down(job_id):
                       self.update_batch_status_tab()
             except Exception as e:
                  logger.error(f"Failed to move job down: {e}")
                  
        elif url == "job_clear_all":
             try:
                  from ..batch_manager import batch_manager
                  from aqt.utils import askUser
                  if askUser("Are you sure you want to clear all queued jobs?"):
                       batch_manager.clear_all_queued_jobs()
                       tooltip("🗑️ All queued jobs cleared.")
                       self.update_batch_status_tab()
             except Exception as e:
                  logger.error(f"Failed to clear all queued jobs: {e}")

    def on_batch_control_clicked(self):
        # Start/resume always works — while a queue is running or paused clicking
        # Initiate appends a new batch to the job list. Pause/resume lives on the
        # dedicated pause button.
        self.on_start_config_batch()

    def on_toggle_pause_local_queue(self):
        from ..batch_manager import batch_manager
        
        if self.rb_native_async.isChecked() or not batch_manager.local_queue_active:
            return
        new_pause = not batch_manager.local_queue_paused
        batch_manager.set_pause_local_queue(new_pause)
        tooltip("⏸️ Local Queue Paused" if new_pause else "▶️ Local Queue Resumed")
        self._refresh_batch_controls()

    def on_stop_local_queue(self):
        from ..batch_manager import batch_manager
        has_pending = hasattr(self, "selected_card_ids") and self.selected_card_ids
        if not batch_manager.local_queue_active and not batch_manager.local_queue and not has_pending:
             info("There is no active queue, saved queue, or pending selection.")
             return
             
        confirm_msg = "Are you sure you want to STOP and CLEAR the local sequential queue?\n\nRemaining queued cards will be discarded."
        if has_pending and not batch_manager.local_queue_active and not batch_manager.local_queue:
             confirm_msg = "Discard the pending card selection from the browser?"
             
        if askUser(confirm_msg):
             batch_manager.stop_local_queue()
             self.selected_card_ids = None
             self.batch_deck_chooser.setEnabled(True)
             self.batch_deck_chooser.setEditable(False)
             self._refresh_deck_list()
             self._refresh_batch_controls()
             self.update_batch_status_tab()

    def _refresh_deck_list(self):
        try:
            current_text = self.batch_deck_chooser.currentText()
            self.batch_deck_chooser.clear()
            all_decks = mw.col.decks.all_names()
            self.batch_deck_chooser.addItem(ENTIRE_COLLECTION)
            self.batch_deck_chooser.addItems(all_decks)
            try:
                comp = self.batch_deck_chooser.completer()
                if comp is not None:
                    from PyQt6.QtCore import QStringListModel
                    comp.setModel(QStringListModel([ENTIRE_COLLECTION] + all_decks))
                    comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                    comp.setFilterMode(Qt.MatchFlag.MatchContains)
            except Exception:
                pass
            
            # 1. First, check if currentText is a valid deck name
            if current_text in all_decks:
                 self.batch_deck_chooser.setCurrentText(current_text)
                 return
                 
            # 2. Otherwise, check if we have a valid saved selected_deck_name
            saved_deck = getattr(self, "selected_deck_name", None)
            if saved_deck in all_decks:
                 self.batch_deck_chooser.setCurrentText(saved_deck)
                 return
                 
            # 3. Last fallback: Anki's current selected deck
            curr = mw.col.decks.current().get('name', '')
            if curr in all_decks:
                 self.batch_deck_chooser.setCurrentText(curr)
        except: pass
        # Ensure searchable state is restored even after a clear
        try:
            self.batch_deck_chooser.setEditable(True)
            self.batch_deck_chooser.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            if not self.batch_deck_chooser.completer():
                from PyQt6.QtCore import QStringListModel
                all_decks = mw.col.decks.all_names() if hasattr(mw, "col") and mw.col else []
                comp = QCompleter([ENTIRE_COLLECTION] + all_decks, self)
                comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                comp.setFilterMode(Qt.MatchFlag.MatchContains)
                comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
                comp.setMaxVisibleItems(16)
                try:
                    comp.popup().setMaximumHeight(320)
                except Exception:
                    pass
                self.batch_deck_chooser.setCompleter(comp)
        except Exception:
            pass

    def _current_deck_name(self):
        """Return the name of the deck currently active in Anki's main window, or ''."""
        try:
            cur = mw.col.decks.current()
            if cur:
                return cur.get("name", "") or ""
        except Exception:
            pass
        return ""

    def _on_deck_chooser_changed(self, text):
        text = text.strip()
        # Avoid saving the temporary "Selected Cards" or "(Selected: X cards)" values
        if text and not text.startswith("Selected") and not text.startswith("(Selected:"):
            try:
                all_decks = mw.col.decks.all_names()
                if text in all_decks:
                    self.selected_deck_name = text
            except:
                pass

    def _record_batch_scan_cursor(self, deck_name):
        """Persist a per-deck "last full scan" cursor (max note id) for this deck + all its
        sub-decks. Called on a full, eligible batch pass so each deck keeps an independent
        timestamp and a later scan of a sub-deck never skips its older cards wrongly."""
        if not deck_name or deck_name in ("Selected Cards", ENTIRE_COLLECTION):
            return
        try:
            max_nid = 0
            try:
                max_nid = int(mw.col.db.scalar("SELECT COALESCE(MAX(id), 0) FROM notes") or 0)
            except Exception:
                max_nid = 0
            if max_nid <= 0:
                return
            cursors = dict(_load_scan_cursors())
            for name in _subtree_deck_names(deck_name):
                cursors[name] = max_nid
            _save_scan_cursors(cursors)
            logger.info(f"AI-Hints Batch: advanced per-deck scan cursor to {max_nid} for {deck_name}")
        except Exception as e:
            logger.error(f"Failed to record batch scan cursor: {e}")

    def set_selected_deck(self, deck_name):
        """External hook to select a specific deck in the Batch tab."""
        self.selected_deck_name = deck_name
        self.selected_card_ids = None
        
        self.batch_deck_chooser.setEnabled(True)
        self.batch_deck_chooser.setEditable(False)
        self._refresh_deck_list()
        
        all_decks = []
        try:
            all_decks = mw.col.decks.all_names()
        except: pass
        
        if deck_name in all_decks:
            self.batch_deck_chooser.setCurrentText(deck_name)
            
        self.update_batch_status_tab()

    def update_batch_ui_for_selection(self):
        """Called when external cards are passed into the dialog from browser."""
        if not hasattr(self, "selected_card_ids") or not self.selected_card_ids:
            return
            
        count = len(self.selected_card_ids)
        # Update Deck Chooser to reflect selection
        self.batch_deck_chooser.setEditable(True)
        self.batch_deck_chooser.lineEdit().setText(f"(Selected: {count} cards)")
        self.batch_deck_chooser.setEnabled(False)
        
        # Switch method to Local Queue by default for broad compatibility
        # unless user already specifically chose Cloud
        if not self.rb_native_async.isChecked():
            self.rb_local_queue.setChecked(True)
            self._on_batch_method_changed()

        self.update_batch_status_tab()

    def on_regen_by_model_clicked(self):
        from ..batch_manager import batch_manager
        from ..reviewer_hooks import find_cards_by_stored_model, clear_ai_hints_for_cards

        model = self.regen_model_edit.text().strip()
        if not model:
            info("Type the model name used to generate the hints you want to regenerate.")
            return

        self.regen_status_label.setText(f"Scanning collection for model '{model}'…")
        self.regen_scan_btn.setEnabled(False)
        self.regen_progress_bar.setVisible(True)
        self.regen_progress_bar.setValue(0)

        def _update_progress(scanned, total, matched):
            # Keep the indeterminate bar animating and show live counts by
            # pumping the event loop from within the synchronous scan.
            self.regen_progress_bar.setMaximum(total)
            self.regen_progress_bar.setValue(scanned)
            self.regen_status_label.setText(f"Scanning for '{model}'… {scanned}/{total} (matched {matched})")
            QApplication.processEvents()

        # Scope the scan to the chosen source: the browser selection, or the
        # deck selected in the Batch Generation deck chooser.
        scope_note_ids = None
        scope_card_ids = None
        scope_label = "collection"
        if hasattr(self, "selected_card_ids") and self.selected_card_ids:
            scope_card_ids = set(self.selected_card_ids)
            try:
                nids = set()
                for cid in self.selected_card_ids:
                    c = mw.col.get_card(cid)
                    if c:
                        nids.add(c.nid)
                scope_note_ids = list(nids)
            except Exception as e:
                logger.error(f"AI-Hints: Failed to resolve selected card notes: {e}")
                scope_card_ids = None
            scope_label = f"selection ({len(self.selected_card_ids)} cards)"
        else:
            deck_name = self.batch_deck_chooser.currentText().strip()
            valid_decks = mw.col.decks.all_names()
            if deck_name == ENTIRE_COLLECTION:
                scope_note_ids = None
                scope_label = "entire collection"
            elif deck_name and deck_name in valid_decks:
                try:
                    scope_note_ids = mw.col.find_notes(f'deck:"{deck_name}"')
                except Exception as e:
                    logger.error(f"AI-Hints: Deck lookup failed for scan scope: {e}")
                    scope_note_ids = None
                scope_label = f'deck "{deck_name}"'

        try:
            card_ids = find_cards_by_stored_model(
                model,
                progress_cb=_update_progress,
                update_every=10,
                note_ids=scope_note_ids,
                card_ids=scope_card_ids,
            )
        except Exception as e:
            logger.error(f"AI-Hints: Regenerate-by-model scan failed: {e}")
            card_ids = []
        finally:
            self.regen_progress_bar.setVisible(False)

        self.regen_scan_btn.setEnabled(True)

        if not card_ids:
            self.regen_status_label.setText(f"No cards found generated with '{model}'.")
            info(f"No cards found generated with model '{model}'.")
            return

        force_model = self.regen_force_model_edit.text().strip()

        limit = self.batch_limit_spin.value()
        chunked = card_ids[:limit]
        excess = len(card_ids) - limit

        confirm = (
            f"Found <b>{len(card_ids)}</b> card(s) generated with model "
            f"<b>{model}</b> (in {scope_label}).\n\n"
            f"This will CLEAR their current AI hints and queue them for regeneration "
            f"via the local background queue."
        )
        if force_model:
            confirm += f"\n\nForce model: <b>{force_model}</b>"
        else:
            confirm += f"\n\nModel: leave the batch **Force Model** selection to decide."
        if excess > 0:
            confirm += f"\n\n(Note: only the first {limit} will be queued; {excess} skipped by the limit.)"
        confirm += "\n\nProceed with scanning & queuing?"

        if not askUser(confirm):
            self.regen_status_label.setText("Cancelled.")
            return

        if hasattr(self, "save_config"):
            try:
                self.save_config(close=False)
            except Exception:
                pass

        # 1. Clear the stored hints so the batch queue can write fresh data.
        try:
            cleared_res = clear_ai_hints_for_cards(chunked)
        except Exception as e:
            logger.error(f"AI-Hints: Failed to clear hints for regenerate-by-model: {e}")
            info(f"Failed to clear AI hints: {e}")
            return

        # 2. Build config with an optional model override (mirrors the main batch path).
        config = self.config.copy()
        config["multithread_providers"] = self.batch_multithread_cb.isChecked()

        combo_idx = self.batch_provider_cb.currentIndex()
        prov_override = None
        if combo_idx > 0:
            prov_override = self.batch_provider_cb.itemData(combo_idx)
        target_prov = prov_override or config.get("ai_provider", "openai")

        chosen_force = force_model or (
            self.batch_model_cb.currentText().strip()
            if self.batch_model_cb.currentText().strip() and "⚡" not in self.batch_model_cb.currentText()
            else ""
        )
        if chosen_force:
            current_models = config.get("models", {})
            if not isinstance(current_models, dict):
                current_models = {}
            else:
                current_models = current_models.copy()
            current_models[target_prov] = chosen_force
            config["models"] = current_models
            logger.info(f"AI-Hints Regenerate-by-model: forcing {target_prov} -> {chosen_force}")

        from ..ai_client import AIClient
        client = AIClient(config)
        if not client.has_any_ready_provider():
            info("No configured API Keys found! Visit Provider settings first.")
            return

        started = batch_manager.start_local_sequential_queue(
            chunked, config, provider_override=prov_override
        )
        if started:
            self.regen_status_label.setText("")
            QTimer.singleShot(500, self._focus_batch_log)
        else:
            self.regen_status_label.setText("Failed to start the regeneration queue.")

    def _focus_batch_log(self):
        """Switch to the Batch tab and scroll its live log to the bottom so the
        running activity is immediately visible (used right after starting a queue)."""
        try:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == "Batch Generation":
                    self.tabs.setCurrentIndex(i)
                    break
        except Exception:
            pass
        self.update_batch_status_tab()
        QTimer.singleShot(200, self._scroll_batch_log_to_bottom)

    def _scroll_batch_log_to_bottom(self):
        try:
            sb = self.batch_list_view.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass
        # Scroll the outer tab scroll area so the "Running & Pending Batches"
        # panel (with the live logs) is actually on screen after starting a queue.
        try:
            outer = getattr(self, "_batch_scroll", None)
            if outer is not None:
                osb = outer.verticalScrollBar()
                osb.setValue(osb.maximum())
        except Exception:
            pass

    def on_start_config_batch(self):
        from ..batch_manager import batch_manager

        tag_filter_msg = ""
        # Set to True when the source scan covered the WHOLE (eligible) deck, i.e. it was
        # not a cursor-limited fast scan. A full pass lets us advance the per-deck cursor so
        # the next run can be incremental. Never advanced for "Selected Cards"/"Entire Collection".
        full_scan_done = False

        # 1. Handle selection from browser if present
        if hasattr(self, "selected_card_ids") and self.selected_card_ids:
            source_cids = list(self.selected_card_ids)
            deck_name = "Selected Cards"
        else:
            # Traditional deck-based search
            if not self.rb_native_async.isChecked() and not batch_manager.local_queue_active and batch_manager.local_queue:
                 count = len(batch_manager.local_queue)
                 res = askUser(
                      f"💾 **UNFINISHED BATCH DETECTED**\n\n"
                      f"Found {count} cards waiting from your previous session.\n\n"
                      f"• Click 'Yes' to RESUME processing these cards.\n"
                      f"• Click 'No' to DISCARD the old queue and start a fresh batch."
                 )
                 if res:
                      started = batch_manager.start_local_sequential_queue(card_ids=None) 
                      if started:
                           QTimer.singleShot(500, self._focus_batch_log)
                           self._on_batch_method_changed() 
                      return
                 else:
                      batch_manager.stop_local_queue() 

            deck_name = self.batch_deck_chooser.currentText().strip()
            is_entire = deck_name == ENTIRE_COLLECTION
            all_valid_decks = mw.col.decks.all_names()
            if not is_entire and deck_name not in all_valid_decks:
                 info(f"⚠️ Deck not found: '{deck_name}'\nPlease select a valid deck from the list.")
                 return

            if not deck_name:
                 info("Please select a deck first.")
                 return
                 
            tag_filter_msg = ""
            if is_entire:
                try:
                    source_cids = mw.col.find_cards("")
                except Exception as e:
                    logger.error(f"Full collection search failed: {e}")
                    source_cids = []
                tag_filter_msg = f" (entire collection: {len(source_cids)} cards)"
            else:
                try:
                    source_cids = mw.col.find_cards(f"deck:\"{deck_name}\"")
                except Exception as e:
                    logger.error(f"Deck search failed: {e}")
                    source_cids = []

                # ⏱️ Incremental fast scan: skip notes created before this deck's last FULL batch scan.
                # The cursor is tracked per-deck (and per-sub-deck), so sub-decks are never wrongly
                # skipped by other deck's (or a global) scan timestamp.
                #
                # NOTE: Anki's search syntax only accepts exact numbers (or a comma-separated list)
                # for `nid:` / `cid:` — operators like `nid:>` or `nid:1-5` are REJECTED with
                # "expected only digits and commas in nid:". So we resolve the new note ids in
                # Python and filter via the valid comma-list form.
                try:
                    cursors = _load_scan_cursors()
                    cursor = int(cursors.get(deck_name, 0) or 0)
                    want_full = hasattr(self, "batch_full_scan_cb") and self.batch_full_scan_cb.isChecked()
                    if want_full:
                        # Forced FULL pass: covers the whole deck, so it may advance the cursor.
                        full_scan_done = True
                        tag_filter_msg = ""
                    elif cursor:
                        new_nids = [n for n in mw.col.find_notes(f'deck:"{deck_name}"') if n > cursor]
                        if new_nids:
                            source_cids = mw.col.find_cards(f'deck:"{deck_name}" nid:{",".join(map(str, new_nids))}')
                            tag_filter_msg = f" (fast scan: {len(source_cids)} candidates - notes created since the last full scan of this deck)"
                        else:
                            source_cids = []
                            tag_filter_msg = " (fast scan: no new notes since the last full scan of this deck)"
                    else:
                        # No cursor yet (first scan of this deck): full pass, may advance the cursor.
                        full_scan_done = True
                        tag_filter_msg = ""
                except Exception as e:
                    logger.error(f"Cursor-based batch filtering failed, falling back to full scan: {e}")
                    # Do NOT advance the cursor on a failed cursor read.
                    tag_filter_msg = " (cursor read failed → full scan)"

        try:
            if not source_cids:
                logger.info(f"AI-Hints Batch Scan: deck='{deck_name}' total_scanned=0 found_for_generation=0 (no matching cards)")
                info(f"No cards found for processing ({deck_name}).")
                return
                
            skipped_count = 0
            if self.batch_skip_existing_cb.isChecked():
                from aqt.qt import Qt, QProgressDialog, QApplication
                from ..card_parser import CardParser

                final_ids = []
                use_ver_gate = self.batch_regen_version_cb.isChecked()
                min_ver = self.batch_regen_min_version_edit.text().strip()

                try:
                    _cfg = self.config if isinstance(getattr(self, "config", None), dict) else {}
                    _parser = CardParser(
                        mathjax_format=_cfg.get("mathjax_format", "delimiters"),
                        fix_latex=_cfg.get("fix_latex", False),
                    )
                except Exception:
                    from ..reviewer_hooks import card_has_hints as _fallback_has_hints
                    _parser = None

                progress = QProgressDialog("Scanning deck for eligible cards...", "Cancel", 0, len(source_cids), self)
                progress.setWindowTitle("AI Hints - Card Scanner")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                # Prevent spurious wasCanceled() from window-close/ESC — handle
                # only explicit Cancel clicks; keep dialog responsive via processEvents
                try:
                    progress.setCancelButton(None)
                except Exception:
                    pass
                try:
                    progress.setAutoClose(False)
                    progress.setAutoReset(False)
                except Exception:
                    pass

                # Fast path: group sibling cloze cards by note so each note is
                # loaded and parsed once. Falls back to per-card checks on error.
                try:
                    # Build cid -> (nid, ord) via a single batched SQL query.
                    cid_to_nid_ord = {}
                    if source_cids:
                        chunk_sz = 900
                        for s in range(0, len(source_cids), chunk_sz):
                            chunk = source_cids[s:s+chunk_sz]
                            placeholders = ",".join("?" for _ in chunk)
                            try:
                                rows = mw.col.db.all(f"SELECT id, nid, ord FROM cards WHERE id IN ({placeholders})", *chunk)
                            except Exception:
                                rows = []
                                for cid in chunk:
                                    try:
                                        c = mw.col.get_card(cid)
                                        if c:
                                            rows.append((c.id, c.nid, c.ord))
                                    except Exception:
                                        pass
                            for r in rows:
                                try:
                                    cid_to_nid_ord[int(r[0])] = (int(r[1]), int(r[2]))
                                except Exception:
                                    pass

                    # Invert to nid -> [(cid, ord)]
                    from collections import defaultdict
                    nid_to_cids = defaultdict(list)
                    orphan_cids = []
                    for cid in source_cids:
                        tup = cid_to_nid_ord.get(cid)
                        if tup is None:
                            orphan_cids.append(cid)
                        else:
                            nid_to_cids[tup[0]].append((cid, tup[1]))

                    total_notes = len(nid_to_cids) + len(orphan_cids)
                    processed_notes = 0
                    last_pump = time.time()

                    # Pre-import version helper lazily
                    _need_version = bool(use_ver_gate and min_ver)
                    if _need_version:
                        from ..reviewer_hooks import _version_less_than as _v_lt
                    else:
                        _v_lt = None

                    for nid, cid_ord_list in list(nid_to_cids.items()):
                        if processed_notes % 10 == 0:
                            now = time.time()
                            if now - last_pump > 0.08:
                                progress.setValue(min(processed_notes * 10, len(source_cids)))
                                progress.setLabelText(f"Scanning notes {processed_notes+1} of {total_notes} ({len(source_cids)} cards)...")
                                QApplication.processEvents()
                                if progress.wasCanceled():
                                    logger.info("AI-Hints Batch: Scanning canceled by user.")
                                    progress.close()
                                    return
                                last_pump = now
                        processed_notes += 1

                        try:
                            note = mw.col.get_note(nid)
                        except Exception:
                            # Note missing -> all its cards are eligible (nothing to skip)
                            for cid, _ in cid_ord_list:
                                final_ids.append(cid)
                            continue

                        # Fast prefilter: if no ai-hints marker at all, skip parsing
                        try:
                            fields = getattr(note, "fields", None)
                            if fields is None and hasattr(note, "values"):
                                fields = list(note.values())
                            has_marker = False
                            if isinstance(fields, (list, tuple)):
                                for f in fields:
                                    if isinstance(f, str) and "ai-hints-json" in f:
                                        has_marker = True
                                        break
                            if not has_marker:
                                for cid, _ in cid_ord_list:
                                    final_ids.append(cid)
                                continue
                        except Exception:
                            pass

                        # Per-card check reusing the same note object
                        for cid, ord_ in cid_ord_list:
                            # Lightweight fake card for parser matching
                            class _FC:
                                __slots__ = ("id","ord","nid","_note")
                                def __init__(self, _id,_ord,_nid,_note):
                                    self.id=_id; self.ord=_ord; self.nid=_nid; self._note=_note
                                def note(self): return self._note
                            fc = _FC(cid, ord_, nid, note)
                            try:
                                block = _parser.find_hints_block(note, fc) if _parser else None
                                has_hints = bool(block)
                            except Exception:
                                # Fallback to legacy helper
                                try:
                                    from ..reviewer_hooks import card_has_hints as _ch
                                    has_hints = bool(_ch(fc))
                                except Exception:
                                    has_hints = False

                            should_process = not has_hints
                            if has_hints and _need_version:
                                try:
                                    # Inline version extraction without extra DB hop
                                    import re as _re, html as _html
                                    from ..card_parser import _safe_loads
                                    saved_ver = ""
                                    for fval in (fields or []):
                                        if not isinstance(fval, str):
                                            continue
                                        for m in _re.finditer(r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>', fval, _re.DOTALL | _re.IGNORECASE):
                                            raw = _html.unescape(m.group(1) or "")
                                            try:
                                                parsed = _safe_loads(raw)
                                            except Exception:
                                                continue
                                            if isinstance(parsed, dict):
                                                card_key = f"c{ord_+1}"
                                                if card_key in parsed and isinstance(parsed[card_key], dict):
                                                    saved_ver = str(parsed[card_key].get("_version",""))
                                                    break
                                                elif "_version" in parsed:
                                                    saved_ver = str(parsed.get("_version",""))
                                                    break
                                        if saved_ver:
                                            break
                                    if _v_lt and _v_lt(saved_ver, min_ver):
                                        should_process = True
                                except Exception:
                                    pass

                            if should_process:
                                final_ids.append(cid)
                            else:
                                skipped_count += 1
                                if skipped_count < 5:
                                    logger.debug(f"AI-Hints Batch: Skipping card {cid} (already has hints).")

                    # Orphan cids that had no cards row (deleted) - treat via fallback
                    for cid in orphan_cids:
                        # Let legacy path decide (will be skipped if card missing)
                        try:
                            from ..reviewer_hooks import _get_card_from_collection, card_has_hints
                            c = _get_card_from_collection(cid)
                            if not c:
                                continue
                            has_hints = card_has_hints(c)
                            should_process = not has_hints
                            if has_hints and _need_version:
                                from ..reviewer_hooks import _card_saved_version, _version_less_than
                                if _version_less_than(_card_saved_version(c), min_ver):
                                    should_process = True
                            if should_process:
                                final_ids.append(cid)
                            else:
                                skipped_count += 1
                        except Exception:
                            final_ids.append(cid)

                    progress.setValue(len(source_cids))
                    try:
                        progress.close()
                    except Exception:
                        try:
                            progress.hide()
                        except Exception:
                            pass
                    logger.info(f"AI-Hints Batch Filtering: Filtered {len(source_cids)} cards -> {len(final_ids)} cards to process ({skipped_count} skipped).")
                except Exception as e:
                    logger.warning(f"AI-Hints Batch fast scan failed ({e}), falling back to per-card scan.")
                    # Fallback: original per-card loop
                    from ..reviewer_hooks import card_has_hints, _get_card_from_collection, _card_saved_version, _version_less_than
                    final_ids = []
                    skipped_count = 0
                    for i, cid in enumerate(source_cids):
                        if i % 10 == 0:
                            progress.setValue(i)
                            progress.setLabelText(f"Scanning card {i+1} of {len(source_cids)}...")
                            QApplication.processEvents()
                            if progress.wasCanceled():
                                logger.info("AI-Hints Batch: Scanning canceled by user.")
                                progress.close()
                                return
                        c = _get_card_from_collection(cid)
                        if not c:
                            continue
                        has_hints = card_has_hints(c)
                        should_process = not has_hints
                        if has_hints and use_ver_gate and min_ver:
                            saved_ver = _card_saved_version(c)
                            if _version_less_than(saved_ver, min_ver):
                                should_process = True
                        if should_process:
                            final_ids.append(cid)
                        else:
                            skipped_count += 1
                    progress.setValue(len(source_cids))
                    try:
                        progress.close()
                    except Exception:
                        try:
                            progress.hide()
                        except Exception:
                            pass
                    logger.info(f"AI-Hints Batch Filtering: Filtered {len(source_cids)} cards -> {len(final_ids)} cards to process ({skipped_count} skipped).")
            else:
                final_ids = list(source_cids)

            logger.info(
                f"AI-Hints Batch Scan: deck='{deck_name}' total_scanned={len(source_cids)} "
                f"found_for_generation={len(final_ids)} skipped={skipped_count}"
                f"{tag_filter_msg}"
            )

            if not final_ids:
                # A full pass found nothing new to generate. The deck was still completely
                # scanned, so advance the per-deck cursor here too — otherwise the NEXT run
                # would re-scan the whole deck again (the deck never gets a cursor because
                # the early return below skips the normal post-queue cursor recording).
                if full_scan_done and deck_name not in ("Selected Cards", ENTIRE_COLLECTION):
                    self._record_batch_scan_cursor(deck_name)
                info("No cards need hint generation (all selected have hints already).")
                return
                
            limit = self.batch_limit_spin.value()
            chunked_ids = final_ids[:limit]
            excess = len(final_ids) - limit

            # Only a full, eligible pass advances the per-deck scan cursor: the deck is wholly
            # scanned (no cards dropped to the safety limit) and it is not a selection run.
            record_cursor = (excess <= 0) and deck_name not in ("Selected Cards", ENTIRE_COLLECTION)

            is_native = self.rb_native_async.isChecked()
            mode_str = "Native Cloud Batch" if is_native else "Local Background Queue"

            confirm_msg = f"Ready to process {len(chunked_ids)} cards using **{mode_str}**."
            if tag_filter_msg:
                confirm_msg += f"\n\n{tag_filter_msg}."
            if excess > 0:
                confirm_msg += f"\n\n(Note: {excess} remaining skipped due to safety limits.)"

            if not askUser(confirm_msg + "\n\nProceed with execution?"):
                return
            
            # Save configuration automatically to persist all settings from UI to disk before starting
            if hasattr(self, "save_config"):
                self.save_config(close=False)
            
            combo_idx = self.batch_provider_cb.currentIndex()
            prov_override = None
            if combo_idx > 0:
                prov_override = self.batch_provider_cb.itemData(combo_idx)

            chosen_model = self.batch_model_cb.currentText().strip()
            model_override = None
            if chosen_model and "⚡" not in chosen_model:
                 model_override = chosen_model
            
            config = self.config.copy()
            config["multithread_providers"] = self.batch_multithread_cb.isChecked()
            target_prov = prov_override or config.get("ai_provider", "openai")
            
            if model_override:
                 current_models = config.get("models", {})
                 if not isinstance(current_models, dict): current_models = {}
                 else: current_models = current_models.copy() 
                 current_models[target_prov] = model_override
                 config["models"] = current_models
                 logger.info(f"Applying transient Batch Model Override: {target_prov} -> {model_override}")

            from ..ai_client import AIClient
            
            client = AIClient(config)
            if not client.has_any_ready_provider():
                 info("No configured API Keys found! Visit Provider settings first.")
                 return

            if not is_native:
                started = batch_manager.start_local_sequential_queue(
                    chunked_ids, 
                    config, 
                    provider_override=prov_override
                )
                if started:
                    if record_cursor:
                        self._record_batch_scan_cursor(deck_name)
                    self.selected_card_ids = None
                    self.batch_deck_chooser.setEnabled(True)
                    self.batch_deck_chooser.setEditable(False)
                    self._refresh_deck_list()
                    QTimer.singleShot(500, self._focus_batch_log)
                return

            else:
                target_prov = prov_override or "gemini"
                if target_prov != "gemini":
                    info(f"❌ Native Cloud Batch is currently NOT supported for provider '{target_prov.upper()}'.\n\nPlease either select 'Gemini' OR switch your Method back to 'Sequential Local Queue'.")
                    return
                
                from ..card_parser import CardParser
                from ..reviewer_hooks import _get_card_from_collection

                parser = CardParser(
                    mathjax_format=config.get("mathjax_format", "delimiters"),
                    fix_latex=config.get("fix_latex", False)
                )
                
                items = []
                actual_cids = []
                
                for cid in chunked_ids:
                    try:
                        card = _get_card_from_collection(cid)
                        if not card: continue
                        f, b = parser.get_note_content(card.note(), card)
                        if not f and not b:
                            continue

                        items.append({
                            "key": str(cid),
                            "system_prompt": config.get("system_prompt", ""),
                            "user_prompt": f"FRONT:\n{f}\n\nBACK:\n{b}"
                        })
                        actual_cids.append(cid)
                    except: pass
                    
                if not items:
                    info("Failed to assemble content payload.")
                    return
                    
                def _bg_run():
                    try:
                        tooltip("Transmitting payload to Google...")
                        resp = client.submit_gemini_batch(items)
                        jname = resp.get("name")
                        if jname:
                            batch_manager.register_job(jname, actual_cids)
                            def _on_success():
                                if record_cursor:
                                    self._record_batch_scan_cursor(deck_name)
                                self.selected_card_ids = None
                                self.batch_deck_chooser.setEnabled(True)
                                self.batch_deck_chooser.setEditable(False)
                                self._refresh_deck_list()
                                self.update_batch_status_tab()
                                info(f"✅ Cloud Batch Initiated: {jname}\nMonitoring setup.")
                            mw.taskman.run_on_main(_on_success)
                        else:
                            mw.taskman.run_on_main(lambda: info("Unknown transmission fault. No tracking ID returned."))
                    except Exception as e:
                        err_msg = str(e)
                        mw.taskman.run_on_main(lambda msg=err_msg: info(msg))
                        
                threading.Thread(target=_bg_run, daemon=True).start()
                
        except Exception as e:
            logger.error(f"Config UI Batch Start Master Error: {e}")
            info(f"Launch failed: {e}")
