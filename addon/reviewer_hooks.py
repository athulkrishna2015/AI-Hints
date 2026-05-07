import os
import json
from aqt import mw, gui_hooks
from aqt.utils import showInfo
from .ai_client import AIClient
from .card_parser import CardParser
from .config_ui import ADDON_PACKAGE, on_config_dialog
from aqt.qt import QMessageBox
from .logger import logger

_hooks_registered = False

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

def on_webview_will_set_content(web_content, context):
    # Determine if we are in the reviewer context
    # Use getattr to safely handle objects without .name attribute
    is_reviewer = (
        getattr(context, "name", None) == "reviewer" or 
        type(context).__name__ == "Reviewer" or
        (context is None and any("reviewer.css" in c for c in web_content.css))
    )
    
    if not is_reviewer:
        return

    addon_dir = get_addon_dir()
    
    # Read CSS and JS
    with open(os.path.join(addon_dir, "web", "style.css"), "r", encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(addon_dir, "web", "script.js"), "r", encoding="utf-8") as f:
        js = f.read()

    card_payload = json.dumps(_card_context_payload(context))

    web_content.head += f"<style>{css}</style>"
    web_content.body += f"<script>window.aiHintsCurrentCard = {card_payload};</script>"
    web_content.body += f"<script>{js}</script>"

def on_webview_did_receive_js_message(handled, message, context):
    if message == "ai_hints_generate":
        generate_hints()
        return (True, None)
    if message == "ai_hints_restart_speed_focus":
        restart_speed_focus_timer()
        return (True, None)
    return handled

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
                    const slot = document.getElementById('ai-hints-bottom-slot');
                    if (slot) {
                        slot.remove();
                    }
                })();
            """)
        except Exception as e:
            logger.error(f"Failed to remove AI-Hints bottom button: {e}")
        return

    try:
        bottom.eval("""
            (function() {
                const middle = document.getElementById('middle');
                if (!middle || document.getElementById('ai-hints-bottom-slot')) {
                    return;
                }

                const button = document.createElement('button');
                button.id = 'ai-hints-bottom-button';
                button.type = 'button';
                button.title = 'Generate AI hints';
                button.textContent = 'AI Hints';
                button.onclick = function() {
                    if (typeof pycmd === 'function') {
                        pycmd('ai_hints_generate');
                    }
                };

                const slot = document.createElement('td');
                slot.id = 'ai-hints-bottom-slot';
                slot.className = 'stat2';
                slot.setAttribute('align', 'center');
                slot.style.paddingRight = '6px';
                slot.appendChild(button);

                const row = middle.querySelector('table tr');
                if (row) {
                    row.insertBefore(slot, row.firstChild);
                    return;
                }

                const wrapper = document.createElement('table');
                wrapper.setAttribute('cellpadding', '0');
                const wrapperRow = document.createElement('tr');
                wrapperRow.appendChild(slot);
                wrapper.appendChild(wrapperRow);
                middle.appendChild(wrapper);
            })();
        """)
    except Exception as e:
        logger.error(f"Failed to add AI-Hints bottom button: {e}")

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
    if not reviewer:
        return

    try:
        refresh = getattr(reviewer, "refresh", None)
        if callable(refresh):
            refresh()
            return

        redraw = getattr(reviewer, "_redraw_current_card", None)
        if callable(redraw):
            redraw()
            return

        card = getattr(reviewer, "card", None)
        if card and hasattr(card, "load"):
            card.load()

        if getattr(reviewer, "state", None) == "answer":
            show_answer = getattr(reviewer, "_showAnswer", None)
            if callable(show_answer):
                show_answer()
                return

        show_question = getattr(reviewer, "_showQuestion", None)
        if callable(show_question):
            show_question()
    except Exception as e:
        logger.error(f"Failed to refresh reviewer card: {e}")

def generate_hints():
    card = mw.reviewer.card
    if not card:
        return

    restart_speed_focus_timer()

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    
    provider = config.get("ai_provider", "openai")

    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json")
    )
    client = AIClient(config)
    if not client.has_any_ready_provider():
        is_custom = provider in (config.get("custom_providers") or {})
        show_api_error_dialog(provider if provider else None, is_custom=is_custom)
        return

    front, back = parser.get_note_content(card.note(), card)

    def on_done(future):
        try:
            data = future.result()
        except Exception as e:
            logger.error(f"AI-Hints Future Error: {e}")
            data = {"hints": [], "options": []}

        # Check if the card is still the same one we started with
        is_current = mw.reviewer.card and mw.reviewer.card.id == card.id

        if not data or (not data.get("hints") and not data.get("options")):
            if is_current:
                showInfo("AI-Hints: Failed to generate hints. Check your API key and provider settings.")
                refresh_current_card()
            return
            
        note = card.note()
        toggles = {
            "show_hints_button": config.get("show_hints_button", True),
            "show_options_button": config.get("show_options_button", True)
        }
        if parser.update_note_with_hints(note, data, toggles, card):
            note.flush()
            if is_current:
                refresh_current_card()
        elif is_current:
            showInfo("AI-Hints: No hints or options were generated.")

    mw.taskman.run_in_background(
        lambda: client.generate_options(front, back),
        on_done
    )

def init_hooks():
    global _hooks_registered
    if _hooks_registered:
        return
    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(on_webview_did_receive_js_message)
    gui_hooks.reviewer_did_show_question.append(update_bottom_bar_button)
    gui_hooks.reviewer_did_show_answer.append(update_bottom_bar_button)
    _hooks_registered = True
