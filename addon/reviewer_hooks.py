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

import os, json
from collections import UserDict

class PregenCache(UserDict):
    """Disk-backed dictionary to persist pre-generated data across Anki sessions."""
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self.load()

    def load(self):
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.data = {int(k) if k.isdigit() else k: v for k, v in data.items()}
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to load pregen cache: {e}")

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to save pregen cache: {e}")

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key):
        super().__delitem__(key)
        self.save()

    def pop(self, key, default=None):
        if key in self.data:
            val = super().pop(key)
            self.save()
            return val
        return default

    def clear(self):
        super().clear()
        self.save()

_pregen_cache_path = os.path.join(os.path.dirname(__file__), "pregen_cache.json")
_pregenerated_data = PregenCache(_pregen_cache_path)

_generated_hint_cache = {}
_popup_dialog_instance = None
MAX_HINT_CACHE_SIZE = 200

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

def _apply_results_to_card(card, data, is_manual=True, web=None, skip_redraw=False):
    if not card or not data:
        return False

    # Force reload fresh objects from the collection on the main thread 
    # to ensure we are not working with stale/pre-Undo data.
    try:
        fresh_card = mw.col.get_card(card.id)
        note = fresh_card.note()
    except Exception as e:
        logger.error(f"AI-Hints: Could not reload card {card.id} for saving: {e}")
        return False

    if web is None:
        web = getattr(mw.reviewer, "web", None)

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}

    parser = CardParser(
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    data = parser.normalize_hint_data(data)
    if _ADDON_VERSION:
        data["_version"] = _ADDON_VERSION
        
    logger.debug(
        f"AI-Hints: Applying data to card {fresh_card.id} (Note {note.id}, Ord {fresh_card.ord}, Model {data.get('_model', 'unknown')})"
    )
        
    toggles = {
        "show_hints_button": config.get("show_hints_button", True),
        "show_options_button": config.get("show_options_button", True)
    }
    
    if parser.update_note_with_hints(note, data, toggles, fresh_card):
        logger.info(f"AI-Hints: Updating database for card {fresh_card.id} (Note {note.id}, Ord {fresh_card.ord}) with new hints.")
        mw.col.update_note(note)
        _remember_generated_hints(fresh_card, data, toggles)
        _just_generated_card_ids.add(fresh_card.id)
        
        # Update UI if we are still on the card in this webview
        if web:
            if skip_redraw:
                _push_hint_data_to_frontend(web, fresh_card, data, is_manual=is_manual)
            else:
                try:
                    refresh_current_card(card=fresh_card, web=web)
                except Exception as e:
                    logger.error(f"AI-Hints card refresh failed: {e}")
        
        return True
    return False

def _trigger_next_pregeneration(current_card_id=None):
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    if not config.get("auto_generate_new", False) or not config.get("pre_generate_next", True):
        return

    # Use provided ID or fallback to reviewer
    if current_card_id is None:
        current_card_id = mw.reviewer.card.id if (mw.reviewer and mw.reviewer.card) else None
        
    if current_card_id and current_card_id in _generating_card_ids:
        logger.debug("AI-Hints pre-gen: Skipping because the current card is actively generating.")
        return

    pregen_limit = int(config.get("pre_generate_count", 3))

    # Check if our active pre-generations already reach the limit
    active_pregen_count = len([cid for cid in _generating_card_ids if cid != current_card_id])
    if active_pregen_count >= pregen_limit:
        logger.debug(f"AI-Hints pre-gen: Skipping because active pre-generations ({active_pregen_count}) reached limit ({pregen_limit}).")
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
                    # Fetch enough queued cards to cover our pregen limit plus current card
                    fetch_depth = max(5, pregen_limit + 4)
                    queued = mw.col.sched.get_queued_cards(fetch_limit=fetch_depth)
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
                        prepared_count = 0
                        for first_item in cards:
                            cid = getattr(first_item, "card_id", None)
                            if cid is None:
                                # Protobuf version: QueuedCard.card.id
                                inner_card = getattr(first_item, "card", None)
                                cid = getattr(inner_card, "id", None)
                            
                            if cid:
                                # Skip if it's the current card
                                if current_card_id and cid == current_card_id:
                                    continue
                                
                                card = mw.col.get_card(cid)
                                if not card:
                                    continue
                                    
                                if card_has_hints(card):
                                    # We also need to be sure that the existing hints actually cover
                                    # this specific card's cloze (if it's a cloze card).
                                    # card_has_hints checks if there is ANY block matching the card.
                                    # For keyed blocks, we should check if this specific cloze ord is covered.
                                    card_ord = getattr(card, "ord", None)
                                    parser = CardParser(
                                        mathjax_format=config.get("mathjax_format", "delimiters"),
                                        fix_latex=config.get("fix_latex", False)
                                    )
                                    block = parser.find_hints_block(card.note(), card)
                                    
                                    # If block is found, we assume it's covered. 
                                    # If it's a cloze and missing its specific key, find_hints_block 
                                    # with the card passed in *should* return None if it doesn't have data for it.
                                    if block:
                                        # Already has hints on disk, does not count against our pregen buffer limit
                                        continue
                                    
                                if cid in _pregenerated_data or cid in _generating_card_ids:
                                    prepared_count += 1
                                    if prepared_count >= pregen_limit:
                                        logger.debug(f"AI-Hints pre-gen: Buffer is fully saturated with {prepared_count} cards.")
                                        return
                                    continue
                                
                                # This is the first upcoming card that needs generation and is not yet in the buffer
                                next_card = card
                                break
            else:
                # Fallback: some old schedulers don't support peeking easily.
                # In this case, it is safer to skip pre-generation than to risk skipping cards.
                logger.debug("AI-Hints pre-gen: get_queued_cards not available, skipping pre-gen.")
                return

            if not next_card:
                logger.debug("AI-Hints pre-gen: All upcoming cards are already prepared or have hints.")
                return

            logger.info(f"AI-Hints: Triggering pre-generation for card {next_card.id} (buffer prepared={prepared_count}/{pregen_limit})")
            # Use taskman to run generation on main thread
            mw.taskman.run_on_main(lambda: generate_hints(is_manual=False, card=next_card, is_pregen=True))
        except Exception as e:
            logger.debug(f"AI-Hints pre-gen error in task: {e}")

    # Defer slightly to let UI settle
    QTimer.singleShot(500, _task)
def get_web_assets():
    global _js_cache, _css_cache
    if _js_cache is None:
        addon_dir = os.path.dirname(__file__)
        with open(os.path.join(addon_dir, "web", "template.js"), "r", encoding="utf-8") as f:
            _js_cache = f.read()
        
        # Dynamically extract STYLES block using regex so we don't duplicate CSS code
        import re
        style_match = re.search(r'const STYLES = `(.*?)`;', _js_cache, re.DOTALL)
        if style_match:
            _css_cache = style_match.group(1).strip()
        else:
            _css_cache = ""
    return _css_cache, _js_cache

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
        
    card_ord = None
    try:
        # We need the ord to distinguish clozes in the same note
        card_ord = int(card.ord)
    except Exception:
        pass
        
    if card_id and card_ord is not None:
        return ("id_ord", card_id, card_ord)
    if card_id:
        return ("id", card_id)

    if card_ord is not None:
        return ("ord", card_ord)
    return None

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

def _push_hint_data_to_frontend(web, card, data, is_manual=True) -> bool:
    if not web or not card or not data:
        return False

    card_payload = json.dumps(_card_payload(card))
    data_payload = json.dumps(data)
    manual_payload = "true" if is_manual else "false"
    return _safe_web_eval(web, f"""
        (function() {{
            var card = {card_payload};
            var hintData = {data_payload};
            var isManual = {manual_payload};
            var attempts = 0;

            function isCurrentCard() {{
                if (!window.aiHintsCurrentCard) return null;
                return String(window.aiHintsCurrentCard.id) === String(card.id) &&
                    String(window.aiHintsCurrentCard.ord) === String(card.ord);
            }}

            function applyHints() {{
                attempts += 1;
                var current = isCurrentCard();
                if (current === false) return;

                if (current) {{
                    if (window.aiHintsUiConfig) {{
                        window.aiHintsUiConfig.is_generating = false;
                    }}
                    if (typeof window.aiHintsUpdateData === 'function') {{
                        window.aiHintsUpdateData(hintData, isManual);
                        return;
                    }}
                    if (typeof window.aiHintsSetup === 'function') {{
                        window.aiHintsSetup(card, hintData);
                        return;
                    }}
                }}

                if (attempts < 60) {{
                    setTimeout(applyHints, 50);
                }}
            }}

            applyHints();
        }})();
    """)

def _prepare_card_review_state(card):
    if not card:
        return

    to_remove = [cid for cid in _just_generated_card_ids if cid != card.id]
    for cid in to_remove:
        _just_generated_card_ids.discard(cid)

    to_remove_cleared = [cid for cid in _just_cleared_card_ids if cid != card.id]
    for cid in to_remove_cleared:
        _just_cleared_card_ids.discard(cid)

def _set_frontend_generating(web, active, card_id=None, is_pregen=False, status=None, error_msg=None):
    if not web:
        return
    status_arg = json.dumps(status) if status is not None else "undefined"
    error_arg = json.dumps(error_msg) if error_msg is not None else "undefined"
    card_id_arg = json.dumps(card_id) if card_id is not None else "undefined"
    _safe_web_eval(web, f"""
        (function() {{
            var active = {json.dumps(bool(active))};
            var cardId = {card_id_arg};
            var isPregen = {json.dumps(bool(is_pregen))};
            var status = {status_arg};
            var errorMsg = {error_arg};
            var attempts = 0;
            function applyState() {{
                attempts += 1;
                if (typeof window.aiHintsSetGenerating === 'function') {{
                    window.aiHintsSetGenerating(active, status, errorMsg, cardId, isPregen);
                    return;
                }}
                if (attempts < 20) setTimeout(applyState, 50);
            }}
            applyState();
        }})();
    """)

def _get_ui_config(card, auto_reveal=False, is_answer=False, has_data=False):
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    return {
        "show_on_card": config.get("show_on_card", True),
        "auto_reveal": auto_reveal,
        "auto_show_hints": config.get("auto_show_hints", False),
        "auto_show_options": config.get("auto_show_options", False),
        "do_not_auto_collapse": config.get("do_not_auto_collapse", False),
        "manual_show_hints": config.get("manual_show_hints", True),
        "manual_show_options": config.get("manual_show_options", False),
        "mathjax_format": config.get("mathjax_format", "delimiters"),
        "fix_latex": config.get("fix_latex", False),
        "review_token": _review_token,
        "is_generating": card.id in _generating_card_ids if card else False,
        "is_pregenerating": any(cid != card.id for cid in _generating_card_ids) if card else False,
        "shortcuts": config.get("shortcuts", {}),
        "is_answer_side": is_answer,
        "hints_font_size": config.get("hints_font_size", ""),
        "answer_display_position": config.get("answer_display_position", "between"),
        "has_data": has_data
    }

def on_webview_will_set_content(web_content, context):
    if type(context).__name__ == "ReviewerBottomBar":
        return

    # Determine if we are in the reviewer or previewer context
    is_supported = (
        getattr(context, "name", None) in ["reviewer", "previewer"] or 
        type(context).__name__ in ["Reviewer", "Previewer"] or
        (context is None and any("reviewer.css" in c for c in web_content.css))
    )
    
    if not is_supported:
        return

    css, js = get_web_assets()
    if css:
        web_content.head += f"\n<style id='ai-hints-head-styles'>{css}</style>\n"

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )

    card, web = _get_card_and_web_from_context(context)

    hints_blocks = []
    has_hints = False
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
                # Auto-format and migrate unformatted/legacy JSON blocks on the fly during review
                try:
                    if parser.format_unformatted_blocks_in_note(note, card):
                        mw.col.update_note(note)
                except Exception as format_err:
                    logger.error(f"Error auto-formatting note on review: {format_err}")

                # Only inject data validated for the active card. This prevents a
                # stale c2/c3 payload from being shown after clozes are added or edited.
                valid_block = parser.find_hints_block(note, card)
                if valid_block:
                    hints_blocks = [valid_block]
            
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
                has_hints = True
            
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

    ui_config = _get_ui_config(card, auto_reveal=auto_reveal, is_answer=is_answer, has_data=has_hints)
    ui_payload = json.dumps(ui_config)

    if config.get("auto_show_hints", False) or config.get("auto_show_options", False):
        logger.debug(
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
    
    # Inject state and the unified template script at the END of the body
    # to ensure all DOM elements (like .ai-hints-json blocks) are fully parsed 
    # and accessible by document.querySelectorAll before the script runs init().
    # Explicitly clear stale setup keys to prevent data from previous card bleeding into this one.
    state_js = f"""
<script>
(function() {{
    // Instantly wipe ALL stale AI-Hints elements from previous card reviews to prevent bleed.
    // We do this before the main script runs init().
    document.querySelectorAll('.ai-hints-container, .ai-hints-container-rendered, .ai-hints-json').forEach(e => e.remove());
}})();
window.aiHintsLastSetupKey = undefined;
window.aiHintsSetupToken = undefined;
window.aiHintsCurrentCard = {card_payload};
window.aiHintsUiConfig = {ui_payload};
{js}
</script>
"""
    web_content.body += state_js

def _trigger_frontend_setup(card=None, web=None):
    logger.debug(f"AI-Hints: _trigger_frontend_setup called. Input card={type(card).__name__} (has note={hasattr(card, 'note')})")
    
    # Detect if 'card' is actually an Anki context (e.g. Reviewer, Previewer instance) rather than a Card object
    if card is not None and not hasattr(card, "note"):
        orig_card = card
        card, extracted_web = _get_card_and_web_from_context(card)
        if extracted_web:
            web = extracted_web
        logger.debug(f"AI-Hints: Extracted Card={type(card).__name__ if card else None} from context {type(orig_card).__name__}")

    if card is None:
        card = getattr(mw.reviewer, "card", None)
        logger.debug(f"AI-Hints: Fallback to mw.reviewer.card yields Card={type(card).__name__ if card else None}")
    
    if not card:
        logger.debug("AI-Hints: _trigger_frontend_setup aborted: no active card found.")
        return
    if _reviewer_is_ending:
        logger.debug("AI-Hints: _trigger_frontend_setup aborted: reviewer is ending.")
        return

    if web is None:
        web = getattr(mw.reviewer, "web", None)

    _prepare_card_review_state(card)

    is_answer = False
    if mw.reviewer:
        is_answer = getattr(mw.reviewer, "state", "") == "answer"

    has_hints = card_has_hints(card)
    ui_config = _get_ui_config(card, is_answer=is_answer, has_data=has_hints)
    ui_config_json = json.dumps(ui_config)

    card_data = {"id": str(card.id), "ord": int(card.ord)}

    # Pass hint data directly so the frontend can render it even if the
    # DOM injection in on_webview_will_set_content was skipped or the
    # JSON block is missing for any reason.
    hint_data = None
    try:
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        # ... (rest of hint_data lookup)
        parser = CardParser(
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
    logger.debug(f"AI-Hints: _trigger_frontend_setup evaluating JS for Card ID: {card.id}, Ord: {card.ord}, has_hints={hint_data is not None}")
    if web:
        _safe_web_eval(web, f"""
            (function() {{
                var data = {json.dumps(card_data)};
                var hintData = {hint_data_json};
                var uiConfig = {ui_config_json};
                var token = String(data.id) + ':' + String(data.ord) + ':' + {json.dumps(_review_token)};
                window.aiHintsSetupToken = token;
                function applySetup() {{
                    if (window.aiHintsSetupToken !== token) return;
                    if (typeof window.aiHintsSetup === 'function') {{
                        window.aiHintsSetup(data, hintData, uiConfig);
                    }}
                }}
                var attempts = 0;
                function trySetup() {{
                    if (window.aiHintsSetupToken !== token) return;
                    attempts += 1;
                    if (typeof window.aiHintsSetup === 'function') {{
                        applySetup();
                    }} else if (attempts < 40) {{
                        setTimeout(trySetup, 50);
                    }}
                }}
                trySetup();
            }})();
        """)

def _get_card_and_web_from_context(context):
    """Helper to extract the active card and web object from various Anki contexts
    (Reviewer, Previewer, etc.)."""
    
    # 1. Prioritize getting the card directly from the context object (Reviewer/Previewer instance).
    # During card transitions, mw.reviewer.card might still point to the previous card
    # while the context object is already preparing the content for the new one.
    card = getattr(context, "card", None)
    if not card:
        card = getattr(context, "_card", None)
        
    if callable(card):
        try:
            card = card()
        except Exception:
            card = None
    
    # 2. Fallback to global reviewer if context doesn't yield a card
    if not card and mw.reviewer:
        card = mw.reviewer.card

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
    
    if not web and mw.reviewer:
        web = mw.reviewer.web
        
    return card, web

def edit_item(card, web, item_type: str, index: int, new_value: str):
    if not card:
        logger.error("AI-Hints: No card provided for edit_item")
        return

    import copy
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )

    note = card.note()

    # 1. Try memory cache first
    cached = _cached_hints_for_card(card)
    data = None
    toggles = None
    if cached:
        # Avoid direct modification in-place of cached object
        data = copy.deepcopy(cached.get("data"))
        toggles = copy.deepcopy(cached.get("toggles"))

    # 2. If not in cache, load from note
    if not data or not toggles:
        block_html = parser.find_hints_block(note, card)
        if block_html:
            import re, html as _html
            m = re.search(
                r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
                block_html, re.DOTALL | re.IGNORECASE
            )
            if m:
                import json as _json
                try:
                    raw = _html.unescape(m.group(1) or "")
                    parsed = _json.loads(raw)
                    card_ord = getattr(card, "ord", None)
                    card_key = None
                    if card_ord is not None:
                        card_key = f"c{card_ord + 1}"

                    if isinstance(parsed, dict) and card_key and card_key in parsed and "hints" not in parsed:
                        data = parsed[card_key]
                    else:
                        data = parsed
                    toggles = parser._extract_toggles_from_block(block_html)
                except Exception as e:
                    logger.error(f"AI-Hints: Failed to parse hints JSON: {e}")

    # 3. Fallbacks
    if not data:
        data = {"hints": [], "options": []}
    if not toggles:
        toggles = {
            "show_hints_button": config.get("show_hints_button", True),
            "show_options_button": config.get("show_options_button", True)
        }

    # Ensure deep copies/mutable items
    if not isinstance(data, dict):
        data = {"hints": [], "options": []}
    if "hints" not in data or not isinstance(data["hints"], list):
        data["hints"] = []
    if "options" not in data or not isinstance(data["options"], list):
        data["options"] = []

    # 4. Modify the item
    if item_type == "hints":
        items = list(data["hints"])
        if 0 <= index < len(items):
            items[index] = new_value
            data["hints"] = items
        else:
            logger.error(f"AI-Hints: Edit index {index} out of range for hints ({len(items)})")
            return
    elif item_type == "options":
        items = list(data["options"])
        if 0 <= index < len(items):
            items[index] = new_value
            data["options"] = items
            if index == 0:
                data["correct_answer"] = new_value
        else:
            logger.error(f"AI-Hints: Edit index {index} out of range for options ({len(items)})")
            return
    else:
        logger.error(f"AI-Hints: Unknown edit type {item_type}")
        return

    # 5. Save back to note and update Anki database
    if parser.update_note_with_hints(note, data, toggles, card):
        mw.col.update_note(note)
        # Update cache with the modified dict
        _remember_generated_hints(card, data, toggles)
        # Push updated data to frontend (without refresh/flicker)
        if web:
            _push_hint_data_to_frontend(web, card, data, is_manual=False)
            tooltip("AI-Hints: Saved.")
    else:
        logger.error("AI-Hints: Failed to update note with edited items")

def on_webview_did_receive_js_message(handled, message, context):
    card, web = _get_card_and_web_from_context(context)
    
    if message.startswith("{"):
        try:
            import json as _json
            data = _json.loads(message)
            if isinstance(data, dict) and data.get("action") == "ai_hints_edit_item":
                edit_item(
                    card=card,
                    web=web,
                    item_type=data.get("type"),
                    index=data.get("index"),
                    new_value=data.get("value")
                )
                return (True, None)
        except Exception as e:
            logger.error(f"AI-Hints: Failed to parse JS JSON message: {e}")

    if message == "ai_hints_generate":
        generate_hints(card=card, web=web)
        return (True, None)
    if message == "ai_hints_clear":
        clear_hints(card=card, web=web)
        return (True, None)
    if message == "ai_hints_remove_warning":
        remove_warning_hint(card=card, web=web)
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
    if message == "ai_hints_skip":
        skip_ai_for_card(card=card, web=web)
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
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    note = card.note()
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

def remove_warning_hint(card=None, web=None):
    if card is None:
        card = mw.reviewer.card
    if not card:
        return

    if web is None:
        web = getattr(mw.reviewer, "web", None)

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    note = card.note()
    if parser.remove_warning_hint_from_note(note, card):
        mw.col.update_note(note)
        _forget_generated_hints(card)
        logger.info("AI-Hints warning removed for card %s", card.id)
        tooltip("AI-Hints: Warning removed.")
        if web:
            QTimer.singleShot(
                100,
                lambda: (
                    None if _reviewer_is_ending or _qt_object_is_deleted(web)
                    else refresh_current_card(card=card, web=web)
                )
            )
    else:
        tooltip("AI-Hints: No warning found.")

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

def clear_ai_hints_for_cards(card_ids) -> tuple[int, int, int]:
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
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
            logger.error(f"Failed to clear AI-Hints for card {card_id}: {e}")

    for note in changed_notes.values():
        try:
            mw.col.update_note(note)
        except Exception as e:
            logger.error(f"Failed to update note after clearing AI-Hints: {e}")

    return len(card_ids), changed_cards, len(changed_notes)

def clear_ai_hints_from_browser_selection(browser):
    card_ids = _selected_browser_card_ids(browser)
    if not card_ids:
        tooltip("AI-Hints: Select one or more cards first.")
        return 0, 0, 0

    res = clear_ai_hints_for_cards(card_ids)
    changed_cards = res[1]

    if changed_cards:
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
    else:
        tooltip("AI-Hints: No cached data found on the selected cards.")

    return res

def unskip_ai_hints_for_cards(card_ids) -> tuple[int, int, int]:
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
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

            if parser.unskip_hints_from_note(note, card):
                changed_cards += 1
                changed_notes[note_id if note_id is not None else id(note)] = note
        except Exception as e:
            missing_cards += 1
            logger.error(f"Failed to unskip AI-Hints for card {card_id}: {e}")

    for note in changed_notes.values():
        try:
            mw.col.update_note(note)
        except Exception as e:
            logger.error(f"Failed to update note after unskipping AI-Hints: {e}")

    return len(card_ids), changed_cards, len(changed_notes)

def unskip_ai_hints_from_browser_selection(browser):
    card_ids = _selected_browser_card_ids(browser)
    if not card_ids:
        tooltip("AI-Hints: Select one or more cards first.")
        return 0, 0, 0

    res = unskip_ai_hints_for_cards(card_ids)
    changed_cards = res[1]

    if changed_cards:
        refresh_browser = getattr(browser, "onReset", None)
        if callable(refresh_browser):
            try:
                refresh_browser()
            except Exception as e:
                logger.error(f"Failed to refresh browser after unskipping AI-Hints: {e}")

    if changed_cards:
        tooltip(
            f"AI-Hints: Re-enabled AI generation for {changed_cards} "
            f"selected card{'s' if changed_cards != 1 else ''}."
        )
    else:
        tooltip("AI-Hints: Selected cards were not in skipped status.")

    return res

def skip_ai_hints_for_cards(card_ids) -> tuple[int, int, int]:
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )

    toggles = {
        "show_hints_button": config.get("show_hints_button", True),
        "show_options_button": config.get("show_options_button", True)
    }

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

            data = {"hints": [], "options": [], "_skipped": True}
            if parser.update_note_with_hints(note, data, toggles, card):
                changed_cards += 1
                changed_notes[note_id if note_id is not None else id(note)] = note
                _remember_generated_hints(card, data, toggles)
        except Exception as e:
            missing_cards += 1
            logger.error(f"Failed to skip AI-Hints for card {card_id}: {e}")

    for note in changed_notes.values():
        try:
            mw.col.update_note(note)
        except Exception as e:
            logger.error(f"Failed to update note after skipping AI-Hints: {e}")

    return len(card_ids), changed_cards, len(changed_notes)

