import os
import json
import time
from aqt import mw, gui_hooks
from .ai_client import AIClient
from .card_parser import CardParser
from .config_ui import ADDON_PACKAGE, on_config_dialog
from aqt.qt import QMessageBox, QMenu, QAction, QPoint, Qt, QDialog, QVBoxLayout, QTimer
from .logger import logger, info, tooltip, state
from .batch_manager import initialize_batch_manager

_hooks_registered = False
_generating_card_ids = set()
_just_generated_card_ids = set()
_just_cleared_card_ids = set()
_pregenerated_data = {} # {card_id: data}
_generated_hint_cache = {}
_popup_dialog_instance = None
MAX_HINT_CACHE_SIZE = 200
_current_card_has_data = False

_review_token = 0
_last_undo_time = 0
_reviewer_is_ending = False

_css_cache = None
_js_cache = None

# Addon version loaded once at import time
_ADDON_VERSION: str = ""
try:
    _addon_dir = os.path.dirname(__file__)
    with open(os.path.join(_addon_dir, "VERSION"), "r", encoding="utf-8") as _vf:
        _ADDON_VERSION = _vf.read().strip()
except Exception:
    pass

def get_addon_version() -> str:
    """Return the addon version string (e.g. '1.4.2')."""
    return _ADDON_VERSION

def _apply_results_to_card(card, data, is_manual=True, web=None):
    if not card or not data:
        return False

    if web is None:
        web = getattr(mw.reviewer, "web", None)

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}

    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    data = parser.normalize_hint_data(data)
    if _ADDON_VERSION:
        data["_version"] = _ADDON_VERSION
        
    logger.info(
        "AI-Hints applying data to card %s: %s",
        card.id,
        json.dumps(data, ensure_ascii=False),
    )
        
    note = card.note()
    toggles = {
        "show_hints_button": config.get("show_hints_button", True),
        "show_options_button": config.get("show_options_button", True)
    }
    
    if parser.update_note_with_hints(note, data, toggles, card):
        mw.col.update_note(note)
        _remember_generated_hints(card, data, toggles)
        _just_generated_card_ids.add(card.id)
        
        # Update UI if we are still on the card in this webview
        if web:
            try:
                if not _safe_web_eval(
                    web,
                    f"if (window.aiHintsUpdateData) {{ window.aiHintsUpdateData({json.dumps(data)}, {'true' if is_manual else 'false'}); }}"
                ):
                    raise RuntimeError("webview not available for direct update")
            except Exception as e:
                logger.error(f"AI-Hints direct web update failed: {e}")
                if not _reviewer_is_ending and not _qt_object_is_deleted(web):
                    refresh_current_card(card=card, web=web)
        
        if is_manual and config.get("show_in_popup", False):
            global _popup_dialog_instance
            close_popup_if_open()
            html_content = parser._build_html_block(data)
            _popup_dialog_instance = ResultsPopup(mw, html_content)
            _popup_dialog_instance.show()
            
        return True
    return False

def _trigger_next_pregeneration():
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    if not config.get("auto_generate_new", False) or not config.get("pre_generate_next", True):
        return

    # Don't pre-generate if we are already generating something (priority to current card)
    if _generating_card_ids:
        logger.debug(f"AI-Hints pre-gen: Skipping because active generations exist: {_generating_card_ids}")
        return

    def _task():
        try:
            # SAFETY: Do NOT use mw.col.sched.getCard() here. In v3 scheduler, getCard() 
            # actually takes the card from the queue. Calling it twice (here and then 
            # by the actual reviewer) causes the card to be skipped by the user.
            
            next_card = None
            if hasattr(mw.col.sched, "get_queued_cards"):
                # Modern Anki (2.1.49+) with v3 scheduler
                try:
                    # Fetch more than 1 to skip the current card if it's still in the queue
                    queued = mw.col.sched.get_queued_cards(fetch_limit=5)
                except TypeError:
                    # Fallback for versions where positional or keyword arguments differ
                    try:
                        queued = mw.col.sched.get_queued_cards()
                    except Exception as e:
                        logger.debug(f"AI-Hints pre-gen: get_queued_cards failed: {e}")
                        return
                
                if queued:
                    # In modern Anki, get_queued_cards returns a QueuedCards protobuf object
                    # which has a 'cards' attribute. In older versions or mocks it might be a list.
                    cards = getattr(queued, "cards", queued)
                    if cards and len(cards) > 0:
                        for first_item in cards:
                            cid = getattr(first_item, "card_id", None)
                            if cid is None:
                                # Protobuf version: QueuedCard.card.id
                                inner_card = getattr(first_item, "card", None)
                                cid = getattr(inner_card, "id", None)
                            
                            if cid:
                                # Skip if it's the current card
                                if mw.reviewer.card and cid == mw.reviewer.card.id:
                                    continue
                                
                                next_card = mw.col.get_card(cid)
                                if next_card:
                                    break
            else:
                # Fallback: some old schedulers don't support peeking easily.
                # In this case, it is safer to skip pre-generation than to risk skipping cards.
                logger.debug("AI-Hints pre-gen: get_queued_cards not available, skipping pre-gen to prevent card stealing.")
                return

            if not next_card:
                logger.debug("AI-Hints pre-gen: No next card in queue (or all are current).")
                return

            # Don't pre-gen if already cached or generating
            if next_card.id in _pregenerated_data:
                logger.debug(f"AI-Hints pre-gen: card {next_card.id} already in pregen cache.")
                return
            if next_card.id in _generating_card_ids:
                logger.debug(f"AI-Hints pre-gen: card {next_card.id} already generating.")
                return

            # Check if it needs hints
            if not card_has_hints(next_card):
                logger.info(f"AI-Hints: Triggering pre-generation for next card {next_card.id}")
                # Use a timer or taskman to run generation to avoid blocking
                mw.taskman.run_on_main(lambda: generate_hints(is_manual=False, card=next_card, is_pregen=True))
            else:
                logger.debug(f"AI-Hints pre-gen: card {next_card.id} already has hints.")
        except Exception as e:
            logger.debug(f"AI-Hints pre-gen error in task: {e}")

    # Defer slightly to let UI settle
    QTimer.singleShot(500, _task)
