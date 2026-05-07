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
_popup_dialog_instance = None

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

    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    parser = CardParser(
        target_fields=config.get("target_fields", []),
        note_type_fields=config.get("note_type_fields", {}),
        storage_mode=config.get("storage_mode", "json")
    )

    card = getattr(context, "card", None) or getattr(mw.reviewer, "card", None)
    hints_block = ""
    if card:
        try:
            hints_block = parser.find_hints_block(card.note(), card) or ""
        except Exception as e:
            logger.error(f"Failed to find hints block in on_webview_will_set_content: {e}")

    card_payload = json.dumps(_card_context_payload(context))
    ui_payload = json.dumps({
        "show_on_card": config.get("show_on_card", True),
    })

    web_content.head += f"<style>{css}</style>"
    if hints_block:
        web_content.body += hints_block
    web_content.body += f"<script>window.aiHintsCurrentCard = {card_payload};</script>"
    web_content.body += f"<script>window.aiHintsUiConfig = {ui_payload};</script>"
    web_content.body += f"<script>{js}</script>"

def on_webview_did_receive_js_message(handled, message, context):
    if message == "ai_hints_generate":
        generate_hints()
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
                const outer = document.getElementById('outer');
                const timer = document.getElementById('time');
                const rightCell = timer
                    ? timer.closest('td')
                    : (outer ? outer.querySelector('td.stat:last-child') : null);
                if (!rightCell) {
                    return;
                }
                rightCell.style.whiteSpace = 'nowrap';

                function updateAIHintsBottomButton() {
                    const slot = document.getElementById('ai-hints-bottom-slot');
                    const button = document.getElementById('ai-hints-bottom-button');
                    if (!slot || !button || !outer) {
                        return;
                    }

                    slot.style.display = 'inline-block';
                    button.textContent = window.innerWidth < 520 ? 'AI' : 'AI Hints';

                    if (outer.scrollWidth > outer.clientWidth && button.textContent !== 'AI') {
                        button.textContent = 'AI';
                    }
                    if (outer.scrollWidth > outer.clientWidth && window.innerWidth < 320) {
                        slot.style.display = 'none';
                    }
                }

                if (document.getElementById('ai-hints-bottom-slot')) {
                    updateAIHintsBottomButton();
                    return;
                }

                const button = document.createElement('button');
                button.id = 'ai-hints-bottom-button';
                button.type = 'button';
                button.title = 'Generate AI hints';
                button.textContent = 'AI Hints';
                button.style.minWidth = '0';
                button.style.paddingLeft = '4px';
                button.style.paddingRight = '4px';
                button.onclick = function() {
                    if (typeof pycmd === 'function') {
                        pycmd('ai_hints_show_menu');
                    }
                };

                const slot = document.createElement('span');
                slot.id = 'ai-hints-bottom-slot';
                slot.style.display = 'inline-block';
                slot.style.marginRight = '4px';
                slot.style.whiteSpace = 'nowrap';
                slot.appendChild(button);

                rightCell.insertBefore(slot, rightCell.firstChild);
                updateAIHintsBottomButton();
                if (!window.aiHintsBottomResizeBound) {
                    window.aiHintsBottomResizeBound = true;
                    window.addEventListener('resize', updateAIHintsBottomButton);
                }
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
        # Explicitly reload the card from database to get latest field content
        card = getattr(reviewer, "card", None)
        if card:
            card.load()

        refresh = getattr(reviewer, "refresh", None)
        if callable(refresh):
            refresh()
            return

        redraw = getattr(reviewer, "_redraw_current_card", None)
        if callable(redraw):
            redraw()
            return

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

def show_bottom_bar_menu():
    reviewer = getattr(mw, "reviewer", None)
    if not reviewer or not reviewer.card:
        return

    menu = QMenu(mw)
    
    # 1. Show Hint
    a_hint = QAction("Show Hint", menu)
    a_hint.triggered.connect(lambda: reviewer.web.eval("document.querySelector('[data-ai-hints-action=\"toggle-hints\"]').click()"))
    menu.addAction(a_hint)
    
    # 2. Show Options
    a_opts = QAction("Show Options", menu)
    a_opts.triggered.connect(lambda: reviewer.web.eval("document.querySelector('[data-ai-hints-action=\"toggle-options\"]').click()"))
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
        config.get("storage_mode", "json")
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

    def on_done(future):
        try:
            try:
                data = future.result()
            except Exception as e:
                logger.error(f"AI-Hints Future Error: {e}")
                data = {"hints": [], "options": []}

            # Check if the card is still the same one we started with
            is_current = mw.reviewer.card and mw.reviewer.card.id == card.id

            if not data or (not data.get("hints") and not data.get("options")):
                if is_current:
                    info("AI-Hints: Failed to generate hints. Check your API key and provider settings.")
                    refresh_current_card()
                return

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
                note.flush()
                logger.info(
                    "AI-Hints saved %d hints and %d options to note %s for card %s.",
                    len(data.get("hints", [])),
                    len(data.get("options", [])),
                    getattr(note, "id", ""),
                    card_id,
                )
                if is_current:
                    tooltip("AI-Hints: Generated. Use Show Hints / Show Options on the card.")
                    refresh_current_card()
                    
                    if config.get("show_in_popup", False):
                        global _popup_dialog_instance
                        close_popup_if_open()
                        html_content = parser._build_html_block(data)
                        _popup_dialog_instance = ResultsPopup(mw, html_content)
                        _popup_dialog_instance.show()
            elif is_current:
                info("AI-Hints: No hints or options were generated.")
        finally:
            _generating_card_ids.discard(card_id)

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
    
    # Close popup on next card or when leaving reviewer
    gui_hooks.reviewer_did_show_question.append(lambda _card: close_popup_if_open())
    gui_hooks.reviewer_will_end.append(close_popup_if_open)
    
    _hooks_registered = True