def skip_ai_hints_from_browser_selection(browser):
    card_ids = _selected_browser_card_ids(browser)
    if not card_ids:
        tooltip("AI-Hints: Select one or more cards first.")
        return 0, 0, 0

    res = skip_ai_hints_for_cards(card_ids)
    changed_cards = res[1]

    if changed_cards:
        refresh_browser = getattr(browser, "onReset", None)
        if callable(refresh_browser):
            try:
                refresh_browser()
            except Exception as e:
                logger.error(f"Failed to refresh browser after skipping AI-Hints: {e}")

    if changed_cards:
        tooltip(
            f"AI-Hints: Marked {changed_cards} "
            f"selected card{'s' if changed_cards != 1 else ''} as skipped."
        )
    else:
        tooltip("AI-Hints: Selected cards were already marked as skipped or couldn't be updated.")

    return res

def on_browser_context_menu(browser, menu):
    # Add separator before our menu
    menu.addSeparator()
    
    # Create AI Hints sub-menu
    ai_menu = QMenu("AI Hints", menu)
    menu.addMenu(ai_menu)
    
    has_selection = bool(_selected_browser_card_ids(browser))
    
    # Action 1: Batch Generation UI
    act_batch_ui = ai_menu.addAction("✨ Batch Generation...")
    act_batch_ui.setEnabled(has_selection)
    act_batch_ui.triggered.connect(
        lambda _checked=False, b=browser: on_config_dialog(mw, tab_index=4, card_ids=_selected_browser_card_ids(b))
    )
    
    # Action 2: Skip AI for Selected Cards
    act_skip = ai_menu.addAction("Skip AI for Selected Cards")
    act_skip.setEnabled(has_selection)
    act_skip.triggered.connect(lambda _checked=False, b=browser: skip_ai_hints_from_browser_selection(b))

    # Action 2.5: Unskip AI for Selected Cards
    act_unskip = ai_menu.addAction("Unskip AI for Selected Cards")
    act_unskip.setEnabled(has_selection)
    act_unskip.triggered.connect(lambda _checked=False, b=browser: unskip_ai_hints_from_browser_selection(b))

    # Action 3: Clear
    act_clear = ai_menu.addAction("Clear AI-Hints")
    act_clear.setEnabled(has_selection)
    act_clear.triggered.connect(lambda _checked=False, b=browser: clear_ai_hints_from_browser_selection(b))

    # Action 4: Clean Orphaned Hints...
    act_orphans = ai_menu.addAction("🧹 Clean Orphaned Hints...")
    act_orphans.setEnabled(has_selection)
    def on_clean_orphans_triggered() -> None:
        from .config_ui.main_dialog import on_clean_orphaned_hints
        card_ids = _selected_browser_card_ids(browser)
        if card_ids:
            query = "cid:" + ",".join(map(str, card_ids))
            on_clean_orphaned_hints(query, f"selected cards ({len(card_ids)})")
    act_orphans.triggered.connect(on_clean_orphans_triggered)