def get_web_assets():
    global _js_cache
    if _js_cache is None:
        addon_dir = os.path.dirname(__file__)
        with open(os.path.join(addon_dir, "web", "template.js"), "r", encoding="utf-8") as f:
            _js_cache = f.read()
    return "", _js_cache

def show_api_error_dialog(provider=None, is_custom=False):
    msg = QMessageBox(mw)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle("AI-Hints")
    if provider is None:
        msg.setText("No AI provider is configured. Add an API key or set the active provider to a running local endpoint.")
    elif is_custom:
        msg.setText(f"API key for custom provider '{provider}' is not configured. Please add it in the add-on config.")
    else:
        msg.setText(f"API key for '{provider}' is not configured. Please add it in the add-on config.")
    
    config_btn = msg.addButton("Open Config", QMessageBox.ButtonRole.ActionRole)
    msg.addButton(QMessageBox.StandardButton.Cancel)
    
    msg.exec()
    if msg.clickedButton() == config_btn:
        on_config_dialog(mw)

def get_addon_dir():
    return os.path.dirname(__file__)

def _card_payload(card):
    if not card:
        return {"id": "", "ord": None}

    try:
        card_id = str(card.id)
    except Exception:
        card_id = ""
    try:
        card_ord = int(card.ord)
    except Exception:
        card_ord = None
    return {"id": card_id, "ord": card_ord}

def _card_context_payload(context):
    card = getattr(context, "card", None)
    if not card:
        card = getattr(context, "_card", None)

    if callable(card):
        try:
            card = card()
        except Exception:
            card = None

    if not card:
        is_reviewer = (
            getattr(context, "name", None) == "reviewer" or
            type(context).__name__ == "Reviewer"
        )
        if is_reviewer:
            card = getattr(mw.reviewer, "card", None)

    return _card_payload(card)

def _card_cache_key(card):
    if not card:
        return None
    try:
        card_id = str(card.id)
    except Exception:
        card_id = ""
    if card_id:
        return ("id", card_id)

    try:
        card_ord = int(card.ord)
    except Exception:
        card_ord = None
    if card_ord is None:
        return None
    return ("ord", card_ord)

def _remember_generated_hints(card, data, toggles):
    key = _card_cache_key(card)
    if key is None:
        return
    _generated_hint_cache[key] = {"data": data, "toggles": toggles or {}}
    while len(_generated_hint_cache) > MAX_HINT_CACHE_SIZE:
        oldest_key = next(iter(_generated_hint_cache))
        del _generated_hint_cache[oldest_key]

def _forget_generated_hints(card):
    key = _card_cache_key(card)
    if key is not None:
        _generated_hint_cache.pop(key, None)

def _cached_hints_for_card(card):
    key = _card_cache_key(card)
    if key is None:
        return None
    return _generated_hint_cache.get(key)

def _qt_object_is_deleted(obj) -> bool:
    if obj is None:
        return True
    for module_name in ("aqt.qt", "PyQt6"):
        try:
            module = __import__(module_name, fromlist=["sip"])
            sip_mod = getattr(module, "sip", None)
            if sip_mod and sip_mod.isdeleted(obj):
                return True
        except Exception:
            pass
    return False

def _safe_web_eval(web, script: str) -> bool:
    if not web or _reviewer_is_ending or _qt_object_is_deleted(web):
        return False
    try:
        page = getattr(web, "page", None)
        if callable(page):
            page_obj = page()
            if _qt_object_is_deleted(page_obj):
                return False
    except Exception:
        pass
    try:
        web.eval(script)
        return True
    except RuntimeError as e:
        logger.debug(f"AI-Hints: skipped eval on closed webview: {e}")
    except Exception as e:
        logger.debug(f"AI-Hints: web eval failed: {e}")
    return False

def _prepare_card_review_state(card):
    if not card:
        return

    to_remove = [cid for cid in _just_generated_card_ids if cid != card.id]
    for cid in to_remove:
        _just_generated_card_ids.discard(cid)

    to_remove_cleared = [cid for cid in _just_cleared_card_ids if cid != card.id]
    for cid in to_remove_cleared:
        _just_cleared_card_ids.discard(cid)

def _set_frontend_generating(web, active, status=None, error_msg=None):
    if not web:
        return
    status_arg = json.dumps(status) if status is not None else "undefined"
    error_arg = json.dumps(error_msg) if error_msg is not None else "undefined"
    _safe_web_eval(web, f"""
        (function() {{
            var active = {json.dumps(bool(active))};
            var status = {status_arg};
            var errorMsg = {error_arg};
            var attempts = 0;
            function applyState() {{
                attempts += 1;
                if (window.aiHintsUiConfig) {{
                    window.aiHintsUiConfig.is_generating = active;
                }}
                if (typeof window.aiHintsSetGenerating === 'function') {{
                    window.aiHintsSetGenerating(active, status, errorMsg);
                    return;
                }}
                if (attempts < 20) setTimeout(applyState, 50);
            }}
            applyState();
        }})();
    """)

