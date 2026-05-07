import os
from aqt import mw, gui_hooks
from aqt.utils import showInfo, showWarning
from .ai_client import AIClient
from .card_parser import CardParser
from .config_ui import on_config_dialog
from aqt.qt import QMessageBox
from .logger import logger

def show_api_error_dialog(provider, is_custom=False):
    msg = QMessageBox(mw)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle("AI-Hints")
    if is_custom:
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
    with open(os.path.join(addon_dir, "web", "style.css"), "r") as f:
        css = f.read()
    with open(os.path.join(addon_dir, "web", "script.js"), "r") as f:
        js = f.read()

    web_content.head += f"<style>{css}</style>"
    web_content.body += f"<script>{js}</script>"

def on_webview_did_receive_js_message(handled, message, context):
    if message == "ai_hints_generate":
        generate_hints()
        return (True, None)
    return handled

def generate_hints():
    card = mw.reviewer.card
    if not card:
        return

    import sys
    sfm = sys.modules.get("1046608507.reviewer")
    if sfm:
        try:
            if mw.reviewer.state == "question":
                sfm.clear_question_timeouts(mw.reviewer)
                sfm.set_answer_timeouts(mw.reviewer)
            elif mw.reviewer.state == "answer":
                sfm.clear_answer_timeouts(mw.reviewer)
                sfm.set_question_timeouts(mw.reviewer)
        except Exception as e:
            logger.error(f"Failed to restart speed focus timer: {e}")

    config = mw.addonManager.getConfig(__name__)
    
    provider = config.get("ai_provider", "openai")
    if provider != "local":
        if provider in config.get("custom_providers", {}):
            api_key = config.get("custom_providers", {}).get(provider, {}).get("api_key")
            if not api_key:
                show_api_error_dialog(provider, is_custom=True)
                return
        else:
            api_key = config.get("api_keys", {}).get(provider)
            if not api_key:
                show_api_error_dialog(provider, is_custom=False)
                return

    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {}),
        config.get("storage_mode", "json")
    )
    client = AIClient(config)

    front, back = parser.get_note_content(card.note())

    def on_done(future):
        try:
            options = future.result()
        except Exception as e:
            logger.error(f"AI-Hints Future Error: {e}")
            options = []

        if not options:
            showInfo("AI-Hints: Failed to generate hints. Check your API key and provider settings.")
            mw.reviewer.refresh()
            return
            
        note = card.note()
        toggles = {
            "show_hints_button": config.get("show_hints_button", True),
            "show_options_button": config.get("show_options_button", True)
        }
        if parser.update_note_with_hints(note, options, toggles):
            note.flush()
            mw.reviewer.refresh()

    mw.taskman.run_in_background(
        lambda: client.generate_options(front, back),
        on_done
    )

def init_hooks():
    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(on_webview_did_receive_js_message)