def on_sidebar_context_menu(sidebar, menu, item, index) -> None:
    search_node = getattr(item, "search_node", None)
    if not search_node:
        return

    try:
        search_string = sidebar.col.build_search_string(search_node)
    except Exception:
        return

    if not search_string:
        return

    try:
        card_ids = sidebar.col.find_cards(search_string)
    except Exception as e:
        logger.error(f"Failed to find cards for sidebar search query '{search_string}': {e}")
        return

    if not card_ids:
        return

    from aqt.utils import askUser
    from .config_ui import on_config_dialog

    # Add separator before our menu
    menu.addSeparator()

    # Create AI Hints sub-menu
    ai_menu = QMenu("AI Hints", menu)
    menu.addMenu(ai_menu)

    # Action 1: Batch Generation...
    act_batch = ai_menu.addAction("✨ Batch Generation...")
    act_batch.triggered.connect(
        lambda _checked=False, cids=card_ids: on_config_dialog(mw, tab_index=4, card_ids=cids)
    )

    # Action 2: Skip AI for Group
    act_skip = ai_menu.addAction("Skip AI for Group")
    def on_skip_triggered() -> None:
        mw.checkpoint("Skip AI Hints")
        res = skip_ai_hints_for_cards(card_ids)
        changed_cards = res[1]
        
        # Trigger reload of browser if active
        browser = getattr(sidebar, "browser", None)
        if browser:
            refresh_browser = getattr(browser, "onReset", None)
            if callable(refresh_browser):
                try:
                    refresh_browser()
                except Exception as e:
                    logger.error(f"Failed to refresh browser after skipping: {e}")
                    
        if changed_cards:
            tooltip(f"AI-Hints: Skipped AI generation for {changed_cards} cards.")
        else:
            tooltip("AI-Hints: Selected cards were already marked as skipped or couldn't be updated.")
    act_skip.triggered.connect(on_skip_triggered)

    # Action 3: Unskip AI for Group
    act_unskip = ai_menu.addAction("Unskip AI for Group")
    def on_unskip_triggered() -> None:
        mw.checkpoint("Unskip AI Hints")
        res = unskip_ai_hints_for_cards(card_ids)
        changed_cards = res[1]
        
        browser = getattr(sidebar, "browser", None)
        if browser:
            refresh_browser = getattr(browser, "onReset", None)
            if callable(refresh_browser):
                try:
                    refresh_browser()
                except Exception as e:
                    logger.error(f"Failed to refresh browser after unskipping: {e}")
                    
        if changed_cards:
            tooltip(f"AI-Hints: Re-enabled AI generation for {changed_cards} cards.")
        else:
            tooltip("AI-Hints: No skipped card indicators found in selected group.")
    act_unskip.triggered.connect(on_unskip_triggered)

    # Action 4: Clear AI-Hints
    act_clear = ai_menu.addAction("Clear AI-Hints")
    def on_clear_triggered() -> None:
        if not askUser(f"Are you sure you want to clear AI Hints from all {len(card_ids)} cards in this group?"):
            return
        mw.checkpoint("Clear AI Hints")
        res = clear_ai_hints_for_cards(card_ids)
        changed_cards = res[1]
        
        browser = getattr(sidebar, "browser", None)
        if browser:
            refresh_browser = getattr(browser, "onReset", None)
            if callable(refresh_browser):
                try:
                    refresh_browser()
                except Exception as e:
                    logger.error(f"Failed to refresh browser after clearing: {e}")
                    
        if changed_cards:
            tooltip(f"AI-Hints: Cleared cached data from {changed_cards} cards.")
        else:
            tooltip("AI-Hints: No cached data found on the selected cards.")
    act_clear.triggered.connect(on_clear_triggered)

