import os
from aqt import mw, gui_hooks
from aqt.webview import WebView
from .ai_client import AIClient
from .card_parser import CardParser

def get_addon_dir():
    return os.path.dirname(__file__)

def on_webview_will_set_content(web_content, context):
    if not context or context.name != "reviewer":
        return

    addon_dir = get_addon_dir()
    
    # Read CSS and JS
    with open(os.path.join(addon_dir, "web", "style.css"), "r") as f:
        css = f.read()
    with open(os.path.join(addon_dir, "web", "script.js"), "r") as f:
        js = f.read()

    web_content.head += f"<style>{css}</style>"
    web_content.body += f"<script>{js}</script>"

def on_webview_did_receive_message(handled, message, context):
    if message == "ai_hints_generate":
        generate_hints()
        return (True, None)
    return handled

def generate_hints():
    card = mw.reviewer.card
    if not card:
        return

    config = mw.addonManager.getConfig(__name__)
    parser = CardParser(
        config.get("target_fields", []),
        config.get("note_type_fields", {})
    )
    client = AIClient(config)

    front, back = parser.get_note_content(card.note())

    def on_success(options):
        if not options:
            mw.utils.showInfo("AI-Hints: Failed to generate hints. Check your API key and provider settings.")
            mw.reviewer.refresh()
            return
            
        note = card.note()
        if parser.update_note_with_hints(note, options):
            note.flush()
            mw.reviewer.refresh()

    mw.taskman.run_in_background(
        lambda: client.generate_options(front, back),
        on_success
    )

def init_hooks():
    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.webview_did_receive_message.append(on_webview_did_receive_message)