def on_webview_will_set_content(web_content, context):
    if type(context).__name__ == "ReviewerBottomBar":
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        if config.get("show_in_bottom_bar", False):
            web_content.body += f"<script>{_bottom_bar_button_script()}</script>"
        return

    # Determine if we are in the reviewer or previewer context
    is_supported = (
        getattr(context, "name", None) in ["reviewer", "previewer"] or 
        type(context).__name__ in ["Reviewer", "Previewer"] or
        (context is None and any("reviewer.css" in c for c in web_content.css))
    )
    
    if not is_supported:
        return

    global _current_card_has_data
    _current_card_has_data = False

    css, js = get_web_assets()

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        target_fields=config.get("target_fields", []),
        note_type_fields=config.get("note_type_fields", {}),
        storage_mode=config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )

    card, web = _get_card_and_web_from_context(context)

    hints_blocks = []
    auto_reveal = False
    if card:
        try:
            # Force reload to ensure we don't have stale data (especially for new cards)
            try:
                card.load()
                note = card.note()
                try:
                    note.load()
                except:
                    pass
            except Exception:
                note = None

            if note:
                # Inject ALL blocks found in the note. The frontend JS will select 
                # the one matching the card ID once the ID is confirmed.
                hints_blocks = parser.find_all_hints_blocks(note)
            
            # If no blocks in note, check cache
            if not hints_blocks:
                cached = _cached_hints_for_card(card)
                if cached:
                    block = parser.build_hints_block(
                        cached.get("data", {}),
                        cached.get("toggles", {}),
                        card,
                    )
                    hints_blocks = [block]
            
            if hints_blocks:
                _current_card_has_data = True
            
            if card.id in _just_generated_card_ids:
                auto_reveal = True
        except Exception as e:
            logger.error(f"Failed to find hints blocks in on_webview_will_set_content: {e}")

    card_payload = json.dumps(_card_payload(card) if card else _card_context_payload(context))
    # Determine if we are currently displaying the back side (answer)
    is_answer = False
    if context and getattr(context, "name", None) == "reviewer":
        is_answer = getattr(mw.reviewer, "state", "") == "answer"
    elif context and getattr(context, "name", None) == "previewer":
        is_answer = getattr(context, "_state", "question") == "answer"

    ui_payload = json.dumps({
        "show_on_card": config.get("show_on_card", True),
        "auto_reveal": auto_reveal,
        "auto_show_hints": config.get("auto_show_hints", False),
        "auto_show_options": config.get("auto_show_options", False),
        "manual_show_hints": config.get("manual_show_hints", True),
        "manual_show_options": config.get("manual_show_options", False),
        "mathjax_format": config.get("mathjax_format", "delimiters"),
        "fix_latex": config.get("fix_latex", False),
        "review_token": _review_token,
        "is_generating": card.id in _generating_card_ids if card else False,
        "shortcuts": config.get("shortcuts", {}),
        "is_answer_side": is_answer
    })

    if config.get("auto_show_hints", False) or config.get("auto_show_options", False):
        logger.info(
            "Auto-show active for card %s (hints=%s, options=%s)",
            card.id if card else "unknown",
            config.get("auto_show_hints", False),
            config.get("auto_show_options", False)
        )

    # Ensure placeholder exists for the unified script to target
    if "<ai-hints" not in web_content.body:
        web_content.body += "<ai-hints></ai-hints>"

    for block in hints_blocks:
        web_content.body += block
    
    # Inject state and the unified template script
    web_content.body += f"""
<script>
window.aiHintsCurrentCard = {card_payload};
window.aiHintsUiConfig = {ui_payload};
{js}
</script>
"""

def _trigger_frontend_setup(card, web=None):
    if not card:
        return
    if _reviewer_is_ending:
        return

    if web is None:
        web = getattr(mw.reviewer, "web", None)

    _prepare_card_review_state(card)

    card_data = {"id": str(card.id), "ord": int(card.ord)}

    # Pass hint data directly so the frontend can render it even if the
    # DOM injection in on_webview_will_set_content was skipped or the
    # JSON block is missing for any reason.
    hint_data = None
    try:
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        parser = CardParser(
            target_fields=config.get("target_fields", []),
            note_type_fields=config.get("note_type_fields", {}),
            storage_mode=config.get("storage_mode", "json"),
            mathjax_format=config.get("mathjax_format", "delimiters"),
            fix_latex=config.get("fix_latex", False)
        )
        # Try memory cache first (fast)
        cached = _cached_hints_for_card(card)
        if cached:
            hint_data = cached.get("data")
        else:
            # Fall back to reading from the note field
            try:
                try:
                    card.load()
                except Exception:
                    pass
                note = card.note()
                try:
                    note.load()
                except Exception:
                    pass
                block_html = parser.find_hints_block(note, card)
                if block_html:
                    import re, html as _html
                    m = re.search(
                        r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
                        block_html, re.DOTALL | re.IGNORECASE
                    )
                    if m:
                        import json as _json
                        raw = _html.unescape(m.group(1) or "")
                        parsed = _json.loads(raw)
                        # Unwrap keyed payload for this card
                        card_ord = getattr(card, "ord", None)
                        if card_ord is not None:
                            card_key = f"c{card_ord + 1}"
                            if isinstance(parsed, dict) and card_key in parsed and "hints" not in parsed:
                                parsed = parsed[card_key]
                        hint_data = parsed
            except Exception as e:
                logger.debug(f"AI-Hints: Could not read note hints in _trigger_frontend_setup: {e}")
    except Exception as e:
        logger.debug(f"AI-Hints: _trigger_frontend_setup hint lookup failed: {e}")

    hint_data_json = json.dumps(hint_data)  # null if no data
    if web:
        _safe_web_eval(web, f"""
            (function() {{
                var data = {json.dumps(card_data)};
                var hintData = {hint_data_json};
                var token = String(data.id) + ':' + String(data.ord) + ':' + {json.dumps(_review_token)};
                window.aiHintsSetupToken = token;
                function applySetup() {{
                    if (window.aiHintsSetupToken !== token) return;
                    window.aiHintsSetup(data, hintData);
                }}
                function trySetup() {{
                    if (typeof window.aiHintsSetup === 'function') {{
                        applySetup();
                    }} else {{
                        setTimeout(trySetup, 50);
                    }}
                }}
                trySetup();
            }})();
        """)