def on_deck_browser_context_menu(menu, did) -> None:
    from aqt.qt import QMenu, QAction
    from aqt.utils import askUser
    
    # Add separator before our menu
    menu.addSeparator()
    
    # Create AI Hints sub-menu
    ai_menu = QMenu("AI Hints", menu)
    menu.addMenu(ai_menu)
    
    # Action 1: Batch Generation...
    act_batch = ai_menu.addAction("✨ Batch Generation...")
    
    def get_deck_name(col) -> str:
        try:
            from anki.decks import DeckId
            return col.decks.name(DeckId(did))
        except:
            return col.decks.name(did)
            
    def on_batch_triggered() -> None:
        from aqt.operations import QueryOp
        def on_success(deck_name: str) -> None:
            if deck_name:
                from .config_ui import on_config_dialog
                on_config_dialog(mw, tab_index=4, deck_name=deck_name)
        QueryOp(
            parent=mw,
            op=get_deck_name,
            success=on_success,
        ).run_in_background()
        
    act_batch.triggered.connect(on_batch_triggered)
    
    # Action 2: Skip AI for All Cards in Deck
    act_skip = ai_menu.addAction("Skip AI for All Cards in Deck")
    
    def on_skip_triggered() -> None:
        from aqt.operations import QueryOp
        
        def run_skip(col) -> tuple[str, list[int]]:
            deck_name = get_deck_name(col)
            card_ids = col.find_cards(f'\"deck:{deck_name}\"')
            return deck_name, card_ids
            
        def on_success(res) -> None:
            deck_name, card_ids = res
            if not card_ids:
                tooltip("AI-Hints: No cards found in this deck.")
                return
            if not askUser(f"Are you sure you want to mark all {len(card_ids)} cards in deck '{deck_name}' as skipped for AI hints?"):
                return
            
            def do_skip(col):
                return skip_ai_hints_for_cards(card_ids)
                
            def on_skip_done(skip_res):
                total, changed, changed_notes = skip_res
                if changed > 0:
                    tooltip(f"AI-Hints: Marked {changed} cards as skipped.")
                else:
                    tooltip("AI-Hints: Cards were already skipped or couldn't be updated.")
                    
            QueryOp(
                parent=mw,
                op=do_skip,
                success=on_skip_done,
            ).run_in_background()
            
        QueryOp(
            parent=mw,
            op=run_skip,
            success=on_success,
        ).run_in_background()
        
    act_skip.triggered.connect(on_skip_triggered)
    
    # Action 2.5: Unskip AI for All Cards in Deck
    act_unskip = ai_menu.addAction("Unskip AI for All Cards in Deck")
    
    def on_unskip_triggered() -> None:
        from aqt.operations import QueryOp
        
        def run_unskip(col) -> tuple[str, list[int]]:
            deck_name = get_deck_name(col)
            card_ids = col.find_cards(f'\"deck:{deck_name}\"')
            return deck_name, card_ids
            
        def on_success(res) -> None:
            deck_name, card_ids = res
            if not card_ids:
                tooltip("AI-Hints: No cards found in this deck.")
                return
            if not askUser(f"Are you sure you want to re-enable AI hints for all {len(card_ids)} cards in deck '{deck_name}'?"):
                return
            
            def do_unskip(col):
                return unskip_ai_hints_for_cards(card_ids)
                
            def on_unskip_done(unskip_res):
                total, changed, changed_notes = unskip_res
                if changed > 0:
                    tooltip(f"AI-Hints: Re-enabled AI generation for {changed} cards.")
                else:
                    tooltip("AI-Hints: Selected cards were not in skipped status.")
                    
            QueryOp(
                parent=mw,
                op=do_unskip,
                success=on_unskip_done,
            ).run_in_background()
            
        QueryOp(
            parent=mw,
            op=run_unskip,
            success=on_success,
        ).run_in_background()
        
    act_unskip.triggered.connect(on_unskip_triggered)
    
    # Action 3: Clear AI-Hints for All Cards in Deck
    act_clear = ai_menu.addAction("Clear AI-Hints for All Cards in Deck")
    
    def on_clear_triggered() -> None:
        from aqt.operations import QueryOp
        
        def run_clear(col) -> tuple[str, list[int]]:
            deck_name = get_deck_name(col)
            card_ids = col.find_cards(f'\"deck:{deck_name}\"')
            return deck_name, card_ids
            
        def on_success(res) -> None:
            deck_name, card_ids = res
            if not card_ids:
                tooltip("AI-Hints: No cards found in this deck.")
                return
            if not askUser(f"Are you sure you want to clear AI hints from all {len(card_ids)} cards in deck '{deck_name}'? This cannot be undone."):
                return
                
            def do_clear(col):
                return clear_ai_hints_for_cards(card_ids)
                
            def on_clear_done(clear_res):
                total, changed, changed_notes = clear_res
                if changed > 0:
                    tooltip(f"AI-Hints: Cleared data from {changed} cards.")
                else:
                    tooltip("AI-Hints: No data found to clear.")
                    
            QueryOp(
                parent=mw,
                op=do_clear,
                success=on_clear_done,
            ).run_in_background()
            
        QueryOp(
            parent=mw,
            op=run_clear,
            success=on_success,
        ).run_in_background()
        
    act_clear.triggered.connect(on_clear_triggered)
    
    # Action 4: Clean Orphaned Hints...
    act_orphans = ai_menu.addAction("🧹 Clean Orphaned Hints...")
    def on_clean_orphans_triggered() -> None:
        from aqt.operations import QueryOp
        def run_orphans(col) -> str:
            return get_deck_name(col)
        def on_success(deck_name: str) -> None:
            if deck_name:
                from .config_ui.main_dialog import on_clean_orphaned_hints
                query = f'\"deck:{deck_name}\"'
                on_clean_orphaned_hints(query, f"deck '{deck_name}'")
        QueryOp(
            parent=mw,
            op=run_orphans,
            success=on_success,
        ).run_in_background()
    act_orphans.triggered.connect(on_clean_orphans_triggered)
    

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
        # NOTE: Do NOT call _forget_generated_hints(card) here.
        # refresh_current_card triggers _showQuestion() which fires on_show_question
        # → card_has_hints → cache lookup.
        # We no longer pop here. We let the consumption logic in on_show_question handle it.
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

