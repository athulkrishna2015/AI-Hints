import os
import json
from aqt import mw, gui_hooks
from .ai_client import AIClient
from .card_parser import CardParser
from .config_ui import ADDON_PACKAGE, on_config_dialog
from aqt.qt import QMessageBox, QMenu, QAction, QPoint, Qt, QDialog, QVBoxLayout
from .logger import logger, info, tooltip

_hooks_registered = False
_generating_card_ids = set()
_just_generated_card_ids = set()
_generated_hint_cache = {}
_popup_dialog_instance = None
MAX_HINT_CACHE_SIZE = 200
_current_card_has_data = False

_review_token = 0

_css_cache = None
_js_cache = None

def get_web_assets():
    global _css_cache, _js_cache
    if _css_cache is None or _js_cache is None:
        addon_dir = os.path.dirname(__file__)
        with open(os.path.join(addon_dir, "web", "style.css"), "r", encoding="utf-8") as f:
            _css_cache = f.read()
        with open(os.path.join(addon_dir, "web", "script.js"), "r", encoding="utf-8") as f:
            _js_cache = f.read()
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

def _card_context_payload(context):
    card = getattr(context, "card", None)
    if not card:
        reviewer = context if type(context).__name__ == "Reviewer" else getattr(context, "reviewer", None)
        card = getattr(reviewer, "card", None) or getattr(mw.reviewer, "card", None)
    
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

def on_webview_will_set_content(web_content, context):
    if type(context).__name__ == "ReviewerBottomBar":
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        if config.get("show_in_bottom_bar", False):
            web_content.body += f"<script>{_bottom_bar_button_script()}</script>"
        return

    # Determine if we are in the reviewer context
    is_reviewer = (
        getattr(context, "name", None) == "reviewer" or 
        type(context).__name__ == "Reviewer" or
        (context is None and any("reviewer.css" in c for c in web_content.css))
    )
    
    if not is_reviewer:
        return

    global _current_card_has_data
    _current_card_has_data = False

    css, js = get_web_assets()

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        target_fields=config.get("target_fields", []),
        note_type_fields=config.get("note_type_fields", {}),
        storage_mode=config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters")
    )

    card = getattr(context, "card", None)
    if not card:
        reviewer = context if type(context).__name__ == "Reviewer" else getattr(context, "reviewer", None)
        card = getattr(reviewer, "card", None) or getattr(mw.reviewer, "card", None)

    hints_block = ""
    auto_reveal = False
    if card:
        try:
            # Force reload to ensure we don't have stale data (especially for new cards)
            try:
                card.load()
                card.note().load()
            except Exception:
                pass

            hints_block = parser.find_hints_block(card.note(), card) or ""
            if not hints_block:
                cached = _cached_hints_for_card(card)
                if cached:
                    hints_block = parser.build_hints_block(
                        cached.get("data", {}),
                        cached.get("toggles", {}),
                        card,
                    )
            
            if hints_block:
                _current_card_has_data = True
            
            if card.id in _just_generated_card_ids:
                auto_reveal = True
                # Don't discard yet; we want it to persist for the 'answer' side too.
                # It will be cleared when the card actually changes.
        except Exception as e:
            logger.error(f"Failed to find hints block in on_webview_will_set_content: {e}")

    card_payload = json.dumps(_card_context_payload(context))
    ui_payload = json.dumps({
        "show_on_card": config.get("show_on_card", True),
        "auto_reveal": auto_reveal,
        "auto_show_hints": config.get("auto_show_hints", False),
        "auto_show_options": config.get("auto_show_options", False),
        "mathjax_format": config.get("mathjax_format", "delimiters"),
        "review_token": _review_token,
        "is_generating": card.id in _generating_card_ids if card else False
    })

    if config.get("auto_show_hints", False) or config.get("auto_show_options", False):
        logger.info(
            "Auto-show active for card %s (hints=%s, options=%s)",
            card.id if card else "unknown",
            config.get("auto_show_hints", False),
            config.get("auto_show_options", False)
        )

    web_content.head += f"<style>{css}</style>"
    if hints_block:
        web_content.body += hints_block
    web_content.body += f"<script>window.aiHintsCurrentCard = {card_payload};</script>"
    web_content.body += f"<script>window.aiHintsUiConfig = {ui_payload};</script>"
    web_content.body += f"<script>{js}</script>"
    
    # Debug log for frontend
    web_content.body += f"<script>console.log('AI-Hints: Content injected for card {card.id if card else 'unknown'} (auto_reveal={auto_reveal})');</script>"