def _get_card_and_web_from_context(context):
    """Helper to extract the active card and web object from various Anki contexts
    (Reviewer, Previewer, etc.)."""
    card = getattr(context, "card", None)
    if not card:
        # Some versions use ._card
        card = getattr(context, "_card", None)
        
    if callable(card):
        # Previewer.card is a method in some Anki versions
        try:
            card = card()
        except Exception:
            card = None
    
    # Final fallback if we have a card id but no card object
    if not card and hasattr(context, "cardId"):
        card_id = getattr(context, "cardId")
        if card_id and mw.col:
            try:
                card = mw.col.get_card(card_id)
            except:
                pass

    web = getattr(context, "web", None)
    if not web:
        # Fallback for internal naming conventions
        web = getattr(context, "_web", None)
    
    # Fallback to global reviewer if context doesn't yield anything
    if not card and mw.reviewer:
        card = mw.reviewer.card
    if not web and mw.reviewer:
        web = mw.reviewer.web
        
    return card, web

def on_webview_did_receive_js_message(handled, message, context):
    card, web = _get_card_and_web_from_context(context)
    
    if message == "ai_hints_generate":
        generate_hints(card=card, web=web)
        return (True, None)
    if message == "ai_hints_clear":
        clear_hints(card=card, web=web)
        return (True, None)
    if message == "ai_hints_refresh":
        refresh_current_card(card=card, web=web)
        return (True, None)
    if message == "ai_hints_restart_speed_focus":
        restart_speed_focus_timer()
        return (True, None)
    if message == "ai_hints_show_menu":
        show_bottom_bar_menu()
        return (True, None)
    return handled

def clear_hints(card=None, web=None):
    if card is None:
        card = mw.reviewer.card
    if not card:
        return

    if web is None:
        web = getattr(mw.reviewer, "web", None)

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    note = card.note()
    _pregenerated_data.pop(card.id, None)
    if parser.clear_hints_from_note(note, card):
        mw.col.update_note(note)
        _forget_generated_hints(card)
        _just_cleared_card_ids.add(card.id)
        logger.info("AI-Hints cleared for card %s", card.id)
        tooltip("AI-Hints: Cleared.")
        if web:
            _safe_web_eval(web, "if (window.aiHintsClearData) { window.aiHintsClearData(); }")
            QTimer.singleShot(
                100,
                lambda: (
                    None if _reviewer_is_ending or _qt_object_is_deleted(web)
                    else refresh_current_card(card=card, web=web)
                )
            )
    elif _cached_hints_for_card(card):
        _forget_generated_hints(card)
        tooltip("AI-Hints: Cleared.")
        if web:
            _safe_web_eval(web, "if (window.aiHintsClearData) { window.aiHintsClearData(); }")
            QTimer.singleShot(
                100,
                lambda: (
                    None if _reviewer_is_ending or _qt_object_is_deleted(web)
                    else refresh_current_card(card=card, web=web)
                )
            )
    else:
        tooltip("AI-Hints: No cached data found to clear.")

def _selected_browser_card_ids(browser):
    selected_cards = getattr(browser, "selectedCards", None)
    if not callable(selected_cards):
        selected_cards = getattr(browser, "selected_cards", None)
    if callable(selected_cards):
        return list(selected_cards())

    table = getattr(browser, "table", None)
    get_selected = getattr(table, "get_selected_card_ids", None)
    if callable(get_selected):
        return list(get_selected())
    return []

def _get_card_from_collection(card_id):
    collection = getattr(mw, "col", None)
    if collection is None:
        return None

    get_card = getattr(collection, "get_card", None)
    if not callable(get_card):
        get_card = getattr(collection, "getCard", None)
    if callable(get_card):
        return get_card(card_id)
    return None

def clear_ai_hints_from_browser_selection(browser):
    card_ids = _selected_browser_card_ids(browser)
    if not card_ids:
        tooltip("AI-Hints: Select one or more cards first.")
        return 0, 0, 0

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )

    notes_by_id = {}
    changed_notes = {}
    changed_cards = 0
    missing_cards = 0

    for card_id in card_ids:
        try:
            card = _get_card_from_collection(card_id)
            if not card:
                missing_cards += 1
                continue

            note_id = getattr(card, "nid", None)
            if note_id is not None and note_id in notes_by_id:
                note = notes_by_id[note_id]
            else:
                note = card.note()
                if note_id is not None:
                    notes_by_id[note_id] = note

            if parser.clear_hints_from_note(note, card):
                changed_cards += 1
                changed_notes[note_id if note_id is not None else id(note)] = note
                _forget_generated_hints(card)
        except Exception as e:
            missing_cards += 1
            logger.error(f"Failed to clear AI-Hints for browser card {card_id}: {e}")

    for note in changed_notes.values():
        try:
            note.flush()
        except Exception as e:
            logger.error(f"Failed to flush note after clearing AI-Hints from browser: {e}")

    if changed_notes:
        refresh_browser = getattr(browser, "onReset", None)
        if callable(refresh_browser):
            try:
                refresh_browser()
            except Exception as e:
                logger.error(f"Failed to refresh browser after clearing AI-Hints: {e}")

    if changed_cards:
        tooltip(
            f"AI-Hints: Cleared cached data from {changed_cards} "
            f"selected card{'s' if changed_cards != 1 else ''}."
        )
    elif missing_cards:
        tooltip("AI-Hints: No cached data found on the selected cards.")
    else:
        tooltip("AI-Hints: No cached data found on the selected cards.")

    return len(card_ids), changed_cards, len(changed_notes)

def on_browser_context_menu(browser, menu):
    menu.addSeparator()
    
    # Action 1: Clear
    act_clear = menu.addAction("Clear AI-Hints")
    act_clear.setEnabled(bool(_selected_browser_card_ids(browser)))
    act_clear.triggered.connect(lambda _checked=False, b=browser: clear_ai_hints_from_browser_selection(b))
    
    # Action 2: Batch Generation UI (Main entry point)
    act_batch_ui = menu.addAction("✨ Batch Generation...")
    act_batch_ui.setEnabled(bool(_selected_browser_card_ids(browser)))
    act_batch_ui.triggered.connect(
        lambda _checked=False, b=browser: on_config_dialog(mw, tab_index=4, card_ids=_selected_browser_card_ids(b))
    )
    