def skip_ai_for_card(card=None, web=None):
    if card is None:
        card = mw.reviewer.card
    if not card:
        return
    
    if web is None:
        web = getattr(mw.reviewer, "web", None)

    logger.info(f"AI-Hints: Skipping AI for card {card.id}")
    
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        mathjax_format=config.get("mathjax_format", "delimiters"),
        fix_latex=config.get("fix_latex", False)
    )
    
    data = {"hints": [], "options": [], "_skipped": True}
    if _apply_results_to_card(card, data, is_manual=True, web=web):
        # Trigger a refresh so the skip state is visible
        refresh_current_card(card=card, web=web)

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

    # 5. Skip AI
    a_skip = QAction("Skip AI Generation", menu)
    a_skip.triggered.connect(skip_ai_for_card)
    menu.addAction(a_skip)
    
    menu.addSeparator()
    
    # 6. Config
    a_config = QAction("Settings...", menu)
    a_config.triggered.connect(lambda: on_config_dialog(mw))
    menu.addAction(a_config)
    
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
    
    # Check cache first for manual generation (to avoid redundant API calls)
    if not is_pregen and card_id in _pregenerated_data:
        logger.info(f"AI-Hints: Found pre-generated data for card {card_id} in disk cache. Applying directly.")
        cached_data = _pregenerated_data.pop(card_id)
        _apply_results_to_card(card, cached_data, is_manual=is_manual, web=web)
        return

    if card_id in _generating_card_ids:
        if not is_pregen and web:
            # If we arrive at a card already being pre-generated, 
            # just trigger the UI animation so the user sees the progress.
            _set_frontend_generating(web, True, card_id=card_id)
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
        
        # Save skipped state to database to ensure verification passes and the UI reflects skip state
        data = {"hints": [], "options": [], "_skipped": True}
        _apply_results_to_card(card, data, is_manual=is_manual, web=web, skip_redraw=is_pregen)

        # If this was a pre-generation, trigger the next one so the chain doesn't break
        if is_pregen:
            _trigger_next_pregeneration(card_id)
        return

    logger.info(f"AI-Hints generating for card {card_id} (ord={card.ord}, manual={is_manual}, pregen={is_pregen}) using {provider}")
    
    if is_manual:
        # User explicitly asked for generation; clear any active emergency stop
        state.GLOBAL_STOP = False

    # Trigger animation in frontend
    if web:
        _set_frontend_generating(web, True, card_id, is_pregen)

    def on_done(data):
        # ALWAYS discard from generating set immediately so other code (and UI refreshes)
        # know this specific task is finished.
        _generating_card_ids.discard(card_id)

        try:
            if not mw.col:
                return

            if state.GLOBAL_STOP:
                logger.info(f"AI-Hints: Generation aborted for card {card_id} via Emergency Stop signal.")
                # Clear animation
                _set_frontend_generating(web, False, card_id, is_pregen)
                return

            # --- Undo Protection Shield (1.0s) ---
            # If an Undo recently happened, discard ANY generation that finishes 
            # to prevent 'future' data from overwriting the 'reverted' state.
            if time.time() - _last_undo_time < 1.0:
                logger.info(f"AI-Hints: Discarding finished generation for {card_id} due to recent Undo protection.")
                _set_frontend_generating(web, False, card_id, is_pregen)
                return

            if is_pregen:
                current_reviewer_card = getattr(mw.reviewer, "card", None)
                is_on_screen = current_reviewer_card and current_reviewer_card.id == card_id
                
                if data and (data.get("hints") or data.get("options")):
                    if is_on_screen:
                         logger.info(f"AI-Hints: Pre-generation complete for {card_id} (Applied immediately).")
                         _apply_results_to_card(card, data, is_manual=False, web=web, skip_redraw=True)
                         # Explicitly clear frontend state as well for double safety
                         _set_frontend_generating(web, False, card_id, is_pregen)
                    else:
                        _pregenerated_data[card_id] = data
                        logger.info(f"AI-Hints: Pre-generation complete for {card_id} (Saved to disk cache).")
                        _set_frontend_generating(web, False, card_id, is_pregen)
                else:
                    logger.info(f"AI-Hints: Pre-generation for {card_id} failed or returned no data.")
                    # If pre-gen failed and it was on screen (upgraded to foreground), clear animation
                    if is_on_screen:
                        _set_frontend_generating(web, False, card_id, is_pregen, "Failed")
                    else:
                        _set_frontend_generating(web, False, card_id, is_pregen)
                
                # IMPORTANT: Trigger the NEXT pre-generation to fill the buffer
                _trigger_next_pregeneration(card_id)
                return

            # --- Foreground / Standard Generation Path ---
            # Identity Verification: verify the card is still the one on screen
            current_reviewer_card = getattr(mw.reviewer, "card", None)
            if current_reviewer_card and current_reviewer_card.id != card.id:
                logger.info(f"AI-Hints: Background generation finished for {card_id}, but user is now on {current_reviewer_card.id}. Discarding to prevent bleed.")
                _set_frontend_generating(web, False, card_id, is_pregen)
                return

            if not data or (not data.get("hints") and not data.get("options")):
                if data is None:
                    data = {}
                err_status = data.get("_ai_error_type") or "Failed"
                err_msg = data.get("_ai_error_msg", "")
                
                # Safely update frontend to transition from animation -> feedback -> rest state
                try:
                    _set_frontend_generating(web, False, card_id, is_pregen, err_status, err_msg)
                except Exception:
                    pass
                return

            if _apply_results_to_card(card, data, is_manual=is_manual, web=web):
                # If we just finished the current card, and pre-generation is on, 
                # try to pre-generate for the NEXT card now.
                if not is_manual:
                    _trigger_next_pregeneration(card_id)
                
                # Double safety: clear animation for current card
                _set_frontend_generating(web, False, card_id, is_pregen)
            else:
                try:
                    _set_frontend_generating(web, False, card_id, is_pregen, "Failed")
                except Exception: pass
                info("AI-Hints: No hints or options were generated.")
        finally:
            # Final safety discard
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
        fields = getattr(note, "fields", [])
        if not fields and hasattr(note, "values"):
            fields = list(note.values())
        for field_val in fields:
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