def _trigger_frontend_setup(card):
    if not card:
        return
    
    # Clear auto-reveal state for OTHER cards when moving to a new one
    to_remove = [cid for cid in _just_generated_card_ids if cid != card.id]
    for cid in to_remove:
        _just_generated_card_ids.discard(cid)

    card_data = {"id": str(card.id), "ord": int(card.ord)}
    mw.reviewer.web.eval(f"""
        (function() {{
            var data = {json.dumps(card_data)};
            function trySetup() {{
                if (typeof window.aiHintsSetup === 'function') {{
                    window.aiHintsSetup(data);
                }} else {{
                    setTimeout(trySetup, 50);
                }}
            }}
            trySetup();
        }})();
    """)

def on_webview_did_receive_js_message(handled, message, context):
    if message == "ai_hints_generate":
        generate_hints()
        return (True, None)
    if message == "ai_hints_clear":
        clear_hints()
        return (True, None)
    if message == "ai_hints_refresh":
        refresh_current_card()
        return (True, None)
    if message == "ai_hints_restart_speed_focus":
        restart_speed_focus_timer()
        return (True, None)
    if message == "ai_hints_show_menu":
        show_bottom_bar_menu()
        return (True, None)
    return handled

def clear_hints():
    card = mw.reviewer.card
    if not card:
        return

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters")
    )
    
    note = card.note()
    if parser.clear_hints_from_note(note, card):
        try:
            mw.col.add_custom_undo_entry("Clear AI Hints")
            mw.col.update_note(note)
            mw.col.merge_undo_entries(1)
        except Exception:
            mw.col.update_note(note)
        _forget_generated_hints(card)
        logger.info("AI-Hints cleared for card %s", card.id)
        tooltip("AI-Hints: Cleared.")
        try:
            mw.reviewer.web.eval("if (window.aiHintsClearData) { window.aiHintsClearData(); }")
        except Exception:
            refresh_current_card()
    elif _cached_hints_for_card(card):
        _forget_generated_hints(card)
        tooltip("AI-Hints: Cleared.")
        try:
            mw.reviewer.web.eval("if (window.aiHintsClearData) { window.aiHintsClearData(); }")
        except Exception:
            refresh_current_card()
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
        mathjax_format=config.get("mathjax_format", "delimiters")
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
    action = menu.addAction("Clear AI-Hints")
    action.setEnabled(bool(_selected_browser_card_ids(browser)))
    action.triggered.connect(lambda _checked=False, b=browser: clear_ai_hints_from_browser_selection(b))

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

def refresh_current_card():
    reviewer = getattr(mw, "reviewer", None)
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
        if getattr(reviewer, "state", None) == "question":
            show_question = getattr(reviewer, "_showQuestion", None)
            if callable(show_question):
                show_question()
                return

        if hasattr(reviewer, "refresh") and callable(reviewer.refresh):
            reviewer.refresh()
            return

        if getattr(reviewer, "state", None) == "answer":
            show_answer = getattr(reviewer, "_showAnswer", None)
            if callable(show_answer):
                show_answer()
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