def update_bottom_bar_button(card=None):
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    reviewer = getattr(mw, "reviewer", None)
    bottom = getattr(getattr(reviewer, "bottom", None), "web", None)
    if not bottom:
        return

    if not config.get("show_in_bottom_bar", False):
        try:
            bottom.eval("""
                (function() {
                    const legacySlot = document.getElementById('ai-hints-bottom-slot');
                    if (legacySlot) {
                        legacySlot.remove();
                    }
                    const spacer = document.getElementById('ai-hints-bottom-spacer');
                    if (spacer) {
                        spacer.remove();
                    }
                    const group = document.getElementById('ai-hints-bottom-group');
                    const button = document.getElementById('ai-hints-bottom-button');
                    if (group && button) {
                        button.remove();
                        const parentCell = group.closest('td');
                        const children = Array.from(group.childNodes);
                        if (parentCell) {
                            parentCell.replaceChildren(...children);
                        }
                    }
                })();
            """)
        except Exception as e:
            logger.error(f"Failed to remove AI-Hints bottom button: {e}")
        return

    try:
        bottom.eval(_bottom_bar_button_script())
    except Exception as e:
        logger.error(f"Failed to add AI-Hints bottom button: {e}")

def _bottom_bar_button_script() -> str:
    return """
        (function() {
            const legacySlot = document.getElementById('ai-hints-bottom-slot');
            if (legacySlot) {
                legacySlot.remove();
            }
            if (document.getElementById('ai-hints-bottom-button')) {
                return;
            }

            const editBtn = document.querySelector("button[onclick*=\\"pycmd('edit')\\"], input[onclick*=\\"pycmd('edit')\\"]");
            const editCell = editBtn ? editBtn.closest('td') : null;
            const middle = document.getElementById('middle');
            if (!editBtn || !editCell || !middle) {
                return;
            }

            function cloneReviewButton(source, text) {
                const cloned = source.cloneNode(true);
                cloned.removeAttribute('id');
                cloned.title = 'AI-Hints';
                if (cloned.tagName === 'INPUT') {
                    cloned.value = text;
                } else {
                    cloned.textContent = text;
                }
                return cloned;
            }

            const aiBtn = cloneReviewButton(editBtn, 'AI Hints');
            aiBtn.id = 'ai-hints-bottom-button';
            aiBtn.removeAttribute('onclick');
            aiBtn.style.marginLeft = '0';
            aiBtn.onclick = function(event) {
                if (typeof pycmd === 'function') {
                    pycmd('ai_hints_show_menu');
                }
                event.preventDefault();
                event.stopPropagation();
            };

            const group = document.createElement('div');
            group.id = 'ai-hints-bottom-group';
            group.style.display = 'inline-flex';
            group.style.alignItems = 'flex-start';
            group.style.whiteSpace = 'nowrap';
            group.appendChild(editBtn);
            group.appendChild(aiBtn);
            editCell.replaceChildren(group);

            const placeholderCell = document.createElement('td');
            placeholderCell.id = 'ai-hints-bottom-spacer';
            placeholderCell.className = 'stat';
            placeholderCell.align = 'center';
            placeholderCell.vAlign = 'top';
            placeholderCell.setAttribute('aria-hidden', 'true');

            const placeholderBtn = cloneReviewButton(editBtn, 'AI Hints');
            placeholderBtn.removeAttribute('onclick');
            placeholderBtn.tabIndex = -1;
            placeholderBtn.disabled = true;
            placeholderBtn.style.marginLeft = '0';
            placeholderBtn.style.visibility = 'hidden';
            placeholderBtn.style.pointerEvents = 'none';
            placeholderCell.appendChild(placeholderBtn);

            middle.insertAdjacentElement('afterend', placeholderCell);
        })();
    """

def _find_speed_focus_module():
    import sys
    candidates = [
        "1046608507.reviewer",
        "speed_focus_mode.reviewer",
    ]
    for name in candidates:
        module = sys.modules.get(name)
        if module and hasattr(module, "set_answer_timeouts"):
            return module

    for module in list(sys.modules.values()):
        if (
            getattr(module, "PYCMD_IDENTIFIER", None) == "spdf"
            and hasattr(module, "set_answer_timeouts")
            and hasattr(module, "set_question_timeouts")
        ):
            return module
    return None

def restart_speed_focus_timer():
    sfm = _find_speed_focus_module()
    if not sfm:
        return

    try:
        reviewer = mw.reviewer
        if not reviewer or not reviewer.card:
            return

        if reviewer.state == "question":
            sfm.clear_answer_timeouts(reviewer)
            sfm.clear_question_timeouts(reviewer)
            sfm.set_answer_timeouts(reviewer)
        elif reviewer.state == "answer":
            sfm.clear_answer_timeouts(reviewer)
            sfm.clear_question_timeouts(reviewer)
            sfm.set_question_timeouts(reviewer)
    except Exception as e:
        logger.error(f"Failed to restart Speed Focus timer: {e}")