def _card_saved_generation_time(card) -> str:
    """Return the generation time string stored inside the card's JSON block (in format %Y-%m-%d %H:%M:%S).
    Returns an empty string if no generation time was recorded.
    """
    if not card:
        return ""
    cached = _cached_hints_for_card(card)
    if cached:
        data = cached.get("data") or {}
        time_str = data.get("_generated_at", "")
        if time_str:
            return str(time_str)
    try:
        import re
        import html as _html
        note = card.note()
        fields = getattr(note, "fields", [])
        if not fields and hasattr(note, "values"):
            fields = list(note.values())
        for field_val in fields:
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
                    card_ord = getattr(card, "ord", None)
                    if card_ord is not None:
                        card_key = f"c{card_ord + 1}"
                        if isinstance(parsed, dict) and card_key in parsed:
                            parsed = parsed[card_key]
                    return str(parsed.get("_generated_at", ""))
                except Exception:
                    pass
    except Exception:
        pass
    return ""

def _time_less_than(t1: str, t2: str) -> bool:
    """Return True if time string t1 is strictly older than t2.
    Supports %Y-%m-%d %H:%M:%S and partial formats.
    """
    if not t1 or not t2:
        return False
    t1_clean = t1.strip().replace("T", " ")
    t2_clean = t2.strip().replace("T", " ")
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt1 = datetime.strptime(t1_clean, fmt)
            dt2 = datetime.strptime(t2_clean, fmt)
            return dt1 < dt2
        except ValueError:
            pass
    min_len = min(len(t1_clean), len(t2_clean))
    if min_len >= 10:
        try:
            dt1 = datetime.strptime(t1_clean[:min_len], "%Y-%m-%d %H:%M:%S"[:min_len])
            dt2 = datetime.strptime(t2_clean[:min_len], "%Y-%m-%d %H:%M:%S"[:min_len])
            return dt1 < dt2
        except ValueError:
            pass
    return t1_clean < t2_clean

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
    gui_hooks.deck_browser_will_show_options_menu.append(on_deck_browser_context_menu)
    if hasattr(gui_hooks, "browser_sidebar_will_show_context_menu"):
        gui_hooks.browser_sidebar_will_show_context_menu.append(on_sidebar_context_menu)
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
        state.GLOBAL_STOP = False
        
        # Trigger frontend setup immediately.
        # The JS-side 'aiHintsSetup' is now smarter and will bail out if 
        # the card is already rendered via the script injection.
        _trigger_frontend_setup(card)
        
        # We no longer need multiple delayed retries because the unified template 
        # script is injected into the body and handles its own init() on load,
        # and our smarter init() prevents flickering.
        
        # Auto generate for new cards if configured and no data exists
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        
        # 1. Check if we have pre-generated data for THIS card
        if card.id in _pregenerated_data:
            # Skip applying pre-generated data if we just undid something.
            # This handles cases where Anki's state is still resolving.
            if time.time() - _last_undo_time < 0.5:
                logger.info(f"AI-Hints: Skipping pre-gen application for {card.id} due to recent undo.")
                # Retention: We do not pop here. It will be applied on the next show after the lockout.
            else:
                data = _pregenerated_data.pop(card.id)
                logger.debug(f"AI-Hints: Applying pre-generated data for card {card.id}")
                _apply_results_to_card(card, data, is_manual=False, skip_redraw=True)
                # Now that this card is done, pre-generate the NEXT one
                _trigger_next_pregeneration(card.id)
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

            # Time-gated regeneration: regenerate if the generation time stored on
            # the card is older than the configured minimum generation time.
            regen_old_time = False
            if (
                not force_regen
                and not regen_old
                and config.get("auto_regenerate_if_old_time", False)
                and card_has_hints(card)
            ):
                min_time = config.get("auto_regenerate_min_time", "").strip()
                saved_time = _card_saved_generation_time(card)
                if min_time and _time_less_than(saved_time, min_time):
                    regen_old_time = True
                    logger.info(
                        "AI-Hints: Card %s saved generation time '%s' < min '%s'; queuing regeneration.",
                        card.id, saved_time, min_time
                    )

            if needs_generation or force_regen or regen_old or regen_old_time:
                logger.info(f"AI-Hints: Auto-generating hints for card {card.id} (force_regen={force_regen}, regen_old={regen_old}, regen_old_time={regen_old_time}).")
                generate_hints(is_manual=False, card=card)
            else:
                # Current card is already good. Pre-generate the NEXT one.
                _trigger_next_pregeneration(card.id)

    gui_hooks.reviewer_did_show_question.append(on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_trigger_frontend_setup)
    
    def _on_reviewer_init(reviewer):
        global _reviewer_is_ending
        _reviewer_is_ending = False
        
    gui_hooks.reviewer_did_init.append(_on_reviewer_init)
    
    # Close popup on next card or when leaving reviewer
    def _on_reviewer_end():
        global _reviewer_is_ending
        _reviewer_is_ending = True
        close_popup_if_open()
        
        # Clear transient session markers to prevent bleed between sessions
        _just_generated_card_ids.clear()
        _just_cleared_card_ids.clear()
        _generated_hint_cache.clear()
        
    gui_hooks.reviewer_did_show_question.append(lambda _card: close_popup_if_open())
    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.profile_will_close.append(_on_reviewer_end)
    
    # Sync UI and caches on undo operations
    def on_undo(changes):
        global _last_undo_time
        _last_undo_time = time.time()
        
        # When Anki undos, it often reverts multiple notes/cards.
        # To be safe, we clear ALL recently generated markers, caches and pre-gen buffers.
        logger.info("AI-Hints: Handling Undo. Wiping all transient session data to prevent bleed.")
        _just_generated_card_ids.clear()
        _just_cleared_card_ids.clear()
        _generated_hint_cache.clear()

        if mw.reviewer and mw.reviewer.card:
            # Force UI setup for the restored card
            _trigger_frontend_setup(mw.reviewer.card)

    gui_hooks.state_did_undo.append(on_undo)
    
    _hooks_registered = True