def generate_hints():
    card = mw.reviewer.card
    if not card:
        return

    card_id = getattr(card, "id", None)
    if card_id in _generating_card_ids:
        tooltip("AI-Hints: Generation already in progress.")
        return
    _generating_card_ids.add(card_id)

    restart_speed_focus_timer()

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    
    provider = config.get("ai_provider", "openai")

    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json"),
        mathjax_format=config.get("mathjax_format", "delimiters")
    )
    client = AIClient(config)
    if not client.has_any_ready_provider():
        _generating_card_ids.discard(card_id)
        is_custom = provider in (config.get("custom_providers") or {})
        show_api_error_dialog(provider if provider else None, is_custom=is_custom)
        return

    front, back = parser.get_note_content(card.note(), card)
    logger.info("AI-Hints generation started for card %s using provider: %s", card_id, provider)
    tooltip("AI-Hints: Generating...")

    def on_done(data):
        try:
            # Check if the card is still the same one we started with
            is_current = mw.reviewer.card and mw.reviewer.card.id == card.id
            if not is_current:
                logger.info("AI-Hints: User moved to another card. Discarding generated data to prevent database and undo conflicts.")
                return

            if not data or (not data.get("hints") and not data.get("options")):
                info("AI-Hints: Failed to generate hints. Check your API key and provider settings.")
                refresh_current_card()
                return

            data = parser.normalize_hint_data(data)
            logger.info(
                "AI-Hints response for card %s: %s",
                card_id,
                json.dumps(data, ensure_ascii=False),
            )
                
            note = card.note()
            toggles = {
                "show_hints_button": config.get("show_hints_button", True),
                "show_options_button": config.get("show_options_button", True)
            }
            if parser.update_note_with_hints(note, data, toggles, card):
                try:
                    mw.col.add_custom_undo_entry("Generate AI Hints")
                    mw.col.update_note(note)
                    mw.col.merge_undo_entries(1)
                except Exception:
                    mw.col.update_note(note)
                _remember_generated_hints(card, data, toggles)
                logger.info(
                    "AI-Hints saved %d hints and %d options to note %s for card %s.",
                    len(data.get("hints", [])),
                    len(data.get("options", [])),
                    getattr(note, "id", ""),
                    card_id,
                )
                _just_generated_card_ids.add(card.id)
                tooltip("AI-Hints: Generated. Use Show Hints / Show Options on the card.")
                try:
                    mw.reviewer.web.eval(
                        f"if (window.aiHintsUpdateData) {{ window.aiHintsUpdateData({json.dumps(data)}); }}"
                    )
                except Exception as e:
                    logger.error(f"AI-Hints direct web update failed: {e}")
                    refresh_current_card()
                
                if config.get("show_in_popup", False):
                    global _popup_dialog_instance
                    close_popup_if_open()
                    html_content = parser._build_html_block(data)
                    _popup_dialog_instance = ResultsPopup(mw, html_content)
                    _popup_dialog_instance.show()
            else:
                info("AI-Hints: No hints or options were generated.")
        finally:
            _generating_card_ids.discard(card_id)

    import threading

    def run_async():
        try:
            res = client.generate_options(front, back)
            mw.taskman.run_on_main(lambda: on_done(res))
        except Exception as e:
            logger.error(f"AI-Hints generation error: {e}")
            mw.taskman.run_on_main(lambda: on_done({"hints": [], "options": []}))

    threading.Thread(target=run_async, daemon=True).start()

def init_hooks():
    global _hooks_registered
    if _hooks_registered:
        return
    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(on_webview_did_receive_js_message)
    gui_hooks.browser_will_show_context_menu.append(on_browser_context_menu)
    
    # Bottom bar button
    gui_hooks.reviewer_did_show_question.append(update_bottom_bar_button)
    gui_hooks.reviewer_did_show_answer.append(update_bottom_bar_button)
    
    # Frontend setup trigger
    def on_show_question(card):
        global _review_token
        _review_token += 1
        _trigger_frontend_setup(card)
        
        # Auto generate for new cards if configured and no data exists
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        if config.get("auto_generate_new", False) and card:
            if not _current_card_has_data:
                logger.info(f"Auto-generating hints for new card {card.id}...")
                generate_hints()

    gui_hooks.reviewer_did_show_question.append(on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_trigger_frontend_setup)
    
    # Close popup on next card or when leaving reviewer
    gui_hooks.reviewer_did_show_question.append(lambda _card: close_popup_if_open())
    gui_hooks.reviewer_will_end.append(close_popup_if_open)
    
    # Sync UI and caches on undo operations
    def on_undo(changes):
        if mw.reviewer and mw.reviewer.card:
            card = mw.reviewer.card
            _forget_generated_hints(card)
            try:
                mw.reviewer.web.eval("if (window.aiHintsClearData) { window.aiHintsClearData(); }")
            except Exception:
                pass
            refresh_current_card()

    gui_hooks.state_did_undo.append(on_undo)
    
    _hooks_registered = True