def refresh_current_card(card=None, web=None):
    if _reviewer_is_ending or (web is not None and _qt_object_is_deleted(web)):
        return

    reviewer = getattr(mw, "reviewer", None)
    
    if card:
        _forget_generated_hints(card)
        _pregenerated_data.pop(card.id, None)
        try:
            card.load()
            card.note().load()
        except Exception:
            pass
    
    # If we have a specific web view (e.g. Previewer), try to refresh it
    if web and card:
        # For Previewer, we can often just trigger a re-render
        # But if it's the reviewer, we use the specialized logic below
        if reviewer and web == reviewer.web:
            pass # Use standard reviewer logic
        else:
            # For other webviews, trigger frontend setup to sync data
            _trigger_frontend_setup(card, web=web)
            return

    if not reviewer or not getattr(reviewer, "card", None):
        return

    try:
        old_card = reviewer.card
        timer_started = getattr(
            old_card,
            "timer_started",
            getattr(old_card, "timerStarted", None),
        )

        get_card = getattr(getattr(mw, "col", None), "getCard", None)
        if callable(get_card):
            reviewer.card = get_card(old_card.id)
        else:
            try:
                old_card.load()
            except Exception:
                pass

        if timer_started is not None and getattr(reviewer, "card", None):
            if hasattr(reviewer.card, "timer_started"):
                reviewer.card.timer_started = timer_started
            else:
                reviewer.card.timerStarted = timer_started

        # Force the current face to redraw so newly-saved hints appear on the
        # question side immediately instead of waiting for Show Answer.
        state = getattr(reviewer, "state", None)
        if state == "question":
            show_question = getattr(reviewer, "_showQuestion", None)
            if callable(show_question):
                show_question()
                return
        elif state == "answer":
            show_answer = getattr(reviewer, "_showAnswer", None)
            if callable(show_answer):
                show_answer()
                return

        if hasattr(reviewer, "refresh") and callable(reviewer.refresh):
            reviewer.refresh()
            return

        redraw = getattr(reviewer, "_redraw_current_card", None)
        if callable(redraw):
            redraw()
            return
    except Exception as e:
        logger.error(f"Failed to refresh reviewer card: {e}")

def show_bottom_bar_menu():
    reviewer = getattr(mw, "reviewer", None)
    if not reviewer or not reviewer.card:
        return

    menu = QMenu(mw)
    
    # 1. Show Hint
    a_hint = QAction("Show Hint", menu)
    a_hint.triggered.connect(lambda: reviewer.web.eval(_click_ai_hints_action_script("toggle-hints")))
    menu.addAction(a_hint)
    
    # 2. Show Options
    a_opts = QAction("Show Options", menu)
    a_opts.triggered.connect(lambda: reviewer.web.eval(_click_ai_hints_action_script("toggle-options")))
    menu.addAction(a_opts)
    
    menu.addSeparator()

    # 3. Refresh
    a_refresh = QAction("Refresh", menu)
    a_refresh.triggered.connect(refresh_current_card)
    menu.addAction(a_refresh)
    
    # 4. Regenerate
    a_regen = QAction("Regenerate All", menu)
    a_regen.triggered.connect(generate_hints)
    menu.addAction(a_regen)
    
    menu.addSeparator()
    
    # 5. Config
    a_config = QAction("Settings...", menu)
    a_config.triggered.connect(lambda: on_config_dialog(mw))
    menu.addAction(a_config)
    
    # Position menu above the bottom bar button
    # This is a bit tricky with webview buttons, so we'll just show it at cursor for now
    menu.exec(QPoint(mw.cursor().pos()))

def _click_ai_hints_action_script(action: str) -> str:
    selector = json.dumps(f'[data-ai-hints-action="{action}"]')
    return f"""
        (function() {{
            const button = document.querySelector({selector});
            if (button && !button.disabled) {{
                button.click();
            }}
        }})();
    """

class ResultsPopup(QDialog):
    def __init__(self, parent, html_content):
        super().__init__(parent)
        self.mw = mw  # Fix: Attribute 'toolbarWeb' access in eventFilter
        self.toolbarWeb = getattr(mw, "toolbarWeb", None)
        self.setWindowTitle("AI Results")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)
        self.web = mw.reviewer.web.__class__(self)
        layout.addWidget(self.web)
        self.web.setHtml(f"<html><head><style>body {{ font-family: sans-serif; }}</style></head><body>{html_content}</body></html>")
        self.resize(400, 300)

def close_popup_if_open():
    global _popup_dialog_instance
    if _popup_dialog_instance:
        _popup_dialog_instance.close()
        _popup_dialog_instance = None

def generate_hints(is_manual=True, card=None, is_pregen=False, web=None):
    if card is None:
        card = mw.reviewer.card
    if not card:
        return
        
    if web is None:
        web = getattr(mw.reviewer, "web", None)

    card_id = getattr(card, "id", None)
    if card_id in _generating_card_ids:
        if not is_pregen and web:
            # If we arrive at a card already being pre-generated, 
            # just trigger the UI animation so the user sees the progress.
            _set_frontend_generating(web, True)
        return
    
    # Priority: If ANY card is currently generating and this is a pre-gen, abort.
    # Current card (manual or auto) always has priority.
    if is_pregen and _generating_card_ids:
        return

    _generating_card_ids.add(card_id)

    restart_speed_focus_timer()

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    
    provider = config.get("ai_provider", "openai")

    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    client = AIClient(config)
    if not client.has_any_ready_provider():
        _generating_card_ids.discard(card_id)
        if not is_pregen:
            is_custom = provider in (config.get("custom_providers") or {})
            show_api_error_dialog(provider if provider else None, is_custom=is_custom)
            # Stop animation in frontend
            _set_frontend_generating(web, False)
        return

    front, back = parser.get_note_content(card.note(), card)
    if not front and not back:
        _generating_card_ids.discard(card_id)
        logger.info("AI-Hints: Skipping generation for card %s as no content was found (likely a missing cloze).", card_id)
        return

    logger.info("AI-Hints generation started for card %s using provider: %s (manual=%s, pregen=%s)", card_id, provider, is_manual, is_pregen)
    
    if is_manual:
        # User explicitly asked for generation; clear any active emergency stop
        state.GLOBAL_STOP = False

    # Trigger animation in frontend only if not pre-generating
    if not is_pregen and web:
        _set_frontend_generating(web, True)

    def on_done(data):
        try:
            if not mw.col:
                return

            if state.GLOBAL_STOP:
                logger.info(f"AI-Hints: Generation aborted for card {card_id} via Emergency Stop signal.")
                # Clear animation
                if not is_pregen:
                    _set_frontend_generating(web, False)
                return

            if is_pregen:
                if data and (data.get("hints") or data.get("options")):
                    logger.info(
                        "AI-Hints pre-generation response for card %s: %s",
                        card_id,
                        json.dumps(data, ensure_ascii=False),
                    )
                    # If by the time it finished, the card is ALREADY on screen, 
                    # apply it immediately instead of just caching.
                    current_reviewer_card = getattr(mw.reviewer, "card", None)
                    if current_reviewer_card and current_reviewer_card.id == card_id:
                         logger.info(f"AI-Hints: Pre-generation finished while card {card_id} is on screen. Applying immediately.")
                         _apply_results_to_card(card, data, is_manual=False, web=web)
                    else:
                        _pregenerated_data[card_id] = data
                        logger.info(f"AI-Hints: Pre-generation complete for card {card_id}. Cached in memory.")
                return

            # Only discard if the user moved to a DIFFERENT card.
            # If mw.reviewer.card is None, it likely means Anki is closing or the user left the reviewer;
            # in these cases, we still want to save the generated hints.
            current_reviewer_card = getattr(mw.reviewer, "card", None)
            if current_reviewer_card and current_reviewer_card.id != card.id:
                logger.info("AI-Hints: User moved to another card. Discarding generated data to prevent database and undo conflicts.")
                # Still need to clear the generating flag in the frontend if it's currently active
                _set_frontend_generating(web, False)
                return

            if not data or (not data.get("hints") and not data.get("options")):
                if data is None:
                    data = {}
                err_status = data.get("_ai_error_type") or "Failed"
                err_msg = data.get("_ai_error_msg", "")
                
                # Safely update frontend to transition from animation -> feedback -> rest state
                try:
                    _set_frontend_generating(web, False, err_status, err_msg)
                except Exception:
                    pass
                
                # Do NOT refresh_current_card() here. It breaks DOM animations 
                # and previously caused recursion bugs by reading the lock before cleanup.
                return

            if _apply_results_to_card(card, data, is_manual=is_manual, web=web):
                # IMPORTANT: Discard current card from generating set BEFORE trying to pre-gen next.
                # Otherwise _trigger_next_pregeneration will see this card and abort.
                _generating_card_ids.discard(card_id)

                # If we just finished the current card, and pre-generation is on, 
                # try to pre-generate for the NEXT card now.
                if not is_manual:
                    _trigger_next_pregeneration()
            else:
                _generating_card_ids.discard(card_id)
                try:
                    _set_frontend_generating(web, False, "Failed")
                except Exception: pass
                info("AI-Hints: No hints or options were generated.")
        finally:
            # Safety discard in case of unexpected exceptions before our manual discards
            _generating_card_ids.discard(card_id)

    import threading

    def run_async():
        import socket
        import urllib.error
        try:
            res = client.generate_options(front, back)
            mw.taskman.run_on_main(lambda: on_done(res))
        except Exception as e:
            logger.error(f"AI-Hints generation error: {e}")
            
            is_network = False
            if isinstance(e, (socket.timeout, ConnectionError, TimeoutError)):
                is_network = True
            elif isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError):
                is_network = True
            
            payload = {
                "hints": [], 
                "options": [], 
                "_ai_error_type": "Offline" if is_network else "Failed",
                "_ai_error_msg": str(e)
            }
            mw.taskman.run_on_main(lambda: on_done(payload))

    threading.Thread(target=run_async, daemon=True).start()

def card_has_hints(card):
    if not card:
        return False
    
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        target_fields=config.get("target_fields", []),
        note_type_fields=config.get("note_type_fields", {}),
        storage_mode=config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    try:
        # Check cache first
        if _cached_hints_for_card(card):
            return True
        # Check note
        return bool(parser.find_hints_block(card.note(), card))
    except Exception:
        return False

def _card_saved_version(card) -> str:
    """Return the addon version string stored inside the card's JSON block.
    Returns an empty string if no version was recorded (i.e. generated before
    version tracking was introduced).
    """
    if not card:
        return ""
    # Check in-memory cache first
    cached = _cached_hints_for_card(card)
    if cached:
        data = cached.get("data") or {}
        ver = data.get("_version", "")
        if ver:
            return str(ver)
    try:
        import re
        import html as _html
        note = card.note()
        for field_val in getattr(note, "fields", []):
            if not isinstance(field_val, str):
                continue
            m = re.search(
                r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
                field_val, re.DOTALL | re.IGNORECASE
            )
            if m:
                raw = _html.unescape(m.group(1) or "")
                try:
                    parsed = json.loads(raw)
                    # Handle keyed payload (cloze)
                    card_ord = getattr(card, "ord", None)
                    if card_ord is not None:
                        card_key = f"c{card_ord + 1}"
                        if isinstance(parsed, dict) and card_key in parsed:
                            parsed = parsed[card_key]
                    return str(parsed.get("_version", ""))
                except Exception:
                    pass
    except Exception:
        pass
    return ""

def _version_less_than(v1: str, v2: str) -> bool:
    """Return True if version string v1 is strictly less than v2.
    Compares as tuples of integers (major, minor, patch).
    An empty or unparseable version is treated as 0.0.0.
    """
    def _parse(v: str):
        try:
            parts = [int(x) for x in str(v).strip().lstrip("v").split(".")]
            # Pad to 3 components
            while len(parts) < 3:
                parts.append(0)
            return tuple(parts[:3])
        except Exception:
            return (0, 0, 0)
    return _parse(v1) < _parse(v2)

def trigger_js_click(text_contains: str, emoji: str) -> None:
    web = getattr(mw.reviewer, "web", None)
    if not web:
        return
    js = f"""
    (function() {{
        const btns = document.querySelectorAll('.ai-hints-btn');
        for (const btn of btns) {{
            const txt = btn.textContent || "";
            if (txt.includes("{text_contains}") || txt.includes("{emoji}")) {{
                btn.click();
                break;
            }}
        }}
    }})();
    """
    _safe_web_eval(web, js)

def on_state_shortcuts_will_change(state: str, shortcuts: list) -> None:
    if state != "review":
        return

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    shortcuts_cfg = config.get("shortcuts", {})
    if not shortcuts_cfg:
        return

    modifier = shortcuts_cfg.get("modifier", "alt")

    def get_shortcut_string(mod: str, key: str) -> str:
        if not key:
            return ""
        key_str = key.strip().upper()
        if not key_str:
            return ""
        if mod == "none":
            return key_str
        return f"{mod.capitalize()}+{key_str}"

    # 1. generate
    gen_key = shortcuts_cfg.get("generate", "")
    if gen_key:
        gen_sc = get_shortcut_string(modifier, gen_key)
        if gen_sc:
            shortcuts.append((gen_sc, lambda: generate_hints(is_manual=True)))

    # 2. toggle-options
    opt_key = shortcuts_cfg.get("toggle-options", "")
    if opt_key:
        opt_sc = get_shortcut_string(modifier, opt_key)
        if opt_sc:
            shortcuts.append((opt_sc, lambda: trigger_js_click("Options", "🎯")))

    # 3. toggle-hints
    hints_key = shortcuts_cfg.get("toggle-hints", "")
    if hints_key:
        hints_sc = get_shortcut_string(modifier, hints_key)
        if hints_sc:
            shortcuts.append((hints_sc, lambda: trigger_js_click("Hints", "💡")))

    # 4. clear
    clear_key = shortcuts_cfg.get("clear", "")
    if clear_key:
        clear_sc = get_shortcut_string(modifier, clear_key)
        if clear_sc:
            shortcuts.append((clear_sc, lambda: clear_hints()))

    # 5. refresh
    refresh_key = shortcuts_cfg.get("refresh", "")
    if refresh_key:
        refresh_sc = get_shortcut_string(modifier, refresh_key)
        if refresh_sc:
            shortcuts.append((refresh_sc, lambda: refresh_current_card()))

    # 6. show-json
    json_key = shortcuts_cfg.get("show-json", "")
    if json_key:
        json_sc = get_shortcut_string(modifier, json_key)
        if json_sc:
            shortcuts.append((json_sc, lambda: trigger_js_click("JSON", "📝")))

def init_hooks():
    global _hooks_registered, _reviewer_is_ending
    if _hooks_registered:
        return
    _reviewer_is_ending = False
    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(on_webview_did_receive_js_message)
    gui_hooks.browser_will_show_context_menu.append(on_browser_context_menu)
    gui_hooks.state_shortcuts_will_change.append(on_state_shortcuts_will_change)
    
    # Initialize background tracking layer for ongoing batch processing jobs
    try:
        initialize_batch_manager()
    except Exception as _e:
        logger.error(f"Failed to init batch manager: {_e}")
    
    # Bottom bar button
    gui_hooks.reviewer_did_show_question.append(update_bottom_bar_button)
    gui_hooks.reviewer_did_show_answer.append(update_bottom_bar_button)
    
    # Frontend setup trigger
    def on_show_question(card):
        global _review_token, _reviewer_is_ending
        _reviewer_is_ending = False
        _review_token += 1
        _trigger_frontend_setup(card)
        
        # Auto generate for new cards if configured and no data exists
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        
        # 1. Check if we have pre-generated data for THIS card
        if card.id in _pregenerated_data:
            data = _pregenerated_data.pop(card.id)
            logger.info(f"AI-Hints: Applying pre-generated data for card {card.id}")
            _apply_results_to_card(card, data, is_manual=False)
            # Now that this card is done, pre-generate the NEXT one
            _trigger_next_pregeneration()
            return

        if config.get("auto_generate_new", False) and card:
            # Skip auto-generation if we just undid something
            if time.time() - _last_undo_time < 0.5:
                logger.info("AI-Hints: Skipping auto-generation because of recent undo.")
                return

            # Skip if manually cleared during this view
            if card.id in _just_cleared_card_ids:
                logger.info(f"AI-Hints: Skipping auto-generation for card {card.id} because it was just manually cleared.")
                return

            needs_generation = not card_has_hints(card)
            force_regen = config.get("auto_regenerate_all", False)

            # Version-gated regeneration: regenerate if the version stored on
            # the card is older than the configured minimum version.
            regen_old = False
            if (
                not force_regen
                and config.get("auto_regenerate_if_old_version", False)
                and card_has_hints(card)
            ):
                min_ver = config.get("auto_regenerate_min_version", "").strip()
                saved_ver = _card_saved_version(card)
                if min_ver and _version_less_than(saved_ver, min_ver):
                    regen_old = True
                    logger.info(
                        "AI-Hints: Card %s saved version '%s' < min '%s'; queuing regeneration.",
                        card.id, saved_ver, min_ver
                    )

            if needs_generation or force_regen or regen_old:
                logger.info(f"AI-Hints: Auto-generating hints for card {card.id} (force_regen={force_regen}, regen_old={regen_old}).")
                generate_hints(is_manual=False, card=card)
            else:
                # Current card is already good. Pre-generate the NEXT one.
                _trigger_next_pregeneration()

    gui_hooks.reviewer_did_show_question.append(on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_trigger_frontend_setup)
    
    # Close popup on next card or when leaving reviewer
    def _on_reviewer_end():
        global _reviewer_is_ending
        _reviewer_is_ending = True
        close_popup_if_open()
        _pregenerated_data.clear()
        
    gui_hooks.reviewer_did_show_question.append(lambda _card: close_popup_if_open())
    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.profile_will_close.append(_on_reviewer_end)
    
    # Sync UI and caches on undo operations
    def on_undo(changes):
        global _last_undo_time
        _last_undo_time = time.time()
        
        if mw.reviewer and mw.reviewer.card:
            card = mw.reviewer.card
            _forget_generated_hints(card)
            _trigger_frontend_setup(card)
            # Anki already refreshes the card face on undo; 
            # calling refresh_current_card here can cause 'UndoEmpty' warnings 
            # and redundant auto-generation loops.

    gui_hooks.state_did_undo.append(on_undo)
    
    _hooks_registered = True
